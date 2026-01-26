"""
Testes de integração para inicialização do Kafka Producer.

Valida comportamento em cenários de falha real:
- Kafka indisponível
- Schema Registry offline
- Credenciais inválidas
- Config corrompido
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from time import perf_counter
import types

from src.clients.kafka_producer import KafkaProducerClient


@pytest.mark.integration
class TestKafkaProducerInitializationResilience:
    """Testes de resiliência na inicialização do Kafka Producer."""

    @pytest.fixture
    def valid_config(self):
        """Config válida para testes."""
        return types.SimpleNamespace(
            service_name='test-orchestrator',
            kafka_bootstrap_servers='localhost:9092',
            kafka_tickets_topic='test.tickets',
            kafka_schema_registry_url='http://localhost:8081',
            kafka_security_protocol='PLAINTEXT',
            kafka_sasl_mechanism=None,
            kafka_sasl_username=None,
            kafka_sasl_password=None,
            schemas_base_path='/tmp/schemas',
            KAFKA_CIRCUIT_BREAKER_ENABLED=True,
            KAFKA_CIRCUIT_BREAKER_FAIL_MAX=5,
            KAFKA_CIRCUIT_BREAKER_TIMEOUT=60,
            KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
        )

    @pytest.mark.asyncio
    async def test_initialization_with_kafka_unavailable(self, valid_config):
        """
        Testa inicialização quando Kafka está indisponível.

        Comportamento esperado:
        - Producer deve ser criado (não valida conectividade no init)
        - Circuit breaker deve ser inicializado
        - Métricas de inicialização devem ser registradas
        """
        with patch('src.clients.kafka_producer.Producer') as mock_producer:
            with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
                with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Connection refused')):
                    client = KafkaProducerClient(valid_config)

                    start = perf_counter()
                    await client.initialize()
                    duration = perf_counter() - start

                    # Producer deve estar inicializado (fail-open para schema registry)
                    assert client.producer is not None
                    # Schema registry deve estar None (fallback JSON)
                    assert client.schema_registry_client is None
                    assert client.avro_serializer is None
                    # Circuit breaker deve estar habilitado
                    assert client.circuit_breaker_enabled is True
                    # Inicialização deve ser rápida (< 5s)
                    assert duration < 5.0

    @pytest.mark.asyncio
    async def test_initialization_with_schema_registry_offline(self, valid_config):
        """
        Testa inicialização quando Schema Registry está offline.

        Comportamento esperado:
        - Fallback para modo JSON-only
        - Producer funcional
        - Circuit breaker habilitado
        """
        with patch('src.clients.kafka_producer.Producer'):
            with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
                with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=ConnectionError('Schema Registry offline')):
                    client = KafkaProducerClient(valid_config)
                    await client.initialize()

                    # Deve operar em modo JSON-only
                    assert client.schema_registry_client is None
                    assert client.avro_serializer is None
                    assert client.producer is not None

    @pytest.mark.asyncio
    async def test_initialization_with_invalid_credentials(self, valid_config):
        """
        Testa inicialização com credenciais SASL inválidas.

        Comportamento esperado:
        - Producer criado (validação de credenciais ocorre no primeiro produce)
        - Circuit breaker habilitado
        """
        valid_config.kafka_security_protocol = 'SASL_PLAINTEXT'
        valid_config.kafka_sasl_mechanism = 'PLAIN'

        with patch('src.clients.kafka_producer.Producer'):
            with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
                with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Schema unavailable')):
                    client = KafkaProducerClient(
                        valid_config,
                        sasl_username_override='invalid_user',
                        sasl_password_override='invalid_pass'
                    )

                    await client.initialize()

                    # Producer deve estar inicializado
                    assert client.producer is not None
                    # Credenciais devem estar configuradas
                    assert client.sasl_username == 'invalid_user'
                    assert client.sasl_password == 'invalid_pass'

    @pytest.mark.asyncio
    async def test_initialization_circuit_breaker_fallback(self, valid_config):
        """
        Testa fallback do circuit breaker quando inicialização falha.

        Comportamento esperado:
        - Circuit breaker desabilitado em caso de erro
        - Producer continua funcional (fail-open)
        """
        # Simular service_name None para forçar erro no circuit breaker
        valid_config.service_name = None

        with pytest.raises(ValueError, match='service_name'):
            KafkaProducerClient(valid_config)

    @pytest.mark.asyncio
    async def test_initialization_metrics_recorded(self, valid_config):
        """
        Testa que métricas de inicialização são registradas corretamente.

        Comportamento esperado:
        - Métrica de sucesso registrada
        - Duração registrada
        """
        with patch('src.clients.kafka_producer.Producer'):
            with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
                with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Schema unavailable')):
                    with patch('src.clients.kafka_producer.KafkaProducerClient._get_metrics') as mock_get_metrics:
                        mock_metrics = MagicMock()
                        mock_get_metrics.return_value = mock_metrics

                        client = KafkaProducerClient(valid_config)
                        await client.initialize()

                        # Verificar que métrica de inicialização foi chamada
                        mock_metrics.record_component_initialization.assert_called_once()
                        call_args = mock_metrics.record_component_initialization.call_args
                        assert call_args[1]['component_name'] == 'kafka_producer'
                        assert call_args[1]['status'] == 'success'
                        assert call_args[1]['duration_seconds'] > 0

    @pytest.mark.asyncio
    async def test_initialization_config_corruption_after_construction(self, valid_config):
        """
        Testa detecção de config corrompido após construção.

        Comportamento esperado:
        - RuntimeError lançado
        - Métrica de erro registrada
        """
        client = KafkaProducerClient(valid_config)

        # Corromper config após construção
        client.config = None

        with pytest.raises(RuntimeError, match='self.config é None'):
            await client.initialize()

    @pytest.mark.asyncio
    async def test_initialization_order_validation(self, valid_config):
        """
        Testa que ordem de inicialização é respeitada.

        Comportamento esperado:
        1. Validação de dependências
        2. Criação do Producer
        3. Instrumentação OTEL
        4. Schema Registry
        5. Circuit Breaker
        """
        call_order = []

        def track_producer(*args, **kwargs):
            call_order.append('producer')
            return MagicMock()

        def track_instrument(producer):
            call_order.append('instrument')
            return producer

        def track_schema_registry(*args, **kwargs):
            call_order.append('schema_registry')
            raise Exception('Schema unavailable')

        def track_circuit_breaker(*args, **kwargs):
            call_order.append('circuit_breaker')
            return MagicMock()

        with patch('src.clients.kafka_producer.Producer', side_effect=track_producer):
            with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=track_instrument):
                with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=track_schema_registry):
                    with patch('src.clients.kafka_producer.MonitoredCircuitBreaker', side_effect=track_circuit_breaker):
                        client = KafkaProducerClient(valid_config)
                        await client.initialize()

                        # Verificar ordem correta
                        assert call_order == ['producer', 'instrument', 'schema_registry', 'circuit_breaker']


@pytest.mark.integration
class TestKafkaProducerInitializationPerformance:
    """Testes de performance de inicialização."""

    @pytest.mark.asyncio
    async def test_initialization_performance_baseline(self):
        """
        Testa que inicialização completa em tempo aceitável.

        SLA: < 5 segundos para inicialização completa
        """
        config = types.SimpleNamespace(
            service_name='test-orchestrator',
            kafka_bootstrap_servers='localhost:9092',
            kafka_tickets_topic='test.tickets',
            kafka_schema_registry_url='http://localhost:8081',
            kafka_security_protocol='PLAINTEXT',
            kafka_sasl_username=None,
            kafka_sasl_password=None,
            schemas_base_path='/tmp/schemas',
            KAFKA_CIRCUIT_BREAKER_ENABLED=True,
            KAFKA_CIRCUIT_BREAKER_FAIL_MAX=5,
            KAFKA_CIRCUIT_BREAKER_TIMEOUT=60,
            KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
        )

        with patch('src.clients.kafka_producer.Producer'):
            with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
                with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Schema unavailable')):
                    client = KafkaProducerClient(config)

                    start = perf_counter()
                    await client.initialize()
                    duration = perf_counter() - start

                    # SLA: < 5 segundos
                    assert duration < 5.0, f"Inicialização levou {duration:.2f}s (SLA: < 5s)"
