"""
Testes do Fallback Storage para Redis com MongoDB.

Gap P0-3: State Divergence - Redis primário sem fallback MongoDB
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock
from unittest.mock import patch

import pytest

from src.services.fallback_storage import FallbackStorage, FallbackRedisWrapper


@pytest.fixture
def mock_redis():
    """Mock de cliente Redis async"""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.lrange = AsyncMock(return_value=[])
    redis.lpush = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_mongodb():
    """Mock de cliente MongoDB"""
    mongodb = MagicMock()
    mongodb.db = MagicMock()
    mongodb.client = MagicMock()

    # Mock de collection com AsyncMock correto
    collection = AsyncMock()
    collection.find_one = AsyncMock(return_value=None)
    collection.update_one = AsyncMock(return_value=True)
    collection.delete_one = AsyncMock(return_value=True)
    collection.create_index = AsyncMock(return_value=True)
    collection.find = MagicMock()

    # Configurar db.__getitem__ para retornar a collection
    mongodb.db.__getitem__ = Mock(return_value=collection)
    mongodb.client.admin.command = AsyncMock(return_value={"ok": 1})

    return mongodb


@pytest.fixture
def mock_config():
    """Mock de configurações"""
    config = MagicMock()
    config.pheromone_ttl = 3600
    config.pheromone_decay_rate = 0.1
    return config


@pytest.fixture
async def fallback_storage(mock_redis, mock_mongodb, mock_config):
    """Fixture do FallbackStorage inicializado"""
    storage = FallbackStorage(
        redis_client=mock_redis,
        mongodb_client=mock_mongodb,
        config=mock_config,
    )
    await storage.initialize()
    return storage


class TestFallbackStorage:
    """Testes do FallbackStorage"""

    @pytest.mark.asyncio
    async def test_initialize_creates_indexes(self, mock_mongodb, mock_config):
        """Testa que initialize cria índices MongoDB"""
        # Criar mock explícito para collection
        collection = AsyncMock()
        collection.create_index = AsyncMock(return_value=True)

        # Configurar db.__getitem__ para retornar a collection
        mock_mongodb.db.__getitem__ = Mock(return_value=collection)

        storage = FallbackStorage(
            redis_client=AsyncMock(),
            mongodb_client=mock_mongodb,
            config=mock_config,
        )
        await storage.initialize()

        # Verifica que create_index foi chamado 3 vezes (key, expires_at, composto, TTL)
        assert collection.create_index.call_count == 4  # 4 índices criados

    @pytest.mark.asyncio
    async def test_get_redis_hit(self, fallback_storage, mock_redis):
        """Testa GET com hit no Redis"""
        mock_redis.get.return_value = '{"value": "test"}'  # String ao invés de bytes

        result = await fallback_storage.get("test_key")

        assert result == '{"value": "test"}'
        assert fallback_storage._redis_hits == 1
        assert fallback_storage._fallback_hits == 0

    @pytest.mark.asyncio
    async def test_get_fallback_to_mongodb(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa GET com fallback para MongoDB quando Redis falha"""
        # Redis falha
        mock_redis.get.side_effect = Exception("Redis connection error")

        # MongoDB retorna valor
        mock_mongodb.db["redis_fallback"].find_one = AsyncMock(
            return_value={
                "key": "test_key",
                "value": "fallback_value",
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            }
        )

        result = await fallback_storage.get("test_key")

        assert result == "fallback_value"
        assert fallback_storage._fallback_hits == 1
        assert fallback_storage._redis_failures == 1

    @pytest.mark.asyncio
    async def test_get_expired_from_mongodb(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa GET com valor expirado no MongoDB"""
        mock_redis.get.side_effect = Exception("Redis down")

        # MongoDB retorna valor expirado
        mock_mongodb.db["redis_fallback"].find_one = AsyncMock(
            return_value={
                "key": "test_key",
                "value": "expired_value",
                "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
            }
        )
        mock_mongodb.db["redis_fallback"].delete_one = AsyncMock()

        result = await fallback_storage.get("test_key")

        assert result is None  # Valor expirado

    @pytest.mark.asyncio
    async def test_set_writes_to_both(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa SET escreve em AMBOS Redis e MongoDB"""
        await fallback_storage.set("test_key", "test_value", ex=300)

        # Verifica que Redis.set foi chamado
        mock_redis.set.assert_called_once_with("test_key", "test_value", ex=300)

        # Verifica que MongoDB update_one foi chamado
        collection = mock_mongodb.db["redis_fallback"]
        assert collection.update_one.call_count == 1

    @pytest.mark.asyncio
    async def test_set_redis_fails_mongodb_succeeds(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa SET quando Redis falha mas MongoDB sucesso"""
        mock_redis.set.side_effect = Exception("Redis down")

        result = await fallback_storage.set("test_key", "test_value", ex=300)

        # Deve retornar True porque MongoDB sucesso
        assert result is True
        assert fallback_storage._redis_failures == 1

    @pytest.mark.asyncio
    async def test_delete_from_both(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa DELETE remove de AMBOS"""
        await fallback_storage.delete("test_key")

        mock_redis.delete.assert_called_once_with("test_key")
        mock_mongodb.db["redis_fallback"].delete_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_lrange_fallback(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa LRANGE com fallback"""
        mock_redis.lrange.side_effect = Exception("Redis down")

        # MongoDB retorna lista
        mock_mongodb.db["redis_fallback"].find_one = AsyncMock(
            return_value={
                "key": "test_list",
                "type": "list",
                "items": ["item1", "item2", "item3"],
            }
        )

        result = await fallback_storage.lrange("test_list", 0, -1)

        assert result == ["item1", "item2", "item3"]

    @pytest.mark.asyncio
    async def test_lpush_to_both(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa LPUSH escreve em AMBOS"""
        mock_redis.lpush.return_value = 3

        result = await fallback_storage.lpush("test_list", "item1", "item2")

        # Redis retorna tamanho
        assert result == 3

        # Verifica que MongoDB também foi chamado
        collection = mock_mongodb.db["redis_fallback"]
        assert collection.update_one.call_count == 1

    @pytest.mark.asyncio
    async def test_ping_both_healthy(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa PING quando AMBOS estão saudáveis"""
        result = await fallback_storage.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_redis_down_mongodb_up(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa PING quando Redis falha mas MongoDB OK"""
        mock_redis.ping.side_effect = Exception("Redis down")

        result = await fallback_storage.ping()

        # Deve retornar True porque MongoDB está OK
        assert result is True
        assert fallback_storage.is_redis_enabled() is False  # Redis desabilitado

    @pytest.mark.asyncio
    async def test_ping_both_down(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa PING quando AMBOS falham"""
        mock_redis.ping.side_effect = Exception("Redis down")
        mock_mongodb.client.admin.command.side_effect = Exception("MongoDB down")

        result = await fallback_storage.ping()

        assert result is False

    @pytest.mark.asyncio
    async def test_disable_enable_redis(self, fallback_storage):
        """Testa desabilitar/habilitar Redis manualmente"""
        assert fallback_storage.is_redis_enabled() is True

        fallback_storage.disable_redis()
        assert fallback_storage.is_redis_enabled() is False

        fallback_storage.enable_redis()
        assert fallback_storage.is_redis_enabled() is True

    @pytest.mark.asyncio
    async def test_get_metrics(self, fallback_storage):
        """Testa obtenção de métricas"""
        # Simular alguns hits
        fallback_storage._redis_hits = 100
        fallback_storage._fallback_hits = 10
        fallback_storage._redis_failures = 5

        metrics = fallback_storage.get_metrics()

        assert metrics["redis_hits"] == 100
        assert metrics["fallback_hits"] == 10
        assert metrics["redis_failures"] == 5
        assert metrics["total_reads"] == 110
        assert metrics["fallback_rate"] == pytest.approx(0.0909, rel=0.01)

    @pytest.mark.asyncio
    async def test_reset_metrics(self, fallback_storage):
        """Testa reset de métricas"""
        fallback_storage._redis_hits = 100
        fallback_storage._fallback_hits = 10
        fallback_storage._redis_failures = 5

        fallback_storage.reset_metrics()

        assert fallback_storage._redis_hits == 0
        assert fallback_storage._fallback_hits == 0
        assert fallback_storage._redis_failures == 0


class TestFallbackRedisWrapper:
    """Testes do FallbackRedisWrapper"""

    @pytest.mark.asyncio
    async def test_wrapper_delegates_to_fallback(self, fallback_storage):
        """Testa que wrapper delega para FallbackStorage"""
        wrapper = FallbackRedisWrapper(fallback_storage)

        # Setup mock para retornar valor
        fallback_storage.get = AsyncMock(return_value="test_value")
        fallback_storage.set = AsyncMock(return_value=True)
        fallback_storage.delete = AsyncMock(return_value=True)
        fallback_storage.lrange = AsyncMock(return_value=[])
        fallback_storage.lpush = AsyncMock(return_value=1)
        fallback_storage.expire = AsyncMock(return_value=True)
        fallback_storage.ping = AsyncMock(return_value=True)

        # Testar todos os métodos
        assert await wrapper.get("key") == "test_value"
        assert await wrapper.set("key", "value", ex=300) is True
        assert await wrapper.delete("key") is True
        assert await wrapper.lrange("list", 0, -1) == []
        assert await wrapper.lpush("list", "item") == 1
        assert await wrapper.expire("key", 300) is True
        assert await wrapper.ping() is True

        # Verifica close (no-op)
        wrapper.close()

    @pytest.mark.asyncio
    async def test_wrapper_close_no_op(self, fallback_storage):
        """Testa que close do wrapper é no-op"""
        wrapper = FallbackRedisWrapper(fallback_storage)
        wrapper.close()  # Não deve levantar exceção


class TestBackgroundSync:
    """Testes de background sync"""

    @pytest.mark.asyncio
    async def test_background_sync_loop(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa loop de background sync"""
        # Setup mock para retornar documentos
        doc = {
            "key": "test_key",
            "value": "test_value",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Mock de cursor async
        async def async_iter():
            yield doc

        mock_find = AsyncMock()
        mock_find.__aiter__ = lambda self: async_iter()

        collection = mock_mongodb.db["redis_fallback"]
        collection.find = lambda *args, **kwargs: mock_find

        mock_redis.get = AsyncMock(return_value=None)  # Redis não tem a chave
        mock_redis.set = AsyncMock(return_value=True)

        # Executar sync
        restored = await fallback_storage._sync_mongodb_to_redis()

        assert restored == 1
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_stop_background_sync(self, fallback_storage):
        """Testa iniciar/parar background sync"""
        assert fallback_storage._sync_running is False

        await fallback_storage.start_background_sync()
        assert fallback_storage._sync_running is True

        await fallback_storage.stop_background_sync()
        assert fallback_storage._sync_running is False

    @pytest.mark.asyncio
    async def test_sync_skip_existing_keys(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa sync pula chaves que já existem no Redis"""
        doc = {
            "key": "existing_key",
            "value": "existing_value",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        async def async_iter():
            yield doc

        mock_find = AsyncMock()
        mock_find.__aiter__ = lambda self: async_iter()

        collection = mock_mongodb.db["redis_fallback"]
        collection.find = lambda *args, **kwargs: mock_find

        mock_redis.get = AsyncMock(return_value=b"existing")  # Chave já existe

        restored = await fallback_storage._sync_mongodb_to_redis()

        # Não deve restaurar pois já existe
        assert restored == 0
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skip_expired_keys(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa sync pula chaves expiradas"""
        doc = {
            "key": "expired_key",
            "value": "expired_value",
            "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }

        async def async_iter():
            yield doc

        mock_find = AsyncMock()
        mock_find.__aiter__ = lambda self: async_iter()

        collection = mock_mongodb.db["redis_fallback"]
        collection.find = lambda *args, **kwargs: mock_find

        restored = await fallback_storage._sync_mongodb_to_redis()

        # Não deve restaurar pois expirou
        assert restored == 0
        mock_redis.set.assert_not_called()


class TestConsisntencyGuarantees:
    """Testes de garantias de consistência do fallback"""

    @pytest.mark.asyncio
    async def test_write_consistency_both_stores(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa que escritas vão para AMBOS os stores"""
        await fallback_storage.set("key", "value", ex=60)

        # Ambos devem ser chamados
        mock_redis.set.assert_called_once()
        mock_mongodb.db["redis_fallback"].update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_consistency_both_stores(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa que deleções vão para AMBOS os stores"""
        await fallback_storage.delete("key")

        # Ambos devem ser chamados
        mock_redis.delete.assert_called_once()
        mock_mongodb.db["redis_fallback"].delete_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_fallback_on_redis_failure(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa que leitura usa MongoDB quando Redis falha"""
        mock_redis.get.side_effect = Exception("Redis down")

        mock_mongodb.db["redis_fallback"].find_one = AsyncMock(
            return_value={
                "key": "test_key",
                "value": "from_mongo",
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            }
        )

        result = await fallback_storage.get("test_key")

        assert result == "from_mongo"
        assert fallback_storage._fallback_hits == 1

    @pytest.mark.asyncio
    async def test_restore_to_redis_on_background_task(self, fallback_storage, mock_redis, mock_mongodb):
        """Testa que dados do MongoDB são restaurados para Redis em background"""
        # Simular restauração
        mock_redis.set = AsyncMock(return_value=True)

        await fallback_storage._restore_to_redis("test_key", "test_value")

        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_track_failures(self, fallback_storage):
        """Testa que métricas rastreiam falhas Redis"""
        fallback_storage._redis_failures = 5
        fallback_storage._redis_hits = 95
        fallback_storage._fallback_hits = 5

        metrics = fallback_storage.get_metrics()

        assert metrics["redis_failures"] == 5
        assert metrics["fallback_rate"] == pytest.approx(0.05, rel=0.01)
