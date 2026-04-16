"""Testes para EmbeddingCache."""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from knowledge_graph_rag.embeddings import EmbeddingCache


@pytest.fixture
def mock_redis_pool():
    """Mock do pool de conexões Redis."""
    with patch("knowledge_graph_rag.embeddings.cache.ConnectionPool") as mock_pool_class:
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        yield mock_pool


@pytest.fixture
def mock_redis(mock_redis_pool):
    """Mock do cliente Redis."""
    with patch("knowledge_graph_rag.embeddings.cache.Redis") as mock_redis_class:
        mock_instance = AsyncMock()
        mock_instance.ping = AsyncMock(return_value=True)
        mock_instance.get = AsyncMock(return_value=None)
        mock_instance.setex = AsyncMock(return_value=True)
        mock_instance.exists = AsyncMock(return_value=False)
        mock_instance.delete = AsyncMock(return_value=1)
        mock_instance.scan_iter = AsyncMock(return_value=[])
        mock_instance.close = AsyncMock()
        mock_redis_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def cache(mock_redis):
    """Instância de EmbeddingCache para testes."""
    return EmbeddingCache(
        host="localhost",
        port=6379,
        db=0,
        prefix="test:",
        ttl=3600,
    )


@pytest.mark.asyncio
async def test_connect(cache, mock_redis):
    """Testa conexão com Redis."""
    await cache.connect()

    assert cache._client is not None
    mock_redis.ping.assert_called_once()


@pytest.mark.asyncio
async def test_close(cache, mock_redis):
    """Testa fechamento de conexão."""
    await cache.connect()
    await cache.close()

    mock_redis.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_cache_hit(cache):
    """Testa get com cache hit."""
    cache._client = AsyncMock()
    embedding = [0.1, 0.2, 0.3]
    cache._client.get = AsyncMock(
        return_value=json.dumps(
            {
                "embedding": embedding,
                "model": "test-model",
                "text": "test",
                "created_at": "2024-01-01",
            }
        )
    )

    result = await cache.get("test text", "test-model")

    assert result == embedding
    cache._client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_cache_miss(cache):
    """Testa get com cache miss."""
    cache._client = AsyncMock()
    cache._client.get = AsyncMock(return_value=None)

    result = await cache.get("test text", "test-model")

    assert result is None


@pytest.mark.asyncio
async def test_get_without_client(cache):
    """Testa get sem cliente Redis conectado."""
    cache._client = None

    result = await cache.get("test text", "test-model")

    assert result is None


@pytest.mark.asyncio
async def test_set(cache):
    """Testa set de embedding no cache."""
    cache._client = AsyncMock()
    embedding = [0.1, 0.2, 0.3]

    result = await cache.set("test text", embedding, "test-model")

    assert result is True
    cache._client.setex.assert_called_once()


@pytest.mark.asyncio
async def test_set_without_client(cache):
    """Testa set sem cliente Redis conectado."""
    cache._client = None
    embedding = [0.1, 0.2, 0.3]

    result = await cache.set("test text", embedding, "test-model")

    assert result is False


@pytest.mark.asyncio
async def test_exists_true(cache):
    """Testa exists quando chave existe."""
    cache._client = AsyncMock()
    cache._client.exists = AsyncMock(return_value=1)

    result = await cache.exists("test text", "test-model")

    assert result is True


@pytest.mark.asyncio
async def test_exists_false(cache):
    """Testa exists quando chave não existe."""
    cache._client = AsyncMock()
    cache._client.exists = AsyncMock(return_value=0)

    result = await cache.exists("test text", "test-model")

    assert result is False


@pytest.mark.asyncio
async def test_exists_without_client(cache):
    """Testa exists sem cliente Redis conectado."""
    cache._client = None

    result = await cache.exists("test text", "test-model")

    assert result is False


@pytest.mark.asyncio
async def test_delete_success(cache):
    """Testa delete com sucesso."""
    cache._client = AsyncMock()
    cache._client.delete = AsyncMock(return_value=1)

    result = await cache.delete("test text", "test-model")

    assert result is True
    cache._client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_not_found(cache):
    """Testa delete quando chave não existe."""
    cache._client = AsyncMock()
    cache._client.delete = AsyncMock(return_value=0)

    result = await cache.delete("test text", "test-model")

    assert result is False


@pytest.mark.asyncio
async def test_delete_without_client(cache):
    """Testa delete sem cliente Redis conectado."""
    cache._client = None

    result = await cache.delete("test text", "test-model")

    assert result is False


@pytest.mark.asyncio
async def test_clear(cache):
    """Testa clear do cache."""
    cache._client = AsyncMock()

    # Criar async generator
    async def mock_scan_iter(**kwargs):
        yield "test:key1"
        yield "test:key2"

    cache._client.scan_iter = mock_scan_iter

    await cache.clear()

    cache._client.delete.assert_called_once_with("test:key1", "test:key2")


@pytest.mark.asyncio
async def test_clear_no_keys(cache):
    """Testa clear quando não há chaves."""
    cache._client = AsyncMock()

    async def mock_scan_iter(**kwargs):
        return
        yield  # pragma: no cover

    cache._client.scan_iter = mock_scan_iter

    await cache.clear()

    cache._client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_clear_without_client(cache):
    """Testa clear sem cliente Redis conectado."""
    cache._client = None

    # Não deve levantar erro
    await cache.clear()


@pytest.mark.asyncio
async def test_generate_key(cache):
    """Testa geração de chave de cache."""
    key1 = cache._generate_key("test text", "test-model")
    key2 = cache._generate_key("test text", "test-model")

    # Mesmo input deve gerar mesma chave
    assert key1 == key2

    # Prefixo deve ser aplicado
    assert key1.startswith(cache.prefix)


@pytest.mark.asyncio
async def test_generate_key_different_inputs(cache):
    """Testa geração de chave com inputs diferentes."""
    key1 = cache._generate_key("text one", "model-a")
    key2 = cache._generate_key("text two", "model-b")

    # Inputs diferentes devem gerar chaves diferentes
    assert key1 != key2


@pytest.mark.asyncio
async def test_is_connected_property(cache):
    """Testa propriedade is_connected."""
    assert not cache.is_connected

    await cache.connect()
    assert cache.is_connected


@pytest.mark.asyncio
async def test_set_get_roundtrip(cache):
    """Testa ciclo completo de set/get."""
    cache._client = AsyncMock()

    embedding = [0.5, 0.6, 0.7]
    cache._client.setex = AsyncMock(return_value=True)
    cache._client.get = AsyncMock(
        return_value=json.dumps(
            {
                "embedding": embedding,
                "model": "test-model",
                "text": "test",
                "created_at": "2024-01-01",
            }
        )
    )

    # Set
    await cache.set("test text", embedding, "test-model")

    # Get
    result = await cache.get("test text", "test-model")

    assert result == embedding
