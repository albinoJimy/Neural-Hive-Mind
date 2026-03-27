"""Testes E2E para fluxo de arquitetura do Architect Agent.

Este módulo testa o fluxo completo de criação e consulta de planos de arquitetura,
incluindo integração com MongoDB e validação via API.
"""
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from src.models.architecture import ArchitectureType


@pytest.mark.integration
class TestArchitectureFlow:
    """Testes de fluxo completo de arquitetura."""

    def test_create_architecture_success(self, test_app: TestClient, sample_cognitive_plan):
        """Testa criação bem-sucedida de plano de arquitetura via API."""
        response = test_app.post(
            "/api/v1/architecture",
            json={
                "intent": sample_cognitive_plan["intent"]["action"],
                "context": sample_cognitive_plan["intent"]["context"],
                "cognitive_plan_id": sample_cognitive_plan["plan_id"],
            }
        )

        assert response.status_code == 201
        data = response.json()

        assert "plan_id" in data
        assert data["cognitive_plan_id"] == sample_cognitive_plan["plan_id"]
        assert data["architecture_type"] in ["microservices", "monolith", "serverless", "hybrid"]
        assert isinstance(data["components"], list)
        assert len(data["components"]) > 0
        assert isinstance(data["patterns"], list)

    def test_create_architecture_without_cognitive_plan_id(self, test_app: TestClient):
        """Testa criação de plano sem ID de plano cognitivo."""
        response = test_app.post(
            "/api/v1/architecture",
            json={
                "intent": "design user authentication system",
                "context": {"requirements": ["oauth2", "jwt"]},
            }
        )

        assert response.status_code == 201
        data = response.json()

        assert "plan_id" in data
        assert data["cognitive_plan_id"] is None

    def test_create_architecture_invalid_input(self, test_app: TestClient):
        """Testa criação de plano com entrada inválida."""
        response = test_app.post(
            "/api/v1/architecture",
            json={
                "intent": "",  # Intent vazio
            }
        )

        assert response.status_code == 422  # Validation error

    def test_get_architecture_by_id(self, test_app: TestClient, sample_cognitive_plan):
        """Testa recuperação de plano por ID."""
        # Primeiro criar
        create_response = test_app.post(
            "/api/v1/architecture",
            json={
                "intent": sample_cognitive_plan["intent"]["action"],
                "context": sample_cognitive_plan["intent"]["context"],
                "cognitive_plan_id": sample_cognitive_plan["plan_id"],
            }
        )
        plan_id = create_response.json()["plan_id"]

        # Depois recuperar
        response = test_app.get(f"/api/v1/architecture/{plan_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["plan_id"] == plan_id
        assert "components" in data

    def test_get_architecture_not_found(self, test_app: TestClient):
        """Testa recuperação de plano inexistente."""
        response = test_app.get("/api/v1/architecture/non-existent-plan-id")

        assert response.status_code == 404

    def test_list_architectures(self, test_app: TestClient):
        """Testa listagem de planos de arquitetura."""
        # Criar alguns planos
        for i in range(3):
            test_app.post(
                "/api/v1/architecture",
                json={
                    "intent": f"design service {i}",
                    "context": {"index": i},
                }
            )

        # Listar
        response = test_app.get("/api/v1/architecture")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 3

    def test_list_architectures_by_type(self, test_app: TestClient):
        """Testa listagem filtrada por tipo de arquitetura."""
        # Criar planos com tipos específicos (pode variar)
        test_app.post(
            "/api/v1/architecture",
            json={"intent": "design microservice api", "context": {"style": "microservices"}},
        )

        # Listar por tipo
        response = test_app.get("/api/v1/architecture?architecture_type=microservices&limit=10")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        for plan in data:
            assert plan["architecture_type"] == "microservices"

    def test_list_architectures_with_limit(self, test_app: TestClient):
        """Testa listagem com limite de resultados."""
        response = test_app.get("/api/v1/architecture?limit=2")

        assert response.status_code == 200
        data = response.json()

        assert len(data) <= 2


@pytest.mark.integration
class TestArchitecturePersistence:
    """Testes de persistência de planos de arquitetura."""

    async def test_architecture_persisted_to_mongodb(
        self, test_app: TestClient, mongo_database, sample_cognitive_plan
    ):
        """Testa que plano é persistido no MongoDB."""
        # Criar via API
        response = test_app.post(
            "/api/v1/architecture",
            json={
                "intent": sample_cognitive_plan["intent"]["action"],
                "context": sample_cognitive_plan["intent"]["context"],
                "cognitive_plan_id": sample_cognitive_plan["plan_id"],
            }
        )
        plan_id = response.json()["plan_id"]

        # Verificar no MongoDB
        from src.config.settings import get_settings
        settings = get_settings()
        collection = mongo_database[settings.mongodb.collection_architecture]

        doc = await collection.find_one({"plan_id": plan_id})

        assert doc is not None
        assert doc["plan_id"] == plan_id
        assert "architecture_type" in doc
        assert "components" in doc

    async def test_architecture_retrieved_from_mongodb(
        self, architecture_repository, sample_architecture_plan
    ):
        """Testa recuperação de plano do MongoDB."""
        # Persistir diretamente
        await architecture_repository.create(sample_architecture_plan)

        # Recuperar
        retrieved = await architecture_repository.get_by_plan_id(sample_architecture_plan.plan_id)

        assert retrieved is not None
        assert retrieved.plan_id == sample_architecture_plan.plan_id
        assert retrieved.architecture_type == sample_architecture_plan.architecture_type
        assert len(retrieved.components) == len(sample_architecture_plan.components)

    async def test_architecture_list_from_mongodb(
        self, architecture_repository, sample_architecture_plan
    ):
        """Testa listagem de planos do MongoDB."""
        # Criar planos
        for i in range(5):
            plan = sample_architecture_plan.model_copy(
                update={"plan_id": f"arch-list-test-{i}"}
            )
            await architecture_repository.create(plan)

        # Listar
        plans = await architecture_repository.list_all(limit=10)

        assert len(plans) >= 5

    async def test_architecture_list_by_type(
        self, architecture_repository, sample_architecture_plan
    ):
        """Testa listagem por tipo de arquitetura."""
        # Criar planos do mesmo tipo
        for i in range(3):
            plan = sample_architecture_plan.model_copy(
                update={
                    "plan_id": f"arch-type-test-{i}",
                    "architecture_type": ArchitectureType.MICROSERVICES,
                }
            )
            await architecture_repository.create(plan)

        # Listar por tipo
        plans = await architecture_repository.list_by_type(ArchitectureType.MICROSERVICES, limit=10)

        assert len(plans) >= 3
        for plan in plans:
            assert plan.architecture_type == ArchitectureType.MICROSERVICES


@pytest.mark.integration
class TestArchitectureIntegration:
    """Testes de integração com outros serviços."""

    def test_health_check_live(self, test_app: TestClient):
        """Testa health check de liveness."""
        response = test_app.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_health_check_ready(self, test_app: TestClient):
        """Testa health check de readiness."""
        response = test_app.get("/health/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    def test_metrics_endpoint(self, test_app: TestClient):
        """Testa endpoint de métricas Prometheus."""
        response = test_app.get("/metrics")

        assert response.status_code == 200
        content = response.text
        assert "PROCESS_TIME" in content or "process_time" in content.lower()
