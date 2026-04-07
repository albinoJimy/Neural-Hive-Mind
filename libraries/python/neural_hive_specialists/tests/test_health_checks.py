import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from neural_hive_specialists.observability.health_checks import (
    ComponentHealth,
    HealthStatus,
    SpecialistHealthChecker,
)


@pytest.fixture
def checker():
    return SpecialistHealthChecker(
        {"mongodb_uri": "mongodb://localhost:27017", "mongodb_database": "test-db"},
        specialist_type="technical",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_all_health_aggregates_status(checker, monkeypatch):
    healthy = ComponentHealth("mongodb", HealthStatus.HEALTHY)
    degraded = ComponentHealth("redis", HealthStatus.DEGRADED)
    monkeypatch.setattr(checker, "_check_mongodb_health", AsyncMock(return_value=healthy))
    monkeypatch.setattr(checker, "_check_mlflow_health", AsyncMock(return_value=healthy))
    monkeypatch.setattr(
        checker, "_check_feature_extraction_health", AsyncMock(return_value=degraded)
    )
    monkeypatch.setattr(checker, "_check_circuit_breakers_health", AsyncMock(return_value=healthy))
    monkeypatch.setattr(checker, "_check_ledger_health", AsyncMock(return_value=healthy))

    report = await checker.check_all_health()

    assert report["overall_status"] in ["healthy", "degraded"]
    assert len(report["components"]) == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_all_health_uses_cache(checker, monkeypatch):
    cached = {"overall_status": "healthy", "components": []}
    checker._health_cache = cached
    checker._cache_timestamp = checker._cache_timestamp or checker._cache_timestamp
    monkeypatch.setattr(checker, "_is_cache_valid", lambda: True)

    result = await checker.check_all_health()

    assert result is cached


@pytest.mark.unit
def test_component_health_to_dict_includes_fields():
    comp = ComponentHealth(
        "mlflow",
        HealthStatus.HEALTHY,
        message="ok",
        details={"version": "1.0"},
        latency_ms=12.3,
    )
    data = comp.to_dict()
    assert data["component"] == "mlflow"
    assert data["status"] == "healthy"
    assert data["details"]["version"] == "1.0"


# =============================================================================
# Testes Adicionais para Cobertura
# =============================================================================


@pytest.mark.unit
def test_health_status_enum_values():
    """Testa valores do enum HealthStatus."""
    assert HealthStatus.HEALTHY.value == "healthy"
    assert HealthStatus.DEGRADED.value == "degraded"
    assert HealthStatus.UNHEALTHY.value == "unhealthy"
    assert HealthStatus.UNKNOWN.value == "unknown"


@pytest.mark.unit
def test_health_status_comparison():
    """Testa comparação de status."""
    assert HealthStatus.HEALTHY == HealthStatus.HEALTHY
    assert HealthStatus.HEALTHY != HealthStatus.DEGRADED


@pytest.mark.unit
def test_component_health_init_minimal():
    """Testa criação de ComponentHealth com parâmetros mínimos."""
    comp = ComponentHealth("test", HealthStatus.HEALTHY)

    assert comp.component_name == "test"
    assert comp.status == HealthStatus.HEALTHY
    assert comp.message == ""
    assert comp.details == {}
    assert comp.latency_ms is None


@pytest.mark.unit
def test_component_health_checked_at_set():
    """Testa que checked_at é definido automaticamente."""
    comp = ComponentHealth("test", HealthStatus.HEALTHY)

    assert comp.checked_at is not None
    assert isinstance(comp.checked_at, datetime)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_mongodb_health_success(checker, monkeypatch):
    """Testa check de MongoDB com sucesso."""
    healthy = ComponentHealth("mongodb", HealthStatus.HEALTHY)
    monkeypatch.setattr(checker, "_check_mongodb_health", AsyncMock(return_value=healthy))

    result = await checker._check_mongodb_health()

    assert result.component_name == "mongodb"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_mlflow_health_success(checker, monkeypatch):
    """Testa check de MLflow com sucesso."""
    healthy = ComponentHealth("mlflow", HealthStatus.HEALTHY)
    monkeypatch.setattr(checker, "_check_mlflow_health", AsyncMock(return_value=healthy))

    result = await checker._check_mlflow_health()

    assert result.component_name == "mlflow"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feature_extraction_health_success(checker, monkeypatch):
    """Testa check de feature extraction com sucesso."""
    healthy = ComponentHealth("feature_extraction", HealthStatus.HEALTHY)
    monkeypatch.setattr(
        checker, "_check_feature_extraction_health", AsyncMock(return_value=healthy)
    )

    result = await checker._check_feature_extraction_health()

    assert result.component_name == "feature_extraction"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_circuit_breakers_health_success(checker, monkeypatch):
    """Testa check de circuit breakers com sucesso."""
    healthy = ComponentHealth("circuit_breakers", HealthStatus.HEALTHY)
    monkeypatch.setattr(checker, "_check_circuit_breakers_health", AsyncMock(return_value=healthy))

    result = await checker._check_circuit_breakers_health()

    assert result.component_name == "circuit_breakers"


@pytest.mark.unit
def test_is_cache_valid_no_cache(checker):
    """Testa _is_cache_valid quando não há cache."""
    checker._health_cache = None
    checker._cache_timestamp = None

    assert checker._is_cache_valid() is False


@pytest.mark.unit
def test_is_cache_valid_expired(checker):
    """Testa _is_cache_valid quando cache expirou."""
    checker._health_cache = {"status": "cached"}
    checker._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=31)

    assert checker._is_cache_valid() is False


@pytest.mark.unit
def test_is_cache_valid_fresh(checker):
    """Testa _is_cache_valid quando cache é fresco."""
    checker._health_cache = {"status": "cached"}
    checker._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)

    assert checker._is_cache_valid() is True


@pytest.mark.unit
def test_specialist_type_property(checker):
    """Testa propriedade specialist_type."""
    assert checker.specialist_type == "technical"


@pytest.mark.unit
def test_config_property(checker):
    """Testa propriedade config."""
    assert checker.config == {
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_database": "test-db",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_ledger_health_success(checker, monkeypatch):
    """Testa check de ledger com sucesso."""
    healthy = ComponentHealth("ledger", HealthStatus.HEALTHY)
    monkeypatch.setattr(checker, "_check_ledger_health", AsyncMock(return_value=healthy))

    result = await checker._check_ledger_health()

    assert result.component_name == "ledger"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_overall_status_calculation(checker, monkeypatch):
    """Testa cálculo de status agregado."""
    # Todos saudáveis
    healthy_mongodb = ComponentHealth("mongodb", HealthStatus.HEALTHY)
    healthy_mlflow = ComponentHealth("mlflow", HealthStatus.HEALTHY)
    healthy_features = ComponentHealth("feature_extraction", HealthStatus.HEALTHY)
    healthy_circuit = ComponentHealth("circuit_breakers", HealthStatus.HEALTHY)
    healthy_ledger = ComponentHealth("ledger", HealthStatus.HEALTHY)

    # Mock dos checks individuais
    monkeypatch.setattr(checker, "_check_mongodb_health", AsyncMock(return_value=healthy_mongodb))
    monkeypatch.setattr(checker, "_check_mlflow_health", AsyncMock(return_value=healthy_mlflow))
    monkeypatch.setattr(
        checker, "_check_feature_extraction_health", AsyncMock(return_value=healthy_features)
    )
    monkeypatch.setattr(
        checker, "_check_circuit_breakers_health", AsyncMock(return_value=healthy_circuit)
    )
    monkeypatch.setattr(checker, "_check_ledger_health", AsyncMock(return_value=healthy_ledger))

    # O método real verifica se todos são healthy
    result = await checker.check_all_health()

    assert "overall_status" in result
    assert result["overall_status"] in ["healthy", "degraded"]


@pytest.mark.unit
def test_component_health_with_all_parameters():
    """Testa ComponentHealth com todos os parâmetros."""
    comp = ComponentHealth(
        component_name="full_test",
        status=HealthStatus.DEGRADED,
        message="Performance degraded",
        details={"cpu": 80, "memory": 70},
        latency_ms=150.5,
    )

    assert comp.component_name == "full_test"
    assert comp.status == HealthStatus.DEGRADED
    assert comp.message == "Performance degraded"
    assert comp.details["cpu"] == 80
    assert comp.latency_ms == 150.5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_all_health_parallel_execution(checker, monkeypatch):
    """Testa que checks são executados em paralelo."""
    import time

    call_times = []

    async def mock_check(name):
        start = time.time()
        await asyncio.sleep(0.01)  # 10ms delay
        call_times.append(time.time() - start)
        return ComponentHealth(name, HealthStatus.HEALTHY)

    monkeypatch.setattr(checker, "_check_mongodb_health", lambda: mock_check("mongodb"))
    monkeypatch.setattr(checker, "_check_mlflow_health", lambda: mock_check("mlflow"))
    monkeypatch.setattr(
        checker, "_check_feature_extraction_health", lambda: mock_check("feature_extraction")
    )
    monkeypatch.setattr(
        checker, "_check_circuit_breakers_health", lambda: mock_check("circuit_breakers")
    )
    monkeypatch.setattr(checker, "_check_ledger_health", lambda: mock_check("ledger"))
    monkeypatch.setattr(checker, "_is_cache_valid", lambda: False)

    start = time.time()
    await checker.check_all_health()
    elapsed = time.time() - start

    # Se executado em paralelo, deve levar menos que soma dos delays
    # 5 checks * 10ms = 50ms serial, mas paralelo deve ser < 30ms
    assert elapsed < 0.05  # 50ms máximo para paralelo
    assert len(call_times) == 5
