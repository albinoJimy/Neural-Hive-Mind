"""
Testes TDD para PostgreSQL Client - Fase RED

Testes escritos ANTES da implementação.
Seguem o ciclo RED-GREEN-REFACTOR.
"""
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.database.postgres_client import PostgresClient, get_postgres_client
from src.models import ExecutionTicket, TicketStatus


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
        'priority': 'NORMAL',
        'risk_band': 'medium',
        'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
        'qos': {
            'delivery_mode': 'AT_MOST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'TRANSIENT'
        },
        'parameters': {},
        'required_capabilities': [],
        'security_level': 'INTERNAL',
        'created_at': 1714800000000,
        'started_at': None,
        'completed_at': None,
        'retry_count': 0,
        'error_message': None,
        'compensation_ticket_id': None,
        'metadata': {},
        'schema_version': 1
    }


def make_mock_orm(ticket_dict: dict) -> MagicMock:
    """Cria mock de ORM."""
    mock_orm = MagicMock()
    for key, value in ticket_dict.items():
        setattr(mock_orm, key, value)
    return mock_orm


# ===== TESTES: Initialization =====


class TestPostgresClientInit:
    """Testes de inicialização do PostgresClient."""

    def test_init_stores_settings(self, mock_settings):
        """
        DADO: Configurações válidas
        QUANDO: Crio PostgresClient
        ENTÃO: Deve armazenar as configurações
        """
        client = PostgresClient(mock_settings)

        assert client.settings == mock_settings
        assert client._engine is None
        assert client._session_maker is None


# ===== TESTES: Connection =====


class TestPostgresClientConnection:
    """Testes de conexão com PostgreSQL."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_settings):
        """
        DADO: Configurações válidas
        QUANDO: Chamo connect
        ENTÃO: Deve estabelecer conexão
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session_maker = MagicMock()
            mock_sessionmaker_func.return_value = mock_session_maker

            client = PostgresClient(mock_settings)
            await client._connect_internal()

        assert client._engine == mock_engine
        assert client._session_maker == mock_session_maker

    @pytest.mark.asyncio
    async def test_start_with_retry(self, mock_settings):
        """
        DADO: PostgreSQL indisponível na primeira tentativa
        QUANDO: Chamo start com retry
        ENTÃO: Deve tentar novamente e conectar
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func, \
             patch('asyncio.sleep') as mock_sleep:

            call_count = 0

            async def failing_then_success(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Connection refused")
                mock_engine = AsyncMock()
                return mock_engine

            mock_engine_func.side_effect = failing_then_success
            mock_session_maker = MagicMock()
            mock_sessionmaker_func.return_value = mock_session_maker

            client = PostgresClient(mock_settings)
            await client.start(max_retries=3, initial_delay=0.01)

        assert client._engine is not None

    @pytest.mark.asyncio
    async def test_start_exhausts_retries(self, mock_settings):
        """
        DADO: PostgreSQL sempre falha
        QUANDO: Chamo start com max_retries
        ENTÃO: Deve levantar exceção após exaurir tentativas
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('asyncio.sleep') as mock_sleep:

            mock_engine_func.side_effect = Exception("Connection refused")

            client = PostgresClient(mock_settings)

            with pytest.raises(Exception):
                await client.start(max_retries=2, initial_delay=0.01)

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_settings):
        """
        DADO: Um cliente conectado
        QUANDO: Chamo disconnect
        ENTÃO: Deve fechar o engine
        """
        client = PostgresClient(mock_settings)
        mock_engine = AsyncMock()
        client._engine = mock_engine

        await client.disconnect()

        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_settings):
        """
        DADO: Um cliente conectado
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar True
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session_maker = MagicMock()
            mock_sessionmaker_func.return_value = mock_session_maker

            client = PostgresClient(mock_settings)
            await client._connect_internal()

            result = await client.health_check()

        assert result is True


# ===== TESTES: CRUD Operations =====


class TestPostgresClientCRUD:
    """Testes de operações CRUD."""

    @pytest.mark.asyncio
    async def test_create_ticket(self, mock_settings, sample_ticket_dict):
        """
        DADO: Um ExecutionTicket válido
        QUANDO: Chamo create_ticket
        ENTÃO: Deve persistir no PostgreSQL
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            mock_orm = make_mock_orm(sample_ticket_dict)
            mock_session.refresh = AsyncMock()

            with patch('src.database.postgres_client.TicketORM') as mock_ticket_orm_class:
                mock_ticket_orm_class.from_pydantic.return_value = mock_orm

                client = PostgresClient(mock_settings)
                client._session_maker = mock_session_maker

                result = await client.create_ticket(ExecutionTicket(**sample_ticket_dict))

        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ticket_by_id_found(self, mock_settings, sample_ticket_dict):
        """
        DADO: Um ticket_id válido existente
        QUANDO: Chamo get_ticket_by_id
        ENTÃO: Deve retornar o ticket
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            mock_orm = make_mock_orm(sample_ticket_dict)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_orm
            mock_session.execute.return_value = mock_result

            client = PostgresClient(mock_settings)
            client._session_maker = mock_session_maker

            result = await client.get_ticket_by_id(sample_ticket_dict['ticket_id'])

        assert result is not None
        assert result.ticket_id == sample_ticket_dict['ticket_id']

    @pytest.mark.asyncio
    async def test_get_ticket_by_id_not_found(self, mock_settings):
        """
        DADO: Um ticket_id inexistente
        QUANDO: Chamo get_ticket_by_id
        ENTÃO: Deve retornar None
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            client = PostgresClient(mock_settings)
            client._session_maker = mock_session_maker

            result = await client.get_ticket_by_id(str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_update_ticket_status(self, mock_settings, sample_ticket_dict):
        """
        DADO: Um ticket_id e novo status
        QUANDO: Chamo update_ticket_status
        ENTÃO: Deve atualizar o status
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            updated_dict = sample_ticket_dict.copy()
            updated_dict['status'] = 'RUNNING'
            mock_orm = make_mock_orm(updated_dict)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_orm
            mock_session.execute.return_value = mock_result

            client = PostgresClient(mock_settings)
            client._session_maker = mock_session_maker

            result = await client.update_ticket_status(
                sample_ticket_dict['ticket_id'],
                TicketStatus.RUNNING
            )

        assert result is not None
        assert result.status == 'RUNNING'
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_retry_count(self, mock_settings, sample_ticket_dict):
        """
        DADO: Um ticket FAILED
        QUANDO: Chamo increment_retry_count
        ENTÃO: Deve incrementar retry_count e resetar para PENDING
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            updated_dict = sample_ticket_dict.copy()
            updated_dict['status'] = 'PENDING'
            updated_dict['retry_count'] = 1
            mock_orm = make_mock_orm(updated_dict)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_orm
            mock_session.execute.return_value = mock_result

            client = PostgresClient(mock_settings)
            client._session_maker = mock_session_maker

            result = await client.increment_retry_count(sample_ticket_dict['ticket_id'])

        assert result is not None
        assert result.status == 'PENDING'
        assert result.retry_count == 1

    @pytest.mark.asyncio
    async def test_list_tickets_with_filters(self, mock_settings, sample_ticket_dict):
        """
        DADO: Filtros de plan_id e status
        QUANDO: Chamo list_tickets
        ENTÃO: Deve aplicar os filtros
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            client = PostgresClient(mock_settings)
            client._session_maker = mock_session_maker

            filters = {
                'plan_id': sample_ticket_dict['plan_id'],
                'status': 'PENDING'
            }

            result = await client.list_tickets(filters, offset=0, limit=10)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_count_tickets(self, mock_settings):
        """
        DADO: Filtros de contagem
        QUANDO: Chamo count_tickets
        ENTÃO: Deve retornar a contagem
        """
        with patch('src.database.postgres_client.create_async_engine') as mock_engine_func, \
             patch('src.database.postgres_client.async_sessionmaker') as mock_sessionmaker_func:

            mock_engine = AsyncMock()
            mock_engine_func.return_value = mock_engine
            mock_session = AsyncMock()
            mock_session_maker = MagicMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            mock_sessionmaker_func.return_value = mock_session_maker

            mock_result = MagicMock()
            mock_result.scalar.return_value = 42
            mock_session.execute.return_value = mock_result

            client = PostgresClient(mock_settings)
            client._session_maker = mock_session_maker

            result = await client.count_tickets({'status': 'PENDING'})

        assert result == 42


# ===== TESTES: Singleton =====


class TestPostgresClientSingleton:
    """Testes do padrão Singleton."""

    @pytest.mark.asyncio
    async def test_get_postgres_client_singleton(self):
        """
        DADO: Nenhum cliente criado
        QUANDO: Chamo get_postgres_client duas vezes
        ENTÃO: Deve retornar a mesma instância
        """
        # Reset singleton
        import src.database.postgres_client
        src.database.postgres_client._postgres_client = None

        with patch('src.config.get_settings') as mock_get_settings:
            mock_settings = SimpleNamespace(
                postgres_host='localhost',
                postgres_port=5432,
                postgres_database='test_db',
                postgres_user='test',
                postgres_password='test',
                postgres_pool_size=5,
                postgres_max_overflow=10,
            )
            mock_get_settings.return_value = mock_settings

            client1 = await get_postgres_client()
            client2 = await get_postgres_client()

        assert client1 is client2
