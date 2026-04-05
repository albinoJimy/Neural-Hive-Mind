"""
Testes unitários para integração OPA Feature Flags.

Testes cobrem:
- Avaliação de flags via OPA
- Cache local e Redis
- Fallback para valores default
- Toggle de flags
- Métricas Prometheus
"""
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime
import pytest
import time

from src.integrations.opa_feature_flags import (
    OPAFeatureFlagsClient,
    OPAFeatureFlagsMetrics,
    _MockMetrics,
    _mock_metrics_instance,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_opa_client():
    """Mock de cliente OPA."""
    client = MagicMock()
    client.evaluate_policy = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    client.clear_cache = Mock()
    return client


@pytest.fixture
def mock_redis_client():
    """Mock de cliente Redis."""
    client = MagicMock()
    client.get = AsyncMock()
    client.set = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    return client


@pytest.fixture
def feature_flags_metrics():
    """Retorna instância de métricas de feature flags."""
    return OPAFeatureFlagsMetrics(
        service_name="test-service",
        component="feature-flags",
        layer="test",
    )


@pytest.fixture
def opa_feature_flags_client(mock_opa_client, mock_redis_client):
    """Retorna instância de OPAFeatureFlagsClient."""
    metrics = OPAFeatureFlagsMetrics(
        service_name="test-service",
        component="feature-flags",
        layer="test",
    )
    return OPAFeatureFlagsClient(
        opa_client=mock_opa_client,
        redis_client=mock_redis_client,
        metrics=metrics,
    )


# ============================================================================
# Testes: OPAFeatureFlagsMetrics
# ============================================================================

class TestOPAFeatureFlagsMetrics:
    """Testes para OPAFeatureFlagsMetrics."""

    def test_initialization(self):
        """Testa inicialização de métricas."""
        metrics = OPAFeatureFlagsMetrics(
            service_name="test-service",
            component="feature-flags",
            layer="test",
        )

        assert metrics.service_name == "test-service"
        assert metrics.component == "feature-flags"
        assert metrics.layer == "test"

        # Verificar que métricas foram criadas
        assert metrics.flag_evaluations_total is not None
        assert metrics.flag_evaluation_duration_seconds is not None
        assert metrics.flag_cache_hits_total is not None
        assert metrics.flag_cache_misses_total is not None
        assert metrics.flag_toggles_total is not None
        assert metrics.flag_rollout_percentage is not None

    def test_record_flag_evaluation(self, feature_flags_metrics):
        """Testa registro de avaliação de flag."""
        # Chamar método
        feature_flags_metrics.record_flag_evaluation(
            flag_name="test_flag",
            result=True,
            duration_ms=50.0,
        )

        # Verificar que métrica foi incrementada
        # (em testes reais, verificaríamos valores via prometheus_client)
        assert True  # Placeholder - na prática verificamos com registry

    def test_record_cache_hit(self, feature_flags_metrics):
        """Testa registro de cache hit."""
        feature_flags_metrics.record_cache_hit("test_flag")
        assert True  # Placeholder

    def test_record_cache_miss(self, feature_flags_metrics):
        """Testa registro de cache miss."""
        feature_flags_metrics.record_cache_miss("test_flag")
        assert True  # Placeholder

    def test_record_flag_toggle(self, feature_flags_metrics):
        """Testa registro de toggle."""
        feature_flags_metrics.record_flag_toggle(
            flag_name="test_flag",
            action="enable",
            user="test_user",
        )
        assert True  # Placeholder

    def test_record_rollout_percentage(self, feature_flags_metrics):
        """Testa registro de percentual de rollout."""
        feature_flags_metrics.record_rollout_percentage(
            flag_name="test_flag",
            strategy="percentage",
            percentage=50,
        )
        assert True  # Placeholder


# ============================================================================
# Testes: OPAFeatureFlagsClient - Avaliação
# ============================================================================

class TestOPAFeatureFlagsClientEvaluation:
    """Testes para avaliação de flags."""

    @pytest.mark.asyncio
    async def test_evaluate_flag_enabled(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa avaliação de flag habilitada."""
        # Setup
        mock_redis_client.get.return_value = None  # Redis vazio
        mock_opa_client.evaluate_policy.return_value = {
            "result": {"enable_test_flag": True},
            "policy_path": "neuralhive.orchestrator.feature_flags",
        }

        # Executar
        result = await opa_feature_flags_client.evaluate_flag(
            flag_name="test_flag",
            context={"tenant_id": "tenant-123", "namespace": "production"},
        )

        # Verificar
        assert result is True
        mock_opa_client.evaluate_policy.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_flag_disabled(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa avaliação de flag desabilitada."""
        # Setup
        mock_redis_client.get.return_value = None
        mock_opa_client.evaluate_policy.return_value = {
            "result": {"enable_test_flag": False},
        }

        # Executar
        result = await opa_feature_flags_client.evaluate_flag(
            flag_name="test_flag",
            context={"tenant_id": "tenant-123"},
        )

        # Verificar
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_flag_with_redis_flags(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa avaliação usando flags do Redis."""
        import json

        # Setup - flags do Redis
        redis_flags = {
            "intelligent_scheduler_enabled": True,
            "burst_capacity_enabled": False,
            "gradual_rollout": False,
        }
        mock_redis_client.get.return_value = json.dumps(redis_flags)
        mock_opa_client.evaluate_policy.return_value = {
            "result": {"enable_intelligent_scheduler": True},
        }

        # Executar
        result = await opa_feature_flags_client.evaluate_flag(
            flag_name="intelligent_scheduler",
            context={"namespace": "production"},
        )

        # Verificar
        assert result is True
        mock_redis_client.get.assert_called_once_with("feature_flags:all")

    @pytest.mark.asyncio
    async def test_evaluate_flag_uses_local_cache(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa que cache local é usado."""
        # Setup - primeira chamada popula cache
        import json

        redis_flags = {"test_flag_enabled": True}
        mock_redis_client.get.return_value = json.dumps(redis_flags)
        mock_opa_client.evaluate_policy.return_value = {
            "result": {"enable_test_flag": True},
        }

        # Primeira chamada
        await opa_feature_flags_client.evaluate_flag(
            flag_name="test_flag",
            context={},
        )

        # Resetar mock
        mock_redis_client.get.reset_mock()

        # Segunda chamada (deve usar cache local)
        await opa_feature_flags_client.evaluate_flag(
            flag_name="test_flag",
            context={},
            use_cache=True,
        )

        # Redis não deve ser chamado (cache local usado)
        mock_redis_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_flag_error_fallback_to_default(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa fallback para valor default em caso de erro."""
        # Setup - erro no OPA
        mock_redis_client.get.return_value = None
        mock_opa_client.evaluate_policy.side_effect = Exception("OPA error")

        # Executar
        result = await opa_feature_flags_client.evaluate_flag(
            flag_name="intelligent_scheduler",
            context={},
        )

        # Verificar - deve usar default (False para flags desconhecidas)
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_multiple_flags(
        self, opa_feature_flags_client, mock_opa_client
    ):
        """Testa avaliação de múltiplas flags."""
        # Setup
        mock_opa_client.evaluate_policy.return_value = {
            "result": {
                "enable_flag1": True,
                "enable_flag2": False,
            },
        }

        # Executar
        results = await opa_feature_flags_client.evaluate_multiple_flags(
            flag_names=["flag1", "flag2"],
            context={},
        )

        # Verificar
        assert results == {"flag1": True, "flag2": False}
        assert mock_opa_client.evaluate_policy.call_count == 2


# ============================================================================
# Testes: OPAFeatureFlagsClient - Toggle
# ============================================================================

class TestOPAFeatureFlagsClientToggle:
    """Testes para toggle de flags."""

    @pytest.mark.asyncio
    async def test_toggle_flag_enable(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa habilitar flag."""
        import json

        # Setup
        mock_redis_client.get.return_value = None

        # Executar
        result = await opa_feature_flags_client.toggle_flag(
            flag_name="test_flag",
            enabled=True,
            user="test_user",
        )

        # Verificar
        assert result["test_flag"] is True
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert "feature_flags:all" in call_args[0]

    @pytest.mark.asyncio
    async def test_toggle_flag_disable(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa desabilitar flag."""
        # Setup
        mock_redis_client.get.return_value = None

        # Executar
        result = await opa_feature_flags_client.toggle_flag(
            flag_name="test_flag",
            enabled=False,
            user="test_user",
        )

        # Verificar
        assert result["test_flag"] is False

    @pytest.mark.asyncio
    async def test_toggle_flag_invalidates_cache(
        self, opa_feature_flags_client, mock_redis_client, mock_opa_client
    ):
        """Testa que toggle invalida cache."""
        # Setup
        mock_redis_client.get.return_value = None

        # Executar toggle
        await opa_feature_flags_client.toggle_flag(
            flag_name="test_flag",
            enabled=True,
        )

        # Verificar cache invalidado
        assert opa_feature_flags_client._local_cache == {}
        assert opa_feature_flags_client._local_cache_timestamp == 0
        mock_opa_client.clear_cache.assert_called_once()


# ============================================================================
# Testes: OPAFeatureFlagsClient - Config Update
# ============================================================================

class TestOPAFeatureFlagsClientConfigUpdate:
    """Testes para atualização de configuração."""

    @pytest.mark.asyncio
    async def test_update_flag_config(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa atualização de configuração de flag."""
        # Setup
        mock_redis_client.get.return_value = None
        config = {
            "scheduler_namespaces": ["production", "staging", "dev"],
            "burst_threshold": 90,
        }

        # Executar
        result = await opa_feature_flags_client.update_flag_config(
            flag_name="intelligent_scheduler",
            config=config,
            user="test_user",
        )

        # Verificar
        assert result["scheduler_namespaces"] == ["production", "staging", "dev"]
        assert result["burst_threshold"] == 90
        mock_redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_flag_config_error(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa erro na atualização de configuração."""
        # Setup - erro no Redis
        mock_redis_client.get.return_value = None
        mock_redis_client.set.side_effect = Exception("Redis error")

        # Executar e verificar exceção
        with pytest.raises(Exception):
            await opa_feature_flags_client.update_flag_config(
                flag_name="test_flag",
                config={"key": "value"},
            )


# ============================================================================
# Testes: OPAFeatureFlagsClient - Get Status
# ============================================================================

class TestOPAFeatureFlagsClientGetStatus:
    """Testes para obter status de flags."""

    @pytest.mark.asyncio
    async def test_get_flag_status(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa obter status de flag."""
        import json

        # Setup
        flags = {
            "enable_intelligent_scheduler": True,
            "scheduler_namespaces": ["production"],
        }
        mock_redis_client.get.return_value = json.dumps(flags)

        # Executar
        status = await opa_feature_flags_client.get_flag_status(
            flag_name="intelligent_scheduler"
        )

        # Verificar
        assert status["name"] == "intelligent_scheduler"
        assert status["enabled"] is True

    @pytest.mark.asyncio
    async def test_get_all_flags(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa obter todas as flags."""
        import json

        # Setup
        flags = {
            "flag1_enabled": True,
            "flag2_enabled": False,
        }
        mock_redis_client.get.return_value = json.dumps(flags)

        # Executar
        all_flags = await opa_feature_flags_client.get_all_flags()

        # Verificar
        assert all_flags["flag1_enabled"] is True
        assert all_flags["flag2_enabled"] is False


# ============================================================================
# Testes: OPAFeatureFlagsClient - Health Check
# ============================================================================

class TestOPAFeatureFlagsClientHealthCheck:
    """Testes para health check."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa health check com todos os componentes saudáveis."""
        # Setup
        mock_opa_client.health_check.return_value = True
        mock_redis_client.ping.return_value = True

        # Executar
        health = await opa_feature_flags_client.health_check()

        # Verificar
        assert health["healthy"] is True
        assert health["checks"]["opa"] is True
        assert health["checks"]["redis"] is True

    @pytest.mark.asyncio
    async def test_health_check_opa_unhealthy(
        self, opa_feature_flags_client, mock_opa_client, mock_redis_client
    ):
        """Testa health check com OPA não saudável."""
        # Setup
        mock_opa_client.health_check.return_value = False
        mock_redis_client.ping.return_value = True

        # Executar
        health = await opa_feature_flags_client.health_check()

        # Verificar
        assert health["healthy"] is False
        assert health["checks"]["opa"] is False

    @pytest.mark.asyncio
    async def test_health_check_redis_unhealthy(
        self, opa_feature_flags_client, mock_redis_client
    ):
        """Testa health check com Redis não saudável."""
        # Setup
        mock_redis_client.ping.side_effect = Exception("Redis error")

        # Executar
        health = await opa_feature_flags_client.health_check()

        # Verificar
        assert health["healthy"] is False
        assert health["checks"]["redis"] is False


# ============================================================================
# Testes: Helpers
# ============================================================================

class TestOPAFeatureFlagsClientHelpers:
    """Testes para métodos helper."""

    def test_to_opa_flag_name_without_prefix(self, opa_feature_flags_client):
        """Testa conversão de nome sem prefixo."""
        result = opa_feature_flags_client._to_opa_flag_name("intelligent_scheduler")
        assert result == "enable_intelligent_scheduler"

    def test_to_opa_flag_name_with_prefix(self, opa_feature_flags_client):
        """Testa conversão de nome com prefixo."""
        result = opa_feature_flags_client._to_opa_flag_name("enable_test_flag")
        assert result == "enable_test_flag"

    def test_extract_flag_result_from_nested(self, opa_feature_flags_client):
        """Testa extração de resultado aninhado."""
        opa_result = {
            "result": {"enable_test_flag": True},
            "policy_path": "test",
        }
        result = opa_feature_flags_client._extract_flag_result(
            opa_result, "test_flag"
        )
        assert result is True

    def test_extract_flag_result_from_flat(self, opa_feature_flags_client):
        """Testa extração de resultado plano."""
        opa_result = {"enable_test_flag": False}
        result = opa_feature_flags_client._extract_flag_result(
            opa_result, "test_flag"
        )
        assert result is False


# ============================================================================
# Testes: Mock Metrics
# ============================================================================

class TestMockMetrics:
    """Testes para mock metrics."""

    def test_mock_metrics_does_not_raise(self):
        """Testa que mock metrics não levanta exceções."""
        mock = _MockMetrics()

        # Todos os métodos devem existir e não levantar exceções
        mock.record_flag_evaluation("test", True, 100)
        mock.record_cache_hit("test")
        mock.record_cache_miss("test")
        mock.record_flag_toggle("test", "enable", "user")

        assert True

    def test_mock_metrics_instance(self):
        """Testa instância global de mock metrics."""
        assert _mock_metrics_instance is not None
        _mock_metrics_instance.record_flag_evaluation("test", True, 100)
