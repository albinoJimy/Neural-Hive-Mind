"""
Testes unitários para validação de configuração e comportamento
de fail-open/fail-closed do MongoDBClient.
"""
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import PyMongoError, DuplicateKeyError

from neural_hive_resilience.circuit_breaker import CircuitBreakerError


# ======================================================
# Testes de Validação de Configuração
# ======================================================

def test_init_raises_if_collection_tickets_not_configured():
    """Valida que ValueError é lançado se mongodb_collection_tickets não configurado."""
    from src.clients.mongodb_client import MongoDBClient

    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets=None,  # Inválido
        mongodb_collection_workflows='workflows'
    )

    with pytest.raises(ValueError, match='mongodb_collection_tickets não configurado'):
        MongoDBClient(config)


def test_init_raises_if_collection_tickets_empty():
    """Valida que ValueError é lançado se mongodb_collection_tickets está vazio."""
    from src.clients.mongodb_client import MongoDBClient

    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='',  # Vazio
        mongodb_collection_workflows='workflows'
    )

    with pytest.raises(ValueError, match='mongodb_collection_tickets não configurado'):
        MongoDBClient(config)


def test_init_logs_configuration():
    """Valida que configuração é logada na inicialização."""
    from src.clients.mongodb_client import MongoDBClient

    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False,
        CIRCUIT_BREAKER_ENABLED=True,
        CIRCUIT_BREAKER_FAIL_MAX=5,
        CIRCUIT_BREAKER_TIMEOUT=60
    )

    with patch('src.clients.mongodb_client.logger') as mock_logger:
        MongoDBClient(config)

        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs['collection_tickets'] == 'execution_tickets'
        assert call_kwargs['fail_open_tickets'] is False


def test_init_succeeds_with_valid_config():
    """Valida que inicialização funciona com config válida."""
    from src.clients.mongodb_client import MongoDBClient

    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False,
        CIRCUIT_BREAKER_ENABLED=False
    )

    client = MongoDBClient(config)
    assert client.config == config


# ======================================================
# Testes de Fail-Open vs Fail-Closed
# ======================================================

@pytest.fixture
def mock_config_fail_closed():
    """Config com fail-open=False."""
    return types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False,
        CIRCUIT_BREAKER_ENABLED=False,
        retry_max_attempts=1,
        retry_initial_interval_ms=1,
        retry_backoff_coefficient=1,
        retry_max_interval_ms=10
    )


@pytest.fixture
def mock_config_fail_open():
    """Config com fail-open=True."""
    return types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=True,
        CIRCUIT_BREAKER_ENABLED=False,
        retry_max_attempts=1,
        retry_initial_interval_ms=1,
        retry_backoff_coefficient=1,
        retry_max_interval_ms=10
    )


@pytest.mark.asyncio
async def test_save_ticket_fail_closed_propagates_pymongo_error(mock_config_fail_closed):
    """Valida que erro PyMongo é propagado quando fail-closed."""
    from src.clients.mongodb_client import MongoDBClient

    client = MongoDBClient(mock_config_fail_closed)
    client.execution_tickets = AsyncMock()
    client.execution_tickets.insert_one = AsyncMock(side_effect=PyMongoError('Connection lost'))

    ticket = {'ticket_id': 'test-1', 'plan_id': 'plan-1'}

    with patch('src.clients.mongodb_client.get_metrics') as mock_metrics:
        mock_metrics.return_value = MagicMock()

        with pytest.raises(RuntimeError, match='Falha crítica'):
            await client.save_execution_ticket(ticket)


@pytest.mark.asyncio
async def test_save_ticket_fail_open_continues(mock_config_fail_open):
    """Valida que erro PyMongo não propaga quando fail-open."""
    from src.clients.mongodb_client import MongoDBClient

    client = MongoDBClient(mock_config_fail_open)
    client.execution_tickets = AsyncMock()
    client.execution_tickets.insert_one = AsyncMock(side_effect=PyMongoError('Connection lost'))

    ticket = {'ticket_id': 'test-1', 'plan_id': 'plan-1'}

    with patch('src.clients.mongodb_client.get_metrics') as mock_metrics:
        mock_metrics_instance = MagicMock()
        mock_metrics.return_value = mock_metrics_instance

        # Não deve lançar exceção
        await client.save_execution_ticket(ticket)

        # Deve registrar métrica de fail-open
        mock_metrics_instance.record_mongodb_persistence_fail_open.assert_called_once_with(
            'execution_tickets'
        )


@pytest.mark.asyncio
async def test_save_ticket_circuit_breaker_always_propagates(mock_config_fail_open):
    """Valida que CircuitBreakerError sempre propaga, mesmo com fail-open."""
    from src.clients.mongodb_client import MongoDBClient

    # Config com circuit breaker habilitado e fail-open=True
    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=True,  # fail-open ativo
        CIRCUIT_BREAKER_ENABLED=True,
        CIRCUIT_BREAKER_FAIL_MAX=5,
        CIRCUIT_BREAKER_TIMEOUT=60,
        CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30,
        service_name='test',
        retry_max_attempts=1,
        retry_initial_interval_ms=1,
        retry_backoff_coefficient=1,
        retry_max_interval_ms=10
    )

    client = MongoDBClient(config)
    client.execution_tickets = AsyncMock()

    # Simular circuit breaker aberto
    client.execution_ticket_breaker = MagicMock()
    client.execution_ticket_breaker.call_async = AsyncMock(
        side_effect=CircuitBreakerError('Circuit open')
    )

    ticket = {'ticket_id': 'test-1', 'plan_id': 'plan-1'}

    with patch('src.clients.mongodb_client.get_metrics') as mock_metrics:
        mock_metrics.return_value = MagicMock()

        # Deve propagar CircuitBreakerError mesmo com fail-open
        with pytest.raises(CircuitBreakerError):
            await client.save_execution_ticket(ticket)


# ======================================================
# Testes de Retry
# ======================================================

@pytest.mark.asyncio
async def test_save_ticket_retries_on_transient_error(mock_config_fail_closed):
    """Valida que erros transitórios são retried."""
    from src.clients.mongodb_client import MongoDBClient

    # Configurar para 3 tentativas
    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False,
        CIRCUIT_BREAKER_ENABLED=False,
        retry_max_attempts=3,
        retry_initial_interval_ms=1,
        retry_backoff_coefficient=1,
        retry_max_interval_ms=10
    )

    client = MongoDBClient(config)
    client.execution_tickets = AsyncMock()

    # Primeira chamada falha, segunda sucede
    client.execution_tickets.insert_one = AsyncMock(
        side_effect=[PyMongoError('Transient'), None]
    )

    ticket = {'ticket_id': 'test-retry', 'plan_id': 'plan-1'}

    with patch('src.clients.mongodb_client.get_metrics') as mock_metrics:
        mock_metrics.return_value = MagicMock()

        await client.save_execution_ticket(ticket)

        # Deve ter tentado 2 vezes
        assert client.execution_tickets.insert_one.await_count == 2


@pytest.mark.asyncio
async def test_save_ticket_no_retry_on_duplicate_key(mock_config_fail_closed):
    """Valida que DuplicateKeyError não faz retry infinito, faz update."""
    from src.clients.mongodb_client import MongoDBClient

    client = MongoDBClient(mock_config_fail_closed)
    client.execution_tickets = AsyncMock()

    # Insert falha com duplicate, replace sucede
    client.execution_tickets.insert_one = AsyncMock(
        side_effect=DuplicateKeyError('Duplicate key')
    )
    client.execution_tickets.replace_one = AsyncMock(return_value=None)

    ticket = {'ticket_id': 'test-dup', 'plan_id': 'plan-1'}

    with patch('src.clients.mongodb_client.get_metrics') as mock_metrics:
        mock_metrics.return_value = MagicMock()

        await client.save_execution_ticket(ticket)

        # Insert chamado 1 vez, depois replace
        assert client.execution_tickets.insert_one.await_count == 1
        assert client.execution_tickets.replace_one.await_count == 1


# ======================================================
# Testes de Índices Esperados
# ======================================================

def test_expected_indexes_defined():
    """Valida que EXPECTED_INDEXES está definido corretamente."""
    from src.clients.mongodb_client import MongoDBClient

    assert hasattr(MongoDBClient, 'EXPECTED_INDEXES')
    assert 'execution_tickets' in MongoDBClient.EXPECTED_INDEXES
    assert 'cognitive_ledger' in MongoDBClient.EXPECTED_INDEXES
    assert 'workflows' in MongoDBClient.EXPECTED_INDEXES

    # Verificar índices de execution_tickets
    expected_ticket_indexes = MongoDBClient.EXPECTED_INDEXES['execution_tickets']
    assert 'ticket_id_1' in expected_ticket_indexes
    assert 'plan_id_1' in expected_ticket_indexes
    assert 'status_1' in expected_ticket_indexes


# ======================================================
# Testes de Métricas de Validação de Índices
# ======================================================

@pytest.mark.asyncio
async def test_validate_indexes_records_metrics():
    """Valida que validate_indexes registra métricas."""
    from src.clients.mongodb_client import MongoDBClient

    config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost',
        mongodb_database='test',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False,
        CIRCUIT_BREAKER_ENABLED=False,
        retry_max_attempts=1,
        retry_initial_interval_ms=1,
        retry_backoff_coefficient=1,
        retry_max_interval_ms=10
    )

    client = MongoDBClient(config)

    # Mock do db com coleções
    mock_collection = AsyncMock()
    mock_collection.list_indexes = MagicMock(return_value=AsyncMock())
    mock_collection.list_indexes.return_value.to_list = AsyncMock(return_value=[
        {'name': '_id_'},
        {'name': 'ticket_id_1'},
        {'name': 'plan_id_1'},
        {'name': 'intent_id_1'},
        {'name': 'decision_id_1'},
        {'name': 'status_1'},
        {'name': 'plan_id_1_created_at_-1'}
    ])

    client.db = MagicMock()
    client.db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch('src.clients.mongodb_client.get_metrics') as mock_metrics:
        mock_metrics_instance = MagicMock()
        mock_metrics.return_value = mock_metrics_instance

        await client.validate_indexes()

        # Deve ter registrado validação
        mock_metrics_instance.record_mongodb_index_validation.assert_called()
