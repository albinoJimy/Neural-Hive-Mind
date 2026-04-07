"""
Testes para ScoutAPI.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

# Import com skip automático se módulo não disponível
ScoutAPI = pytest.importorskip("src.api.scout_api").ScoutAPI


class TestScoutAPIInitialization:
    """Testes de inicialização da API."""

    def test_api_initialization(self):
        """Testa que a API é inicializada corretamente."""
        mock_orchestrator = AsyncMock()
        mock_ledger = AsyncMock()

        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)

        assert api is not None


class TestHealthEndpoint:
    """Testes do endpoint de health."""

    @pytest.fixture
    def client(self):
        mock_orchestrator = AsyncMock()
        mock_ledger = AsyncMock()
        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)
        return TestClient(api.app)

    def test_health_returns_ok(self, client):
        """Testa que health retorna status ok."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestStartExplorationEndpoint:
    """Testes do endpoint POST /explorations."""

    @pytest.fixture
    def client(self):
        mock_orchestrator = AsyncMock()
        mock_orchestrator.coordinate_exploration = AsyncMock(
            return_value={"exploration_id": "scout-exp-1", "status": "running"}
        )

        mock_ledger = AsyncMock()
        mock_ledger.save_exploration = AsyncMock(return_value={"exploration_id": "scout-exp-1"})

        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)
        return TestClient(api.app)

    def test_start_exploration_returns_id(self, client):
        """Testa que iniciar exploração retorna exploration_id."""
        response = client.post(
            "/explorations",
            json={"plan_id": "plan-1", "intent_text": "Implementar API de usuários"},
        )

        assert response.status_code == 200
        assert "exploration_id" in response.json()


class TestGetExplorationEndpoint:
    """Testes do endpoint GET /explorations/{id}."""

    @pytest.fixture
    def client(self):
        mock_orchestrator = AsyncMock()
        mock_ledger = AsyncMock()
        mock_ledger.get_exploration = AsyncMock(
            return_value={
                "exploration_id": "scout-exp-1",
                "status": "completed",
                "results": {"patterns": []},
            }
        )

        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)
        return TestClient(api.app)

    def test_get_existing_exploration(self, client):
        """Testa recuperação de exploração existente."""
        response = client.get("/explorations/scout-exp-1")

        assert response.status_code == 200
        assert response.json()["exploration_id"] == "scout-exp-1"

    def test_get_nonexistent_returns_404(self, client):
        """Testa exploração inexistente retorna 404."""
        mock_ledger = AsyncMock()
        mock_ledger.get_exploration = AsyncMock(return_value=None)

        api = ScoutAPI(scout_orchestrator=AsyncMock(), scout_ledger=mock_ledger)
        client = TestClient(api.app)

        response = client.get("/explorations/nonexistent")

        assert response.status_code == 404


class TestListExplorationsEndpoint:
    """Testes do endpoint GET /explorations."""

    @pytest.fixture
    def client(self):
        mock_orchestrator = AsyncMock()
        mock_ledger = AsyncMock()
        mock_ledger.list_explorations = AsyncMock(
            return_value=[
                {"exploration_id": "exp-1", "status": "completed"},
                {"exploration_id": "exp-2", "status": "running"},
            ]
        )

        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)
        return TestClient(api.app)

    def test_list_explorations(self, client):
        """Testa listagem de explorações."""
        response = client.get("/explorations")

        assert response.status_code == 200
        assert len(response.json()) == 2


class TestStatsEndpoint:
    """Testes do endpoint GET /stats."""

    @pytest.fixture
    def client(self):
        mock_orchestrator = AsyncMock()
        mock_ledger = AsyncMock()
        mock_ledger.get_exploration_stats = AsyncMock(
            return_value={"total": 42, "by_status": {"completed": 30, "running": 10, "failed": 2}}
        )

        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)
        return TestClient(api.app)

    def test_get_stats(self, client):
        """Testa obtenção de estatísticas."""
        response = client.get("/stats")

        assert response.status_code == 200
        assert response.json()["total"] == 42


class TestDeleteExplorationEndpoint:
    """Testes do endpoint DELETE /explorations/{id}."""

    @pytest.fixture
    def client(self):
        mock_orchestrator = AsyncMock()
        mock_ledger = AsyncMock()
        mock_ledger.delete_exploration = AsyncMock(return_value=True)

        api = ScoutAPI(scout_orchestrator=mock_orchestrator, scout_ledger=mock_ledger)
        return TestClient(api.app)

    def test_delete_existing_exploration(self, client):
        """Testa deleção de exploração existente."""
        response = client.delete("/explorations/scout-exp-1")

        assert response.status_code == 204
