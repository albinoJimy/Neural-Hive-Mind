"""
Testes para persistência MongoDB no MongoDBClient com retry e fail-open.
"""
import types
from unittest.mock import AsyncMock, call

import pytest
from pymongo.errors import PyMongoError

from src.clients.mongodb_client import MongoDBClient


class FakeCollection:
    """Coleção fake com métodos assíncronos para testes."""

    def __init__(self):
        self.insert_one = AsyncMock()
        self.replace_one = AsyncMock()
        self.create_index = AsyncMock()


@pytest.fixture
def mock_config():
    """Configuração mínima para MongoDBClient."""
    return types.SimpleNamespace(
        mongodb_uri='mongodb://localhost:27017',
        mongodb_database='test-db',
        mongodb_collection_tickets='execution_tickets',
        mongodb_collection_workflows='workflows',
        retry_max_attempts=3,
        retry_initial_interval_ms=1,
        retry_backoff_coefficient=1,
        retry_max_interval_ms=10
    )


@pytest.fixture
def client(mock_config):
    """Instância do MongoDBClient com coleções mockadas."""
    mongo_client = MongoDBClient(mock_config)
    mongo_client.cognitive_ledger = FakeCollection()
    mongo_client.execution_tickets = FakeCollection()
    mongo_client.workflows = FakeCollection()
    mongo_client.validation_audit = FakeCollection()
    mongo_client.workflow_results = FakeCollection()
    mongo_client.incidents = FakeCollection()
    mongo_client.telemetry_buffer = FakeCollection()
    return mongo_client


@pytest.mark.asyncio
async def test_save_validation_audit_success(client):
    """Deve persistir validação com hash e workflow_id."""
    await client.save_validation_audit('plan-1', {'valid': True}, 'wf-1')

    assert client.validation_audit.insert_one.await_count == 1
    saved_doc = client.validation_audit.insert_one.await_args.args[0]
    assert saved_doc['plan_id'] == 'plan-1'
    assert saved_doc['workflow_id'] == 'wf-1'
    assert saved_doc['hash']
    assert 'timestamp' in saved_doc


@pytest.mark.asyncio
async def test_save_validation_audit_retry(client):
    """Deve tentar novamente em erro transitório e completar."""
    client.validation_audit.insert_one.side_effect = [PyMongoError('boom'), None]

    await client.save_validation_audit('plan-2', {'valid': False}, 'wf-2')

    assert client.validation_audit.insert_one.await_count == 2


@pytest.mark.asyncio
async def test_save_validation_audit_fail_open(client):
    """Erros permanentes não devem propagar exceção."""
    client.validation_audit.insert_one.side_effect = PyMongoError('down')

    await client.save_validation_audit('plan-3', {'valid': True}, 'wf-3')

    assert client.validation_audit.insert_one.await_count >= 1


@pytest.mark.asyncio
async def test_validation_audit_hash_consistency(client):
    """Hash deve ser determinístico para o mesmo resultado."""
    validation_result = {'valid': True, 'errors': [], 'warnings': []}

    await client.save_validation_audit('plan-4', validation_result, 'wf-4')
    first_hash = client.validation_audit.insert_one.await_args.args[0]['hash']

    client.validation_audit.insert_one.reset_mock()

    await client.save_validation_audit('plan-4', validation_result, 'wf-4')
    second_hash = client.validation_audit.insert_one.await_args.args[0]['hash']

    assert first_hash == second_hash


@pytest.mark.asyncio
async def test_save_workflow_result_upsert(client):
    """Deve fazer upsert com _id = workflow_id."""
    workflow_result = {'workflow_id': 'wf-10', 'status': 'SUCCESS', 'metrics': {'total_tickets': 1}}

    await client.save_workflow_result(workflow_result)

    client.workflow_results.replace_one.assert_awaited_once()
    args, kwargs = client.workflow_results.replace_one.await_args
    assert args[0] == {'_id': 'wf-10'}
    assert kwargs['upsert'] is True


@pytest.mark.asyncio
async def test_save_workflow_result_retry(client):
    """Deve fazer retry em falha temporária."""
    client.workflow_results.replace_one.side_effect = [PyMongoError('retry'), None]

    await client.save_workflow_result({'workflow_id': 'wf-20', 'status': 'PARTIAL'})

    assert client.workflow_results.replace_one.await_count == 2


@pytest.mark.asyncio
async def test_save_incident_fail_open(client):
    """Persistência de incidentes é fail-open."""
    client.incidents.insert_one.side_effect = PyMongoError('incident failure')

    await client.save_incident({'workflow_id': 'wf-30', 'type': 'E', 'severity': 'CRITICAL'})

    assert client.incidents.insert_one.await_count >= 1


@pytest.mark.asyncio
async def test_save_telemetry_buffer_success(client):
    """Deve persistir frame de telemetria em buffer."""
    frame = {'correlation': {'workflow_id': 'wf-40'}, 'source': 'orchestrator'}

    await client.save_telemetry_buffer(frame)

    client.telemetry_buffer.insert_one.assert_awaited_once_with(frame)


@pytest.mark.asyncio
async def test_create_indexes(client):
    """Cria índices esperados para coleções novas."""
    await client._create_indexes()

    assert client.validation_audit.create_index.await_count >= 4
    workflow_index_calls = client.workflow_results.create_index.await_args_list
    assert any(call.args[0] == 'workflow_id' and call.kwargs.get('unique') for call in workflow_index_calls)
    telemetry_index_calls = client.telemetry_buffer.create_index.await_args_list
    assert any(call.args[0] == 'retry_count' for call in telemetry_index_calls)
