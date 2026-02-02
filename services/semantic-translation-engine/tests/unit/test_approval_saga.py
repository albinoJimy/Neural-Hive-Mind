"""
Testes unitários para ApprovalSaga

Testa o Saga Pattern de aprovação com cenários de sucesso,
falha na publicação, compensação e idempotência.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from tenacity import RetryError


class TestApprovalSagaSuccess:
    """Testes para execução bem-sucedida da saga"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.update_plan_approval_status = AsyncMock(return_value=True)
        client.revert_plan_approval_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer"""
        producer = MagicMock()
        producer.send_plan = AsyncMock()
        return producer

    @pytest.fixture
    def dlq_producer(self):
        """Mock DLQ producer"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, dlq_producer, metrics):
        """Create ApprovalSaga instance"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-saga-123',
            intent_id='intent-saga-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.5,
            risk_band='medium',
            complexity_score=0.3,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='medium',
            original_security_level='internal'
        )

    @pytest.mark.asyncio
    async def test_saga_success_updates_ledger_and_publishes(
        self, saga, mongodb_client, plan_producer, metrics, sample_cognitive_plan
    ):
        """Saga bem-sucedida atualiza ledger e publica plano"""
        trace_context = {'correlation_id': 'corr-123'}

        result = await saga.execute(
            plan_id='plan-saga-123',
            intent_id='intent-saga-456',
            approved_by='admin@example.com',
            approved_at=datetime.utcnow(),
            cognitive_plan=sample_cognitive_plan,
            trace_context=trace_context,
            risk_band='medium',
            is_destructive=False
        )

        assert result is True

        # Verificar que ledger foi atualizado duas vezes (executing -> completed)
        assert mongodb_client.update_plan_approval_status.call_count == 2

        # Primeira chamada: saga_state='executing'
        first_call = mongodb_client.update_plan_approval_status.call_args_list[0]
        assert first_call.kwargs['saga_state'] == 'executing'

        # Segunda chamada: saga_state='completed'
        second_call = mongodb_client.update_plan_approval_status.call_args_list[1]
        assert second_call.kwargs['saga_state'] == 'completed'

        # Verificar que plano foi publicado
        plan_producer.send_plan.assert_called_once()

        # Verificar métrica de duração
        metrics.observe_saga_duration.assert_called_once()
        call_args = metrics.observe_saga_duration.call_args
        assert call_args[0][1] == 'completed'

    @pytest.mark.asyncio
    async def test_saga_success_no_compensation_called(
        self, saga, mongodb_client, dlq_producer, sample_cognitive_plan
    ):
        """Saga bem-sucedida não chama compensação"""
        await saga.execute(
            plan_id='plan-saga-123',
            intent_id='intent-saga-456',
            approved_by='admin@example.com',
            approved_at=datetime.utcnow(),
            cognitive_plan=sample_cognitive_plan,
            trace_context={},
            risk_band='low',
            is_destructive=False
        )

        # Compensação não deve ser chamada
        mongodb_client.revert_plan_approval_status.assert_not_called()
        dlq_producer.send_dlq_entry.assert_not_called()


class TestApprovalSagaCompensation:
    """Testes para compensação da saga após falha"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.update_plan_approval_status = AsyncMock(return_value=True)
        client.revert_plan_approval_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer que falha"""
        producer = MagicMock()
        producer.send_plan = AsyncMock(side_effect=Exception('Kafka error'))
        return producer

    @pytest.fixture
    def dlq_producer(self):
        """Mock DLQ producer"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, dlq_producer, metrics):
        """Create ApprovalSaga instance"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-comp-123',
            intent_id='intent-comp-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.8,
            risk_band='high',
            complexity_score=0.5,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='high',
            original_security_level='confidential'
        )

    @pytest.mark.asyncio
    async def test_saga_failure_triggers_compensation(
        self, saga, mongodb_client, plan_producer, metrics, sample_cognitive_plan
    ):
        """Falha na publicação dispara compensação"""
        trace_context = {'correlation_id': 'corr-comp-123'}

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-123',
                    intent_id='intent-comp-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context=trace_context,
                    risk_band='high',
                    is_destructive=True
                )

        # Verificar que compensação foi chamada
        mongodb_client.revert_plan_approval_status.assert_called_once()
        call_args = mongodb_client.revert_plan_approval_status.call_args
        assert call_args.kwargs['plan_id'] == 'plan-comp-123'
        assert call_args.kwargs['saga_state'] == 'compensated'

    @pytest.mark.asyncio
    async def test_saga_compensation_reverts_to_pending(
        self, saga, mongodb_client, sample_cognitive_plan
    ):
        """Compensação reverte status para pending"""
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-123',
                    intent_id='intent-comp-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='high',
                    is_destructive=True
                )

        # Verificar parâmetros da reversão
        call_args = mongodb_client.revert_plan_approval_status.call_args
        assert 'compensation_reason' in call_args.kwargs
        assert 'Kafka error' in call_args.kwargs['compensation_reason']

    @pytest.mark.asyncio
    async def test_saga_compensation_records_metric(
        self, saga, metrics, sample_cognitive_plan
    ):
        """Compensação registra métrica"""
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-123',
                    intent_id='intent-comp-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='high',
                    is_destructive=True
                )

        metrics.record_saga_compensation.assert_called_once_with(
            reason='kafka_publish_failed',
            risk_band='high'
        )

    @pytest.mark.asyncio
    async def test_saga_compensation_sends_to_dlq(
        self, saga, dlq_producer, sample_cognitive_plan
    ):
        """Compensação envia entrada para DLQ"""
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-123',
                    intent_id='intent-comp-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={'correlation_id': 'corr-123'},
                    risk_band='high',
                    is_destructive=True
                )

        dlq_producer.send_dlq_entry.assert_called_once()
        dlq_entry = dlq_producer.send_dlq_entry.call_args[0][0]
        assert dlq_entry.plan_id == 'plan-comp-123'
        assert '[COMPENSATED]' in dlq_entry.failure_reason


class TestApprovalSagaInitFailure:
    """Testes para falha na inicialização da saga"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client que falha na primeira atualização"""
        client = MagicMock()
        client.update_plan_approval_status = AsyncMock(return_value=False)
        client.revert_plan_approval_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer"""
        producer = MagicMock()
        producer.send_plan = AsyncMock()
        return producer

    @pytest.fixture
    def dlq_producer(self):
        """Mock DLQ producer"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, dlq_producer, metrics):
        """Create ApprovalSaga instance"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-init-fail-123',
            intent_id='intent-init-fail-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.5,
            risk_band='medium',
            complexity_score=0.3,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='medium',
            original_security_level='internal'
        )

    @pytest.mark.asyncio
    async def test_saga_init_failure_raises_exception(
        self, saga, plan_producer, metrics, sample_cognitive_plan
    ):
        """Falha na inicialização da saga propaga exceção"""
        with pytest.raises(RuntimeError) as exc_info:
            await saga.execute(
                plan_id='plan-init-fail-123',
                intent_id='intent-init-fail-456',
                approved_by='admin@example.com',
                approved_at=datetime.utcnow(),
                cognitive_plan=sample_cognitive_plan,
                trace_context={},
                risk_band='medium',
                is_destructive=False
            )

        assert 'Falha ao iniciar saga' in str(exc_info.value)

        # Kafka não deve ser chamado
        plan_producer.send_plan.assert_not_called()

        # Métrica de erro deve ser registrada
        metrics.increment_approval_ledger_error.assert_called_with('saga_init_failed')


class TestApprovalSagaCompensationFailure:
    """Testes para falha na compensação"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        # Primeira chamada sucesso, segunda também (para completed), mas revert falha
        client.update_plan_approval_status = AsyncMock(return_value=True)
        client.revert_plan_approval_status = AsyncMock(return_value=False)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer que falha"""
        producer = MagicMock()
        producer.send_plan = AsyncMock(side_effect=Exception('Kafka error'))
        return producer

    @pytest.fixture
    def dlq_producer(self):
        """Mock DLQ producer"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, dlq_producer, metrics):
        """Create ApprovalSaga instance"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-comp-fail-123',
            intent_id='intent-comp-fail-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.9,
            risk_band='critical',
            complexity_score=0.7,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='critical',
            original_security_level='restricted'
        )

    @pytest.mark.asyncio
    async def test_compensation_failure_still_sends_to_dlq(
        self, saga, dlq_producer, sample_cognitive_plan
    ):
        """Falha na compensação ainda envia para DLQ com flag"""
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-fail-123',
                    intent_id='intent-comp-fail-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='critical',
                    is_destructive=True
                )

        dlq_producer.send_dlq_entry.assert_called_once()
        dlq_entry = dlq_producer.send_dlq_entry.call_args[0][0]
        assert '[COMPENSATION_FAILED]' in dlq_entry.failure_reason

    @pytest.mark.asyncio
    async def test_compensation_failure_does_not_block_exception(
        self, saga, sample_cognitive_plan
    ):
        """Falha na compensação não bloqueia propagação da exceção original"""
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-fail-123',
                    intent_id='intent-comp-fail-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='critical',
                    is_destructive=True
                )
        # Se chegou aqui, a exceção foi propagada corretamente


class TestApprovalSagaNoDLQ:
    """Testes para saga sem DLQ configurado"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.update_plan_approval_status = AsyncMock(return_value=True)
        client.revert_plan_approval_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer que falha"""
        producer = MagicMock()
        producer.send_plan = AsyncMock(side_effect=Exception('Kafka error'))
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalSaga instance without DLQ"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, None, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-no-dlq-123',
            intent_id='intent-no-dlq-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.5,
            risk_band='medium',
            complexity_score=0.3,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='medium',
            original_security_level='internal'
        )

    @pytest.mark.asyncio
    async def test_saga_without_dlq_still_compensates(
        self, saga, mongodb_client, sample_cognitive_plan
    ):
        """Saga sem DLQ ainda executa compensação no MongoDB"""
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-no-dlq-123',
                    intent_id='intent-no-dlq-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='medium',
                    is_destructive=False
                )

        # Compensação no MongoDB deve ser chamada
        mongodb_client.revert_plan_approval_status.assert_called_once()


class TestApprovalSagaCompletionUpdateFailure:
    """
    Testes para Comment 2: Falha ao atualizar ledger para completed após publicação bem-sucedida.

    Quando a publicação no Kafka é bem-sucedida mas a atualização final do ledger falha,
    a saga deve marcar o ledger como 'failed' em vez de silenciosamente retornar sucesso.
    """

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client que falha na segunda atualização (completed)"""
        client = MagicMock()
        # Primeira chamada (executing) sucesso, segunda (completed) falha
        client.update_plan_approval_status = AsyncMock(side_effect=[True, False, False, False, False])
        client.revert_plan_approval_status = AsyncMock(return_value=True)
        client.update_plan_saga_state = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer que funciona"""
        producer = MagicMock()
        producer.send_plan = AsyncMock()
        return producer

    @pytest.fixture
    def dlq_producer(self):
        """Mock DLQ producer"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.increment_saga_compensation_failure = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, dlq_producer, metrics):
        """Create ApprovalSaga instance"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-comp-fail-update-123',
            intent_id='intent-comp-fail-update-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.6,
            risk_band='medium',
            complexity_score=0.4,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='medium',
            original_security_level='internal'
        )

    @pytest.mark.asyncio
    async def test_completion_update_failure_marks_saga_as_failed(
        self, saga, mongodb_client, metrics, sample_cognitive_plan
    ):
        """
        Comment 2 Test: Quando update final falha, saga marca ledger como 'failed'.

        Verifica que se a publicação Kafka foi bem-sucedida mas a atualização
        do ledger para 'completed' falha após retries, a saga:
        1. Marca o ledger com saga_state='failed'
        2. Registra a métrica 'saga_completion_update_failed'
        3. Retorna True (pois plano foi publicado com sucesso)
        """
        result = await saga.execute(
            plan_id='plan-comp-fail-update-123',
            intent_id='intent-comp-fail-update-456',
            approved_by='admin@example.com',
            approved_at=datetime.utcnow(),
            cognitive_plan=sample_cognitive_plan,
            trace_context={'correlation_id': 'corr-123'},
            risk_band='medium',
            is_destructive=False
        )

        # Saga retorna True pois plano foi publicado
        assert result is True

        # Verificar que métrica de erro foi registrada
        metrics.increment_approval_ledger_error.assert_called_with('saga_completion_update_failed')

        # Verificar duração foi observada com estado FAILED
        metrics.observe_saga_duration.assert_called_once()
        call_args = metrics.observe_saga_duration.call_args
        assert call_args[0][1] == 'failed'

        # Verificar que a atualização final tentou marcar como failed
        # (4 chamadas: 1 executing + 3 retries para completed + 1 para failed)
        assert mongodb_client.update_plan_approval_status.call_count >= 4

        # Última chamada deve ter saga_state='failed'
        last_call = mongodb_client.update_plan_approval_status.call_args_list[-1]
        assert last_call.kwargs.get('saga_state') == 'failed'

    @pytest.mark.asyncio
    async def test_completion_update_with_exception_marks_saga_as_failed(
        self, mongodb_client, plan_producer, dlq_producer, metrics
    ):
        """
        Comment 2 Test: Quando update final lança exceção, saga marca ledger como 'failed'.

        Verifica comportamento quando MongoDB lança exceção durante atualização final.
        """
        from src.sagas.approval_saga import ApprovalSaga
        from src.models.cognitive_plan import CognitivePlan

        # Primeira chamada sucesso, próximas lançam exceção
        mongodb_client.update_plan_approval_status = AsyncMock(
            side_effect=[True, Exception('MongoDB connection lost'), Exception('MongoDB connection lost'), Exception('MongoDB connection lost'), True]
        )

        saga = ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

        plan = CognitivePlan(
            plan_id='plan-exc-123',
            intent_id='intent-exc-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.5,
            risk_band='medium',
            complexity_score=0.3,
            explainability_token='exp-token',
            reasoning_summary='Test',
            original_domain='test',
            original_priority='medium',
            original_security_level='internal'
        )

        result = await saga.execute(
            plan_id='plan-exc-123',
            intent_id='intent-exc-456',
            approved_by='admin@example.com',
            approved_at=datetime.utcnow(),
            cognitive_plan=plan,
            trace_context={},
            risk_band='medium',
            is_destructive=False
        )

        assert result is True
        metrics.increment_approval_ledger_error.assert_called_with('saga_completion_update_failed')


class TestApprovalSagaCompensationFailureMarksFailed:
    """
    Testes para Comment 3: Quando compensação falha, saga marca ledger como 'failed'.

    Quando a publicação Kafka falha e a compensação (reversão do ledger) também falha,
    a saga deve marcar o ledger com saga_state='failed' via best-effort update
    para não deixar o ledger em estado inconsistente (approved/executing).
    """

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        # update_plan_approval_status: primeira chamada sucesso (executing)
        client.update_plan_approval_status = AsyncMock(return_value=True)
        # Reversão falha
        client.revert_plan_approval_status = AsyncMock(return_value=False)
        # Best-effort update para failed
        client.update_plan_saga_state = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer que falha"""
        producer = MagicMock()
        producer.send_plan = AsyncMock(side_effect=Exception('Kafka broker unavailable'))
        return producer

    @pytest.fixture
    def dlq_producer(self):
        """Mock DLQ producer"""
        producer = MagicMock()
        producer.send_dlq_entry = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.increment_saga_compensation_failure = MagicMock()
        return m

    @pytest.fixture
    def saga(self, mongodb_client, plan_producer, dlq_producer, metrics):
        """Create ApprovalSaga instance"""
        from src.sagas.approval_saga import ApprovalSaga
        return ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        from src.models.cognitive_plan import CognitivePlan
        return CognitivePlan(
            plan_id='plan-comp-mark-failed-123',
            intent_id='intent-comp-mark-failed-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.85,
            risk_band='high',
            complexity_score=0.6,
            explainability_token='exp-token',
            reasoning_summary='Test summary',
            original_domain='test',
            original_priority='high',
            original_security_level='confidential'
        )

    @pytest.mark.asyncio
    async def test_compensation_failure_calls_mark_saga_as_failed(
        self, saga, mongodb_client, metrics, sample_cognitive_plan
    ):
        """
        Comment 3 Test: Falha na compensação chama _mark_saga_as_failed.

        Verifica que quando revert_plan_approval_status retorna False,
        a saga chama update_plan_saga_state para marcar como 'failed'.
        """
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-mark-failed-123',
                    intent_id='intent-comp-mark-failed-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={'correlation_id': 'corr-123'},
                    risk_band='high',
                    is_destructive=True
                )

        # Verificar que update_plan_saga_state foi chamado para marcar como failed
        mongodb_client.update_plan_saga_state.assert_called_once()
        call_args = mongodb_client.update_plan_saga_state.call_args
        assert call_args.kwargs['plan_id'] == 'plan-comp-mark-failed-123'
        assert call_args.kwargs['saga_state'] == 'failed'
        assert 'Compensação falhou' in call_args.kwargs['saga_failure_reason']

    @pytest.mark.asyncio
    async def test_compensation_failure_records_specific_metric(
        self, saga, metrics, sample_cognitive_plan
    ):
        """
        Comment 3 Test: Falha na compensação registra métrica específica.

        Verifica que increment_saga_compensation_failure é chamada
        com o risk_band correto.
        """
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-mark-failed-123',
                    intent_id='intent-comp-mark-failed-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='high',
                    is_destructive=True
                )

        metrics.increment_saga_compensation_failure.assert_called_once_with('high')

    @pytest.mark.asyncio
    async def test_compensation_failure_dlq_entry_contains_compensation_failed_flag(
        self, saga, dlq_producer, sample_cognitive_plan
    ):
        """
        Comment 3 Test: DLQ entry contém flag COMPENSATION_FAILED.

        Verifica que a entrada DLQ indica que a compensação falhou.
        """
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-comp-mark-failed-123',
                    intent_id='intent-comp-mark-failed-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=sample_cognitive_plan,
                    trace_context={},
                    risk_band='high',
                    is_destructive=True
                )

        dlq_producer.send_dlq_entry.assert_called_once()
        dlq_entry = dlq_producer.send_dlq_entry.call_args[0][0]
        assert '[COMPENSATION_FAILED]' in dlq_entry.failure_reason

    @pytest.mark.asyncio
    async def test_mark_saga_as_failed_is_best_effort(
        self, mongodb_client, plan_producer, dlq_producer, metrics
    ):
        """
        Comment 3 Test: mark_saga_as_failed não propaga exceção (best-effort).

        Verifica que se update_plan_saga_state também falhar, a exceção
        não é propagada e o fluxo continua.
        """
        from src.sagas.approval_saga import ApprovalSaga
        from src.models.cognitive_plan import CognitivePlan

        # Configurar para que update_plan_saga_state lance exceção
        mongodb_client.update_plan_saga_state = AsyncMock(
            side_effect=Exception('MongoDB completely unavailable')
        )

        saga = ApprovalSaga(mongodb_client, plan_producer, dlq_producer, metrics)

        plan = CognitivePlan(
            plan_id='plan-best-effort-123',
            intent_id='intent-best-effort-456',
            version='1.0.0',
            tasks=[],
            execution_order=[],
            risk_score=0.9,
            risk_band='critical',
            complexity_score=0.7,
            explainability_token='exp-token',
            reasoning_summary='Test',
            original_domain='test',
            original_priority='critical',
            original_security_level='restricted'
        )

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            # Deve lançar RetryError do Kafka, não exceção do MongoDB
            with pytest.raises(RetryError):
                await saga.execute(
                    plan_id='plan-best-effort-123',
                    intent_id='intent-best-effort-456',
                    approved_by='admin@example.com',
                    approved_at=datetime.utcnow(),
                    cognitive_plan=plan,
                    trace_context={},
                    risk_band='critical',
                    is_destructive=True
                )

        # DLQ ainda deve ser enviada mesmo que best-effort update falhe
        dlq_producer.send_dlq_entry.assert_called_once()
