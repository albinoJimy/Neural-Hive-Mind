"""Tests para Fluxo G integration activities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.activities.fluxo_g_integration import (
    generate_documentation,
    generate_requirements,
    query_knowledge_graph,
    request_approval,
    set_fluxo_g_dependencies,
    update_knowledge_graph,
)


@pytest.fixture()
def mock_http_client():
    """Mock do cliente HTTP."""
    client = AsyncMock()
    return client


@pytest.fixture()
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        "plan_id": "PLAN-001",
        "intent_id": "INTENT-001",
        "summary": "Sistema de autenticação",
        "description": "Implementar login e registro",
        "tasks": [
            {"task_id": "T1", "description": "Criar API de login"},
            {"task_id": "T2", "description": "Criar frontend"},
        ],
    }


@pytest.mark.asyncio()
class TestGenerateRequirements:
    """Testes para generate_requirements activity."""

    async def test_generate_requirements_success(self, mock_http_client, sample_cognitive_plan):
        """Testa geração de requisitos com sucesso."""
        from src.activities.fluxo_g_integration import set_fluxo_g_dependencies

        set_fluxo_g_dependencies(http_client=mock_http_client)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "requirements_set_id": "REQ-SET-001",
            "plan_id": "PLAN-001",
            "requirements": [
                {"id": "REQ-001", "title": "Login", "type": "functional"},
                {"id": "REQ-002", "title": "Registro", "type": "functional"},
            ],
            "user_stories": [],
        }
        mock_http_client.post.return_value = mock_response

        result = await generate_requirements(sample_cognitive_plan, "Criar login")

        assert result["requirements_set_id"] == "REQ-SET-001"
        assert result["plan_id"] == "PLAN-001"
        assert len(result["requirements"]) == 2

    async def test_generate_requirements_http_error(self, mock_http_client, sample_cognitive_plan):
        """Testa tratamento de erro HTTP."""
        set_fluxo_g_dependencies(http_client=mock_http_client)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http_client.post.return_value = mock_response

        with pytest.raises(RuntimeError, match="Falha ao gerar requisitos"):
            await generate_requirements(sample_cognitive_plan)

    async def test_generate_requirements_no_client(self, sample_cognitive_plan):
        """Testa fallback quando cliente HTTP não disponível."""
        set_fluxo_g_dependencies(http_client=None)

        result = await generate_requirements(sample_cognitive_plan)

        assert result["status"] == "stub"
        assert result["plan_id"] == "PLAN-001"


@pytest.mark.asyncio()
class TestGenerateDocumentation:
    """Testes para generate_documentation activity."""

    async def test_generate_documentation_success(self, mock_http_client, sample_cognitive_plan):
        """Testa geração de documentação com sucesso."""
        set_fluxo_g_dependencies(http_client=mock_http_client)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "documentation_id": "DOC-001",
            "plan_id": "PLAN-001",
            "readme": "# Sistema de Autenticação\n...",
            "diagrams": ["architecture"],
        }
        mock_http_client.post.return_value = mock_response

        result = await generate_documentation(sample_cognitive_plan)

        assert result["documentation_id"] == "DOC-001"
        assert result["readme"] is not None


@pytest.mark.asyncio()
class TestUpdateKnowledgeGraph:
    """Testes para update_knowledge_graph activity."""

    async def test_update_knowledge_graph_success(self, mock_http_client, sample_cognitive_plan):
        """Testa atualização do grafo com sucesso."""
        set_fluxo_g_dependencies(http_client=mock_http_client)

        # Mock responses para POST /nodes
        plan_response = MagicMock()
        plan_response.status_code = 201
        plan_response.json.return_value = {"id": "NODE-PLAN-001", "name": "Plan PLAN-001"}

        req_response = MagicMock()
        req_response.status_code = 201
        req_response.json.return_value = {"id": "NODE-REQ-001", "name": "Login"}

        rel_response = MagicMock()
        rel_response.status_code = 201
        rel_response.json.return_value = {"id": "REL-001"}

        call_count = [0]

        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if "nodes" in str(args[0]):
                if call_count[0] == 1:
                    return plan_response
                else:
                    return req_response
            elif "relations" in str(args[0]):
                return rel_response

        mock_http_client.post.side_effect = mock_post

        result = await update_knowledge_graph(
            sample_cognitive_plan,
            {"requirements": [{"id": "REQ-001", "title": "Login"}]},
            {},
        )

        assert result["nodes_created"] >= 1
        assert result["plan_node_id"] == "NODE-PLAN-001"

    async def test_update_knowledge_graph_no_client(self, sample_cognitive_plan):
        """Testa fallback sem cliente HTTP."""
        set_fluxo_g_dependencies(http_client=None)

        result = await update_knowledge_graph(sample_cognitive_plan)

        assert result["status"] == "stub"
        assert result["nodes_created"] == 0


@pytest.mark.asyncio()
class TestRequestApproval:
    """Testes para request_approval activity."""

    async def test_request_approval_success(self, mock_http_client):
        """Testa solicitação de aprovação com sucesso."""
        set_fluxo_g_dependencies(http_client=mock_http_client)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "request_id": "APPR-001",
            "status": "approved",
            "confidence_score": 0.9,
            "reasoning": "Solicitação bem estruturada",
            "requires_human_review": False,
        }
        mock_http_client.post.return_value = mock_response

        result = await request_approval(
            "requirement",
            {
                "title": "Login Requirements",
                "description": "Requisitos de login",
                "context": {"priority": "high"},
            },
            "orchestrator",
        )

        assert result["status"] == "approved"
        assert result["confidence_score"] == 0.9
        assert result["requires_human_review"] is False

    async def test_request_approval_requires_human(self, mock_http_client):
        """Testa aprovação que requer revisão humana."""
        set_fluxo_g_dependencies(http_client=mock_http_client)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "request_id": "APPR-002",
            "status": "pending",
            "confidence_score": 0.5,
            "reasoning": "Requer análise mais detalhada",
            "requires_human_review": True,
        }
        mock_http_client.post.return_value = mock_response

        result = await request_approval(
            "architecture",
            {"title": "Complex Architecture", "description": "Arquitetura complexa"},
            "orchestrator",
        )

        assert result["status"] == "pending"
        assert result["requires_human_review"] is True


@pytest.mark.asyncio()
class TestQueryKnowledgeGraph:
    """Testes para query_knowledge_graph activity."""

    async def test_query_rag_success(self, mock_http_client):
        """Testa query RAG com sucesso."""
        set_fluxo_g_dependencies(http_client=mock_http_client)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "query": "Sistemas de autenticação",
            "response": "Baseado no conhecimento existente, sistemas de autenticação...",
            "context_used": True,
        }
        mock_http_client.post.return_value = mock_response

        result = await query_knowledge_graph("Sistemas de autenticação")

        assert result["context_used"] is True
        assert "autenticação" in result["response"].lower()

    async def test_query_rag_no_client(self):
        """Testa query sem cliente HTTP."""
        set_fluxo_g_dependencies(http_client=None)

        result = await query_knowledge_graph("Test query")

        assert result["context_used"] is False
        assert "indisponível" in result["response"]
