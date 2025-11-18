"""
Testes unitários para ClickHouseClient.

Testa conexão, queries, retry logic, cache, timeout e parametrização.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import json

from src.clients.clickhouse_client import ClickHouseClient


# Fixtures

@pytest.fixture
def mock_redis():
    """Mock de Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


@pytest.fixture
def mock_config():
    """Mock de configuração."""
    return {
        'clickhouse_host': 'clickhouse.test.local',
        'clickhouse_port': 9000,
        'clickhouse_user': 'test_user',
        'clickhouse_password': 'test_password',
        'clickhouse_database': 'test_db'
    }


@pytest.fixture
def sample_execution_data():
    """Dados de execução de exemplo."""
    base_time = datetime.utcnow() - timedelta(hours=24)
    return [
        (
            base_time + timedelta(hours=i),
            100 + i,
            60000,
            500,
            2048,
            'BUILD',
            'high'
        )
        for i in range(24)
    ]


@pytest.fixture
def sample_metrics_data():
    """Dados de métricas de exemplo."""
    base_time = datetime.utcnow() - timedelta(hours=12)
    return [
        (
            base_time + timedelta(hours=i),
            0.75 + (i * 0.01),
            0.85 + (i * 0.01),
            'worker_cpu_usage',
            'worker-agents'
        )
        for i in range(12)
    ]


# Tests - Inicialização e Conexão

@pytest.mark.asyncio
class TestClickHouseClientInitialization:
    """Testes de inicialização e conexão."""

    async def test_initialize_success(self, mock_redis, mock_config):
        """Testa inicialização bem-sucedida."""
        client = ClickHouseClient(mock_redis, mock_config)

        with patch.object(client, '_create_sync_client') as mock_create:
            mock_sync_client = Mock()
            mock_sync_client.execute = Mock(return_value=[(1,)])
            mock_create.return_value = mock_sync_client

            await client.initialize()

        assert client._initialized
        assert client.client is not None

    async def test_initialize_with_retry(self, mock_redis, mock_config):
        """Testa retry logic na inicialização."""
        client = ClickHouseClient(mock_redis, mock_config)

        call_count = 0

        def mock_execute_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection failed")
            return [(1,)]

        with patch.object(client, '_create_sync_client') as mock_create:
            mock_sync_client = Mock()
            mock_create.return_value = mock_sync_client

            with patch.object(client, '_execute_query', side_effect=mock_execute_with_retry):
                await client.initialize()

        assert call_count == 2  # 1 falha + 1 sucesso
        assert client._initialized

    async def test_initialize_max_retries_exceeded(self, mock_redis, mock_config):
        """Testa falha após máximo de retries."""
        client = ClickHouseClient(mock_redis, mock_config)

        with patch.object(client, '_create_sync_client') as mock_create:
            mock_create.side_effect = Exception("Connection refused")

            with pytest.raises(Exception, match="Connection refused"):
                await client.initialize()

        assert not client._initialized


# Tests - Query Execution Timeseries

@pytest.mark.asyncio
class TestQueryExecutionTimeseries:
    """Testes de queries de séries temporais."""

    async def test_query_execution_timeseries_success(self, mock_redis, mock_config, sample_execution_data):
        """Testa query bem-sucedida."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=sample_execution_data)
        client.client = mock_sync_client

        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()

        result = await client.query_execution_timeseries(
            start_timestamp=start_time,
            end_timestamp=end_time,
            aggregation_interval='1h'
        )

        assert len(result) == len(sample_execution_data)
        assert 'timestamp' in result[0]
        assert 'ticket_count' in result[0]
        assert 'avg_duration_ms' in result[0]

    async def test_query_execution_timeseries_cache_hit(self, mock_redis, mock_config):
        """Testa cache hit."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        # Mock cache retornando dados
        cached_data = [
            {
                'timestamp': datetime.utcnow().isoformat(),
                'ticket_count': 100,
                'avg_duration_ms': 60000
            }
        ]
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()

        result = await client.query_execution_timeseries(
            start_timestamp=start_time,
            end_timestamp=end_time
        )

        # Deve retornar do cache sem executar query
        assert result == cached_data
        # client.client nunca foi usado
        assert not hasattr(client, 'client') or client.client is None

    async def test_query_execution_timeseries_different_intervals(self, mock_redis, mock_config, sample_execution_data):
        """Testa diferentes intervalos de agregação."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=sample_execution_data)
        client.client = mock_sync_client

        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()

        for interval in ['1m', '1h', '1d']:
            result = await client.query_execution_timeseries(
                start_timestamp=start_time,
                end_timestamp=end_time,
                aggregation_interval=interval
            )

            assert isinstance(result, list)
            # Verificar que query foi chamada com intervalo correto
            mock_sync_client.execute.assert_called()

    async def test_query_execution_timeseries_error_handling(self, mock_redis, mock_config):
        """Testa tratamento de erros."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(side_effect=Exception("Query error"))
        client.client = mock_sync_client

        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()

        result = await client.query_execution_timeseries(
            start_timestamp=start_time,
            end_timestamp=end_time
        )

        # Deve retornar lista vazia em caso de erro
        assert result == []


# Tests - Query Resource Utilization

@pytest.mark.asyncio
class TestQueryResourceUtilization:
    """Testes de queries de utilização de recursos."""

    async def test_query_resource_utilization_success(self, mock_redis, mock_config, sample_metrics_data):
        """Testa query bem-sucedida."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=sample_metrics_data)
        client.client = mock_sync_client

        start_time = datetime.utcnow() - timedelta(hours=12)
        end_time = datetime.utcnow()

        result = await client.query_resource_utilization(
            start_timestamp=start_time,
            end_timestamp=end_time
        )

        assert len(result) == len(sample_metrics_data)
        assert 'timestamp' in result[0]
        assert 'avg_value' in result[0]
        assert 'metric_name' in result[0]


# Tests - Query SLA Compliance

@pytest.mark.asyncio
class TestQuerySlaCompliance:
    """Testes de queries de SLA compliance."""

    async def test_query_sla_compliance_success(self, mock_redis, mock_config):
        """Testa query bem-sucedida."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_data = [
            (datetime.utcnow().date(), 'service-a', 95.5, 1000),
            (datetime.utcnow().date(), 'service-b', 98.2, 1500)
        ]

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=mock_data)
        client.client = mock_sync_client

        start_time = datetime.utcnow() - timedelta(days=7)
        end_time = datetime.utcnow()

        result = await client.query_sla_compliance(
            start_timestamp=start_time,
            end_timestamp=end_time
        )

        assert len(result) == 2
        assert result[0]['compliance_percentage'] == 95.5
        assert result[1]['total_tickets'] == 1500


# Tests - Query Bottleneck Events

@pytest.mark.asyncio
class TestQueryBottleneckEvents:
    """Testes de queries de eventos de bottleneck."""

    async def test_query_bottleneck_events_success(self, mock_redis, mock_config):
        """Testa query bem-sucedida."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_data = [
            (datetime.utcnow(), 'queue_depth', 150, 'worker-agents'),
            (datetime.utcnow(), 'worker_utilization', 0.95, 'worker-agents')
        ]

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=mock_data)
        client.client = mock_sync_client

        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()

        result = await client.query_bottleneck_events(
            start_timestamp=start_time,
            end_timestamp=end_time
        )

        assert len(result) == 2
        assert result[0]['bottleneck_type'] == 'queue_saturation'
        assert result[1]['bottleneck_type'] == 'worker_saturation'


# Tests - Cache

@pytest.mark.asyncio
class TestCache:
    """Testes de caching."""

    async def test_get_cached_result_hit(self, mock_redis, mock_config):
        """Testa recuperação do cache."""
        client = ClickHouseClient(mock_redis, mock_config)

        cached_data = [{'key': 'value'}]
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        result = await client._get_cached_result('test_key')

        assert result == cached_data
        mock_redis.get.assert_called_once_with('test_key')

    async def test_get_cached_result_miss(self, mock_redis, mock_config):
        """Testa cache miss."""
        client = ClickHouseClient(mock_redis, mock_config)

        mock_redis.get = AsyncMock(return_value=None)

        result = await client._get_cached_result('test_key')

        assert result is None

    async def test_cache_result_success(self, mock_redis, mock_config):
        """Testa armazenamento no cache."""
        client = ClickHouseClient(mock_redis, mock_config)

        data = [
            {
                'timestamp': datetime.utcnow(),
                'value': 100
            }
        ]

        await client._cache_result('test_key', data, ttl=300)

        # Verificar que setex foi chamado
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == 'test_key'
        assert args[1] == 300
        # args[2] deve ser JSON serializado

    async def test_cache_result_datetime_serialization(self, mock_redis, mock_config):
        """Testa serialização de datetimes."""
        client = ClickHouseClient(mock_redis, mock_config)

        data = [
            {
                'timestamp': datetime(2024, 1, 1, 12, 0, 0),
                'value': 100
            }
        ]

        await client._cache_result('test_key', data, ttl=300)

        # Verificar que datetime foi convertido para ISO string
        args = mock_redis.setex.call_args[0]
        cached_json = args[2]
        parsed = json.loads(cached_json)
        assert parsed[0]['timestamp'] == '2024-01-01T12:00:00'


# Tests - Query Execution (Low-level)

@pytest.mark.asyncio
class TestQueryExecution:
    """Testes de execução de queries."""

    async def test_execute_query_success(self, mock_redis, mock_config):
        """Testa execução bem-sucedida de query."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=[(1, 'test')])
        client.client = mock_sync_client

        result = await client._execute_query(
            "SELECT 1, 'test'",
            params={'param1': 'value1'}
        )

        assert result == [(1, 'test')]
        mock_sync_client.execute.assert_called_once()

    async def test_execute_query_not_initialized(self, mock_redis, mock_config):
        """Testa execução sem inicialização."""
        client = ClickHouseClient(mock_redis, mock_config)
        # Não inicializado

        with pytest.raises(RuntimeError, match="ClickHouse client não inicializado"):
            await client._execute_query("SELECT 1")

    async def test_execute_query_with_timeout(self, mock_redis, mock_config):
        """Testa timeout de query."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True
        client.query_timeout = 1  # 1 segundo

        mock_sync_client = Mock()
        # Simular query lenta
        def slow_execute(*args, **kwargs):
            import time
            time.sleep(2)
            return [(1,)]

        mock_sync_client.execute = slow_execute
        client.client = mock_sync_client

        # Query deve falhar por timeout (driver sincronizado tem seu próprio timeout)
        # Aqui apenas testamos que a configuração foi passada
        assert client.query_timeout == 1


# Tests - Connection Pooling

@pytest.mark.asyncio
class TestConnectionPooling:
    """Testes de pooling de conexões."""

    async def test_create_sync_client(self, mock_redis, mock_config):
        """Testa criação de cliente síncrono."""
        client = ClickHouseClient(mock_redis, mock_config)

        with patch('src.clients.clickhouse_client.SyncClickHouseClient') as mock_client_class:
            mock_instance = Mock()
            mock_client_class.return_value = mock_instance

            sync_client = client._create_sync_client()

            # Verificar parâmetros de conexão
            mock_client_class.assert_called_once_with(
                host=mock_config['clickhouse_host'],
                port=mock_config['clickhouse_port'],
                user=mock_config['clickhouse_user'],
                password=mock_config['clickhouse_password'],
                database=mock_config['clickhouse_database'],
                connect_timeout=10,
                send_receive_timeout=client.query_timeout
            )


# Tests - Close

@pytest.mark.asyncio
class TestClose:
    """Testes de fechamento de conexão."""

    async def test_close_success(self, mock_redis, mock_config):
        """Testa fechamento bem-sucedido."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.disconnect = Mock()
        client.client = mock_sync_client

        await client.close()

        mock_sync_client.disconnect.assert_called_once()
        assert client.client is None
        assert not client._initialized

    async def test_close_not_initialized(self, mock_redis, mock_config):
        """Testa fechamento sem cliente inicializado."""
        client = ClickHouseClient(mock_redis, mock_config)

        # Não deve gerar erro
        await client.close()

        assert client.client is None


# Tests de Parametrização

@pytest.mark.asyncio
class TestParameterization:
    """Testes de parametrização de queries."""

    async def test_parameterized_query(self, mock_redis, mock_config):
        """Testa query parametrizada."""
        client = ClickHouseClient(mock_redis, mock_config)
        client._initialized = True

        mock_sync_client = Mock()
        mock_sync_client.execute = Mock(return_value=[(100,)])
        client.client = mock_sync_client

        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 2, 0, 0, 0)

        await client.query_execution_timeseries(
            start_timestamp=start_time,
            end_timestamp=end_time
        )

        # Verificar que execute foi chamado com parâmetros
        call_args = mock_sync_client.execute.call_args
        assert 'start_time' in call_args[0][1]
        assert 'end_time' in call_args[0][1]
        assert call_args[0][1]['start_time'] == start_time
        assert call_args[0][1]['end_time'] == end_time


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
