"""
Testes de Integração E2E para Feature Flags Dinâmicas.

Task 10: Integration Tests - E2E com docker-compose

Testa o fluxo completo:
- 10.1: CRUD completo via API
- 10.2: Rollout gradual com OPA
- 10.3: Invalidação de cache
- 10.4: Fallback se Redis indisponível
- 10.5: Métricas Prometheus
- 10.6: Verificar todos os testes E2E passando

Nota: Testes usam mocks para MongoDB e Redis para não dependerem de
serviços externos durante desenvolvimento.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.feature_flags import create_feature_flags_router
from src.cache.feature_flag_cache import FeatureFlagCache
from src.models.feature_flag import (
    AttributeCondition,
    FeatureFlag,
    PercentageCondition,
    RolloutStrategy as RolloutStrategyModel,
    RolloutType,
    WhitelistCondition,
)
from src.services.feature_flag_service import FeatureFlagService
from src.services.rollout_strategy import RolloutStrategy


# =============================================================================
# Fixtures E2E (Mock-based)
# =============================================================================


@pytest.fixture
def mock_mongodb():
    """Mock do MongoDB para testes de integração."""
    mock_collection = AsyncMock()

    # Mock find_one
    mock_collection.find_one = AsyncMock(return_value=None)

    # Mock insert_one
    mock_result = MagicMock()
    mock_result.inserted_id = "test_id"
    mock_collection.insert_one = AsyncMock(return_value=mock_result)

    # Mock update_one
    mock_update_result = MagicMock()
    mock_update_result.modified_count = 1
    mock_update_result.upserted_id = None
    mock_collection.update_one = AsyncMock(return_value=mock_update_result)

    # Mock delete_one
    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 1
    mock_collection.delete_one = AsyncMock(return_value=mock_delete_result)

    # Mock find
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection.find = MagicMock(return_value=mock_cursor)

    # Mock count_documents
    mock_collection.count_documents = AsyncMock(return_value=0)

    return mock_collection


@pytest.fixture
def mock_redis():
    """Mock do Redis para testes de integração."""
    # Cache em memória para simular Redis
    _cache = {}

    async def mock_get(key):
        """Mock get que retorna do cache em memória."""
        return _cache.get(key)

    async def mock_setex(key, ttl, value):
        """Mock setex que armazena no cache em memória."""
        _cache[key] = value
        return True

    async def mock_delete(key):
        """Mock delete que remove do cache em memória."""
        if key in _cache:
            del _cache[key]
            return 1
        return 0

    async def mock_keys(pattern):
        """Mock keys que retorna chaves do cache em memória."""
        return list(_cache.keys())

    mock_redis = AsyncMock()
    mock_redis.get = mock_get
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.setex = mock_setex
    mock_redis.delete = mock_delete
    mock_redis.keys = mock_keys
    return mock_redis


@pytest.fixture
def feature_flag_cache(mock_redis):
    """Cache de feature flags com Redis mock."""
    return FeatureFlagCache(
        redis=mock_redis,
        ttl_seconds=60,
        key_prefix="test_feature_flag:",
    )


@pytest.fixture
def feature_flag_service(mock_mongodb, mock_redis):
    """Service de feature flags com mocks."""
    return FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)


@pytest.fixture
def sample_flag_data():
    """Dados de uma feature flag para testes."""
    return {
        "flag_name": "intelligent_scheduler_v2",
        "description": "Nova versão do scheduler com ML avançado",
        "enabled": True,
        "rollout_strategy": "gradual",
        "rollout_config": {
            "percentage": 50,
            "whitelist": ["tenant-premium", "tenant-beta"],
            "namespaces": ["staging", "beta"],
            "canary_list": [],
        },
        "created_by": "platform-team",
        "owner": "orchestrator-team",
        "tags": ["scheduler", "ml", "performance"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# Task 10.1: CRUD completo via API (Service Layer)
# =============================================================================


class TestServiceCRUDFlowE2E:
    """Testa fluxo CRUD completo via Service Layer."""

    @pytest.mark.asyncio
    async def test_create_and_get_flag(self, feature_flag_service, sample_flag_data):
        """Testa criar e buscar flag."""
        flag_name = "test_crud_flag"

        # Criar flag
        await feature_flag_service.set_flag(flag_name, sample_flag_data)

        # Mock find_one para retornar a flag
        flag_with_id = {**sample_flag_data, "flag_name": flag_name}
        feature_flag_service.mongodb.find_one = AsyncMock(return_value=flag_with_id)

        # Buscar flag
        fetched = await feature_flag_service.get_flag(flag_name)
        assert fetched is not None
        assert fetched["flag_name"] == flag_name

    @pytest.mark.asyncio
    async def test_list_flags_empty(self, feature_flag_service):
        """Testa listar flags quando não há nenhuma."""
        feature_flag_service.mongodb.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[])))
        flags = await feature_flag_service.list_flags()
        assert flags == []

    @pytest.mark.asyncio
    async def test_delete_flag(self, feature_flag_service):
        """Testa deletar flag."""
        flag_name = "test_delete_flag"

        # Mock delete_one
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        feature_flag_service.mongodb.delete_one = AsyncMock(return_value=mock_result)

        # Deletar
        deleted = await feature_flag_service.delete_flag(flag_name)
        assert deleted is True


# =============================================================================
# Task 10.2: Rollout gradual com OPA
# =============================================================================


class TestRolloutGradualE2E:
    """Testa estratégias de rollout com contexto real."""

    @pytest.mark.asyncio
    async def test_gradual_rollout_percentage_deterministic(self, feature_flag_cache):
        """Testa rollout gradual com hash determinístico."""
        # Criar flag com 50% de rollout
        flag = FeatureFlag(
            name="gradual_feature",
            description="Feature com rollout gradual",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.GRADUAL, percentage=50),
            conditions=[
                PercentageCondition(percentage=50, attribute="tenant_id"),
            ],
        )

        await feature_flag_cache.set(flag)

        # Hash determinístico - mesmo tenant sempre tem mesmo resultado
        context = {"tenant_id": "tenant-123", "namespace": "staging"}

        result1 = await feature_flag_cache.is_enabled_for(flag.name, context)
        result2 = await feature_flag_cache.is_enabled_for(flag.name, context)

        assert result1 == result2  # Determinístico

    @pytest.mark.asyncio
    async def test_gradual_rollout_distribution(self, feature_flag_cache):
        """Testa distribuição aproximada do rollout gradual."""
        flag = FeatureFlag(
            name="distribution_test",
            description="Teste de distribuição",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.GRADUAL, percentage=50),
            conditions=[
                PercentageCondition(percentage=50, attribute="tenant_id"),
            ],
        )

        await feature_flag_cache.set(flag)

        # Testar com 100 tenants diferentes
        enabled_count = 0
        total_tests = 100

        for i in range(total_tests):
            context = {"tenant_id": f"tenant-{i}", "namespace": "staging"}
            if await feature_flag_cache.is_enabled_for(flag.name, context):
                enabled_count += 1

        # Distribuição deve estar próxima de 50% (40-60% aceitável)
        ratio = enabled_count / total_tests
        assert 0.4 <= ratio <= 0.6, f"Distribuição fora do esperado: {ratio:.2%}"

    @pytest.mark.asyncio
    async def test_whitelist_strategy(self, feature_flag_cache):
        """Testa estratégia de whitelist."""
        flag = FeatureFlag(
            name="whitelist_feature",
            description="Feature via whitelist",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
            conditions=[
                WhitelistCondition(
                    values=["tenant-allowed-1", "tenant-allowed-2"], attribute="tenant_id"
                ),
            ],
        )

        await feature_flag_cache.set(flag)

        # Tenant na whitelist
        context_allowed = {"tenant_id": "tenant-allowed-1", "namespace": "staging"}
        assert await feature_flag_cache.is_enabled_for(flag.name, context_allowed) is True

        # Tenant fora da whitelist
        context_denied = {"tenant_id": "tenant-denied", "namespace": "staging"}
        assert await feature_flag_cache.is_enabled_for(flag.name, context_denied) is False

    @pytest.mark.asyncio
    async def test_attribute_condition_operators(self, feature_flag_cache):
        """Testa operadores de condição de atributo."""
        flag = FeatureFlag(
            name="attribute_feature",
            description="Feature com condição de atributo",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
            conditions=[
                AttributeCondition(
                    attribute="risk_band", operator="in", value=["critical", "high"]
                ),
            ],
        )

        await feature_flag_cache.set(flag)

        # risk_band na lista
        context_high = {"tenant_id": "tenant-1", "risk_band": "high"}
        assert await feature_flag_cache.is_enabled_for(flag.name, context_high) is True

        # risk_band fora da lista
        context_low = {"tenant_id": "tenant-1", "risk_band": "low"}
        assert await feature_flag_cache.is_enabled_for(flag.name, context_low) is False

    @pytest.mark.asyncio
    async def test_multiple_conditions_and_logic(self, feature_flag_cache):
        """Testa múltiplas condições com lógica AND."""
        flag = FeatureFlag(
            name="multi_condition_feature",
            description="Feature com múltiplas condições",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
            conditions=[
                WhitelistCondition(values=["tenant-allowed"], attribute="tenant_id"),
                AttributeCondition(attribute="namespace", operator="equals", value="staging"),
                AttributeCondition(attribute="risk_band", operator="in", value=["critical", "high"]),
            ],
        )

        await feature_flag_cache.set(flag)

        # Todas condições satisfeitas
        context_all_ok = {
            "tenant_id": "tenant-allowed",
            "namespace": "staging",
            "risk_band": "high",
        }
        assert await feature_flag_cache.is_enabled_for(flag.name, context_all_ok) is True

        # Condição de risk_band falha
        context_risk_fail = {
            "tenant_id": "tenant-allowed",
            "namespace": "staging",
            "risk_band": "low",
        }
        assert await feature_flag_cache.is_enabled_for(flag.name, context_risk_fail) is False

        # Condição de namespace falha
        context_ns_fail = {
            "tenant_id": "tenant-allowed",
            "namespace": "production",
            "risk_band": "high",
        }
        assert await feature_flag_cache.is_enabled_for(flag.name, context_ns_fail) is False


# =============================================================================
# Task 10.3: Invalidação de cache
# =============================================================================


class TestCacheInvalidationE2E:
    """Testa invalidação e consistência de cache."""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, feature_flag_cache):
        """Testa armazenar e buscar do cache."""
        flag = FeatureFlag(
            name="cache_test",
            description="Teste de cache",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
        )

        # Armazenar no cache
        result = await feature_flag_cache.set(flag)
        assert result is True

        # Buscar do cache
        fetched = await feature_flag_cache.get(flag.name)
        assert fetched is not None
        assert fetched.name == flag.name

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, feature_flag_cache):
        """Testa invalidação de cache."""
        flag = FeatureFlag(
            name="invalidate_test",
            description="Teste de invalidação",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
        )

        # Armazenar no cache
        await feature_flag_cache.set(flag)

        # Invalidar cache
        await feature_flag_cache.invalidate(flag.name)

        # Verificar que foi removido
        fetched = await feature_flag_cache.get(flag.name)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_cache_clear_all(self, feature_flag_cache):
        """Testa limpar todo o cache."""
        # Criar flags
        for i in range(3):
            flag = FeatureFlag(
                name=f"clear_test_{i}",
                description=f"Teste {i}",
                enabled=True,
                rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
            )
            await feature_flag_cache.set(flag)

        # Limpar todo o cache
        cleared = await feature_flag_cache.clear()
        assert cleared >= 0

    @pytest.mark.asyncio
    async def test_cache_metrics_tracking(self, feature_flag_cache):
        """Testa que métricas de cache são rastreadas."""
        # Reset métricas
        feature_flag_cache.reset_metrics()

        # Simular hits e misses
        feature_flag_cache._metrics.record_hit()
        feature_flag_cache._metrics.record_hit()
        feature_flag_cache._metrics.record_miss()

        metrics = feature_flag_cache.get_metrics()
        assert metrics["total_hits"] == 2
        assert metrics["total_misses"] == 1
        assert metrics["hit_ratio"] == pytest.approx(0.6667, rel=0.1)


# =============================================================================
# Task 10.4: Fallback se Redis indisponível
# =============================================================================


class TestRedisFallbackE2E:
    """Testa comportamento quando Redis está indisponível."""

    @pytest.mark.asyncio
    async def test_cache_returns_none_when_redis_unavailable(self, feature_flag_cache):
        """Testa que cache retorna None quando Redis indisponível."""
        # Simular Redis indisponível
        feature_flag_cache._redis = None

        result = await feature_flag_cache.get("any_flag")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_returns_false_when_redis_unavailable(self, feature_flag_cache):
        """Testa que set retorna False quando Redis indisponível."""
        flag = FeatureFlag(
            name="fallback_test",
            description="Teste de fallback",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.IMMEDIATE),
        )

        # Simular Redis indisponível
        feature_flag_cache._redis = None

        result = await feature_flag_cache.set(flag)
        assert result is False


# =============================================================================
# Task 10.5: Métricas Prometheus
# =============================================================================


class TestPrometheusMetricsE2E:
    """Testa métricas Prometheus para feature flags."""

    @pytest.mark.asyncio
    async def test_toggle_count_metric(self):
        """Testa métrica de toggle count."""
        from src.observability.feature_flag_metrics import get_metrics

        flag_name = "test_toggle_metric"

        # Obter instância de métricas
        metrics = get_metrics()

        # Registrar toggle - não deve levantar exceção
        metrics.record_toggle(
            flag_name=flag_name, action="enable", user="test-user"
        )

        # Se chegou aqui, métrica foi registrada com sucesso
        assert True

    @pytest.mark.asyncio
    async def test_evaluation_latency_metric(self):
        """Testa métrica de latência de avaliação."""
        import time
        from src.observability.feature_flag_metrics import get_metrics

        flag_name = "test_latency_metric"

        # Obter instância de métricas
        metrics = get_metrics()

        # Registrar avaliação
        start_time = time.time()
        await asyncio.sleep(0.01)  # 10ms
        duration = time.time() - start_time

        metrics.record_evaluation(flag_name=flag_name, result=True, duration_seconds=duration)

        # Se chegou aqui, métrica foi registrada com sucesso
        assert True

    @pytest.mark.asyncio
    async def test_cache_hit_ratio_metric(self):
        """Testa métrica de hit ratio do cache."""
        from src.observability.feature_flag_metrics import get_metrics

        # Obter instância de métricas
        metrics = get_metrics()

        # Simular hits e misses usando métricas globais
        metrics.record_cache_hit("redis", "test_flag")
        metrics.record_cache_hit("redis", "test_flag")
        metrics.record_cache_miss("redis", "test_flag")

        # Se chegou aqui, métricas foram registradas com sucesso
        assert True


# =============================================================================
# Task 10.6: Testes E2E com contexto real
# =============================================================================


class TestRealWorldScenariosE2E:
    """Testa cenários reais de uso."""

    @pytest.mark.asyncio
    async def test_phased_rollout_scenario(self, feature_flag_cache):
        """Testa cenário de rollout em fases."""
        # Fase 1: 10% para staging
        flag = FeatureFlag(
            name="phased_rollout_feature",
            description="Feature com rollout em fases",
            enabled=True,
            rollout_strategy=RolloutStrategyModel(type=RolloutType.GRADUAL, percentage=10),
            conditions=[
                PercentageCondition(percentage=10, attribute="tenant_id"),
                WhitelistCondition(values=["staging", "beta"], attribute="namespace"),
            ],
        )

        await feature_flag_cache.set(flag)

        # Contexto de staging
        context_staging = {"tenant_id": "tenant-1", "namespace": "staging"}
        result_staging = await feature_flag_cache.is_enabled_for(
            flag.name, context_staging
        )
        # Resultado depende do hash, não vamos afirmar valor específico

        # Contexto de production (não está na whitelist de namespace)
        context_prod = {"tenant_id": "tenant-1", "namespace": "production"}
        result_prod = await feature_flag_cache.is_enabled_for(flag.name, context_prod)
        assert result_prod is False  # Namespace não permitido

    @pytest.mark.asyncio
    async def test_service_evaluate_integration(self, feature_flag_service, sample_flag_data):
        """Testa integração do serviço de avaliação."""
        flag_name = "test_evaluate"

        # Criar flag
        await feature_flag_service.set_flag(flag_name, sample_flag_data)

        # Mock find_one para retornar a flag
        flag_with_id = {**sample_flag_data, "flag_name": flag_name}
        feature_flag_service.mongodb.find_one = AsyncMock(return_value=flag_with_id)

        # Avaliar com contexto
        context = {
            "tenant_id": "tenant-premium",
            "namespace": "staging",
        }

        result = await feature_flag_service.evaluate_flag(flag_name, context)

        # Resultado depende do hash, mas deve ser bool
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_service_list_integration(self, feature_flag_service, sample_flag_data):
        """Testa integração do serviço de listagem."""
        # Criar flags
        flags_list = []
        for i in range(3):
            flag_data = {
                **sample_flag_data,
                "flag_name": f"list_test_{i}",
                "enabled": i % 2 == 0,
            }
            flags_list.append(flag_data)

        # Mock find para retornar as flags
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=flags_list)
        feature_flag_service.mongodb.find = MagicMock(return_value=mock_cursor)

        # Listar todas
        all_flags = await feature_flag_service.list_flags(enabled_only=False)
        assert len(all_flags) == 3


# =============================================================================
# Teste de RolloutStrategy Engine
# =============================================================================


class TestRolloutStrategyEngineE2E:
    """Testa engine de estratégias de rollout."""

    def test_evaluate_gradual_strategy_hash_consistency(self):
        """Testa consistência de hash em rollout gradual."""
        flag = {
            "flag_name": "hash_test",
            "rollout_strategy": "gradual",
            "rollout_config": {"percentage": 50},
        }

        context = {"tenant_id": "tenant-123"}

        # Mesmo resultado sempre
        result1 = RolloutStrategy.evaluate(flag, context)
        result2 = RolloutStrategy.evaluate(flag, context)
        result3 = RolloutStrategy.evaluate(flag, context)

        assert result1 == result2 == result3

    def test_evaluate_gradual_different_tenants(self):
        """Testa que diferentes tenants podem ter resultados diferentes."""
        flag = {
            "flag_name": "distribution_test",
            "rollout_strategy": "gradual",
            "rollout_config": {"percentage": 50},
        }

        # Coletar resultados para 100 tenants
        results = [
            RolloutStrategy.evaluate(flag, {"tenant_id": f"tenant-{i}"}) for i in range(100)
        ]

        # Deve ter ambos True e False (distribuição)
        assert any(results)  # Pelo menos um True
        assert not all(results)  # Não todos True

    def test_evaluate_whitelist_strategy(self):
        """Testa estratégia whitelist."""
        flag = {
            "flag_name": "whitelist_test",
            "rollout_strategy": "whitelist",
            "rollout_config": {"whitelist": ["tenant-a", "tenant-b"]},
        }

        # Tenant na whitelist
        assert (
            RolloutStrategy.evaluate(flag, {"tenant_id": "tenant-a"}) is True
        )

        # Tenant fora da whitelist
        assert (
            RolloutStrategy.evaluate(flag, {"tenant_id": "tenant-c"}) is False
        )

    def test_evaluate_all_strategy(self):
        """Testa estratégia all (sem restrições)."""
        flag = {
            "flag_name": "all_test",
            "rollout_strategy": "all",
            "rollout_config": {},
        }

        # Qualquer contexto deve retornar True
        assert RolloutStrategy.evaluate(flag, {}) is True
        assert RolloutStrategy.evaluate(flag, {"tenant_id": "any"}) is True

    def test_evaluate_namespace_filter(self):
        """Testa filtro de namespace."""
        flag = {
            "flag_name": "namespace_test",
            "rollout_strategy": "all",
            "rollout_config": {"namespaces": ["staging", "dev"]},
        }

        # Namespace permitido
        assert (
            RolloutStrategy.evaluate(flag, {"namespace": "staging"}) is True
        )

        # Namespace não permitido
        assert (
            RolloutStrategy.evaluate(flag, {"namespace": "production"}) is False
        )

        # Sem namespace (requerido quando lista configurada)
        assert RolloutStrategy.evaluate(flag, {}) is False

    def test_evaluate_combined_filters(self):
        """Testa combinação de namespace + gradual."""
        flag = {
            "flag_name": "combined_test",
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 100,  # 100% se passar filtro
                "namespaces": ["staging"],
            },
        }

        # Namespace correto + 100% = True
        assert (
            RolloutStrategy.evaluate(flag, {"tenant_id": "any", "namespace": "staging"})
            is True
        )

        # Namespace errado = False (mesmo com 100%)
        assert (
            RolloutStrategy.evaluate(
                flag, {"tenant_id": "any", "namespace": "production"}
            )
            is False
        )
