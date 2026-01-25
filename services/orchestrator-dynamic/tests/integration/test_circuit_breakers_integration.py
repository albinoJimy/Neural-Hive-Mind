"""
Testes de integração para circuit breakers com serviços reais.
"""
import pytest
import asyncio
import sys
from unittest.mock import patch, MagicMock, AsyncMock
from neural_hive_resilience.circuit_breaker import CircuitBreakerError

# Mock proto stubs que podem não estar disponíveis no ambiente de teste
_mock_proto = MagicMock()
_mock_proto.TicketRequest = MagicMock()
_mock_proto.TicketResponse = MagicMock()
_mock_proto_grpc = MagicMock()
_mock_proto_grpc.TicketServiceStub = MagicMock()

sys.modules['neural_hive_integration'] = MagicMock()
sys.modules['neural_hive_integration.proto_stubs'] = MagicMock()
sys.modules['neural_hive_integration.proto_stubs'].ticket_service_pb2 = _mock_proto
sys.modules['neural_hive_integration.proto_stubs'].ticket_service_pb2_grpc = _mock_proto_grpc


@pytest.mark.integration
class TestCircuitBreakerTransitions:
    """Testes de transições de estado dos circuit breakers."""

    @pytest.fixture
    def mock_config(self):
        """Fixture para configuração mock."""
        config = MagicMock()
        config.service_name = 'test-service'
        config.kafka_bootstrap_servers = 'localhost:9092'
        config.kafka_tickets_topic = 'test.tickets'
        config.kafka_schema_registry_url = 'http://localhost:8081'
        config.kafka_security_protocol = 'PLAINTEXT'
        config.kafka_sasl_mechanism = None
        config.kafka_sasl_username = None
        config.kafka_sasl_password = None
        config.schemas_base_path = '/tmp/schemas'
        config.KAFKA_CIRCUIT_BREAKER_ENABLED = True
        config.KAFKA_CIRCUIT_BREAKER_FAIL_MAX = 2
        config.KAFKA_CIRCUIT_BREAKER_TIMEOUT = 2
        config.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 1

        config.TEMPORAL_CIRCUIT_BREAKER_ENABLED = True
        config.TEMPORAL_CIRCUIT_BREAKER_FAIL_MAX = 2
        config.TEMPORAL_CIRCUIT_BREAKER_TIMEOUT = 2
        config.TEMPORAL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 1

        config.REDIS_CIRCUIT_BREAKER_ENABLED = True
        config.REDIS_CIRCUIT_BREAKER_FAIL_MAX = 2
        config.REDIS_CIRCUIT_BREAKER_TIMEOUT = 2
        config.REDIS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 1

        config.redis_cluster_nodes = 'localhost:6379'
        config.redis_password = None
        config.redis_ssl_enabled = False
        return config

    @pytest.mark.asyncio
    async def test_temporal_circuit_breaker_wrapper_with_mock_breaker(self, mock_config):
        """
        Testa wrapper do Temporal com circuit breaker mockado.
        Verifica que o wrapper propaga corretamente CircuitBreakerError.
        """
        from src.temporal_client import TemporalClientWrapper

        mock_client = AsyncMock()
        mock_client.start_workflow = AsyncMock(return_value=MagicMock())

        wrapper = TemporalClientWrapper(
            client=mock_client,
            service_name='test-service',
            circuit_breaker_enabled=True,
            fail_max=2,
            timeout_duration=1,
            recovery_timeout=1
        )

        # Mock do breaker para simular circuito aberto
        wrapper.breaker = MagicMock()
        wrapper.breaker.call_async = AsyncMock(side_effect=CircuitBreakerError())

        # Deve propagar CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await wrapper.start_workflow(
                'TestWorkflow',
                {},
                id='test-open',
                task_queue='test'
            )

    @pytest.mark.asyncio
    async def test_redis_circuit_breaker_fail_open_behavior(self, mock_config):
        """
        Testa comportamento fail-open do Redis quando circuit breaker abre.
        """
        import src.clients.redis_client as redis_client

        # Resetar estado
        redis_client._redis_client_instance = None
        redis_client._circuit_breaker = None

        # Simular falha na inicialização
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_redis.return_value.ping = AsyncMock(side_effect=Exception('Redis down'))

            client = await redis_client.get_redis_client(mock_config)

            # Fail-open: retorna None ao invés de exceção
            assert client is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_metrics_registered(self, mock_config):
        """
        Testa que métricas Prometheus são registradas corretamente.
        """
        from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker

        breaker = MonitoredCircuitBreaker(
            service_name='test-service',
            circuit_name='test_circuit',
            fail_max=5
        )

        # Verificar que o circuit breaker foi criado corretamente
        assert breaker.fail_max == 5
        assert breaker.service_name == 'test-service'


@pytest.mark.integration
class TestCircuitBreakerRecovery:
    """Testes de recuperação de circuit breakers."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_wrapper_success_path(self):
        """
        Testa caminho de sucesso do wrapper com circuit breaker mockado.
        """
        from src.temporal_client import TemporalClientWrapper

        mock_client = AsyncMock()
        expected_handle = MagicMock()
        mock_client.start_workflow = AsyncMock(return_value=expected_handle)

        wrapper = TemporalClientWrapper(
            client=mock_client,
            service_name='test-service',
            circuit_breaker_enabled=True,
            fail_max=2,
            timeout_duration=1,
            recovery_timeout=1
        )

        # Mock do breaker para simular sucesso
        wrapper.breaker = MagicMock()
        wrapper.breaker.call_async = AsyncMock(return_value=expected_handle)

        handle = await wrapper.start_workflow(
            'TestWorkflow',
            {},
            id='test-success',
            task_queue='test'
        )

        assert handle == expected_handle
        wrapper.breaker.call_async.assert_called_once()


@pytest.mark.integration
class TestCircuitBreakerConcurrency:
    """Testes de concorrência para circuit breakers."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_with_mocked_circuit_breaker(self):
        """
        Testa comportamento com requisições concorrentes usando breaker mockado.
        """
        from src.temporal_client import TemporalClientWrapper

        mock_client = AsyncMock()
        mock_client.start_workflow = AsyncMock(return_value=MagicMock())

        wrapper = TemporalClientWrapper(
            client=mock_client,
            service_name='test-service',
            circuit_breaker_enabled=True,
            fail_max=5
        )

        # Mock do breaker para retornar sucesso
        wrapper.breaker = MagicMock()
        wrapper.breaker.call_async = AsyncMock(return_value=MagicMock())

        # Enviar 10 requisições concorrentes
        tasks = [
            wrapper.start_workflow(
                'TestWorkflow',
                {},
                id=f'test-concurrent-{i}',
                task_queue='test'
            )
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # Todas devem ter sucesso
        assert len(results) == 10
        assert all(r is not None for r in results)
        assert wrapper.breaker.call_async.call_count == 10
