"""
Testes unitários para o endpoint POST /api/v1/workflows/start.

Valida o comportamento do endpoint de início de workflow Temporal,
incluindo cenários de sucesso, erros e validações.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_app_state():
    """Mock do app_state para testes."""
    with patch('src.main.app_state') as mock_state:
        yield mock_state


@pytest.fixture
def mock_settings():
    """Mock das configurações."""
    with patch('src.main.get_settings') as mock_get_settings:
        mock_config = MagicMock()
        mock_config.temporal_workflow_id_prefix = 'nhm-'
        mock_config.temporal_task_queue = 'orchestration-tasks'
        mock_get_settings.return_value = mock_config
        yield mock_config


class TestWorkflowStartSuccess:
    """Testes de sucesso do endpoint /api/v1/workflows/start."""

    @pytest.mark.asyncio
    async def test_workflow_start_basic_success(self, mock_app_state, mock_settings):
        """Testa início de workflow com sucesso básico."""
        from src.main import app

        # Mock Temporal client
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {
                        "plan_id": "plan-123",
                        "intent_id": "intent-456",
                        "decision_id": "decision-789",
                        "tasks": []
                    },
                    "correlation_id": "corr-abc",
                    "priority": 7,
                    "sla_deadline_seconds": 7200
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "nhm-flow-c-corr-abc"
        assert data["status"] == "started"
        assert data["correlation_id"] == "corr-abc"

        # Validar chamada ao Temporal
        mock_temporal.start_workflow.assert_called_once()
        call_args = mock_temporal.start_workflow.call_args
        assert call_args.kwargs["id"] == "nhm-flow-c-corr-abc"
        assert call_args.kwargs["task_queue"] == "orchestration-tasks"

    @pytest.mark.asyncio
    async def test_workflow_start_with_default_priority(self, mock_app_state, mock_settings):
        """Testa início de workflow com prioridade default (5)."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {
                        "plan_id": "plan-123",
                        "intent_id": "intent-456"
                    },
                    "correlation_id": "corr-def"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

        # Validar que input_data contém prioridade default
        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]
        assert input_data["consolidated_decision"]["priority"] == 5

    @pytest.mark.asyncio
    async def test_workflow_start_with_default_sla(self, mock_app_state, mock_settings):
        """Testa início de workflow com SLA default (14400s = 4h)."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-ghi"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]
        assert input_data["consolidated_decision"]["sla_deadline_seconds"] == 14400


class TestWorkflowStartTemporalUnavailable:
    """Testes de erro quando Temporal não está disponível."""

    @pytest.mark.asyncio
    async def test_workflow_start_temporal_client_none(self, mock_app_state):
        """Testa erro 503 quando temporal_client é None."""
        from src.main import app

        mock_app_state.temporal_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-xyz"
                }
            )

        assert response.status_code == 503
        assert "Temporal client not available" in response.json()["detail"]


class TestWorkflowStartErrors:
    """Testes de erro ao iniciar workflow."""

    @pytest.mark.asyncio
    async def test_workflow_start_temporal_exception(self, mock_app_state, mock_settings):
        """Testa erro 500 quando Temporal lança exceção."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-err"
                }
            )

        assert response.status_code == 500
        assert "Failed to start workflow" in response.json()["detail"]
        assert "Connection refused" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_workflow_start_workflow_already_exists(self, mock_app_state, mock_settings):
        """Testa erro quando workflow já existe."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock(
            side_effect=Exception("Workflow already exists")
        )
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-dup"
                }
            )

        assert response.status_code == 500
        assert "Workflow already exists" in response.json()["detail"]


class TestWorkflowStartValidation:
    """Testes de validação de request."""

    @pytest.mark.asyncio
    async def test_workflow_start_missing_cognitive_plan(self, mock_app_state, mock_settings):
        """Testa erro 422 quando cognitive_plan está ausente."""
        from src.main import app

        mock_app_state.temporal_client = MagicMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "correlation_id": "corr-xyz"
                }
            )

        assert response.status_code == 422
        assert "cognitive_plan" in str(response.json())

    @pytest.mark.asyncio
    async def test_workflow_start_missing_correlation_id(self, mock_app_state, mock_settings):
        """Testa erro 422 quando correlation_id está ausente."""
        from src.main import app

        mock_app_state.temporal_client = MagicMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"}
                }
            )

        assert response.status_code == 422
        assert "correlation_id" in str(response.json())

    @pytest.mark.asyncio
    async def test_workflow_start_priority_below_minimum(self, mock_app_state, mock_settings):
        """Testa erro 422 quando priority < 1."""
        from src.main import app

        mock_app_state.temporal_client = MagicMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-xyz",
                    "priority": 0
                }
            )

        assert response.status_code == 422
        assert "priority" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_workflow_start_priority_above_maximum(self, mock_app_state, mock_settings):
        """Testa erro 422 quando priority > 10."""
        from src.main import app

        mock_app_state.temporal_client = MagicMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-xyz",
                    "priority": 11
                }
            )

        assert response.status_code == 422
        assert "priority" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_workflow_start_empty_body(self, mock_app_state, mock_settings):
        """Testa erro 422 quando body está vazio."""
        from src.main import app

        mock_app_state.temporal_client = MagicMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={}
            )

        assert response.status_code == 422


class TestWorkflowStartDecisionIdFallback:
    """Testes de fallback de decision_id."""

    @pytest.mark.asyncio
    async def test_workflow_start_uses_decision_id_from_plan(self, mock_app_state, mock_settings):
        """Testa que decision_id é extraído do cognitive_plan."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {
                        "plan_id": "plan-123",
                        "decision_id": "decision-from-plan"
                    },
                    "correlation_id": "corr-xyz"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]
        assert input_data["consolidated_decision"]["decision_id"] == "decision-from-plan"

    @pytest.mark.asyncio
    async def test_workflow_start_fallback_to_correlation_id(self, mock_app_state, mock_settings):
        """Testa fallback para correlation_id quando decision_id ausente."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {
                        "plan_id": "plan-123"
                        # decision_id ausente
                    },
                    "correlation_id": "corr-fallback"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]
        assert input_data["consolidated_decision"]["decision_id"] == "corr-fallback"

    @pytest.mark.asyncio
    async def test_workflow_start_fallback_with_empty_decision_id(self, mock_app_state, mock_settings):
        """Testa fallback quando decision_id é string vazia."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {
                        "plan_id": "plan-123",
                        "decision_id": ""  # String vazia
                    },
                    "correlation_id": "corr-empty"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]
        # String vazia é falsy, deve usar correlation_id como fallback
        assert input_data["consolidated_decision"]["decision_id"] == "corr-empty"


class TestWorkflowIdGeneration:
    """Testes de geração de workflow_id."""

    @pytest.mark.asyncio
    async def test_workflow_id_format(self, mock_app_state, mock_settings):
        """Testa formato correto do workflow_id."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "test-correlation-id"
                }
            )

        assert response.status_code == 200
        data = response.json()
        # Formato: {prefix}flow-c-{correlation_id}
        assert data["workflow_id"] == "nhm-flow-c-test-correlation-id"

    @pytest.mark.asyncio
    async def test_workflow_id_uses_configured_prefix(self, mock_app_state):
        """Testa que workflow_id usa prefixo configurado."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        # Mock com prefixo diferente
        with patch('src.main.get_settings') as mock_get_settings:
            mock_config = MagicMock()
            mock_config.temporal_workflow_id_prefix = 'custom-prefix-'
            mock_config.temporal_task_queue = 'test-queue'
            mock_get_settings.return_value = mock_config

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/workflows/start",
                    json={
                        "cognitive_plan": {"plan_id": "plan-123"},
                        "correlation_id": "corr-id"
                    }
                )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "custom-prefix-flow-c-corr-id"

    @pytest.mark.asyncio
    async def test_workflow_id_with_uuid_correlation(self, mock_app_state, mock_settings):
        """Testa workflow_id com UUID como correlation_id."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        uuid_correlation = "550e8400-e29b-41d4-a716-446655440000"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": uuid_correlation
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == f"nhm-flow-c-{uuid_correlation}"


class TestWorkflowStartInputData:
    """Testes de construção do input_data para o workflow."""

    @pytest.mark.asyncio
    async def test_input_data_contains_consolidated_decision(self, mock_app_state, mock_settings):
        """Testa que input_data contém consolidated_decision."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {
                        "plan_id": "plan-123",
                        "intent_id": "intent-456",
                        "decision_id": "decision-789"
                    },
                    "correlation_id": "corr-xyz",
                    "priority": 8,
                    "sla_deadline_seconds": 3600
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]

        consolidated_decision = input_data["consolidated_decision"]
        assert consolidated_decision["decision_id"] == "decision-789"
        assert consolidated_decision["plan_id"] == "plan-123"
        assert consolidated_decision["intent_id"] == "intent-456"
        assert consolidated_decision["final_decision"] == "approve"
        assert consolidated_decision["correlation_id"] == "corr-xyz"
        assert consolidated_decision["priority"] == 8
        assert consolidated_decision["sla_deadline_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_input_data_contains_cognitive_plan(self, mock_app_state, mock_settings):
        """Testa que input_data contém cognitive_plan original."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        cognitive_plan = {
            "plan_id": "plan-123",
            "intent_id": "intent-456",
            "tasks": [
                {"task_id": "task-1", "type": "BUILD"},
                {"task_id": "task-2", "type": "DEPLOY"}
            ]
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": cognitive_plan,
                    "correlation_id": "corr-xyz"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]

        assert input_data["cognitive_plan"] == cognitive_plan

    @pytest.mark.asyncio
    async def test_input_data_unknown_plan_id_fallback(self, mock_app_state, mock_settings):
        """Testa fallback para 'unknown' quando plan_id ausente."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {},  # Sem plan_id
                    "correlation_id": "corr-xyz"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]

        assert input_data["consolidated_decision"]["plan_id"] == "unknown"
        assert input_data["consolidated_decision"]["intent_id"] == "unknown"


# =============================================================================
# Testes para GET /api/v1/tickets/{ticket_id}
# =============================================================================

class TestGetTicketEndpoint:
    """Testes para o endpoint GET /api/v1/tickets/{ticket_id}."""

    @pytest.fixture
    def mock_mongodb_client(self):
        """Mock do cliente MongoDB."""
        client = AsyncMock()
        client.get_ticket = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_ticket_success(self, mock_app_state, mock_mongodb_client):
        """Testa consulta de ticket com sucesso."""
        from src.main import app

        expected_ticket = {
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-456',
            'status': 'COMPLETED',
            'task_type': 'BUILD'
        }
        mock_mongodb_client.get_ticket.return_value = expected_ticket
        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/ticket-123")

        assert response.status_code == 200
        data = response.json()
        assert data['ticket_id'] == 'ticket-123'
        assert data['status'] == 'COMPLETED'
        assert data['cached'] is False

    @pytest.mark.asyncio
    async def test_get_ticket_not_found(self, mock_app_state, mock_mongodb_client):
        """Testa erro 404 quando ticket não existe."""
        from src.main import app

        mock_mongodb_client.get_ticket.return_value = None
        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/ticket-inexistente")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_ticket_mongodb_unavailable(self, mock_app_state):
        """Testa erro 503 quando MongoDB não está disponível."""
        from src.main import app

        mock_app_state.mongodb_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/ticket-123")

        assert response.status_code == 503
        assert "MongoDB not available" in response.json()["detail"]


# =============================================================================
# Testes para GET /api/v1/tickets/by-plan/{plan_id}
# =============================================================================

class TestGetTicketsByPlanEndpoint:
    """Testes para o endpoint GET /api/v1/tickets/by-plan/{plan_id}."""

    @pytest.fixture
    def mock_mongodb_client(self):
        """Mock do cliente MongoDB com collection de tickets."""
        client = AsyncMock()
        client.execution_tickets = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_get_tickets_by_plan_success(self, mock_app_state, mock_mongodb_client):
        """Testa listagem de tickets com sucesso."""
        from src.main import app

        expected_tickets = [
            {'ticket_id': 'ticket-1', 'status': 'COMPLETED'},
            {'ticket_id': 'ticket-2', 'status': 'RUNNING'}
        ]

        # Mock collection methods
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=expected_tickets)

        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=2)
        mock_mongodb_client.execution_tickets.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/by-plan/plan-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data['tickets']) == 2
        assert data['total'] == 2
        assert data['cached'] is False

    @pytest.mark.asyncio
    async def test_get_tickets_by_plan_with_status_filter(self, mock_app_state, mock_mongodb_client):
        """Testa filtragem por status."""
        from src.main import app

        expected_tickets = [{'ticket_id': 'ticket-1', 'status': 'COMPLETED'}]

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=expected_tickets)

        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=1)
        mock_mongodb_client.execution_tickets.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/by-plan/plan-123?status=COMPLETED")

        assert response.status_code == 200
        data = response.json()
        assert len(data['tickets']) == 1

    @pytest.mark.asyncio
    async def test_get_tickets_by_plan_invalid_limit(self, mock_app_state, mock_mongodb_client):
        """Testa erro 400 quando limit > 500."""
        from src.main import app

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/by-plan/plan-123?limit=600")

        assert response.status_code == 400
        assert "cannot exceed 500" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_tickets_by_plan_invalid_status(self, mock_app_state, mock_mongodb_client):
        """Testa erro 400 com status inválido."""
        from src.main import app

        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=0)
        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/by-plan/plan-123?status=INVALID")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_tickets_by_plan_mongodb_unavailable(self, mock_app_state):
        """Testa erro 503 quando MongoDB não está disponível."""
        from src.main import app

        mock_app_state.mongodb_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/tickets/by-plan/plan-123")

        assert response.status_code == 503
        assert "MongoDB not available" in response.json()["detail"]


# =============================================================================
# Testes para GET /api/v1/workflows/{workflow_id}
# =============================================================================

class TestGetWorkflowStatusEndpoint:
    """Testes para o endpoint GET /api/v1/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_get_workflow_status_success(self, mock_app_state):
        """Testa consulta de status de workflow com sucesso."""
        from src.main import app

        # Mock Temporal client
        mock_handle = AsyncMock()
        mock_description = MagicMock()
        mock_description.workflow_execution_info = MagicMock()
        mock_description.workflow_execution_info.status.name = 'RUNNING'
        mock_description.workflow_execution_info.start_time = None
        mock_description.workflow_execution_info.close_time = None
        mock_description.workflow_execution_info.execution_time = None
        mock_description.workflow_execution_info.type = MagicMock()
        mock_description.workflow_execution_info.type.name = 'OrchestrationWorkflow'
        mock_description.workflow_execution_info.task_queue = 'orchestration-tasks'
        mock_handle.describe = AsyncMock(return_value=mock_description)

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle.return_value = mock_handle
        mock_app_state.temporal_client = mock_temporal
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/workflows/flow-c-test-123")

        assert response.status_code == 200
        data = response.json()
        assert data['workflow_id'] == 'flow-c-test-123'
        assert data['status'] == 'RUNNING'
        assert data['cached'] is False

    @pytest.mark.asyncio
    async def test_get_workflow_status_not_found(self, mock_app_state):
        """Testa erro 404 quando workflow não existe."""
        from src.main import app

        mock_handle = AsyncMock()
        mock_handle.describe = AsyncMock(side_effect=Exception("Workflow not found"))

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle.return_value = mock_handle
        mock_app_state.temporal_client = mock_temporal
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/workflows/workflow-inexistente")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_workflow_status_temporal_unavailable(self, mock_app_state):
        """Testa erro 503 quando Temporal não está disponível."""
        from src.main import app

        mock_app_state.temporal_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/workflows/flow-c-test-123")

        assert response.status_code == 503
        assert "Temporal client not available" in response.json()["detail"]
