"""Testes unitários para PostgresClient"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.postgres_client import PostgresClient, PipelineResultORM
from src.models.artifact import PipelineResult, PipelineStatus


@pytest.fixture
def mock_engine():
    """Mock do SQLAlchemy engine"""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    engine.begin = MagicMock()
    return engine


@pytest.fixture
def mock_session():
    """Mock da sessão SQLAlchemy"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.merge = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_pipeline_result():
    """PipelineResult de exemplo para testes"""
    return PipelineResult(
        pipeline_id='pipe-123',
        ticket_id='ticket-456',
        plan_id='plan-789',
        intent_id='intent-001',
        decision_id='decision-001',
        status=PipelineStatus.COMPLETED,
        artifacts=[],
        pipeline_stages=[],
        total_duration_ms=5000,
        approval_required=False,
        created_at=datetime.utcnow()
    )


@pytest.mark.asyncio
async def test_start_success(mock_engine, mock_session):
    """Testar inicialização bem-sucedida do cliente"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=0)
    mock_session.execute.return_value = mock_result

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        # Mock run_sync para criar tabelas
        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        assert client.engine is not None
        assert client.session_factory is not None


@pytest.mark.asyncio
async def test_stop_disposes_engine(mock_engine, mock_session):
    """Testar fechamento da conexão"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=0)
    mock_session.execute.return_value = mock_result

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()
        await client.stop()

        mock_engine.dispose.assert_awaited_once()
        assert client.engine is None
        assert client.session_factory is None


@pytest.mark.asyncio
async def test_save_pipeline_success(mock_engine, mock_session, sample_pipeline_result):
    """Testar salvamento de pipeline"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=0)
    mock_session.execute.return_value = mock_result

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        await client.save_pipeline(sample_pipeline_result)

        mock_session.merge.assert_awaited_once()
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pipeline_found(mock_engine, mock_session):
    """Testar busca de pipeline existente"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock do resultado com ORM
    mock_orm = MagicMock()
    mock_orm.pipeline_id = 'pipe-123'
    mock_orm.ticket_id = 'ticket-456'
    mock_orm.plan_id = 'plan-789'
    mock_orm.intent_id = 'intent-001'
    mock_orm.decision_id = 'decision-001'
    mock_orm.status = 'COMPLETED'
    mock_orm.artifacts = []
    mock_orm.pipeline_stages = []
    mock_orm.total_duration_ms = 5000
    mock_orm.approval_required = False
    mock_orm.approval_reason = None
    mock_orm.error_message = None
    mock_orm.git_mr_url = None
    mock_orm.metadata = {}
    mock_orm.created_at = datetime.utcnow()
    mock_orm.completed_at = None
    mock_orm.schema_version = 1
    mock_orm.correlation_id = None
    mock_orm.trace_id = None
    mock_orm.span_id = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_orm)
    mock_result.scalar = MagicMock(return_value=0)
    mock_session.execute.return_value = mock_result

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        result = await client.get_pipeline('pipe-123')

        assert result is not None
        assert result.pipeline_id == 'pipe-123'


@pytest.mark.asyncio
async def test_get_pipeline_not_found(mock_engine, mock_session):
    """Testar busca de pipeline não existente"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalar = MagicMock(return_value=0)
    mock_session.execute.return_value = mock_result

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        result = await client.get_pipeline('nonexistent')

        assert result is None


@pytest.mark.asyncio
async def test_list_pipelines_with_filters(mock_engine, mock_session):
    """Testar listagem de pipelines com filtros"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock resultado vazio para start
    mock_start_result = MagicMock()
    mock_start_result.scalar = MagicMock(return_value=0)

    # Mock resultado para list
    mock_list_result = MagicMock()
    mock_list_result.scalars = MagicMock()
    mock_list_result.scalars.return_value.all = MagicMock(return_value=[])

    mock_session.execute.side_effect = [mock_start_result, mock_list_result]

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        results = await client.list_pipelines({'ticket_id': 'ticket-456'})

        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_update_pipeline_status(mock_engine, mock_session):
    """Testar atualização de status de pipeline"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_start_result = MagicMock()
    mock_start_result.scalar = MagicMock(return_value=0)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_session.execute.side_effect = [mock_start_result, mock_update_result]

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        updated = await client.update_pipeline_status('pipe-123', PipelineStatus.FAILED, 'Test error')

        assert updated is True


@pytest.mark.asyncio
async def test_health_check_success(mock_engine, mock_session):
    """Testar health check bem-sucedido"""
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=0)
    mock_session.execute.return_value = mock_result

    with patch('src.clients.postgres_client.create_async_engine', return_value=mock_engine), \
         patch('src.clients.postgres_client.async_sessionmaker', return_value=mock_session_maker):

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

        client = PostgresClient('postgresql://user:pass@localhost/db')
        await client.start()

        healthy = await client.health_check()

        assert healthy is True


@pytest.mark.asyncio
async def test_operations_raise_when_not_started():
    """Testar que operações falham quando cliente não iniciado"""
    client = PostgresClient('postgresql://user:pass@localhost/db')

    with pytest.raises(RuntimeError, match='PostgreSQL client not started'):
        await client.get_pipeline('pipe-123')

    with pytest.raises(RuntimeError, match='PostgreSQL client not started'):
        await client.list_pipelines({})


def test_url_conversion_to_asyncpg():
    """Testar conversão de URL para driver asyncpg"""
    client = PostgresClient('postgresql://user:pass@localhost/db')
    assert 'asyncpg' in client.url

    client2 = PostgresClient('postgresql+asyncpg://user:pass@localhost/db')
    assert 'asyncpg' in client2.url
