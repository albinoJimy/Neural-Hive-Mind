"""
Testes de contrato para os endpoints GET de tickets e workflows.

Valida schemas de resposta e campos obrigatórios para:
- GET /api/v1/tickets/{ticket_id}
- GET /api/v1/tickets/by-plan/{plan_id}
- GET /api/v1/workflows/{workflow_id}

Estes testes são independentes de mocks unitários e focam na estrutura
da resposta conforme esperado pelos consumidores da API.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# =============================================================================
# Schemas de Contrato
# =============================================================================

TICKET_REQUIRED_FIELDS = {
    'ticket_id': str,
    'plan_id': str,
    'status': str,
}

TICKET_OPTIONAL_FIELDS = {
    'intent_id': str,
    'decision_id': str,
    'task_id': str,
    'task_type': str,
    'description': str,
    'priority': (str, int),
    'risk_band': str,
    'created_at': (str, int, float),
    'started_at': (str, int, float, type(None)),
    'completed_at': (str, int, float, type(None)),
    'cached': bool,
}

TICKETS_LIST_REQUIRED_FIELDS = {
    'tickets': list,
    'total': int,
    'cached': bool,
}

TICKETS_LIST_OPTIONAL_FIELDS = {
    'limit': int,
    'offset': int,
    'has_more': bool,
}

WORKFLOW_STATUS_REQUIRED_FIELDS = {
    'workflow_id': str,
    'status': str,
    'cached': bool,
}

WORKFLOW_STATUS_OPTIONAL_FIELDS = {
    'start_time': (str, type(None)),
    'close_time': (str, type(None)),
    'execution_time': (str, type(None)),
    'workflow_type': str,
    'task_queue': str,
}

ERROR_RESPONSE_REQUIRED_FIELDS = {
    'detail': str,
}

VALID_TICKET_STATUSES = [
    'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'REJECTED', 'COMPENSATING', 'COMPENSATED'
]

VALID_WORKFLOW_STATUSES = [
    'RUNNING', 'COMPLETED', 'FAILED', 'CANCELED', 'TERMINATED', 'CONTINUED_AS_NEW', 'TIMED_OUT'
]


# =============================================================================
# Helper Functions
# =============================================================================

def validate_field_types(data: dict, required_fields: dict, optional_fields: dict = None):
    """
    Valida tipos de campos em uma resposta.

    Args:
        data: Dicionário de resposta
        required_fields: Dict de campo -> tipo esperado
        optional_fields: Dict de campo -> tipo esperado (opcional)

    Raises:
        AssertionError: Se validação falhar
    """
    # Validar campos obrigatórios
    for field, expected_type in required_fields.items():
        assert field in data, f"Campo obrigatório ausente: {field}"
        if isinstance(expected_type, tuple):
            assert isinstance(data[field], expected_type), \
                f"Campo {field} esperava tipo {expected_type}, recebeu {type(data[field])}"
        else:
            assert isinstance(data[field], expected_type), \
                f"Campo {field} esperava tipo {expected_type}, recebeu {type(data[field])}"

    # Validar campos opcionais (se presentes)
    if optional_fields:
        for field, expected_type in optional_fields.items():
            if field in data and data[field] is not None:
                if isinstance(expected_type, tuple):
                    assert isinstance(data[field], expected_type), \
                        f"Campo opcional {field} esperava tipo {expected_type}, recebeu {type(data[field])}"
                else:
                    assert isinstance(data[field], expected_type), \
                        f"Campo opcional {field} esperava tipo {expected_type}, recebeu {type(data[field])}"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_app_state():
    """Mock do app_state para testes."""
    with patch('src.main.app_state') as mock_state:
        yield mock_state


@pytest.fixture
def mock_mongodb_client():
    """Mock do cliente MongoDB."""
    client = AsyncMock()
    client.get_ticket = AsyncMock()
    client.execution_tickets = MagicMock()
    return client


@pytest.fixture
def mock_temporal_client():
    """Mock do cliente Temporal."""
    client = MagicMock()
    return client


# =============================================================================
# GET /api/v1/tickets/{ticket_id} - Contract Tests
# =============================================================================

class TestGetTicketContract:
    """Testes de contrato para GET /api/v1/tickets/{ticket_id}."""

    @pytest.mark.asyncio
    async def test_success_response_schema(self, mock_app_state, mock_mongodb_client):
        """Valida schema de resposta de sucesso."""
        from src.main import app

        mock_ticket = {
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-456',
            'intent_id': 'intent-789',
            'task_id': 'task-001',
            'task_type': 'BUILD',
            'status': 'COMPLETED',
            'description': 'Build application',
            'priority': 7,
            'created_at': 1704067200000,
        }
        mock_mongodb_client.get_ticket.return_value = mock_ticket
        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/ticket-123')

        assert response.status_code == 200
        data = response.json()

        validate_field_types(data, TICKET_REQUIRED_FIELDS, TICKET_OPTIONAL_FIELDS)
        assert data['status'] in VALID_TICKET_STATUSES

    @pytest.mark.asyncio
    async def test_not_found_error_schema(self, mock_app_state, mock_mongodb_client):
        """Valida schema de erro 404."""
        from src.main import app

        mock_mongodb_client.get_ticket.return_value = None
        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/ticket-inexistente')

        assert response.status_code == 404
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)
        assert 'not found' in data['detail'].lower()

    @pytest.mark.asyncio
    async def test_service_unavailable_error_schema(self, mock_app_state):
        """Valida schema de erro 503 quando MongoDB indisponível."""
        from src.main import app

        mock_app_state.mongodb_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/ticket-123')

        assert response.status_code == 503
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)
        assert 'mongodb' in data['detail'].lower() or 'not available' in data['detail'].lower()


# =============================================================================
# GET /api/v1/tickets/by-plan/{plan_id} - Contract Tests
# =============================================================================

class TestGetTicketsByPlanContract:
    """Testes de contrato para GET /api/v1/tickets/by-plan/{plan_id}."""

    @pytest.mark.asyncio
    async def test_success_response_schema(self, mock_app_state, mock_mongodb_client):
        """Valida schema de resposta de sucesso com lista de tickets."""
        from src.main import app

        mock_tickets = [
            {'ticket_id': 'ticket-1', 'plan_id': 'plan-123', 'status': 'COMPLETED'},
            {'ticket_id': 'ticket-2', 'plan_id': 'plan-123', 'status': 'RUNNING'},
        ]

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_tickets)

        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=2)
        mock_mongodb_client.execution_tickets.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/by-plan/plan-123')

        assert response.status_code == 200
        data = response.json()

        validate_field_types(data, TICKETS_LIST_REQUIRED_FIELDS, TICKETS_LIST_OPTIONAL_FIELDS)

        # Validar cada ticket na lista
        for ticket in data['tickets']:
            assert 'ticket_id' in ticket
            assert 'status' in ticket

    @pytest.mark.asyncio
    async def test_empty_list_response_schema(self, mock_app_state, mock_mongodb_client):
        """Valida schema de resposta com lista vazia."""
        from src.main import app

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=0)
        mock_mongodb_client.execution_tickets.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/by-plan/plan-sem-tickets')

        assert response.status_code == 200
        data = response.json()

        validate_field_types(data, TICKETS_LIST_REQUIRED_FIELDS)
        assert data['tickets'] == []
        assert data['total'] == 0

    @pytest.mark.asyncio
    async def test_invalid_limit_error_schema(self, mock_app_state, mock_mongodb_client):
        """Valida schema de erro 400 para limit inválido."""
        from src.main import app

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/by-plan/plan-123?limit=1000')

        assert response.status_code == 400
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)
        assert '500' in data['detail'] or 'limit' in data['detail'].lower()

    @pytest.mark.asyncio
    async def test_invalid_status_error_schema(self, mock_app_state, mock_mongodb_client):
        """Valida schema de erro 400 para status inválido."""
        from src.main import app

        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=0)
        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/by-plan/plan-123?status=INVALID_STATUS')

        assert response.status_code == 400
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)
        assert 'status' in data['detail'].lower() or 'invalid' in data['detail'].lower()

    @pytest.mark.asyncio
    async def test_service_unavailable_error_schema(self, mock_app_state):
        """Valida schema de erro 503 quando MongoDB indisponível."""
        from src.main import app

        mock_app_state.mongodb_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/tickets/by-plan/plan-123')

        assert response.status_code == 503
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)


# =============================================================================
# GET /api/v1/workflows/{workflow_id} - Contract Tests
# =============================================================================

class TestGetWorkflowStatusContract:
    """Testes de contrato para GET /api/v1/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_success_response_schema(self, mock_app_state, mock_temporal_client):
        """Valida schema de resposta de sucesso."""
        from src.main import app

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

        mock_temporal_client.get_workflow_handle.return_value = mock_handle
        mock_app_state.temporal_client = mock_temporal_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/workflows/flow-c-test-123')

        assert response.status_code == 200
        data = response.json()

        validate_field_types(data, WORKFLOW_STATUS_REQUIRED_FIELDS, WORKFLOW_STATUS_OPTIONAL_FIELDS)
        assert data['status'] in VALID_WORKFLOW_STATUSES

    @pytest.mark.asyncio
    async def test_not_found_error_schema(self, mock_app_state, mock_temporal_client):
        """Valida schema de erro 404 quando workflow não existe."""
        from src.main import app

        mock_handle = AsyncMock()
        mock_handle.describe = AsyncMock(side_effect=Exception('Workflow not found'))

        mock_temporal_client.get_workflow_handle.return_value = mock_handle
        mock_app_state.temporal_client = mock_temporal_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/workflows/workflow-inexistente')

        assert response.status_code == 404
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)
        assert 'not found' in data['detail'].lower()

    @pytest.mark.asyncio
    async def test_service_unavailable_error_schema(self, mock_app_state):
        """Valida schema de erro 503 quando Temporal indisponível."""
        from src.main import app

        mock_app_state.temporal_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            response = await ac.get('/api/v1/workflows/flow-c-test-123')

        assert response.status_code == 503
        data = response.json()

        validate_field_types(data, ERROR_RESPONSE_REQUIRED_FIELDS)
        assert 'temporal' in data['detail'].lower() or 'not available' in data['detail'].lower()


# =============================================================================
# Cross-Endpoint Contract Tests
# =============================================================================

class TestCrossEndpointConsistency:
    """Testes de consistência entre endpoints."""

    @pytest.mark.asyncio
    async def test_cached_flag_present_in_all_success_responses(self, mock_app_state, mock_mongodb_client):
        """Valida que todas as respostas de sucesso incluem flag 'cached'."""
        from src.main import app

        # Setup mocks
        mock_ticket = {
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-456',
            'status': 'COMPLETED',
        }
        mock_mongodb_client.get_ticket.return_value = mock_ticket

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[mock_ticket])
        mock_mongodb_client.execution_tickets.count_documents = AsyncMock(return_value=1)
        mock_mongodb_client.execution_tickets.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor

        mock_app_state.mongodb_client = mock_mongodb_client
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            # GET ticket
            response = await ac.get('/api/v1/tickets/ticket-123')
            assert response.status_code == 200
            assert 'cached' in response.json()

            # GET tickets by plan
            response = await ac.get('/api/v1/tickets/by-plan/plan-456')
            assert response.status_code == 200
            assert 'cached' in response.json()

    @pytest.mark.asyncio
    async def test_error_responses_have_consistent_format(self, mock_app_state):
        """Valida formato consistente de erros entre endpoints."""
        from src.main import app

        mock_app_state.mongodb_client = None
        mock_app_state.temporal_client = None
        mock_app_state.redis_client = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            # Todos os endpoints 503 devem ter 'detail'
            for endpoint in [
                '/api/v1/tickets/ticket-123',
                '/api/v1/tickets/by-plan/plan-123',
                '/api/v1/workflows/workflow-123',
            ]:
                response = await ac.get(endpoint)
                assert response.status_code == 503
                data = response.json()
                assert 'detail' in data
                assert isinstance(data['detail'], str)
                assert len(data['detail']) > 0
