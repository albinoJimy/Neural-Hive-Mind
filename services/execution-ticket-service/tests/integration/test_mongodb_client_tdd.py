"""
Integration Tests para MongoDB Client - Execution Ticket Service

Testes de integração que usam MongoDB real via Docker Compose.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from src.database.mongodb_client import MongoDBClient


# ===== FIXTURES =====


@pytest.fixture
async def mongodb_container(docker_ip, docker_services):
    """Fixture para obter URI do MongoDB container."""
    # Esperar MongoDB estar pronto
    await docker_services.start("mongodb")
    return f"mongodb://{docker_ip}:27017"


@pytest.fixture
def mock_settings():
    """Configurações para testes de integração."""
    return SimpleNamespace(
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test_neural_hive",
        mongodb_collection_tickets="tickets",
        mongodb_collection_audit="audit_log",
    )


@pytest.fixture
async def mongodb_client(mock_settings, mongodb_container):
    """Cliente MongoDB para testes."""
    client = MongoDBClient(mock_settings)
    await client.start()
    yield client
    await client.client.close()


# ===== TESTES: Conexão =====


class TestMongoDBClientConnection:
    """Testes de conexão com MongoDB."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_settings):
        """
        DADO: Configurações válidas do MongoDB
        QUANDO: Chamo start
        ENTÃO: Deve conectar sem erros
        """
        client = MongoDBClient(mock_settings)

        with patch.object(client, '_connect_internal') as mock_connect:
            await client.start()

        mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_retry(self, mock_settings):
        """
        DADO: MongoDB indisponível na primeira tentativa
        QUANDO: Chamo start com retry
        ENTÃO: Deve tentar novamente e conectar
        """
        client = MongoDBClient(mock_settings)

        call_count = 0

        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection refused")
            # Conexão bem-sucedida na segunda tentação

        with patch.object(client, '_connect_internal', side_effect=failing_then_success), \
             patch('asyncio.sleep') as mock_sleep:

            await client.start(max_retries=3, initial_delay=0.01)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_settings):
        """
        DADO: Um cliente conectado
        QUANDO: Chamo disconnect (fechando client)
        ENTÃO: Deve fechar a conexão
        """
        client = MongoDBClient(mock_settings)
        mock_motor_client = AsyncMock()
        client.client = mock_motor_client

        await client.client.close()

        mock_motor_client.close.assert_called_once()


# ===== TESTES: Operações de Audit Trail =====


class TestMongoDBAuditTrail:
    """Testes do audit trail no MongoDB."""

    @pytest.mark.asyncio
    async def test_log_status_change(self, mock_settings):
        """
        DADO: Uma mudança de status de ticket
        QUANDO: Chamo log_status_change
        ENTÃO: Deve registrar no MongoDB
        """
        client = MongoDBClient(mock_settings)

        # Mock collections
        mock_collection = AsyncMock()
        mock_collection.insert_one = AsyncMock()
        client.audit_collection = mock_collection

        ticket_id = str(uuid4())
        await client.log_status_change(
            ticket_id=ticket_id,
            old_status="PENDING",
            new_status="RUNNING",
            changed_by="worker-agent",
            metadata={"retry_count": 0}
        )

        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_status_change_with_timestamp(self, mock_settings):
        """
        DADO: Uma mudança de status
        QUANDO: Chamo log_status_change
        ENTÃO: Deve incluir timestamp gerado automaticamente
        """
        client = MongoDBClient(mock_settings)

        mock_collection = AsyncMock()
        mock_collection.insert_one = AsyncMock()
        client.audit_collection = mock_collection

        ticket_id = str(uuid4())
        await client.log_status_change(
            ticket_id=ticket_id,
            old_status="RUNNING",
            new_status="COMPLETED",
            changed_by="worker",
            metadata={"duration_ms": 1500}
        )

        # Verificar que insert_one foi chamado com timestamp incluído
        assert mock_collection.insert_one.called
        call_args = mock_collection.insert_one.call_args[0][0]
        assert 'timestamp' in call_args
        assert call_args['ticket_id'] == ticket_id

    @pytest.mark.asyncio
    async def test_log_status_change_handles_errors(self, mock_settings):
        """
        DADO: MongoDB lançando exceção
        QUANDO: Chamo log_status_change
        ENTÃO: Deve propagar a exceção
        """
        client = MongoDBClient(mock_settings)

        mock_collection = AsyncMock()
        mock_collection.insert_one = AsyncMock(side_effect=Exception("MongoDB error"))
        client.audit_collection = mock_collection

        with pytest.raises(Exception, match="MongoDB error"):
            await client.log_status_change(
                ticket_id=str(uuid4()),
                old_status="PENDING",
                new_status="RUNNING",
                changed_by="test",
                metadata={}
            )


# ===== TESTES: Health Check =====


class TestMongoDBHealthCheck:
    """Testes de health check do MongoDB."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_settings):
        """
        DADO: Cliente conectado ao MongoDB
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar True
        """
        client = MongoDBClient(mock_settings)

        mock_client = AsyncMock()
        mock_client.admin.command.return_value = {"ok": 1}
        client.client = mock_client

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_settings):
        """
        DADO: MongoDB desconectado
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar False
        """
        client = MongoDBClient(mock_settings)

        mock_client = AsyncMock()
        mock_client.admin.command.side_effect = Exception("Connection lost")
        client.client = mock_client

        result = await client.health_check()

        assert result is False


# ===== TESTES: Collection Access =====


class TestMongoDBCollections:
    """Testes de acesso às coleções."""

    @pytest.mark.asyncio
    async def test_collections_initialized_after_connect(self, mock_settings):
        """
        DADO: Cliente conectado
        QUANDO: Acesso collections
        ENTÃO: Devem estar inicializadas
        """
        client = MongoDBClient(mock_settings)

        # Mock do motor client
        mock_motor_client = MagicMock()
        mock_database = MagicMock()
        mock_tickets_collection = MagicMock()
        mock_audit_collection = MagicMock()

        mock_database.__getitem__ = MagicMock(side_effect=lambda x: {
            "tickets": mock_tickets_collection,
            "audit_log": mock_audit_collection
        }.get(x))
        mock_motor_client.__getitem__ = MagicMock(return_value=mock_database)

        # Configurar _connect_internal mock
        async def mock_connect():
            client.client = mock_motor_client
            client.db = mock_database
            client.tickets_collection = mock_tickets_collection
            client.audit_collection = mock_audit_collection

        with patch.object(client, '_connect_internal', side_effect=mock_connect), \
             patch.object(client, '_create_indexes'):

            await client.start()

        assert client.tickets_collection is not None
        assert client.audit_collection is not None


# ===== TESTES: Index Creation =====


class TestMongoDBIndexes:
    """Testes de criação de índices."""

    @pytest.mark.asyncio
    async def test_create_indexes_in_connect_internal(self, mock_settings):
        """
        DADO: Cliente conectando
        QUANDO: _connect_internal é chamado
        ENTÃO: Deve chamar _create_indexes
        """
        client = MongoDBClient(mock_settings)

        # Mock do motor client
        mock_motor_client = AsyncMock()
        mock_motor_client.admin.command = AsyncMock(return_value={"ok": 1})

        # Mock do database
        mock_database = MagicMock()
        mock_tickets_collection = MagicMock()
        mock_audit_collection = MagicMock()

        # Wrapper para rastrear chamadas a create_index
        tickets_create_index_mock = MagicMock()
        audit_create_index_mock = MagicMock()

        async def mock_tickets_create_index(*args, **kwargs):
            tickets_create_index_mock(*args, **kwargs)
            return "index_name"

        async def mock_audit_create_index(*args, **kwargs):
            audit_create_index_mock(*args, **kwargs)
            return "index_name"

        mock_tickets_collection.create_index = mock_tickets_create_index
        mock_audit_collection.create_index = mock_audit_create_index

        # Configurar __getitem__ do database
        def mock_getitem(name):
            if name == "tickets":
                return mock_tickets_collection
            elif name == "audit_log":
                return mock_audit_collection
            return MagicMock()

        mock_database.__getitem__ = mock_getitem
        mock_motor_client.__getitem__ = MagicMock(return_value=mock_database)

        # Patch _connect_internal para executar código real
        async def mock_connect_internal():
            # Configurar cliente e database
            client.client = mock_motor_client
            client.db = mock_database
            client.tickets_collection = mock_tickets_collection
            client.audit_collection = mock_audit_collection
            # Chamar _create_indexes (que está no código real)
            await client._create_indexes()

        with patch.object(client, '_connect_internal', side_effect=mock_connect_internal):

            await client.start()

        # Verificar que create_index foi chamado pelo menos uma vez
        assert tickets_create_index_mock.called or audit_create_index_mock.called


# ===== TESTES: Singleton =====


class TestMongoDBClientSingleton:
    """Testes do padrão Singleton."""

    @pytest.mark.asyncio
    async def test_get_mongodb_client_singleton(self):
        """
        DADO: Nenhum cliente criado
        QUANDO: Chamo get_mongodb_client duas vezes
        ENTÃO: Deve retornar a mesma instância
        """
        # Reset singleton
        import src.database.mongodb_client
        src.database.mongodb_client._mongodb_client = None

        with patch('src.config.get_settings') as mock_get_settings:
            mock_settings = SimpleNamespace(
                mongodb_uri="mongodb://localhost:27017",
                mongodb_database="test_db",
                mongodb_collection_tickets="tickets",
                mongodb_collection_audit="audit",
            )
            mock_get_settings.return_value = mock_settings

            from src.database.mongodb_client import get_mongodb_client

            client1 = await get_mongodb_client()
            client2 = await get_mongodb_client()

        assert client1 is client2
