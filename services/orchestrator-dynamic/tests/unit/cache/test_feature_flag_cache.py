"""
Testes unitários para FeatureFlagCache.

Cobertura:
- get: Buscar flag do cache
- set: Armazenar flag no cache
- delete: Remover flag do cache
- invalidate: Invalidar cache de flag específica
- clear: Limpar todo o cache
- get_or_load: Buscar do cache ou carregar do repositório
- TTL configurável (default 60s)
- Tratamento de erros de Redis
"""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.models.feature_flag import FeatureFlag
from src.cache.feature_flag_cache import (
    CacheError,
    CacheMetrics,
    FeatureFlagCache,
)


@pytest.fixture
def mock_redis():
    """Fixture para cliente Redis mockado."""
    redis = MagicMock()
    redis.get = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.keys = AsyncMock()
    redis.ping = AsyncMock()
    return redis


@pytest.fixture
def sample_flag():
    """Fixture para flag de exemplo."""
    return FeatureFlag(
        name="test_feature",
        description="Test feature",
        enabled=True,
    )


class TestFeatureFlagCacheInit:
    """Testes para inicialização do cache."""

    def test_init_with_defaults(self):
        """Testa inicialização com valores default."""
        cache = FeatureFlagCache(redis=None, ttl_seconds=60)

        assert cache.ttl_seconds == 60
        assert cache.key_prefix == "feature_flag:"

    def test_init_with_custom_values(self):
        """Testa inicialização com valores customizados."""
        cache = FeatureFlagCache(redis=None, ttl_seconds=120, key_prefix="custom:")

        assert cache.ttl_seconds == 120
        assert cache.key_prefix == "custom:"


class TestFeatureFlagCacheGet:
    """Testes para método get."""

    @pytest.mark.asyncio
    async def test_get_hit(self, mock_redis, sample_flag):
        """Testa cache hit."""
        import json

        cache = FeatureFlagCache(redis=mock_redis)
        flag_data = sample_flag.to_dict()
        mock_redis.get.return_value = json.dumps(flag_data)

        result = await cache.get("test_feature")

        assert result is not None
        assert result.name == "test_feature"

    @pytest.mark.asyncio
    async def test_get_miss(self, mock_redis):
        """Testa cache miss."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = None

        result = await cache.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_invalid_json(self, mock_redis):
        """Testa get com JSON inválido."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = "invalid json"

        result = await cache.get("bad_json")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_redis_error(self, mock_redis):
        """Testa get com erro de Redis."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.side_effect = Exception("Connection error")

        result = await cache.get("test")

        # Deve retornar None em caso de erro (fail-open)
        assert result is None


class TestFeatureFlagCacheSet:
    """Testes para método set."""

    @pytest.mark.asyncio
    async def test_set_success(self, mock_redis, sample_flag):
        """Testa armazenar flag no cache."""
        cache = FeatureFlagCache(redis=mock_redis, ttl_seconds=60)

        await cache.set(sample_flag)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert "test_feature" in str(call_args)

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self, mock_redis, sample_flag):
        """Testa set com TTL customizado."""
        cache = FeatureFlagCache(redis=mock_redis, ttl_seconds=120)

        await cache.set(sample_flag)

        call_args = mock_redis.setex.call_args
        # Verificar que TTL de 120 segundos foi usado
        assert call_args[0][1] == 120

    @pytest.mark.asyncio
    async def test_set_redis_error(self, mock_redis, sample_flag):
        """Testa set com erro de Redis."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.setex.side_effect = Exception("Connection error")

        # Não deve lançar exceção (fail-open)
        await cache.set(sample_flag)


class TestFeatureFlagCacheDelete:
    """Testes para método delete."""

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_redis):
        """Testa deletar flag do cache."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.delete.return_value = 1

        result = await cache.delete("test_feature")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_redis):
        """Testa deletar flag inexistente."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.delete.return_value = 0

        result = await cache.delete("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_redis_error(self, mock_redis):
        """Testa delete com erro de Redis."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.delete.side_effect = Exception("Connection error")

        result = await cache.delete("test")

        # Deve retornar False em caso de erro
        assert result is False


class TestFeatureFlagCacheInvalidate:
    """Testes para método invalidate."""

    @pytest.mark.asyncio
    async def test_invalidate_calls_delete(self, mock_redis):
        """Testa que invalidate chama delete."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.delete.return_value = 1

        await cache.invalidate("test_feature")

        mock_redis.delete.assert_called_once()


class TestFeatureFlagCacheClear:
    """Testes para método clear."""

    @pytest.mark.asyncio
    async def test_clear_all(self, mock_redis):
        """Testa limpar todo o cache."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.keys.return_value = ["key1", "key2", "key3"]
        mock_redis.delete.return_value = 3  # Número de chaves deletadas

        result = await cache.clear()

        assert result == 3

    @pytest.mark.asyncio
    async def test_clear_empty_cache(self, mock_redis):
        """Testa limpar cache vazio."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.keys.return_value = []

        result = await cache.clear()

        assert result == 0

    @pytest.mark.asyncio
    async def test_clear_with_pattern(self, mock_redis):
        """Testa limpar com padrão específico."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.keys.return_value = ["feature_flag:test", "feature_flag:other"]

        result = await cache.clear()

        mock_redis.keys.assert_called_with("feature_flag:*")


class TestFeatureFlagCacheGetOrLoad:
    """Testes para método get_or_load."""

    @pytest.mark.asyncio
    async def test_get_or_load_cache_hit(self, mock_redis, sample_flag):
        """Testa get_or_load com cache hit."""
        import json

        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = json.dumps(sample_flag.to_dict())

        loader = AsyncMock()

        result = await cache.get_or_load("test_feature", loader)

        assert result is not None
        assert result.name == "test_feature"
        loader.assert_not_awaited()  # Loader não foi chamado

    @pytest.mark.asyncio
    async def test_get_or_load_cache_miss(self, mock_redis, sample_flag):
        """Testa get_or_load com cache miss."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()

        loader = AsyncMock(return_value=sample_flag)

        result = await cache.get_or_load("test_feature", loader)

        assert result is not None
        assert result.name == "test_feature"
        loader.assert_awaited_once()  # Loader foi chamado

    @pytest.mark.asyncio
    async def test_get_or_load_loader_returns_none(self, mock_redis):
        """Testa get_or_load quando loader retorna None."""
        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = None

        loader = AsyncMock(return_value=None)

        result = await cache.get_or_load("nonexistent", loader)

        assert result is None
        # Não deve tentar cachear None
        mock_redis.setex.assert_not_called()


class TestFeatureFlagCacheMultiple:
    """Testes para operações em lote."""

    @pytest.mark.asyncio
    async def test_get_multiple(self, mock_redis, sample_flag):
        """Testa buscar múltiplas flags."""
        import json

        cache = FeatureFlagCache(redis=mock_redis)
        flag_data = sample_flag.to_dict()

        # Configurar mock para retornar dados para cada chave
        async def mock_get_side_effect(key):
            if "test" in key:
                return json.dumps(flag_data)
            return None

        mock_redis.get.side_effect = mock_get_side_effect

        results = await cache.get_multiple(["test_feature", "other_feature"])

        assert len(results) == 2
        assert results[0].name == "test_feature"
        assert results[1] is None

    @pytest.mark.asyncio
    async def test_set_multiple(self, mock_redis):
        """Testa armazenar múltiplas flags."""
        cache = FeatureFlagCache(redis=mock_redis)

        flags = [
            FeatureFlag(name="flag1", description="1", enabled=True),
            FeatureFlag(name="flag2", description="2", enabled=False),
        ]

        await cache.set_multiple(flags)

        assert mock_redis.setex.call_count == 2


class TestFeatureFlagCacheIsEnabledFor:
    """Testes para método is_enabled_for (avaliação cached)."""

    @pytest.mark.asyncio
    async def test_is_enabled_for_cached_flag(self, mock_redis):
        """Testa avaliação de flag cached."""
        import json

        flag = FeatureFlag(
            name="test_feature",
            description="Test",
            enabled=True,
        )

        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = json.dumps(flag.to_dict())

        result = await cache.is_enabled_for("test_feature", {"tenant_id": "tenant-123"})

        assert result is True

    @pytest.mark.asyncio
    async def test_is_enabled_for_with_conditions(self, mock_redis):
        """Testa avaliação com condições."""
        import json

        from src.models.feature_flag import (
            AttributeCondition,
            ConditionType,
            OperatorType,
        )

        flag = FeatureFlag(
            name="conditional_feature",
            description="Conditional",
            enabled=True,
            conditions=[
                AttributeCondition(
                    type=ConditionType.ATTRIBUTE,
                    attribute="environment",
                    operator=OperatorType.EQUALS,
                    value="staging",
                ),
            ],
        )

        cache = FeatureFlagCache(redis=mock_redis)
        mock_redis.get.return_value = json.dumps(flag.to_dict())

        result = await cache.is_enabled_for(
            "conditional_feature", {"environment": "staging"}
        )

        assert result is True


class TestCacheMetrics:
    """Testes para CacheMetrics."""

    def test_metrics_initialization(self):
        """Testa inicialização de métricas."""
        metrics = CacheMetrics()

        assert metrics.total_hits == 0
        assert metrics.total_misses == 0
        assert metrics.hit_ratio == 0.0

    def test_record_hit(self):
        """Testa registro de hit."""
        metrics = CacheMetrics()

        metrics.record_hit()

        assert metrics.total_hits == 1
        assert metrics.total_misses == 0
        assert metrics.hit_ratio == 1.0

    def test_record_miss(self):
        """Testa registro de miss."""
        metrics = CacheMetrics()

        metrics.record_miss()

        assert metrics.total_hits == 0
        assert metrics.total_misses == 1
        assert metrics.hit_ratio == 0.0

    def test_hit_ratio_calculation(self):
        """Testa cálculo de hit ratio."""
        metrics = CacheMetrics()

        for _ in range(7):
            metrics.record_hit()
        for _ in range(3):
            metrics.record_miss()

        assert metrics.total_hits == 7
        assert metrics.total_misses == 3
        assert metrics.hit_ratio == 0.7

    def test_reset(self):
        """Testa reset de métricas."""
        metrics = CacheMetrics()

        metrics.record_hit()
        metrics.record_miss()
        metrics.reset()

        assert metrics.total_hits == 0
        assert metrics.total_misses == 0

    def test_get_stats(self):
        """Testa obter estatísticas."""
        metrics = CacheMetrics()

        metrics.record_hit()
        metrics.record_hit()
        metrics.record_miss()

        stats = metrics.get_stats()

        assert stats["total_hits"] == 2
        assert stats["total_misses"] == 1
        # hit_ratio é arredondado para 4 casas decimais
        assert stats["hit_ratio"] == 0.6667
        assert stats["total_operations"] == 3


class TestFeatureFlagCacheWithMetrics:
    """Testes para cache com métricas."""

    @pytest.mark.asyncio
    async def test_get_increments_metrics(self, mock_redis, sample_flag):
        """Testa que get atualiza métricas."""
        import json

        cache = FeatureFlagCache(redis=mock_redis)

        # Cache hit
        mock_redis.get.return_value = json.dumps(sample_flag.to_dict())
        await cache.get("test_feature")

        metrics = cache.get_metrics()
        assert metrics["total_hits"] == 1

        # Cache miss
        mock_redis.get.return_value = None
        await cache.get("nonexistent")

        metrics = cache.get_metrics()
        assert metrics["total_misses"] == 1
