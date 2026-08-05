from collections.abc import Mapping

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class StubHealthService:
    def __init__(self, checks: Mapping[str, bool]) -> None:
        self._checks = dict(checks)

    async def readiness(self) -> dict[str, bool]:
        return self._checks


def test_health_and_metrics_endpoints() -> None:
    app = create_app(Settings(_env_file=None, app_env="test"))

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "text/plain" in metrics_response.headers["content-type"]


def test_readiness_returns_200_when_dependencies_are_ready() -> None:
    app = create_app(Settings(_env_file=None, app_env="test"))

    with TestClient(app) as client:
        app.state.health_service = StubHealthService({"postgres": True, "redis": True})
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_returns_503_when_a_dependency_is_down() -> None:
    app = create_app(Settings(_env_file=None, app_env="test"))

    with TestClient(app) as client:
        app.state.health_service = StubHealthService({"postgres": True, "redis": False})
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"postgres": True, "redis": False},
    }
