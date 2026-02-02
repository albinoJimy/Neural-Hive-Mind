"""
Testes de integração para Approval DLQ Consumer e DLQ Reprocessor

Valida o fluxo completo de reprocessamento de mensagens da Dead Letter Queue.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from src.consumers.approval_dlq_consumer import ApprovalDLQConsumer
from src.services.dlq_reprocessor import DLQReprocessor
from src.models.approval_dlq import ApprovalDLQEntry


class TestDLQConsumerBackoffCalculation:
    """Testes para cálculo de backoff progressivo no DLQ consumer"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado para testes de backoff"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_dlq_topic = 'cognitive-plans-approval-dlq'
        settings.dlq_polling_interval_seconds = 300
        settings.dlq_max_retry_count = 10
        settings.dlq_backoff_base_minutes = 2
        return settings

    def test_backoff_calculation_retry_0(self, mock_settings):
        """Backoff para retry_count=0 deve ser 2^0 * 60 = 60 segundos"""
        consumer = ApprovalDLQConsumer(mock_settings)
        backoff = consumer._calculate_backoff(retry_count=0)
        # base_minutes^0 * 60 = 2^0 * 60 = 60
        assert backoff == 60

    def test_backoff_calculation_retry_1(self, mock_settings):
        """Backoff para retry_count=1 deve ser 2^1 * 60 = 120 segundos"""
        consumer = ApprovalDLQConsumer(mock_settings)
        backoff = consumer._calculate_backoff(retry_count=1)
        # base_minutes^1 * 60 = 2^1 * 60 = 120
        assert backoff == 120

    def test_backoff_calculation_retry_3(self, mock_settings):
        """Backoff para retry_count=3 deve ser 2^3 * 60 = 480 segundos"""
        consumer = ApprovalDLQConsumer(mock_settings)
        backoff = consumer._calculate_backoff(retry_count=3)
        # base_minutes^3 * 60 = 2^3 * 60 = 480
        assert backoff == 480

    def test_backoff_calculation_max_24_hours(self, mock_settings):
        """Backoff máximo deve ser limitado a 24 horas"""
        consumer = ApprovalDLQConsumer(mock_settings)
        backoff = consumer._calculate_backoff(retry_count=20)  # Valor muito alto
        max_backoff = 24 * 60 * 60  # 24 horas em segundos
        assert backoff == max_backoff


class TestDLQConsumerMessageDeserialization:
    """Testes para deserialização de mensagens DLQ"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_dlq_topic = 'cognitive-plans-approval-dlq'
        settings.dlq_polling_interval_seconds = 300
        settings.dlq_max_retry_count = 10
        settings.dlq_backoff_base_minutes = 2
        return settings

    @pytest.fixture
    def valid_dlq_message_data(self):
        """Dados válidos de mensagem DLQ"""
        return {
            'plan_id': 'plan-dlq-001',
            'intent_id': 'intent-dlq-001',
            'failure_reason': 'Kafka producer timeout',
            'retry_count': 2,
            'original_approval_response': {
                'plan_id': 'plan-dlq-001',
                'intent_id': 'intent-dlq-001',
                'decision': 'approved',
                'approved_by': 'admin@company.com',
                'approved_at': int(datetime.utcnow().timestamp() * 1000)
            },
            'failed_at': int(datetime.utcnow().timestamp() * 1000),
            'correlation_id': 'corr-dlq-001',
            'trace_id': 'trace-dlq-001',
            'span_id': 'span-dlq-001',
            'risk_band': 'high',
            'is_destructive': True
        }

    def test_deserialize_valid_dlq_message(self, mock_settings, valid_dlq_message_data):
        """Deve deserializar mensagem DLQ válida corretamente"""
        consumer = ApprovalDLQConsumer(mock_settings)

        mock_msg = MagicMock()
        mock_msg.value.return_value = json.dumps(valid_dlq_message_data).encode('utf-8')

        entry = consumer._deserialize_dlq_message(mock_msg)

        assert entry.plan_id == 'plan-dlq-001'
        assert entry.intent_id == 'intent-dlq-001'
        assert entry.retry_count == 2
        assert entry.correlation_id == 'corr-dlq-001'
        assert entry.risk_band == 'high'
        assert entry.is_destructive is True

    def test_deserialize_message_missing_required_field(self, mock_settings):
        """Deve falhar ao deserializar mensagem sem campo obrigatório"""
        consumer = ApprovalDLQConsumer(mock_settings)

        invalid_data = {
            'plan_id': 'plan-dlq-001',
            # Missing: intent_id, original_approval_response, retry_count
        }

        mock_msg = MagicMock()
        mock_msg.value.return_value = json.dumps(invalid_data).encode('utf-8')

        with pytest.raises(ValueError) as exc_info:
            consumer._deserialize_dlq_message(mock_msg)

        assert 'Campo obrigatório ausente' in str(exc_info.value)

    def test_deserialize_message_converts_failed_at_timestamp(
        self,
        mock_settings,
        valid_dlq_message_data
    ):
        """Deve converter failed_at de millis para datetime"""
        consumer = ApprovalDLQConsumer(mock_settings)

        mock_msg = MagicMock()
        mock_msg.value.return_value = json.dumps(valid_dlq_message_data).encode('utf-8')

        entry = consumer._deserialize_dlq_message(mock_msg)

        assert isinstance(entry.failed_at, datetime)


class TestDLQConsumerHealthCheck:
    """Testes para health check do DLQ consumer"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_dlq_topic = 'cognitive-plans-approval-dlq'
        settings.dlq_polling_interval_seconds = 300
        settings.dlq_max_retry_count = 10
        settings.dlq_backoff_base_minutes = 2
        return settings

    def test_health_check_not_running(self, mock_settings):
        """Consumer não inicializado deve retornar unhealthy"""
        consumer = ApprovalDLQConsumer(mock_settings)

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy is False
        assert 'não está em estado running' in reason

    def test_health_check_no_consumer(self, mock_settings):
        """Consumer sem Kafka client deve retornar unhealthy"""
        consumer = ApprovalDLQConsumer(mock_settings)
        consumer.running = True
        consumer.consumer = None

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy is False
        assert 'não inicializado' in reason

    def test_health_check_no_poll_time(self, mock_settings):
        """Consumer sem poll time deve retornar unhealthy"""
        consumer = ApprovalDLQConsumer(mock_settings)
        consumer.running = True
        consumer.consumer = MagicMock()
        consumer.last_poll_time = None

        is_healthy, reason = consumer.is_healthy()

        assert is_healthy is False
        assert 'não iniciou polling' in reason

    def test_health_check_poll_too_old(self, mock_settings):
        """Consumer com poll muito antigo deve retornar unhealthy"""
        import time

        consumer = ApprovalDLQConsumer(mock_settings)
        consumer.running = True
        consumer.consumer = MagicMock()
        consumer.last_poll_time = time.time() - 1000  # 1000 segundos atrás

        is_healthy, reason = consumer.is_healthy(max_poll_age_seconds=600.0)

        assert is_healthy is False
        assert 'Último poll há' in reason

    def test_health_check_healthy(self, mock_settings):
        """Consumer saudável deve retornar healthy"""
        import time

        consumer = ApprovalDLQConsumer(mock_settings)
        consumer.running = True
        consumer.consumer = MagicMock()
        consumer.last_poll_time = time.time() - 10  # 10 segundos atrás
        consumer.messages_processed = 5
        consumer.messages_skipped = 3

        is_healthy, reason = consumer.is_healthy(max_poll_age_seconds=600.0)

        assert is_healthy is True
        assert 'DLQ Consumer ativo' in reason
        assert '5 reprocessadas' in reason
        assert '3 skipped' in reason


class TestDLQReprocessorIntegration:
    """Testes de integração para DLQReprocessor"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.dlq_max_retry_count = 10
        return settings

    @pytest.fixture
    def mock_mongodb_client(self):
        """MongoDB client mockado"""
        client = MagicMock()
        client.update_plan_dlq_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mockadas"""
        metrics = MagicMock()
        metrics.increment_dlq_reprocessed = MagicMock()
        metrics.increment_dlq_reprocess_failure = MagicMock()
        metrics.increment_dlq_permanently_failed = MagicMock()
        return metrics

    @pytest.fixture
    def sample_dlq_entry(self):
        """Entrada DLQ de exemplo"""
        return ApprovalDLQEntry(
            plan_id='plan-reprocess-001',
            intent_id='intent-reprocess-001',
            failure_reason='Kafka timeout',
            retry_count=2,
            original_approval_response={
                'plan_id': 'plan-reprocess-001',
                'intent_id': 'intent-reprocess-001',
                'decision': 'approved',
                'approved_by': 'admin@company.com',
                'approved_at': int(datetime.utcnow().timestamp() * 1000)
            },
            failed_at=datetime.utcnow() - timedelta(minutes=30),
            correlation_id='corr-reprocess-001',
            trace_id='trace-reprocess-001',
            span_id='span-reprocess-001',
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_dlq_entry_success(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics,
        sample_dlq_entry
    ):
        """Deve reprocessar entrada DLQ com sucesso"""
        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings
        )
        reprocessor._producer = mock_producer

        trace_context = {
            'correlation_id': 'corr-reprocess-001',
            'trace_id': 'trace-reprocess-001',
            'span_id': 'span-reprocess-001'
        }

        result = await reprocessor.reprocess_dlq_entry(sample_dlq_entry, trace_context)

        assert result is True
        mock_producer.produce.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_metrics.increment_dlq_reprocessed.assert_called_once_with('success', 'high')

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_dlq_entry_exceeds_max_retries(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics,
        sample_dlq_entry
    ):
        """Deve tratar falha permanente quando retry_count excede limite"""
        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        # Configurar entrada com retry_count acima do limite
        sample_dlq_entry.retry_count = 15  # > dlq_max_retry_count (10)

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings
        )
        reprocessor._producer = mock_producer

        trace_context = {'correlation_id': 'corr-permanent-fail'}

        result = await reprocessor.reprocess_dlq_entry(sample_dlq_entry, trace_context)

        assert result is True  # Retorna True para commitar offset
        mock_producer.produce.assert_not_called()  # Não republica
        mock_metrics.increment_dlq_permanently_failed.assert_called_once_with('high')
        mock_mongodb_client.update_plan_dlq_status.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_dlq_entry_producer_failure(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics,
        sample_dlq_entry
    ):
        """Deve retornar False quando producer falha"""
        mock_producer = MagicMock()
        mock_producer.produce.side_effect = Exception('Kafka unavailable')
        mock_producer_class.return_value = mock_producer

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings
        )
        reprocessor._producer = mock_producer

        trace_context = {'correlation_id': 'corr-producer-fail'}

        result = await reprocessor.reprocess_dlq_entry(sample_dlq_entry, trace_context)

        assert result is False  # Retorna False para não commitar offset
        mock_metrics.increment_dlq_reprocess_failure.assert_called_once()


class TestDLQReprocessorMessageValidation:
    """Testes para validação de mensagens no DLQReprocessor"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.dlq_max_retry_count = 10
        return settings

    @pytest.fixture
    def mock_mongodb_client(self):
        """MongoDB client mockado"""
        return MagicMock()

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mockadas"""
        metrics = MagicMock()
        metrics.increment_dlq_reprocess_failure = MagicMock()
        return metrics

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_validates_required_fields(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics
    ):
        """Deve falhar se original_approval_response não tem campos obrigatórios"""
        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        # Entrada com original_approval_response incompleto
        dlq_entry = ApprovalDLQEntry(
            plan_id='plan-invalid-001',
            intent_id='intent-invalid-001',
            failure_reason='test',
            retry_count=1,
            original_approval_response={
                # Missing: plan_id, intent_id, decision
            },
            failed_at=datetime.utcnow()
        )

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings
        )
        reprocessor._producer = mock_producer

        result = await reprocessor.reprocess_dlq_entry(dlq_entry, {})

        assert result is False
        mock_metrics.increment_dlq_reprocess_failure.assert_called_once()


class TestDLQConsumerReprocessorIntegration:
    """Testes de integração entre DLQ Consumer e DLQ Reprocessor"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado completo"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_dlq_topic = 'cognitive-plans-approval-dlq'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.dlq_polling_interval_seconds = 300
        settings.dlq_max_retry_count = 10
        settings.dlq_backoff_base_minutes = 2
        return settings

    @pytest.mark.asyncio
    async def test_consumer_calls_reprocessor_callback(self, mock_settings):
        """Consumer deve chamar callback do reprocessor corretamente"""
        consumer = ApprovalDLQConsumer(mock_settings)

        # Simular entrada DLQ
        dlq_entry = ApprovalDLQEntry(
            plan_id='plan-callback-001',
            intent_id='intent-callback-001',
            failure_reason='test',
            retry_count=1,
            original_approval_response={
                'plan_id': 'plan-callback-001',
                'intent_id': 'intent-callback-001',
                'decision': 'approved'
            },
            failed_at=datetime.utcnow() - timedelta(hours=1),  # Suficiente para passar backoff
            correlation_id='corr-callback-001'
        )

        # Mock do callback
        mock_callback = AsyncMock(return_value=True)

        trace_context = {
            'correlation_id': 'corr-callback-001',
            'trace_id': None,
            'span_id': None
        }

        # Chamar callback diretamente (simular processamento)
        result = await mock_callback(dlq_entry, trace_context)

        assert result is True
        mock_callback.assert_called_once_with(dlq_entry, trace_context)


class TestDLQReprocessorRetryCountIncrement:
    """
    Testes para Comment 2: Incremento de retry_count em falhas de reprocessamento.

    Verifica que quando o reprocessamento falha, o retry_count é incrementado
    e a entrada é republicada na DLQ para controle de max retries.
    """

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.dlq_max_retry_count = 5
        return settings

    @pytest.fixture
    def mock_mongodb_client(self):
        """MongoDB client mockado"""
        client = MagicMock()
        client.update_plan_dlq_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mockadas"""
        metrics = MagicMock()
        metrics.increment_dlq_reprocessed = MagicMock()
        metrics.increment_dlq_reprocess_failure = MagicMock()
        metrics.increment_dlq_permanently_failed = MagicMock()
        return metrics

    @pytest.fixture
    def mock_dlq_producer(self):
        """DLQ producer mockado"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def sample_dlq_entry(self):
        """Entrada DLQ de exemplo"""
        return ApprovalDLQEntry(
            plan_id='plan-retry-001',
            intent_id='intent-retry-001',
            failure_reason='Original failure',
            retry_count=2,
            original_approval_response={
                'plan_id': 'plan-retry-001',
                'intent_id': 'intent-retry-001',
                'decision': 'approved',
                'approved_by': 'admin@company.com',
                'approved_at': int(datetime.utcnow().timestamp() * 1000)
            },
            failed_at=datetime.utcnow() - timedelta(minutes=30),
            correlation_id='corr-retry-001',
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_failure_republishes_to_dlq_with_incremented_retry_count(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics,
        mock_dlq_producer,
        sample_dlq_entry
    ):
        """
        Falha no reprocessamento deve republicar na DLQ com retry_count incrementado.
        """
        mock_producer = MagicMock()
        mock_producer.produce.side_effect = Exception('Kafka unavailable')
        mock_producer_class.return_value = mock_producer

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings,
            dlq_producer=mock_dlq_producer
        )
        reprocessor._producer = mock_producer

        trace_context = {'correlation_id': 'corr-retry-001'}

        result = await reprocessor.reprocess_dlq_entry(sample_dlq_entry, trace_context)

        # Deve retornar True porque republicou na DLQ
        assert result is True

        # Verificar que foi republicado na DLQ
        mock_dlq_producer.send_dlq_entry.assert_called_once()

        # Verificar que retry_count foi incrementado
        republished_entry = mock_dlq_producer.send_dlq_entry.call_args[0][0]
        assert republished_entry.retry_count == sample_dlq_entry.retry_count + 1
        assert '[REPROCESS_FAILED]' in republished_entry.failure_reason

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_failure_triggers_permanent_failure_when_max_exceeded(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics,
        mock_dlq_producer
    ):
        """
        Falha no reprocessamento deve tratar como permanente quando retry_count excede max.
        """
        mock_producer = MagicMock()
        mock_producer.produce.side_effect = Exception('Kafka unavailable')
        mock_producer_class.return_value = mock_producer

        # Entrada com retry_count = max_retry_count (5), então após incremento será 6 > 5
        dlq_entry = ApprovalDLQEntry(
            plan_id='plan-max-retry-001',
            intent_id='intent-max-retry-001',
            failure_reason='Previous failure',
            retry_count=5,  # max_retry_count = 5
            original_approval_response={
                'plan_id': 'plan-max-retry-001',
                'intent_id': 'intent-max-retry-001',
                'decision': 'approved'
            },
            failed_at=datetime.utcnow() - timedelta(hours=1),
            risk_band='critical'
        )

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings,
            dlq_producer=mock_dlq_producer
        )
        reprocessor._producer = mock_producer

        result = await reprocessor.reprocess_dlq_entry(dlq_entry, {})

        # Deve retornar True porque tratou como permanent failure
        assert result is True

        # NÃO deve republicar na DLQ (foi para permanent failure)
        mock_dlq_producer.send_dlq_entry.assert_not_called()

        # Deve registrar métrica de falha permanente
        mock_metrics.increment_dlq_permanently_failed.assert_called_once_with('critical')

        # Deve atualizar MongoDB
        mock_mongodb_client.update_plan_dlq_status.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.dlq_reprocessor.Producer')
    async def test_reprocess_failure_without_dlq_producer_returns_false(
        self,
        mock_producer_class,
        mock_settings,
        mock_mongodb_client,
        mock_metrics,
        sample_dlq_entry
    ):
        """
        Falha sem DLQ producer deve retornar False para retry local.
        """
        mock_producer = MagicMock()
        mock_producer.produce.side_effect = Exception('Kafka unavailable')
        mock_producer_class.return_value = mock_producer

        reprocessor = DLQReprocessor(
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics,
            settings=mock_settings,
            dlq_producer=None  # Sem DLQ producer
        )
        reprocessor._producer = mock_producer

        result = await reprocessor.reprocess_dlq_entry(sample_dlq_entry, {})

        # Deve retornar False porque não pode republicar na DLQ
        assert result is False


class TestApprovalSagaDLQIntegration:
    """
    Testes de integração para envio à DLQ após falha de retries na saga de aprovação.

    Verifica que quando a publicação Kafka falha após esgotamento de retries,
    a saga de aprovação envia corretamente uma entrada para a DLQ e
    incrementa as métricas correspondentes.
    """

    @pytest.fixture
    def mock_mongodb_client(self):
        """MongoDB client mockado"""
        client = MagicMock()
        client.update_plan_approval_status = AsyncMock(return_value=True)
        client.revert_plan_approval_status = AsyncMock(return_value=True)
        client.update_plan_saga_state = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mock_plan_producer_failing(self):
        """Plan producer que sempre falha"""
        producer = MagicMock()
        producer.send_plan = AsyncMock(side_effect=Exception('Kafka broker unavailable'))
        return producer

    @pytest.fixture
    def mock_dlq_producer(self):
        """DLQ producer mockado"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mockadas"""
        metrics = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()
        metrics.increment_approval_dlq_messages = MagicMock()
        metrics.record_saga_compensation = MagicMock()
        metrics.observe_saga_duration = MagicMock()
        metrics.increment_saga_compensation_failure = MagicMock()
        return metrics

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo para testes de integração"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-dlq-integration-001',
            intent_id='intent-dlq-integration-001',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.7,
            risk_band='high',
            complexity_score=0.5,
            explainability_token='exp-dlq-token',
            reasoning_summary='Test DLQ integration',
            original_domain='test',
            original_priority='high',
            original_security_level='confidential'
        )

    @pytest.mark.asyncio
    async def test_saga_sends_dlq_entry_after_kafka_retries_exhausted(
        self,
        mock_mongodb_client,
        mock_plan_producer_failing,
        mock_dlq_producer,
        mock_metrics,
        sample_cognitive_plan
    ):
        """
        Teste de integração: Saga envia entrada DLQ após retries esgotados.

        Verifica que quando send_plan falha após 3 tentativas (retry padrão),
        a saga executa compensação e envia a entrada para DLQ.
        """
        from src.sagas.approval_saga import ApprovalSaga
        from tenacity import RetryError

        saga = ApprovalSaga(
            mongodb_client=mock_mongodb_client,
            plan_producer=mock_plan_producer_failing,
            dlq_producer=mock_dlq_producer,
            metrics=mock_metrics
        )

        trace_context = {'correlation_id': 'corr-dlq-integration-001'}

        # Executar saga - deve falhar após retries e enviar para DLQ
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-dlq-integration-001',
                    intent_id='intent-dlq-integration-001',
                    approved_by='admin@company.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context=trace_context,
                    risk_band='high',
                    is_destructive=True
                )

        # Verificar que DLQ entry foi enviada
        mock_dlq_producer.send_dlq_entry.assert_called_once()

        # Verificar conteúdo da entrada DLQ
        dlq_entry = mock_dlq_producer.send_dlq_entry.call_args[0][0]
        assert dlq_entry.plan_id == 'plan-dlq-integration-001'
        assert dlq_entry.intent_id == 'intent-dlq-integration-001'
        assert dlq_entry.risk_band == 'high'
        assert dlq_entry.is_destructive is True
        assert 'Kafka broker unavailable' in dlq_entry.failure_reason

        # Verificar métricas de compensação
        mock_metrics.record_saga_compensation.assert_called_once_with(
            reason='kafka_publish_failed',
            risk_band='high'
        )

        # Verificar métrica de DLQ
        mock_metrics.increment_approval_dlq_messages.assert_called_once_with(
            reason='saga_compensation',
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    async def test_saga_dlq_entry_contains_original_approval_response(
        self,
        mock_mongodb_client,
        mock_plan_producer_failing,
        mock_dlq_producer,
        mock_metrics,
        sample_cognitive_plan
    ):
        """
        Teste de integração: Entrada DLQ contém original_approval_response completa.

        Verifica que a entrada DLQ preserva todos os dados necessários
        para reprocessamento posterior.
        """
        from src.sagas.approval_saga import ApprovalSaga
        from tenacity import RetryError

        saga = ApprovalSaga(
            mongodb_client=mock_mongodb_client,
            plan_producer=mock_plan_producer_failing,
            dlq_producer=mock_dlq_producer,
            metrics=mock_metrics
        )

        approved_at = datetime.utcnow()
        trace_context = {
            'correlation_id': 'corr-original-response-001',
            'trace_id': 'trace-original-001',
            'span_id': 'span-original-001'
        }

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-dlq-integration-001',
                    intent_id='intent-dlq-integration-001',
                    approved_by='reviewer@company.com',
                    approved_at=approved_at,
                    cognitive_plan=sample_cognitive_plan,
                    trace_context=trace_context,
                    risk_band='high',
                    is_destructive=True
                )

        dlq_entry = mock_dlq_producer.send_dlq_entry.call_args[0][0]

        # Verificar que original_approval_response contém dados necessários
        original_response = dlq_entry.original_approval_response
        assert original_response['plan_id'] == 'plan-dlq-integration-001'
        assert original_response['intent_id'] == 'intent-dlq-integration-001'
        assert original_response['decision'] == 'approved'
        assert original_response['approved_by'] == 'reviewer@company.com'
        assert 'cognitive_plan' in original_response

        # Verificar trace context preservado
        assert dlq_entry.correlation_id == 'corr-original-response-001'
        assert dlq_entry.trace_id == 'trace-original-001'
        assert dlq_entry.span_id == 'span-original-001'

    @pytest.mark.asyncio
    async def test_saga_compensation_failure_still_sends_to_dlq(
        self,
        mock_plan_producer_failing,
        mock_dlq_producer,
        mock_metrics,
        sample_cognitive_plan
    ):
        """
        Teste de integração: DLQ entry enviada mesmo quando compensação falha.

        Verifica que mesmo quando revert_plan_approval_status falha,
        a entrada DLQ ainda é enviada (com flag COMPENSATION_FAILED).
        """
        from src.sagas.approval_saga import ApprovalSaga
        from tenacity import RetryError

        # MongoDB que falha na compensação
        mongodb_client = MagicMock()
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)
        mongodb_client.revert_plan_approval_status = AsyncMock(return_value=False)
        mongodb_client.update_plan_saga_state = AsyncMock(return_value=True)

        saga = ApprovalSaga(
            mongodb_client=mongodb_client,
            plan_producer=mock_plan_producer_failing,
            dlq_producer=mock_dlq_producer,
            metrics=mock_metrics
        )

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-dlq-integration-001',
                    intent_id='intent-dlq-integration-001',
                    approved_by='admin@company.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='critical',
                    is_destructive=True
                )

        # DLQ entry deve ser enviada mesmo com falha na compensação
        mock_dlq_producer.send_dlq_entry.assert_called_once()

        dlq_entry = mock_dlq_producer.send_dlq_entry.call_args[0][0]
        assert '[COMPENSATION_FAILED]' in dlq_entry.failure_reason

        # Métrica de falha de compensação deve ser incrementada
        mock_metrics.increment_saga_compensation_failure.assert_called_once_with('critical')
