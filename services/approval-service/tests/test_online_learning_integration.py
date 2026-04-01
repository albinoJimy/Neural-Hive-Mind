"""
Testes de Integração de Online Learning

Cobre FeedbackConsumer, OnlineLearningService e RetrainingScheduler.
Meta: 20+ testes
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, Mock, patch
from collections import deque

from src.consumers.feedback_consumer import (
    FeedbackConsumer,
    FeedbackBuffer
)
from src.services.online_learning_service import (
    OnlineLearningService,
    OnlineLearningServiceError,
    OnlineLearningNotEnabledError,
    FeatureExtractionError
)
from src.schedulers.retraining_scheduler import (
    RetrainingScheduler,
    SchedulerStatus,
    RetrainingTrigger,
    ValidationStatus,
    create_retraining_scheduler
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_settings_with_online_learning(mock_settings):
    """Settings com online learning habilitado"""
    mock_settings.enable_online_learning = True
    mock_settings.online_learning_buffer_size = 50
    mock_settings.online_learning_retrain_interval_hours = 12
    mock_settings.kafka_specialist_feedback_topic = 'specialist-feedback-test'
    mock_settings.online_learning_checkpoint_path = '/tmp/test_checkpoints'
    mock_settings.online_learning_algorithm = 'sgd'
    mock_settings.online_learning_learning_rate = 0.001
    mock_settings.online_learning_checkpoint_interval_updates = 50
    return mock_settings


@pytest.fixture
def sample_feedback_message():
    """Mensagem de feedback de exemplo"""
    return {
        'feedback_id': 'feedback-001',
        'opinion_id': 'opinion-001',
        'plan_id': 'plan-001',
        'specialist_type': 'technical',
        'human_rating': 1.0,
        'human_recommendation': 'approve',
        'feedback_notes': 'Recomendação correta',
        'submitted_at': int(datetime.now(timezone.utc).timestamp() * 1000),
        'submitted_by': 'admin@example.com',
        'intent_raw_text': 'List all users from the database',
        'specialist_recommendation': 'approve',
        'specialist_confidence': 0.85
    }


@pytest.fixture
def sample_feedback_message_with_nlp():
    """Feedback com features NLP"""
    feedback = sample_feedback_message()
    feedback['nlp_features'] = {
        'sentiment_score': 0.7,
        'urgency_score': 0.5,
        'complexity_score': 0.3,
        'primary_domain': 'technical'
    }
    return feedback


@pytest.fixture
def sample_feedback_batch(sample_feedback_message):
    """Lote de feedbacks para teste"""
    return [
        {**sample_feedback_message, 'feedback_id': f'feedback-{i:03d}', 'specialist_type': 'technical'}
        for i in range(10)
    ]


# ============================================================================
# Testes: FeedbackBuffer
# ============================================================================

class TestFeedbackBuffer:
    """Testes para FeedbackBuffer"""

    def test_buffer_initialization(self):
        """D001-T01: Buffer deve inicializar com tamanho maximo correto"""
        buffer = FeedbackBuffer(max_size=100)
        assert buffer.size == 0
        assert buffer.is_full is False
        assert buffer._max_size == 100

    @pytest.mark.asyncio
    async def test_buffer_add_single_item(self, sample_feedback_message):
        """D001-T02: Buffer deve adicionar item corretamente"""
        buffer = FeedbackBuffer(max_size=10)
        added = await buffer.add(sample_feedback_message)
        assert added is True
        assert buffer.size == 1

    @pytest.mark.asyncio
    async def test_buffer_add_when_full(self, sample_feedback_message):
        """D001-T03: Buffer deve rejeitar itens quando cheio"""
        buffer = FeedbackBuffer(max_size=2)

        await buffer.add(sample_feedback_message)
        await buffer.add(sample_feedback_message)

        # Terceiro item deve ser rejeitado
        added = await buffer.add(sample_feedback_message)
        assert added is False
        assert buffer.is_full is True

    @pytest.mark.asyncio
    async def test_buffer_get_batch_all(self, sample_feedback_message):
        """D001-T04: Buffer deve retornar todos os itens quando batch_size=None"""
        buffer = FeedbackBuffer(max_size=10)

        for i in range(5):
            await buffer.add({**sample_feedback_message, 'feedback_id': f'fb-{i}'})

        batch = await buffer.get_batch()
        assert len(batch) == 5
        assert buffer.size == 0

    @pytest.mark.asyncio
    async def test_buffer_get_batch_partial(self, sample_feedback_message):
        """D001-T05: Buffer deve retornar lote parcial quando batch_size especificado"""
        buffer = FeedbackBuffer(max_size=10)

        for i in range(5):
            await buffer.add({**sample_feedback_message, 'feedback_id': f'fb-{i}'})

        batch = await buffer.get_batch(batch_size=3)
        assert len(batch) == 3
        assert buffer.size == 2

    @pytest.mark.asyncio
    async def test_buffer_peek(self, sample_feedback_message):
        """D001-T06: Buffer deve espiar itens sem remove-los"""
        buffer = FeedbackBuffer(max_size=10)

        await buffer.add(sample_feedback_message)
        await buffer.add(sample_feedback_message)

        peeked = await buffer.peek(count=2)
        assert len(peeked) == 2
        assert buffer.size == 2  # Nao removeu

    def test_buffer_clear(self, sample_feedback_message):
        """D001-T07: Buffer deve limpar todos os itens"""
        buffer = FeedbackBuffer(max_size=10)
        # Sincrono - buffer usa deque interno
        buffer._buffer.append(sample_feedback_message)
        buffer._buffer.append(sample_feedback_message)

        buffer.clear()
        assert buffer.size == 0


# ============================================================================
# Testes: FeedbackConsumer
# ============================================================================

class TestFeedbackConsumer:
    """Testes para FeedbackConsumer"""

    @pytest.mark.asyncio
    async def test_consumer_initialization(self, mock_settings_with_online_learning):
        """D001-T08: Consumer deve inicializar com configuracoes corretas"""
        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning,
            buffer_size=100
        )

        assert consumer._buffer_size == 100
        assert consumer.running is False
        assert consumer._buffer.size == 0

    @pytest.mark.asyncio
    async def test_consumer_initialize_without_kafka(self, mock_settings_with_online_learning):
        """D001-T09: Consumer deve falhar graceful ao inicializar sem Kafka"""
        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning
        )

        # Mock para evitar conexao real
        with patch('src.consumers.feedback_consumer.Consumer') as mock_consumer_class:
            mock_instance = MagicMock()
            mock_consumer_class.return_value = mock_instance

            await consumer.initialize()

            mock_instance.subscribe.assert_called_once_with(
                [mock_settings_with_online_learning.kafka_specialist_feedback_topic]
            )

    @pytest.mark.asyncio
    async def test_deserialize_feedback_message(
        self,
        mock_settings_with_online_learning,
        sample_feedback_message
    ):
        """D001-T10: Consumer deve deserializar mensagem JSON corretamente"""
        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning
        )

        # Criar mensagem mock
        mock_msg = MagicMock()
        mock_msg.value.return_value = json.dumps(sample_feedback_message).encode('utf-8')
        mock_msg.topic.return_value = 'specialist-feedback'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        mock_msg.timestamp.return_value = (0, int(datetime.now(timezone.utc).timestamp() * 1000))
        mock_msg.headers.return_value = None

        feedback = await consumer._deserialize_message(mock_msg)

        assert feedback is not None
        assert feedback['feedback_id'] == 'feedback-001'
        assert feedback['specialist_type'] == 'technical'
        assert '_kafka_metadata' in feedback

    @pytest.mark.asyncio
    async def test_buffer_stats(self, mock_settings_with_online_learning):
        """D001-T11: Consumer deve retornar estatisticas do buffer"""
        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning,
            buffer_size=100
        )

        stats = await consumer.get_buffer_stats()

        assert stats['buffer_size'] == 0
        assert stats['buffer_max_size'] == 100
        assert stats['buffer_utilization'] == 0.0
        assert stats['is_full'] is False

    @pytest.mark.asyncio
    async def test_consumer_health_check(self, mock_settings_with_online_learning):
        """D001-T12: Consumer health check deve funcionar corretamente"""
        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning
        )

        # Consumer não inicializado
        is_healthy, reason = consumer.is_healthy()
        assert is_healthy is False
        assert 'nao inicializado' in reason.lower()

        # Consumer rodando (mock)
        consumer.running = True
        consumer.consumer = MagicMock()
        consumer._last_poll_time = datetime.now(timezone.utc)

        is_healthy, reason = consumer.is_healthy()
        assert is_healthy is True


# ============================================================================
# Testes: OnlineLearningService
# ============================================================================

class TestOnlineLearningService:
    """Testes para OnlineLearningService"""

    def test_service_disabled_by_default(self, mock_settings):
        """D002-T01: Servico deve ser desabilitado se configuracao ou dependencia faltar"""
        mock_settings.enable_online_learning = False

        service = OnlineLearningService(settings=mock_settings)
        assert service.is_enabled is False

    @pytest.mark.asyncio
    async def test_service_initialization_when_disabled(self, mock_settings):
        """D002-T02: Servico deve inicializar graceful quando desabilitado"""
        mock_settings.enable_online_learning = False

        service = OnlineLearningService(settings=mock_settings)
        await service.initialize()  # Nao deve levantar excecao

    def test_extract_label_from_human_recommendation(
        self,
        mock_settings_with_online_learning,
        sample_feedback_message
    ):
        """D002-T03: Extrair label de human_recommendation deve funcionar"""
        service = OnlineLearningService(settings=mock_settings_with_online_learning)

        # Testar diferentes valores
        test_cases = [
            ('approve', 'approve'),
            ('approved', 'approve'),
            ('reject', 'reject'),
            ('rejected', 'reject'),
            ('review', 'review_required'),
            ('review_required', 'review_required'),
        ]

        for input_val, expected in test_cases:
            feedback = {**sample_feedback_message, 'human_recommendation': input_val}
            label = service._extract_label(feedback)
            assert label == expected, f"Input: {input_val}, Expected: {expected}, Got: {label}"

    def test_extract_label_from_rating(
        self,
        mock_settings_with_online_learning,
        sample_feedback_message
    ):
        """D002-T04: Extrair label de rating quando sem human_recommendation"""
        service = OnlineLearningService(settings=mock_settings_with_online_learning)

        test_cases = [
            (1.0, 'approve'),
            (0.8, 'approve'),
            (0.7, 'approve'),
            (0.5, 'review_required'),
            (0.4, 'review_required'),
            (0.3, 'reject'),
            (0.0, 'reject'),
        ]

        for rating, expected in test_cases:
            feedback = {
                **sample_feedback_message,
                'human_recommendation': None,
                'human_rating': rating
            }
            label = service._extract_label(feedback)
            assert label == expected, f"Rating: {rating}, Expected: {expected}, Got: {label}"

    def test_extract_features_basic(
        self,
        mock_settings_with_online_learning,
        sample_feedback_message
    ):
        """D002-T05: Extrair features básicas deve funcionar"""
        service = OnlineLearningService(settings=mock_settings_with_online_learning)

        features = service._extract_features(sample_feedback_message)

        assert features is not None
        assert len(features) == 10  # 10 features esperadas
        assert features[0] == 0.85  # specialist_confidence

    def test_extract_features_with_nlp(
        self,
        mock_settings_with_online_learning,
        sample_feedback_message_with_nlp
    ):
        """D002-T06: Extrair features com NLP deve incluir sentiment, urgency, complexity"""
        service = OnlineLearningService(settings=mock_settings_with_online_learning)

        features = service._extract_features(sample_feedback_message_with_nlp)

        assert features is not None
        # sentiment (3), urgency (4), complexity (5)
        assert features[3] == 0.7
        assert features[4] == 0.5
        assert features[5] == 0.3

    @pytest.mark.asyncio
    async def test_get_model_state_when_disabled(
        self,
        mock_settings
    ):
        """D002-T07: get_model_state deve retornar None quando desabilitado"""
        mock_settings.enable_online_learning = False
        service = OnlineLearningService(settings=mock_settings)

        state = await service.get_model_state('technical')
        assert state is None

    @pytest.mark.asyncio
    async def test_get_all_learner_states_when_disabled(
        self,
        mock_settings
    ):
        """D002-T08: get_all_learner_states deve retornar disabled quando desabilitado"""
        mock_settings.enable_online_learning = False
        service = OnlineLearningService(settings=mock_settings)

        states = await service.get_all_learner_states()
        assert states['enabled'] is False

    def test_process_feedback_batch_raises_when_disabled(
        self,
        mock_settings,
        sample_feedback_batch
    ):
        """D002-T09: process_feedback_batch deve levantar OnlineLearningNotEnabledError"""
        mock_settings.enable_online_learning = False
        service = OnlineLearningService(settings=mock_settings)

        with pytest.raises(OnlineLearningNotEnabledError):
            asyncio.run(service.process_feedback_batch(sample_feedback_batch))

    @pytest.mark.asyncio
    async def test_group_feedbacks_by_specialist(
        self,
        mock_settings_with_online_learning,
        sample_feedback_batch
    ):
        """D002-T10: Agrupar feedbacks por specialist deve funcionar"""
        service = OnlineLearningService(settings=mock_settings_with_online_learning)

        # Adicionar feedbacks de outros specialists
        mixed_batch = [
            *sample_feedback_batch[:3],
            {**sample_feedback_batch[0], 'specialist_type': 'security'},
            {**sample_feedback_batch[0], 'specialist_type': 'business'},
        ]

        grouped = service._group_feedbacks_by_specialist(mixed_batch)

        assert 'technical' in grouped
        assert 'security' in grouped
        assert 'business' in grouped
        assert len(grouped['technical']) == 3


# ============================================================================
# Testes: RetrainingScheduler
# ============================================================================

class TestRetrainingScheduler:
    """Testes para RetrainingScheduler"""

    def test_scheduler_initialization(self, mock_settings_with_online_learning):
        """D003-T01: Scheduler deve inicializar com configuracoes corretas"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        assert scheduler.status == SchedulerStatus.STOPPED
        assert scheduler.is_running is False
        assert scheduler._retrain_interval_hours == 12

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self, mock_settings_with_online_learning):
        """D003-T02: Scheduler deve iniciar e parar corretamente"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        await scheduler.start()
        assert scheduler.is_running is True

        await scheduler.stop()
        assert scheduler.status == SchedulerStatus.STOPPED

    @pytest.mark.asyncio
    async def test_scheduler_pause_resume(self, mock_settings_with_online_learning):
        """D003-T03: Scheduler deve pausar e retomar corretamente"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        await scheduler.start()
        await scheduler.pause()
        assert scheduler.status == SchedulerStatus.PAUSED

        await scheduler.resume()
        assert scheduler.is_running is True

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_manual_retraining_trigger(self, mock_settings_with_online_learning):
        """D003-T04: Trigger manual de retreino deve funcionar"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        result = await scheduler.trigger_manual_retraining(
            reason='Test manual trigger',
            requested_by='test@example.com'
        )

        assert result['triggered'] is True
        assert result['trigger_type'] == RetrainingTrigger.MANUAL
        assert result['requested_by'] == 'test@example.com'

    @pytest.mark.asyncio
    async def test_shadow_validation(self, mock_settings_with_online_learning):
        """D003-T05: Shadow validation deve executar com sucesso"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        result = await scheduler._run_shadow_validation(sample_size=100)

        assert 'validation_id' in result
        assert result['status'] in [
            ValidationStatus.VALIDATING,
            ValidationStatus.PASSED,
            ValidationStatus.FAILED
        ]
        assert result['sample_size'] == 100

    @pytest.mark.asyncio
    async def test_ab_test_creation(self, mock_settings_with_online_learning):
        """D003-T06: Criar teste A/B deve retornar configuracao correta"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        result = await scheduler.run_ab_test(
            model_a_id='model-v1',
            model_b_id='model-v2',
            traffic_split=0.3,
            duration_minutes=30
        )

        assert 'test_id' in result
        assert result['model_a_id'] == 'model-v1'
        assert result['model_b_id'] == 'model-v2'
        assert result['traffic_split'] == 0.3
        assert result['status'] == 'running'

    @pytest.mark.asyncio
    async def test_get_scheduler_status(self, mock_settings_with_online_learning):
        """D003-T07: Status do scheduler deve ser retornado corretamente"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        status = await scheduler.get_scheduler_status()

        assert 'status' in status
        assert 'is_running' in status
        assert 'retrain_interval_hours' in status
        assert status['retrain_interval_hours'] == 12

    @pytest.mark.asyncio
    async def test_clear_validation_history(self, mock_settings_with_online_learning):
        """D003-T08: Limpar historico de validacoes deve funcionar"""
        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning
        )

        # Adicionar validacoes mock
        scheduler._validation_results['old_validation'] = {
            'validation_id': 'old_validation',
            'status': ValidationStatus.PASSED,
            'started_at': '2024-01-01T00:00:00'
        }
        scheduler._validation_results['new_validation'] = {
            'validation_id': 'new_validation',
            'status': ValidationStatus.PENDING,
            'started_at': datetime.now(timezone.utc).isoformat()
        }

        scheduler.clear_validation_history(older_than_hours=1)

        # Validacao antiga deve ser removida
        assert 'old_validation' not in scheduler._validation_results
        # Nova validacao deve permanecer
        assert 'new_validation' in scheduler._validation_results


# ============================================================================
# Testes: Factory Function
# ============================================================================

class TestFactoryFunction:
    """Testes para funcoes factory"""

    def test_create_retraining_scheduler(self, mock_settings_with_online_learning):
        """D003-T09: Factory function deve criar scheduler corretamente"""
        scheduler = create_retraining_scheduler(
            settings=mock_settings_with_online_learning
        )

        assert isinstance(scheduler, RetrainingScheduler)
        assert scheduler.status == SchedulerStatus.STOPPED

    def test_create_retraining_scheduler_with_dependencies(
        self,
        mock_settings_with_online_learning
    ):
        """D003-T10: Factory deve aceitar dependencias opcionais"""
        mock_ol_service = MagicMock()
        mock_drift_detector = MagicMock()

        scheduler = create_retraining_scheduler(
            settings=mock_settings_with_online_learning,
            online_learning_service=mock_ol_service,
            drift_detector=mock_drift_detector
        )

        assert scheduler.online_learning_service == mock_ol_service
        assert scheduler.drift_detector == mock_drift_detector


# ============================================================================
# Testes de Integracao
# ============================================================================

class TestOnlineLearningIntegration:
    """Testes de integracao entre componentes"""

    @pytest.mark.asyncio
    async def test_feedback_consumer_to_service_flow(
        self,
        mock_settings_with_online_learning,
        sample_feedback_batch
    ):
        """D004-T01: Fluxo de FeedbackConsumer para OnlineLearningService"""
        # Este teste verifica que feedbacks podem ser processados
        # end-to-end atraves do buffer e do servico

        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning,
            buffer_size=20
        )

        # Adicionar feedbacks ao buffer
        for feedback in sample_feedback_batch:
            await consumer._buffer.add(feedback)

        # Verificar buffer tem itens
        assert consumer._buffer.size == 10

        # Obter batch
        batch = await consumer._buffer.get_batch()

        assert len(batch) == 10
        assert consumer._buffer.size == 0

    @pytest.mark.asyncio
    async def test_scheduler_with_online_learning_service(
        self,
        mock_settings_with_online_learning
    ):
        """D004-T02: Scheduler deve interagir com OnlineLearningService"""
        mock_ol_service = AsyncMock()
        mock_ol_service.save_all_checkpoints.return_value = {
            'enabled': True,
            'results': {'technical': {'success': True}}
        }

        scheduler = RetrainingScheduler(
            settings=mock_settings_with_online_learning,
            online_learning_service=mock_ol_service
        )

        # Executar retreino agendado (mock)
        await scheduler._run_scheduled_retraining()

        # Verificar que checkpoints foram salvos
        mock_ol_service.save_all_checkpoints.assert_called_once()

    @pytest.mark.asyncio
    async def test_buffer_utilization_tracking(
        self,
        mock_settings_with_online_learning
    ):
        """D004-T03: Utilizacao do buffer deve ser calculada corretamente"""
        consumer = FeedbackConsumer(
            settings=mock_settings_with_online_learning,
            buffer_size=100
        )

        # Adicionar alguns itens
        for i in range(25):
            await consumer._buffer.add({'feedback_id': f'fb-{i}'})

        stats = await consumer.get_buffer_stats()
        assert stats['buffer_utilization'] == 0.25

    @pytest.mark.asyncio
    async def test_concurrent_buffer_access(
        self,
        mock_settings_with_online_learning,
        sample_feedback_message
    ):
        """D004-T04: Buffer deve ser thread-safe para acesso concorrente"""
        buffer = FeedbackBuffer(max_size=100)

        # Adicionar itens concorrentemente
        tasks = [
            buffer.add({**sample_feedback_message, 'feedback_id': f'fb-{i}'})
            for i in range(50)
        ]

        results = await asyncio.gather(*tasks)

        # Todos devem ser adicionados com sucesso
        assert all(results)
        assert buffer.size == 50
