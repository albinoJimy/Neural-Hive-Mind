"""
Testes unitarios para ApprovalRequestConsumer

Testa deserializacao e processamento de mensagens Kafka.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from src.models.approval import ApprovalRequest, RiskBand
from src.consumers.approval_request_consumer import ApprovalRequestConsumer


class TestApprovalRequestConsumerDeserialize:
    """Testes para deserializacao de mensagens"""

    @pytest.fixture
    def consumer(self, mock_settings):
        """Cria instancia de ApprovalRequestConsumer para testes"""
        consumer = ApprovalRequestConsumer(mock_settings)
        consumer.avro_deserializer = None  # JSON mode
        return consumer

    @pytest.fixture
    def valid_kafka_message(self, sample_cognitive_plan):
        """Mock de mensagem Kafka valida"""
        msg = MagicMock()
        msg.value.return_value = json.dumps(sample_cognitive_plan).encode('utf-8')
        msg.topic.return_value = 'cognitive-plans-approval-requests'
        msg.headers.return_value = [
            ('plan-id', b'plan-001'),
            ('intent-id', b'intent-001')
        ]
        msg.offset.return_value = 100
        return msg

    @pytest.mark.asyncio
    async def test_deserialize_json_success(
        self, consumer, valid_kafka_message, sample_cognitive_plan
    ):
        """Teste deserializacao JSON bem-sucedida"""
        result = await consumer._deserialize_message(valid_kafka_message)

        assert isinstance(result, ApprovalRequest)
        assert result.plan_id == sample_cognitive_plan['plan_id']
        assert result.intent_id == sample_cognitive_plan['intent_id']
        assert result.risk_score == sample_cognitive_plan['risk_score']
        assert result.is_destructive == sample_cognitive_plan['is_destructive']

    @pytest.mark.asyncio
    async def test_deserialize_with_risk_band_string(
        self, consumer
    ):
        """Teste deserializacao com risk_band como string"""
        plan_data = {
            'plan_id': 'plan-002',
            'intent_id': 'intent-002',
            'risk_score': 0.5,
            'risk_band': 'medium',
            'is_destructive': False
        }

        msg = MagicMock()
        msg.value.return_value = json.dumps(plan_data).encode('utf-8')
        msg.headers.return_value = []
        msg.offset.return_value = 101

        result = await consumer._deserialize_message(msg)

        assert result.risk_band == RiskBand.MEDIUM

    @pytest.mark.asyncio
    async def test_deserialize_defaults_risk_band_high(
        self, consumer
    ):
        """Teste que risk_band padrao e HIGH"""
        plan_data = {
            'plan_id': 'plan-003',
            'intent_id': 'intent-003',
            'risk_score': 0.8
        }

        msg = MagicMock()
        msg.value.return_value = json.dumps(plan_data).encode('utf-8')
        msg.headers.return_value = []
        msg.offset.return_value = 102

        result = await consumer._deserialize_message(msg)

        assert result.risk_band == RiskBand.HIGH

    @pytest.mark.asyncio
    async def test_deserialize_invalid_json(
        self, consumer
    ):
        """Teste deserializacao com JSON invalido"""
        msg = MagicMock()
        msg.value.return_value = b'invalid json {'
        msg.headers.return_value = []
        msg.offset.return_value = 103

        result = await consumer._deserialize_message(msg)

        assert result is None

    @pytest.mark.asyncio
    async def test_deserialize_missing_required_fields(
        self, consumer
    ):
        """Teste deserializacao sem campos obrigatorios"""
        plan_data = {
            'risk_score': 0.5
            # plan_id e intent_id ausentes
        }

        msg = MagicMock()
        msg.value.return_value = json.dumps(plan_data).encode('utf-8')
        msg.headers.return_value = []
        msg.offset.return_value = 104

        result = await consumer._deserialize_message(msg)

        # Deve falhar pois plan_id e intent_id sao obrigatorios
        assert result is None


class TestApprovalRequestConsumerHealth:
    """Testes para health check do consumer"""

    @pytest.fixture
    def consumer(self, mock_settings):
        """Cria instancia de ApprovalRequestConsumer para testes"""
        consumer = ApprovalRequestConsumer(mock_settings)
        consumer.consumer = MagicMock()
        consumer.running = True
        return consumer

    def test_is_healthy_when_running(self, consumer):
        """Teste health check quando consumer esta saudavel"""
        consumer._last_poll_time = datetime.utcnow()

        is_healthy, reason = consumer.is_healthy(max_poll_age_seconds=60.0)

        assert is_healthy == True
        assert 'saudavel' in reason

    def test_is_healthy_not_running(self, consumer):
        """Teste health check quando consumer parado"""
        consumer.running = False

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy == False
        assert 'nao esta rodando' in reason

    def test_is_healthy_not_initialized(self, mock_settings):
        """Teste health check quando consumer nao inicializado"""
        consumer = ApprovalRequestConsumer(mock_settings)

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy == False
        assert 'nao inicializado' in reason

    def test_is_healthy_stale_poll(self, consumer):
        """Teste health check quando ultimo poll muito antigo"""
        from datetime import timedelta

        consumer._last_poll_time = datetime.utcnow() - timedelta(seconds=120)

        is_healthy, reason = consumer.is_healthy(max_poll_age_seconds=60.0)

        assert is_healthy == False
        assert 'Ultimo poll' in reason


class TestApprovalRequestConsumerInit:
    """Testes para inicializacao do consumer"""

    @pytest.mark.asyncio
    @patch('src.consumers.approval_request_consumer.Consumer')
    async def test_initialize_creates_consumer(
        self, mock_consumer_class, mock_settings
    ):
        """Teste que initialize cria consumer Kafka"""
        consumer = ApprovalRequestConsumer(mock_settings)
        await consumer.initialize()

        mock_consumer_class.assert_called_once()
        # Verificar que subscribe foi chamado
        consumer.consumer.subscribe.assert_called_once_with(
            [mock_settings.kafka_approval_requests_topic]
        )

    @pytest.mark.asyncio
    @patch('src.consumers.approval_request_consumer.Consumer')
    async def test_initialize_with_security(
        self, mock_consumer_class, mock_settings
    ):
        """Teste inicializacao com seguranca Kafka"""
        mock_settings.kafka_security_protocol = 'SASL_SSL'
        mock_settings.kafka_sasl_mechanism = 'SCRAM-SHA-512'
        mock_settings.kafka_sasl_username = 'user'
        mock_settings.kafka_sasl_password = 'pass'

        consumer = ApprovalRequestConsumer(mock_settings)
        await consumer.initialize()

        call_config = mock_consumer_class.call_args[0][0]
        assert call_config['security.protocol'] == 'SASL_SSL'
        assert call_config['sasl.mechanism'] == 'SCRAM-SHA-512'


class TestApprovalRequestConsumerClose:
    """Testes para fechamento do consumer"""

    @pytest.mark.asyncio
    @patch('src.consumers.approval_request_consumer.Consumer')
    async def test_close_stops_running(
        self, mock_consumer_class, mock_settings
    ):
        """Teste que close para o consumer"""
        consumer = ApprovalRequestConsumer(mock_settings)
        await consumer.initialize()
        consumer.running = True

        await consumer.close()

        assert consumer.running == False
        consumer.consumer.close.assert_called_once()


class TestApprovalRequestConsumerDuplicateHandling:
    """Testes para tratamento de duplicatas no consumer"""

    @pytest.fixture
    def consumer(self, mock_settings):
        """Cria instancia de ApprovalRequestConsumer para testes"""
        consumer = ApprovalRequestConsumer(mock_settings)
        consumer.consumer = MagicMock()
        consumer.avro_deserializer = None  # JSON mode
        consumer.running = True
        return consumer

    @pytest.mark.asyncio
    async def test_duplicate_message_commits_and_skips(
        self, consumer, sample_cognitive_plan
    ):
        """Teste que mensagem duplicada e commitada e pulada"""
        from pymongo.errors import DuplicateKeyError

        # Setup mock message
        msg = MagicMock()
        msg.value.return_value = json.dumps(sample_cognitive_plan).encode('utf-8')
        msg.headers.return_value = []
        msg.offset.return_value = 100
        msg.error.return_value = None

        # Callback que simula DuplicateKeyError
        async def raise_duplicate(approval_request):
            raise DuplicateKeyError('Duplicate key error')

        # Poll retorna msg uma vez e depois None
        poll_count = [0]
        def mock_poll(timeout):
            poll_count[0] += 1
            if poll_count[0] == 1:
                return msg
            consumer.running = False
            return None

        consumer.consumer.poll = mock_poll

        # Executa consumo
        await consumer.start_consuming(raise_duplicate)

        # Verifica que commit foi chamado mesmo com erro de duplicata
        consumer.consumer.commit.assert_called_once_with(message=msg)


class TestApprovalRequestConsumerServiceHandoff:
    """Testes para handoff entre consumer e service"""

    @pytest.fixture
    def consumer(self, mock_settings):
        """Cria instancia de ApprovalRequestConsumer para testes"""
        consumer = ApprovalRequestConsumer(mock_settings)
        consumer.consumer = MagicMock()
        consumer.avro_deserializer = None  # JSON mode
        consumer.running = True
        return consumer

    @pytest.mark.asyncio
    async def test_callback_receives_approval_request_object(
        self, consumer, sample_cognitive_plan
    ):
        """Teste que callback recebe ApprovalRequest e nao dict"""
        # Setup mock message
        msg = MagicMock()
        msg.value.return_value = json.dumps(sample_cognitive_plan).encode('utf-8')
        msg.headers.return_value = []
        msg.offset.return_value = 100
        msg.error.return_value = None

        # Callback que verifica tipo do argumento
        received_args = []
        async def capture_callback(approval_request):
            received_args.append(approval_request)

        # Poll retorna msg uma vez e depois None
        poll_count = [0]
        def mock_poll(timeout):
            poll_count[0] += 1
            if poll_count[0] == 1:
                return msg
            consumer.running = False
            return None

        consumer.consumer.poll = mock_poll

        # Executa consumo
        await consumer.start_consuming(capture_callback)

        # Verifica que callback recebeu ApprovalRequest
        assert len(received_args) == 1
        assert isinstance(received_args[0], ApprovalRequest)
        assert received_args[0].plan_id == sample_cognitive_plan['plan_id']
        assert received_args[0].intent_id == sample_cognitive_plan['intent_id']
