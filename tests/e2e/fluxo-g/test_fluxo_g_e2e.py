"""Testes E2E para Fluxo G (Idea → Software)."""

import asyncio
import pytest
import httpx
from datetime import datetime
from typing import AsyncGenerator


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Cliente HTTP para testes."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.mark.e2e
@pytest.mark.fluxo_g
class TestFluxoGE2E:
    """Testes E2E do Fluxo G."""

    @pytest.mark.asyncio
    async def test_fluxo_g_complete_flow(self, http_client: httpx.AsyncClient):
        """
        Testa o fluxo completo do Fluxo G.

        1. Requisitos são gerados
        2. Documentação é gerada
        3. Grafo de conhecimento é atualizado
        4. Aprovações são processadas
        5. Query RAG funciona
        """
        # Dados de entrada
        cognitive_plan = {
            "plan_id": f"E2E-PLAN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "intent_id": "E2E-INTENT-001",
            "summary": "Sistema de E-commerce",
            "description": "Plataforma de e-commerce com catálogo e checkout",
        }

        # G1: Requirements
        response = await http_client.post(
            "http://localhost:8010/api/v1/requirements/from-plan",
            json={
                "plan_id": cognitive_plan["plan_id"],
                "plan_text": str(cognitive_plan),
                "generate_user_stories": True,
            },
        )
        assert response.status_code == 200
        requirements_data = response.json()
        assert "requirements_set_id" in requirements_data

        # G2: Documentation
        response = await http_client.post(
            "http://localhost:8014/api/v1/docs/generate",
            json={
                "plan_id": cognitive_plan["plan_id"],
                "include_readme": True,
                "include_diagrams": True,
            },
        )
        assert response.status_code == 200
        docs_data = response.json()
        assert "documentation_id" in docs_data

        # G3: Knowledge Graph
        response = await http_client.post(
            "http://localhost:8016/api/v1/graph/nodes",
            json={
                "node_type": "epic",
                "name": f"E2E Test {cognitive_plan['plan_id']}",
                "description": cognitive_plan["summary"],
            },
        )
        assert response.status_code == 201
        node_data = response.json()
        assert "id" in node_data

        # G4: Approval
        response = await http_client.post(
            "http://localhost:8017/api/v1/approvals/request",
            json={
                "type": "requirement",
                "title": f"E2E Test Approval {cognitive_plan['plan_id']}",
                "description": "Teste E2E de aprovação",
                "requested_by": "e2e-test",
            },
        )
        assert response.status_code == 201
        approval_data = response.json()
        assert "request_id" in approval_data

        # G5: RAG Query
        response = await http_client.post(
            "http://localhost:8016/api/v1/graph/rag/query",
            json={"query_text": "Sistema de e-commerce"},
        )
        assert response.status_code == 200
        rag_data = response.json()
        assert "response" in rag_data

    @pytest.mark.asyncio
    async def test_orchestrator_integration(self, http_client: httpx.AsyncClient):
        """
        Testa integração do orchestrator com novos serviços.
        """
        # Verificar health do orchestrator
        response = await http_client.get("http://localhost:8003/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_metrics(self, http_client: httpx.AsyncClient):
        """
        Testa se o dashboard consegue coletar métricas.
        """
        # Metrics endpoint
        response = await http_client.get("http://localhost:8018/api/metrics")
        assert response.status_code == 200
        metrics = response.json()
        assert "total_workflows" in metrics

        # Workflows list
        response = await http_client.get("http://localhost:8018/api/workflows?limit=5")
        assert response.status_code == 200
        workflows = response.json()
        assert "workflows" in workflows

        # Approvals pending
        response = await http_client.get("http://localhost:8018/api/approvals/pending")
        assert response.status_code == 200
        approvals = response.json()
        assert "approvals" in approvals

    @pytest.mark.asyncio
    async def test_service_discovery(self, http_client: httpx.AsyncClient):
        """
        Testa se todos os serviços estão acessíveis.
        """
        services = {
            "requirements-engineering": 8010,
            "documentation-generation": 8014,
            "knowledge-graph-rag": 8016,
            "approval-gateway": 8017,
            "fluxo-g-dashboard": 8018,
        }

        for service, port in services.items():
            response = await http_client.get(f"http://localhost:{port}/health")
            assert response.status_code == 200, f"{service} not healthy"


@pytest.mark.e2e
@pytest.mark.fluxo_g
class TestFluxoGPerformance:
    """Testes de performance para Fluxo G."""

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, http_client: httpx.AsyncClient):
        """
        Testa se o sistema suporta requisições concorrentes.
        """

        async def single_request():
            response = await http_client.get("http://localhost:8018/api/metrics")
            return response.status_code

        # Executar 10 requisições concorrentes
        results = await asyncio.gather(*[single_request() for _ in range(10)])

        # Todas devem ter sucesso
        assert all(r == 200 for r in results)

    @pytest.mark.asyncio
    async def test_response_time(self, http_client: httpx.AsyncClient):
        """
        Testa tempo de resposta dos serviços.
        """
        import time

        start = time.time()
        response = await http_client.get("http://localhost:8018/api/metrics")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 2.0, f"Response time too slow: {duration:.2f}s"
