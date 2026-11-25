"""Security and isolation tests through the HTTP API (needs Postgres).

Every test uses real registration, real signed tokens and the real Postgres
stores. Only the paid or slow parts are faked: PDF extraction returns a fixed
document model, embeddings are a local hash, and the LLM answers from a
script while recording every prompt it is shown (so a test can prove that
another tenant's text never reached it).

Covers audit findings P0-1 (PDF access), P0-2 (no tenant isolation), P0-3
(default signing secret) and P1-9 (thread takeover).
"""

from __future__ import annotations

import json
import re
import zlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from src.agents.prompt_profiles import get_profile
from src.api.auth_utils import InsecureSecretError, create_access_token, jwt_secret
from src.api.main import create_app
from src.document.model import Block, BlockType, DocumentModel, Page, PageQuality
from src.llm.base import LLMClient, LLMResult

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


# --- fakes -------------------------------------------------------------------


class _HashEmbedder:
    model = "hash-1536"

    def embed(self, texts):
        out = []
        for text in texts:
            v = [0.0] * 1536
            for word in text.lower().split():
                v[zlib.crc32(word.encode()) % 1536] += 1.0
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / norm for x in v])
        return out


class _RecordingLLM(LLMClient):
    provider = "fake"
    prompts: list[str] = []

    def __init__(self):
        super().__init__(model="fake")

    def _chat(self, messages, **params):
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        text = "\n".join(str(m.get("content") or "") for m in messages)
        _RecordingLLM.prompts.append(text)
        if system == get_profile().plan_system:
            latest = messages[-1]["content"].split("latest message:\n")[-1].split("\n\nReturn")[0]
            out = json.dumps({"kind": "question", "question": latest, "document_id": None, "facts": None})
        else:  # the answer: repeat the first evidence passage and cite it
            m = re.search(r'<evidence id="E1"[^>]*>\n(.*?)\n</evidence>', messages[-1]["content"], re.S)
            out = f"{m.group(1).strip()} [E1]" if m else "Not found in the document: nothing matched."
        return LLMResult(text=out, model=self.model, provider=self.provider, input_tokens=500, output_tokens=40, cost_usd=0.01)


def _model_with(text: str) -> DocumentModel:
    page = Page(
        number=1,
        width=200,
        height=200,
        blocks=[
            Block(block_id="p1-b0", type=BlockType.HEADING, text="Summary"),
            Block(block_id="p1-b1", type=BlockType.TEXT, text=text),
        ],
        quality=PageQuality(engine="text_layer", confidence=0.95),
    )
    return DocumentModel(doc_id="x", file_name="x.pdf", sha256="x", page_count=1, pages=[page])


@pytest.fixture()
def client(pg, monkeypatch):
    _RecordingLLM.prompts = []
    texts: dict[bytes, str] = {}

    def fake_extract(pdf_path, **_kw):
        data = open(pdf_path, "rb").read()
        return _model_with(texts.get(data, "Revenue was ETB 1 billion."))

    monkeypatch.setattr("src.document.extract.extract_document", fake_extract)
    monkeypatch.setattr("src.retrieval.ingest.build_embedding_client", lambda: _HashEmbedder())
    monkeypatch.setattr("src.api.services.client_for_request", lambda *a, **k: _RecordingLLM())
    with TestClient(create_app()) as c:
        c.pdf_texts = texts  # tests register the text a given PDF "contains"
        yield c


def _account(client) -> dict:
    email = f"{uuid4().hex[:10]}@example.com"
    assert client.post("/api/auth/register", json={"email": email, "password": "pass-1234"}).status_code == 201
    token = client.post("/api/auth/login", json={"email": email, "password": "pass-1234"}).json()["access_token"]
    return {"email": email, "token": token, "h": {"Authorization": f"Bearer {token}"}}


def _upload(client, account, text: str, *, data: bytes | None = None) -> dict:
    """Upload, then let an in-process worker read the queued document."""
    from src.jobs.worker import run_once

    data = data or (_MINIMAL_PDF + f"%{uuid4().hex}\n".encode())
    client.pdf_texts[data] = text
    res = client.post("/upload", headers=account["h"], files={"file": ("report.pdf", data, "application/pdf")})
    assert res.status_code == 202, res.text
    run_once()
    return res.json()


def _chat(client, account, thread, message="What was revenue?", **extra):
    return client.post("/chat", headers=account["h"], json={"message": message, "thread_id": thread, **extra})


# --- accounts ----------------------------------------------------------------


def test_register_login_me_and_bad_credentials(client):
    a = _account(client)
    assert client.get("/api/auth/me", headers=a["h"]).json()["email"] == a["email"]
    dup = client.post("/api/auth/register", json={"email": a["email"].upper(), "password": "pass-1234"})
    assert dup.status_code == 409
    assert client.post("/api/auth/login", json={"email": a["email"], "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code == 401


def test_every_new_account_gets_its_own_tenant(client):
    a, b = _account(client), _account(client)
    ta = jwt.decode(a["token"], options={"verify_signature": False})["tid"]
    tb = jwt.decode(b["token"], options={"verify_signature": False})["tid"]
    assert ta != tb


# --- P0-1 and P0-2: documents ---------------------------------------------------


def test_pdf_needs_a_valid_token(client):
    a = _account(client)
    doc = _upload(client, a, "Alpha revenue")["document_id"]
    assert client.get(f"/documents/{doc}/pdf").status_code == 401
    assert client.get(f"/documents/{doc}/pdf", params={"token": "not-a-jwt"}).status_code == 401


def test_owner_downloads_pdf_by_header_or_a_short_lived_link(client):
    a, b = _account(client), _account(client)
    doc = _upload(client, a, "Alpha revenue")["document_id"]
    other = _upload(client, a, "Beta revenue")["document_id"]
    res = client.get(f"/documents/{doc}/pdf", headers=a["h"])
    assert res.status_code == 200 and res.content.startswith(b"%PDF")
    # the sign-in token never works in a URL
    assert client.get(f"/documents/{doc}/pdf", params={"token": a["token"]}).status_code == 401
    assert client.get(f"/documents/{doc}/pdf", params={"sig": a["token"]}).status_code == 401
    link = client.post(f"/documents/{doc}/link", headers=a["h"]).json()
    assert link["expires_in"] == 600
    assert client.get(link["url"]).content.startswith(b"%PDF")
    sig = link["url"].split("sig=", 1)[1]
    # a link opens its own document only, and is not a sign-in
    assert client.get(f"/documents/{other}/pdf", params={"sig": sig}).status_code == 401
    assert client.get("/documents", headers={"Authorization": f"Bearer {sig}"}).status_code == 401
    assert client.post(f"/documents/{doc}/link", headers=b["h"]).status_code == 404


def test_other_tenant_gets_not_found_for_pdf_and_bad_ids_are_not_errors(client):
    a, b = _account(client), _account(client)
    doc = _upload(client, a, "Alpha revenue")["document_id"]
    assert client.get(f"/documents/{doc}/pdf", headers=b["h"]).status_code == 404
    assert client.get("/documents/not-a-uuid/pdf", headers=a["h"]).status_code == 404
    assert client.get(f"/documents/{uuid4()}/pdf", headers=a["h"]).status_code == 404


def test_document_list_shows_only_own_documents(client):
    a, b = _account(client), _account(client)
    mine = _upload(client, a, "Alpha revenue")["document_id"]
    theirs = _upload(client, b, "Beta revenue")["document_id"]
    ids = {d["document_id"] for d in client.get("/documents", headers=a["h"]).json()["documents"]}
    assert mine in ids and theirs not in ids


def test_same_file_is_processed_once_per_tenant(client):
    a, b = _account(client), _account(client)
    data = _MINIMAL_PDF + b"%same-file\n"
    first = _upload(client, a, "Alpha revenue", data=data)
    again = _upload(client, a, "Alpha revenue", data=data)
    assert again["deduplicated"] is True and again["document_id"] == first["document_id"]
    other = _upload(client, b, "Alpha revenue", data=data)
    assert other["deduplicated"] is False and other["document_id"] != first["document_id"]


def test_chat_on_another_tenants_document_is_not_found(client):
    a, b = _account(client), _account(client)
    doc = _upload(client, a, "Alpha revenue")["document_id"]
    for path in ("/chat", "/chat/stream"):
        res = client.post(path, headers=b["h"], json={"message": "hi there", "thread_id": f"t-{uuid4().hex}", "document_id": doc})
        assert res.status_code == 404, path
    res = _chat(client, b, f"t-{uuid4().hex}", document_id="not-a-uuid")
    assert res.status_code == 404


def test_corpus_wide_search_never_reaches_another_tenants_text(client):
    a, b = _account(client), _account(client)
    _upload(client, a, "Alpha confidential revenue was ETB 777 billion.")
    _upload(client, b, "Beta public revenue was ETB 5 billion.")
    _RecordingLLM.prompts = []
    res = _chat(client, b, f"t-{uuid4().hex}", message="What was revenue?", federated_search=True)
    assert res.status_code == 200, res.text
    seen = "\n".join(_RecordingLLM.prompts)
    assert "Beta public revenue" in seen  # B's own evidence reached the model
    assert "777" not in seen and "Alpha confidential" not in seen
    assert all("777" not in (c.get("excerpt") or "") for c in res.json()["provenance"])


def test_pinned_chat_cites_the_document(client):
    a = _account(client)
    doc = _upload(client, a, "Alpha revenue was ETB 9 billion.")["document_id"]
    res = _chat(client, a, f"t-{uuid4().hex}", document_id=doc)
    assert res.status_code == 200, res.text
    cites = res.json()["provenance"]
    assert cites and all(c["doc_id"] == doc for c in cites)


# --- P1-9: threads ----------------------------------------------------------------


def test_thread_memory_persists_and_is_listed(client):
    a = _account(client)
    doc = _upload(client, a, "Alpha revenue was ETB 9 billion.")["document_id"]
    thread = f"t-{uuid4().hex}"
    assert _chat(client, a, thread, message="What was revenue?", document_id=doc).status_code == 200
    assert _chat(client, a, thread, message="And in words?").status_code == 200
    history = client.get(f"/history/{thread}", headers=a["h"]).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert history["document_id"] == doc
    threads = client.get("/threads", headers=a["h"]).json()["threads"]
    mine = next(t for t in threads if t["thread_id"] == thread)
    assert mine["message_count"] == 4 and mine["title"] == "What was revenue?"


def test_thread_cannot_be_read_or_taken_over(client):
    from src.db.pool import app_tx

    a, b = _account(client), _account(client)
    thread = f"t-{uuid4().hex}"
    assert _chat(client, a, thread, message="Alpha private question").status_code == 200

    # A colleague in A's own tenant: same tenant, different user.
    tid = jwt.decode(a["token"], options={"verify_signature": False})["tid"]
    with app_tx() as conn:
        uid = conn.execute(
            "INSERT INTO users (tenant_id, email, hashed_password) VALUES (%s, %s, 'x') RETURNING id",
            (tid, f"{uuid4().hex[:8]}@example.com"),
        ).fetchone()["id"]
    colleague = {"Authorization": f"Bearer {create_access_token(str(uid), tid)}"}
    for path in ("/chat", "/chat/stream"):
        res = client.post(path, headers=colleague, json={"message": "what did they ask?", "thread_id": thread})
        assert res.status_code == 404, path
    assert client.get(f"/history/{thread}", headers=colleague).status_code == 404

    # Another tenant reusing the id gets a new, empty thread of its own.
    assert client.get(f"/history/{thread}", headers=b["h"]).status_code == 404
    assert _chat(client, b, thread, message="Beta question").status_code == 200
    contents = [m["content"] for m in client.get(f"/history/{thread}", headers=b["h"]).json()["messages"]]
    assert "Alpha private question" not in contents and "Beta question" in contents
    assert thread not in {t["thread_id"] for t in client.get("/threads", headers=colleague).json()["threads"]}


def test_unknown_or_malformed_thread_history_fails_closed(client):
    a = _account(client)
    assert client.get(f"/history/t-{uuid4().hex}", headers=a["h"]).status_code == 404
    assert client.get("/history/bad%20id", headers=a["h"]).status_code == 404


# --- P0-3: tokens and the signing secret -----------------------------------------


@pytest.mark.parametrize("value", ["", "short", "docmind-dev-secret-change-me-in-production"])
def test_weak_or_public_secrets_are_refused(monkeypatch, value):
    monkeypatch.setenv("JWT_SECRET_KEY", value)
    with pytest.raises(InsecureSecretError):
        jwt_secret()


def test_app_refuses_to_start_without_a_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(InsecureSecretError):
        with TestClient(create_app()):
            pass


def _forged(claims: dict, secret: str | None = None) -> dict:
    return {"Authorization": f"Bearer {jwt.encode(claims, secret or jwt_secret(), algorithm='HS256')}"}


def test_bad_tokens_are_rejected(client):
    a = _account(client)
    claims = jwt.decode(a["token"], options={"verify_signature": False})
    later = datetime.now(timezone.utc) + timedelta(hours=1)
    cases = {
        "old default secret": _forged({**claims, "exp": later}, "docmind-dev-secret-change-me-in-production"),
        "no expiry": _forged({"sub": claims["sub"], "tid": claims["tid"]}),
        "no tenant (pre-M3 token)": _forged({"sub": claims["sub"], "exp": later}),
        "tenant not a uuid": _forged({"sub": claims["sub"], "tid": "' OR 1=1", "exp": later}),
        "expired": _forged({**claims, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}),
    }
    for name, headers in cases.items():
        assert client.get("/documents", headers=headers).status_code == 401, name


# --- M4: queued uploads, status and progress ---------------------------------


def test_upload_is_queued_and_status_is_private(client):
    a, b = _account(client), _account(client)
    data = _MINIMAL_PDF + f"%{uuid4().hex}\n".encode()
    client.pdf_texts[data] = "Alpha revenue was ETB 3 billion."
    res = client.post("/upload", headers=a["h"], files={"file": ("q.pdf", data, "application/pdf")})
    assert res.status_code == 202 and res.json()["status"] == "queued"
    doc = res.json()["document_id"]

    status = client.get(f"/documents/{doc}", headers=a["h"]).json()
    assert status["status"] == "queued" and status["searchable"] is False
    assert client.get(f"/documents/{doc}", headers=b["h"]).status_code == 404
    assert client.get(f"/documents/{doc}/events", headers=b["h"]).status_code == 404

    # Asking about a document that is still being read is a clear 409, not an empty answer.
    res = _chat(client, a, f"t-{uuid4().hex}", document_id=doc)
    assert res.status_code == 409 and "still being read" in res.json()["detail"]
    res = client.post("/chat/stream", headers=a["h"], json={"message": "hi there", "thread_id": f"t-{uuid4().hex}", "document_id": doc})
    assert res.status_code == 409

    from src.jobs.worker import run_once

    run_once()
    status = client.get(f"/documents/{doc}", headers=a["h"]).json()
    assert status["status"] == "indexed" and status["searchable"] and status["progress"] == 1.0
    sig = client.post(f"/documents/{doc}/link", headers=a["h"]).json()["url"].split("sig=", 1)[1]
    events = client.get(f"/documents/{doc}/events", params={"sig": sig}).text
    assert "event: progress" in events and '"status": "indexed"' in events and "event: end" in events


# --- M7: cost ledger and spending caps ------------------------------------------


def test_usage_is_recorded_per_account_and_the_cap_blocks_only_that_account(client, monkeypatch):
    a, b = _account(client), _account(client)
    doc = _upload(client, a, "Alpha revenue was ETB 9 billion.")["document_id"]
    res = _chat(client, a, f"t-{uuid4().hex}", document_id=doc)
    assert res.status_code == 200, res.text
    footer = res.json()["usage"]
    assert footer["llm_calls"] == 1 and footer["cost_usd"] == 0.01 and footer["model"] == "fake"

    mine = client.get("/usage", headers=a["h"]).json()
    assert mine["spent_usd"] >= 0.01
    assert any(r["purpose"] == "answer" for r in mine["by_purpose"])
    assert client.get("/usage", headers=b["h"]).json()["spent_usd"] == 0  # B never sees A's rows

    monkeypatch.setenv("DOCMIND_TENANT_MONTHLY_BUDGET_USD", "0.005")
    blocked = _chat(client, a, f"t-{uuid4().hex}", document_id=doc)
    assert blocked.status_code == 402 and "monthly model budget" in blocked.json()["detail"]
    doc_b = _upload(client, b, "Beta revenue was ETB 5 billion.")["document_id"]
    assert _chat(client, b, f"t-{uuid4().hex}", document_id=doc_b).status_code == 200


def test_a_model_the_server_cannot_run_is_refused(client, monkeypatch):
    from src.llm import factory

    monkeypatch.setattr("src.api.services.client_for_request", factory.client_for_request)
    a = _account(client)
    doc = _upload(client, a, "Alpha revenue was ETB 9 billion.")["document_id"]
    res = _chat(client, a, f"t-{uuid4().hex}", document_id=doc, model="gemini-2.5-flash-lite")
    assert res.status_code == 400 and "no gemini API key" in res.json()["detail"]
    res = _chat(client, a, f"t-{uuid4().hex}", document_id=doc, model="made-up-model")
    assert res.status_code == 400 and "not in the model registry" in res.json()["detail"]
