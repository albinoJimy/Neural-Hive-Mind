"""
Testes unitários para cliente MongoDB.

Cobre conexão, operações CRUD e health check.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.mongodb import MongoDBClient, get_mongodb_client


@pytest.fixture(autouse=True)
def reset_mongodb_singleton():
    """Reseta singleton do MongoDB entre testes."""
    MongoDBClient._reset_for_tests()
    yield
    MongoDBClient._reset_for_tests()


@pytest.fixture
def mock_settings():
    """Fixture com configurações mock."""
    settings = MagicMock()
    settings.mongodb_url = "mongodb://localhost:27017"
    settings.mongodb_database = "test_migration"
    return settings


class TestMongoDBClient:
    """Testes para MongoDBClient."""

    def test_singleton_pattern(self, mock_settings):
        """Verifica padrão singleton."""
        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            client1 = MongoDBClient()
            client2 = MongoDBClient()

            # Deve ser a mesma instância (singleton por classe)
            assert client1 is client2

    def test_initialization(self, mock_settings):
        """Verifica inicialização do cliente."""
        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            client = MongoDBClient()

            assert client._database_name == "test_migration"
            assert client._client is None

    @pytest.mark.asyncio
    async def test_connect(self, mock_settings):
        """Verifica conexão ao MongoDB."""
        mock_motor_client = MagicMock()

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                assert client._client == mock_motor_client

    @pytest.mark.asyncio
    async def test_connect_idempotent(self, mock_settings):
        """Verifica que reconnect não cria nova instância."""
        mock_motor_client = MagicMock()

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()
                first_client = client._client

                # Segunda connect não deve criar novo cliente
                await client.connect()
                assert client._client is first_client

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_settings):
        """Verifica desconexão do MongoDB."""
        mock_motor_client = MagicMock()
        mock_motor_client.close = MagicMock()

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()
                await client.disconnect()

                mock_motor_client.close.assert_called_once()
                assert client._client is None

    @pytest.mark.asyncio
    async def test_ping_success(self, mock_settings):
        """Verifica ping com sucesso."""
        mock_motor_client = MagicMock()
        mock_motor_client.admin.command = AsyncMock(return_value={"ok": 1})

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                result = await client.ping()

                assert result is True
                mock_motor_client.admin.command.assert_called_once_with("ping")

    @pytest.mark.asyncio
    async def test_ping_failure(self, mock_settings):
        """Verifica ping com falha."""
        mock_motor_client = MagicMock()
        mock_motor_client.admin.command = AsyncMock(side_effect=Exception("Connection lost"))

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                result = await client.ping()

                assert result is False

    @pytest.mark.asyncio
    async def test_ping_raises_when_not_connected(self, mock_settings):
        """Verifica ping levanta erro quando não conectado."""
        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            client = MongoDBClient()

            with pytest.raises(RuntimeError, match="MongoDB client not connected"):
                await client.ping()

    @pytest.mark.asyncio
    async def test_client_property(self, mock_settings):
        """Verifica property client."""
        mock_motor_client = MagicMock()

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                assert client.client == mock_motor_client

    @pytest.mark.asyncio
    async def test_client_property_raises_when_not_connected(self, mock_settings):
        """Verifica property client levanta erro quando não conectado."""
        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            client = MongoDBClient()

            with pytest.raises(RuntimeError, match="MongoDB client not connected"):
                _ = client.client

    @pytest.mark.asyncio
    async def test_insert_migration_job(self, mock_settings):
        """Verifica inserção de migration job."""
        mock_motor_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test-id"))

        # Setup database mock chain
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_motor_client.__getitem__ = MagicMock(return_value=mock_db)

        job_data = {
            "job_id": "job-123",
            "schema_mapping_id": "schema-456",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        }

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                result = await client.insert_migration_job(job_data)

                assert result == "test-id"
                mock_collection.insert_one.assert_called_once_with(job_data)

    @pytest.mark.asyncio
    async def test_find_migration_job_by_id(self, mock_settings):
        """Verifica busca de migration job por ID."""
        mock_motor_client = MagicMock()
        mock_collection = MagicMock()
        mock_job = {
            "job_id": "job-123",
            "schema_mapping_id": "schema-456",
            "status": "pending",
        }
        mock_collection.find_one = AsyncMock(return_value=mock_job)

        # Setup database mock chain
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_motor_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                result = await client.find_migration_job_by_id("job-123")

                assert result == mock_job
                mock_collection.find_one.assert_called_once_with({"job_id": "job-123"})

    @pytest.mark.asyncio
    async def test_update_migration_job_status(self, mock_settings):
        """Verifica atualização de status de migration job."""
        mock_motor_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        # Setup database mock chain
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_motor_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                await client.update_migration_job_status("job-123", "analyzing", error_message=None)

                mock_collection.update_one.assert_called_once()
                call_args = mock_collection.update_one.call_args
                assert call_args[0][0] == {"job_id": "job-123"}
                assert "$set" in call_args[0][1]
                assert call_args[0][1]["$set"]["status"] == "analyzing"

    @pytest.mark.asyncio
    async def test_count_migration_jobs_by_status(self, mock_settings):
        """Verifica contagem de jobs por status."""
        mock_motor_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=42)

        # Setup database mock chain
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_motor_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            with patch("src.db.mongodb.AsyncIOMotorClient", return_value=mock_motor_client):
                client = MongoDBClient()
                await client.connect()

                result = await client.count_migration_jobs_by_status("pending")

                assert result == 42
                mock_collection.count_documents.assert_called_once_with({"status": "pending"})


class TestGetMongoDBClient:
    """Testes para função get_mongodb_client."""

    @pytest.mark.asyncio
    async def test_returns_singleton_instance(self, mock_settings):
        """Verifica que retorna instância singleton."""
        with patch("src.db.mongodb.get_settings", return_value=mock_settings):
            client1 = await get_mongodb_client()
            client2 = await get_mongodb_client()

            # Deve ser a mesma instância global
            assert client1 is client2
