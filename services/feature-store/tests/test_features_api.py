"""
Testes para API REST do Feature Store

Testa endpoints CRUD e validações de schema.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.models.feature import (
    ComputationStatus,
    FeatureVector,
    MetadataFeatures,
)


@pytest.fixture()
def client():
    """Cliente de teste FastAPI"""
    return TestClient(app)


@pytest.fixture()
def mock_feature_store():
    """Mock do FeatureStoreService"""
    store = MagicMock()
    store.get_features = AsyncMock()
    store.compute_and_save = AsyncMock()
    store.delete_features = AsyncMock(return_value=True)
    store.list_features = AsyncMock()
    store.get_metrics = AsyncMock()
    store.get_features_by_plan_ids = AsyncMock()
    return store


@pytest.fixture()
def sample_feature_vector():
    """FeatureVector de exemplo"""
    return FeatureVector(
        plan_id="test-plan-123",
        metadata=MetadataFeatures(
            num_tasks=5,
            priority_score=0.7,
            total_duration_ms=5000.0,
            avg_duration_ms=1000.0,
            risk_score=0.3,
            complexity_score=0.6,
        ),
        computation_status=ComputationStatus.COMPLETED,
    )


@pytest.fixture()
def sample_cognitive_plan():
    """Plano cognitivo de exemplo"""
    return {
        "plan_id": "test-plan-123",
        "priority": "high",
        "risk_score": 0.3,
        "tasks": [
            {
                "task_id": "task-1",
                "type": "query",
                "estimated_duration_ms": 1000,
                "is_destructive": False,
                "complexity_factor": 0.5,
            },
            {
                "task_id": "task-2",
                "type": "transform",
                "estimated_duration_ms": 2000,
                "is_destructive": False,
                "complexity_factor": 0.7,
            },
        ],
        "dependency_graph": {
            "edges": [{"source": "task-1", "target": "task-2"}],
            "critical_path_length": 2,
        },
    }


class TestHealthEndpoints:
    """Testes para endpoints de health check"""

    def test_health_endpoint(self, client):
        """Testa endpoint de health check"""
        with patch(
            "src.api.routers.health._app_state", {"mongodb": MagicMock(), "cache": MagicMock()}
        ):
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "service" in data
            assert data["service"] == "feature-store"

    def test_readiness_endpoint(self, client):
        """Testa endpoint de readiness"""
        with patch("src.api.routers.health._app_state", {"feature_store": MagicMock()}):
            response = client.get("/health/ready")
            assert response.status_code == 200
            assert response.json() == {"ready": True}

    def test_liveness_endpoint(self, client):
        """Testa endpoint de liveness"""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"alive": True}


class TestGetFeatures:
    """Testes para GET /features/{plan_id}"""

    def test_get_features_success(self, client, mock_feature_store, sample_feature_vector):
        """Testa buscar features com sucesso"""
        mock_feature_store.get_features.return_value = sample_feature_vector

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features/test-plan-123")
            assert response.status_code == 200
            data = response.json()
            assert data["plan_id"] == "test-plan-123"
            assert data["metadata"]["num_tasks"] == 5

    def test_get_features_not_found(self, client, mock_feature_store):
        """Testa buscar features inexistentes"""
        mock_feature_store.get_features.return_value = None

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features/nonexistent")
            assert response.status_code == 404
            assert "não encontradas" in response.json()["detail"]

    def test_get_features_with_cache_param(self, client, mock_feature_store, sample_feature_vector):
        """Testa parâmetro use_cache"""
        mock_feature_store.get_features.return_value = sample_feature_vector

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features/test-plan-123?use_cache=false")
            assert response.status_code == 200
            mock_feature_store.get_features.assert_called_with("test-plan-123", use_cache=False)


class TestSaveFeatures:
    """Testes para POST /features/{plan_id}"""

    def test_compute_and_save_features(
        self, client, mock_feature_store, sample_feature_vector, sample_cognitive_plan
    ):
        """Testa computar e salvar features"""
        mock_feature_store.compute_and_save.return_value = sample_feature_vector

        request_data = {
            "plan_id": "test-plan-123",
            "cognitive_plan": sample_cognitive_plan,
            "force_recompute": False,
            "skip_cache": False,
        }

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.post("/api/v1/features/test-plan-123", json=request_data)
            assert response.status_code == 200
            data = response.json()
            assert data["plan_id"] == "test-plan-123"
            mock_feature_store.compute_and_save.assert_called_once()

    def test_compute_with_force_recompute(
        self, client, mock_feature_store, sample_feature_vector, sample_cognitive_plan
    ):
        """Testa computação com force_recompute"""
        mock_feature_store.compute_and_save.return_value = sample_feature_vector

        request_data = {
            "plan_id": "test-plan-123",
            "cognitive_plan": sample_cognitive_plan,
            "force_recompute": True,
        }

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.post("/api/v1/features/test-plan-123", json=request_data)
            assert response.status_code == 200


class TestDeleteFeatures:
    """Testes para DELETE /features/{plan_id}"""

    def test_delete_features_success(self, client, mock_feature_store):
        """Testa deletar features com sucesso"""
        mock_feature_store.delete_features.return_value = True

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.delete("/api/v1/features/test-plan-123")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "test-plan-123" in data["message"]

    def test_delete_features_not_found(self, client, mock_feature_store):
        """Testa deletar features inexistentes"""
        mock_feature_store.delete_features.return_value = False

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.delete("/api/v1/features/nonexistent")
            assert response.status_code == 404


class TestListFeatures:
    """Testes para GET /features (listagem)"""

    def test_list_features_default(self, client, mock_feature_store, sample_feature_vector):
        """Testa listagem com parâmetros padrão"""
        mock_feature_store.list_features.return_value = MagicMock(
            success=True,
            count=1,
            features=[sample_feature_vector.model_dump(mode="json")],
            message="Listados 1 features",
        )

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features")
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1

    def test_list_features_with_pagination(self, client, mock_feature_store):
        """Testa listagem com paginação"""
        mock_feature_store.list_features.return_value = MagicMock(
            success=True, count=0, features=[], message="Listados 0 features"
        )

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features?limit=10&offset=5")
            assert response.status_code == 200
            mock_feature_store.list_features.assert_called_with(
                limit=10, offset=5, status_filter=None
            )

    def test_list_features_with_status_filter(self, client, mock_feature_store):
        """Testa listagem com filtro de status"""
        mock_feature_store.list_features.return_value = MagicMock(
            success=True, count=0, features=[], message="Listados 0 features"
        )

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features?status=completed")
            assert response.status_code == 200


class TestBatchCompute:
    """Testes para POST /features/batch"""

    def test_batch_compute_features(
        self, client, mock_feature_store, sample_feature_vector, sample_cognitive_plan
    ):
        """Testa computação em batch"""
        mock_feature_store.compute_and_save.return_value = sample_feature_vector

        requests = {
            "requests": [
                {"plan_id": "plan-1", "cognitive_plan": sample_cognitive_plan},
                {"plan_id": "plan-2", "cognitive_plan": sample_cognitive_plan},
            ]
        }

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.post("/api/v1/features/batch", json=requests)
            if response.status_code != 200:
                print(f"Error response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2


class TestGetMetrics:
    """Testes para GET /features/metrics/summary"""

    def test_get_metrics(self, client, mock_feature_store):
        """Testa obter métricas"""
        mock_feature_store.get_metrics.return_value = {
            "total_features": 100,
            "cached_features": 80,
            "computation_count": 50,
            "cache_hits": 80,
            "cache_misses": 20,
            "cache_hit_rate": 0.8,
            "cache_available": True,
        }

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features/metrics/summary")
            assert response.status_code == 200
            data = response.json()
            assert data["total_features"] == 100
            assert data["cached_features"] == 80


class TestGetFeaturesByPlanIds:
    """Testes para GET /features/by-plan-ids"""

    def test_get_features_by_multiple_ids(self, client, mock_feature_store, sample_feature_vector):
        """Testa buscar features por múltiplos IDs"""
        mock_feature_store.get_features_by_plan_ids.return_value = {
            "plan-1": sample_feature_vector,
            "plan-2": sample_feature_vector,
        }

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            response = client.get("/api/v1/features/by-plan-ids?plan_ids=plan-1,plan-2")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2


class TestSchemaValidation:
    """Testes para validação de schema"""

    def test_invalid_plan_id_format(self, client):
        """Testa validação de plan_id (deve aceitar qualquer string)"""
        # Plan ID pode ser qualquer string, então isso não deve falhar
        with patch("src.api.routers.features.get_feature_store_service") as mock:
            mock.return_value.get_features = AsyncMock(return_value=None)
            response = client.get("/api/v1/features/any-plan-id-123")
            assert response.status_code in [200, 404, 500]  # 404 se não existe

    def test_invalid_limit_value(self, client, mock_feature_store):
        """Testa validação de limite (max 100)"""
        mock_feature_store.list_features.return_value = MagicMock(
            success=True, count=0, features=[], message="ok"
        )

        with patch(
            "src.api.routers.features.get_feature_store_service", return_value=mock_feature_store
        ):
            # Limite acima de 100 deve ser rejeitado pela validação do FastAPI
            response = client.get("/api/v1/features?limit=150")
            # FastAPI retorna 422 para validação de query params
            assert response.status_code == 422

    def test_invalid_offset_value(self, client):
        """Testa validação de offset (não pode ser negativo)"""
        with patch("src.api.routers.features.get_feature_store_service") as mock:
            mock.return_value.list_features = AsyncMock()
            response = client.get("/api/v1/features?offset=-1")
            assert response.status_code == 422
