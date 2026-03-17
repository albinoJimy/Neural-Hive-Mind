"""
Testes de integração para Migration 001 - Active Learning Schema.

Verifica que a migration cria corretamente as coleções e índices.

NOTA: Estes testes requerem uma instância MongoDB real rodando.
Execute com: docker-compose up -d mongodb
"""

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime
import os

# Import das funções de migration
try:
    from src.database.migrations.m001_active_learning_schema import (
        create_active_learning_queue_collection,
        update_specialist_feedback_collection,
        verify_schema
    )
except ImportError:
    pytest.skip("Migration module not available", allow_module_level=True)


# Skip todos os testes de integração se não houver MongoDB real
needs_mongodb = pytest.mark.skipif(
    not os.getenv('MONGODB_URI') and not os.getenv('TEST_MONGODB'),
    reason="Requer MongoDB real (defina MONGODB_URI ou TEST_MONGODB)"
)


@needs_mongodb
@pytest.mark.asyncio
async def test_create_active_learning_queue_collection(mongo_client):
    """Testa criação da coleção active_learning_queue com índices."""
    db_name = mongo_client.name
    await create_active_learning_queue_collection(mongo_client, db_name)

    # Verificar que coleção existe
    collections = await mongo_client[db_name].list_collection_names()
    assert 'active_learning_queue' in collections

    # Verificar índices
    collection = mongo_client[db_name]['active_learning_queue']
    indexes = await collection.list_indexes()
    index_names = [idx['name'] for idx in indexes]

    # Índices esperados
    expected_indexes = [
        '_id_',  # Default MongoDB index
        'idx_queue_id',
        'idx_plan_id',
        'idx_status',
        'idx_expires_at',
        'idx_domain',
        'idx_confidence',
        'idx_predicted_decision'
    ]

    for expected in expected_indexes:
        assert expected in index_names, f"Índice {expected} não encontrado"


@needs_mongodb
@pytest.mark.asyncio
async def test_update_specialist_feedback_collection(mongo_client):
    """Testa atualização da coleção specialist_feedback."""
    db_name = mongo_client.name

    # Inserir documento de teste sem os novos campos
    collection = mongo_client[db_name]['specialist_feedback']
    await collection.insert_one({
        'feedback_id': 'test-1',
        'human_recommendation': 'approve'
    })

    # Executar migration
    await update_specialist_feedback_collection(mongo_client, db_name)

    # Verificar que campo foi adicionado
    doc = await collection.find_one({'feedback_id': 'test-1'})
    assert doc.get('balanced_dataset') is False

    # Verificar índices
    indexes = await collection.list_indexes()
    index_names = [idx['name'] for idx in indexes]

    assert 'idx_balanced_dataset' in index_names
    assert 'idx_collection_method' in index_names
    assert 'idx_balanced_recommendation' in index_names


@pytest.mark.asyncio
async def test_verify_schema(mongo_client):
    """Testa verificação do schema."""
    db_name = mongo_client.name

    # Criar estrutura mínima
    await mongo_client[db_name]['active_learning_queue'].create_index('queue_id', unique=True)
    await mongo_client[db_name]['specialist_feedback'].create_index('balanced_dataset')

    # Executar verificação
    result = await verify_schema(mongo_client, db_name)

    assert result['timestamp'] is not None
    assert 'active_learning_queue' in result['collections']
    assert 'specialist_feedback' in result['collections']
    assert 'active_learning_queue' in result['indexes']
    assert 'specialist_feedback' in result['indexes']


@needs_mongodb
@pytest.mark.asyncio
async def test_active_learning_queue_document_structure(mongo_client):
    """Testa que documentos na fila seguem o schema esperado."""
    db_name = mongo_client.name
    collection = mongo_client[db_name]['active_learning_queue']

    # Documento de teste
    test_doc = {
        'queue_id': 'test-queue-1',
        'plan_id': 'plan-1',
        'intent_preview': 'Test intent',
        'information_value': 0.85,
        'priority_reason': 'alta incerteza',
        'domain': 'technical',
        'confidence': 0.5,
        'predicted_decision': 'approve',
        'status': 'pending',
        'created_at': datetime.utcnow()
    }

    await collection.insert_one(test_doc)

    # Buscar e verificar
    doc = await collection.find_one({'queue_id': 'test-queue-1'})
    assert doc['queue_id'] == 'test-queue-1'
    assert doc['information_value'] == 0.85
    assert doc['status'] == 'pending'


@pytest.fixture
async def mongo_client():
    """Fixture para cliente MongoDB de teste."""
    # Em um cenário real, usaríamos mongodb_container
    # Aqui usamos um mock para demonstração
    client = MagicMock(spec=AsyncIOMotorClient)
    client.name = 'test_neural_hive'

    # Mock database e coleções
    async def list_collection_names():
        return ['specialist_feedback', 'active_learning_queue']

    db = MagicMock()
    db.list_collection_names = list_collection_names

    async def mock_list_indexes():
        return [
            {'name': '_id_'},
            {'name': 'idx_queue_id'},
            {'name': 'idx_balanced_dataset'}
        ]

    collection = MagicMock()
    collection.list_indexes = mock_list_indexes

    async def mock_create_index(*args, **kwargs):
        return 'index_name'

    async def mock_create_indexes(*args, **kwargs):
        return ['index_name']

    async def mock_update_many(*args, **kwargs):
        return MagicMock(matched_count=1, modified_count=1)

    async def mock_insert_one(*args, **kwargs):
        return MagicMock(inserted_id='test_id')

    async def mock_find_one(*args, **kwargs):
        return {'queue_id': 'test-queue-1', 'balanced_dataset': False}

    async def mock_count_documents(*args, **kwargs):
        return 0

    collection.create_index = mock_create_index
    collection.create_indexes = mock_create_indexes
    collection.update_many = mock_update_many
    collection.insert_one = mock_insert_one
    collection.find_one = mock_find_one
    collection.count_documents = mock_count_documents
    collection.list_indexes = mock_list_indexes

    db.__getitem__ = lambda self, name: collection
    client.__getitem__ = lambda self, name: db

    yield client
