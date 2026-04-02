# libraries/python/neural_hive_api/tests/test_health_router.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from neural_hive_api.health import HealthRouter, HealthStatus, CheckResult, BaseHealthCheck


class ExceptionCheck(BaseHealthCheck):
    """Check que lança exceção para testar error handling."""

    def __init__(self, name: str = "exception_check", critical: bool = True):
        super().__init__(name, critical)

    async def check(self):
        raise RuntimeError("Simulated failure")


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


@pytest.mark.asyncio
async def test_execute_checks_handles_exception():
    """_execute_checks deve tratar exceções e retornar UNHEALTHY."""
    router = HealthRouter("test-service")
    router.register_check(ExceptionCheck())

    checks = await router._execute_checks()

    assert "exception_check" in checks
    status, critical = checks["exception_check"]
    assert status == HealthStatus.UNHEALTHY
    assert critical is True


@pytest.mark.asyncio
async def test_aggregate_multiple_checks():
    """_aggregate_status deve considerar múltiplos checks corretamente."""
    router = HealthRouter("test-service")

    # Nenhum check -> HEALTHY
    assert router._aggregate_status({}) == HealthStatus.HEALTHY

    # Todos HEALTHY -> HEALTHY
    all_healthy = {"check1": (HealthStatus.HEALTHY, True)}
    assert router._aggregate_status(all_healthy) == HealthStatus.HEALTHY

    # Check crítico UNHEALTHY -> UNHEALTHY
    critical_unhealthy = {"check1": (HealthStatus.UNHEALTHY, True)}
    assert router._aggregate_status(critical_unhealthy) == HealthStatus.UNHEALTHY

    # Check não-crítico UNHEALTHY -> DEGRADED
    non_critical_unhealthy = {"check1": (HealthStatus.UNHEALTHY, False)}
    assert router._aggregate_status(non_critical_unhealthy) == HealthStatus.DEGRADED


@pytest.mark.asyncio
async def test_degraded_when_critical_check_fails():
    """Health deve retornar degraded quando check crítico retorna DEGRADED."""
    router = HealthRouter("test-service")

    class DegradedCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("degraded", critical=True)

        async def check(self):
            return CheckResult(name="degraded", status=HealthStatus.DEGRADED, message="Slow")

    router.register_check(DegradedCheck())
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_endpoint_returns_timestamp_in_utc():
    """Health endpoint deve retornar timestamp válido."""
    router = HealthRouter("test-service")
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "timestamp" in data
    # Timestamp deve ser uma string ISO format válida
    assert isinstance(data["timestamp"], str)


@pytest.mark.asyncio
async def test_multiple_checks_aggregation():
    """Router deve agregar corretamente múltiplos checks com estados mistos."""
    router = HealthRouter("test-service")

    class HealthyCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("healthy", critical=False)

        async def check(self):
            return CheckResult(name="healthy", status=HealthStatus.HEALTHY)

    class DegradedCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("degraded", critical=False)

        async def check(self):
            return CheckResult(name="degraded", status=HealthStatus.DEGRADED)

    router.register_check(HealthyCheck())
    router.register_check(DegradedCheck())
    app = FastAPI()
    router.add_route(app)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert "healthy" in data["checks"]
    assert "degraded" in data["checks"]
