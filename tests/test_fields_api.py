"""Schema fields through the API: extract in the worker, read, review, export; per tenant (M8)."""

from __future__ import annotations

import io
import json
import zlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.document.model import BBox, Block, BlockType, DocumentModel, Page, PageQuality
from src.llm.base import LLMClient, LLMResult

_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


class _HashEmbedder:
    model = "hash-1536"

    def embed(self, texts):
        out = []
        for text in texts:
            v = [0.0] * 1536
            for word in text.lower().split():
                v[zlib.crc32(word.encode()) % 1536] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out


class _InvoiceReader(LLMClient):
    """Reads the one invoice page: every field but the seller, which it cannot find."""

    provider = "fake"

    def __init__(self):
        super().__init__(model="fake-fields")

    def _chat(self, messages, **params):
        out = {
            "fields": {
                "invoice_number": {"value": "INV-7", "ref": "p1-b0", "confidence": 0.95},
                "invoice_date": {"value": "05/03/2026", "ref": "p1-b0", "confidence": 0.95},
                "buyer_name": {"value": "Blue Nile Hotel S.C.", "ref": "p1-b1", "confidence": 0.9},
                "currency": {"value": "ETB", "ref": "p1-b2", "confidence": 0.9},
                "subtotal": {"value": "13,300.00", "ref": "p1-b2", "confidence": 0.95},
                "vat_amount": {"value": "1,995.00", "ref": "p1-b2", "confidence": 0.95},
                "total_amount": {"value": "15,295.00", "ref": "p1-b2", "confidence": 0.95},
            },
            "items": [{"description": "Cement", "quantity": "10", "unit_price": "1,330.00", "amount": "13,300.00", "ref": "p1-b3"}],
        }
        return LLMResult(text=json.dumps(out), model=self.model, provider=self.provider, input_tokens=900, output_tokens=200, cost_usd=0.0004)


def _invoice_model(*_a, **_k) -> DocumentModel:
    texts = [
        (BlockType.HEADING, "TAX INVOICE  Invoice No: INV-7  Date: 05/03/2026"),
        (BlockType.TEXT, "Bill To: Blue Nile Hotel S.C., Bahir Dar"),
        (BlockType.TEXT, "Subtotal ETB 13,300.00  VAT 15% ETB 1,995.00  Total ETB 15,295.00"),
        (BlockType.TEXT, "Cement 10 1,330.00 13,300.00"),
    ]
    blocks = [
        Block(block_id=f"p1-b{i}", type=t, text=s, bbox=BBox(x0=40, top=40 + 30 * i, x1=500, bottom=60 + 30 * i))
        for i, (t, s) in enumerate(texts)
    ]
    page = Page(number=1, width=595, height=842, blocks=blocks, quality=PageQuality(engine="text_layer", confidence=0.95))
    return DocumentModel(doc_id="x", file_name="x.pdf", sha256="x", page_count=1, pages=[page])


@pytest.fixture()
def client(pg, monkeypatch):
    monkeypatch.setattr("src.document.extract.extract_document", _invoice_model)
    monkeypatch.setattr("src.retrieval.ingest.build_embedding_client", lambda: _HashEmbedder())
    monkeypatch.setattr("src.llm.factory.get_text_client", lambda *a, **k: _InvoiceReader())
    with TestClient(create_app()) as c:
        yield c


def _account(client) -> dict:
    email = f"{uuid4().hex[:10]}@example.com"
    assert client.post("/api/auth/register", json={"email": email, "password": "pass-1234"}).status_code == 201
    token = client.post("/api/auth/login", json={"email": email, "password": "pass-1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ready_invoice(client, h) -> str:
    from src.jobs.worker import run_once

    data = _PDF + f"%{uuid4().hex}\n".encode()
    res = client.post("/upload", headers=h, files={"file": ("invoice.pdf", data, "application/pdf")})
    assert res.status_code == 202, res.text
    run_once()
    return res.json()["document_id"]


def test_extract_review_and_export_an_invoice(client):
    from src.jobs.worker import run_once

    a, b = _account(client), _account(client)
    doc = _ready_invoice(client, a)
    assert {s["name"] for s in client.get("/schemas", headers=a).json()["schemas"]} >= {"invoice", "financial_statement_summary"}

    res = client.post(f"/documents/{doc}/fields", headers=a, json={"schema": "invoice"})
    assert res.status_code == 202 and res.json()["status"] == "queued"
    run_once()  # the worker runs the extraction

    got = client.get(f"/documents/{doc}/fields", headers=a, params={"schema": "invoice"}).json()
    assert got["status"] == "done" and got["pages_read"] == [1]
    by = {f["field"]: f for f in got["fields"]}
    assert by["invoice_number"]["value"] == "INV-7" and by["invoice_number"]["status"] == "auto"
    assert by["invoice_number"]["page"] == 1 and by["invoice_number"]["bbox"] == [40.0, 40.0, 500.0, 60.0]
    assert by["invoice_date"]["value"] == "2026-03-05" and by["total_amount"]["value"] == 15295.0
    assert by["seller_name"]["status"] == "needs_review" and by["seller_name"]["value"] is None
    assert {r["name"]: r["passed"] for r in got["rules"]}["total_is_subtotal_plus_vat"]

    queue = client.get("/review", headers=a).json()["fields"]
    assert any(f["field"] == "seller_name" and f["document_id"] == doc for f in queue)
    assert client.get("/review", headers=b).json()["fields"] == []  # another account sees none of it
    assert client.get(f"/documents/{doc}/fields", headers=b).status_code == 404
    assert client.patch(f"/documents/{doc}/fields/seller_name", headers=b, json={"action": "reject"}).status_code == 404

    fixed = client.patch(f"/documents/{doc}/fields/seller_name", headers=a, json={"action": "correct", "value": "Abay Office Supplies PLC"})
    assert fixed.status_code == 200 and fixed.json()["status"] == "corrected" and fixed.json()["value"] == "Abay Office Supplies PLC"
    money = client.patch(f"/documents/{doc}/fields/total_amount", headers=a, json={"action": "correct", "value": "ETB 15,300.00"}).json()
    assert money["value"] == 15300.0 and money["machine_value"] == 15295.0  # the machine's value is kept
    assert client.patch(f"/documents/{doc}/fields/total_amount", headers=a, json={"action": "correct", "value": "abc"}).status_code == 400
    assert client.patch(f"/documents/{doc}/fields/invoice_number", headers=a, json={"action": "confirm"}).json()["status"] == "confirmed"
    assert all(f["field"] != "seller_name" for f in client.get("/review", headers=a).json()["fields"])

    csv_text = client.get("/exports/invoice.csv", headers=a).text
    header, row = csv_text.splitlines()[:2]
    assert "invoice_number" in header and "INV-7" in row and "Abay Office Supplies PLC" in row and "15300.0" in row
    assert client.get("/exports/invoice.csv", headers=b).text.count("\n") == 1  # header only

    from openpyxl import load_workbook

    xlsx = client.get("/exports/invoice.xlsx", headers=a)
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert wb.sheetnames == ["Invoice", "Line items", "About"]
    first = [c.value for c in wb["Invoice"][2]]
    assert "INV-7" in first and 15300.0 in first
    assert [c.value for c in wb["Line items"][2]][4:8] == ["Cement", 10.0, 1330.0, 13300.0]

    spent = client.get("/usage", headers=a).json()
    assert any(p["purpose"] == "fields" for p in spent["by_purpose"])


def test_unknown_schema_and_other_tenants_documents_are_refused(client):
    a, b = _account(client), _account(client)
    doc = _ready_invoice(client, a)
    assert client.post(f"/documents/{doc}/fields", headers=a, json={"schema": "payslip"}).status_code == 404
    assert client.post(f"/documents/{doc}/fields", headers=b, json={"schema": "invoice"}).status_code == 404
    assert client.get(f"/documents/{doc}/fields", headers=a).status_code == 404  # nothing extracted yet
    assert client.get("/exports/payslip.csv", headers=a).status_code == 404
