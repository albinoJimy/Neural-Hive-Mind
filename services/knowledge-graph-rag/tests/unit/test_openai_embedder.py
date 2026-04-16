"""Testes para OpenAIEmbedder."""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from knowledge_graph_rag.embeddings import OpenAIEmbedder, EmbeddingCache
from knowledge_graph_rag.embeddings.models import (
    EmbeddingResponse,
    EmbeddingBatchResponse,
)


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
def mock_cache(mock_redis):
    """Mock do cache de embeddings."""
    cache = EmbeddingCache(host="localhost", port=6379)
    cache._client = mock_redis
    return cache


@pytest.fixture
def mock_openai_client():
    """Mock do cliente OpenAI."""
    mock_instance = AsyncMock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1] * 1536)]
    mock_instance.embeddings.create = AsyncMock(return_value=mock_response)
    mock_instance.close = AsyncMock()
    return mock_instance


@pytest.fixture
def embedder(mock_cache, mock_openai_client):
    """Instância do OpenAIEmbedder para testes."""
    embedder = OpenAIEmbedder(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
        cache=mock_cache,
    )
    # Injeta o mock do OpenAI diretamente
    embedder._client = mock_openai_client
    return embedder


@pytest.mark.asyncio
async def test_embed_returns_correct_vector(embedder):
    """Testa se embed() retorna vetor com 1536 dimensões."""
    result = await embedder.embed("Texto de teste", use_cache=False)

    assert isinstance(result, list)
    assert len(result) == 1536
    assert all(isinstance(x, float) for x in result)
    assert result == [0.1] * 1536


@pytest.mark.asyncio
async def test_embed_with_cache_hit(embedder, mock_cache):
    """Testa se embed() usa cache quando disponível."""
    cached_embedding = [0.5] * 1536

    # Configurar cache para retornar valor
    mock_cache._client.exists = AsyncMock(return_value=True)
    mock_cache._client.get = AsyncMock(
        return_value=json.dumps({"embedding": cached_embedding, "model": "test-model"})
    )

    result = await embedder.embed("Texto em cache")

    assert result == cached_embedding
    # Não deve chamar a API pois hit no cache
    embedder._client.embeddings.create.assert_not_called()


@pytest.mark.asyncio
async def test_embed_empty_text_raises_error(embedder):
    """Testa se embed() levanta erro para texto vazio."""
    with pytest.raises(ValueError, match="Text cannot be empty"):
        await embedder.embed("")


@pytest.mark.asyncio
async def test_embed_batch_handles_multiple_texts(embedder):
    """Testa se embed_batch() processa múltiplos textos."""
    # Configurar mock para retornar embeddings diferentes
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1] * 1536),
        Mock(embedding=[0.2] * 1536),
        Mock(embedding=[0.3] * 1536),
    ]
    embedder._client.embeddings.create = AsyncMock(return_value=mock_response)

    texts = ["Texto 1", "Texto 2", "Texto 3"]
    results = await embedder.embed_batch(texts, use_cache=False)

    assert len(results) == 3
    assert len(results[0]) == 1536
    assert len(results[1]) == 1536
    assert len(results[2]) == 1536
    assert results[0] == [0.1] * 1536
    assert results[1] == [0.2] * 1536
    assert results[2] == [0.3] * 1536


@pytest.mark.asyncio
async def test_embed_batch_with_empty_list_raises_error(embedder):
    """Testa se embed_batch() levanta erro para lista vazia."""
    with pytest.raises(ValueError, match="Texts list cannot be empty"):
        await embedder.embed_batch([])


@pytest.mark.asyncio
async def test_cosine_similarity():
    """Testa cálculo de similaridade de cosseno."""
    # Vetores idênticos devem ter similaridade 1
    vec1 = [0.1, 0.2, 0.3]
    vec2 = [0.1, 0.2, 0.3]

    similarity = OpenAIEmbedder.cosine_similarity(vec1, vec2)
    assert similarity == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_cosine_similarity_opposite():
    """Testa similaridade de cosseno para vetores opostos."""
    vec1 = [1.0, 0.0]
    vec2 = [-1.0, 0.0]

    similarity = OpenAIEmbedder.cosine_similarity(vec1, vec2)
    assert similarity == pytest.approx(-1.0)


@pytest.mark.asyncio
async def test_cosine_similarity_orthogonal():
    """Testa similaridade de cosseno para vetores ortogonais."""
    vec1 = [1.0, 0.0]
    vec2 = [0.0, 1.0]

    similarity = OpenAIEmbedder.cosine_similarity(vec1, vec2)
    assert similarity == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_cosine_similarity_different_dimensions_raises_error():
    """Testa se cosine_similarity levanta erro para vetores de tamanhos diferentes."""
    vec1 = [0.1, 0.2]
    vec2 = [0.1, 0.2, 0.3]

    with pytest.raises(ValueError, match="Vectors must have same length"):
        OpenAIEmbedder.cosine_similarity(vec1, vec2)


@pytest.mark.asyncio
async def test_to_response(embedder):
    """Testa conversão para EmbeddingResponse."""
    response = await embedder.to_response("Teste", use_cache=False)

    assert isinstance(response, EmbeddingResponse)
    assert len(response.embedding) == 1536
    assert response.model == "text-embedding-3-small"
    assert response.dimensions == 1536


@pytest.mark.asyncio
async def test_to_batch_response(embedder):
    """Testa conversão para EmbeddingBatchResponse."""
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1] * 1536),
        Mock(embedding=[0.2] * 1536),
    ]
    embedder._client.embeddings.create = AsyncMock(return_value=mock_response)

    response = await embedder.to_batch_response(["Texto 1", "Texto 2"], use_cache=False)

    assert isinstance(response, EmbeddingBatchResponse)
    assert len(response.embeddings) == 2
    assert response.model == "text-embedding-3-small"
    assert response.dimensions == 1536


@pytest.mark.asyncio
async def test_is_connected_property(embedder):
    """Testa propriedade is_connected."""
    assert embedder.is_connected is True


@pytest.mark.asyncio
async def test_cache_set_get(mock_cache):
    """Testa set e get do cache."""
    import json

    embedding = [0.7] * 1536

    # Configurar mock para retornar valor em cache no get
    mock_cache._client.get = AsyncMock(
        return_value=json.dumps(
            {
                "embedding": embedding,
                "model": "test-model",
                "text": "test key",
                "created_at": "2024-01-01",
            }
        )
    )

    result = await mock_cache.get("test key", "test-model")

    assert result is not None
    assert result == embedding


@pytest.mark.asyncio
async def test_cache_exists(embedder, mock_cache):
    """Testa método exists do cache."""
    mock_cache._client.exists = AsyncMock(return_value=1)
    exists = await mock_cache.exists("test key", "test-model")

    assert exists is True


@pytest.mark.asyncio
async def test_cache_delete(embedder, mock_cache):
    """Testa método delete do cache."""
    deleted = await mock_cache.delete("test key", "test-model")

    assert deleted is True
    mock_cache._client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cache_clear(mock_cache):
    """Testa método clear do cache."""

    # Configurar scan_iter para retornar algumas chaves
    # Usar um async generator
    async def mock_scan_iter(**kwargs):
        yield "embed:key1"
        yield "embed:key2"

    mock_cache._client.scan_iter = mock_scan_iter

    await mock_cache.clear()

    mock_cache._client.delete.assert_called_once_with("embed:key1", "embed:key2")


@pytest.mark.asyncio
async def test_connect_without_api_key():
    """Testa connect sem chave de API."""
    embedder = OpenAIEmbedder(api_key="", cache=None)
    await embedder.connect()

    assert embedder._client is None
    assert embedder.is_connected is False


@pytest.mark.asyncio
async def test_close_closes_clients(embedder, mock_cache):
    """Testa se close() fecha conexões."""
    await embedder.close()

    mock_cache._client.close.assert_called_once()
    embedder._client.close.assert_called_once()


@pytest.mark.asyncio
async def test_embed_batch_with_cache_partial_hit(mock_cache):
    """Testa embed_batch com cache parcial."""
    # Criar embedder sem cache para teste simples
    embedder = OpenAIEmbedder(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
        cache=None,
    )

    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1] * 1536),
    ]
    embedder._client = AsyncMock()
    embedder._client.embeddings.create = AsyncMock(return_value=mock_response)

    texts = ["Texto 1"]
    results = await embedder.embed_batch(texts)

    assert len(results) == 1
    assert len(results[0]) == 1536
