"""Tenant isolation at the database layer (needs Postgres; see conftest ``pg``).

These tests talk to the stores and repositories directly. The same guarantees
through the HTTP API are in tests/test_api_security.py.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from src.chunking.models import DocumentChunk
from src.db import repos
from src.db.pool import app_tx, tenant_tx
from src.facts.models import FactRecord
from src.pageindex.builder import build_page_index
from src.stores.pg import pg_stores

pytestmark = pytest.mark.usefixtures("pg")

TENANT_TABLES = ["documents", "pages", "chunks", "facts", "page_indexes", "threads"]


def _vec(i: int) -> list[float]:
    v = [0.0] * 1536
    v[i] = 1.0
    return v


def _tenant() -> repos.Principal:
    return repos.create_tenant_with_owner(f"{uuid4().hex[:10]}@example.com", "not-a-real-hash")


def _ready_doc(p: repos.Principal, *, text: str = "Revenue was ETB 5 billion in 2023.") -> str:
    doc = repos.new_document_id()
    repos.create_document(p, document_id=doc, sha256=uuid4().hex, file_name="a.pdf", storage_key="k")
    stores = pg_stores(p.tenant_id)
    chunks = [DocumentChunk.create(text, parent_hierarchy=["Summary"], page_numbers=[3])]
    stores.chunks.replace_doc_chunks(doc, chunks, [_vec(0)])
    stores.facts.replace_doc_facts(doc, [FactRecord(doc_id=doc, metric="Revenue", value_text="ETB 5 billion", page_number=3)])
    stores.pageindex.save(build_page_index(chunks, doc_id=doc, summarize=True, llm_client=None))
    repos.mark_document_ready(
        p.tenant_id, doc, page_count=3, model_key=None,
        ledger=[{"page": 1, "engine": "text_layer", "confidence": 0.9, "needs_review": True}],
    )
    return doc


def test_every_tenant_table_has_forced_row_level_security():
    with app_tx() as conn:
        rows = conn.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)",
            (TENANT_TABLES,),
        ).fetchall()
    assert {r["relname"] for r in rows} == set(TENANT_TABLES)
    assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)


def test_app_role_is_not_a_superuser_and_cannot_bypass_rls():
    with app_tx() as conn:
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
    assert row == {"rolsuper": False, "rolbypassrls": False}


def test_without_a_tenant_nothing_is_visible():
    _ready_doc(_tenant())
    with app_tx() as conn:
        for table in TENANT_TABLES:
            assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0, table


def test_stores_never_return_another_tenants_rows():
    a, b = _tenant(), _tenant()
    doc = _ready_doc(a)
    sa, sb = pg_stores(a.tenant_id), pg_stores(b.tenant_id)

    assert [h.doc_id for h in sa.chunks.query(_vec(0))] == [doc]
    assert sb.chunks.query(_vec(0)) == []
    assert sb.chunks.query(_vec(0), doc_id=doc) == []  # even when the id is known
    assert sb.chunks.count() == 0
    assert sb.facts.search(metric_contains="revenue") == []
    assert sb.facts.search(doc_id=doc) == []
    assert sb.pageindex.load(doc) is None
    assert repos.get_document(b.tenant_id, doc) is None
    assert repos.page_ledger(b.tenant_id, doc) == []
    assert doc not in {d.id for d in repos.list_documents(b.tenant_id)}

    # B deleting or overwriting A's rows by id has no effect.
    sb.chunks.delete_doc(doc)
    assert sa.chunks.count(doc) == 1


def test_writing_rows_into_another_tenant_is_refused():
    a, b = _tenant(), _tenant()
    doc = _ready_doc(a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_tx(b.tenant_id) as conn:
            conn.execute(
                "INSERT INTO chunks (id, tenant_id, document_id, ordinal, text, content_hash)"
                " VALUES (gen_random_uuid(), %s, %s, 0, 'planted', 'h')",
                (a.tenant_id, doc),
            )
    # A document id from another tenant cannot be referenced either. Foreign
    # key checks ignore RLS, so this relies on the composite (tenant_id, id) keys.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        pg_stores(b.tenant_id).chunks.replace_doc_chunks(
            doc, [DocumentChunk.create("planted", parent_hierarchy=[], page_numbers=[1])], [_vec(1)]
        )
    assert [h.text for h in pg_stores(a.tenant_id).chunks.query(_vec(1))] != ["planted"]


def test_reindexing_reuses_stored_vectors_for_unchanged_text():
    from src.retrieval.ingest import ingest_chunks

    class Counting:
        def __init__(self):
            self.texts = 0

        def embed(self, texts):
            self.texts += len(texts)
            return [_vec(i % 1536) for i, _ in enumerate(texts)]

    a = _tenant()
    doc = _ready_doc(a)
    store = pg_stores(a.tenant_id).chunks
    emb = Counting()
    same = DocumentChunk.create("Revenue was ETB 5 billion in 2023.", parent_hierarchy=["Summary"], page_numbers=[3])
    new = DocumentChunk.create("A new paragraph from a scanned page.", parent_hierarchy=["Summary"], page_numbers=[4])
    ingest_chunks([same], doc_id=doc, store=store, embedder=emb, document_name="a.pdf")
    assert emb.texts == 1
    res = ingest_chunks([same, new], doc_id=doc, store=store, embedder=emb, document_name="a.pdf")
    assert emb.texts == 2 and res.texts_embedded == 1  # only the new text was embedded
    assert store.count(doc) == 2 and len(store.existing_embeddings(doc)) == 2
    # The context is part of what is embedded: a renamed section is embedded again.
    moved = DocumentChunk.create(same.text, parent_hierarchy=["Financial review"], page_numbers=[3])
    assert ingest_chunks([moved, new], doc_id=doc, store=store, embedder=emb, document_name="a.pdf").texts_embedded == 1


def test_documents_that_are_not_ready_are_not_searchable():
    a = _tenant()
    doc = repos.new_document_id()
    repos.create_document(a, document_id=doc, sha256="x", file_name="p.pdf", storage_key="k")
    pg_stores(a.tenant_id).chunks.replace_doc_chunks(
        doc, [DocumentChunk.create("half indexed", parent_hierarchy=[], page_numbers=[1])], [_vec(2)]
    )
    assert pg_stores(a.tenant_id).chunks.query(_vec(2)) == []
    repos.mark_document_failed(a.tenant_id, doc, "boom")
    assert pg_stores(a.tenant_id).chunks.query(_vec(2)) == []


def test_ledger_and_review_count_are_stored():
    a = _tenant()
    doc = _ready_doc(a)
    row = repos.get_document(a.tenant_id, doc)
    assert row.status == "ready" and row.pages_needing_review == 1
    assert repos.page_ledger(a.tenant_id, doc)[0]["engine"] == "text_layer"


def test_threads_have_one_owner_and_are_scoped_per_tenant():
    a, b = _tenant(), _tenant()
    t = repos.claim_thread(a, "shared-id")
    assert t.user_id == a.user_id
    # Another tenant using the same id gets a separate thread, not A's.
    tb = repos.claim_thread(b, "shared-id")
    assert tb.user_id == b.user_id
    # Another user in A's tenant cannot read or take over A's thread.
    with app_tx() as conn:
        uid = conn.execute(
            "INSERT INTO users (tenant_id, email, hashed_password) VALUES (%s, %s, 'x') RETURNING id",
            (a.tenant_id, f"{uuid4().hex[:8]}@example.com"),
        ).fetchone()["id"]
    colleague = repos.Principal(user_id=str(uid), tenant_id=a.tenant_id)
    with pytest.raises(repos.AccessDeniedError):
        repos.get_thread(colleague, "shared-id")
    with pytest.raises(repos.AccessDeniedError):
        repos.claim_thread(colleague, "shared-id")
    with pytest.raises(repos.AccessDeniedError):
        repos.claim_thread(a, "bad id with spaces")


def test_tenant_tx_rejects_non_uuid_tenants():
    with pytest.raises(ValueError):
        with tenant_tx("' OR 1=1 --"):
            pass


def test_postgres_checkpointer_keys_include_the_tenant():
    from langchain_core.messages import HumanMessage

    from src.agents.memory import checkpoint_key, postgres_checkpointer, read_messages

    a, b = _tenant(), _tenant()
    saver = postgres_checkpointer()
    key_a = checkpoint_key(a.tenant_id, "t1")
    config = {"configurable": {"thread_id": key_a, "checkpoint_ns": ""}}
    from langgraph.checkpoint.base import empty_checkpoint

    cp = empty_checkpoint()
    cp["channel_values"] = {"messages": [HumanMessage(content="secret question")]}
    cp["channel_versions"] = {"messages": 1}
    saver.put(config, cp, {"source": "input", "step": 0}, {"messages": 1})
    assert [m.content for m in read_messages(saver, key_a)] == ["secret question"]
    assert read_messages(saver, checkpoint_key(b.tenant_id, "t1")) == []
