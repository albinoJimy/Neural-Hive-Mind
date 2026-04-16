"""Tests para router Knowledge Graph."""

import pytest
from fastapi import testclient
from unittest.mock import AsyncMock, MagicMock, patch

from src.main import app
from src.models.knowledge import NodeType, RelationType


@pytest.fixture
def client():
    """Cliente de teste."""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def mock_rag_service():
    """Mock do serviço RAG."""
    service = MagicMock()
    service.create_node = AsyncMock()
    service.create_relation = AsyncMock()
    service.search = AsyncMock()
    service.query_with_rag = AsyncMock()

    return service


@pytest.mark.asyncio
class TestKnowledgeGraphRouter:
    """Testes para router de grafo de conhecimento."""

    def test_root_endpoint(self, client):
        """Testa endpoint raiz."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "knowledge-graph-rag"
        assert "version" in data

    def test_health_check(self, client):
        """Testa health check."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_graph_health_check(self, client):
        """Testa health check do grafo."""
        response = client.get("/api/v1/graph/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_create_node(self, client, mock_rag_service):
        """Testa criação de nó via API."""
        from src.models.knowledge import KnowledgeNode

        mock_node = KnowledgeNode(
            id="REQ:123abc",
            node_type=NodeType.REQUIREMENT,
            name="Login",
            description="Funcionalidade de login",
            properties={},
            embedding=[0.1] * 1536
        )
        mock_rag_service.create_node.return_value = mock_node

        with patch('src.api.routers.knowledge_graph.get_rag_service', return_value=mock_rag_service):
            response = client.post(
                "/api/v1/graph/nodes",
                json={
                    "node_type": "requirement",
                    "name": "Login",
                    "description": "Funcionalidade de login"
                }
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Login"
        assert data["node_type"] == "requirement"

    @pytest.mark.asyncio
    async def test_create_node_invalid_type(self, client):
        """Testa criação de nó com tipo inválido."""
        response = client.post(
            "/api/v1/graph/nodes",
            json={
                "node_type": "invalid_type",
                "name": "Test",
                "description": "Test"
            }
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_relation(self, client, mock_rag_service):
        """Testa criação de relação via API."""
        from src.models.knowledge import KnowledgeRelation

        mock_relation = KnowledgeRelation(
            id="REL:123abc",
            source_id="REQ:001",
            target_id="USR:001",
            relation_type=RelationType.IMPLEMENTS,
            properties={}
        )
        mock_rag_service.create_relation.return_value = mock_relation

        with patch('src.api.routers.knowledge_graph.get_rag_service', return_value=mock_rag_service):
            response = client.post(
                "/api/v1/graph/relations",
                json={
                    "source_id": "REQ:001",
                    "target_id": "USR:001",
                    "relation_type": "implements"
                }
            )

        assert response.status_code == 201
        data = response.json()
        assert data["source_id"] == "REQ:001"
        assert data["target_id"] == "USR:001"
        assert data["relation_type"] == "implements"

    @pytest.mark.asyncio
    async def test_search_graph(self, client, mock_rag_service):
        """Testa busca no grafo."""
        from src.models.knowledge import GraphSearchResult, KnowledgeNode

        mock_node = KnowledgeNode(
            id="DOC:001",
            node_type=NodeType.DOCUMENT,
            name="Architecture",
            description="Arquitetura"
        )
        mock_result = GraphSearchResult(
            nodes=[mock_node],
            relations=[],
            total_found=1,
            query_id="Q-search"
        )
        mock_rag_service.search.return_value = mock_result

        with patch('src.api.routers.knowledge_graph.get_rag_service', return_value=mock_rag_service):
            response = client.post(
                "/api/v1/graph/search",
                json={
                    "query_text": "arquitetura",
                    "limit": 10
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_found"] == 1
        assert len(data["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_rag_query(self, client, mock_rag_service):
        """Testa query com RAG."""
        mock_rag_service.query_with_rag.return_value = "Resposta gerada pelo LLM"

        with patch('src.api.routers.knowledge_graph.get_rag_service', return_value=mock_rag_service):
            response = client.post(
                "/api/v1/graph/rag/query",
                json={
                    "query_text": "Explique a arquitetura do sistema"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "Explique a arquitetura do sistema"
        assert "response" in data
        assert data["context_used"] is True
