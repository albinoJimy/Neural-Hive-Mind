"""
Testes unitários para OpinionCache.
"""

import json
from unittest.mock import Mock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError, RedisError

from neural_hive_specialists.opinion_cache import OpinionCache


class TestOpinionCacheInitialization:
    """Testes de inicialização do OpinionCache."""

    def test_init_success(self):
        """Testa inicialização bem-sucedida."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.return_value.ping.return_value = True

            cache = OpinionCache(
                redis_cluster_nodes="localhost:6379",
                cache_ttl_seconds=3600,
                specialist_type="technical",
            )

            assert cache.is_connected() is True
            assert cache.cache_ttl_seconds == 3600
            assert cache.specialist_type == "technical"
            # ping é chamado na inicialização e no is_connected()
            assert mock_redis.return_value.ping.call_count == 2

    def test_init_failure_continues_without_cache(self):
        """Testa que falha na inicialização não quebra o sistema."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.side_effect = RedisConnectionError("Connection failed")

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="technical")

            assert cache.is_connected() is False
            assert cache.redis_client is None

    def test_init_with_multiple_nodes(self):
        """Testa inicialização com múltiplos nodes."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.return_value.ping.return_value = True

            cache = OpinionCache(
                redis_cluster_nodes="node1:6379,node2:6379,node3:6379",
                specialist_type="business",
            )

            # Verificar que RedisCluster foi chamado com 3 nodes
            call_args = mock_redis.call_args
            startup_nodes = call_args[1]["startup_nodes"]
            assert len(startup_nodes) == 3
            assert startup_nodes[0] == {"host": "node1", "port": 6379}


class TestCacheKeyGeneration:
    """Testes de geração de chave de cache."""

    @pytest.fixture()
    def cache(self):
        with patch("neural_hive_specialists.opinion_cache.RedisCluster"):
            return OpinionCache(
                redis_cluster_nodes="localhost:6379",
                key_prefix="test:",
                specialist_type="technical",
            )

    def test_generate_cache_key_deterministic(self, cache):
        """Testa que mesmos inputs geram mesma chave."""
        plan_bytes = b'{"plan_id": "test-123"}'

        key1 = cache.generate_cache_key(plan_bytes, "technical", "1.0.0")
        key2 = cache.generate_cache_key(plan_bytes, "technical", "1.0.0")

        assert key1 == key2

    def test_generate_cache_key_different_plans(self, cache):
        """Testa que planos diferentes geram chaves diferentes."""
        plan1 = b'{"plan_id": "test-123"}'
        plan2 = b'{"plan_id": "test-456"}'

        key1 = cache.generate_cache_key(plan1, "technical", "1.0.0")
        key2 = cache.generate_cache_key(plan2, "technical", "1.0.0")

        assert key1 != key2

    def test_generate_cache_key_different_versions(self, cache):
        """Testa que versões diferentes geram chaves diferentes."""
        plan_bytes = b'{"plan_id": "test-123"}'

        key1 = cache.generate_cache_key(plan_bytes, "technical", "1.0.0")
        key2 = cache.generate_cache_key(plan_bytes, "technical", "2.0.0")

        assert key1 != key2

    def test_generate_cache_key_format(self, cache):
        """Testa formato da chave gerada."""
        plan_bytes = b'{"plan_id": "test-123"}'

        key = cache.generate_cache_key(plan_bytes, "technical", "1.0.0")

        # Formato: prefix:tenant:type:version:hash
        assert key.startswith("test:default:technical:1.0.0:")
        assert len(key.split(":")) == 5  # prefix:tenant:type:version:hash


class TestCacheOperations:
    """Testes de operações de cache (get/set)."""

    @pytest.fixture()
    def cache(self):
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.return_value.ping.return_value = True
            cache = OpinionCache(
                redis_cluster_nodes="localhost:6379",
                cache_ttl_seconds=3600,
                specialist_type="technical",
            )
            cache.redis_client = mock_redis.return_value
            cache._connected = True
            return cache

    def test_get_cached_opinion_hit(self, cache):
        """Testa cache hit."""
        opinion = {"confidence_score": 0.9, "recommendation": "approve"}
        cache.redis_client.get.return_value = json.dumps(opinion)

        result = cache.get_cached_opinion("test:key")

        assert result == opinion
        cache.redis_client.get.assert_called_once_with("test:key")

    def test_get_cached_opinion_miss(self, cache):
        """Testa cache miss."""
        cache.redis_client.get.return_value = None

        result = cache.get_cached_opinion("test:key")

        assert result is None

    def test_get_cached_opinion_redis_error(self, cache):
        """Testa tratamento de erro Redis."""
        cache.redis_client.get.side_effect = RedisError("Connection lost")

        result = cache.get_cached_opinion("test:key")

        assert result is None  # Graceful degradation

    def test_get_cached_opinion_json_decode_error(self, cache):
        """Testa tratamento de JSON inválido."""
        cache.redis_client.get.return_value = "invalid json{"
        cache.redis_client.delete = Mock()

        result = cache.get_cached_opinion("test:key")

        assert result is None
        # Deve invalidar cache corrompido
        cache.redis_client.delete.assert_called_once_with("test:key")

    def test_set_cached_opinion_success(self, cache):
        """Testa salvamento bem-sucedido."""
        opinion = {"confidence_score": 0.9, "recommendation": "approve"}
        cache.redis_client.setex = Mock()

        result = cache.set_cached_opinion("test:key", opinion, ttl_seconds=1800)

        assert result is True
        cache.redis_client.setex.assert_called_once()
        call_args = cache.redis_client.setex.call_args[0]
        assert call_args[0] == "test:key"
        assert call_args[1] == 1800
        assert json.loads(call_args[2]) == opinion

    def test_set_cached_opinion_uses_default_ttl(self, cache):
        """Testa que usa TTL padrão quando não especificado."""
        opinion = {"confidence_score": 0.9}
        cache.redis_client.setex = Mock()

        cache.set_cached_opinion("test:key", opinion)

        call_args = cache.redis_client.setex.call_args[0]
        assert call_args[1] == 3600  # TTL padrão

    def test_set_cached_opinion_redis_error(self, cache):
        """Testa tratamento de erro ao salvar."""
        cache.redis_client.setex.side_effect = RedisError("Write failed")

        result = cache.set_cached_opinion("test:key", {"test": "data"})

        assert result is False  # Graceful degradation


class TestCacheInvalidation:
    """Testes de invalidação de cache."""

    @pytest.fixture()
    def cache(self):
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.return_value.ping.return_value = True
            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="technical")
            cache.redis_client = mock_redis.return_value
            cache._connected = True
            return cache

    def test_invalidate_cache_success(self, cache):
        """Testa invalidação bem-sucedida."""
        cache.redis_client.delete.return_value = 1  # 1 key deleted

        result = cache.invalidate_cache("test:key")

        assert result is True
        cache.redis_client.delete.assert_called_once_with("test:key")

    def test_invalidate_cache_key_not_found(self, cache):
        """Testa invalidação de chave inexistente."""
        cache.redis_client.delete.return_value = 0  # No keys deleted

        result = cache.invalidate_cache("test:key")

        assert result is False

    def test_invalidate_cache_error(self, cache):
        """Testa tratamento de erro na invalidação."""
        cache.redis_client.delete.side_effect = RedisError("Delete failed")

        result = cache.invalidate_cache("test:key")

        assert result is False


class TestConnectionManagement:
    """Testes de gerenciamento de conexão."""

    def test_is_connected_true(self):
        """Testa verificação de conexão ativa."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.return_value.ping.return_value = True

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="technical")

            assert cache.is_connected() is True

    def test_is_connected_false_after_ping_failure(self):
        """Testa que is_connected retorna False após falha de ping."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            # side_effect: init(True), is_connected #1(True), is_connected #2(exceção)
            mock_redis.return_value.ping.side_effect = [True, True, RedisError("Ping failed")]

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="technical")

            assert cache.is_connected() is True  # Primeira vez
            assert cache.is_connected() is False  # Segunda vez (ping falha)

    def test_close_connection(self):
        """Testa fechamento de conexão."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_redis.return_value.ping.return_value = True

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="technical")

            cache.close()

            mock_redis.return_value.close.assert_called_once()
            assert cache._connected is False


# =============================================================================
# Testes Adicionais para Cobertura
# =============================================================================


class TestGenerateCacheKey:
    """Testes de geração de chave de cache."""

    def test_generate_cache_key_basic(self):
        """Testa geração básica de chave."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster"):
            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            plan_bytes = b"test plan content"

            key = cache.generate_cache_key(
                plan_bytes=plan_bytes, specialist_type="business", specialist_version="v1.0"
            )

            assert key.startswith("opinion:")
            assert "business" in key

    def test_generate_cache_key_with_tenant(self):
        """Testa geração de chave com tenant."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster"):
            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="technical")

            plan_bytes = b"test plan content"

            key = cache.generate_cache_key(
                plan_bytes=plan_bytes,
                specialist_type="technical",
                specialist_version="v2.0",
                tenant_id="tenant-123",
            )

            assert "tenant-123" in key

    def test_generate_cache_key_deterministic(self):
        """Testa que mesma entrada gera mesma chave."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster"):
            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            plan_bytes = b"test plan content"

            key1 = cache.generate_cache_key(
                plan_bytes=plan_bytes, specialist_type="business", specialist_version="v1.0"
            )

            key2 = cache.generate_cache_key(
                plan_bytes=plan_bytes, specialist_type="business", specialist_version="v1.0"
            )

            assert key1 == key2

    def test_generate_cache_key_different_content(self):
        """Testa que conteúdo diferente gera chave diferente."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster"):
            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            key1 = cache.generate_cache_key(
                plan_bytes=b"content 1", specialist_type="business", specialist_version="v1.0"
            )

            key2 = cache.generate_cache_key(
                plan_bytes=b"content 2", specialist_type="business", specialist_version="v1.0"
            )

            assert key1 != key2


class TestGetOpinion:
    """Testes de get de opinião."""

    def test_get_opinion_cached(self):
        """Testa get de opinião em cache."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.get = Mock(return_value='{"opinion": "approve"}')
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            result = cache.get_cached_opinion("test:key")

            assert result == {"opinion": "approve"}

    def test_get_opinion_not_cached(self):
        """Testa get de opinião não em cache."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.get = Mock(return_value=None)
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            result = cache.get_cached_opinion("test:key")

            assert result is None

    def test_get_opinion_deserialize_error(self):
        """Testa get com erro de desserialização."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.get = Mock(return_value="invalid json")
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            result = cache.get_cached_opinion("test:key")

            assert result is None


class TestSetOpinion:
    """Testes de set de opinião."""

    def test_set_opinion_success(self):
        """Testa set de opinião com sucesso."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.setex = Mock()
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            cache.set_cached_opinion("test:key", {"opinion": "approve"})

            mock_client.setex.assert_called_once()

    def test_set_opinion_serializes_json(self):
        """Testa que opinião é serializada para JSON."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.setex = Mock()
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            cache.set_cached_opinion("test:key", {"opinion": "approve", "confidence": 0.8})

            # Verificar que JSON foi serializado
            call_args = mock_client.setex.call_args
            assert call_args is not None


class TestInvalidateOpinion:
    """Testes de invalidate de opinião."""

    def test_invalidate_opinion_success(self):
        """Testa invalidate de opinião com sucesso."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.delete = Mock(return_value=1)
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            result = cache.invalidate_cache("test:key")

            assert result is True

    def test_invalidate_opinion_not_exists(self):
        """Testa invalidate de opinião que não existe."""
        with patch("neural_hive_specialists.opinion_cache.RedisCluster") as mock_redis:
            mock_client = Mock()
            mock_client.delete = Mock(return_value=0)
            mock_redis.return_value = mock_client

            cache = OpinionCache(redis_cluster_nodes="localhost:6379", specialist_type="business")

            result = cache.invalidate_cache("test:key")

            assert result is False
