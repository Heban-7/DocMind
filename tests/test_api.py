"""Offline smoke tests for the DocMind FastAPI gateway (services mocked, no database).

Real register/login and the isolation guarantees are in tests/test_api_security.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.dependencies import get_principal, get_principal_or_file_link
from src.api.main import create_app
from src.api.schemas import ChatResponse, HistoryResponse, UploadResponse
from src.db.repos import Principal

_PRINCIPAL = Principal(
    user_id="00000000-0000-4000-8000-000000000001",
    tenant_id="00000000-0000-4000-8000-0000000000aa",
)


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: _PRINCIPAL
    app.dependency_overrides[get_principal_or_file_link] = lambda: _PRINCIPAL
    return TestClient(app)


def _unauth_client() -> TestClient:
    return TestClient(create_app())


def test_health():
    res = _client().get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_protected_endpoints_require_auth():
    client = _unauth_client()
    assert client.post("/upload").status_code == 401
    assert client.post("/chat", json={"message": "hi", "thread_id": "t1"}).status_code == 401
    assert client.get("/history/t1").status_code == 401
    assert client.get("/threads").status_code == 401
    assert client.get("/documents").status_code == 401
    assert client.get("/documents/any/pdf").status_code == 401
    assert client.post("/chat/stream", json={"message": "hi", "thread_id": "t1"}).status_code == 401


def test_upload_rejects_non_pdf():
    res = _client().post(
        "/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400
    assert "PDF" in res.json()["detail"]


def test_upload_success_mocked():
    fake = UploadResponse(
        document_id="abc123",
        file_name="report.pdf",
        page_count=12,
        strategy_tier="needs_layout_model",
        status="indexed",
    )
    with patch("src.api.routers.process_upload", return_value=fake):
        res = _client().post(
            "/upload",
            files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert res.status_code == 202
    assert res.json()["document_id"] == "abc123"
    assert res.json()["page_count"] == 12


def test_chat_success_mocked():
    fake = ChatResponse(
        response="Import tax was ETB 120.7 billion.",
        thread_id="t-1",
        provenance=[
            {
                "document_name": "sample.pdf",
                "page_number": 4,
                "excerpt": "ETB 120.7 billion",
            }
        ],
    )
    with patch("src.api.routers.prepare_chat", return_value=MagicMock()), patch("src.api.routers.run_chat", return_value=fake):
        res = _client().post(
            "/chat",
            json={
                "message": "What was import tax?",
                "thread_id": "t-1",
                "document_id": "212dc42370e2",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["thread_id"] == "t-1"
    assert len(body["provenance"]) == 1


def test_chat_validation_error():
    res = _client().post("/chat", json={"message": "", "thread_id": "t-1"})
    assert res.status_code == 422


def test_chat_with_custom_model_parameter():
    fake = ChatResponse(
        response="Model selected response",
        provenance=[],
        thread_id="t-99",
    )
    with patch("src.api.routers.prepare_chat", return_value=MagicMock()) as mock_prep, patch(
        "src.api.routers.run_chat", return_value=fake
    ) as mock_run:
        res = _client().post(
            "/chat",
            json={
                "message": "Summarize this",
                "model": "GPT-4o",
                "thread_id": "t-99",
            },
        )
    assert res.status_code == 200
    assert res.json()["response"] == "Model selected response"
    mock_run.assert_called_once()
    assert mock_prep.call_args.args[0].model == "GPT-4o"


def test_chat_without_a_model_uses_the_server_default_not_gpt_4o():
    from src.api.schemas import ChatRequest

    assert ChatRequest(message="hi", thread_id="t").model is None


def test_provider_failure_is_an_error_status_not_a_refusal():
    from src.llm.errors import LLMError

    boom = LLMError("ReadTimeout after 3 attempt(s)", kind="timeout", provider="openai")
    with patch("src.api.routers.prepare_chat", return_value=MagicMock()), patch("src.api.routers.run_chat", side_effect=boom):
        res = _client().post("/chat", json={"message": "What was revenue?", "thread_id": "t-1"})
    assert res.status_code == 504
    assert "did not answer in time" in res.json()["detail"]


def test_spending_cap_and_unknown_model_are_refused_before_any_work():
    from src.llm.errors import ModelNotAvailableError, SpendingCapError

    with patch("src.api.routers.prepare_chat", side_effect=SpendingCapError("This account has used its monthly model budget.")):
        assert _client().post("/chat", json={"message": "q", "thread_id": "t"}).status_code == 402
        assert _client().post("/chat/stream", json={"message": "q", "thread_id": "t"}).status_code == 402
    with patch("src.api.routers.prepare_chat", side_effect=ModelNotAvailableError("Model 'x' is not available.")):
        assert _client().post("/chat", json={"message": "q", "thread_id": "t", "model": "x"}).status_code == 400


def test_models_endpoint_lists_prices_and_capabilities():
    res = _client().get("/models")
    assert res.status_code == 200
    body = res.json()
    ids = {m["id"]: m for m in body["models"]}
    assert "gpt-4o-mini" in ids and "gemini-2.5-flash-lite" in ids
    m = ids["gpt-4o-mini"]
    assert m["price"]["input_per_m"] == 0.15 and m["price"]["checked_on"] == body["prices_checked_on"]
    assert m["capabilities"]["vision"] is True
    assert m["available"] is False and "API key" in m["unavailable_reason"]  # tests run without keys
    assert ids["gemini-2.5-flash-lite"]["free_tier"] is True


def test_stream_sends_tokens_then_the_checked_answer():
    import json as _json

    from src.api import services

    class _Agent:
        class deps:  # noqa: N801
            class llm:  # noqa: N801
                model, provider = "gpt-4o-mini", "openai"

        def ask(self, message, *, thread_id, on_token, mode):
            from src.models.provenance import ProvenanceChain
            from src.models.query import QueryAnswer

            on_token("It was ")
            on_token("ETB 5 [Page 2].")
            return QueryAnswer(
                question=message, answer="Not found in the document: x.", provenance=ProvenanceChain(),
                status="not_found", usage={"llm_calls": 1, "cost_usd": 0.0004}, timings={"total_s": 1.2, "first_token_s": 0.6},
            )

    prepared = services.PreparedChat(agent=_Agent(), doc_pin=None, mode="balanced")
    payload = services.ChatRequest(message="q", thread_id="t")
    with patch("src.api.services.ledger.record"), patch("src.api.services.repos.record_turn"):
        events = [
            _json.loads(chunk[len("data: "):])
            for chunk in services.run_chat_stream(payload, principal=_PRINCIPAL, prepared=prepared)
        ]
    assert [e["type"] for e in events] == ["token", "token", "done"]
    assert events[-1]["answer"].startswith("Not found") and events[-1]["status"] == "not_found"
    assert events[-1]["usage"]["model"] == "gpt-4o-mini" and events[-1]["usage"]["first_token_s"] == 0.6


def test_stream_reports_a_provider_failure_as_an_error_event():
    import json as _json

    from src.api import services
    from src.llm.errors import LLMError

    class _Agent:
        class deps:  # noqa: N801
            class llm:  # noqa: N801
                model, provider = "gpt-4o-mini", "openai"

        def ask(self, *a, **k):
            raise LLMError("ConnectError", kind="network", provider="openai")

    prepared = services.PreparedChat(agent=_Agent(), doc_pin=None, mode="balanced")
    with patch("src.api.services.ledger.record"):
        events = [
            _json.loads(c[len("data: "):])
            for c in services.run_chat_stream(services.ChatRequest(message="q", thread_id="t"), principal=_PRINCIPAL, prepared=prepared)
        ]
    assert events == [{"type": "error", "kind": "network", "message": "Could not reach openai (network error). Please try again."}]


def test_history_mocked():
    fake = HistoryResponse(
        thread_id="t-1",
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ],
    )
    with patch("src.api.routers.fetch_history", return_value=fake):
        res = _client().get("/history/t-1")
    assert res.status_code == 200
    assert len(res.json()["messages"]) == 2


def test_cors_headers_for_localhost():
    res = _client().options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code in {200, 204}
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def _upload(name: str, data: bytes, content_type: str = "application/pdf"):
    from io import BytesIO

    upload = MagicMock()
    upload.filename = name
    upload.content_type = content_type
    upload.file = BytesIO(data)
    return upload


def test_spool_upload_writes_pdf(tmp_path):
    from src.api.services import _spool_upload

    path = _spool_upload(_upload("My Report!.pdf", b"%PDF-1.4 content"), tmp_path)
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")


def test_spool_upload_rejects_empty_fake_and_oversized(tmp_path, monkeypatch):
    import pytest

    from src.api.services import _spool_upload

    with pytest.raises(ValueError, match="empty"):
        _spool_upload(_upload("a.pdf", b""), tmp_path)
    with pytest.raises(ValueError, match="not a PDF"):
        _spool_upload(_upload("a.pdf", b"<html>not a pdf</html>"), tmp_path)
    monkeypatch.setenv("DOCMIND_MAX_UPLOAD_MB", "0.001")
    with pytest.raises(ValueError, match="larger than"):
        _spool_upload(_upload("a.pdf", b"%PDF-" + b"x" * 5000), tmp_path)


def test_threads_endpoint_mocked():
    from src.api.schemas import ThreadListResponse, ThreadSummary

    fake = ThreadListResponse(
        threads=[
            ThreadSummary(thread_id="t-1", title="Q3 Review", message_count=4)
        ]
    )
    with patch("src.api.routers.list_threads", return_value=fake):
        res = _client().get("/threads")
    assert res.status_code == 200
    assert len(res.json()["threads"]) == 1
    assert res.json()["threads"][0]["thread_id"] == "t-1"


def test_documents_endpoint_mocked():
    from src.api.schemas import DocumentInfo, DocumentListResponse

    fake = DocumentListResponse(
        documents=[
            DocumentInfo(
                document_id="doc1",
                file_name="test.pdf",
                page_count=5,
                strategy_tier="fast",
                status="indexed",
            )
        ]
    )
    with patch("src.api.routers.list_documents", return_value=fake):
        res = _client().get("/documents")
    assert res.status_code == 200
    assert len(res.json()["documents"]) == 1
    assert res.json()["documents"][0]["document_id"] == "doc1"


def test_pdf_endpoint_404_when_missing():
    with patch("src.api.routers.get_pdf_file_path", side_effect=FileNotFoundError("Missing")):
        res = _client().get("/documents/nonexistent/pdf")
    assert res.status_code == 404
