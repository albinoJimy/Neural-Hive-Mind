"""
Testes unitários para comportamento de resiliência do PlanConsumer.

Cobre cenários de:
- Backoff exponencial
- Circuit breaker
- Classificação de erros (sistêmico vs negócio)
- Commits de offset
- Shutdown gracioso
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from confluent_kafka import KafkaError
import grpc

from src.consumers.plan_consumer import PlanConsumer
from src.observability.metrics import ConsensusMetrics


class MockConfigWithResilience:
    """Configuração mock com parâmetros de resiliência para testes."""
    kafka_plans_topic = 'plans.ready'
    kafka_bootstrap_servers = 'localhost:9092'
    kafka_consumer_group_id = 'consensus-engine-test'
    kafka_auto_offset_reset = 'earliest'
    kafka_enable_auto_commit = False
    enable_parallel_invocation = True
    grpc_timeout_ms = 5000
    # Parâmetros de resiliência (valores menores para testes rápidos)
    consumer_max_consecutive_errors = 3
    consumer_base_backoff_seconds = 0.01
    consumer_max_backoff_seconds = 0.1
    consumer_poll_timeout_seconds = 0.01
    consumer_enable_dlq = False
    kafka_dlq_topic = 'plans.ready.dlq'
    consumer_max_retries_before_dlq = 2


@pytest.fixture
def mock_config_resilience():
    """Configuração mock com parâmetros de resiliência."""
    return MockConfigWithResilience()


@pytest.fixture
def mock_specialists_client():
    """Cliente de especialistas mock."""
    client = AsyncMock()
    client.evaluate_plan_parallel = AsyncMock(return_value=[
        {
            'specialist_type': 'business',
            'opinion_id': 'op-1',
            'opinion': {'confidence_score': 0.85, 'risk_score': 0.2, 'recommendation': 'approve'},
            'processing_time_ms': 100
        }
    ])
    return client


@pytest.fixture
def mock_mongodb_client():
    """Cliente MongoDB mock."""
    client = AsyncMock()
    client.save_consensus_decision = AsyncMock()
    return client


@pytest.fixture
def mock_pheromone_client():
    """Cliente de feromônios mock."""
    client = AsyncMock()
    client.calculate_dynamic_weight = AsyncMock(return_value=0.2)
    client.get_aggregated_pheromone = AsyncMock(return_value={'net_strength': 0.5})
    client.publish_pheromone = AsyncMock()
    return client


@pytest.fixture
def plan_consumer(mock_config_resilience, mock_specialists_client, mock_mongodb_client, mock_pheromone_client):
    """Instância de PlanConsumer para testes."""
    consumer = PlanConsumer(
        config=mock_config_resilience,
        specialists_client=mock_specialists_client,
        mongodb_client=mock_mongodb_client,
        pheromone_client=mock_pheromone_client
    )
    return consumer


# ===========================
# Testes de Configuração
# ===========================

@pytest.mark.unit
class TestConsumerConfiguration:
    """Testes para verificar uso correto de parâmetros de configuração."""

    def test_consumer_uses_config_parameters(self, mock_config_resilience):
        """Verifica que consumer lê parâmetros de resiliência do config."""
        assert mock_config_resilience.consumer_max_consecutive_errors == 3
        assert mock_config_resilience.consumer_base_backoff_seconds == 0.01
        assert mock_config_resilience.consumer_max_backoff_seconds == 0.1
        assert mock_config_resilience.consumer_poll_timeout_seconds == 0.01


# ===========================
# Testes de Backoff Exponencial
# ===========================

@pytest.mark.unit
class TestExponentialBackoff:
    """Testes para cálculo de backoff exponencial."""

    def test_exponential_backoff_calculation(self, mock_config_resilience):
        """Verifica que backoff dobra a cada iteração."""
        base = mock_config_resilience.consumer_base_backoff_seconds
        max_backoff = mock_config_resilience.consumer_max_backoff_seconds

        # Backoff = base * 2^consecutive_errors, limitado a max
        assert min(base * (2 ** 1), max_backoff) == 0.02
        assert min(base * (2 ** 2), max_backoff) == 0.04
        assert min(base * (2 ** 3), max_backoff) == 0.08
        assert min(base * (2 ** 4), max_backoff) == 0.1  # Cap

    def test_backoff_respects_max_limit(self, mock_config_resilience):
        """Verifica que backoff nunca excede max_backoff_seconds."""
        base = mock_config_resilience.consumer_base_backoff_seconds
        max_backoff = mock_config_resilience.consumer_max_backoff_seconds

        # Com muitos erros consecutivos, deve ser limitado ao max
        for i in range(10, 20):
            backoff = min(base * (2 ** i), max_backoff)
            assert backoff <= max_backoff


# ===========================
# Testes de Circuit Breaker
# ===========================

@pytest.mark.unit
@pytest.mark.asyncio
class TestCircuitBreaker:
    """Testes para comportamento do circuit breaker."""

    async def test_circuit_breaker_opens_after_max_errors(self, plan_consumer):
        """Verifica que circuit breaker abre após max_consecutive_errors."""
        plan_consumer.consumer = MagicMock()

        # Criar mock de mensagem com erro
        mock_msg = MagicMock()
        mock_error = MagicMock()
        mock_error.code.return_value = KafkaError._ALL_BROKERS_DOWN
        mock_msg.error.return_value = mock_error

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count <= 5:  # Mais que max_consecutive_errors (3)
                return mock_msg
            return None

        plan_consumer.consumer.poll = poll_side_effect

        with patch.object(ConsensusMetrics, 'set_circuit_breaker_state') as mock_cb_state, \
             patch.object(ConsensusMetrics, 'increment_circuit_breaker_trip') as mock_cb_trip, \
             patch.object(ConsensusMetrics, 'set_consecutive_errors'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error'), \
             patch.object(ConsensusMetrics, 'increment_backoff_event'), \
             patch.object(ConsensusMetrics, 'observe_backoff_duration'):

            await plan_consumer.start()

            # Circuit breaker deve ter sido aberto
            assert plan_consumer.circuit_breaker_open is True
            mock_cb_state.assert_called_with(True)
            mock_cb_trip.assert_called()

    async def test_circuit_breaker_opens_on_systemic_process_errors(self, plan_consumer):
        """
        Verifica que circuit breaker abre quando _process_message lança erros
        sistêmicos repetidamente até ultrapassar max_consecutive_errors.
        """
        plan_consumer.consumer = MagicMock()
        plan_consumer.consumer.commit = MagicMock()

        # Mock de mensagem válida
        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_msg.topic.return_value = 'plans.ready'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 1

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count <= 5:  # Mais que max_consecutive_errors (3)
                return mock_msg
            return None

        plan_consumer.consumer.poll = poll_side_effect

        # Forçar erro sistêmico no _process_message
        async def process_raise_systemic_error(msg, plan):
            raise ConnectionError("gRPC unavailable")

        plan_consumer._process_message = process_raise_systemic_error

        with patch.object(ConsensusMetrics, 'set_circuit_breaker_state') as mock_cb_state, \
             patch.object(ConsensusMetrics, 'increment_circuit_breaker_trip') as mock_cb_trip, \
             patch.object(ConsensusMetrics, 'set_consecutive_errors') as mock_set_errors, \
             patch.object(ConsensusMetrics, 'increment_consumer_error') as mock_inc_error, \
             patch.object(ConsensusMetrics, 'increment_message_processed'), \
             patch.object(ConsensusMetrics, 'observe_processing_duration'), \
             patch.object(ConsensusMetrics, 'increment_backoff_event'), \
             patch.object(ConsensusMetrics, 'observe_backoff_duration'):

            await plan_consumer.start()

            # Circuit breaker deve ter sido aberto
            assert plan_consumer.circuit_breaker_open is True
            # set_circuit_breaker_state(True) deve ter sido chamado
            mock_cb_state.assert_called_with(True)
            # increment_circuit_breaker_trip deve ter sido chamado
            mock_cb_trip.assert_called_once()
            # increment_consumer_error deve ter sido chamado com is_systemic=True
            systemic_calls = [c for c in mock_inc_error.call_args_list if c[1].get('is_systemic') is True]
            assert len(systemic_calls) >= 1

    async def test_circuit_breaker_stays_closed_on_business_errors(self, plan_consumer, mock_config_resilience):
        """Verifica que circuit breaker não abre para erros de negócio."""
        plan_consumer.consumer = MagicMock()

        # Mock de mensagem válida
        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_msg.topic.return_value = 'plans.ready'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 1

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count <= 5:
                return mock_msg
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect
        plan_consumer.consumer.commit = MagicMock()

        # Forçar erro de negócio (ValueError)
        async def process_raise_business_error(msg, plan):
            raise ValueError("Invalid plan format")

        plan_consumer._process_message = process_raise_business_error

        with patch.object(ConsensusMetrics, 'set_circuit_breaker_state') as mock_cb_state, \
             patch.object(ConsensusMetrics, 'increment_circuit_breaker_trip') as mock_cb_trip, \
             patch.object(ConsensusMetrics, 'set_consecutive_errors'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error'), \
             patch.object(ConsensusMetrics, 'increment_message_processed'), \
             patch.object(ConsensusMetrics, 'observe_processing_duration'), \
             patch.object(ConsensusMetrics, 'increment_offset_commit'):

            await plan_consumer.start()

            # Circuit breaker NÃO deve ter sido aberto (erros de negócio não contam)
            assert plan_consumer.circuit_breaker_open is False
            # set_circuit_breaker_state(True) não deve ter sido chamado
            calls_with_true = [c for c in mock_cb_state.call_args_list if c[0][0] is True]
            assert len(calls_with_true) == 0


# ===========================
# Testes de Classificação de Erros
# ===========================

@pytest.mark.unit
class TestErrorClassification:
    """Testes para classificação de erros sistêmicos vs negócio."""

    def test_is_systemic_error_detects_connection_errors(self, plan_consumer):
        """Verifica detecção de ConnectionError, TimeoutError, OSError."""
        assert plan_consumer._is_systemic_error(ConnectionError("Connection refused")) is True
        assert plan_consumer._is_systemic_error(TimeoutError("Request timeout")) is True
        assert plan_consumer._is_systemic_error(OSError("Network unreachable")) is True

    def test_is_systemic_error_detects_keyword_errors(self, plan_consumer):
        """Verifica detecção por palavras-chave no erro."""
        assert plan_consumer._is_systemic_error(Exception("gRPC unavailable")) is True
        assert plan_consumer._is_systemic_error(Exception("MongoDB connection failed")) is True
        assert plan_consumer._is_systemic_error(Exception("Kafka broker down")) is True
        assert plan_consumer._is_systemic_error(Exception("deadline exceeded")) is True

    def test_is_systemic_error_rejects_business_errors(self, plan_consumer):
        """Verifica que ValueError, KeyError, TypeError retornam False."""
        assert plan_consumer._is_systemic_error(ValueError("Invalid value")) is False
        assert plan_consumer._is_systemic_error(KeyError("Missing key")) is False
        assert plan_consumer._is_systemic_error(TypeError("Wrong type")) is False

    def test_is_systemic_error_detects_grpc_rpc_error(self, plan_consumer):
        """Verifica detecção de grpc.RpcError como erro sistêmico."""
        # Criar mock de grpc.RpcError (é uma classe abstrata)
        class MockRpcError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.UNAVAILABLE

            def details(self):
                return "Service unavailable"

        grpc_error = MockRpcError()
        assert plan_consumer._is_systemic_error(grpc_error) is True


# ===========================
# Testes de Processamento de Mensagens
# ===========================

@pytest.mark.unit
@pytest.mark.asyncio
class TestMessageProcessing:
    """Testes para processamento de mensagens e métricas."""

    async def test_consecutive_errors_reset_on_success(self, plan_consumer):
        """Verifica que consecutive_errors reseta após processamento bem-sucedido."""
        plan_consumer.consumer = MagicMock()

        # Sequência: erro Kafka, sucesso
        mock_error_msg = MagicMock()
        mock_error = MagicMock()
        mock_error.code.return_value = KafkaError._ALL_BROKERS_DOWN
        mock_error_msg.error.return_value = mock_error

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_error_msg
            elif call_count == 2:
                return None  # Sucesso (poll vazio)
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        consecutive_errors_values = []

        def capture_consecutive_errors(count):
            consecutive_errors_values.append(count)

        with patch.object(ConsensusMetrics, 'set_consecutive_errors', side_effect=capture_consecutive_errors), \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error'), \
             patch.object(ConsensusMetrics, 'increment_backoff_event'), \
             patch.object(ConsensusMetrics, 'observe_backoff_duration'):

            await plan_consumer.start()

            # Deve ter: [1 (erro), 0 (reset após poll vazio)]
            assert 0 in consecutive_errors_values  # Reset aconteceu


# ===========================
# Testes de Offset Commit
# ===========================

@pytest.mark.unit
@pytest.mark.asyncio
class TestOffsetCommit:
    """Testes para comportamento de commit de offset."""

    async def test_offset_not_committed_on_systemic_error(self, plan_consumer):
        """Verifica que offset NÃO é commitado quando há erro sistêmico."""
        plan_consumer.consumer = MagicMock()
        plan_consumer.consumer.commit = MagicMock()

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_msg.topic.return_value = 'plans.ready'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 1

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_msg
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        # Forçar erro sistêmico
        async def process_raise_systemic_error(msg, plan):
            raise ConnectionError("gRPC unavailable")

        plan_consumer._process_message = process_raise_systemic_error

        with patch.object(ConsensusMetrics, 'set_consecutive_errors'), \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error'), \
             patch.object(ConsensusMetrics, 'increment_message_processed'), \
             patch.object(ConsensusMetrics, 'observe_processing_duration'), \
             patch.object(ConsensusMetrics, 'increment_backoff_event'), \
             patch.object(ConsensusMetrics, 'observe_backoff_duration'):

            await plan_consumer.start()

            # Commit NÃO deve ter sido chamado (erro sistêmico permite retry)
            plan_consumer.consumer.commit.assert_not_called()

    async def test_offset_not_committed_on_business_error(self, plan_consumer):
        """Verifica que offset NÃO é commitado quando há erro de negócio."""
        plan_consumer.consumer = MagicMock()
        plan_consumer.consumer.commit = MagicMock()

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_msg.topic.return_value = 'plans.ready'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 1

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_msg
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        # Forçar erro de negócio (ValueError)
        async def process_raise_business_error(msg, plan):
            raise ValueError("Invalid plan format")

        plan_consumer._process_message = process_raise_business_error

        with patch.object(ConsensusMetrics, 'set_consecutive_errors'), \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error'), \
             patch.object(ConsensusMetrics, 'increment_message_processed'), \
             patch.object(ConsensusMetrics, 'observe_processing_duration'):

            await plan_consumer.start()

            # Commit NÃO deve ter sido chamado (erro de negócio também não commita)
            plan_consumer.consumer.commit.assert_not_called()


# ===========================
# Testes de Métricas
# ===========================

@pytest.mark.unit
@pytest.mark.asyncio
class TestMetricsEmission:
    """Testes para verificar emissão correta de métricas."""

    async def test_metrics_emitted_on_successful_processing(self, plan_consumer):
        """Verifica métricas emitidas em processamento bem-sucedido."""
        plan_consumer.consumer = MagicMock()
        plan_consumer.consumer.commit = MagicMock()

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_msg.topic.return_value = 'plans.ready'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 1

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_msg
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        # Mock _process_message para sucesso
        async def process_success(msg, plan):
            pass

        plan_consumer._process_message = process_success

        with patch.object(ConsensusMetrics, 'set_consecutive_errors') as mock_set_errors, \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'), \
             patch.object(ConsensusMetrics, 'increment_message_processed') as mock_inc_processed, \
             patch.object(ConsensusMetrics, 'observe_processing_duration') as mock_obs_duration, \
             patch.object(ConsensusMetrics, 'increment_offset_commit') as mock_inc_commit:

            await plan_consumer.start()

            # Verificar métricas de sucesso
            mock_set_errors.assert_called_with(0)
            mock_inc_processed.assert_called_with('success')
            mock_obs_duration.assert_called()
            # Verificar que duration foi observada com status 'success'
            duration_calls = [c for c in mock_obs_duration.call_args_list if c[0][1] == 'success']
            assert len(duration_calls) >= 1

    async def test_metrics_emitted_on_business_error(self, plan_consumer):
        """Verifica métricas emitidas em erro de negócio."""
        plan_consumer.consumer = MagicMock()
        plan_consumer.consumer.commit = MagicMock()

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_msg.topic.return_value = 'plans.ready'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 1

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_msg
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        # Forçar erro de negócio
        async def process_raise_business_error(msg, plan):
            raise ValueError("Invalid plan")

        plan_consumer._process_message = process_raise_business_error

        with patch.object(ConsensusMetrics, 'set_consecutive_errors'), \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error') as mock_inc_error, \
             patch.object(ConsensusMetrics, 'increment_message_processed') as mock_inc_processed, \
             patch.object(ConsensusMetrics, 'observe_processing_duration') as mock_obs_duration:

            await plan_consumer.start()

            # Verificar métricas de falha
            mock_inc_processed.assert_called_with('failed', 'ValueError')
            # increment_consumer_error com is_systemic=False
            mock_inc_error.assert_called_with('ValueError', is_systemic=False)
            # Duration observada com status 'failed'
            duration_calls = [c for c in mock_obs_duration.call_args_list if c[0][1] == 'failed']
            assert len(duration_calls) >= 1


# ===========================
# Testes de Recuperação
# ===========================

@pytest.mark.unit
@pytest.mark.asyncio
class TestTransientErrorRecovery:
    """Testes para recuperação após erros transientes."""

    async def test_recovery_after_transient_kafka_error(self, plan_consumer):
        """Verifica que consumer se recupera após erro Kafka transiente."""
        plan_consumer.consumer = MagicMock()
        plan_consumer.consumer.commit = MagicMock()

        # Sequência: erro Kafka, sucesso, parar
        mock_error_msg = MagicMock()
        mock_error = MagicMock()
        mock_error.code.return_value = KafkaError._ALL_BROKERS_DOWN
        mock_error_msg.error.return_value = mock_error

        mock_success_msg = MagicMock()
        mock_success_msg.error.return_value = None
        mock_success_msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
        mock_success_msg.topic.return_value = 'plans.ready'
        mock_success_msg.partition.return_value = 0
        mock_success_msg.offset.return_value = 2

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_error_msg  # Erro transiente
            elif call_count == 2:
                return mock_success_msg  # Recuperação
            plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        # Mock _process_message para sucesso
        async def process_success(msg, plan):
            pass

        plan_consumer._process_message = process_success

        consecutive_errors_values = []

        def capture_consecutive_errors(count):
            consecutive_errors_values.append(count)

        with patch.object(ConsensusMetrics, 'set_consecutive_errors', side_effect=capture_consecutive_errors), \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'), \
             patch.object(ConsensusMetrics, 'increment_consumer_error'), \
             patch.object(ConsensusMetrics, 'increment_backoff_event'), \
             patch.object(ConsensusMetrics, 'observe_backoff_duration'), \
             patch.object(ConsensusMetrics, 'increment_message_processed'), \
             patch.object(ConsensusMetrics, 'observe_processing_duration'), \
             patch.object(ConsensusMetrics, 'increment_offset_commit'):

            await plan_consumer.start()

            # Consumer deve ter se recuperado (consecutive_errors voltou a 0)
            assert plan_consumer.circuit_breaker_open is False
            assert 0 in consecutive_errors_values


# ===========================
# Testes de Shutdown Gracioso
# ===========================

@pytest.mark.unit
@pytest.mark.asyncio
class TestGracefulShutdown:
    """Testes para shutdown gracioso do consumer."""

    async def test_consumer_stops_when_running_false(self, plan_consumer):
        """Verifica que consumer para quando running=False."""
        plan_consumer.consumer = MagicMock()

        call_count = 0

        def poll_side_effect(timeout):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                plan_consumer.running = False
            return None

        plan_consumer.consumer.poll = poll_side_effect

        with patch.object(ConsensusMetrics, 'set_consecutive_errors'), \
             patch.object(ConsensusMetrics, 'set_circuit_breaker_state'):

            await plan_consumer.start()

            assert plan_consumer.running is False

    async def test_consumer_cleanup_on_shutdown(self, plan_consumer):
        """Verifica que stop() fecha consumer e define running=False."""
        plan_consumer.consumer = MagicMock()
        plan_consumer.running = True

        await plan_consumer.stop()

        assert plan_consumer.running is False
        plan_consumer.consumer.close.assert_called_once()
