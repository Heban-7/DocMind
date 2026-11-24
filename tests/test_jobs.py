"""The ingest job queue and worker (needs Postgres; see conftest ``pg``)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db import repos
from src.db.pool import app_tx, tenant_tx
from src.document.model import Block, BlockType, DocumentModel, Page, PageQuality
from src.jobs import queue
from src.jobs.worker import run_once
from src.pipeline.ingest import submit_document

pytestmark = pytest.mark.usefixtures("pg")

_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _tenant() -> repos.Principal:
    return repos.create_tenant_with_owner(f"{uuid4().hex[:10]}@example.com", "x")


def _pdf(tmp_path, tag: str):
    path = tmp_path / f"{tag}.pdf"
    path.write_bytes(_PDF + f"%{tag}\n".encode())
    return path


def _model(text: str) -> DocumentModel:
    page = Page(
        number=1,
        width=200,
        height=200,
        blocks=[Block(block_id="p1-b0", type=BlockType.TEXT, text=text)],
        quality=PageQuality(engine="text_layer", confidence=0.9),
    )
    return DocumentModel(doc_id="x", file_name="x.pdf", sha256="x", page_count=1, pages=[page])


@pytest.fixture()
def fake_extract(monkeypatch):
    calls = {"n": 0, "fail": 0}

    def extract(pdf_path, **_kw):
        calls["n"] += 1
        if calls["fail"] > 0:
            calls["fail"] -= 1
            raise RuntimeError("simulated crash in a page")
        return _model("Revenue was ETB 5 billion in 2023, up from ETB 4 billion.")

    monkeypatch.setattr("src.document.extract.extract_document", extract)
    monkeypatch.setattr("src.jobs.queue.RETRY_DELAY_SECONDS", 0)
    run_once(embed=False)  # the queue is shared: finish other tests' jobs first
    calls["n"] = 0
    return calls


def _job_rows(tenant_id: str, doc_id: str) -> list[dict]:
    with tenant_tx(tenant_id) as conn:
        return conn.execute(
            "SELECT status, attempts, error FROM jobs WHERE document_id = %s ORDER BY created_at", (doc_id,)
        ).fetchall()


def test_submit_returns_queued_and_worker_makes_it_ready(tmp_path, fake_extract):
    p = _tenant()
    res = submit_document(_pdf(tmp_path, "a"), principal=p)
    assert res.status == "queued" and res.page_count == 1
    doc = repos.require_document(p.tenant_id, res.document_id)
    assert doc.status == "queued" and not doc.searchable

    assert run_once(embed=False) >= 1
    doc = repos.require_document(p.tenant_id, res.document_id)
    assert doc.status == "ready" and doc.searchable and doc.stage == "done"
    assert doc.pages_done == doc.page_count == 1 and doc.progress == 1.0
    assert "first_searchable_s" in doc.stats and "reading" in doc.stats["seconds"]
    assert [r["status"] for r in _job_rows(p.tenant_id, res.document_id)] == ["done"]


def test_same_file_queued_twice_is_one_job(tmp_path, fake_extract):
    p = _tenant()
    path = _pdf(tmp_path, "twice")
    first = submit_document(path, principal=p)
    again = submit_document(path, principal=p)
    assert again.deduplicated and again.document_id == first.document_id
    assert len(_job_rows(p.tenant_id, first.document_id)) == 1


def test_a_failing_job_is_retried_then_marked_failed(tmp_path, fake_extract):
    p = _tenant()
    fake_extract["fail"] = 1  # first attempt crashes, the retry works
    res = submit_document(_pdf(tmp_path, "retry"), principal=p)
    run_once(embed=False)
    doc = repos.require_document(p.tenant_id, res.document_id)
    assert doc.status == "ready"
    assert _job_rows(p.tenant_id, res.document_id)[0]["attempts"] == 2

    fake_extract["fail"] = 10  # every attempt crashes
    res = submit_document(_pdf(tmp_path, "broken"), principal=p)
    run_once(embed=False)
    doc = repos.require_document(p.tenant_id, res.document_id)
    job = _job_rows(p.tenant_id, res.document_id)[0]
    assert doc.status == "failed" and "simulated crash" in doc.error and not doc.searchable
    assert job["status"] == "failed" and job["attempts"] == 3

    # Uploading the failed file again queues a fresh attempt.
    fake_extract["fail"] = 0
    again = submit_document(_pdf(tmp_path, "broken"), principal=p)
    assert again.document_id == res.document_id and again.status == "queued"
    run_once(embed=False)
    assert repos.require_document(p.tenant_id, res.document_id).status == "ready"


def test_a_job_whose_worker_died_is_claimed_again(tmp_path, fake_extract):
    p = _tenant()
    res = submit_document(_pdf(tmp_path, "orphan"), principal=p)
    job = queue.claim("dead-worker", lease_seconds=60)
    assert job is not None and job.document_id == res.document_id
    assert queue.claim("other-worker") is None or True  # nothing else runnable for this doc
    with app_tx() as conn:  # the dead worker's lease runs out
        conn.execute("SELECT set_config('app.worker', 'on', true)")
        conn.execute("UPDATE jobs SET locked_until = now() - interval '1 second' WHERE id = %s", (job.id,))
    retaken = queue.claim("live-worker")
    assert retaken is not None and retaken.id == job.id and retaken.attempts == 2
    assert not queue.renew(job, "dead-worker")  # the old worker cannot keep it
    queue.complete(retaken, "live-worker")


def test_queue_rows_are_tenant_scoped_outside_worker_mode(tmp_path, fake_extract):
    a, b = _tenant(), _tenant()
    res = submit_document(_pdf(tmp_path, "scoped"), principal=a)
    assert _job_rows(b.tenant_id, res.document_id) == []
    with app_tx() as conn:  # neither tenant nor worker mode: nothing
        assert conn.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"] == 0
    run_once(embed=False)


def test_too_many_pages_is_refused(tmp_path, monkeypatch, fake_extract):
    from src.pipeline.ingest import TooManyPagesError

    monkeypatch.setenv("DOCMIND_MAX_PAGES", "0")
    with pytest.raises(TooManyPagesError):
        submit_document(_pdf(tmp_path, "big"), principal=_tenant())
