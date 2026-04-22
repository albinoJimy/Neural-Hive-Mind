"""
Testes para Redis Cache Service

Testa operações CRUD, hit/miss, expiração e statistics.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.config.settings import Settings
from src.services.cache_service import RedisCacheService


@pytest.fixture()
def mock_settings():
    """Mock das configurações"""
    settings = MagicMock(spec=Settings)
    settings.redis_url = "redis://localhost:6379/0"
    settings.redis_max_connections = 50
    settings.redis_socket_timeout = 5
    settings.redis_socket_connect_timeout = 5
    settings.redis_cache_ttl_seconds = 3600
    return settings


@pytest.fixture()
def cache_service(mock_settings):
    """Instância do serviço de cache"""
    return RedisCacheService(mock_settings)


@pytest.fixture()
def sample_features():
    """Features de exemplo para cache"""
    return {
        "plan_id": "test-plan-123",
        "metadata": {"num_tasks": 5, "priority_score": 0.7},
        "computation_status": "completed",
    }


class TestRedisCacheServiceInit:
    """Testes para inicialização do RedisCacheService"""

    def test_init_with_settings(self, cache_service, mock_settings):
        """Testa inicialização com settings"""
        assert cache_service.settings == mock_settings
        assert cache_service._redis is None
        assert cache_service._is_connected is False

    def test_is_available_when_not_connected(self, cache_service):
        """Testa is_available quando não conectado"""
        assert cache_service.is_available() is False


class TestInitialize:
    """Testes para inicialização da conexão Redis"""

    @pytest.mark.asyncio()
    async def test_initialize_success(self, cache_service):
        """Testa inicialização bem-sucedida"""
        with patch("src.services.cache_service.HAS_AIOREDIS", True):
            # Mock redis
            mock_redis = MagicMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_pool = MagicMock()

            with patch(
                "src.services.cache_service.aioredis.ConnectionPool", return_value=mock_pool
            ):
                with patch("src.services.cache_service.aioredis.Redis", return_value=mock_redis):
                    await cache_service.initialize()

                    assert cache_service._is_connected is True
                    assert cache_service._redis == mock_redis

    @pytest.mark.asyncio()
    async def test_initialize_without_aioredis(self, cache_service):
        """Testa inicialização sem aioredis instalado"""
        with patch("src.services.cache_service.HAS_AIOREDIS", False):
            await cache_service.initialize()

            assert cache_service._is_connected is False


class TestGet:
    """Testes para get (cache hit/miss)"""

    @pytest.mark.asyncio()
    async def test_get_cache_hit(self, cache_service, sample_features):
        """Testa cache hit"""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value='{"key": "value"}')
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        with patch("src.services.cache_service.json.loads", return_value=sample_features):
            result = await cache_service.get("test-plan-123")

            assert result == sample_features
            mock_redis.get.assert_called_once()

    @pytest.mark.asyncio()
    async def test_get_cache_miss(self, cache_service):
        """Testa cache miss"""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio()
    async def test_get_when_not_available(self, cache_service):
        """Testa get quando cache não disponível"""
        cache_service._is_connected = False

        result = await cache_service.get("test-plan-123")

        assert result is None

    @pytest.mark.asyncio()
    async def test_get_with_exception(self, cache_service):
        """Testa get com exceção"""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.get("test-plan-123")

        assert result is None


class TestSet:
    """Testes para set (salvar no cache)"""

    @pytest.mark.asyncio()
    async def test_set_success(self, cache_service, sample_features):
        """Testa salvar no cache com sucesso"""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(return_value=True)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.set("test-plan-123", sample_features)

        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio()
    async def test_set_with_custom_ttl(self, cache_service, sample_features):
        """Testa salvar com TTL customizado"""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(return_value=True)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        custom_ttl = 7200
        result = await cache_service.set("test-plan-123", sample_features, ttl_seconds=custom_ttl)

        assert result is True
        # Verifica que TTL customizado foi usado
        call_args = mock_redis.setex.call_args
        # setex é chamado com (key, ttl, value) ou argumentos nomeados
        ttl_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("ttl")
        assert ttl_arg == custom_ttl

    @pytest.mark.asyncio()
    async def test_set_when_not_available(self, cache_service, sample_features):
        """Testa set quando cache não disponível"""
        cache_service._is_connected = False

        result = await cache_service.set("test-plan-123", sample_features)

        assert result is False

    @pytest.mark.asyncio()
    async def test_set_adds_cached_at(self, cache_service, sample_features):
        """Testa que set adiciona timestamp _cached_at"""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(return_value=True)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        with patch("src.services.cache_service.json.dumps") as mock_dumps:
            await cache_service.set("test-plan-123", sample_features)

            # Verifica que _cached_at foi adicionado antes de serializar
            call_args = mock_dumps.call_args
            assert "_cached_at" in call_args[0][0]


class TestDelete:
    """Testes para delete (remover do cache)"""

    @pytest.mark.asyncio()
    async def test_delete_success(self, cache_service):
        """Testa deletar do cache com sucesso"""
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=1)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.delete("test-plan-123")

        assert result is True

    @pytest.mark.asyncio()
    async def test_delete_not_found(self, cache_service):
        """Testa deletar chave inexistente"""
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=0)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.delete("nonexistent")

        assert result is False

    @pytest.mark.asyncio()
    async def test_delete_when_not_available(self, cache_service):
        """Testa delete quando cache não disponível"""
        cache_service._is_connected = False

        result = await cache_service.delete("test-plan-123")

        assert result is False


class TestClearAll:
    """Testes para clear_all (limpar todo o cache)"""

    @pytest.mark.asyncio()
    async def test_clear_all_success(self, cache_service):
        """Testa limpar todo o cache"""
        mock_redis = MagicMock()
        mock_keys = ["key1", "key2", "key3"]

        async def mock_scan_iter(match):
            for key in mock_keys:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete = AsyncMock(return_value=3)
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.clear_all()

        assert result == 3
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio()
    async def test_clear_all_empty(self, cache_service):
        """Testa limpar cache vazio"""
        mock_redis = MagicMock()

        async def mock_scan_iter(match):
            return
            yield  # Generator vazio

        mock_redis.scan_iter = mock_scan_iter
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        result = await cache_service.clear_all()

        assert result == 0


class TestGetStats:
    """Testes para get_stats (estatísticas do cache)"""

    @pytest.mark.asyncio()
    async def test_get_stats_when_available(self, cache_service):
        """Testa obter estatísticas quando disponível"""
        mock_redis = MagicMock()

        async def mock_scan_iter(match):
            yield "feature_store:key1"
            yield "feature_store:key2"

        mock_redis.scan_iter = mock_scan_iter
        cache_service._redis = mock_redis
        cache_service._is_connected = True

        stats = await cache_service.get_stats()

        assert stats["available"] is True
        assert stats["keys_count"] == 2
        assert stats["ttl_seconds"] == 3600

    @pytest.mark.asyncio()
    async def test_get_stats_when_not_available(self, cache_service):
        """Testa obter estatísticas quando não disponível"""
        cache_service._is_connected = False

        stats = await cache_service.get_stats()

        assert stats["available"] is False
        assert stats["keys_count"] == 0


class TestMakeKey:
    """Testes para _make_key (geração de chaves)"""

    def test_make_key(self, cache_service):
        """Testa geração de chave Redis"""
        key = cache_service._make_key("test-plan-123")

        assert key == "feature_store:test-plan-123"

    def test_make_key_with_special_chars(self, cache_service):
        """Testa chave com caracteres especiais"""
        key = cache_service._make_key("plan/with/slashes")

        assert key == "feature_store:plan/with/slashes"


class TestClose:
    """Testes para close (fechar conexão)"""

    @pytest.mark.asyncio()
    async def test_close_with_connection(self, cache_service):
        """Testa fechar conexão ativa"""
        mock_redis = MagicMock()
        mock_redis.close = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        cache_service._redis = mock_redis
        cache_service._pool = mock_pool
        cache_service._is_connected = True

        await cache_service.close()

        assert cache_service._is_connected is False
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio()
    async def test_close_without_connection(self, cache_service):
        """Testa fechar quando não há conexão"""
        cache_service._redis = None
        cache_service._pool = None
        cache_service._is_connected = False

        await cache_service.close()

        assert cache_service._is_connected is False
