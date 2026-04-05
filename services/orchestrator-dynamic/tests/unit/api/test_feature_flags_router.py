"""
Testes unitários para FeatureFlagsRouter (Task 6).

Testa endpoints REST da API de Feature Flags:
- POST /api/v1/feature-flags - Criar flag
- GET /api/v1/feature-flags - Listar flags
- GET /api/v1/feature-flags/{name} - Obter flag
- PUT /api/v1/feature-flags/{name} - Atualizar flag
- DELETE /api/v1/feature-flags/{name} - Deletar flag
- POST /api/v1/feature-flags/{name}/toggle - Toggle flag
- POST /api/v1/feature-flags/{name}/evaluate - Avaliar flag
- POST /api/v1/feature-flags/batch-update - Batch update
"""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_feature_flag_service():
    """Mock do FeatureFlagService."""
    service = AsyncMock()
    service.get_flag = AsyncMock()
    service.set_flag = AsyncMock()
    service.delete_flag = AsyncMock()
    service.list_flags = AsyncMock()
    service.evaluate_flag = AsyncMock()
    return service


@pytest.fixture
def feature_flag_data():
    """Dados de uma feature flag para testes."""
    return {
        "flag_name": "new_workflow_engine",
        "description": "Ativa novo motor de workflows",
        "enabled": True,
        "rollout_strategy": "gradual",
        "rollout_config": {
            "percentage": 50,
            "whitelist": ["tenant-123", "tenant-456"],
            "namespaces": ["staging", "dev"],
            "canary_list": [],
        },
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "created_by": "platform-engineer",
        "owner": "orchestrator-team",
        "tags": ["workflow", "performance"],
    }


@pytest.fixture
def app_with_router(mock_feature_flag_service):
    """App FastAPI com router de feature flags."""
    from src.api.feature_flags import create_feature_flags_router

    app = FastAPI()
    router = create_feature_flags_router(mock_feature_flag_service)
    app.include_router(router)
    return app


# =============================================================================
# Testes POST /api/v1/feature-flags - Criar flag
# =============================================================================


class TestCreateFlagEndpoint:
    """Testes do endpoint POST /api/v1/feature-flags."""

    def test_create_flag_success(self, app_with_router, mock_feature_flag_service):
        """Testa criar flag com sucesso."""
        flag_data = {
            "flag_name": "new_workflow_engine",
            "description": "Ativa novo motor de workflows",
            "enabled": True,
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 50,
                "whitelist": ["tenant-123", "tenant-456"],
                "namespaces": ["staging", "dev"],
                "canary_list": [],
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "platform-engineer",
            "owner": "orchestrator-team",
            "tags": ["workflow"],
        }

        mock_feature_flag_service.set_flag = AsyncMock(return_value=flag_data)
        mock_feature_flag_service.get_flag = AsyncMock(return_value=flag_data)

        payload = {
            "flag_name": "new_workflow_engine",
            "description": "Ativa novo motor de workflows",
            "enabled": True,
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 50,
                "whitelist": ["tenant-123"],
                "namespaces": ["staging"],
            },
            "created_by": "platform-engineer",
            "owner": "orchestrator-team",
            "tags": ["workflow"],
        }

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags", json=payload)

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["flag_name"] == "new_workflow_engine"
            assert data["enabled"] is True
            assert data["rollout_strategy"] == "gradual"
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_create_flag_minimal_payload(self, app_with_router, mock_feature_flag_service):
        """Testa criar flag com payload mínimo."""
        minimal_data = {
            "flag_name": "minimal_flag",
            "description": None,
            "enabled": False,
            "rollout_strategy": "all",
            "rollout_config": {},
            "created_at": None,
            "updated_at": None,
            "created_by": "user",
            "owner": None,
            "tags": [],
        }

        mock_feature_flag_service.set_flag = AsyncMock(return_value=minimal_data)
        mock_feature_flag_service.get_flag = AsyncMock(return_value=minimal_data)

        with TestClient(app_with_router) as client:
            response = client.post(
                "/api/v1/feature-flags",
                json={
                    "flag_name": "minimal_flag",
                    "created_by": "user",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["flag_name"] == "minimal_flag"

    def test_create_flag_invalid_percentage(self, app_with_router):
        """Testa criar flag com percentual inválido."""
        with TestClient(app_with_router) as client:
            response = client.post(
                "/api/v1/feature-flags",
                json={
                    "flag_name": "invalid_flag",
                    "created_by": "user",
                    "rollout_config": {"percentage": 150},  # Inválido > 100
                },
            )

            # Pydantic valida automaticamente
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# Testes GET /api/v1/feature-flags - Listar flags
# =============================================================================


class TestListFlagsEndpoint:
    """Testes do endpoint GET /api/v1/feature-flags."""

    def test_list_flags_all(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa listar todas as flags."""
        mock_feature_flag_service.list_flags = AsyncMock(return_value=[feature_flag_data])

        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["flag_name"] == "new_workflow_engine"
            mock_feature_flag_service.list_flags.assert_called_once_with(enabled_only=False)

    def test_list_flags_enabled_only(self, app_with_router, mock_feature_flag_service):
        """Testa listar apenas flags ativas."""
        mock_feature_flag_service.list_flags = AsyncMock(return_value=[])

        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags?enabled=true")

            assert response.status_code == status.HTTP_200_OK
            mock_feature_flag_service.list_flags.assert_called_once_with(enabled_only=True)

    def test_list_flags_disabled_only(self, app_with_router, mock_feature_flag_service):
        """Testa listar todas as flags quando enabled=false."""
        mock_feature_flag_service.list_flags = AsyncMock(return_value=[])

        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags?enabled=false")

            assert response.status_code == status.HTTP_200_OK
            # enabled=false passa enabled_only=False para o serviço (listar todas, sem filtro)
            mock_feature_flag_service.list_flags.assert_called_once_with(enabled_only=False)

    def test_list_flags_with_limit(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa listar flags com limite."""
        # Retornar 10 flags
        flags = [{**feature_flag_data, "flag_name": f"flag_{i}"} for i in range(10)]
        mock_feature_flag_service.list_flags = AsyncMock(return_value=flags)

        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags?limit=5")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data) == 5

    def test_list_flags_invalid_limit(self, app_with_router):
        """Testa listar flags com limite inválido."""
        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags?limit=0")

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# Testes GET /api/v1/feature-flags/{name} - Obter flag
# =============================================================================


class TestGetFlagEndpoint:
    """Testes do endpoint GET /api/v1/feature-flags/{name}."""

    def test_get_flag_success(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa obter flag com sucesso."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=feature_flag_data)

        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags/new_workflow_engine")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["flag_name"] == "new_workflow_engine"
            assert data["enabled"] is True
            mock_feature_flag_service.get_flag.assert_called_once_with("new_workflow_engine")

    def test_get_flag_not_found(self, app_with_router, mock_feature_flag_service):
        """Testa obter flag inexistente."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=None)

        with TestClient(app_with_router) as client:
            response = client.get("/api/v1/feature-flags/nonexistent")

            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "não encontrada" in response.json()["detail"]


# =============================================================================
# Testes PUT /api/v1/feature-flags/{name} - Atualizar flag
# =============================================================================


class TestUpdateFlagEndpoint:
    """Testes do endpoint PUT /api/v1/feature-flags/{name}."""

    def test_update_flag_enabled(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa atualizar estado da flag."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=feature_flag_data)
        mock_feature_flag_service.set_flag = AsyncMock(return_value=feature_flag_data)

        updated_data = {**feature_flag_data, "enabled": False}
        mock_feature_flag_service.get_flag = AsyncMock(return_value=updated_data)

        with TestClient(app_with_router) as client:
            response = client.put(
                "/api/v1/feature-flags/new_workflow_engine",
                json={"enabled": False},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["enabled"] is False
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_update_flag_description(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa atualizar descrição da flag."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=feature_flag_data)
        mock_feature_flag_service.set_flag = AsyncMock(return_value=feature_flag_data)

        with TestClient(app_with_router) as client:
            response = client.put(
                "/api/v1/feature-flags/new_workflow_engine",
                json={"description": "Nova descrição"},
            )

            assert response.status_code == status.HTTP_200_OK
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_update_flag_rollout_config(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa atualizar configuração de rollout."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=feature_flag_data)
        mock_feature_flag_service.set_flag = AsyncMock(return_value=feature_flag_data)

        with TestClient(app_with_router) as client:
            response = client.put(
                "/api/v1/feature-flags/new_workflow_engine",
                json={"rollout_config": {"percentage": 75}},
            )

            assert response.status_code == status.HTTP_200_OK
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_update_flag_not_found(self, app_with_router, mock_feature_flag_service):
        """Testa atualizar flag inexistente."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=None)

        with TestClient(app_with_router) as client:
            response = client.put(
                "/api/v1/feature-flags/nonexistent",
                json={"enabled": True},
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes DELETE /api/v1/feature-flags/{name} - Deletar flag
# =============================================================================


class TestDeleteFlagEndpoint:
    """Testes do endpoint DELETE /api/v1/feature-flags/{name}."""

    def test_delete_flag_success(self, app_with_router, mock_feature_flag_service):
        """Testa deletar flag com sucesso."""
        mock_feature_flag_service.delete_flag = AsyncMock(return_value=True)

        with TestClient(app_with_router) as client:
            response = client.delete("/api/v1/feature-flags/test_flag")

            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert response.content == b""
            mock_feature_flag_service.delete_flag.assert_called_once_with("test_flag")

    def test_delete_flag_not_found(self, app_with_router, mock_feature_flag_service):
        """Testa deletar flag inexistente."""
        mock_feature_flag_service.delete_flag = AsyncMock(return_value=False)

        with TestClient(app_with_router) as client:
            response = client.delete("/api/v1/feature-flags/nonexistent")

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes POST /api/v1/feature-flags/{name}/evaluate - Avaliar flag
# =============================================================================


class TestEvaluateFlagEndpoint:
    """Testes do endpoint POST /api/v1/feature-flags/{name}/evaluate."""

    def test_evaluate_flag_enabled(self, app_with_router, mock_feature_flag_service, feature_flag_data):
        """Testa avaliar flag ativa."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=feature_flag_data)
        mock_feature_flag_service.evaluate_flag = AsyncMock(return_value=True)

        context = {"tenant_id": "tenant-123", "namespace": "staging"}

        with TestClient(app_with_router) as client:
            response = client.post(
                "/api/v1/feature-flags/new_workflow_engine/evaluate",
                json=context,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["result"] is True
            assert data["flag_name"] == "new_workflow_engine"
            mock_feature_flag_service.evaluate_flag.assert_called_once_with("new_workflow_engine", context)

    def test_evaluate_flag_disabled(self, app_with_router, mock_feature_flag_service):
        """Testa avaliar flag desativada."""
        disabled_flag = {
            "flag_name": "new_workflow_engine",
            "description": "Ativa novo motor de workflows",
            "enabled": False,
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 50,
                "whitelist": ["tenant-123", "tenant-456"],
                "namespaces": ["staging", "dev"],
                "canary_list": [],
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "platform-engineer",
            "owner": "orchestrator-team",
            "tags": ["workflow", "performance"],
        }
        mock_feature_flag_service.get_flag = AsyncMock(return_value=disabled_flag)
        mock_feature_flag_service.evaluate_flag = AsyncMock(return_value=False)

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/new_workflow_engine/evaluate")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["result"] is False
            assert data["enabled"] is False

    def test_evaluate_flag_not_found(self, app_with_router, mock_feature_flag_service):
        """Testa avaliar flag inexistente."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=None)

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/nonexistent/evaluate")

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes POST /api/v1/feature-flags/{name}/toggle - Toggle flag
# =============================================================================


class TestToggleFlagEndpoint:
    """Testes do endpoint POST /api/v1/feature-flags/{name}/toggle."""

    def test_toggle_flag_enable(self, app_with_router, mock_feature_flag_service):
        """Testa ativar flag via toggle."""
        disabled_flag = {
            "flag_name": "test_flag",
            "description": "Test flag",
            "enabled": False,
            "rollout_strategy": "all",
            "rollout_config": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "test",
            "tags": [],
        }
        enabled_flag = {**disabled_flag, "enabled": True}

        mock_feature_flag_service.get_flag = AsyncMock(side_effect=[disabled_flag, enabled_flag])
        mock_feature_flag_service.set_flag = AsyncMock(return_value=enabled_flag)

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/test_flag/toggle")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["enabled"] is True
            assert data["previous_state"] is False
            assert "ativada" in data["message"].lower()

    def test_toggle_flag_disable(self, app_with_router, mock_feature_flag_service):
        """Testa desativar flag via toggle."""
        enabled_flag = {
            "flag_name": "test_flag",
            "description": "Test flag",
            "enabled": True,
            "rollout_strategy": "all",
            "rollout_config": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "test",
            "tags": [],
        }
        disabled_flag = {**enabled_flag, "enabled": False}

        mock_feature_flag_service.get_flag = AsyncMock(side_effect=[enabled_flag, disabled_flag])
        mock_feature_flag_service.set_flag = AsyncMock(return_value=disabled_flag)

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/test_flag/toggle")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["enabled"] is False
            assert data["previous_state"] is True
            assert "desativada" in data["message"].lower()

    def test_toggle_flag_not_found(self, app_with_router, mock_feature_flag_service):
        """Testa toggle de flag inexistente."""
        mock_feature_flag_service.get_flag = AsyncMock(return_value=None)

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/nonexistent/toggle")

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes POST /api/v1/feature-flags/batch-update - Batch update
# =============================================================================


class TestBatchUpdateEndpoint:
    """Testes do endpoint POST /api/v1/feature-flags/batch-update."""

    def test_batch_update_all_success(self, app_with_router, mock_feature_flag_service):
        """Testa batch update com todas atualizações bem-sucedidas."""
        flag_data = {
            "flag_name": "test",
            "description": "Test",
            "enabled": True,
            "rollout_strategy": "all",
            "rollout_config": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "test",
            "tags": [],
        }
        mock_feature_flag_service.get_flag = AsyncMock(return_value=flag_data)
        mock_feature_flag_service.set_flag = AsyncMock(return_value=flag_data)

        payload = {
            "updates": [
                {"flag_name": "flag_1", "enabled": True},
                {"flag_name": "flag_2", "enabled": False},
                {"flag_name": "flag_3", "rollout_strategy": "all"},
            ]
        }

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/batch-update", json=payload)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_updated"] == 3
            assert data["total_failed"] == 0
            assert len(data["updated"]) == 3
            assert len(data["failed"]) == 0

    def test_batch_update_invalid_payload(self, app_with_router):
        """Testa batch update com payload inválido."""
        with TestClient(app_with_router) as client:
            # Sem campo 'updates'
            response = client.post("/api/v1/feature-flags/batch-update", json={})

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_batch_update_too_many_updates(self, app_with_router):
        """Testa batch update com mais que 50 atualizações."""
        updates = [{"flag_name": f"flag_{i}", "enabled": True} for i in range(51)]

        with TestClient(app_with_router) as client:
            response = client.post("/api/v1/feature-flags/batch-update", json={"updates": updates})

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


    def test_batch_update_partial_failure(self, app_with_router, mock_feature_flag_service):
        """Testa batch update com falhas parciais."""
        # Flag data para flag_1
        flag_data = {
            "flag_name": "flag_1",
            "description": "Test flag",
            "enabled": True,
            "rollout_strategy": "all",
            "rollout_config": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "test",
            "tags": [],
        }

        def get_flag_side_effect(name):
            return flag_data if name == "flag_1" else None

        mock_feature_flag_service.get_flag = AsyncMock(side_effect=get_flag_side_effect)
        mock_feature_flag_service.set_flag = AsyncMock(return_value=flag_data)
