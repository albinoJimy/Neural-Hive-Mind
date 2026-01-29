import asyncio
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
    monkeypatch.setattr(
        checker, "_check_mongodb_health", AsyncMock(return_value=healthy)
    )
    monkeypatch.setattr(
        checker, "_check_mlflow_health", AsyncMock(return_value=healthy)
    )
    monkeypatch.setattr(
        checker, "_check_feature_extraction_health", AsyncMock(return_value=degraded)
    )
    monkeypatch.setattr(
        checker, "_check_circuit_breakers_health", AsyncMock(return_value=healthy)
    )
    monkeypatch.setattr(
        checker, "_check_ledger_health", AsyncMock(return_value=healthy)
    )

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
