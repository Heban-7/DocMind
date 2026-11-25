"""Field extraction as a product feature: request, run (in the worker), read, review, export.

Every function works inside the caller's tenant (row-level security); the
worker runs extractions inside the document's tenant, like ingest.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from src.db import repos
from src.db.pool import tenant_tx
from src.db.repos import AccessDeniedError, Principal
from src.llm import ledger, usage
from src.schemas import values as V
from src.schemas.extract import ExtractionResult, extract_fields, normalize, page_images
from src.schemas.schema import Schema, all_schemas, get_schema
from src.stores.pg import as_uuid

logger = logging.getLogger("docmind.fields")

REVIEW_ACTIONS = ("confirm", "correct", "reject")


class FieldNotFoundError(KeyError):
    """No extraction (or no such field) for this document and schema."""


# --- requesting and running ---------------------------------------------------------------


def request_extraction(principal: Principal, document_id: str, schema_name: str) -> dict:
    """Queue an extraction; the worker runs it. Raises KeyError (unknown schema),
    AccessDeniedError, SpendingCapError or ValueError (document not ready)."""
    from src.jobs import queue

    schema = get_schema(schema_name)
    doc = repos.require_document(principal.tenant_id, document_id)
    if doc.status != "ready":
        raise ValueError(f"{doc.file_name} is still being read ({doc.pages_done} of {doc.page_count} pages).")
    ledger.check_caps(principal.tenant_id)
    with tenant_tx(principal.tenant_id) as conn:
        row = conn.execute(
            """INSERT INTO field_extractions (document_id, schema_name, schema_version, requested_by)
               VALUES (%s, %s, %s, %s) RETURNING id, created_at""",
            (doc.id, schema.name, schema.version, as_uuid(principal.user_id)),
        ).fetchone()
        extraction_id = str(row["id"])
        queue.enqueue(
            principal.tenant_id, doc.id, conn=conn, kind="extract_fields",
            payload={"extraction_id": extraction_id, "schema": schema.name},
        )
    return {"extraction_id": extraction_id, "status": "queued", "schema": schema.name, "document_id": doc.id}


def run_extraction(tenant_id: str, document_id: str, extraction_id: str, schema_name: str, *, llm=None) -> ExtractionResult:
    """What the worker does for an 'extract_fields' job."""
    from src.document.model import DocumentModel
    from src.llm.factory import get_text_client
    from src.storage.blobs import get_blob_store

    schema = get_schema(schema_name)
    with tenant_tx(tenant_id) as conn:
        conn.execute("UPDATE field_extractions SET status = 'running' WHERE id = %s", (extraction_id,))
    doc = repos.require_document(tenant_id, document_id)
    model = DocumentModel.model_validate_json(get_blob_store().local_path(doc.model_key).read_text(encoding="utf-8"))
    client = llm or get_text_client()
    if client is None:
        raise RuntimeError("No LLM is configured on this server.")
    try:
        with usage.purpose("fields"), usage.collect() as events:
            try:
                pdf = get_blob_store().local_path(doc.storage_key)
                result = extract_fields(model, schema, client, document_id=document_id, page_image=page_images(pdf))
            finally:
                ledger.record(events, tenant_id=tenant_id, document_id=document_id)
    except Exception as exc:
        with tenant_tx(tenant_id) as conn:
            conn.execute(
                "UPDATE field_extractions SET status = 'failed', error = %s, finished_at = now() WHERE id = %s",
                (f"{type(exc).__name__}: {exc}"[:500], extraction_id),
            )
        raise
    save_result(tenant_id, extraction_id, result)
    return result


def save_result(tenant_id: str, extraction_id: str, result: ExtractionResult) -> None:
    with tenant_tx(tenant_id) as conn:
        conn.execute("DELETE FROM extracted_fields WHERE extraction_id = %s", (extraction_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO extracted_fields (extraction_id, document_id, schema_name, field, value, printed, unit,
                       page_number, ref, bbox, confidence, grounded, status, reasons, alternatives)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        extraction_id, result.document_id, result.schema, f.name,
                        Jsonb(f.value) if f.value is not None else None, f.printed, f.unit, f.page, f.ref,
                        Jsonb(f.bbox) if f.bbox else None, f.confidence, f.grounded, f.status,
                        f.reasons, Jsonb(f.alternatives),
                    )
                    for f in result.fields.values()
                ],
            )
        conn.execute(
            """UPDATE field_extractions SET status = 'done', model = %s, pages_read = %s, rules = %s, cost_usd = %s,
                      seconds = %s, finished_at = now(), error = NULL WHERE id = %s""",
            (result.model, result.pages_read, Jsonb(result.rules), result.usage.get("cost_usd", 0.0), result.seconds, extraction_id),
        )


# --- reading -------------------------------------------------------------------------------


def _field_row(r: dict) -> dict:
    return {
        "field": r["field"],
        "value": r["value"],
        "printed": r["printed"],
        "unit": r["unit"],
        "page": r["page_number"],
        "ref": r["ref"],
        "bbox": r["bbox"],
        "confidence": round(float(r["confidence"]), 3),
        "grounded": r["grounded"],
        "status": r["status"],
        "reasons": list(r["reasons"] or []),
        "alternatives": r["alternatives"] or [],
        "machine_value": r["machine_value"],
        "reviewed_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
    }


def latest_extraction(principal: Principal, document_id: str, schema_name: str | None = None) -> dict:
    """The newest extraction of a document (for one schema, or the newest of any)."""
    doc = repos.require_document(principal.tenant_id, document_id)
    with tenant_tx(principal.tenant_id) as conn:
        ex = conn.execute(
            """SELECT * FROM field_extractions WHERE document_id = %s AND (%s::text IS NULL OR schema_name = %s)
                ORDER BY created_at DESC LIMIT 1""",
            (doc.id, schema_name, schema_name),
        ).fetchone()
        if ex is None:
            raise FieldNotFoundError(f"No field extraction for {doc.file_name}" + (f" with schema {schema_name}" if schema_name else ""))
        rows = conn.execute("SELECT * FROM extracted_fields WHERE extraction_id = %s ORDER BY id", (ex["id"],)).fetchall()
    schema = get_schema(ex["schema_name"])
    order = {name: i for i, name in enumerate(schema.fields)}
    fields = sorted((_field_row(r) for r in rows), key=lambda f: order.get(f["field"], 999))
    for f in fields:
        spec = schema.fields.get(f["field"])
        f["label"] = (spec.label or f["field"]) if spec else f["field"]
        f["type"] = spec.type if spec else None
    return {
        "extraction_id": str(ex["id"]),
        "document_id": doc.id,
        "file_name": doc.file_name,
        "schema": ex["schema_name"],
        "schema_version": ex["schema_version"],
        "status": ex["status"],
        "error": ex["error"],
        "model": ex["model"],
        "pages_read": list(ex["pages_read"] or []),
        "rules": ex["rules"],
        "cost_usd": round(float(ex["cost_usd"] or 0), 6),
        "seconds": ex["seconds"],
        "created_at": ex["created_at"].isoformat(),
        "finished_at": ex["finished_at"].isoformat() if ex["finished_at"] else None,
        "fields": fields,
        "needs_review": [f["field"] for f in fields if f["status"] == "needs_review"],
    }


def review_queue(principal: Principal, *, limit: int = 100) -> list[dict]:
    """Fields a person should check, newest documents first (latest extraction of each)."""
    with tenant_tx(principal.tenant_id) as conn:
        rows = conn.execute(
            """SELECT f.*, d.file_name FROM extracted_fields f
                 JOIN field_extractions e ON e.id = f.extraction_id
                 JOIN documents d ON d.id = f.document_id
                WHERE f.status = 'needs_review'
                  AND e.created_at = (SELECT max(created_at) FROM field_extractions e2
                                       WHERE e2.document_id = e.document_id AND e2.schema_name = e.schema_name)
                ORDER BY e.created_at DESC, f.id LIMIT %s""",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_field_row(r) | {"document_id": str(r["document_id"]), "file_name": r["file_name"], "schema": r["schema_name"]} for r in rows]


def review_field(principal: Principal, document_id: str, field: str, *, action: str, value: Any = None, schema_name: str | None = None) -> dict:
    """A person confirms, corrects or rejects a field of the latest extraction."""
    if action not in REVIEW_ACTIONS:
        raise ValueError(f"action must be one of {', '.join(REVIEW_ACTIONS)}")
    current = latest_extraction(principal, document_id, schema_name)
    schema = get_schema(current["schema"])
    spec = schema.fields.get(field)
    if spec is None:
        raise FieldNotFoundError(f"Schema {schema.name} has no field '{field}'")
    new_value = None
    if action == "correct":
        if spec.type == "list":
            if not isinstance(value, list):
                raise ValueError("line items must be a list of objects")
            new_value = value
        else:
            new_value, problems = normalize(spec, value, None)
            if new_value is None or problems:
                raise ValueError(f"'{value}' is not a valid {spec.type}: {'; '.join(problems) or 'empty'}")
    status = {"confirm": "confirmed", "correct": "corrected", "reject": "rejected"}[action]
    with tenant_tx(principal.tenant_id) as conn:
        row = conn.execute(
            """UPDATE extracted_fields
                  SET status = %s,
                      machine_value = CASE WHEN %s = 'corrected' AND machine_value IS NULL THEN value ELSE machine_value END,
                      value = CASE WHEN %s = 'corrected' THEN %s::jsonb WHEN %s = 'rejected' THEN NULL ELSE value END,
                      reviewed_by = %s, reviewed_at = now()
                WHERE extraction_id = %s AND field = %s RETURNING *""",
            (status, status, status, json.dumps(new_value), status, as_uuid(principal.user_id), current["extraction_id"], field),
        ).fetchone()
    if row is None:
        raise FieldNotFoundError(f"No field '{field}' in the latest extraction")
    return _field_row(row)


# --- export ----------------------------------------------------------------------------------


def export_table(principal: Principal, schema_name: str, document_ids: list[str] | None = None) -> tuple[list[str], list[dict], list[dict]]:
    """(columns, one row per document, one row per list item) from each document's latest extraction."""
    schema = get_schema(schema_name)
    if document_ids:
        docs = [repos.require_document(principal.tenant_id, d) for d in document_ids]
    else:
        docs = repos.list_documents(principal.tenant_id, ready_only=True)
    scalar = [n for n, f in schema.fields.items() if f.type != "list"]
    lists = [n for n, f in schema.fields.items() if f.type == "list"]
    columns = ["document", "file_name", "extracted_at"] + scalar + [f"{n}_status" for n in scalar] + ["needs_review"]
    rows, items = [], []
    for doc in docs:
        try:
            ex = latest_extraction(principal, doc.id, schema.name)
        except FieldNotFoundError:
            continue
        if ex["status"] != "done":
            continue
        by = {f["field"]: f for f in ex["fields"]}
        row: dict[str, Any] = {"document": doc.id, "file_name": doc.file_name, "extracted_at": ex["finished_at"]}
        for n in scalar:
            f = by.get(n) or {}
            row[n] = f.get("value")
            row[f"{n}_status"] = f.get("status")
        row["needs_review"] = ", ".join(ex["needs_review"])
        rows.append(row)
        for n in lists:
            for i, item in enumerate((by.get(n) or {}).get("value") or [], start=1):
                cols = schema.fields[n].item
                items.append({"document": doc.id, "file_name": doc.file_name, "list": n, "line": i, **{c: item.get(c) for c in cols}, "page": item.get("page")})
    return columns, rows, items


def to_csv(columns: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: _cell(v) for k, v in r.items()})
    return buf.getvalue()


def to_xlsx(schema: Schema, columns: list[str], rows: list[dict], items: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = schema.label[:31] or schema.name[:31]
    labels = {n: (f.label or n) for n, f in schema.fields.items()}
    ws.append([labels.get(c, c.replace("_", " ").capitalize()) for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    review = PatternFill("solid", fgColor="FFF2CC")
    for r in rows:
        ws.append([_cell(r.get(c)) for c in columns])
        for i, c in enumerate(columns, start=1):
            if r.get(f"{c}_status") == "needs_review":
                ws.cell(row=ws.max_row, column=i).fill = review
    for i, c in enumerate(columns, start=1):
        if c in schema.fields and schema.fields[c].type == "money":
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                row[0].number_format = "#,##0.00"
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(12, min(40, len(str(ws.cell(row=1, column=i).value)) + 4))
    if items:
        wi = wb.create_sheet("Line items")
        keys = list(items[0].keys())
        wi.append(keys)
        for cell in wi[1]:
            cell.font = Font(bold=True)
        for it in items:
            wi.append([_cell(it.get(k)) for k in keys])
    note = wb.create_sheet("About")
    note.append(["Schema", f"{schema.label} ({schema.name} v{schema.version})"])
    note.append(["Exported", datetime.now(timezone.utc).isoformat(timespec="seconds")])
    note.append(["Money", "Absolute amounts in the document's currency, scale applied (Birr'000 x 1000)."])
    note.append(["Yellow cells", "Fields waiting for review: check them against the page before use."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(v: Any) -> Any:
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def schemas_public() -> list[dict]:
    return [s.public() for s in all_schemas().values()]


__all__ = [
    "AccessDeniedError", "FieldNotFoundError", "request_extraction", "run_extraction", "latest_extraction",
    "review_queue", "review_field", "export_table", "to_csv", "to_xlsx", "schemas_public", "V",
]
