"""Testes unitários para o cliente MongoDB."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.db.mongodb import AsyncMongoDBClient, get_mongodb_client


@pytest.fixture
def mock_settings():
    """Fixture para mock das configurações."""
    with patch("src.db.mongodb.get_settings") as mock:
        settings = Mock()
        settings.mongodb_url = "mongodb://localhost:27017"
        settings.mongodb_database = "test_db"
        mock.return_value = settings
        yield mock


@pytest.fixture
def reset_singleton():
    """Reseta o singleton entre testes."""
    AsyncMongoDBClient._instance = None
    yield
    AsyncMongoDBClient._instance = None


@pytest.mark.asyncio
async def test_mongodb_client_connect(reset_singleton, mock_settings):
    """Testa conexão do cliente MongoDB."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()

        # Act
        await client.connect()

        # Assert
        assert client._client is not None
        mock_motor.assert_called_once_with("mongodb://localhost:27017")


@pytest.mark.asyncio
async def test_mongodb_client_database_property(reset_singleton, mock_settings):
    """Testa propriedade database."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_db = Mock()
        mock_client.__getitem__.return_value = mock_db
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()
        await client.connect()

        # Act
        db = client.database

        # Assert
        assert db is not None
        mock_client.__getitem__.assert_called_once_with("test_db")


@pytest.mark.asyncio
async def test_mongodb_client_singleton(reset_singleton, mock_settings):
    """Testa padrão singleton do cliente MongoDB."""
    # Arrange & Act
    client1 = AsyncMongoDBClient()
    client2 = AsyncMongoDBClient()

    # Assert
    assert client1 is client2, "Deve retornar a mesma instância"


@pytest.mark.asyncio
async def test_mongodb_client_ping(reset_singleton, mock_settings):
    """Testa método ping."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_admin = Mock()
        mock_admin.command = AsyncMock(return_value={"ok": 1})
        mock_client.admin = mock_admin
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()
        await client.connect()

        # Act
        result = await client.ping()

        # Assert
        assert result is True


@pytest.mark.asyncio
async def test_mongodb_client_disconnect(reset_singleton, mock_settings):
    """Testa desconexão do cliente MongoDB."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = Mock()
        mock_client.close = Mock()
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()
        await client.connect()

        # Act
        await client.disconnect()

        # Assert
        assert client._client is None
        mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_mongodb_client_documents_collection(reset_singleton, mock_settings):
    """Testa propriedade documents_collection."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_db = Mock()
        mock_db.__getitem__ = Mock(return_value=Mock())
        mock_client.__getitem__ = Mock(return_value=mock_db)
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()
        await client.connect()

        # Act
        collection = client.documents_collection

        # Assert
        assert collection is not None
        mock_db.__getitem__.assert_called_once_with("documents")


@pytest.mark.asyncio
async def test_mongodb_client_entities_collection(reset_singleton, mock_settings):
    """Testa propriedade entities_collection."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_db = Mock()
        mock_db.__getitem__ = Mock(return_value=Mock())
        mock_client.__getitem__ = Mock(return_value=mock_db)
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()
        await client.connect()

        # Act
        collection = client.entities_collection

        # Assert
        assert collection is not None
        mock_db.__getitem__.assert_called_once_with("entities")


@pytest.mark.asyncio
async def test_mongodb_client_parsing_jobs_collection(reset_singleton, mock_settings):
    """Testa propriedade parsing_jobs_collection."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_db = Mock()
        mock_db.__getitem__ = Mock(return_value=Mock())
        mock_client.__getitem__ = Mock(return_value=mock_db)
        mock_motor.return_value = mock_client
        client = AsyncMongoDBClient()
        await client.connect()

        # Act
        collection = client.parsing_jobs_collection

        # Assert
        assert collection is not None
        mock_db.__getitem__.assert_called_once_with("parsing_jobs")


@pytest.mark.asyncio
async def test_get_mongodb_client_singleton(reset_singleton, mock_settings):
    """Testa função get_mongodb_client como singleton."""
    # Arrange
    with patch("src.db.mongodb.AsyncIOMotorClient") as mock_motor:
        mock_client = AsyncMock()
        mock_motor.return_value = mock_client

        # Act
        client1 = await get_mongodb_client()
        client2 = await get_mongodb_client()

        # Assert
        assert client1 is client2
