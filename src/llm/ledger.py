"""The cost ledger: every model call written down, and monthly spending caps.

The API collects the usage events of one request (``usage.collect``) and
writes them here in one transaction, inside the caller's tenant. Before a
question is sent to a model, ``check_caps`` refuses it when the account or
the whole service has spent its monthly budget:

    DOCMIND_TENANT_MONTHLY_BUDGET_USD   per account (default 1.00)
    DOCMIND_MONTHLY_BUDGET_USD          all accounts together (default 5.00)

Set either to "off" for no cap. The defaults keep a public demo close to $0.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.llm.errors import SpendingCapError
from src.llm.usage import UsageEvent

logger = logging.getLogger("docmind.ledger")


def _cap(name: str, default: float) -> float | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("off", "none", "unlimited"):
        return None
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def tenant_cap() -> float | None:
    return _cap("DOCMIND_TENANT_MONTHLY_BUDGET_USD", 1.00)


def global_cap() -> float | None:
    return _cap("DOCMIND_MONTHLY_BUDGET_USD", 5.00)


def _month_start(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return date(now.year, now.month, 1)


def record(
    events: list[UsageEvent],
    *,
    tenant_id: str,
    user_id: str | None = None,
    thread_id: str | None = None,
    document_id: str | None = None,
) -> None:
    """Write the calls of one request (best effort: a ledger failure never fails an answer)."""
    if not events:
        return
    from src.stores.pg import as_uuid
    from src.db.pool import tenant_tx

    try:
        with tenant_tx(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO llm_usage (user_id, thread_id, document_id, purpose, kind, provider, model,
                           input_tokens, output_tokens, cost_usd, latency_ms, first_token_ms, ok, error_kind)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (
                            as_uuid(user_id) if user_id else None,
                            thread_id,
                            as_uuid(document_id) if document_id else None,
                            e.purpose,
                            e.kind,
                            e.provider,
                            e.model,
                            e.input_tokens,
                            e.output_tokens,
                            e.cost_usd,
                            int(e.latency_ms),
                            int(e.first_token_ms) if e.first_token_ms is not None else None,
                            e.ok,
                            e.error_kind,
                        )
                        for e in events
                    ],
                )
            conn.execute(
                """INSERT INTO llm_spend_monthly (month, cost_usd, calls) VALUES (%s, %s, %s)
                   ON CONFLICT (month) DO UPDATE SET cost_usd = llm_spend_monthly.cost_usd + EXCLUDED.cost_usd,
                                                     calls = llm_spend_monthly.calls + EXCLUDED.calls""",
                (_month_start(), sum(e.cost_usd for e in events), len(events)),
            )
    except Exception:
        logger.exception("could not write %d usage rows to the ledger", len(events))


def tenant_month_spend(tenant_id: str) -> float:
    from src.db.pool import tenant_tx

    with tenant_tx(tenant_id) as conn:
        row = conn.execute(
            "SELECT coalesce(sum(cost_usd), 0) AS c FROM llm_usage WHERE created_at >= %s", (_month_start(),)
        ).fetchone()
    return float(row["c"])


def global_month_spend() -> float:
    from src.db.pool import app_tx

    with app_tx() as conn:
        row = conn.execute("SELECT cost_usd FROM llm_spend_monthly WHERE month = %s", (_month_start(),)).fetchone()
    return float(row["cost_usd"]) if row else 0.0


@dataclass(frozen=True)
class CapStatus:
    tenant_spend: float
    tenant_cap: float | None
    global_spend: float
    global_cap: float | None

    @property
    def blocked(self) -> str | None:
        if self.tenant_cap is not None and self.tenant_spend >= self.tenant_cap:
            return f"This account has used its monthly model budget (${self.tenant_spend:.2f} of ${self.tenant_cap:.2f})."
        if self.global_cap is not None and self.global_spend >= self.global_cap:
            return f"The service has used its monthly model budget (${self.global_spend:.2f} of ${self.global_cap:.2f})."
        return None


def cap_status(tenant_id: str) -> CapStatus:
    return CapStatus(tenant_month_spend(tenant_id), tenant_cap(), global_month_spend(), global_cap())


def check_caps(tenant_id: str) -> None:
    """Raise SpendingCapError when a monthly budget is used up."""
    reason = cap_status(tenant_id).blocked
    if reason:
        raise SpendingCapError(reason + " It resets on the 1st of next month (UTC).")


def usage_summary(tenant_id: str, *, recent: int = 20) -> dict:
    """The account's spending this month: totals, by model and purpose, and the latest calls."""
    from src.db.pool import tenant_tx

    start = _month_start()
    with tenant_tx(tenant_id) as conn:
        by_model = conn.execute(
            """SELECT provider, model, kind, count(*) AS calls, sum(input_tokens) AS input_tokens,
                      sum(output_tokens) AS output_tokens, sum(cost_usd) AS cost_usd
                 FROM llm_usage WHERE created_at >= %s GROUP BY provider, model, kind ORDER BY sum(cost_usd) DESC""",
            (start,),
        ).fetchall()
        by_purpose = conn.execute(
            """SELECT purpose, count(*) AS calls, sum(cost_usd) AS cost_usd
                 FROM llm_usage WHERE created_at >= %s GROUP BY purpose ORDER BY sum(cost_usd) DESC""",
            (start,),
        ).fetchall()
        by_day = conn.execute(
            """SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*) AS calls, sum(cost_usd) AS cost_usd
                 FROM llm_usage WHERE created_at >= %s GROUP BY 1 ORDER BY 1""",
            (start,),
        ).fetchall()
        chat = conn.execute(
            """SELECT count(*) FILTER (WHERE purpose = 'answer' AND ok) AS questions,
                      coalesce(sum(cost_usd) FILTER (WHERE thread_id IS NOT NULL), 0) AS cost_usd
                 FROM llm_usage WHERE created_at >= %s""",
            (start,),
        ).fetchone()
        documents = conn.execute(
            """SELECT u.document_id, d.file_name, d.page_count,
                      coalesce(sum(u.cost_usd) FILTER (WHERE u.purpose = 'ingest'), 0) AS ingest_usd,
                      coalesce(sum(u.cost_usd) FILTER (WHERE u.purpose = 'fields'), 0) AS fields_usd,
                      count(*) AS calls
                 FROM llm_usage u LEFT JOIN documents d ON d.id = u.document_id
                WHERE u.document_id IS NOT NULL AND u.thread_id IS NULL
                GROUP BY u.document_id, d.file_name, d.page_count
                ORDER BY max(u.created_at) DESC LIMIT 50"""
        ).fetchall()
        latest = conn.execute(
            """SELECT created_at, purpose, provider, model, input_tokens, output_tokens, cost_usd, latency_ms, ok, error_kind
                 FROM llm_usage ORDER BY created_at DESC, id DESC LIMIT %s""",
            (recent,),
        ).fetchall()
    status = cap_status(tenant_id)

    def money(v) -> float:
        return round(float(v or 0), 6)

    return {
        "month": start.isoformat(),
        "spent_usd": money(status.tenant_spend),
        "cap_usd": status.tenant_cap,
        "service_spent_usd": money(status.global_spend),
        "service_cap_usd": status.global_cap,
        "by_model": [dict(r) | {"cost_usd": money(r["cost_usd"])} for r in by_model],
        "by_purpose": [dict(r) | {"cost_usd": money(r["cost_usd"])} for r in by_purpose],
        "by_provider": _by_provider(by_model),
        "by_day": [{"day": r["day"].isoformat(), "calls": r["calls"], "cost_usd": money(r["cost_usd"])} for r in by_day],
        "questions": int(chat["questions"] or 0),
        "cost_per_question_usd": money(float(chat["cost_usd"] or 0) / chat["questions"]) if chat["questions"] else None,
        # documents ever read with model calls (vision on a page, schema fields), newest first
        "documents": [
            {
                "document_id": str(r["document_id"]),
                "file_name": r["file_name"] or "(deleted)",
                "page_count": r["page_count"] or 0,
                "ingest_usd": money(r["ingest_usd"]),
                "fields_usd": money(r["fields_usd"]),
                "calls": r["calls"],
            }
            for r in documents
        ],
        "latest": [
            dict(r) | {"cost_usd": money(r["cost_usd"]), "created_at": r["created_at"].isoformat()} for r in latest
        ],
    }


def _by_provider(rows) -> list[dict]:
    out: dict[str, dict] = {}
    for r in rows:
        p = out.setdefault(r["provider"] or "unknown", {"provider": r["provider"] or "unknown", "calls": 0, "cost_usd": 0.0})
        p["calls"] += r["calls"]
        p["cost_usd"] += float(r["cost_usd"] or 0)
    return sorted(({**p, "cost_usd": round(p["cost_usd"], 6)} for p in out.values()), key=lambda p: -p["cost_usd"])
