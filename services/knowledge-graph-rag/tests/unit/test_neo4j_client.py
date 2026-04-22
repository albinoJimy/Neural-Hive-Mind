"""Testes para Neo4jClient."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from knowledge_graph_rag.graph.neo4j_client import Neo4jClient


@pytest.fixture
def client():
    return Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="test")


@pytest.mark.asyncio
async def test_find_similar_architectures(client):
    """Testa busca de arquiteturas similares."""
    with patch.object(client, "execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [
            {"plan_id": "ARCH-001", "similarity": 0.85, "architecture_type": "microservices"}
        ]

        results = await client.find_similar_architectures(
            requirements=["API REST", "Database"], limit=5
        )

        assert len(results) > 0
        assert results[0]["similarity"] >= 0.8


@pytest.mark.asyncio
async def test_get_connections_context(client):
    """Testa obtenção de contexto de conexões."""
    with patch.object(client, "execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [
            {
                "from_id": "service-123",
                "to_id": "service-456",
                "connection_type": "HTTP",
                "description": "REST calls",
            }
        ]

        context = await client.get_connections_context(node_id="service-123")

        assert "from_id" in context[0]
        assert context[0]["from_id"] == "service-123"


@pytest.mark.asyncio
async def test_connect(client):
    """Testa conexão com Neo4j."""
    with patch("knowledge_graph_rag.graph.neo4j_client.AsyncGraphDatabase") as mock_driver:
        mock_graph_database = Mock()
        mock_driver.driver.return_value = mock_graph_database

        await client.connect()

        assert client.driver is not None
        mock_driver.driver.assert_called_once()


@pytest.mark.asyncio
async def test_close(client):
    """Testa fechamento de conexão."""
    client.driver = AsyncMock()
    client.driver.close = AsyncMock()

    await client.close()

    client.driver.close.assert_called_once()


@pytest.mark.asyncio
async def test_execute_query(client):
    """Testa execução de query."""
    client.driver = Mock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"key": "value"}]
    mock_session.run.return_value = mock_result
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    client.driver.session.return_value = mock_session

    result = await client.execute_query("MATCH (n) RETURN n")

    assert len(result) == 1
    assert result[0]["key"] == "value"


@pytest.mark.asyncio
async def test_get_component_templates(client):
    """Testa obtenção de templates de componentes."""
    with patch.object(client, "execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [
            {
                "template_id": "TPL-001",
                "template_name": "REST API",
                "description": "API template",
                "stack": "FastAPI",
            }
        ]

        results = await client.get_component_templates("API")

        assert len(results) == 1
        assert results[0]["template_id"] == "TPL-001"


@pytest.mark.asyncio
async def test_create_architecture_node(client):
    """Testa criação de nó de arquitetura."""
    with patch.object(client, "execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [{"plan_id": "PLAN-001"}]

        result = await client.create_architecture_node(
            plan_id="PLAN-001",
            architecture_type="microservices",
            components=[{"id": "comp-1", "name": "API", "stack": "FastAPI"}],
        )

        assert result == "PLAN-001"
