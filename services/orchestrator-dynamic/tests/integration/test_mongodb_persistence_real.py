"""
Testes de integração para persistência MongoDB com container real.

Usa testcontainers-python para validar persistência real de execution tickets.

NOTA: Estes testes requerem Docker disponível e podem ser lentos.
Use markers para filtrar: pytest -m integration
"""
import types
from datetime import datetime
from typing import Generator

import pytest
from pymongo.errors import PyMongoError

# Verificar se testcontainers está disponível
try:
    from testcontainers.mongodb import MongoDbContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    MongoDbContainer = None


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TESTCONTAINERS_AVAILABLE,
        reason='testcontainers-python não instalado'
    )
]


@pytest.fixture(scope='module')
def mongodb_container() -> Generator:
    """
    Container MongoDB para testes de integração.

    Usa escopo de módulo para reutilizar container entre testes.
    """
    if not TESTCONTAINERS_AVAILABLE:
        pytest.skip('testcontainers-python não instalado')

    with MongoDbContainer('mongo:7.0') as container:
        yield container


@pytest.fixture
def config_fail_closed(mongodb_container) -> types.SimpleNamespace:
    """Config com fail-open=False (modo produção)."""
    return types.SimpleNamespace(
        mongodb_uri=mongodb_container.get_connection_url(),
        mongodb_database='test_neural_hive',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_MAX_POOL_SIZE=10,
        MONGODB_MIN_POOL_SIZE=1,
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False,
        MONGODB_FAIL_OPEN_VALIDATION_AUDIT=True,
        MONGODB_FAIL_OPEN_WORKFLOW_RESULTS=True,
        CIRCUIT_BREAKER_ENABLED=False,
        CIRCUIT_BREAKER_FAIL_MAX=5,
        CIRCUIT_BREAKER_TIMEOUT=60,
        service_name='test-orchestrator',
        retry_max_attempts=3,
        retry_initial_interval_ms=100,
        retry_backoff_coefficient=1.5,
        retry_max_interval_ms=1000
    )


@pytest.fixture
def config_fail_open(mongodb_container) -> types.SimpleNamespace:
    """Config com fail-open=True (modo desenvolvimento)."""
    config = types.SimpleNamespace(
        mongodb_uri=mongodb_container.get_connection_url(),
        mongodb_database='test_neural_hive',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        MONGODB_MAX_POOL_SIZE=10,
        MONGODB_MIN_POOL_SIZE=1,
        MONGODB_FAIL_OPEN_EXECUTION_TICKETS=True,
        MONGODB_FAIL_OPEN_VALIDATION_AUDIT=True,
        MONGODB_FAIL_OPEN_WORKFLOW_RESULTS=True,
        CIRCUIT_BREAKER_ENABLED=False,
        CIRCUIT_BREAKER_FAIL_MAX=5,
        CIRCUIT_BREAKER_TIMEOUT=60,
        service_name='test-orchestrator',
        retry_max_attempts=3,
        retry_initial_interval_ms=100,
        retry_backoff_coefficient=1.5,
        retry_max_interval_ms=1000
    )
    return config


@pytest.fixture
async def mongodb_client_real(config_fail_closed):
    """Cliente MongoDB conectado ao container de teste."""
    from src.clients.mongodb_client import MongoDBClient

    client = MongoDBClient(config_fail_closed)
    await client.initialize()
    yield client
    await client.close()


@pytest.fixture
def sample_ticket() -> dict:
    """Ticket de execução de exemplo para testes."""
    return {
        'ticket_id': f'test-ticket-{datetime.now().timestamp()}',
        'plan_id': 'test-plan-1',
        'intent_id': 'test-intent-1',
        'decision_id': 'test-decision-1',
        'task_id': 'test-task-1',
        'status': 'PENDING',
        'priority': 'NORMAL',
        'risk_band': 'medium',
        'sla': {
            'deadline': int(datetime.now().timestamp() * 1000) + 3600000,
            'timeout_ms': 60000,
            'max_retries': 3
        },
        'qos': {
            'delivery_mode': 'AT_LEAST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'PERSISTENT'
        },
        'created_at': int(datetime.now().timestamp() * 1000),
        'metadata': {
            'workflow_id': 'test-workflow-1',
            'generated_by': 'test-suite'
        },
        'schema_version': 1
    }


# ======================================================
# Testes de Criação de Documento
# ======================================================

@pytest.mark.asyncio
async def test_save_execution_ticket_creates_document(mongodb_client_real, sample_ticket):
    """Valida que documento é criado corretamente no MongoDB."""
    await mongodb_client_real.save_execution_ticket(sample_ticket)

    # Buscar documento salvo
    saved = await mongodb_client_real.get_ticket(sample_ticket['ticket_id'])

    assert saved is not None
    assert saved['ticket_id'] == sample_ticket['ticket_id']
    assert saved['plan_id'] == sample_ticket['plan_id']
    assert saved['status'] == 'PENDING'
    assert saved['_id'] == sample_ticket['ticket_id']


@pytest.mark.asyncio
async def test_save_execution_ticket_updates_existing(mongodb_client_real, sample_ticket):
    """Valida que ticket existente é atualizado (upsert)."""
    # Primeiro save
    await mongodb_client_real.save_execution_ticket(sample_ticket)

    # Atualizar status
    updated_ticket = sample_ticket.copy()
    updated_ticket['status'] = 'RUNNING'

    await mongodb_client_real.save_execution_ticket(updated_ticket)

    # Verificar atualização
    saved = await mongodb_client_real.get_ticket(sample_ticket['ticket_id'])
    assert saved['status'] == 'RUNNING'


# ======================================================
# Testes de Validação de Índices
# ======================================================

@pytest.mark.asyncio
async def test_indexes_created_correctly(mongodb_client_real):
    """Valida que índices são criados corretamente."""
    collection = mongodb_client_real.execution_tickets
    indexes = await collection.list_indexes().to_list(length=None)
    index_names = {idx['name'] for idx in indexes}

    # Índices esperados (exceto _id_ que sempre existe)
    expected_indexes = [
        'ticket_id_1',
        'plan_id_1',
        'intent_id_1',
        'decision_id_1',
        'status_1',
    ]

    for expected in expected_indexes:
        assert expected in index_names, f'Índice {expected} não encontrado. Existentes: {index_names}'


@pytest.mark.asyncio
async def test_ticket_id_index_is_unique(mongodb_client_real):
    """Valida que índice ticket_id é único."""
    collection = mongodb_client_real.execution_tickets
    indexes = await collection.list_indexes().to_list(length=None)

    ticket_id_index = next(
        (idx for idx in indexes if idx['name'] == 'ticket_id_1'),
        None
    )

    assert ticket_id_index is not None
    assert ticket_id_index.get('unique') is True


# ======================================================
# Testes de Ensure Collection Exists
# ======================================================

@pytest.mark.asyncio
async def test_ensure_collection_exists_creates_collection(mongodb_client_real):
    """Valida que coleção é criada se não existir."""
    test_collection = f'test_collection_{datetime.now().timestamp()}'

    result = await mongodb_client_real.ensure_collection_exists(test_collection)

    assert result is True

    # Verificar que coleção existe
    existing = await mongodb_client_real.db.list_collection_names()
    assert test_collection in existing


@pytest.mark.asyncio
async def test_ensure_collection_exists_idempotent(mongodb_client_real):
    """Valida que chamada repetida não causa erro."""
    # Chamar múltiplas vezes para mesma coleção
    result1 = await mongodb_client_real.ensure_collection_exists('execution_tickets')
    result2 = await mongodb_client_real.ensure_collection_exists('execution_tickets')

    assert result1 is True
    assert result2 is True


# ======================================================
# Testes de Validate Indexes
# ======================================================

@pytest.mark.asyncio
async def test_validate_indexes_no_errors_when_all_present(mongodb_client_real):
    """Valida que validate_indexes não loga erros quando índices estão corretos."""
    # Índices já foram criados em initialize()
    # Apenas verificar que método executa sem exceção
    await mongodb_client_real.validate_indexes()
    # Sucesso se não lançou exceção


# ======================================================
# Testes de Fail-Open vs Fail-Closed
# ======================================================

@pytest.mark.asyncio
async def test_initialization_validates_collection_config():
    """Valida que inicialização falha se collection_tickets não configurado."""
    from src.clients.mongodb_client import MongoDBClient

    invalid_config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost:27017',
        mongodb_database='test',
        mongodb_collection_tickets=None,  # Inválido
        mongodb_collection_workflows='workflows'
    )

    with pytest.raises(ValueError, match='mongodb_collection_tickets'):
        MongoDBClient(invalid_config)


@pytest.mark.asyncio
async def test_initialization_validates_empty_collection_config():
    """Valida que inicialização falha se collection_tickets está vazio."""
    from src.clients.mongodb_client import MongoDBClient

    invalid_config = types.SimpleNamespace(
        mongodb_uri='mongodb://localhost:27017',
        mongodb_database='test',
        mongodb_collection_tickets='',  # Vazio
        mongodb_collection_workflows='workflows'
    )

    with pytest.raises(ValueError, match='mongodb_collection_tickets'):
        MongoDBClient(invalid_config)


# ======================================================
# Testes de Métricas
# ======================================================

@pytest.mark.asyncio
async def test_save_ticket_records_duration_metrics(mongodb_client_real, sample_ticket):
    """Valida que métricas de duração são registradas."""
    from unittest.mock import patch, MagicMock

    with patch('src.clients.mongodb_client.get_metrics') as mock_get_metrics:
        mock_metrics = MagicMock()
        mock_get_metrics.return_value = mock_metrics

        await mongodb_client_real.save_execution_ticket(sample_ticket)

        mock_metrics.record_mongodb_persistence_duration.assert_called()
        call_args = mock_metrics.record_mongodb_persistence_duration.call_args
        assert call_args[0][0] == 'execution_tickets'


# ======================================================
# Testes de Coleções Críticas
# ======================================================

@pytest.mark.asyncio
async def test_cognitive_ledger_created(mongodb_client_real):
    """Valida que coleção cognitive_ledger existe."""
    existing = await mongodb_client_real.db.list_collection_names()
    assert 'cognitive_ledger' in existing


@pytest.mark.asyncio
async def test_validation_audit_created(mongodb_client_real):
    """Valida que coleção validation_audit existe."""
    existing = await mongodb_client_real.db.list_collection_names()
    assert 'validation_audit' in existing


@pytest.mark.asyncio
async def test_workflow_results_created(mongodb_client_real):
    """Valida que coleção workflow_results existe."""
    existing = await mongodb_client_real.db.list_collection_names()
    assert 'workflow_results' in existing
