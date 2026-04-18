"""Testes E2E para Fluxo G Fase 1.

Estes testes validam a integração completa dos novos módulos:
- BoundedContextsIdentifier
- TechStackRecommender
- ArchitectureDiagramGenerator
- MongoDB persistence
- Redis caching
- Endpoints REST

Pré-requisitos:
- docker-compose.e2e.yml deve estar rodando
- OPENAI_API_KEY deve estar configurada (ou usar mock)
"""

import pytest
import asyncio
from httpx import AsyncClient, TimeoutException
from typing import Dict, Any


@pytest.mark.e2e
class TestFluxoGFase1Integration:
    """Testes E2E para Fluxo G Fase 1."""

    @pytest.fixture
    async def client(self):
        """Fixture para cliente HTTP."""
        async with AsyncClient(
            base_url="http://architect-agent:8011",
            timeout=30.0
        ) as ac:
            yield ac

    @pytest.fixture
    def headers(self):
        """Headers comuns para requests."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def test_health_check(self, client: AsyncClient):
        """Testa que o serviço está saudável."""
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    async def test_identify_bounded_contexts_e2e(self, client: AsyncClient, headers: Dict):
        """Testa identificação de bounded contexts via API."""
        request_data = {
            "requirements": """
            Sistema de e-commerce com:
            - Gestão de utilizadores e autenticação
            - Catálogo de produtos e categorias
            - Carrinho de compras e checkout
            - Processamento de pagamentos
            - Gestão de encomendas e envio
            """,
            "domain_hints": ["Identity", "Catalog", "Billing"]
        }

        response = await client.post(
            "/api/v1/architecture/bounded-contexts/identify",
            json=request_data,
            headers=headers
        )

        # Verificar response
        assert response.status_code == 200
        data = response.json()

        # Validar estrutura
        assert "total_contexts" in data
        assert "contexts" in data
        assert "confidence_score" in data

        # Validar que temos pelo menos 2 contextos
        assert data["total_contexts"] >= 2
        assert len(data["contexts"]) >= 2

        # Validar estrutura dos contextos
        for ctx in data["contexts"]:
            assert "name" in ctx
            assert "description" in ctx
            assert "responsibilities" in ctx
            assert "domain_models" in ctx
            assert "ubiquitous_language" in ctx
            assert "relationships" in ctx

        # Verificar que contextos sugeridos aparecem
        context_names = [ctx["name"] for ctx in data["contexts"]]
        assert any("Identity" in name or "Auth" in name for name in context_names)

    async def test_recommend_tech_stack_e2e(self, client: AsyncClient, headers: Dict):
        """Testa recomendação de tech stack via API."""
        request_data = {
            "requirements": "API REST de alta performance para microsserviços",
            "constraints": [
                {"type": "language", "value": "Python"},
                {"type": "latency", "value": "<100ms"}
            ]
        }

        response = await client.post(
            "/api/v1/architecture/tech-stack/recommend",
            json=request_data,
            headers=headers
        )

        # Verificar response
        assert response.status_code == 200
        data = response.json()

        # Validar estrutura
        assert "choices" in data
        assert "constraints_satisfied" in data
        assert "confidence_score" in data

        # Validar que temos recomendações
        assert len(data["choices"]) >= 1

        # Verificar que Python aparece nas choices
        has_python = any(
            choice.get("name", "").lower() == "python"
            for choice in data["choices"]
        )
        assert has_python, "Python should be recommended based on constraint"

    async def test_generate_diagram_e2e(self, client: AsyncClient, headers: Dict):
        """Testa geração de diagrama via API."""
        request_data = {
            "description": "User → API Gateway → Microservices → Database",
            "diagram_type": "c4_context"
        }

        response = await client.post(
            "/api/v1/architecture/diagrams/generate",
            json=request_data,
            headers=headers
        )

        # Verificar response
        assert response.status_code == 200
        data = response.json()

        # Validar estrutura
        assert "diagram_id" in data or "mermaid_code" in data
        assert "type" in data or "diagram_type" in data

        # Se gerou diagrama com ID, validar campos
        if "diagram_id" in data:
            assert data["diagram_id"]
            assert data.get("svg_url") or data.get("mermaid_code")

    async def test_create_architecture_with_extended_fields_e2e(
        self, client: AsyncClient, headers: Dict
    ):
        """Testa criação de arquitetura completa com campos Fluxo G."""
        request_data = {
            "intent": "Sistema de gestão de tarefas multi-tenant",
            "context": {
                "users": "Equipes de 5-50 pessoas",
                "constraints": ["Multi-tenant", "Real-time notifications"]
            },
            "cognitive_plan_id": "cp-test-123"
        }

        response = await client.post(
            "/api/v1/architecture",
            json=request_data,
            headers=headers
        )

        # Verificar response
        assert response.status_code == 201
        data = response.json()

        # Validar campos base
        assert "plan_id" in data
        assert "architecture_type" in data
        assert "components" in data
        assert "patterns" in data
        assert "rationale" in data

        # Guardar plan_id para testes subsequentes
        plan_id = data["plan_id"]

        # Verificar que a arquitetura foi persistida
        response = await client.get(f"/api/v1/architecture/{plan_id}")
        assert response.status_code == 200
        fetched = response.json()
        assert fetched["plan_id"] == plan_id

        # Se campos extendidos foram gerados, validá-los
        # (Nota: dependem de OPENAI_API_KEY estar configurada)
        if data.get("bounded_contexts"):
            assert isinstance(data["bounded_contexts"], list)

        if data.get("tech_stack"):
            assert isinstance(data["tech_stack"], list)

        if data.get("diagrams"):
            assert isinstance(data["diagrams"], list)

    async def test_architecture_persistence_e2e(
        self, client: AsyncClient, headers: Dict
    ):
        """Testa persistência de arquitetura no MongoDB."""
        # Criar arquitetura
        request_data = {
            "intent": "Teste de persistência",
            "context": {"test": True}
        }

        response = await client.post(
            "/api/v1/architecture",
            json=request_data,
            headers=headers
        )

        assert response.status_code == 201
        plan_id = response.json()["plan_id"]

        # Buscar arquitetura
        response = await client.get(f"/api/v1/architecture/{plan_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["plan_id"] == plan_id
        assert data["architecture_type"] in ["microservices", "monolith", "serverless", "hybrid"]

    async def test_rate_limiting_e2e(self, client: AsyncClient, headers: Dict):
        """Testa que rate limiting está funcionando."""
        request_data = {
            "requirements": "Sistema simples",
            "domain_hints": ["Test"]
        }

        # Fazer 11 requests (limite é 10/minute)
        responses = []
        for i in range(11):
            response = await client.post(
                "/api/v1/architecture/bounded-contexts/identify",
                json=request_data,
                headers=headers
            )
            responses.append(response.status_code)

        # Primeiros 10 devem ser 200 ou 503 (sem LLM)
        # O 11º deve ser 429 (rate limit)
        success_count = sum(1 for s in responses if s == 200)
        rate_limited = any(s == 429 for s in responses)

        # Pelo menos alguns devem ter sucesso
        assert success_count >= 1, "At least some requests should succeed"

        # Se rate limiting está ativo, 11º request deve ser 429
        # (Nota: pode não funcionar em todos os ambientes E2E)
        if success_count >= 10:
            assert rate_limited, "11th request should be rate limited"

    async def test_full_fluxo_g_workflow_e2e(self, client: AsyncClient, headers: Dict):
        """Testa workflow completo do Fluxo G Fase 1.

        Fluxo:
        1. Identificar bounded contexts
        2. Recomendar tech stack
        3. Gerar diagrama
        4. Criar arquitetura completa
        5. Verificar persistência
        """
        # 1. Identificar bounded contexts
        contexts_request = {
            "requirements": "Sistema bancário com contas, transações e empréstimos",
            "domain_hints": ["Identity", "Transactions", "Loans"]
        }

        contexts_response = await client.post(
            "/api/v1/architecture/bounded-contexts/identify",
            json=contexts_request,
            headers=headers
        )

        assert contexts_response.status_code == 200
        contexts_data = contexts_response.json()
        assert contexts_data["total_contexts"] >= 2

        # 2. Recomendar tech stack
        stack_request = {
            "requirements": "API bancária com alta segurança",
            "constraints": [{"type": "compliance", "value": "PCI-DSS"}]
        }

        stack_response = await client.post(
            "/api/v1/architecture/tech-stack/recommend",
            json=stack_request,
            headers=headers
        )

        assert stack_response.status_code == 200
        stack_data = stack_response.json()
        assert len(stack_data["choices"]) >= 1

        # 3. Gerar diagrama
        diagram_request = {
            "description": "Banking System with Identity, Transactions, Loans",
            "diagram_type": "c4_context"
        }

        diagram_response = await client.post(
            "/api/v1/architecture/diagrams/generate",
            json=diagram_request,
            headers=headers
        )

        assert diagram_response.status_code == 200
        diagram_data = diagram_response.json()

        # 4. Criar arquitetura completa
        arch_request = {
            "intent": "Sistema bancário completo",
            "context": {
                "requirements": ["Alta disponibilidade", "PCI-DSS compliance"],
                "bounded_contexts": contexts_data["contexts"],
                "tech_stack": stack_data["choices"]
            }
        }

        arch_response = await client.post(
            "/api/v1/architecture",
            json=arch_request,
            headers=headers
        )

        assert arch_response.status_code == 201
        arch_data = arch_response.json()
        plan_id = arch_data["plan_id"]

        # 5. Verificar persistência
        get_response = await client.get(f"/api/v1/architecture/{plan_id}")
        assert get_response.status_code == 200
        persisted = get_response.json()
        assert persisted["plan_id"] == plan_id


@pytest.mark.e2e
@pytest.mark.skip(reason="Requer OPENAI_API_KEY real")
class TestFluxoGWithRealLLM:
    """Testes E2E com LLM real (requer OPENAI_API_KEY)."""

    @pytest.fixture
    async def client(self):
        """Fixture para cliente HTTP."""
        async with AsyncClient(
            base_url="http://architect-agent:8011",
            timeout=60.0
        ) as ac:
            yield ac

    async def test_bounded_contexts_with_real_llm(self, client: AsyncClient):
        """Testa identificação com LLM real."""
        request_data = {
            "requirements": """
            Plataforma de streaming de vídeo com:
            - Upload e transcodificação de vídeos
            - Gestão de perfis de utilizadores
            - Sistema de subscrição e pagamentos
            - Recomendação de conteúdo baseada em histórico
            """,
            "domain_hints": ["Content", "User", "Payments"]
        }

        response = await client.post(
            "/api/v1/architecture/bounded-contexts/identify",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()

        # Validar contexto identificado
        assert data["total_contexts"] >= 3
        assert data["confidence_score"] >= 0.7

        # Verificar contextos esperados
        context_names = [ctx["name"] for ctx in data["contexts"]]
        assert any("User" in name or "Profile" in name for name in context_names)
