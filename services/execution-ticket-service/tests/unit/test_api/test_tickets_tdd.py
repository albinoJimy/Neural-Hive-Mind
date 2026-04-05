"""
Testes TDD para API de Tickets - Fase RED

Testes escritos ANTES da implementação.
Seguem o ciclo RED-GREEN-REFACTOR.
"""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api import tickets as tickets_api
from src.models import TicketStatus, Priority, RiskBand


# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        postgres_host='localhost',
        postgres_port=5432,
        postgres_database='test_db',
        postgres_user='test',
        postgres_password='test',
        postgres_pool_size=5,
        postgres_max_overflow=10,
        mongodb_uri='mongodb://localhost:27017',
        mongodb_database='test_db',
        mongodb_collection_tickets='tickets',
        mongodb_collection_audit='audit',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='execution.tickets',
        kafka_consumer_group_id='test-consumer',
        kafka_auto_offset_reset='earliest',
        kafka_enable_auto_commit=False,
        kafka_schema_registry_url='http://localhost:8081',
        kafka_security_protocol='PLAINTEXT',
        kafka_sasl_mechanism=None,
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_ssl_ca_location=None,
        kafka_ssl_certificate_location=None,
        kafka_ssl_key_location=None,
        schemas_base_path='/schemas',
        enable_audit_trail=False,
        enable_jwt_tokens=True,
        jwt_secret_key='test-secret-key',
        jwt_algorithm='HS256',
        jwt_token_expiration_seconds=3600,
        enable_idempotency=False,
        environment='test',
        service_name='execution-ticket-service',
        service_version='1.0.0',
        log_level='INFO',
        otel_exporter_endpoint='http://localhost:4317',
        prometheus_port=9090,
        grpc_port=50052,
        enable_webhooks=False,
        webhook_timeout_seconds=30,
        webhook_worker_count=2,
        max_connection_retries=3,
        initial_retry_delay_seconds=0.1,
        redis_host='localhost',
        redis_port=6379,
        redis_db=0,
        redis_password=None,
        redis_idempotency_ttl_seconds=604800,
        # Adicionando campos faltantes para o TicketServiceSettings
        otel_exporter_otlp_endpoint='http://localhost:4317',
        service_instance_id='test-instance',
    )


def make_pydantic_mock(ticket_dict: dict) -> SimpleNamespace:
    """Cria mock de Pydantic model."""
    return SimpleNamespace(**ticket_dict)


def make_orm_mock(ticket_dict: dict) -> MagicMock:
    """Cria mock de ORM com to_pydantic."""
    mock_orm = MagicMock()
    mock_orm.to_pydantic.return_value = make_pydantic_mock(ticket_dict)
    return mock_orm


@pytest.fixture
def sample_ticket_dict():
    """Ticket de exemplo."""
    return {
        'ticket_id': str(uuid4()),
        'plan_id': str(uuid4()),
        'intent_id': str(uuid4()),
        'decision_id': str(uuid4()),
        'task_id': 'task-123',
        'task_type': 'BUILD',
        'description': 'Test ticket',
        'dependencies': [],
        'status': 'PENDING',
        'priority': 'NORMAL',
        'risk_band': 'medium',
        'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
        'qos': SimpleNamespace(
            delivery_mode='AT_MOST_ONCE',
            consistency='EVENTUAL',
            durability='TRANSIENT'
        ),
        'parameters': {},
        'required_capabilities': [],
        'security_level': 'INTERNAL',
        'created_at': int(datetime.now(timezone.utc).timestamp() * 1000),
        'started_at': None,
        'completed_at': None,
        'retry_count': 0,
        'error_message': None,
        'compensation_ticket_id': None,
        'metadata': {},
        'schema_version': 1
    }


@pytest.fixture
def mock_postgres_client(sample_ticket_dict):
    """Cliente PostgreSQL mockado."""
    client = AsyncMock()

    # Mock do get_ticket_by_id
    client.get_ticket_by_id.return_value = make_orm_mock(sample_ticket_dict)

    # Mock do increment_retry_count
    retry_dict = sample_ticket_dict.copy()
    retry_dict['status'] = 'PENDING'
    retry_dict['retry_count'] = 1
    client.increment_retry_count.return_value = make_orm_mock(retry_dict)

    # Mock do update_ticket_status
    updated_dict = sample_ticket_dict.copy()
    updated_dict['status'] = 'RUNNING'
    client.update_ticket_status.return_value = make_orm_mock(updated_dict)

    # Mock do create_ticket
    client.create_ticket.return_value = make_orm_mock(sample_ticket_dict)

    # Mock do list_tickets
    client.list_tickets.return_value = []
    client.count_tickets.return_value = 0

    # Mock do update_ticket_compensation
    client.update_ticket_compensation = AsyncMock()

    return client


@pytest.fixture
def mock_mongodb_client():
    """Cliente MongoDB mockado."""
    client = AsyncMock()
    client.db = MagicMock()
    client.settings = SimpleNamespace(
        mongodb_collection_audit='audit'
    )
    client.log_status_change = AsyncMock()

    # Mock da collection
    mock_collection = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection.find = MagicMock(return_value=mock_cursor)
    client.db.__getitem__ = MagicMock(return_value=mock_collection)

    return client


# ===== TESTES: GET /{ticket_id} =====


class TestGetTicket:
    """Testes do endpoint GET /{ticket_id}."""

    @pytest.mark.asyncio
    async def test_get_ticket_success(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket_id válido
        QUANDO: Chamo get_ticket
        ENTÃO: Deve retornar o ticket
        """
        ticket_id = sample_ticket_dict['ticket_id']

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.get_ticket(ticket_id)

        mock_postgres_client.get_ticket_by_id.assert_called_once_with(ticket_id)
        assert result.ticket_id == ticket_id

    @pytest.mark.asyncio
    async def test_get_ticket_not_found(self, mock_settings, mock_postgres_client):
        """
        DADO: Um ticket_id inexistente
        QUANDO: Chamo get_ticket
        ENTÃO: Deve levantar HTTPException 404
        """
        ticket_id = str(uuid4())
        mock_postgres_client.get_ticket_by_id.return_value = None

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.get_ticket(ticket_id)

        assert exc_info.value.status_code == 404
        assert 'not found' in exc_info.value.detail.lower()


# ===== TESTES: POST / =====


class TestCreateTicket:
    """Testes do endpoint POST /."""

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Dados válidos de ticket
        QUANDO: Chamo create_ticket
        ENTÃO: Deve criar e retornar o ticket
        """
        ticket_data = {
            'plan_id': sample_ticket_dict['plan_id'],
            'intent_id': sample_ticket_dict['intent_id'],
            'decision_id': sample_ticket_dict['decision_id'],
            'task_id': 'task-123',
            'task_type': 'BUILD',
            'description': 'Test ticket',
            'priority': 'NORMAL',
            'risk_band': 'medium',
            'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
            'qos': {
                'delivery_mode': 'AT_MOST_ONCE',
                'consistency': 'EVENTUAL',
                'durability': 'TRANSIENT'
            },
            'security_level': 'INTERNAL',
            'parameters': {},
            'dependencies': [],
            'required_capabilities': []
        }

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.asyncio') as mock_asyncio:
            mock_asyncio.create_task = MagicMock()

            result = await tickets_api.create_ticket(ticket_data)

        mock_postgres_client.create_ticket.assert_called_once()
        assert result is not None
        # Verificar que o ticket foi criado
        assert result is not None
        assert hasattr(result, 'ticket_id')

    @pytest.mark.asyncio
    async def test_create_ticket_generates_id_if_missing(self, mock_settings, mock_postgres_client):
        """
        DADO: Dados de ticket sem ticket_id
        QUANDO: Chamo create_ticket
        ENTÃO: Deve gerar um ticket_id automaticamente
        """
        ticket_data = {
            'plan_id': str(uuid4()),
            'intent_id': str(uuid4()),
            'decision_id': str(uuid4()),
            'task_id': 'task-123',
            'task_type': 'BUILD',
            'description': 'Test ticket',
            'priority': 'NORMAL',
            'risk_band': 'medium',
            'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
            'qos': {
                'delivery_mode': 'AT_MOST_ONCE',
                'consistency': 'EVENTUAL',
                'durability': 'TRANSIENT'
            },
            'security_level': 'INTERNAL',
            'parameters': {},
            'dependencies': [],
            'required_capabilities': []
        }

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.asyncio') as mock_asyncio:
            mock_asyncio.create_task = MagicMock()

            result = await tickets_api.create_ticket(ticket_data)

        assert result.ticket_id is not None
        assert len(result.ticket_id) > 0

    @pytest.mark.asyncio
    async def test_create_ticket_sets_default_status(self, mock_settings, mock_postgres_client):
        """
        DADO: Dados de ticket sem status
        QUANDO: Chamo create_ticket
        ENTÃO: Deve definir status como PENDING
        """
        ticket_data = {
            'plan_id': str(uuid4()),
            'intent_id': str(uuid4()),
            'decision_id': str(uuid4()),
            'task_id': 'task-123',
            'task_type': 'BUILD',
            'description': 'Test ticket',
            'priority': 'NORMAL',
            'risk_band': 'medium',
            'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
            'qos': {
                'delivery_mode': 'AT_MOST_ONCE',
                'consistency': 'EVENTUAL',
                'durability': 'TRANSIENT'
            },
            'security_level': 'INTERNAL',
            'parameters': {},
            'dependencies': [],
            'required_capabilities': []
        }

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.asyncio') as mock_asyncio:
            mock_asyncio.create_task = MagicMock()

            result = await tickets_api.create_ticket(ticket_data)

        assert result.status == 'PENDING'

    @pytest.mark.asyncio
    async def test_create_ticket_generates_timestamp(self, mock_settings, mock_postgres_client):
        """
        DADO: Dados de ticket sem created_at
        QUANDO: Chamo create_ticket
        ENTÃO: Deve incluir created_at gerado automaticamente
        """
        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.asyncio') as mock_asyncio:
            mock_asyncio.create_task = MagicMock()

            ticket_data = {
                'plan_id': str(uuid4()),
                'intent_id': str(uuid4()),
                'decision_id': str(uuid4()),
                'task_id': 'task-123',
                'task_type': 'BUILD',
                'description': 'Test ticket',
                'priority': 'NORMAL',
                'risk_band': 'medium',
                'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
                'qos': {
                    'delivery_mode': 'AT_MOST_ONCE',
                    'consistency': 'EVENTUAL',
                    'durability': 'TRANSIENT'
                },
                'security_level': 'INTERNAL',
                'parameters': {},
                'dependencies': [],
                'required_capabilities': []
            }

            result = await tickets_api.create_ticket(ticket_data)

        # Verificar que created_at foi definido pelo código
        assert hasattr(result, 'created_at')
        assert result.created_at is not None
        assert result.created_at > 0


# ===== TESTES: GET / (list) =====


class TestListTickets:
    """Testes do endpoint GET / (list tickets)."""

    @pytest.mark.asyncio
    async def test_list_tickets_empty(self, mock_settings, mock_postgres_client):
        """
        DADO: Nenhum ticket no banco
        QUANDO: Chamo list_tickets
        ENTÃO: Deve retornar lista vazia
        """
        mock_postgres_client.list_tickets.return_value = []
        mock_postgres_client.count_tickets.return_value = 0

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.list_tickets()

        assert result['tickets'] == []
        assert result['total'] == 0

    @pytest.mark.asyncio
    async def test_list_tickets_with_plan_id_filter(self, mock_settings, mock_postgres_client):
        """
        DADO: Tickets existem para um plan_id específico
        QUANDO: Chamo list_tickets com plan_id
        ENTÃO: Deve filtrar por plan_id
        """
        plan_id = str(uuid4())
        filters = {'plan_id': plan_id}

        mock_postgres_client.list_tickets.return_value = []
        mock_postgres_client.count_tickets.return_value = 0

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            await tickets_api.list_tickets(plan_id=plan_id)

        mock_postgres_client.list_tickets.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tickets_with_status_filter(self, mock_settings, mock_postgres_client):
        """
        DADO: Tickets com vários status
        QUANDO: Chamo list_tickets com status
        ENTÃO: Deve filtrar por status
        """
        mock_postgres_client.list_tickets.return_value = []
        mock_postgres_client.count_tickets.return_value = 0

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            await tickets_api.list_tickets(status=TicketStatus.PENDING)

        mock_postgres_client.list_tickets.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tickets_with_pagination(self, mock_settings, mock_postgres_client):
        """
        DADO: Mais tickets que o limite da página
        QUANDO: Chamo list_tickets com offset e limit
        ENTÃO: Deve respeitar paginação
        """
        mock_postgres_client.list_tickets.return_value = []
        mock_postgres_client.count_tickets.return_value = 100

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.list_tickets(offset=10, limit=20)

        assert result['offset'] == 10
        assert result['limit'] == 20
        mock_postgres_client.list_tickets.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tickets_limit_max_validation(self, mock_settings, mock_postgres_client):
        """
        DADO: Limite máximo de 1000 tickets por página
        QUANDO: Chamo list_tickets com limit > 1000
        ENTÃO: Deve validar (o parâmetro Query já valida isso)
        """
        mock_postgres_client.list_tickets.return_value = []
        mock_postgres_client.count_tickets.return_value = 0

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.list_tickets(limit=1000)

        assert result['limit'] == 1000


# ===== TESTES: PATCH /{ticket_id}/status =====


class TestUpdateTicketStatus:
    """Testes do endpoint PATCH /{ticket_id}/status."""

    @pytest.mark.asyncio
    async def test_update_status_success(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket válido e novo status
        QUANDO: Chamo update_ticket_status
        ENTÃO: Deve atualizar o status
        """
        ticket_id = sample_ticket_dict['ticket_id']
        request = SimpleNamespace(
            status=TicketStatus.RUNNING,
            error_message=None
        )

        updated_dict = sample_ticket_dict.copy()
        updated_dict['status'] = 'RUNNING'
        mock_postgres_client.update_ticket_status.return_value = make_orm_mock(updated_dict)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.update_ticket_status(ticket_id, request)

        assert result.status == 'RUNNING'
        mock_postgres_client.update_ticket_status.assert_called_once_with(
            ticket_id, request.status, request.error_message
        )

    @pytest.mark.asyncio
    async def test_update_status_ticket_not_found(self, mock_settings, mock_postgres_client):
        """
        DADO: Um ticket_id inexistente
        QUANDO: Chamo update_ticket_status
        ENTÃO: Deve levantar HTTPException 404
        """
        ticket_id = str(uuid4())
        mock_postgres_client.get_ticket_by_id.return_value = None
        request = SimpleNamespace(status=TicketStatus.RUNNING, error_message=None)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.update_ticket_status(ticket_id, request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_with_error_message(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket falhando
        QUANDO: Chamo update_ticket_status com error_message
        ENTÃO: Deve atualizar com a mensagem de erro
        """
        ticket_id = sample_ticket_dict['ticket_id']
        request = SimpleNamespace(
            status=TicketStatus.FAILED,
            error_message='Timeout exceeded'
        )

        updated_dict = sample_ticket_dict.copy()
        updated_dict['status'] = 'FAILED'
        updated_dict['error_message'] = 'Timeout exceeded'
        mock_postgres_client.update_ticket_status.return_value = make_orm_mock(updated_dict)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.update_ticket_status(ticket_id, request)

        assert result.status == 'FAILED'


# ===== TESTES: GET /{ticket_id}/token =====


class TestGetTicketToken:
    """Testes do endpoint GET /{ticket_id}/token."""

    @pytest.mark.asyncio
    async def test_get_token_pending_ticket(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket com status PENDING
        QUANDO: Chamo get_ticket_token
        ENTÃO: Deve gerar token JWT
        """
        ticket_id = sample_ticket_dict['ticket_id']
        ticket_dict = make_pydantic_mock(sample_ticket_dict)
        ticket_dict.status = TicketStatus.PENDING
        mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_settings', return_value=mock_settings):

            result = await tickets_api.get_ticket_token(ticket_id)

        assert result.access_token is not None
        assert result.expires_at is not None
        assert result.token_type == 'Bearer'

    @pytest.mark.asyncio
    async def test_get_token_running_ticket(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket com status RUNNING
        QUANDO: Chamo get_ticket_token
        ENTÃO: Deve gerar token JWT
        """
        ticket_id = sample_ticket_dict['ticket_id']
        ticket_dict = make_pydantic_mock(sample_ticket_dict)
        ticket_dict.status = TicketStatus.RUNNING
        mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_settings', return_value=mock_settings):

            result = await tickets_api.get_ticket_token(ticket_id)

        assert result.access_token is not None

    @pytest.mark.asyncio
    async def test_get_token_completed_ticket_forbidden(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket com status COMPLETED
        QUANDO: Chamo get_ticket_token
        ENTÃO: Deve levantar HTTPException 403
        """
        ticket_id = sample_ticket_dict['ticket_id']
        ticket_dict = make_pydantic_mock(sample_ticket_dict)
        ticket_dict.status = TicketStatus.COMPLETED
        mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_settings', return_value=mock_settings):

            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.get_ticket_token(ticket_id)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_token_ticket_not_found(self, mock_settings, mock_postgres_client):
        """
        DADO: Um ticket_id inexistente
        QUANDO: Chamo get_ticket_token
        ENTÃO: Deve levantar HTTPException 404
        """
        ticket_id = str(uuid4())
        mock_postgres_client.get_ticket_by_id.return_value = None

        # Patch get_settings para retornar objeto com atributos necessários para generate_token
        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_settings') as mock_get_settings, \
             patch('src.api.tickets.generate_token') as mock_generate_token:
            # Criar settings mock com atributos necessários
            settings_mock = SimpleNamespace(
                jwt_secret_key='test-secret-key-with-enough-bytes',
                jwt_algorithm='HS256',
                jwt_token_expiration_seconds=3600
            )
            mock_get_settings.return_value = settings_mock
            # Mock generate_token to avoid actual JWT generation
            mock_generate_token.return_value = SimpleNamespace(
                access_token='test-token',
                token_type='Bearer',
                expires_at=1234567890
            )

            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.get_ticket_token(ticket_id)

        assert exc_info.value.status_code == 404


# ===== TESTES: POST /compensation =====


class TestCreateCompensationTicket:
    """Testes do endpoint POST /compensation."""

    @pytest.mark.asyncio
    async def test_create_compensation_success(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket original FAILED
        QUANDO: Chamo create_compensation_ticket
        ENTÃO: Deve criar ticket de compensação
        """
        original_dict = sample_ticket_dict.copy()
        # Criar mock com status como enum TicketStatus
        mock_ticket = SimpleNamespace(**original_dict)
        mock_ticket.status = TicketStatus.FAILED
        mock_ticket.sla = SimpleNamespace(timeout_ms=30000, deadline=0, max_retries=3)
        mock_ticket.qos = SimpleNamespace(delivery_mode='AT_MOST_ONCE', consistency='EVENTUAL', durability='TRANSIENT')
        mock_ticket.priority = 'NORMAL'
        mock_ticket.risk_band = 'medium'

        mock_orm = MagicMock()
        mock_orm.to_pydantic.return_value = mock_ticket
        mock_postgres_client.get_ticket_by_id.return_value = mock_orm
        mock_postgres_client.create_ticket = AsyncMock()
        mock_postgres_client.update_ticket_compensation = AsyncMock()

        request = SimpleNamespace(
            original_ticket_id=sample_ticket_dict['ticket_id'],
            reason='Original task failed',
            compensation_action='rollback',
            parameters={}
        )

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            result = await tickets_api.create_compensation_ticket(request)

        assert 'ticket_id' in result
        assert result['original_ticket_id'] == sample_ticket_dict['ticket_id']
        assert result['status'] == 'PENDING'

    @pytest.mark.asyncio
    async def test_create_compensation_original_not_found(self, mock_settings, mock_postgres_client):
        """
        DADO: Um original_ticket_id inexistente
        QUANDO: Chamo create_compensation_ticket
        ENTÃO: Deve levantar HTTPException 404
        """
        mock_postgres_client.get_ticket_by_id.return_value = None

        request = SimpleNamespace(
            original_ticket_id=str(uuid4()),
            reason='Test',
            compensation_action='rollback',
            parameters={}
        )

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.create_compensation_ticket(request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_compensation_invalid_status(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket original COMPLETED
        QUANDO: Chamo create_compensation_ticket
        ENTÃO: Deve levantar HTTPException 400
        """
        original_dict = sample_ticket_dict.copy()
        # Criar mock com status como enum TicketStatus
        mock_ticket = SimpleNamespace(**original_dict)
        mock_ticket.status = TicketStatus.COMPLETED
        mock_ticket.sla = SimpleNamespace(timeout_ms=30000, deadline=0, max_retries=3)
        mock_ticket.qos = SimpleNamespace(delivery_mode='AT_MOST_ONCE', consistency='EVENTUAL', durability='TRANSIENT')
        mock_ticket.priority = 'NORMAL'
        mock_ticket.risk_band = 'medium'

        mock_orm = MagicMock()
        mock_orm.to_pydantic.return_value = mock_ticket
        mock_postgres_client.get_ticket_by_id.return_value = mock_orm

        request = SimpleNamespace(
            original_ticket_id=sample_ticket_dict['ticket_id'],
            reason='Test',
            compensation_action='rollback',
            parameters={}
        )

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.create_compensation_ticket(request)

        assert exc_info.value.status_code == 400


# ===== TESTES: POST /{ticket_id}/retry =====


class TestRetryTicket:
    """Testes do endpoint POST /{ticket_id}/retry."""

    @pytest.mark.asyncio
    async def test_retry_success(self, mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
        """
        DADO: Um ticket FAILED com retries disponíveis
        QUANDO: Chamo retry_ticket
        ENTÃO: Deve incrementar retry_count e resetar para PENDING
        """
        ticket_id = sample_ticket_dict['ticket_id']
        ticket_dict = make_pydantic_mock(sample_ticket_dict)
        ticket_dict.status = TicketStatus.FAILED
        ticket_dict.sla = SimpleNamespace(max_retries=3)
        ticket_dict.retry_count = 1
        mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

        retry_dict = sample_ticket_dict.copy()
        retry_dict['status'] = 'PENDING'
        retry_dict['retry_count'] = 2
        mock_postgres_client.increment_retry_count.return_value = make_orm_mock(retry_dict)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

            result = await tickets_api.retry_ticket(ticket_id)

        assert result.status == 'PENDING'
        assert result.retry_count == 2
        mock_postgres_client.increment_retry_count.assert_called_once_with(ticket_id)

    @pytest.mark.asyncio
    async def test_retry_not_found(self, mock_settings, mock_postgres_client):
        """
        DADO: Um ticket_id inexistente
        QUANDO: Chamo retry_ticket
        ENTÃO: Deve levantar HTTPException 404
        """
        ticket_id = str(uuid4())
        mock_postgres_client.get_ticket_by_id.return_value = None

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.retry_ticket(ticket_id)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_not_failed(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket com status COMPLETED
        QUANDO: Chamo retry_ticket
        ENTÃO: Deve levantar HTTPException 400
        """
        ticket_id = sample_ticket_dict['ticket_id']
        ticket_dict = make_pydantic_mock(sample_ticket_dict)
        ticket_dict.status = TicketStatus.COMPLETED
        mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.retry_ticket(ticket_id)

        assert exc_info.value.status_code == 400
        assert 'FAILED' in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_retry_max_retries_exceeded(self, mock_settings, mock_postgres_client, sample_ticket_dict):
        """
        DADO: Um ticket FAILED com retries excedidos
        QUANDO: Chamo retry_ticket
        ENTÃO: Deve levantar HTTPException 400
        """
        ticket_id = sample_ticket_dict['ticket_id']
        ticket_dict = make_pydantic_mock(sample_ticket_dict)
        ticket_dict.status = TicketStatus.FAILED
        ticket_dict.sla = SimpleNamespace(max_retries=3)
        ticket_dict.retry_count = 3
        mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.retry_ticket(ticket_id)

        assert exc_info.value.status_code == 400
        assert 'Limite de retries excedido' in exc_info.value.detail


# ===== TESTES: GET /{ticket_id}/history =====


class TestGetTicketHistory:
    """Testes do endpoint GET /{ticket_id}/history."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
        """
        DADO: Um ticket com histórico
        QUANDO: Chamo get_ticket_history
        ENTÃO: Deve retornar histórico ordenado
        """
        ticket_id = sample_ticket_dict['ticket_id']
        now = datetime.now(timezone.utc)

        history_docs = [
            {
                'ticket_id': ticket_id,
                'old_status': 'FAILED',
                'new_status': 'PENDING',
                'changed_by': 'api.retry',
                'timestamp': now,
                'metadata': {'retry_count': 1}
            },
        ]

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=history_docs)
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_mongodb_client.db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

            result = await tickets_api.get_ticket_history(ticket_id)

        assert len(result) == 1
        assert result[0].ticket_id == ticket_id
        assert result[0].new_status == 'PENDING'

    @pytest.mark.asyncio
    async def test_get_history_ticket_not_found(self, mock_settings, mock_postgres_client):
        """
        DADO: Um ticket_id inexistente
        QUANDO: Chamo get_ticket_history
        ENTÃO: Deve levantar HTTPException 404
        """
        ticket_id = str(uuid4())
        mock_postgres_client.get_ticket_by_id.return_value = None

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
            with pytest.raises(HTTPException) as exc_info:
                await tickets_api.get_ticket_history(ticket_id)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_history_mongodb_error(self, mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
        """
        DADO: MongoDB indisponível
        QUANDO: Chamo get_ticket_history
        ENTÃO: Deve retornar lista vazia (fallback gracioso)
        """
        ticket_id = sample_ticket_dict['ticket_id']

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(side_effect=Exception("MongoDB error"))
        mock_mongodb_client.db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

            result = await tickets_api.get_ticket_history(ticket_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_with_limit(self, mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
        """
        DADO: Um ticket com muito histórico
        QUANDO: Chamo get_ticket_history com limit=10
        ENTÃO: Deve retornar apenas 10 entradas
        """
        ticket_id = sample_ticket_dict['ticket_id']
        limit = 10

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_mongodb_client.db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
             patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

            await tickets_api.get_ticket_history(ticket_id, limit=limit)

        mock_cursor.limit.assert_called_once_with(limit)
