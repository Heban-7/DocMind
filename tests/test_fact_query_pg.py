"""Numeric questions compiled to SQL and run read-only (needs Postgres; see conftest ``pg``)."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from src.db import repos
from src.db.pool import tenant_tx
from src.facts.query import FactQuery
from src.facts.typed import facts_from_model
from src.stores.pg import PgFactStore
from tests.test_facts import _model

pytestmark = pytest.mark.usefixtures("pg")


def _doc_with_facts() -> tuple[repos.Principal, str]:
    p = repos.create_tenant_with_owner(f"{uuid4().hex[:10]}@example.com", "x")
    doc = repos.new_document_id()
    repos.create_document(p, document_id=doc, sha256=uuid4().hex, file_name="r.pdf", storage_key="k")
    PgFactStore(p.tenant_id).replace_doc_facts(doc, facts_from_model(_model(), doc_id=doc, document_name="r.pdf"))
    repos.mark_document_ready(p.tenant_id, doc, page_count=3, model_key=None, ledger=[])
    return p, doc


def test_typed_facts_round_trip_through_postgres():
    p, doc = _doc_with_facts()
    fee = next(f for f in PgFactStore(p.tenant_id).search(doc_id=doc, metric_contains="fee income") if f.column_label == "2022/23")
    assert fee.value == -300 and fee.scale == 1e6 and fee.absolute_value == -3e8
    assert fee.bbox == [180.0, 260.0, 250.0, 275.0] and fee.row_group == "Operating income"


def test_lookup_change_and_sum_are_computed_in_sql():
    p, doc = _doc_with_facts()
    store = PgFactStore(p.tenant_id)
    looked = store.run_query(FactQuery(op="lookup", metric="fee income", periods=["2023/24"]), doc_id=doc)
    assert looked.facts and looked.facts[0].value == 450

    change = store.run_query(FactQuery(op="percent_change", metric="fee income", periods=["2022/23", "2023/24"]), doc_id=doc)
    assert change.computed and change.computed[0].value == pytest.approx(250.0)
    diff = store.run_query(FactQuery(op="difference", metric="interest income", periods=["2022/23", "2023/24"]), doc_id=doc)
    assert diff.computed[0].value == pytest.approx(300e6) and diff.computed[0].unit == "ETB"

    total = store.run_query(FactQuery(op="sum", metric="interest income", periods=["2023/24"]), doc_id=doc)
    assert total.computed[0].value == pytest.approx(1950e6)  # the "Total" row is left out
    top = store.run_query(FactQuery(op="max", metric="income", periods=["2023/24"]), doc_id=doc)
    assert top.computed[0].value == pytest.approx(1500e6)


def test_hostile_text_in_the_spec_is_only_ever_data():
    p, doc = _doc_with_facts()
    store = PgFactStore(p.tenant_id)
    for metric in ["fee'; DROP TABLE facts; --", "x%' OR 1=1 --", "income) UNION SELECT * FROM users --"]:
        store.run_query(FactQuery(op="lookup", metric=metric, periods=["2023/24'; --"]), doc_id=doc)
    assert store.count(doc) > 0


def test_the_reader_role_cannot_change_data():
    p, doc = _doc_with_facts()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_tx(p.tenant_id) as conn:
            conn.execute("SET LOCAL ROLE docmind_reader")
            conn.execute("DELETE FROM facts")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_tx(p.tenant_id) as conn:
            conn.execute("SET LOCAL ROLE docmind_reader")
            conn.execute("SELECT * FROM users")


def test_queries_never_cross_tenants():
    p, doc = _doc_with_facts()
    other = repos.create_tenant_with_owner(f"{uuid4().hex[:10]}@example.com", "x")
    store = PgFactStore(other.tenant_id)
    assert store.run_query(FactQuery(op="lookup", metric="fee income"), doc_id=doc).facts == []
    assert store.run_query(FactQuery(op="lookup", metric="fee income")).facts == []
