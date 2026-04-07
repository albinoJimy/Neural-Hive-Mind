"""
Testes para RedisStateStore.
Compartilhamento de estado via Redis.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from src.coordination.redis_state_store import RedisStateStore, REDIS_AVAILABLE


@pytest.fixture
def state_store():
    """Instância de RedisStateStore para testes."""
    return RedisStateStore(redis_url="redis://localhost:6379/15", key_prefix="test_scout", ttl=60)


@pytest.fixture
def mock_redis():
    """Mock de cliente Redis."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.hset = AsyncMock(return_value=True)
    mock.hexists = AsyncMock(return_value=False)
    mock.expire = AsyncMock(return_value=True)
    mock.lpush = AsyncMock(return_value=1)
    mock.ltrim = AsyncMock(return_value=True)
    mock.lrange = AsyncMock(return_value=[])
    mock.incrby = AsyncMock(return_value=1)
    mock.ping = AsyncMock(return_value=True)
    mock.scan_iter = MagicMock(return_value=[])
    mock.close = AsyncMock(return_value=True)
    mock.ttl = AsyncMock(return_value=300)
    return mock


class TestConnection:
    """Testes de conexão com Redis."""

    @pytest.mark.asyncio
    async def test_start_without_redis(self, state_store):
        """Testa start sem Redis disponível."""
        # Redis pode não estar disponível em testes
        await state_store.start()
        # Não deve lançar exceção

    @pytest.mark.asyncio
    async def test_stop(self, state_store, mock_redis):
        """Testa fechamento de conexão."""
        state_store._redis = mock_redis
        await state_store.stop()

        mock_redis.close.assert_called_once()


class TestTaskProgress:
    """Testes de progresso de tarefa."""

    @pytest.mark.asyncio
    async def test_set_and_get_task_progress(self, state_store, mock_redis):
        """Testa armazenar e recuperar progresso."""
        state_store._redis = mock_redis

        progress = {"completed": 50, "total": 100}
        await state_store.set_task_progress("scout_1", "task_1", progress)

        # Setup mock para retornar dados
        mock_redis.get.return_value = (
            '{"scout_id": "scout_1", "progress": ' + json.dumps(progress) + "}"
        )
        mock_redis.get = AsyncMock(
            return_value=json.dumps({"scout_id": "scout_1", "progress": progress})
        )

        result = await state_store.get_task_progress("task_1")

        assert result is not None
        assert result["scout_id"] == "scout_1"
        assert result["progress"] == progress

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, state_store, mock_redis):
        """Testa buscar tarefa inexistente."""
        state_store._redis = mock_redis
        mock_redis.get.return_value = None

        result = await state_store.get_task_progress("nonexistent")

        assert result is None


class TestExploredFiles:
    """Testes de arquivos explorados."""

    @pytest.mark.asyncio
    async def test_mark_and_check_file(self, state_store, mock_redis):
        """Testa marcar e verificar arquivo explorado."""
        state_store._redis = mock_redis

        await state_store.mark_file_explored("test.py", "scout_1", "exp_1")
        mock_redis.hexists.return_value = True

        is_explored = await state_store.is_file_explored("test.py", "exp_1")

        assert is_explored is True

    @pytest.mark.asyncio
    async def test_check_unexplored_file(self, state_store, mock_redis):
        """Testa verificar arquivo não explorado."""
        state_store._redis = mock_redis
        mock_redis.hexists.return_value = False

        is_explored = await state_store.is_file_explored("unexplored.py", "exp_1")

        assert is_explored is False


class TestLocks:
    """Testes de locks."""

    @pytest.mark.asyncio
    async def test_acquire_and_release_lock(self, state_store, mock_redis):
        """Testa adquirir e liberar lock."""
        state_store._redis = mock_redis
        mock_redis.set.return_value = True  # Lock adquirido
        mock_redis.get.return_value = "scout_1:123456.789"

        # Adquirir lock
        acquired = await state_store.acquire_lock("resource", "scout_1")
        assert acquired is True

        # Liberar lock
        await state_store.release_lock("resource", "scout_1")

        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_already_held(self, state_store, mock_redis):
        """Testa lock já segurado por outro."""
        state_store._redis = mock_redis
        # Lock já existe
        mock_redis.set.return_value = False

        acquired = await state_store.acquire_lock("resource", "scout_2")

        assert acquired is False


class TestDiscoveries:
    """Testes de descobertas."""

    @pytest.mark.asyncio
    async def test_publish_and_get_discoveries(self, state_store, mock_redis):
        """Testa publicar e recuperar descobertas."""
        state_store._redis = mock_redis

        discovery = {"type": "pattern", "name": "Repository"}
        await state_store.publish_discovery("exp_1", discovery)

        # Configurar mock
        mock_redis.lrange.return_value = [
            json.dumps({"discovery": discovery, "published_at": "2024-01-01T00:00:00"})
        ]

        discoveries = await state_store.get_discoveries("exp_1")

        assert len(discoveries) == 1
        assert discoveries[0]["discovery"] == discovery


class TestScoutState:
    """Testes de estado de scout."""

    @pytest.mark.asyncio
    async def test_set_and_get_scout_state(self, state_store, mock_redis):
        """Testa armazenar e recuperar estado."""
        state_store._redis = mock_redis

        state = {"position": "/src", "files_scanned": 10}
        await state_store.set_scout_state("scout_1", state)

        mock_redis.get.return_value = json.dumps(state)
        result = await state_store.get_scout_state("scout_1")

        assert result is not None
        assert result["position"] == "/src"
        assert result["files_scanned"] == 10


class TestCounters:
    """Testes de contadores compartilhados."""

    @pytest.mark.asyncio
    async def test_increment_counter(self, state_store, mock_redis):
        """Testa incrementar contador."""
        state_store._redis = mock_redis
        mock_redis.incrby.return_value = 5

        new_value = await state_store.increment_counter("files_scanned", 3)

        assert new_value == 5
        mock_redis.incrby.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_counter(self, state_store, mock_redis):
        """Testa obter contador."""
        state_store._redis = mock_redis
        mock_redis.get.return_value = "10"

        value = await state_store.get_counter("files_scanned")

        assert value == 10


class TestMakeKey:
    """Testes de criação de chaves Redis."""

    def test_make_key(self, state_store):
        """Testa criação de chaves com prefixo."""
        key1 = state_store._make_key("task", "task_1")
        assert key1 == "test_scout:task:task_1"

        key2 = state_store._make_key("lock", "resource", "sub")
        assert key2 == "test_scout:lock:resource:sub"


class TestFallbackBehavior:
    """Testes de comportamento fallback sem Redis."""

    @pytest.mark.asyncio
    async def test_acquire_lock_fallback(self, state_store):
        """Testa lock sem Redis (fallback)."""
        state_store._redis = None

        acquired = await state_store.acquire_lock("resource", "scout_1")

        # Sem Redis, sempre retorna True
        assert acquired is True

    @pytest.mark.asyncio
    async def test_get_counter_fallback(self, state_store):
        """Testa contador sem Redis (fallback)."""
        state_store._redis = None

        value = await state_store.get_counter("nonexistent")

        # Sem Redis, retorna 0
        assert value == 0
