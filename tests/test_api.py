"""Offline smoke tests for the DocMind FastAPI gateway."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.schemas import ChatResponse, HistoryResponse, UploadResponse


def _client() -> TestClient:
    return TestClient(create_app())


def test_health():
    res = _client().get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"]


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
    assert res.status_code == 201
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
    with patch("src.api.routers.run_chat", return_value=fake):
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


def test_save_upload_writes_pdf(tmp_path):
    from src.api.services import save_upload

    upload = MagicMock()
    upload.filename = "My Report!.pdf"
    upload.content_type = "application/pdf"
    upload.file = MagicMock()
    # copyfileobj reads from .file
    from io import BytesIO

    upload.file = BytesIO(b"%PDF-1.4 content")
    path = save_upload(upload, destination_dir=tmp_path)
    assert path.exists()
    assert path.suffix.lower() == ".pdf"
    assert path.read_bytes().startswith(b"%PDF")


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

