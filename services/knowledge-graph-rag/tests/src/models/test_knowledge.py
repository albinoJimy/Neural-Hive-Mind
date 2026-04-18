"""Tests para modelos de conhecimento."""

import pytest
from datetime import datetime
from knowledge_graph_rag.models.knowledge import (
    NodeType,
    RelationType,
    KnowledgeNode,
    KnowledgeRelation,
    GraphQuery,
    GraphSearchResult,
    RAGContext,
)


class TestNodeType:
    """Testes para enum NodeType."""

    def test_node_type_values(self):
        """Verifica valores do enum."""
        assert NodeType.REQUIREMENT == "requirement"
        assert NodeType.USER_STORY == "user_story"
        assert NodeType.COMPONENT == "component"
        assert NodeType.DOCUMENT == "document"
        assert NodeType.DECISION == "decision"
        assert NodeType.PERSONA == "persona"


class TestRelationType:
    """Testes para enum RelationType."""

    def test_relation_type_values(self):
        """Verifica valores do enum."""
        assert RelationType.DEPENDS_ON == "depends_on"
        assert RelationType.RELATES_TO == "relates_to"
        assert RelationType.IMPLEMENTS == "implements"
        assert RelationType.DERIVES_FROM == "derives_from"
        assert RelationType.BLOCKS == "blocks"
        assert RelationType.REFINES == "refines"


class TestKnowledgeNode:
    """Testes para KnowledgeNode."""

    def test_create_minimal_node(self):
        """Cria nó mínimo."""
        node = KnowledgeNode(
            id="REQ:001",
            node_type=NodeType.REQUIREMENT,
            name="Login",
            description="Funcionalidade de login"
        )

        assert node.id == "REQ:001"
        assert node.node_type == NodeType.REQUIREMENT
        assert node.name == "Login"
        assert node.description == "Funcionalidade de login"
        assert node.properties == {}
        assert node.embedding is None
        assert isinstance(node.created_at, datetime)

    def test_create_full_node(self):
        """Cria nó completo."""
        embedding = [0.1] * 1536
        properties = {"priority": "high", "complexity": 5}

        node = KnowledgeNode(
            id="USR:123",
            node_type=NodeType.USER_STORY,
            name="Autenticação",
            description="História de autenticação",
            properties=properties,
            embedding=embedding
        )

        assert len(node.embedding) == 1536
        assert node.properties["priority"] == "high"
        assert node.properties["complexity"] == 5


class TestKnowledgeRelation:
    """Testes para KnowledgeRelation."""

    def test_create_minimal_relation(self):
        """Cria relação mínima."""
        relation = KnowledgeRelation(
            id="REL:001",
            source_id="REQ:001",
            target_id="USR:001",
            relation_type=RelationType.IMPLEMENTS
        )

        assert relation.id == "REL:001"
        assert relation.source_id == "REQ:001"
        assert relation.target_id == "USR:001"
        assert relation.relation_type == RelationType.IMPLEMENTS
        assert relation.weight == 1.0
        assert relation.properties == {}

    def test_create_weighted_relation(self):
        """Cria relação com peso customizado."""
        relation = KnowledgeRelation(
            id="REL:002",
            source_id="REQ:002",
            target_id="REQ:003",
            relation_type=RelationType.DEPENDS_ON,
            weight=0.8,
            properties={"strength": "strong"}
        )

        assert relation.weight == 0.8
        assert relation.properties["strength"] == "strong"


class TestGraphQuery:
    """Testes para GraphQuery."""

    def test_create_query(self):
        """Cria query básica."""
        query = GraphQuery(query_text="buscar login")

        assert query.query_text == "buscar login"
        assert query.limit == 10
        assert query.include_relations is True
        assert query.node_types is None

    def test_create_filtered_query(self):
        """Cria query com filtros."""
        query = GraphQuery(
            query_text="requisitos de autenticação",
            node_types=[NodeType.REQUIREMENT, NodeType.USER_STORY],
            limit=20,
            include_relations=False
        )

        assert len(query.node_types) == 2
        assert query.limit == 20
        assert query.include_relations is False


class TestGraphSearchResult:
    """Testes para GraphSearchResult."""

    def test_create_empty_result(self):
        """Cria resultado vazio."""
        result = GraphSearchResult(
            nodes=[],
            relations=[],
            total_found=0,
            query_id="Q-test"
        )

        assert result.total_found == 0
        assert len(result.nodes) == 0
        assert len(result.relations) == 0

    def test_create_result_with_data(self):
        """Cria resultado com dados."""
        node = KnowledgeNode(
            id="REQ:001",
            node_type=NodeType.REQUIREMENT,
            name="Test",
            description="Test node"
        )

        result = GraphSearchResult(
            nodes=[node],
            relations=[],
            total_found=1,
            query_id="Q-search"
        )

        assert result.total_found == 1
        assert len(result.nodes) == 1
        assert result.nodes[0].name == "Test"


class TestRAGContext:
    """Testes para RAGContext."""

    def test_create_rag_context(self):
        """Cria contexto RAG."""
        node = KnowledgeNode(
            id="DOC:001",
            node_type=NodeType.DOCUMENT,
            name="Arquitetura",
            description="Doc de arquitetura"
        )

        context = RAGContext(
            query="explain architecture",
            retrieved_nodes=[node],
            context_text="Architecture doc content",
            relevance_scores=[0.9]
        )

        assert context.query == "explain architecture"
        assert len(context.retrieved_nodes) == 1
        assert context.relevance_scores[0] == 0.9
