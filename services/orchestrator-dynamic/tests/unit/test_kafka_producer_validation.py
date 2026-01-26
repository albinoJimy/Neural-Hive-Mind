"""
Testes unitários para validação de configuração do KafkaProducerClient.

Valida comportamento de fail-fast no construtor e fail-safe no circuit breaker.
"""
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ======================================================
# Testes de Validação de Configuração no Construtor
# ======================================================

def test_kafka_producer_init_with_none_config():
    """Valida que ValueError é lançado se config for None."""
    from src.clients.kafka_producer import KafkaProducerClient

    with pytest.raises(ValueError, match='config não pode ser None'):
        KafkaProducerClient(None)


def test_kafka_producer_init_with_none_config_and_overrides():
    """Valida que mesmo com overrides, config=None lança ValueError."""
    from src.clients.kafka_producer import KafkaProducerClient

    with pytest.raises(ValueError, match='config não pode ser None'):
        KafkaProducerClient(
            config=None,
            sasl_username_override='user',
            sasl_password_override='pass'
        )


def test_kafka_producer_init_with_missing_service_name():
    """Valida que ValueError é lançado se service_name estiver ausente."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name=None,  # Ausente
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with pytest.raises(ValueError, match='service_name'):
        KafkaProducerClient(config)


def test_kafka_producer_init_with_missing_bootstrap_servers():
    """Valida que ValueError é lançado se kafka_bootstrap_servers estiver ausente."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers=None,  # Ausente
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with pytest.raises(ValueError, match='kafka_bootstrap_servers'):
        KafkaProducerClient(config)


def test_kafka_producer_init_with_missing_tickets_topic():
    """Valida que ValueError é lançado se kafka_tickets_topic estiver ausente."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic=None,  # Ausente
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with pytest.raises(ValueError, match='kafka_tickets_topic'):
        KafkaProducerClient(config)


def test_kafka_producer_init_without_schema_registry_url_succeeds():
    """Valida que inicialização funciona sem kafka_schema_registry_url (modo JSON-only)."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url=None,  # Ausente - modo JSON fallback
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    assert client.config == config
    # Não deve lançar exceção - kafka_schema_registry_url é opcional


def test_kafka_producer_init_with_multiple_missing_attrs():
    """Valida que todos os atributos ausentes são listados na mensagem de erro."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name=None,
        kafka_bootstrap_servers=None,
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with pytest.raises(ValueError) as exc_info:
        KafkaProducerClient(config)

    error_msg = str(exc_info.value)
    assert 'service_name' in error_msg
    assert 'kafka_bootstrap_servers' in error_msg


def test_kafka_producer_init_with_valid_config():
    """Valida que inicialização funciona com config válida."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username='user',
        kafka_sasl_password='pass',
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    assert client.config == config
    assert client.sasl_username == 'user'
    assert client.sasl_password == 'pass'


def test_kafka_producer_init_with_sasl_overrides():
    """Valida que overrides de SASL sobrescrevem valores do config."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username='config-user',
        kafka_sasl_password='config-pass',
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(
            config,
            sasl_username_override='override-user',
            sasl_password_override='override-pass'
        )

    assert client.sasl_username == 'override-user'
    assert client.sasl_password == 'override-pass'


def test_kafka_producer_init_logs_configuration():
    """Valida que configuração é logada na inicialização."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        KAFKA_CIRCUIT_BREAKER_ENABLED=True
    )

    with patch('src.clients.kafka_producer.logger') as mock_logger:
        KafkaProducerClient(config)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == 'kafka_producer_config_validated'
        assert call_args[1]['service_name'] == 'test-service'


# ======================================================
# Testes de Modo JSON-Only (sem Schema Registry)
# ======================================================

@pytest.mark.asyncio
async def test_kafka_producer_initialize_json_only_mode():
    """Valida que initialize() funciona em modo JSON-only sem schema registry."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url=None,  # Sem schema registry
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    with patch('src.clients.kafka_producer.Producer'):
        with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
            with patch('src.clients.kafka_producer.logger') as mock_logger:
                await client.initialize()

                # Não deve lançar exceção
                assert client.producer is not None
                # Schema registry e Avro devem estar None
                assert client.schema_registry_client is None
                assert client.avro_serializer is None


@pytest.mark.asyncio
async def test_kafka_producer_json_only_logs_fallback():
    """Valida que modo JSON-only loga corretamente o fallback."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url=None,  # Sem schema registry
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with patch('src.clients.kafka_producer.logger') as mock_logger:
        client = KafkaProducerClient(config)

        # Deve logar que schema_registry_url não está configurado
        call_args = mock_logger.info.call_args
        assert 'NOT_CONFIGURED' in str(call_args) or 'JSON fallback' in str(call_args)


# ======================================================
# Testes de Validação no Método initialize()
# ======================================================

@pytest.mark.asyncio
async def test_kafka_producer_initialize_validates_config():
    """Valida que initialize() re-valida config."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=False
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    # Simular config corrompido após construção
    client.config = None

    with pytest.raises(RuntimeError, match='self.config é None'):
        await client.initialize()


# ======================================================
# Testes de Fallback do Circuit Breaker
# ======================================================

@pytest.mark.asyncio
async def test_kafka_producer_circuit_breaker_fallback_on_missing_service_name():
    """Valida que inicialização falha se service_name estiver ausente após construção."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=True,
        KAFKA_CIRCUIT_BREAKER_FAIL_MAX=5,
        KAFKA_CIRCUIT_BREAKER_TIMEOUT=60,
        KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    # Simular service_name None para forçar erro de validação
    client.config.service_name = None

    with patch('src.clients.kafka_producer.Producer'):
        with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
            with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Schema unavailable')):
                with patch('src.clients.kafka_producer.logger') as mock_logger:
                    # Deve lançar RuntimeError devido à validação antecipada
                    with pytest.raises(RuntimeError, match='service_name'):
                        await client.initialize()

                    # Deve ter logado erro com dependências ausentes
                    error_calls = [
                        call for call in mock_logger.error.call_args_list
                        if 'missing_dependencies' in str(call)
                    ]
                    assert len(error_calls) >= 1


@pytest.mark.asyncio
async def test_kafka_producer_circuit_breaker_enabled_with_valid_config():
    """Valida que circuit breaker é habilitado com config válida."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=True,
        KAFKA_CIRCUIT_BREAKER_FAIL_MAX=5,
        KAFKA_CIRCUIT_BREAKER_TIMEOUT=60,
        KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    with patch('src.clients.kafka_producer.Producer'):
        with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
            with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Schema unavailable')):
                with patch('src.clients.kafka_producer.MonitoredCircuitBreaker') as mock_cb:
                    mock_cb_instance = MagicMock()
                    mock_cb_instance.fail_max = 5
                    mock_cb_instance.recovery_timeout = 30
                    mock_cb.return_value = mock_cb_instance

                    with patch('src.clients.kafka_producer.logger'):
                        await client.initialize()

                    # Circuit breaker deve estar habilitado
                    assert client.circuit_breaker_enabled is True
                    assert client.producer_breaker is mock_cb_instance

                    # Deve ter sido criado com service_name correto
                    mock_cb.assert_called_once()
                    call_kwargs = mock_cb.call_args[1]
                    assert call_kwargs['service_name'] == 'test-service'


@pytest.mark.asyncio
async def test_kafka_producer_initialize_records_success_metrics():
    """Valida que métricas de sucesso são registradas na inicialização."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=True,
        KAFKA_CIRCUIT_BREAKER_FAIL_MAX=5,
        KAFKA_CIRCUIT_BREAKER_TIMEOUT=60,
        KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    with patch('src.clients.kafka_producer.Producer'):
        with patch('src.clients.kafka_producer.instrument_kafka_producer', side_effect=lambda x: x):
            with patch('src.clients.kafka_producer.SchemaRegistryClient', side_effect=Exception('Schema unavailable')):
                with patch('src.clients.kafka_producer.MonitoredCircuitBreaker'):
                    with patch.object(client, '_get_metrics') as mock_get_metrics:
                        mock_metrics = MagicMock()
                        mock_get_metrics.return_value = mock_metrics

                        await client.initialize()

                        # Verificar que métrica foi registrada
                        mock_metrics.record_component_initialization.assert_called_once()
                        call_kwargs = mock_metrics.record_component_initialization.call_args[1]
                        assert call_kwargs['component_name'] == 'kafka_producer'
                        assert call_kwargs['status'] == 'success'
                        assert call_kwargs['duration_seconds'] > 0


@pytest.mark.asyncio
async def test_kafka_producer_initialize_records_failure_metrics():
    """Valida que métricas de falha são registradas quando inicialização falha."""
    from src.clients.kafka_producer import KafkaProducerClient

    config = types.SimpleNamespace(
        service_name='test-service',
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path='/schemas',
        KAFKA_CIRCUIT_BREAKER_ENABLED=True
    )

    with patch('src.clients.kafka_producer.logger'):
        client = KafkaProducerClient(config)

    # Corromper config para forçar falha
    client.config = None

    with patch.object(client, '_get_metrics') as mock_get_metrics:
        mock_metrics = MagicMock()
        mock_get_metrics.return_value = mock_metrics

        with pytest.raises(RuntimeError):
            await client.initialize()

        # Verificar que métrica de falha foi registrada
        mock_metrics.record_component_initialization.assert_called_once()
        call_kwargs = mock_metrics.record_component_initialization.call_args[1]
        assert call_kwargs['component_name'] == 'kafka_producer'
        assert call_kwargs['status'] == 'failed'
