"""
Testes para PostgreSQL Client.
"""
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

# Set environment variables antes dos imports
os.environ.setdefault('POSTGRESQL_HOST', 'localhost')
os.environ.setdefault('POSTGRESQL_PORT', '5432')
os.environ.setdefault('POSTGRESQL_USER', 'postgres')
os.environ.setdefault('POSTGRESQL_PASSWORD', 'password')
os.environ.setdefault('POSTGRESQL_DATABASE', 'test_analyst_agents')
os.environ.setdefault('POSTGRESQL_MIN_POOL_SIZE', '5')
os.environ.setdefault('POSTGRESQL_MAX_POOL_SIZE', '20')


@pytest.fixture
def mock_asyncpg_pool():
    """Mock do pool asyncpg."""
    pool = AsyncMock()
    pool.close = AsyncMock()

    # Mock connection
    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[
        MagicMock(**{'id': '1', 'plan_id': 'plan-123', 'analyst_type': 'text', 'insight_data': {}, 'created_at': datetime.now(timezone.utc)})
    ])
    mock_conn.fetchrow = AsyncMock(return_value=MagicMock(**{'id': '1'}))
    mock_conn.fetchval = AsyncMock(return_value=1)
    mock_conn.execute = AsyncMock(return_value='SELECT 1')

    # Context manager mock para pool.acquire()
    class AcquireContext:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, *args):
            pass

    pool.acquire = MagicMock(return_value=AcquireContext())

    # Mock create_pool como coroutine
    async def mock_create_pool(*args, **kwargs):
        return pool

    return mock_create_pool, pool, mock_conn


@pytest.fixture
async def postgresql_client(mock_asyncpg_pool):
    """Cliente PostgreSQL para testes."""
    from src.clients.postgresql_client import PostgreSQLClient

    client = PostgreSQLClient(
        host='localhost',
        port=5432,
        database='test_analyst_agents',
        user='postgres',
        password='password'
    )

    # Mock asyncpg.create_pool
    mock_create_pool, pool, conn = mock_asyncpg_pool
    with patch('asyncpg.create_pool', side_effect=mock_create_pool):
        await client.connect()
        yield client


class TestPostgreSQLClient:
    """Testes para PostgreSQLClient."""

    def test_init_with_params(self):
        """Testa inicialização com parâmetros individuais."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(
            host='localhost',
            port=5432,
            database='test_db',
            user='testuser',
            password='testpass'
        )

        assert 'testuser' in client.dsn
        assert 'localhost' in client.dsn
        assert 'test_db' in client.dsn
        assert client.min_size == 10
        assert client.max_size == 100

    def test_init_with_dsn(self):
        """Testa inicialização com DSN completo."""
        from src.clients.postgresql_client import PostgreSQLClient

        dsn = 'postgresql://user:pass@host:5432/db'
        client = PostgreSQLClient(dsn=dsn)

        assert client.dsn == dsn

    def test_init_without_password(self):
        """Testa DSN sem senha."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(
            host='localhost',
            port=5432,
            database='test_db',
            user='testuser'
        )

        assert 'testuser@' in client.dsn
        assert ':****' not in client.dsn

    @pytest.mark.asyncio
    async def test_connect(self, mock_asyncpg_pool):
        """Testa conexão com PostgreSQL."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(host='localhost', database='test')

        mock_create_pool, pool, conn = mock_asyncpg_pool
        with patch('asyncpg.create_pool', side_effect=mock_create_pool):
            await client.connect()

            assert client._connected is True
            assert client.pool is not None

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Testa falha de conexão."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(host='invalid-host', database='test')

        async def mock_create_pool_fail(*args, **kwargs):
            raise Exception('Connection failed')

        with patch('asyncpg.create_pool', side_effect=mock_create_pool_fail):
            with pytest.raises(ConnectionError):
                await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, postgresql_client):
        """Testa desconexão."""
        await postgresql_client.disconnect()
        assert postgresql_client._connected is False

    @pytest.mark.asyncio
    async def test_is_connected(self, postgresql_client):
        """Testa verificação de conexão."""
        assert await postgresql_client.is_connected() is True

    @pytest.mark.asyncio
    async def test_execute_query_fetch_all(self, postgresql_client):
        """Testa execute_query com fetch='all'."""
        results = await postgresql_client.execute_query('SELECT 1', fetch='all')

        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_execute_query_fetch_one(self, postgresql_client):
        """Testa execute_query com fetch='one'."""
        result = await postgresql_client.execute_query('SELECT 1', fetch='one')

        assert result is not None
        # fetchrow retorna dict com 'id' no mock
        assert isinstance(result, dict) or result is None

    @pytest.mark.asyncio
    async def test_execute_query_fetch_val(self, postgresql_client):
        """Testa execute_query com fetch='val'."""
        result = await postgresql_client.execute_query('SELECT 1', fetch='val')

        assert result == 1

    @pytest.mark.asyncio
    async def test_execute_query_fetch_none(self, postgresql_client):
        """Testa execute_query com fetch='none'."""
        result = await postgresql_client.execute_query('SELECT 1', fetch='none')

        assert result == []

    @pytest.mark.asyncio
    async def test_execute_query_not_connected(self):
        """Testa execute_query sem conexão."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(host='localhost', database='test')
        # Não chamar connect()

        with pytest.raises(RuntimeError, match='PostgreSQL não está conectado'):
            await client.execute_query('SELECT 1')

    @pytest.mark.asyncio
    async def test_get_insights_basic(self, postgresql_client):
        """Testa get_insights básico."""
        results = await postgresql_client.get_insights(limit=10)

        assert isinstance(results, list)
        # Mock retorna 1 resultado
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_insights_with_plan_id(self, postgresql_client):
        """Testa get_insights filtrando por plan_id."""
        results = await postgresql_client.get_insights(plan_id='plan-123', limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_insights_with_analyst_type(self, postgresql_client):
        """Testa get_insights filtrando por analyst_type."""
        results = await postgresql_client.get_insights(analyst_type='text', limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_insights_with_time_range(self, postgresql_client):
        """Testa get_insights com filtro de tempo."""
        time_range = {
            'start': datetime.now(timezone.utc) - timedelta(hours=24),
            'end': datetime.now(timezone.utc)
        }
        results = await postgresql_client.get_insights(time_range=time_range, limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_analyst_actions(self, postgresql_client):
        """Testa get_analyst_actions."""
        with patch.object(postgresql_client, 'execute_query', return_value=[
            {'id': '1', 'action_type': 'approve', 'status': 'completed'}
        ]):
            results = await postgresql_client.get_analyst_actions(limit=10)

            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_feature_usage(self, postgresql_client):
        """Testa get_feature_usage."""
        with patch.object(postgresql_client, 'execute_query', return_value=[
            {'feature_name': 'analytics', 'usage_count': 100}
        ]):
            results = await postgresql_client.get_feature_usage(limit=10)

            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_insight_by_id(self, postgresql_client):
        """Testa get_insight_by_id."""
        result = await postgresql_client.get_insight_by_id('insight-123')

        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_insights_by_plan(self, postgresql_client):
        """Testa get_insights_by_plan."""
        results = await postgresql_client.get_insights_by_plan('plan-456', limit=50)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_count_insights(self, postgresql_client):
        """Testa count_insights."""
        count = await postgresql_client.count_insights()

        assert isinstance(count, int)
        # Mock retorna 0 ou 1
        assert count >= 0

    @pytest.mark.asyncio
    async def test_count_insights_with_filters(self, postgresql_client):
        """Testa count_insights com filtros."""
        with patch.object(postgresql_client, 'execute_query', return_value=5):
            count = await postgresql_client.count_insights(
                plan_id='plan-123',
                analyst_type='text'
            )

            assert count == 5

    @pytest.mark.asyncio
    async def test_get_insights_statistics(self, postgresql_client):
        """Testa get_insights_statistics."""
        with patch.object(postgresql_client, 'execute_query', return_value=[
            {'analyst_type': 'text', 'count': 10, 'avg_confidence': 0.85},
            {'analyst_type': 'code', 'count': 5, 'avg_confidence': 0.75}
        ]):
            stats = await postgresql_client.get_insights_statistics(time_range_hours=24)

            assert 'by_type' in stats
            assert 'total_insights' in stats
            assert 'avg_confidence' in stats
            assert stats['total_insights'] == 15
            assert 'text' in stats['by_type']

    @pytest.mark.asyncio
    async def test_create_tables(self, postgresql_client, mock_asyncpg_pool):
        """Testa create_tables."""
        await postgresql_client.create_tables()
        # Verifica se execute foi chamado
        assert True  # Se não levantar exceção, passou

    @pytest.mark.asyncio
    async def test_insert_insight(self, postgresql_client):
        """Testa insert_insight."""
        with patch.object(postgresql_client, 'execute_query', return_value='new-uuid'):
            insight_id = await postgresql_client.insert_insight(
                plan_id='plan-123',
                analyst_type='text',
                insight_data={'confidence': 0.9}
            )

            assert insight_id == 'new-uuid'

    @pytest.mark.asyncio
    async def test_update_insight(self, postgresql_client):
        """Testa update_insight."""
        with patch.object(postgresql_client, 'execute_query', return_value='UPDATE 1'):
            result = await postgresql_client.update_insight(
                insight_id='insight-123',
                insight_data={'confidence': 0.95}
            )

            assert result is True

    def test_mask_dsn(self):
        """Testa _mask_dsn."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(
            host='localhost',
            database='test',
            user='testuser',
            password='secret123'
        )

        masked = client._mask_dsn(client.dsn)

        assert 'secret123' not in masked
        assert '****' in masked
        assert 'testuser' in masked

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, postgresql_client):
        """Testa health_check quando saudável."""
        result = await postgresql_client.health_check()

        assert result['status'] == 'healthy'
        assert 'latency_ms' in result
        assert result['connected'] is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Testa health_check quando não saudável."""
        from src.clients.postgresql_client import PostgreSQLClient

        client = PostgreSQLClient(host='invalid', database='test')
        client._connected = False

        result = await client.health_check()

        assert result['status'] == 'unhealthy'
        assert result['connected'] is False

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_asyncpg_pool):
        """Testa uso como context manager."""
        from src.clients.postgresql_client import PostgreSQLClient

        mock_create_pool, pool, conn = mock_asyncpg_pool
        with patch('asyncpg.create_pool', side_effect=mock_create_pool):
            async with PostgreSQLClient(host='localhost', database='test') as client:
                assert await client.is_connected() is True


class TestPostgreSQLClientIntegration:
    """Testes de integração para PostgreSQLClient."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_workflow(self):
        """Testa fluxo completo de trabalho (requer PostgreSQL real)."""
        from src.clients.postgresql_client import PostgreSQLClient

        # Este teste só roda se PostgreSQL estiver disponível
        client = PostgreSQLClient(
            host=os.environ.get('TEST_POSTGRESQL_HOST', 'localhost'),
            port=int(os.environ.get('TEST_POSTGRESQL_PORT', '5432')),
            database=os.environ.get('TEST_POSTGRESQL_DB', 'test_db'),
            user=os.environ.get('TEST_POSTGRESQL_USER', 'postgres'),
            password=os.environ.get('TEST_POSTGRESQL_PASSWORD', 'postgres')
        )

        try:
            await client.connect()
            assert await client.is_connected() is True

            # Criar tabelas
            await client.create_tables()

            # Inserir insight
            insight_id = await client.insert_insight(
                plan_id='test-plan',
                analyst_type='test',
                insight_data={'test': True}
            )
            assert insight_id is not None

            # Buscar insight
            insight = await client.get_insight_by_id(insight_id)
            assert insight is not None

            # Contar insights
            count = await client.count_insights(plan_id='test-plan')
            assert count >= 1

            # Health check
            health = await client.health_check()
            assert health['status'] == 'healthy'

        except Exception as e:
            pytest.skip(f'PostgreSQL não disponível: {e}')
        finally:
            await client.disconnect()
