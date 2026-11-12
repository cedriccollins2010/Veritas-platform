from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app


def test_liveness_does_not_need_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["application"] == "VERITAS"


class _BrokenSession:
    def execute(self, *_args, **_kwargs):
        raise ConnectionError("base indisponible")

    def close(self) -> None:
        pass


def test_readiness_reports_503_when_database_is_down(client: TestClient) -> None:
    app.dependency_overrides[get_db] = lambda: _BrokenSession()
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["database"] == "down"


def test_cors_allows_configured_frontend_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
