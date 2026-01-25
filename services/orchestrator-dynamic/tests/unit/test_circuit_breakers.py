"""
Testes unitários para circuit breakers de Kafka, Temporal e Redis.
"""
import pytest
import asyncio
import sys
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from neural_hive_resilience.circuit_breaker import CircuitBreakerError

# Mock proto stubs que podem não estar disponíveis no ambiente de teste
# Precisa ser feito ANTES de qualquer import de src.clients
_mock_proto = MagicMock()
_mock_proto.TicketRequest = MagicMock()
_mock_proto.TicketResponse = MagicMock()
_mock_proto_grpc = MagicMock()
_mock_proto_grpc.TicketServiceStub = MagicMock()

sys.modules['neural_hive_integration'] = MagicMock()
sys.modules['neural_hive_integration.proto_stubs'] = MagicMock()
sys.modules['neural_hive_integration.proto_stubs'].ticket_service_pb2 = _mock_proto
sys.modules['neural_hive_integration.proto_stubs'].ticket_service_pb2_grpc = _mock_proto_grpc


class TestKafkaProducerCircuitBreaker:
    """Testes para circuit breaker do Kafka Producer."""

    @pytest.fixture
    def mock_config(self):
        """Fixture para configuração mock."""
        config = Mock()
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
        config.KAFKA_CIRCUIT_BREAKER_FAIL_MAX = 3
        config.KAFKA_CIRCUIT_BREAKER_TIMEOUT = 60
        config.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30
        return config

    @pytest.mark.asyncio
    async def test_circuit_breaker_disabled(self, mock_config):
        """Testa que circuit breaker desabilitado não bloqueia operações."""
        mock_config.KAFKA_CIRCUIT_BREAKER_ENABLED = False

        # Import direto do módulo para evitar problemas com __init__.py
        from src.clients.kafka_producer import KafkaProducerClient

        producer = KafkaProducerClient(mock_config)
        assert producer.circuit_breaker_enabled is False
        assert producer.producer_breaker is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_initialized(self, mock_config):
        """Testa que circuit breaker é inicializado corretamente."""
        from src.clients.kafka_producer import KafkaProducerClient

        producer = KafkaProducerClient(mock_config)

        # Simular inicialização sem conectar ao Kafka real
        with patch.object(producer, '_configure_security', return_value={}):
            with patch('confluent_kafka.Producer'):
                with patch('confluent_kafka.schema_registry.SchemaRegistryClient'):
                    with patch('pathlib.Path.read_text', return_value='{}'):
                        with patch('confluent_kafka.schema_registry.avro.AvroSerializer'):
                            await producer.initialize()

        assert producer.circuit_breaker_enabled is True
        assert producer.producer_breaker is not None
        assert producer.producer_breaker.fail_max == 3

    @pytest.mark.asyncio
    async def test_execute_with_breaker_success(self, mock_config):
        """Testa execução bem-sucedida através do circuit breaker."""
        from src.clients.kafka_producer import KafkaProducerClient

        producer = KafkaProducerClient(mock_config)
        producer.producer_breaker = MagicMock()
        producer.producer_breaker.call_async = AsyncMock(return_value='success')

        async def mock_func():
            return 'success'

        result = await producer._execute_with_breaker(mock_func)
        assert result == 'success'
        producer.producer_breaker.call_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_breaker_disabled_bypasses(self, mock_config):
        """Testa que circuit breaker desabilitado bypassa proteção."""
        from src.clients.kafka_producer import KafkaProducerClient

        producer = KafkaProducerClient(mock_config)
        producer.circuit_breaker_enabled = False

        async def mock_func():
            return 'direct_result'

        result = await producer._execute_with_breaker(mock_func)
        assert result == 'direct_result'


class TestTemporalClientCircuitBreaker:
    """Testes para circuit breaker do Temporal Client."""

    @pytest.fixture
    def mock_temporal_client(self):
        """Fixture para cliente Temporal mock."""
        client = AsyncMock()
        client.start_workflow = AsyncMock(return_value=Mock())
        client.get_workflow_handle = Mock(return_value=Mock())
        return client

    @pytest.mark.asyncio
    async def test_wrapper_initialization(self, mock_temporal_client):
        """Testa inicialização do wrapper com circuit breaker."""
        from src.temporal_client import TemporalClientWrapper

        wrapper = TemporalClientWrapper(
            client=mock_temporal_client,
            service_name='test-service',
            circuit_breaker_enabled=True,
            fail_max=3,
            timeout_duration=60,
            recovery_timeout=30
        )

        assert wrapper.circuit_breaker_enabled is True
        assert wrapper.breaker is not None
        assert wrapper.breaker.fail_max == 3

    @pytest.mark.asyncio
    async def test_wrapper_disabled(self, mock_temporal_client):
        """Testa wrapper com circuit breaker desabilitado."""
        from src.temporal_client import TemporalClientWrapper

        wrapper = TemporalClientWrapper(
            client=mock_temporal_client,
            service_name='test-service',
            circuit_breaker_enabled=False
        )

        assert wrapper.circuit_breaker_enabled is False
        assert wrapper.breaker is None

    @pytest.mark.asyncio
    async def test_start_workflow_with_circuit_breaker(self, mock_temporal_client):
        """Testa start_workflow protegido por circuit breaker."""
        from src.temporal_client import TemporalClientWrapper

        wrapper = TemporalClientWrapper(
            client=mock_temporal_client,
            service_name='test-service',
            circuit_breaker_enabled=True,
            fail_max=3
        )

        # Mock do circuit breaker para simular sucesso
        wrapper.breaker = MagicMock()
        wrapper.breaker.call_async = AsyncMock(return_value=Mock())

        handle = await wrapper.start_workflow(
            'TestWorkflow',
            {'arg': 'value'},
            id='test-workflow-1',
            task_queue='test-queue'
        )

        assert handle is not None
        wrapper.breaker.call_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_workflow_circuit_breaker_open(self, mock_temporal_client):
        """Testa que CircuitBreakerError é propagado corretamente."""
        from src.temporal_client import TemporalClientWrapper

        wrapper = TemporalClientWrapper(
            client=mock_temporal_client,
            service_name='test-service',
            circuit_breaker_enabled=True
        )

        # Mock do circuit breaker para simular circuito aberto
        wrapper.breaker = MagicMock()
        wrapper.breaker.call_async = AsyncMock(side_effect=CircuitBreakerError())

        with pytest.raises(CircuitBreakerError):
            await wrapper.start_workflow(
                'TestWorkflow',
                {},
                id='test-1',
                task_queue='test'
            )

    @pytest.mark.asyncio
    async def test_getattr_delegates_to_client(self, mock_temporal_client):
        """Testa que atributos não implementados são delegados."""
        from src.temporal_client import TemporalClientWrapper

        mock_temporal_client.some_method = Mock(return_value='delegated')

        wrapper = TemporalClientWrapper(
            client=mock_temporal_client,
            service_name='test-service'
        )

        result = wrapper.some_method()
        assert result == 'delegated'


class TestRedisCircuitBreaker:
    """Testes para circuit breaker do Redis Client."""

    @pytest.mark.asyncio
    async def test_redis_get_safe_with_circuit_breaker(self):
        """Testa redis_get_safe protegido por circuit breaker."""
        # Import direto do módulo
        from src.clients.redis_client import (
            redis_get_safe,
            _redis_client_instance,
            _circuit_breaker
        )
        import src.clients.redis_client as redis_client_module

        # Resetar estado global
        redis_client_module._redis_client_instance = AsyncMock()
        redis_client_module._redis_client_instance.get = AsyncMock(return_value='test-value')

        redis_client_module._circuit_breaker = MagicMock()
        redis_client_module._circuit_breaker.call_async = AsyncMock(return_value='test-value')

        result = await redis_client_module.redis_get_safe('test-key')

        assert result == 'test-value'
        redis_client_module._circuit_breaker.call_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_get_safe_circuit_breaker_open(self):
        """Testa que circuit breaker aberto retorna None."""
        import src.clients.redis_client as redis_client_module

        redis_client_module._redis_client_instance = AsyncMock()
        redis_client_module._circuit_breaker = MagicMock()
        redis_client_module._circuit_breaker.call_async = AsyncMock(side_effect=CircuitBreakerError())

        result = await redis_client_module.redis_get_safe('test-key')

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_setex_safe_with_circuit_breaker(self):
        """Testa redis_setex_safe protegido por circuit breaker."""
        import src.clients.redis_client as redis_client_module

        redis_client_module._redis_client_instance = AsyncMock()
        redis_client_module._redis_client_instance.setex = AsyncMock(return_value=True)

        redis_client_module._circuit_breaker = MagicMock()
        redis_client_module._circuit_breaker.call_async = AsyncMock(return_value=True)

        result = await redis_client_module.redis_setex_safe('test-key', 60, 'test-value')

        assert result is True
        redis_client_module._circuit_breaker.call_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_setex_safe_circuit_breaker_open(self):
        """Testa que circuit breaker aberto retorna False."""
        import src.clients.redis_client as redis_client_module

        redis_client_module._redis_client_instance = AsyncMock()
        redis_client_module._circuit_breaker = MagicMock()
        redis_client_module._circuit_breaker.call_async = AsyncMock(side_effect=CircuitBreakerError())

        result = await redis_client_module.redis_setex_safe('test-key', 60, 'test-value')

        assert result is False

    @pytest.mark.asyncio
    async def test_redis_ping_safe_with_circuit_breaker(self):
        """Testa redis_ping_safe protegido por circuit breaker."""
        import src.clients.redis_client as redis_client_module

        redis_client_module._redis_client_instance = AsyncMock()
        redis_client_module._redis_client_instance.ping = AsyncMock(return_value=True)

        redis_client_module._circuit_breaker = MagicMock()
        redis_client_module._circuit_breaker.call_async = AsyncMock(return_value=True)

        result = await redis_client_module.redis_ping_safe()

        assert result is True

    @pytest.mark.asyncio
    async def test_redis_ping_safe_circuit_breaker_open(self):
        """Testa que circuit breaker aberto retorna False para ping."""
        import src.clients.redis_client as redis_client_module

        redis_client_module._redis_client_instance = AsyncMock()
        redis_client_module._circuit_breaker = MagicMock()
        redis_client_module._circuit_breaker.call_async = AsyncMock(side_effect=CircuitBreakerError())

        result = await redis_client_module.redis_ping_safe()

        assert result is False

    def test_get_circuit_breaker_state_not_initialized(self):
        """Testa estado quando circuit breaker não inicializado."""
        import src.clients.redis_client as redis_client_module

        redis_client_module._circuit_breaker = None

        state = redis_client_module.get_circuit_breaker_state()

        assert state['state'] == 'not_initialized'
        assert state['failure_count'] == 0

    def test_get_circuit_breaker_state_initialized(self):
        """Testa estado quando circuit breaker inicializado."""
        import src.clients.redis_client as redis_client_module

        mock_breaker = MagicMock()
        mock_breaker.current_state = 'closed'
        mock_breaker.fail_counter = 2
        mock_breaker.fail_max = 5
        mock_breaker.recovery_timeout = 60

        redis_client_module._circuit_breaker = mock_breaker

        state = redis_client_module.get_circuit_breaker_state()

        assert state['state'] == 'CLOSED'
        assert state['failure_count'] == 2
        assert state['failure_threshold'] == 5
        assert state['recovery_timeout'] == 60
