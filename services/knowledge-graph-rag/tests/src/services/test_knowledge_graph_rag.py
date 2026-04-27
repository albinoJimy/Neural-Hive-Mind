"""Tests para KnowledgeGraphRAG service."""

import pytest
from unittest.mock import AsyncMock, patch
from knowledge_graph_rag.models.knowledge import (
    NodeType,
    RelationType,
    GraphQuery,
    KnowledgeNode,
)
from knowledge_graph_rag.services.knowledge_graph_rag import KnowledgeGraphRAG


@pytest.mark.asyncio
class TestKnowledgeGraphRAG:
    """Testes para KnowledgeGraphRAG."""

    async def test_create_node(self, mock_llm_client):
        """Testa criação de nó."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        node = await service.create_node(
            node_type=NodeType.REQUIREMENT,
            name="Login Functionality",
            description="Sistema deve permitir login via email e senha",
            properties={"priority": "high", "complexity": 5},
        )

        assert node.node_type == NodeType.REQUIREMENT
        assert node.name == "Login Functionality"
        assert node.description == "Sistema deve permitir login via email e senha"
        assert node.properties["priority"] == "high"
        assert node.properties["complexity"] == 5
        assert node.id.startswith("REQUIREMENT:")
        assert len(node.embedding) == 1536

    async def test_create_relation(self, mock_llm_client):
        """Testa criação de relação."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        relation = await service.create_relation(
            source_id="REQ:001",
            target_id="USR:001",
            relation_type=RelationType.IMPLEMENTS,
            properties={"confidence": 0.9},
        )

        assert relation.source_id == "REQ:001"
        assert relation.target_id == "USR:001"
        assert relation.relation_type == RelationType.IMPLEMENTS
        assert relation.properties["confidence"] == 0.9
        assert relation.id.startswith("REL:")

    async def test_search_empty_result(self, mock_llm_client):
        """Testa busca com resultado vazio."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        query = GraphQuery(query_text="busca por algo inexistente")
        result = await service.search(query)

        assert result.total_found == 0
        assert len(result.nodes) == 0
        assert len(result.relations) == 0

    async def test_generate_rag_context(self, mock_llm_client):
        """Testa geração de contexto RAG."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        nodes = [
            KnowledgeNode(
                id="REQ:001",
                node_type=NodeType.REQUIREMENT,
                name="Login",
                description="Requisito de login",
                properties={"priority": "high"},
            ),
            KnowledgeNode(
                id="USR:001",
                node_type=NodeType.USER_STORY,
                name="Auth Story",
                description="História de autenticação",
                properties={"story_points": 5},
            ),
        ]

        context = await service.generate_rag_context(
            query="autenticação e login", retrieved_nodes=nodes
        )

        assert context.query == "autenticação e login"
        assert len(context.retrieved_nodes) == 2
        assert len(context.relevance_scores) == 2
        assert "**Login**" in context.context_text
        assert "**Auth Story**" in context.context_text

    async def test_query_with_rag_no_results(self, mock_llm_client):
        """Testa query RAG sem resultados."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        response = await service.query_with_rag("query sem resultados")

        assert "Nenhum resultado encontrado" in response

    async def test_query_with_rag_with_results(self, mock_llm_client):
        """Testa query RAG com resultados."""
        # Primeiro criar um nó para ter resultados
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        # Mock search para retornar um nó
        with patch.object(service, "search", new_callable=AsyncMock) as mock_search:
            node = KnowledgeNode(
                id="DOC:001",
                node_type=NodeType.DOCUMENT,
                name="Architecture",
                description="Arquitetura do sistema",
                embedding=[0.1] * 1536,
            )
            from knowledge_graph_rag.models.knowledge import GraphSearchResult

            mock_search.return_value = GraphSearchResult(
                nodes=[node], relations=[], total_found=1, query_id="Q-test"
            )

            response = await service.query_with_rag("explique a arquitetura")

            assert response == "Resposta de teste"
            mock_llm_client.generate.assert_called_once()

    async def test_generate_embedding(self, mock_llm_client):
        """Testa geração de embedding."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        embedding = await service._generate_embedding("texto de teste")

        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)

    async def test_generate_embedding_failure(self, mock_llm_client):
        """Testa fallback quando embedding falha."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        # Patch para simular erro na API OpenAI (embeddings ainda usam AsyncOpenAI)
        with patch("openai.AsyncOpenAI") as mock_openai_class:
            from unittest.mock import Mock

            mock_instance = Mock()
            mock_embeddings = Mock()
            mock_embeddings.create = AsyncMock(side_effect=Exception("API error"))
            mock_instance.embeddings = mock_embeddings
            mock_openai_class.return_value = mock_instance

            embedding = await service._generate_embedding("texto")

            # Deve retornar embedding zero
            assert embedding == [0.0] * 1536


class TestKnowledgeGraphRAGSync:
    """Testes síncronos para KnowledgeGraphRAG."""

    def test_calculate_relevance_exact_match(self, mock_llm_client):
        """Testa cálculo de relevância com match exato."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        node = KnowledgeNode(
            id="REQ:001",
            node_type=NodeType.REQUIREMENT,
            name="autenticação",
            description="Sistema de autenticação",
        )

        score = service._calculate_relevance("preciso de autenticação", node)

        assert score >= 0.5  # Match exato no nome

    def test_calculate_relevance_no_match(self, mock_llm_client):
        """Testa cálculo de relevância sem match."""
        service = KnowledgeGraphRAG(llm_client=mock_llm_client)

        node = KnowledgeNode(
            id="REQ:001",
            node_type=NodeType.REQUIREMENT,
            name="pagamento",
            description="Sistema de pagamentos",
        )

        score = service._calculate_relevance("autenticação de usuários", node)

        # Sem match exato, score deve ser baixo (< 0.2)
        assert score < 0.2
