# libraries/python/neural_hive_api/tests/test_health_router.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from neural_hive_api.health import HealthRouter, HealthStatus, CheckResult, BaseHealthCheck


@pytest.mark.asyncio
async def test_health_router_creates_endpoints():
    """Router deve criar /health, /health/live, /health/ready."""
    router = HealthRouter("test-service")
    app = FastAPI()
    router.add_route(app)

    routes = [r.path for r in app.routes]
    assert "/health" in routes
    assert "/health/live" in routes
    assert "/health/ready" in routes


@pytest.mark.asyncio
async def test_health_returns_200_when_healthy():
    """Health deve retornar 200 quando saudável."""
    router = HealthRouter("test-service")
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "test-service"


@pytest.mark.asyncio
async def test_health_degraded_when_non_critical_check_fails():
    """Health deve retornar degraded quando check não-crítico falha."""
    router = HealthRouter("test-service")

    class FailingCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("failing", critical=False)

        async def check(self):
            return CheckResult(name="failing", status=HealthStatus.UNHEALTHY, message="Failed")

    router.register_check(FailingCheck())
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_liveness_always_returns_healthy():
    """Liveness probe deve sempre retornar healthy."""
    router = HealthRouter("test-service")

    class FailingCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("failing", critical=True)

        async def check(self):
            return CheckResult(name="failing", status=HealthStatus.UNHEALTHY, message="Failed")

    router.register_check(FailingCheck())
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_unhealthy_when_critical_check_fails():
    """Readiness deve retornar unhealthy quando check crítico falha."""
    router = HealthRouter("test-service")

    class FailingCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("failing", critical=True)

        async def check(self):
            return CheckResult(name="failing", status=HealthStatus.UNHEALTHY, message="Failed")

    router.register_check(FailingCheck())
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_register_check_adds_to_list():
    """register_check deve adicionar check à lista."""
    router = HealthRouter("test-service")

    class DummyCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("dummy")

        async def check(self):
            return CheckResult(name="dummy", status=HealthStatus.HEALTHY)

    check = DummyCheck()
    router.register_check(check)

    assert len(router.checks) == 1
    assert router.checks[0] is check
