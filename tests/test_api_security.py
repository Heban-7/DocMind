"""Security regression tests for milestone M0 (audit findings P0-1, P0-3, P1-9).

Each test exercises the real auth dependency with real signed tokens; nothing
here overrides ``get_current_user_id``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from src import config
from src.api import ownership
from src.api.auth_utils import InsecureSecretError, create_access_token, jwt_secret
from src.api.main import create_app

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _make_document(tmp_path: Path, owner: str | None) -> str:
    """Write a profile + PDF the API can resolve; optionally record an owner."""
    doc_id = uuid4().hex[:12]
    pdf = tmp_path / f"{doc_id}.pdf"
    pdf.write_bytes(_MINIMAL_PDF)
    config.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    (config.PROFILES_DIR / f"{doc_id}.json").write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "source_path": str(pdf),
                "source_filename": pdf.name,
                "page_count": 1,
            }
        ),
        encoding="utf-8",
    )
    if owner:
        ownership.record_document_owner(doc_id, owner)
    return doc_id


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


# --- P0-1: PDF downloads need a login and ownership ---------------------------


def test_pdf_requires_a_token(client, tmp_path):
    doc_id = _make_document(tmp_path, owner="alice")
    assert client.get(f"/documents/{doc_id}/pdf").status_code == 401


def test_pdf_rejects_a_bad_token(client, tmp_path):
    doc_id = _make_document(tmp_path, owner="alice")
    res = client.get(f"/documents/{doc_id}/pdf", params={"token": "not-a-jwt"})
    assert res.status_code == 401


def test_owner_can_download_pdf_by_header_and_by_query_token(client, tmp_path):
    doc_id = _make_document(tmp_path, owner="alice")
    res = client.get(f"/documents/{doc_id}/pdf", headers=_auth("alice"))
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    res = client.get(
        f"/documents/{doc_id}/pdf", params={"token": create_access_token("alice")}
    )
    assert res.status_code == 200


def test_other_user_gets_not_found_for_pdf(client, tmp_path):
    doc_id = _make_document(tmp_path, owner="alice")
    res = client.get(f"/documents/{doc_id}/pdf", headers=_auth("mallory"))
    assert res.status_code == 404


def test_legacy_unowned_documents_are_hidden_by_default(client, tmp_path, monkeypatch):
    doc_id = _make_document(tmp_path, owner=None)
    assert client.get(f"/documents/{doc_id}/pdf", headers=_auth("alice")).status_code == 404
    monkeypatch.setenv("DOCMIND_LEGACY_SHARED_DOCS", "1")
    assert client.get(f"/documents/{doc_id}/pdf", headers=_auth("alice")).status_code == 200


def test_document_list_shows_only_own_documents(client, tmp_path):
    mine = _make_document(tmp_path, owner="alice")
    theirs = _make_document(tmp_path, owner="bob")
    ids = {d["document_id"] for d in client.get("/documents", headers=_auth("alice")).json()["documents"]}
    assert mine in ids
    assert theirs not in ids


def test_chat_on_someone_elses_document_is_not_found(client, tmp_path):
    theirs = _make_document(tmp_path, owner="bob")
    res = client.post(
        "/chat",
        headers=_auth("alice"),
        json={"message": "hi there", "thread_id": f"t-{uuid4().hex}", "document_id": theirs},
    )
    assert res.status_code == 404


# --- P1-9: threads cannot be taken over or read by another user ---------------


def test_thread_cannot_be_hijacked_or_read(client):
    thread = f"t-{uuid4().hex}"
    ownership.claim_thread(thread, "alice")

    for path in ("/chat", "/chat/stream"):
        res = client.post(
            path,
            headers=_auth("mallory"),
            json={"message": "what did alice ask?", "thread_id": thread},
        )
        assert res.status_code == 404, path

    assert client.get(f"/history/{thread}", headers=_auth("mallory")).status_code == 404
    assert ownership.thread_owner(thread) == "alice"


def test_unknown_thread_history_fails_closed(client):
    res = client.get(f"/history/t-{uuid4().hex}", headers=_auth("alice"))
    assert res.status_code == 404


# --- P0-3: the signing secret cannot be a default ------------------------------


@pytest.mark.parametrize(
    "value",
    ["", "short", "docmind-dev-secret-change-me-in-production"],
)
def test_weak_or_public_secrets_are_refused(monkeypatch, value):
    monkeypatch.setenv("JWT_SECRET_KEY", value)
    with pytest.raises(InsecureSecretError):
        jwt_secret()


def test_app_refuses_to_start_without_a_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(InsecureSecretError):
        with TestClient(create_app()):
            pass


def test_token_signed_with_the_old_default_secret_is_rejected(client, tmp_path):
    doc_id = _make_document(tmp_path, owner="alice")
    forged = jwt.encode(
        {"sub": "alice", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "docmind-dev-secret-change-me-in-production",
        algorithm="HS256",
    )
    res = client.get(f"/documents/{doc_id}/pdf", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401


def test_token_without_expiry_is_rejected(client):
    no_exp = jwt.encode({"sub": "alice"}, jwt_secret(), algorithm="HS256")
    res = client.get("/documents", headers={"Authorization": f"Bearer {no_exp}"})
    assert res.status_code == 401
