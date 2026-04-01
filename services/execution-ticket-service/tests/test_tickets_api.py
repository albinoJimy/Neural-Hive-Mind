"""Testes para API de Tickets."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

# Importar módulos - path configurado no conftest.py
from src.api import tickets as tickets_api
from src.models import TicketStatus


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
        schemas_base_path=str(Path(__file__).resolve().parents[1] / "schemas"),
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
    )


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
        'priority': 'MEDIUM',
        'risk_band': 'MEDIUM',
        'sla': {'timeout_ms': 30000, 'deadline': None, 'max_retries': 3},
        'qos': {
            'delivery_mode': 'AT_MOST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'TRANSIENT'
        },
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


def make_pydantic_mock(ticket_dict: dict) -> SimpleNamespace:
    """Cria mock de Pydantic model."""
    return SimpleNamespace(**ticket_dict)


def make_orm_mock(ticket_dict: dict) -> MagicMock:
    """Cria mock de ORM com to_pydantic."""
    mock_orm = MagicMock()
    mock_orm.to_pydantic.return_value = make_pydantic_mock(ticket_dict)
    return mock_orm


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


# Tests for retry endpoint
@pytest.mark.asyncio
async def test_retry_ticket_success(mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
    """Testa retry de ticket com sucesso."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Configurar ticket como FAILED
    ticket_dict = make_pydantic_mock(sample_ticket_dict)
    ticket_dict.status = TicketStatus.FAILED
    ticket_dict.sla = SimpleNamespace(max_retries=3)
    ticket_dict.retry_count = 1
    mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
         patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

        result = await tickets_api.retry_ticket(ticket_id)

        assert result.status == 'PENDING'
        assert result.retry_count == 1
        mock_postgres_client.increment_retry_count.assert_called_once_with(ticket_id)
        mock_mongodb_client.log_status_change.assert_called_once()


@pytest.mark.asyncio
async def test_retry_ticket_not_found(mock_settings, mock_postgres_client):
    """Testa retry de ticket inexistente."""
    ticket_id = str(uuid4())
    mock_postgres_client.get_ticket_by_id.return_value = None

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
        with pytest.raises(HTTPException) as exc_info:
            await tickets_api.retry_ticket(ticket_id)

        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_retry_ticket_not_failed(mock_settings, mock_postgres_client, sample_ticket_dict):
    """Testa retry de ticket que não está FAILED."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Configurar ticket como COMPLETED
    ticket_dict = make_pydantic_mock(sample_ticket_dict)
    ticket_dict.status = TicketStatus.COMPLETED
    mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
        with pytest.raises(HTTPException) as exc_info:
            await tickets_api.retry_ticket(ticket_id)

        assert exc_info.value.status_code == 400
        assert 'FAILED' in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_ticket_max_retries_exceeded(mock_settings, mock_postgres_client, sample_ticket_dict):
    """Testa retry quando limite de retries foi excedido."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Configurar ticket como FAILED com retries excedidos
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


# Tests for history endpoint
@pytest.mark.asyncio
async def test_get_ticket_history_success(mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
    """Testa busca de histórico de ticket com sucesso."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Mock do histórico MongoDB
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
        {
            'ticket_id': ticket_id,
            'old_status': 'RUNNING',
            'new_status': 'FAILED',
            'changed_by': 'worker',
            'timestamp': now - timedelta(minutes=5),
            'metadata': {'error': 'Timeout'}
        }
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

        assert len(result) == 2
        assert result[0].ticket_id == ticket_id
        assert result[0].new_status == 'PENDING'
        assert result[0].old_status == 'FAILED'
        assert result[0].changed_by == 'api.retry'
        assert result[1].new_status == 'FAILED'
        assert result[1].old_status == 'RUNNING'


@pytest.mark.asyncio
async def test_get_ticket_history_not_found(mock_settings, mock_postgres_client):
    """Testa busca de histórico de ticket inexistente."""
    ticket_id = str(uuid4())
    mock_postgres_client.get_ticket_by_id.return_value = None

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
        with pytest.raises(HTTPException) as exc_info:
            await tickets_api.get_ticket_history(ticket_id)

        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_ticket_history_mongodb_error(mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
    """Testa busca de histórico quando MongoDB falha."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Mock para lançar exceção no MongoDB
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(side_effect=Exception("MongoDB error"))
    mock_mongodb_client.db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
         patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

        result = await tickets_api.get_ticket_history(ticket_id)

        # Deve retornar lista vazia em caso de erro
        assert result == []


# Tests for list tickets with additional filters
@pytest.mark.asyncio
async def test_list_tickets_with_filters(mock_settings, mock_postgres_client):
    """Testa listagem de tickets com filtros."""
    mock_postgres_client.list_tickets.return_value = []
    mock_postgres_client.count_tickets.return_value = 0

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
        # Pass status as enum (not string)
        result = await tickets_api.list_tickets(plan_id='plan-123', status=TicketStatus.PENDING)

        mock_postgres_client.list_tickets.assert_called_once()
        mock_postgres_client.count_tickets.assert_called_once()
        assert 'tickets' in result
        assert 'total' in result


# Tests for create ticket endpoint
@pytest.mark.asyncio
async def test_create_ticket_success(mock_settings, mock_postgres_client, sample_ticket_dict):
    """Testa criação de ticket com sucesso."""
    ticket_data = {
        'plan_id': sample_ticket_dict['plan_id'],
        'intent_id': sample_ticket_dict['intent_id'],
        'decision_id': sample_ticket_dict['decision_id'],
        'task_id': 'task-123',
        'task_type': 'BUILD',
        'description': 'Test ticket',
        'priority': 'NORMAL',  # Correct Priority enum value
        'risk_band': 'medium',  # Correct RiskBand enum value (lowercase)
        'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},  # deadline as int
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

    # Mock kafka producer to raise exception
    mock_producer = AsyncMock()
    mock_producer.publish_ticket = AsyncMock(side_effect=Exception("Kafka not available"))

    # Patch the kafka module path
    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
         patch('src.kafka.producer.get_kafka_producer', return_value=mock_producer), \
         patch('src.api.tickets.asyncio') as mock_asyncio:

        mock_asyncio.create_task = MagicMock()

        result = await tickets_api.create_ticket(ticket_data)

        mock_postgres_client.create_ticket.assert_called_once()
        assert result is not None


# Tests for get ticket
@pytest.mark.asyncio
async def test_get_ticket_success(mock_settings, mock_postgres_client, sample_ticket_dict):
    """Testa busca de ticket por ID com sucesso."""
    ticket_id = sample_ticket_dict['ticket_id']

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
        result = await tickets_api.get_ticket(ticket_id)

        mock_postgres_client.get_ticket_by_id.assert_called_once_with(ticket_id)
        assert result is not None


@pytest.mark.asyncio
async def test_get_ticket_not_found(mock_settings, mock_postgres_client):
    """Testa busca de ticket inexistente."""
    ticket_id = str(uuid4())
    mock_postgres_client.get_ticket_by_id.return_value = None

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client):
        with pytest.raises(HTTPException) as exc_info:
            await tickets_api.get_ticket(ticket_id)

        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_ticket_status_success(mock_settings, mock_postgres_client, mock_mongodb_client, sample_ticket_dict):
    """Testa atualização de status com sucesso."""
    ticket_id = sample_ticket_dict['ticket_id']

    request_data = SimpleNamespace(
        status=TicketStatus.RUNNING,
        error_message=None
    )

    # Configurar ticket retornado
    updated_dict = sample_ticket_dict.copy()
    updated_dict['status'] = 'RUNNING'
    mock_postgres_client.update_ticket_status.return_value = make_orm_mock(updated_dict)

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
         patch('src.api.tickets.get_mongodb_client', return_value=mock_mongodb_client):

        result = await tickets_api.update_ticket_status(ticket_id, request_data)

        mock_postgres_client.update_ticket_status.assert_called_once()
        assert result.status == 'RUNNING'


@pytest.mark.asyncio
async def test_get_ticket_token_success(mock_settings, mock_postgres_client, sample_ticket_dict):
    """Testa geração de token JWT com sucesso."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Configurar ticket como PENDING
    ticket_dict = make_pydantic_mock(sample_ticket_dict)
    ticket_dict.status = TicketStatus.PENDING
    mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
         patch('src.api.tickets.get_settings', return_value=mock_settings):

        result = await tickets_api.get_ticket_token(ticket_id)

        assert result.access_token is not None
        assert result.expires_at is not None


@pytest.mark.asyncio
async def test_get_ticket_token_invalid_status(mock_settings, mock_postgres_client, sample_ticket_dict):
    """Testa geração de token para ticket com status inválido."""
    ticket_id = sample_ticket_dict['ticket_id']

    # Configurar ticket como COMPLETED
    ticket_dict = make_pydantic_mock(sample_ticket_dict)
    ticket_dict.status = TicketStatus.COMPLETED
    mock_postgres_client.get_ticket_by_id.return_value.to_pydantic.return_value = ticket_dict

    with patch('src.api.tickets.get_postgres_client', return_value=mock_postgres_client), \
         patch('src.api.tickets.get_settings', return_value=mock_settings):

        with pytest.raises(HTTPException) as exc_info:
            await tickets_api.get_ticket_token(ticket_id)

        assert exc_info.value.status_code == 403
