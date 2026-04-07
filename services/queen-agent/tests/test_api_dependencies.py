"""
Testes de Dependency Injection para APIs REST do Queen Agent.

Verifica que as dependências são injetadas correctamente usando FastAPI Depends().
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from fastapi import HTTPException

from src.api.dependencies import (
    get_mongodb_client,
    get_load_balancer,
    get_leader_election,
    get_exception_service,
    get_mcp_orchestrator,
)
from src.clients import MongoDBClient
from src.services import (
    LoadBalancer,
    LeaderElection,
    ExceptionApprovalService,
)


@pytest.fixture
def mock_request():
    """Mock Request com app_state"""
    request = MagicMock()
    request.app.state.app_state = MagicMock()
    return request


class TestGetMongoDBClient:
    """Testes do get_mongodb_client"""

    @pytest.mark.asyncio
    async def test_get_mongodb_client_success(self, mock_request):
        """Testa obtenção bem-sucedida do cliente MongoDB"""
        mock_client = MagicMock(spec=MongoDBClient)
        mock_request.app.state.app_state.mongodb_client = mock_client

        result = await get_mongodb_client(mock_request)

        assert result == mock_client

    @pytest.mark.asyncio
    async def test_get_mongodb_client_not_initialized(self, mock_request):
        """Testa erro quando cliente não está inicializado"""
        mock_request.app.state.app_state.mongodb_client = None

        with pytest.raises(HTTPException) as exc_info:
            await get_mongodb_client(mock_request)

        assert "MongoDB client not initialized" in str(exc_info.value)


class TestGetLoadBalancer:
    """Testes do get_load_balancer"""

    @pytest.mark.asyncio
    async def test_get_load_balancer_success(self, mock_request):
        """Testa obtenção bem-sucedida do LoadBalancer"""
        mock_lb = MagicMock(spec=LoadBalancer)
        mock_request.app.state.app_state.load_balancer = mock_lb

        result = await get_load_balancer(mock_request)

        assert result == mock_lb

    @pytest.mark.asyncio
    async def test_get_load_balancer_not_enabled(self, mock_request):
        """Testa erro quando LoadBalancer não está habilitado"""
        mock_request.app.state.app_state.load_balancer = None

        with pytest.raises(HTTPException) as exc_info:
            await get_load_balancer(mock_request)

        assert "Load balancer not enabled" in str(exc_info.value)


class TestGetLeaderElection:
    """Testes do get_leader_election"""

    @pytest.mark.asyncio
    async def test_get_leader_election_success(self, mock_request):
        """Testa obtenção bem-sucedida do LeaderElection"""
        mock_le = MagicMock(spec=LeaderElection)
        mock_request.app.state.app_state.leader_election = mock_le

        result = await get_leader_election(mock_request)

        assert result == mock_le

    @pytest.mark.asyncio
    async def test_get_leader_election_not_enabled(self, mock_request):
        """Testa erro quando LeaderElection não está habilitado"""
        mock_request.app.state.app_state.leader_election = None

        with pytest.raises(HTTPException) as exc_info:
            await get_leader_election(mock_request)

        assert "Leader election not enabled" in str(exc_info.value)


class TestGetExceptionService:
    """Testes do get_exception_service"""

    @pytest.mark.asyncio
    async def test_get_exception_service_success(self, mock_request):
        """Testa obtenção bem-sucedida do ExceptionApprovalService"""
        mock_service = MagicMock(spec=ExceptionApprovalService)
        mock_request.app.state.app_state.exception_service = mock_service

        result = await get_exception_service(mock_request)

        assert result == mock_service

    @pytest.mark.asyncio
    async def test_get_exception_service_not_enabled(self, mock_request):
        """Testa erro quando ExceptionApprovalService não está habilitado"""
        mock_request.app.state.app_state.exception_service = None

        with pytest.raises(HTTPException) as exc_info:
            await get_exception_service(mock_request)

        assert "Exception approval service not enabled" in str(exc_info.value)


class TestGetMcpOrchestrator:
    """Testes do get_mcp_orchestrator"""

    @pytest.mark.asyncio
    async def test_get_mcp_orchestrator_success(self, mock_request):
        """Testa obtenção bem-sucedida do MCPToolOrchestrator"""
        mock_orchestrator = MagicMock()
        mock_request.app.state.app_state.mcp_orchestrator = mock_orchestrator

        result = await get_mcp_orchestrator(mock_request)

        assert result == mock_orchestrator

    @pytest.mark.asyncio
    async def test_get_mcp_orchestrator_not_available(self, mock_request):
        """Testa erro quando MCPToolOrchestrator não está disponível"""
        mock_request.app.state.app_state.mcp_orchestrator = None

        with pytest.raises(HTTPException) as exc_info:
            await get_mcp_orchestrator(mock_request)

        assert "MCP Orchestrator not available" in str(exc_info.value)


class TestDependencyInjectionIntegration:
    """Testes de integração de DI com endpoints FastAPI"""

    @pytest.fixture
    def app_with_di(self):
        """App FastAPI com DI configurado"""
        from fastapi import FastAPI
        from src.api.workers import router as workers_router
        from src.api.election import router as election_router
        from src.api.decisions import router as decisions_router
        from src.api.exceptions import router as exceptions_router
        from src.api.mcp import router as mcp_router

        app = FastAPI()

        # Configurar app_state com mocks
        app.state.app_state = MagicMock()

        # Mock services
        mock_load_balancer = MagicMock(spec=LoadBalancer)
        mock_load_balancer.is_running = True
        mock_load_balancer.register_worker = AsyncMock(return_value=True)
        mock_load_balancer.unregister_worker = AsyncMock(return_value=True)
        mock_load_balancer.update_worker_metrics = AsyncMock(return_value=True)
        mock_load_balancer.get_workers_status = AsyncMock(return_value=[])
        mock_load_balancer.get_statistics = AsyncMock(
            return_value={"total_workers": 0}
        )
        from src.services.load_balancer import BalancingStrategy, TaskAssignment
        mock_load_balancer.assign_task = AsyncMock(
            return_value=TaskAssignment(
                worker_id="worker-1",
                strategy=BalancingStrategy.ROUND_ROBIN,
                assigned_at=datetime.now(timezone.utc)
            )
        )
        mock_load_balancer.complete_task = AsyncMock(return_value=True)

        mock_leader_election = MagicMock(spec=LeaderElection)
        from src.services import NodeRole, ElectionState
        mock_leader_election.node_id = "queen-test-1"
        mock_leader_election.get_state = MagicMock(
            return_value=ElectionState(
                role=NodeRole.FOLLOWER,
                leader_id="queen-1",
                term=1,
            )
        )
        mock_leader_election.get_leader_metadata = AsyncMock(
            return_value={"node_id": "queen-1", "term": 1}
        )
        mock_leader_election.get_leader_heartbeat = AsyncMock(
            return_value={"node_id": "queen-1", "timestamp": "2026-04-07T00:00:00Z"}
        )
        mock_leader_election.is_leader = MagicMock(return_value=False)

        mock_mongodb_client = MagicMock(spec=MongoDBClient)
        mock_mongodb_client.get_strategic_decision = AsyncMock(return_value=None)
        mock_mongodb_client.list_strategic_decisions = AsyncMock(return_value=[])
        mock_mongodb_client.get_recent_decisions = AsyncMock(return_value=[])

        mock_exception_service = MagicMock(spec=ExceptionApprovalService)
        mock_exception_service.get_pending_exceptions = AsyncMock(return_value=[])

        mock_mcp_orchestrator = MagicMock()
        mock_mcp_orchestrator.get_available_tools = AsyncMock(return_value={})

        app.state.app_state.load_balancer = mock_load_balancer
        app.state.app_state.leader_election = mock_leader_election
        app.state.app_state.mongodb_client = mock_mongodb_client
        app.state.app_state.exception_service = mock_exception_service
        app.state.app_state.mcp_orchestrator = mock_mcp_orchestrator

        # Incluir routers
        app.include_router(workers_router)
        app.include_router(election_router)
        app.include_router(decisions_router)
        app.include_router(exceptions_router)
        app.include_router(mcp_router)

        return app

    @pytest.mark.asyncio
    async def test_workers_api_with_di(self, app_with_di):
        """Testa que workers API funciona com DI"""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_di)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/workers")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_election_api_with_di(self, app_with_di):
        """Testa que election API funciona com DI"""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_di)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/election/status")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_decisions_api_with_di(self, app_with_di):
        """Testa que decisions API funciona com DI"""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_di)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/decisions")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_exceptions_api_with_di(self, app_with_di):
        """Testa que exceptions API funciona com DI"""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_di)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/exceptions/pending")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_mcp_api_with_di(self, app_with_di):
        """Testa que MCP API funciona com DI"""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app_with_di)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/mcp/status")

            assert response.status_code == 200
