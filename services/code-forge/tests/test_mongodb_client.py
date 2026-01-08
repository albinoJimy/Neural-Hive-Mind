"""Testes unitários para MongoDBClient"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.mongodb_client import MongoDBClient


@pytest.fixture
def mock_motor_client():
    """Mock do AsyncIOMotorClient"""
    client = MagicMock()
    client.admin.command = AsyncMock(return_value={'ok': 1})
    client.close = MagicMock()

    # Mock database e collections
    db = MagicMock()
    db.artifacts = MagicMock()
    db.pipeline_logs = MagicMock()

    # Setup async methods
    db.artifacts.create_index = AsyncMock()
    db.artifacts.find_one = AsyncMock()
    db.artifacts.insert_one = AsyncMock()
    db.artifacts.update_one = AsyncMock()
    db.artifacts.delete_one = AsyncMock()

    db.pipeline_logs.create_index = AsyncMock()
    db.pipeline_logs.insert_one = AsyncMock()
    db.pipeline_logs.find = MagicMock()
    db.pipeline_logs.update_one = AsyncMock()

    client.__getitem__ = MagicMock(return_value=db)

    return client, db


@pytest.mark.asyncio
async def test_start_success(mock_motor_client):
    """Testar inicialização bem-sucedida do cliente"""
    mock_client, mock_db = mock_motor_client

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        assert client.client is not None
        assert client.db is not None
        mock_client.admin.command.assert_awaited_once_with('ping')


@pytest.mark.asyncio
async def test_start_creates_indexes(mock_motor_client):
    """Testar criação de índices na inicialização"""
    mock_client, mock_db = mock_motor_client

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        # Verifica que índices foram criados
        mock_db.artifacts.create_index.assert_awaited()
        mock_db.pipeline_logs.create_index.assert_awaited()


@pytest.mark.asyncio
async def test_stop_closes_connection(mock_motor_client):
    """Testar fechamento da conexão"""
    mock_client, mock_db = mock_motor_client

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()
        await client.stop()

        mock_client.close.assert_called_once()
        assert client.client is None
        assert client.db is None


@pytest.mark.asyncio
async def test_save_artifact_content_success(mock_motor_client):
    """Testar salvamento de conteúdo de artefato"""
    mock_client, mock_db = mock_motor_client
    mock_db.artifacts.update_one.return_value = MagicMock(upserted_id='123')

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        await client.save_artifact_content('art-1', 'print("hello")')

        mock_db.artifacts.update_one.assert_awaited_once()
        call_args = mock_db.artifacts.update_one.call_args
        assert call_args[0][0] == {'artifact_id': 'art-1'}


@pytest.mark.asyncio
async def test_get_artifact_content_found(mock_motor_client):
    """Testar recuperação de artefato existente"""
    mock_client, mock_db = mock_motor_client
    mock_db.artifacts.find_one.return_value = {
        'artifact_id': 'art-1',
        'content': 'print("hello")',
        'created_at': datetime.utcnow()
    }

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        content = await client.get_artifact_content('art-1')

        assert content == 'print("hello")'
        mock_db.artifacts.find_one.assert_awaited_once_with({'artifact_id': 'art-1'})


@pytest.mark.asyncio
async def test_get_artifact_content_not_found(mock_motor_client):
    """Testar recuperação de artefato não existente"""
    mock_client, mock_db = mock_motor_client
    mock_db.artifacts.find_one.return_value = None

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        content = await client.get_artifact_content('nonexistent')

        assert content is None


@pytest.mark.asyncio
async def test_delete_artifact_success(mock_motor_client):
    """Testar remoção de artefato"""
    mock_client, mock_db = mock_motor_client
    mock_db.artifacts.delete_one.return_value = MagicMock(deleted_count=1)

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        deleted = await client.delete_artifact('art-1')

        assert deleted is True
        mock_db.artifacts.delete_one.assert_awaited_once_with({'artifact_id': 'art-1'})


@pytest.mark.asyncio
async def test_save_pipeline_logs_success(mock_motor_client):
    """Testar salvamento de logs de pipeline"""
    mock_client, mock_db = mock_motor_client
    mock_db.pipeline_logs.insert_one.return_value = MagicMock(inserted_id='log-123')

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        logs = [{'stage': 'build', 'status': 'success'}]
        await client.save_pipeline_logs('pipe-1', logs)

        mock_db.pipeline_logs.insert_one.assert_awaited_once()
        call_args = mock_db.pipeline_logs.insert_one.call_args
        assert call_args[0][0]['pipeline_id'] == 'pipe-1'
        assert call_args[0][0]['logs'] == logs


@pytest.mark.asyncio
async def test_get_pipeline_logs_success(mock_motor_client):
    """Testar recuperação de logs de pipeline"""
    mock_client, mock_db = mock_motor_client

    # Setup cursor mock
    cursor_mock = MagicMock()
    cursor_mock.sort = MagicMock(return_value=cursor_mock)
    cursor_mock.limit = MagicMock(return_value=cursor_mock)
    cursor_mock.to_list = AsyncMock(return_value=[
        {'pipeline_id': 'pipe-1', 'logs': [{'stage': 'build'}]}
    ])

    mock_db.pipeline_logs.find = MagicMock(return_value=cursor_mock)

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        logs = await client.get_pipeline_logs('pipe-1')

        assert len(logs) == 1
        assert logs[0]['pipeline_id'] == 'pipe-1'


@pytest.mark.asyncio
async def test_health_check_success(mock_motor_client):
    """Testar health check bem-sucedido"""
    mock_client, mock_db = mock_motor_client

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        healthy = await client.health_check()

        assert healthy is True


@pytest.mark.asyncio
async def test_health_check_failure(mock_motor_client):
    """Testar health check com falha"""
    mock_client, mock_db = mock_motor_client
    mock_client.admin.command.side_effect = [{'ok': 1}, Exception('Connection lost')]

    with patch('src.clients.mongodb_client.AsyncIOMotorClient', return_value=mock_client):
        client = MongoDBClient('mongodb://localhost:27017', 'test_db')
        await client.start()

        healthy = await client.health_check()

        assert healthy is False


@pytest.mark.asyncio
async def test_operations_raise_when_not_started():
    """Testar que operações falham quando cliente não iniciado"""
    client = MongoDBClient('mongodb://localhost:27017', 'test_db')

    with pytest.raises(RuntimeError, match='MongoDB client not started'):
        await client.save_artifact_content('art-1', 'content')

    with pytest.raises(RuntimeError, match='MongoDB client not started'):
        await client.get_artifact_content('art-1')

    with pytest.raises(RuntimeError, match='MongoDB client not started'):
        await client.save_pipeline_logs('pipe-1', [])
