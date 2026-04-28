import io
import json
from unittest.mock import MagicMock, patch


def _ndjson(resp):
    """Parse an NDJSON response body into a list of records."""
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]

import pytest
from fastapi.testclient import TestClient

from src.classifier import ClassificationResult

# ── helpers ───────────────────────────────────────────────────────────────────

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _make_result(**kwargs) -> ClassificationResult:
    defaults = dict(
        filename="test.png",
        doc_type="bill",
        sub_type=None,
        method="rules",
        latency_ms=1,
        input_tokens=0,
        output_tokens=0,
    )
    return ClassificationResult(**{**defaults, **kwargs})


def _upload(filename: str, content: bytes = FAKE_PNG, content_type: str = "image/png"):
    return ("files", (filename, io.BytesIO(content), content_type))


# Patch classify at the api module level (where it is imported)
CLASSIFY_PATCH = "src.api.classify"


@pytest.fixture()
def client():
    """TestClient with the classify pipeline fully mocked."""
    from src.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── GET /health ───────────────────────────────────────────────────────────────

def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── GET /metrics ──────────────────────────────────────────────────────────────

def test_metrics_returns_200(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_requests" in data
    assert "total_documents" in data
    assert "by_method" in data
    assert "by_doc_type" in data


# ── POST /classify — bill file ────────────────────────────────────────────────

def test_classify_bill_file_returns_200(client):
    with patch(CLASSIFY_PATCH, return_value=_make_result(
        filename="bill_innovh_01.png", doc_type="bill", method="rules"
    )):
        resp = client.post("/classify", files=[_upload("bill_innovh_01.png")])
    assert resp.status_code == 200


def test_classify_bill_file_doc_type(client):
    with patch(CLASSIFY_PATCH, return_value=_make_result(
        filename="bill_innovh_01.png", doc_type="bill", method="rules"
    )):
        resp = client.post("/classify", files=[_upload("bill_innovh_01.png")])
    body = _ndjson(resp)
    assert body[0]["doc_type"] == "bill"
    assert body[0]["method"] == "rules"


# ── POST /classify — multiple files ──────────────────────────────────────────

def test_classify_multiple_files_returns_array(client):
    results = [
        _make_result(filename=f"doc_{i}.png", doc_type="image", method="llm", sub_type="Medical Reports")
        for i in range(5)
    ]
    with patch(CLASSIFY_PATCH, side_effect=results):
        files = [_upload(f"doc_{i}.png") for i in range(5)]
        resp = client.post("/classify", files=files)
    assert resp.status_code == 200
    assert len(_ndjson(resp)) == 5


def test_classify_response_schema_has_required_fields(client):
    with patch(CLASSIFY_PATCH, return_value=_make_result(
        doc_type="image", sub_type="Prescriptions", method="llm"
    )):
        resp = client.post("/classify", files=[_upload("test.png")])
    record = _ndjson(resp)[0]
    for field in ("filename", "doc_type", "sub_type", "method", "latency_ms"):
        assert field in record, f"Missing field: {field}"


# ── POST /classify — validation errors ───────────────────────────────────────

def test_classify_unsupported_mime_type_returns_422(client):
    resp = client.post("/classify", files=[_upload("doc.pdf", content_type="application/pdf")])
    assert resp.status_code == 422


def test_classify_unsupported_mime_type_error_message(client):
    resp = client.post("/classify", files=[_upload("doc.pdf", content_type="application/pdf")])
    assert "Unsupported" in resp.json()["detail"]


def test_classify_jpeg_is_accepted(client):
    with patch(CLASSIFY_PATCH, return_value=_make_result()):
        resp = client.post("/classify", files=[_upload("photo.jpg", content_type="image/jpeg")])
    assert resp.status_code == 200


# ── POST /classify — metrics updated ─────────────────────────────────────────

def test_classify_increments_total_requests(client):
    import src.api as api_module
    api_module._metrics["total_requests"] = 0

    with patch(CLASSIFY_PATCH, return_value=_make_result()):
        client.post("/classify", files=[_upload("bill.png")])

    assert api_module._metrics["total_requests"] == 1


def test_classify_increments_total_documents(client):
    import src.api as api_module
    api_module._metrics["total_documents"] = 0

    results = [_make_result(filename=f"f{i}.png") for i in range(3)]
    with patch(CLASSIFY_PATCH, side_effect=results):
        client.post("/classify", files=[_upload(f"f{i}.png") for i in range(3)])

    assert api_module._metrics["total_documents"] == 3
