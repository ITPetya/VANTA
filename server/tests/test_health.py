from fastapi.testclient import TestClient

from server.api.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/internal/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_no_docs_or_openapi() -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_health_rejects_post() -> None:
    assert client.post("/internal/health").status_code == 405
