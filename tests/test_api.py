from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_initial():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] >= 0
    assert "by_method" in data


def test_classify_invalid_mime_type():
    # Only images are allowed
    files = {"files": ("test.txt", b"hello world", "text/plain")}
    response = client.post("/classify", files=files)
    assert response.status_code == 422
    assert "Unsupported file type" in response.text


def test_classify_missing_files():
    response = client.post("/classify")
    assert response.status_code == 422


# Mocks for actual classification would be complex for the FastAPI client 
# unless we override dependencies, which the original didn't cleanly do.
# The original tests relied on a similar level of coverage.
