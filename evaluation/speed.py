"""Ingest speed and API responsiveness on a small CPU box, measured end to end.

    python -m evaluation.speed --mode worker --run runs/m4-speed/after
    python -m evaluation.speed --mode sync --code <dir with older code> --run runs/m4-speed/before

It starts the API (and, in ``worker`` mode, the ingest worker) as separate
processes pinned to the same CPU cores (default: two P-cores, to stand in
for the 2-OCPU server), each run with its own fresh database. For each
document it uploads through the HTTP API and records:

* total time from upload to ``ready``
* time until the document is first searchable
* latency of /health and of a database-backed request, every 250 ms, while
  the document is being read (the API must stay responsive)

``sync`` mode is for code before M4, where the upload request itself ran
the whole ingest. Extraction runs on CPU in both modes; embeddings use the
real API (keys from .env), as a user's upload would.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx

EVAL_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_ROOT.parent


def _pctl(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * len(s)))], 4)


def _fresh_database(name: str) -> str:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    base = os.getenv("DOCMIND_DATABASE_URL", "postgresql://docmind:docmind-dev-only@localhost:5433/docmind")
    params = conninfo_to_dict(base)
    with psycopg.connect(make_conninfo(**{**params, "dbname": "postgres"}), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    return make_conninfo(**{**params, "dbname": name})


def _pin(proc: subprocess.Popen, cores: list[int]) -> None:
    import psutil

    psutil.Process(proc.pid).cpu_affinity(cores)


class Probe(threading.Thread):
    """Measures API latency every ``every`` seconds until stopped."""

    def __init__(self, base: str, headers: dict, doc_id_ref: dict, every: float = 0.25):
        super().__init__(daemon=True)
        self.base, self.headers, self.doc_ref, self.every = base, headers, doc_id_ref, every
        self.health: list[float] = []
        self.db: list[float] = []
        self.errors = 0
        self.stop = threading.Event()

    def run(self) -> None:
        # A long timeout on purpose: a blocked API should show up as latency.
        with httpx.Client(timeout=3600) as c:
            while not self.stop.is_set():
                for path, bucket in (("/health", self.health), ("/documents", self.db)):
                    t = time.perf_counter()
                    try:
                        r = c.get(self.base + path, headers=self.headers)
                        r.raise_for_status()
                        bucket.append(time.perf_counter() - t)
                    except Exception:
                        self.errors += 1
                self.stop.wait(self.every)


def run(args) -> dict:
    run_dir = Path(args.run) if Path(args.run).is_absolute() else EVAL_ROOT / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    code = Path(args.code).resolve() if args.code else PROJECT_ROOT
    cores = [int(c) for c in args.cores.split(",")]

    import src.config  # noqa: F401  (loads .env into this process; passed on to the children)
    from evaluation.schema import load_golden

    golden = load_golden("v1")
    files = {d.doc_key: d for d in golden.documents}
    docs = [files[k] for k in args.docs.split(",")]
    corpus = Path(os.getenv("DOCMIND_CORPUS_DIR", PROJECT_ROOT / "data" / "data"))

    db_url = _fresh_database(f"docmind_speed_{run_dir.name.replace('-', '_')}")
    env = {
        **os.environ,
        "PYTHONPATH": str(code),
        "DOCMIND_DATABASE_URL": db_url,
        "DOCMIND_DATABASE_ADMIN_URL": db_url,
        "DOCMIND_REFINERY_DIR": str(run_dir / "refinery"),
        "DOCMIND_DEVICE": "cpu",
        "DOCMIND_EMBEDDED_WORKER": "0",
        "LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    env.pop("DOCMIND_STORAGE_DIR", None)
    env.update(dict(kv.split("=", 1) for kv in args.env))
    port = args.port
    logs = open(run_dir / "server.log", "w", encoding="utf-8")
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=code, env=env, stdout=logs, stderr=subprocess.STDOUT,
    )
    _pin(api, cores)
    worker = None
    if args.mode == "worker":
        worker = subprocess.Popen(
            [sys.executable, "-m", "src.jobs.worker"], cwd=code, env=env, stdout=logs, stderr=subprocess.STDOUT
        )
        _pin(worker, cores)
    base = f"http://127.0.0.1:{port}"
    out: dict = {"mode": args.mode, "code": str(code), "cores": cores, "env": args.env, "documents": []}
    try:
        for _ in range(240):
            try:
                if httpx.get(base + "/health", timeout=2).status_code == 200:
                    break
            except Exception:
                time.sleep(0.5)
        email = f"speed-{uuid4().hex[:8]}@example.com"
        httpx.post(base + "/api/auth/register", json={"email": email, "password": "speed-test-1"}, timeout=30).raise_for_status()
        token = httpx.post(base + "/api/auth/login", json={"email": email, "password": "speed-test-1"}, timeout=30).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # Warm the models on a tiny scanned document first, as a running server would be.
        warm = corpus / files["audited_fs_2021"].file_name
        r = httpx.post(base + "/upload", headers=h, files={"file": (warm.name, warm.read_bytes(), "application/pdf")}, timeout=1800)
        r.raise_for_status()
        if args.mode == "worker":
            wid = r.json()["document_id"]
            while httpx.get(f"{base}/documents/{wid}", headers=h, timeout=30).json()["status"] not in ("indexed", "failed"):
                time.sleep(1)

        for d in docs:
            pdf = corpus / d.file_name
            ref: dict = {}
            probe = Probe(base, h, ref)
            probe.start()
            t0 = time.perf_counter()
            row: dict = {"doc_key": d.doc_key, "pages": d.pages, "timeline": []}
            r = httpx.post(base + "/upload", headers=h, files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")}, timeout=7200)
            row["upload_response_s"] = round(time.perf_counter() - t0, 3)
            r.raise_for_status()
            doc_id = r.json()["document_id"]
            first_searchable = None
            info = r.json()
            while args.mode == "worker":
                info = httpx.get(f"{base}/documents/{doc_id}", headers=h, timeout=60).json()
                now = time.perf_counter() - t0
                row["timeline"].append([round(now, 1), info.get("stage", info["status"]), info.get("pages_done", 0)])
                searchable = info.get("searchable", info["status"] == "indexed")
                if searchable and first_searchable is None:
                    first_searchable = now
                if info["status"] in ("indexed", "failed"):
                    break
                time.sleep(0.5)
            total = time.perf_counter() - t0
            probe.stop.set()
            probe.join()
            row.update(
                status=info["status"],
                total_s=round(total, 1),
                seconds_per_page=round(total / d.pages, 2),
                first_searchable_s=round(first_searchable or total, 1),
                api_health_p50_ms=round(1000 * (statistics.median(probe.health) if probe.health else 0), 1),
                api_health_p95_ms=round(1000 * (_pctl(probe.health, 0.95) or 0), 1),
                api_health_max_ms=round(1000 * max(probe.health, default=0), 1),
                api_db_p95_ms=round(1000 * (_pctl(probe.db, 0.95) or 0), 1),
                api_requests=len(probe.health) + len(probe.db),
                api_errors=probe.errors,
            )
            print(json.dumps({k: v for k, v in row.items() if k != "timeline"}), flush=True)
            out["documents"].append(row)
    finally:
        for p in (worker, api):
            if p is not None:
                p.terminate()
                try:
                    p.wait(timeout=20)
                except Exception:
                    p.kill()
        logs.close()
    (run_dir / "speed.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def render(before: dict | None, after: dict, title: str) -> str:
    """A markdown comparison of two speed runs (before may be None)."""

    def mins(s):
        return f"{s / 60:.1f} min" if s is not None else "n/a"

    def ms(v):
        if v is None:
            return "n/a"
        return f"{v / 1000:.0f} s (blocked)" if v >= 1000 else f"{v:.0f} ms"

    b = {d["doc_key"]: d for d in (before or {}).get("documents", [])}
    lines = [
        f"# {title}",
        "",
        "API and worker as separate processes pinned to 2 CPU cores (two P-cores of an i7-13620H laptop, CPU only), "
        "each run on a fresh database, uploads through the HTTP API, real embeddings. The 2-OCPU ARM server is "
        "expected to be slower per core; the targets are for that server.",
        "",
        "| Document | Pages | Ready, before | Ready, after | First searchable, before | First searchable, after "
        "| API /health p95, before | API /health p95, after | API DB read p95, after |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for d in after["documents"]:
        o = b.get(d["doc_key"], {})
        lines.append(
            f"| {d['doc_key']} | {d['pages']} | {mins(o.get('total_s'))} | {mins(d['total_s'])} | "
            f"{mins(o.get('first_searchable_s'))} | {d['first_searchable_s']:.0f} s | "
            f"{ms(o.get('api_health_p95_ms'))} | {ms(d['api_health_p95_ms'])} | {ms(d['api_db_p95_ms'])} |"
        )
    lines += [
        "",
        "First searchable: the time until questions can use the document. Before M4 that was only when the whole "
        "document was done. Now the pages that have a text layer are indexed first; table pages get their tables "
        "and scanned pages their text when the full read finishes (column 'Ready').",
        "",
        "Before M4 the upload request itself ran the whole ingest on the API's event loop, so every other request "
        "(health checks and logins included) waited until it finished.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    if argv and argv[0] == "report":
        rp = argparse.ArgumentParser(prog="python -m evaluation.speed report")
        rp.add_argument("--before", default="")
        rp.add_argument("--after", required=True)
        rp.add_argument("--title", default="Ingest speed")
        rp.add_argument("--publish", default="")
        a = rp.parse_args(argv[1:])

        def load(run):
            p = Path(run) if Path(run).is_absolute() else EVAL_ROOT / run
            return json.loads((p / "speed.json").read_text(encoding="utf-8"))

        before, after = (load(a.before) if a.before else None), load(a.after)
        md = render(before, after, a.title)
        print(md)
        if a.publish:
            (EVAL_ROOT / "reports" / f"{a.publish}.md").write_text(md, encoding="utf-8")
            (EVAL_ROOT / "reports" / f"{a.publish}.json").write_text(
                json.dumps({"before": before, "after": after}, indent=2), encoding="utf-8"
            )
        return
    ap = argparse.ArgumentParser(prog="python -m evaluation.speed")
    ap.add_argument("--mode", choices=["worker", "sync"], default="worker")
    ap.add_argument("--code", default="", help="folder with the code to run (default: this checkout)")
    ap.add_argument("--run", required=True)
    ap.add_argument("--docs", default="cbe_2006_07,cbe_2023_24,dbe_audit_2023")
    ap.add_argument("--cores", default="0,2", help="CPU cores to pin the API and worker to")
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--env", nargs="*", default=[], help="extra KEY=VALUE for the server processes")
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
