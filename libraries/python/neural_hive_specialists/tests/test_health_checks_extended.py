"""
Testes para SpecialistHealthChecker.

Cobertura para observability/health_checks.py
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import Dict, Any
from datetime import datetime
import asyncio


class TestComponentHealth:
    """Testes para ComponentHealth."""

    def test_init_with_defaults(self):
        """Testa inicialização com valores padrão."""
        from neural_hive_specialists.observability.health_checks import (
            ComponentHealth,
            HealthStatus,
        )

        comp = ComponentHealth(
            component_name="mongodb",
            status=HealthStatus.HEALTHY,
        )

        assert comp.component_name == "mongodb"
        assert comp.status == HealthStatus.HEALTHY
        assert comp.message == ""
        assert comp.details == {}
        assert comp.latency_ms is None
        assert isinstance(comp.checked_at, datetime)

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        from neural_hive_specialists.observability.health_checks import (
            ComponentHealth,
            HealthStatus,
        )

        comp = ComponentHealth(
            component_name="mlflow",
            status=HealthStatus.DEGRADED,
            message="Slow response",
            details={"latency": 500},
            latency_ms=250.5,
        )

        result = comp.to_dict()

        assert result["component"] == "mlflow"
        assert result["status"] == "degraded"
        assert result["message"] == "Slow response"
        assert result["details"] == {"latency": 500}
        assert result["latency_ms"] == 250.5


class TestSpecialistHealthChecker:
    """Testes para SpecialistHealthChecker."""

    @pytest.fixture
    def config(self):
        """Configuração de teste."""
        return {
            "mongodb_uri": "mongodb://localhost:27017",
            "mongodb_database": "test_db",
            "mlflow_tracking_uri": "http://mlflow:5000",
            "mlflow_model_name": "test_model",
            "enable_feature_extraction": True,
            "enable_circuit_breaker": True,
        }

    def test_init(self, config):
        """Testa inicialização."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
        )

        checker = SpecialistHealthChecker(config, "technical")

        assert checker.config is config
        assert checker.specialist_type == "technical"
        assert checker._health_cache is None

    @pytest.mark.asyncio
    async def test_check_all_health(self, config):
        """Testa verificação de saúde completa."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
        )

        checker = SpecialistHealthChecker(config, "technical")

        # Mock das chamadas externas
        with patch("neural_hive_specialists.observability.health_checks.MongoClient"):
            with patch("neural_hive_specialists.observability.health_checks.mlflow"):
                result = await checker.check_all_health()

        assert result["specialist_type"] == "technical"
        assert "overall_status" in result
        assert "components" in result
        assert "checked_at" in result

    def test_is_cache_valid_initially(self):
        """Testa que cache não é válido inicialmente."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
        )

        checker = SpecialistHealthChecker({}, "technical")

        assert checker._is_cache_valid() is False

    def test_determine_overall_status_all_healthy(self):
        """Testa status geral quando todos estão saudáveis."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
            ComponentHealth,
            HealthStatus,
        )

        checker = SpecialistHealthChecker({}, "technical")

        components = [
            ComponentHealth("mongodb", HealthStatus.HEALTHY),
            ComponentHealth("mlflow", HealthStatus.HEALTHY),
        ]

        status = checker._determine_overall_status(components)

        assert status == HealthStatus.HEALTHY

    def test_determine_overall_status_with_degraded(self):
        """Testa status geral com componente degradado."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
            ComponentHealth,
            HealthStatus,
        )

        checker = SpecialistHealthChecker({}, "technical")

        components = [
            ComponentHealth("mongodb", HealthStatus.HEALTHY),
            ComponentHealth("mlflow", HealthStatus.DEGRADED),
        ]

        status = checker._determine_overall_status(components)

        assert status == HealthStatus.DEGRADED

    def test_determine_overall_status_critical_unhealthy(self):
        """Testa status geral com componente crítico não saudável."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
            ComponentHealth,
            HealthStatus,
        )

        checker = SpecialistHealthChecker({}, "technical")

        components = [
            ComponentHealth("mongodb", HealthStatus.UNHEALTHY),
            ComponentHealth("mlflow", HealthStatus.HEALTHY),
        ]

        status = checker._determine_overall_status(components)

        # MongoDB é crítico, então deve ser UNHEALTHY
        assert status == HealthStatus.UNHEALTHY

    def test_generate_summary(self):
        """Testa geração de resumo."""
        from neural_hive_specialists.observability.health_checks import (
            SpecialistHealthChecker,
            ComponentHealth,
            HealthStatus,
        )

        checker = SpecialistHealthChecker({}, "technical")

        components = [
            ComponentHealth("c1", HealthStatus.HEALTHY, latency_ms=100),
            ComponentHealth("c2", HealthStatus.HEALTHY, latency_ms=200),
            ComponentHealth("c3", HealthStatus.DEGRADED, latency_ms=300),
            ComponentHealth("c4", HealthStatus.UNHEALTHY, latency_ms=400),
        ]

        summary = checker._generate_summary(components)

        assert summary["total_components"] == 4
        assert summary["healthy_components"] == 2
        assert summary["degraded_components"] == 1
        assert summary["unhealthy_components"] == 1
        assert summary["avg_latency_ms"] == 250.0


class TestHealthStatus:
    """Testes para HealthStatus enum."""

    def test_values(self):
        """Testa valores do enum."""
        from neural_hive_specialists.observability.health_checks import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"
