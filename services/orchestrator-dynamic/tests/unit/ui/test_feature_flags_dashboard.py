"""
Testes unitários para Feature Flags Dashboard UI (Task 9).

Testa os endpoints da UI de administração de feature flags:
- GET /admin/feature-flags - Retornar dashboard HTML
- GET /admin/feature-flags/api/flags - Listar flags (JSON)
- POST /admin/feature-flags/api/flags/{name}/toggle - Toggle flag
- POST /admin/feature-flags/api/flags - Criar nova flag
- DELETE /admin/feature-flags/api/flags/{name} - Deletar flag
"""
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from src.ui.feature_flags_dashboard import create_dashboard_router

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
def sample_flags():
    """Dados de flags para testes."""
    return [
        {
            "flag_name": "new_workflow_engine",
            "description": "Ativa novo motor de workflows",
            "enabled": True,
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 50,
                "whitelist": ["tenant-123"],
                "namespaces": ["staging"],
                "canary_list": [],
            },
            "created_at": "2026-04-05T12:00:00Z",
            "updated_at": "2026-04-05T12:00:00Z",
            "created_by": "platform-engineer",
            "owner": "orchestrator-team",
            "tags": ["workflow", "performance"],
        },
        {
            "flag_name": "ml_v2_inference",
            "description": "Novo modelo de inferência ML v2",
            "enabled": False,
            "rollout_strategy": "canary",
            "rollout_config": {
                "percentage": 10,
                "whitelist": [],
                "namespaces": [],
                "canary_list": ["user-1", "user-2"],
            },
            "created_at": "2026-04-04T10:00:00Z",
            "updated_at": "2026-04-04T10:00:00Z",
            "created_by": "ml-engineer",
            "owner": "ml-team",
            "tags": ["ml", "inference"],
        },
    ]


# =============================================================================
# Testes GET /admin/feature-flags - Dashboard HTML
# =============================================================================


class TestDashboardEndpoint:
    """Testes do endpoint GET /admin/feature-flags."""

    def test_dashboard_returns_html(self, mock_feature_flag_service):
        """Testa se o endpoint retorna HTML válido."""
        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.get("/admin/feature-flags")

            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"].startswith("text/html")
            content = response.text
            assert "<!DOCTYPE html>" in content or "<html" in content
            assert "Feature Flags" in content or "feature flags" in content.lower()

    def test_dashboard_has_required_elements(self, mock_feature_flag_service):
        """Testa se o dashboard contém elementos HTML necessários."""
        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.get("/admin/feature-flags")

            content = response.text
            # Verificar elementos principais
            assert "<title>" in content
            # Botões de ação
            assert (
                "toggle" in content.lower()
                or "ativar" in content.lower()
                or "enable" in content.lower()
            )
            # Tabela ou lista de flags
            assert "flag" in content.lower()


# =============================================================================
# Testes GET /admin/feature-flags/api/flags - Listar flags (JSON)
# =============================================================================


class TestDashboardApiListFlags:
    """Testes do endpoint GET /admin/feature-flags/api/flags."""

    def test_list_flags_json(self, mock_feature_flag_service, sample_flags):
        """Testa listar flags em formato JSON para UI."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        mock_feature_flag_service.list_flags = AsyncMock(return_value=sample_flags)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.get("/admin/feature-flags/api/flags")

            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "application/json"
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["flag_name"] == "new_workflow_engine"
            mock_feature_flag_service.list_flags.assert_called_once()

    def test_list_flags_enabled_filter(self, mock_feature_flag_service, sample_flags):
        """Testa filtro de flags ativas."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        enabled_flags = [f for f in sample_flags if f["enabled"]]
        mock_feature_flag_service.list_flags = AsyncMock(return_value=enabled_flags)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.get("/admin/feature-flags/api/flags?enabled=true")

            assert response.status_code == status.HTTP_200_OK
            mock_feature_flag_service.list_flags.assert_called_once_with(
                enabled_only=True
            )

    def test_list_flags_empty(self, mock_feature_flag_service):
        """Testa resposta quando não há flags."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        mock_feature_flag_service.list_flags = AsyncMock(return_value=[])

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.get("/admin/feature-flags/api/flags")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data == []


# =============================================================================
# Testes POST /admin/feature-flags/api/flags/{name}/toggle - Toggle
# =============================================================================


class TestDashboardApiToggleFlag:
    """Testes do endpoint POST /admin/feature-flags/api/flags/{name}/toggle."""

    def test_toggle_flag_success(self, mock_feature_flag_service, sample_flags):
        """Testa toggle de flag com sucesso."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        flag = sample_flags[0]
        mock_feature_flag_service.get_flag = AsyncMock(
            side_effect=[flag, {**flag, "enabled": False}]
        )
        mock_feature_flag_service.set_flag = AsyncMock(
            return_value={**flag, "enabled": False}
        )

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                f"/admin/feature-flags/api/flags/{flag['flag_name']}/toggle"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["enabled"] is False
            assert data["previous_state"] is True
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_toggle_flag_not_found(self, mock_feature_flag_service):
        """Testa toggle de flag inexistente."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        mock_feature_flag_service.get_flag = AsyncMock(return_value=None)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post("/admin/feature-flags/api/flags/nonexistent/toggle")

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes POST /admin/feature-flags/api/flags - Criar flag
# =============================================================================


class TestDashboardApiCreateFlag:
    """Testes do endpoint POST /admin/feature-flags/api/flags."""

    def test_create_flag_success(self, mock_feature_flag_service):
        """Testa criar flag via UI."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        flag_data = {
            "flag_name": "test_flag",
            "description": "Test flag via UI",
            "enabled": True,
            "rollout_strategy": "all",
            "rollout_config": {},
            "created_by": "admin-ui",
            "tags": [],
        }

        mock_feature_flag_service.set_flag = AsyncMock(return_value=flag_data)
        mock_feature_flag_service.get_flag = AsyncMock(return_value=flag_data)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post("/admin/feature-flags/api/flags", json=flag_data)

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["flag_name"] == "test_flag"
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_create_flag_invalid_payload(self, mock_feature_flag_service):
        """Testa criar flag com payload inválido."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            # Sem flag_name
            response = client.post(
                "/admin/feature-flags/api/flags",
                json={"description": "test"},
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# Testes DELETE /admin/feature-flags/api/flags/{name} - Deletar flag
# =============================================================================


class TestDashboardApiDeleteFlag:
    """Testes do endpoint DELETE /admin/feature-flags/api/flags/{name}."""

    def test_delete_flag_success(self, mock_feature_flag_service):
        """Testa deletar flag com sucesso."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        mock_feature_flag_service.delete_flag = AsyncMock(return_value=True)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.delete("/admin/feature-flags/api/flags/test_flag")

            assert response.status_code == status.HTTP_204_NO_CONTENT
            mock_feature_flag_service.delete_flag.assert_called_once_with("test_flag")

    def test_delete_flag_not_found(self, mock_feature_flag_service):
        """Testa deletar flag inexistente."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        mock_feature_flag_service.delete_flag = AsyncMock(return_value=False)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.delete("/admin/feature-flags/api/flags/nonexistent")

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes UPDATE /admin/feature-flags/api/flags/{name} - Atualizar flag
# =============================================================================


class TestDashboardApiUpdateFlag:
    """Testes do endpoint PUT /admin/feature-flags/api/flags/{name}."""

    def test_update_flag_success(self, mock_feature_flag_service, sample_flags):
        """Testa atualizar flag com sucesso."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        flag = sample_flags[0]
        updated_flag = {**flag, "description": "Updated description"}
        mock_feature_flag_service.get_flag = AsyncMock(side_effect=[flag, updated_flag])
        mock_feature_flag_service.set_flag = AsyncMock(return_value=updated_flag)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.put(
                f"/admin/feature-flags/api/flags/{flag['flag_name']}",
                json={"description": "Updated description"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["description"] == "Updated description"
            mock_feature_flag_service.set_flag.assert_called_once()

    def test_update_flag_not_found(self, mock_feature_flag_service):
        """Testa atualizar flag inexistente."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        mock_feature_flag_service.get_flag = AsyncMock(return_value=None)

        app = FastAPI()
        router = create_dashboard_router(mock_feature_flag_service)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.put(
                "/admin/feature-flags/api/flags/nonexistent",
                json={"description": "test"},
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Testes de configuração
# =============================================================================


class TestDashboardConfiguration:
    """Testes de configuração do dashboard."""

    def test_dashboard_router_prefix(self, mock_feature_flag_service):
        """Testa se o router tem o prefixo correto."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        router = create_dashboard_router(mock_feature_flag_service)
        assert router.prefix == "/admin/feature-flags"

    def test_dashboard_router_tags(self, mock_feature_flag_service):
        """Testa se o router tem as tags corretas."""
        from src.ui.feature_flags_dashboard import create_dashboard_router

        router = create_dashboard_router(mock_feature_flag_service)
        assert router.tags == ["Admin UI"]
