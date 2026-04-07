"""
Testes unitários abrangentes para KafkaSignalProducer.

Cobertura: publicação de sinais, oportunidades, batch, tratamento de erros.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.kafka_signal_producer import KafkaSignalProducer
from src.models.scout_signal import ScoutSignal, SignalType, SignalSource, ChannelType, Geolocation
from neural_hive_domain import UnifiedDomain


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_signal():
    """Sinal de exemplo para testes."""
    return ScoutSignal(
        scout_agent_id="test-scout",
        correlation_id="corr-001",
        trace_id="trace-001",
        span_id="span-001",
        signal_type=SignalType.ANOMALY_POSITIVE,
        exploration_domain=UnifiedDomain.BUSINESS,
        source=SignalSource(channel=ChannelType.CORE),
        curiosity_score=0.8,
        confidence=0.75,
        relevance_score=0.7,
        risk_score=0.3,
        description="Test signal",
        raw_data={"key": "value"},
        features=[0.1, 0.2, 0.3],
    )


@pytest.fixture
def opportunity_signal():
    """Sinal de oportunidade para testes."""
    return ScoutSignal(
        scout_agent_id="test-scout",
        correlation_id="corr-002",
        trace_id="trace-002",
        span_id="span-002",
        signal_type=SignalType.OPPORTUNITY,
        exploration_domain=UnifiedDomain.BUSINESS,
        source=SignalSource(channel=ChannelType.WEB),
        curiosity_score=0.9,
        confidence=0.85,
        relevance_score=0.8,
        risk_score=0.2,
        description="Opportunity signal",
        raw_data={},
        features=[0.5, 0.6],
    )


@pytest.fixture
def signal_with_geolocation():
    """Sinal com geolocalização."""
    return ScoutSignal(
        scout_agent_id="test-scout",
        correlation_id="corr-003",
        trace_id="trace-003",
        span_id="span-003",
        signal_type=SignalType.THREAT,
        exploration_domain=UnifiedDomain.SECURITY,
        source=SignalSource(
            channel=ChannelType.MOBILE,
            geolocation=Geolocation(latitude=37.7749, longitude=-122.4194),
        ),
        curiosity_score=0.95,
        confidence=0.9,
        relevance_score=0.85,
        risk_score=0.95,
        description="Threat with location",
        raw_data={},
        features=[0.8, 0.9],
    )


# ============================================================================
# Testes de Inicialização
# ============================================================================


class TestKafkaSignalProducerInitialization:
    """Testes de inicialização do KafkaSignalProducer."""

    def test_initialization(self):
        """Testa inicialização básica."""
        producer = KafkaSignalProducer()
        assert producer.settings is not None
        assert producer.producer is None
        assert producer._is_running is False


# ============================================================================
# Testes de Start/Stop
# ============================================================================


class TestKafkaProducerLifecycle:
    """Testes de ciclo de vida do produtor."""

    @pytest.mark.asyncio
    async def test_start_initializes_producer(self):
        """Testa que start inicializa o produtor Kafka."""
        producer = KafkaSignalProducer()

        with patch("src.clients.kafka_signal_producer.AIOKafkaProducer") as MockProducer:
            mock_instance = AsyncMock()
            MockProducer.return_value = mock_instance
            mock_instance.start = AsyncMock()

            await producer.start()

            MockProducer.assert_called_once()
            mock_instance.start.assert_called_once()
            assert producer._is_running is True

    @pytest.mark.asyncio
    async def test_start_error_handling(self):
        """Testa tratamento de erro no start."""
        producer = KafkaSignalProducer()

        with patch("src.clients.kafka_signal_producer.AIOKafkaProducer") as MockProducer:
            MockProducer.side_effect = Exception("Connection error")

            with pytest.raises(Exception):
                await producer.start()

    @pytest.mark.asyncio
    async def test_stop_gracefully(self):
        """Testa parada graceful do produtor."""
        producer = KafkaSignalProducer()
        producer._is_running = True
        producer.producer = AsyncMock()
        producer.producer.stop = AsyncMock()

        await producer.stop()

        producer.producer.stop.assert_called_once()
        assert producer._is_running is False

    @pytest.mark.asyncio
    async def test_stop_handles_none_producer(self):
        """Testa stop quando producer é None."""
        producer = KafkaSignalProducer()
        producer.producer = None

        # Não deve levantar exceção
        await producer.stop()

        assert producer._is_running is False

    @pytest.mark.asyncio
    async def test_stop_error_handling(self):
        """Testa tratamento de erro no stop."""
        producer = KafkaSignalProducer()
        producer._is_running = True
        producer.producer = AsyncMock()
        producer.producer.stop.side_effect = Exception("Stop error")

        # Não deve levantar exceção
        await producer.stop()

        assert producer._is_running is False


# ============================================================================
# Testes de Publicação de Sinais
# ============================================================================


class TestSignalPublishing:
    """Testes de publicação de sinais."""

    @pytest.mark.asyncio
    async def test_publish_signal_success(self, sample_signal):
        """Testa publicação bem-sucedida de sinal."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        # Mock producer e futuro
        mock_producer = AsyncMock()
        producer.producer = mock_producer

        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="signals", partition=0, offset=123)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        result = await producer.publish_signal(sample_signal)

        assert result is True
        mock_producer.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_signal_not_running(self, sample_signal):
        """Testa que publicação falha quando producer não está rodando."""
        producer = KafkaSignalProducer()
        producer._is_running = False
        producer.producer = None

        result = await producer.publish_signal(sample_signal)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_signal_to_avro_format(self, sample_signal):
        """Testa que sinal é convertido para formato Avro."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="signals", partition=0, offset=123)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        await producer.publish_signal(sample_signal)

        # Verificar que send foi chamado
        call_args = mock_producer.send.call_args
        assert call_args is not None

        # Verificar partition key
        sent_data = call_args[1]["value"]
        assert sent_data["exploration_domain"] == "BUSINESS"
        assert sent_data["signal_type"] == "ANOMALY_POSITIVE"

    @pytest.mark.asyncio
    async def test_publish_signal_with_geolocation(self, signal_with_geolocation):
        """Testa publicação de sinal com geolocalização."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="signals", partition=1, offset=456)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        result = await producer.publish_signal(signal_with_geolocation)

        assert result is True

    @pytest.mark.asyncio
    async def test_publish_signal_partition_key(self, sample_signal):
        """Testa que partition key baseia-se no domínio."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="signals", partition=0, offset=789)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        await producer.publish_signal(sample_signal)

        call_args = mock_producer.send.call_args
        partition_key = call_args[1]["key"]
        assert partition_key == b"BUSINESS"


# ============================================================================
# Testes de Tratamento de Erros na Publicação
# ============================================================================


class TestPublishErrorHandling:
    """Testes de tratamento de erros na publicação."""

    @pytest.mark.asyncio
    async def test_publish_signal_kafka_error(self, sample_signal):
        """Testa tratamento de erro do Kafka."""
        from aiokafka.errors import KafkaError

        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_producer.send_and_wait.side_effect = KafkaError("Kafka error")

        result = await producer.publish_signal(sample_signal)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_signal_generic_error(self, sample_signal):
        """Testa tratamento de erro genérico."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_producer.send_and_wait.side_effect = Exception("Generic error")

        result = await producer.publish_signal(sample_signal)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_signal_timeout(self, sample_signal):
        """Testa tratamento de timeout."""
        import asyncio

        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_producer.send_and_wait.side_effect = asyncio.TimeoutError("Timeout")

        result = await producer.publish_signal(sample_signal)

        assert result is False


# ============================================================================
# Testes de Publicação de Oportunidades
# ============================================================================


class TestOpportunityPublishing:
    """Testes de publicação de oportunidades."""

    @pytest.mark.asyncio
    async def test_publish_opportunity_success(self, opportunity_signal):
        """Testa publicação bem-sucedida de oportunidade."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="opportunities", partition=0, offset=100)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        result = await producer.publish_opportunity(opportunity_signal)

        assert result is True

    @pytest.mark.asyncio
    async def test_publish_opportunity_not_running(self, opportunity_signal):
        """Testa que oportunidade falha quando producer não rodando."""
        producer = KafkaSignalProducer()
        producer._is_running = False

        result = await producer.publish_opportunity(opportunity_signal)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_opportunity_uses_correct_topic(self, opportunity_signal):
        """Testa que oportunidade usa topic correto."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="opportunities", partition=0, offset=200)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        await producer.publish_opportunity(opportunity_signal)

        # Verificar que o tópico correto foi usado
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        # Deve usar tópico de oportunidades (config)
        assert topic is not None


# ============================================================================
# Testes de Publicação em Batch
# ============================================================================


class TestBatchPublishing:
    """Testes de publicação em lote."""

    @pytest.mark.asyncio
    async def test_publish_batch_empty(self):
        """Testa publicação de batch vazio."""
        producer = KafkaSignalProducer()

        result = await producer.publish_batch([])

        assert result == 0

    @pytest.mark.asyncio
    async def test_publish_batch_all_success(self, sample_signal):
        """Testa batch onde todos os sinais são publicados."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="signals", partition=0, offset=1)
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        # Criar batch de sinais
        signals = [
            ScoutSignal(
                scout_agent_id="test",
                correlation_id=f"corr-{i}",
                trace_id=f"trace-{i}",
                span_id=f"span-{i}",
                signal_type=SignalType.ANOMALY_POSITIVE,
                exploration_domain=UnifiedDomain.BUSINESS,
                source=SignalSource(channel=ChannelType.CORE),
                curiosity_score=0.8,
                confidence=0.7,
                relevance_score=0.6,
                risk_score=0.3,
                description=f"Signal {i}",
                raw_data={},
                features=[0.1],
            )
            for i in range(5)
        ]

        result = await producer.publish_batch(signals)

        assert result == 5

    @pytest.mark.asyncio
    async def test_publish_batch_partial_failure(self, sample_signal):
        """Testa batch com falhas parciais."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer

        # Simular 3 sucessos e 2 falhas
        call_count = [0]

        async def side_effect(signal):
            call_count[0] += 1
            if call_count[0] <= 3:
                return True
            return False

        with patch.object(producer, "publish_signal", side_effect=side_effect):
            signals = [sample_signal] * 5
            result = await producer.publish_batch(signals)

            assert result == 3

    @pytest.mark.asyncio
    async def test_publish_batch_with_exceptions(self, sample_signal):
        """Testa batch com exceções."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        call_count = [0]

        async def side_effect(signal):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Test error")
            return call_count[0] <= 3

        with patch.object(producer, "publish_signal", side_effect=side_effect):
            signals = [sample_signal] * 5
            result = await producer.publish_batch(signals)

            # 1 sucesso + 1 erro + 2 sucessos = 3
            assert result == 3


# ============================================================================
# Testes de Configuração
# ============================================================================


class TestKafkaConfiguration:
    """Testes de configuração do Kafka."""

    @pytest.mark.asyncio
    async def test_uses_correct_bootstrap_servers(self):
        """Testa que bootstrap servers corretos são usados."""
        producer = KafkaSignalProducer()

        with patch("src.clients.kafka_signal_producer.AIOKafkaProducer") as MockProducer:
            mock_instance = AsyncMock()
            MockProducer.return_value = mock_instance

            await producer.start()

            call_args = MockProducer.call_args
            config = call_args[1] if call_args else {}
            assert "bootstrap_servers" in config

    @pytest.mark.asyncio
    async def test_uses_compression_type(self):
        """Testa que compressão gzip é configurada."""
        producer = KafkaSignalProducer()

        with patch("src.clients.kafka_signal_producer.AIOKafkaProducer") as MockProducer:
            mock_instance = AsyncMock()
            MockProducer.return_value = mock_instance

            await producer.start()

            call_args = MockProducer.call_args
            config = call_args[1] if call_args else {}
            assert config.get("compression_type") == "gzip"

    @pytest.mark.asyncio
    async def test_enables_idempotence(self):
        """Testa que idempotência está habilitada."""
        producer = KafkaSignalProducer()

        with patch("src.clients.kafka_signal_producer.AIOKafkaProducer") as MockProducer:
            mock_instance = AsyncMock()
            MockProducer.return_value = mock_instance

            await producer.start()

            call_args = MockProducer.call_args
            config = call_args[1] if call_args else {}
            assert config.get("enable_idempotence") is True

    @pytest.mark.asyncio
    async def test_acks_all(self):
        """Testa que acks='all' é configurado."""
        producer = KafkaSignalProducer()

        with patch("src.clients.kafka_signal_producer.AIOKafkaProducer") as MockProducer:
            mock_instance = AsyncMock()
            MockProducer.return_value = mock_instance

            await producer.start()

            call_args = MockProducer.call_args
            config = call_args[1] if call_args else {}
            assert config.get("acks") == "all"


# ============================================================================
# Testes de Conversão Avro
# ============================================================================


class TestAvroConversion:
    """Testes de conversão para formato Avro."""

    def test_signal_to_avro_dict(self, sample_signal):
        """Testa conversão de sinal para dict Avro."""
        avro_dict = sample_signal.to_avro_dict()

        assert isinstance(avro_dict, dict)
        assert avro_dict["signal_type"] == "ANOMALY_POSITIVE"
        assert avro_dict["exploration_domain"] == "BUSINESS"
        assert avro_dict["source"]["channel"] == "CORE"

    def test_signal_with_geolocation_to_avro(self, signal_with_geolocation):
        """Testa conversão de sinal com geolocalização."""
        avro_dict = signal_with_geolocation.to_avro_dict()

        assert "geolocation" in avro_dict["source"]
        assert avro_dict["source"]["geolocation"]["latitude"] == 37.7749
        assert avro_dict["source"]["geolocation"]["longitude"] == -122.4194

    def test_all_signal_types_to_avro(self):
        """Testa conversão de todos os tipos de sinal."""
        for signal_type in SignalType:
            signal = ScoutSignal(
                scout_agent_id="test",
                correlation_id="corr",
                trace_id="trace",
                span_id="span",
                signal_type=signal_type,
                exploration_domain=UnifiedDomain.BUSINESS,
                source=SignalSource(channel=ChannelType.CORE),
                curiosity_score=0.5,
                confidence=0.5,
                relevance_score=0.5,
                risk_score=0.5,
                description="Test",
                raw_data={},
                features=[],
            )
            avro_dict = signal.to_avro_dict()
            assert avro_dict["signal_type"] == signal_type.value

    def test_all_channel_types_to_avro(self):
        """Testa conversão de todos os tipos de canal."""
        for channel_type in ChannelType:
            signal = ScoutSignal(
                scout_agent_id="test",
                correlation_id="corr",
                trace_id="trace",
                span_id="span",
                signal_type=SignalType.TREND,
                exploration_domain=UnifiedDomain.BUSINESS,
                source=SignalSource(channel=channel_type),
                curiosity_score=0.5,
                confidence=0.5,
                relevance_score=0.5,
                risk_score=0.5,
                description="Test",
                raw_data={},
                features=[],
            )
            avro_dict = signal.to_avro_dict()
            assert avro_dict["source"]["channel"] == channel_type.value


# ============================================================================
# Testes de Integração
# ============================================================================


class TestKafkaProducerIntegration:
    """Testes de integração."""

    @pytest.mark.asyncio
    async def test_full_publishing_workflow(self, sample_signal):
        """Testa workflow completo de publicação."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_future.metadata = MagicMock(topic="signals", partition=0, offset=999)
        mock_producer.send.return_value = mock_future
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        # Publicar
        result = await producer.publish_signal(sample_signal)

        assert result is True

    @pytest.mark.asyncio
    async def test_publish_different_domains(self, sample_signal):
        """Testa publicação de diferentes domínios."""
        producer = KafkaSignalProducer()
        producer._is_running = True

        mock_producer = AsyncMock()
        producer.producer = mock_producer
        mock_future = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=mock_future)

        for domain in [UnifiedDomain.BUSINESS, UnifiedDomain.SECURITY, UnifiedDomain.TECHNICAL]:
            sample_signal.exploration_domain = domain
            result = await producer.publish_signal(sample_signal)
            assert result is True
