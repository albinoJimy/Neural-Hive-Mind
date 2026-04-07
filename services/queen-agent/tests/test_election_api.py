"""
Testes de API REST para Leader Election

Testa endpoints de consulta de estado da eleição.
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock

from src.services.leader_election import NodeRole, ElectionState


@pytest.fixture
def mock_app_state():
    """Mock app state"""
    state = MagicMock()
    state.leader_election = MagicMock()
    state.leader_election.node_id = "test-node-1"
    state.leader_election.is_running = True
    state.leader_election.get_state = MagicMock(
        return_value=ElectionState(role=NodeRole.LEADER, leader_id="test-node-1", term=1)
    )
    state.leader_election.get_leader_metadata = AsyncMock(
        return_value={"node_id": "test-node-1", "term": "1", "acquired_at": "2024-01-01T00:00:00"}
    )
    state.leader_election.get_leader_heartbeat = AsyncMock(
        return_value={"node_id": "test-node-1", "timestamp": "2024-01-01T00:00:00"}
    )
    state.leader_election.is_leader = MagicMock(return_value=True)
    state.leader_election._resign_leadership = AsyncMock()
    return state


@pytest.fixture
def app(mock_app_state):
    """Fixture FastAPI app"""
    from fastapi import FastAPI
    from src.api.election import router

    app = FastAPI()
    app.state.app_state = mock_app_state
    app.include_router(router)
    return app


class TestElectionStatusEndpoint:
    """Testes do endpoint /api/v1/election/status"""

    @pytest.mark.asyncio
    async def test_get_election_status_leader(self, app, async_client: AsyncClient):
        """Testa obtenção de status quando é líder"""
        app.state.app_state.leader_election.get_state.return_value = ElectionState(
            role=NodeRole.LEADER, leader_id="test-node-1", term=1
        )

        response = await async_client.get("/api/v1/election/status")

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "leader"
        assert data["is_leader"] is True
        assert data["term"] == 1

    @pytest.mark.asyncio
    async def test_get_election_status_follower(self, app, async_client: AsyncClient):
        """Testa obtenção de status quando é follower"""
        app.state.app_state.leader_election.get_state.return_value = ElectionState(
            role=NodeRole.FOLLOWER, leader_id="other-node", term=1
        )

        response = await async_client.get("/api/v1/election/status")

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "follower"
        assert data["is_leader"] is False
        assert data["leader_id"] == "other-node"

    @pytest.mark.asyncio
    async def test_get_election_status_disabled(self, app, async_client: AsyncClient):
        """Testa resposta quando election está desabilitado"""
        app.state.app_state.leader_election = None

        response = await async_client.get("/api/v1/election/status")

        assert response.status_code == 503


class TestLeaderInfoEndpoint:
    """Testes do endpoint /api/v1/election/leader"""

    @pytest.mark.asyncio
    async def test_get_leader_info(self, async_client: AsyncClient):
        """Testa obtenção de informações do líder"""
        response = await async_client.get("/api/v1/election/leader")

        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "test-node-1"
        assert data["term"] == 1
        assert data["acquired_at"] == "2024-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_get_leader_info_no_leader(self, app, async_client: AsyncClient):
        """Testa resposta quando não há líder"""
        app.state.app_state.leader_election.get_leader_metadata = AsyncMock(return_value={})

        response = await async_client.get("/api/v1/election/leader")

        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] is None


class TestLeaderHeartbeatEndpoint:
    """Testes do endpoint /api/v1/election/leader/heartbeat"""

    @pytest.mark.asyncio
    async def test_get_leader_heartbeat(self, async_client: AsyncClient):
        """Testa obtenção de heartbeat do líder"""
        response = await async_client.get("/api/v1/election/leader/heartbeat")

        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "test-node-1"
        assert data["timestamp"] == "2024-01-01T00:00:00"


class TestResignLeadershipEndpoint:
    """Testes do endpoint POST /api/v1/election/resign"""

    @pytest.mark.asyncio
    async def test_resign_leadership_as_leader(self, async_client: AsyncClient):
        """Testa renúncia de liderança quando é líder"""
        response = await async_client.post("/api/v1/election/resign")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Leadership resigned successfully"

    @pytest.mark.asyncio
    async def test_resign_leadership_as_follower(self, app, async_client: AsyncClient):
        """Testa tentativa de renúncia quando não é líder"""
        app.state.app_state.leader_election.is_leader.return_value = False

        response = await async_client.post("/api/v1/election/resign")

        assert response.status_code == 403
