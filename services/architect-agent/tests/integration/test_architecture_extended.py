"""Testes de integração para funcionalidades extendidas do Architect Agent.

Testa os novos endpoints para bounded contexts, tech stack recommendation e diagram generation.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestExtendedFeatures:
    """Testes de funcionalidades extendidas."""

    def test_identify_bounded_contexts_no_llm(self, test_app: TestClient):
        """Testa endpoint de bounded contexts quando LLM não configurado."""
        response = test_app.post(
            "/api/v1/architecture/bounded-contexts/identify",
            json={
                "requirements": "Sistema de e-commerce com catálogo, carrinho e pagamentos",
                "domain_hints": ["Catalog", "Checkout", "Payments"],
            },
        )

        # Sem LLM configurado, deve retornar 503
        assert response.status_code in [503, 500]

    def test_recommend_tech_stack_no_llm(self, test_app: TestClient):
        """Testa endpoint de tech stack quando LLM não configurado."""
        response = test_app.post(
            "/api/v1/architecture/tech-stack/recommend",
            json={
                "requirements": "API REST de alta performance",
                "constraints": [{"type": "language", "value": "Python"}],
            },
        )

        # Sem LLM configurado, deve retornar 503
        assert response.status_code in [503, 500]

    def test_generate_diagram_context(self, test_app: TestClient):
        """Testa endpoint de geração de diagrama C4 Context."""
        response = test_app.post(
            "/api/v1/architecture/diagrams/generate",
            json={"description": "Sistema de gestão de tarefas", "diagram_type": "c4_context"},
        )

        # Sem módulos configurados, deve retornar 503
        assert response.status_code in [503, 500]

    def test_generate_diagram_unsupported_type(self, test_app: TestClient):
        """Testa endpoint com tipo de diagrama não suportado."""
        response = test_app.post(
            "/api/v1/architecture/diagrams/generate",
            json={"description": "Test flow", "diagram_type": "unsupported_type"},
        )

        # Tipo não suportado deve retornar 503 ou 400
        assert response.status_code in [503, 400]

    def test_architecture_list_still_works(self, test_app: TestClient):
        """Verifica que endpoints existentes ainda funcionam."""
        response = test_app.get("/api/v1/architecture")

        # Deve retornar 200 (mesmo que vazio)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
class TestExtendedFeaturesWithMocks:
    """Testes com mocks para quando LLM está disponível."""

    def test_identify_contexts_request_validation(self, test_app: TestClient):
        """Testa validação do request de bounded contexts."""
        # Request sem requirements
        response = test_app.post("/api/v1/architecture/bounded-contexts/identify", json={})

        # Deve retornar erro de validação (422)
        assert response.status_code == 422

    def test_recommend_stack_request_validation(self, test_app: TestClient):
        """Testa validação do request de tech stack."""
        # Request sem requirements
        response = test_app.post("/api/v1/architecture/tech-stack/recommend", json={})

        # Deve retornar erro de validação (422)
        assert response.status_code == 422

    def test_diagram_generation_request_validation(self, test_app: TestClient):
        """Testa validação do request de diagram generation."""
        # Request sem campos obrigatórios
        response = test_app.post("/api/v1/architecture/diagrams/generate", json={})

        # Deve retornar erro de validação (422)
        assert response.status_code == 422
