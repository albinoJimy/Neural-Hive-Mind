"""Testes para QdrantClient."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from knowledge_graph_rag.graph.qdrant_client import QdrantClient


@pytest.fixture
def client():
    return QdrantClient(host="localhost", port=6333)


@pytest.mark.asyncio
async def test_connect(client):
    """Testa conexão com Qdrant."""
    with patch("knowledge_graph_rag.graph.qdrant_client.QdrantClient") as mock_qdrant:
        mock_instance = AsyncMock()
        mock_qdrant.return_value = mock_instance
        mock_instance.create_collection = AsyncMock()
        mock_instance.create_collection.side_effect = Exception("Collection exists")

        await client.connect()

        assert client.client is not None
        mock_qdrant.assert_called_once_with(host="localhost", port=6333)


@pytest.mark.asyncio
async def test_close(client):
    """Testa fechamento de conexão."""
    client.client = AsyncMock()
    client.client.close = Mock()

    await client.close()

    client.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_search_templates(client):
    """Testa busca de templates similares."""
    client.client = AsyncMock()
    mock_result = Mock()
    mock_result.id = "tpl-001"
    mock_result.score = 0.85
    mock_result.payload = {"name": "API Template", "language": "python"}

    client.client.search = AsyncMock(return_value=[mock_result])

    results = await client.search_templates(
        query_vector=[0.1] * 1536,
        limit=10,
        score_threshold=0.7
    )

    assert len(results) == 1
    assert results[0]["id"] == "tpl-001"
    assert results[0]["score"] == 0.85
    assert results[0]["payload"]["name"] == "API Template"


@pytest.mark.asyncio
async def test_search_code(client):
    """Testa busca de código similar."""
    client.client = AsyncMock()
    mock_result = Mock()
    mock_result.id = "code-001"
    mock_result.score = 0.92
    mock_result.payload = {"name": "main.py", "language": "python"}

    client.client.search = AsyncMock(return_value=[mock_result])

    results = await client.search_code(
        query_vector=[0.1] * 1536,
        limit=10,
        score_threshold=0.7,
        language_filter="python"
    )

    assert len(results) == 1
    assert results[0]["id"] == "code-001"
    assert results[0]["score"] == 0.92
    assert results[0]["payload"]["language"] == "python"


@pytest.mark.asyncio
async def test_search_code_without_filter(client):
    """Testa busca de código sem filtro de linguagem."""
    client.client = AsyncMock()
    mock_result = Mock()
    mock_result.id = "code-002"
    mock_result.score = 0.78
    mock_result.payload = {"name": "app.js", "language": "javascript"}

    client.client.search = AsyncMock(return_value=[mock_result])

    results = await client.search_code(
        query_vector=[0.1] * 1536,
        limit=10,
        score_threshold=0.7
    )

    assert len(results) == 1
    assert results[0]["payload"]["language"] == "javascript"


@pytest.mark.asyncio
async def test_index_template(client):
    """Testa indexação de template."""
    client.client = AsyncMock()
    client.client.upsert = AsyncMock()

    await client.index_template(
        template_id="tpl-001",
        vector=[0.1] * 1536,
        payload={"name": "API Template", "language": "python"}
    )

    client.client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_index_code(client):
    """Testa indexação de código."""
    client.client = AsyncMock()
    client.client.upsert = AsyncMock()

    await client.index_code(
        code_id="code-001",
        vector=[0.1] * 1536,
        payload={"name": "main.py", "language": "python"}
    )

    client.client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_delete_points(client):
    """Testa remoção de pontos."""
    client.client = AsyncMock()
    client.client.delete = AsyncMock()

    await client.delete_points(
        collection_name="nhm_templates",
        ids=["tpl-001", "tpl-002"]
    )

    client.client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_collections(client):
    """Testa garantia de existência de coleções."""
    client.client = AsyncMock()
    client.client.create_collection = AsyncMock()

    await client._ensure_collections()

    assert client.client.create_collection.call_count == 2
