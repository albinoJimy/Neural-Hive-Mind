"""
Testes unitários para ApprovalProcessor

Testa processamento de aprovações/rejeições, atualização de ledger,
publicação de planos aprovados e métricas.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from tenacity import RetryError


class TestApprovalProcessorApproved:
    """Testes para processamento de planos aprovados"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
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
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.fixture
    def sample_ledger_entry(self):
        """Entrada de ledger de exemplo"""
        return {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-123',
                'intent_id': 'intent-456',
                'version': '1.0.0',
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': True,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.8,
                'complexity_score': 0.5,
                'explainability_token': 'exp-token',
                'reasoning_summary': 'Test summary',
                'original_domain': 'test',
                'original_priority': 'high',
                'original_security_level': 'confidential'
            }
        }

    @pytest.mark.asyncio
    async def test_process_approved_plan_updates_ledger(
        self, processor, mongodb_client, sample_ledger_entry
    ):
        """Aprovação deve atualizar status no ledger via saga (executing + completed)"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Saga chama ledger 2 vezes: executing e completed
        assert mongodb_client.update_plan_approval_status.call_count == 2
        calls = mongodb_client.update_plan_approval_status.call_args_list
        # Primeira chamada: saga_state='executing'
        assert calls[0].kwargs['plan_id'] == 'plan-123'
        assert calls[0].kwargs['approval_status'] == 'approved'
        assert calls[0].kwargs['saga_state'] == 'executing'
        # Segunda chamada: saga_state='completed'
        assert calls[1].kwargs['plan_id'] == 'plan-123'
        assert calls[1].kwargs['saga_state'] == 'completed'

    @pytest.mark.asyncio
    async def test_process_approved_plan_publishes_to_kafka(
        self, processor, mongodb_client, plan_producer, sample_ledger_entry
    ):
        """Aprovação deve publicar plano no Kafka"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        plan_producer.send_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_approved_plan_records_metrics(
        self, processor, mongodb_client, metrics, sample_ledger_entry
    ):
        """Aprovação deve registrar métricas"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        metrics.record_approval_decision.assert_called_once_with(
            decision='approved',
            risk_band='high',
            is_destructive=True
        )
        metrics.observe_approval_processing_duration.assert_called_once()


class TestApprovalProcessorRejected:
    """Testes para processamento de planos rejeitados"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
        client.update_plan_approval_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer"""
        producer = MagicMock()
        producer.send_plan = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.fixture
    def sample_ledger_entry(self):
        """Entrada de ledger de exemplo"""
        return {
            'plan_id': 'plan-789',
            'intent_id': 'intent-abc',
            'timestamp': datetime.utcnow() - timedelta(minutes=30),
            'plan_data': {
                'plan_id': 'plan-789',
                'approval_status': 'pending',
                'risk_band': 'critical',
                'is_destructive': True
            }
        }

    @pytest.mark.asyncio
    async def test_process_rejected_plan_updates_ledger(
        self, processor, mongodb_client, sample_ledger_entry
    ):
        """Rejeição deve atualizar status no ledger com motivo"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-789',
            'intent_id': 'intent-abc',
            'decision': 'rejected',
            'approved_by': 'security@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': 'Operação muito arriscada para produção'
        }

        await processor.process_approval_response(approval_response, {})

        mongodb_client.update_plan_approval_status.assert_called_once()
        call_args = mongodb_client.update_plan_approval_status.call_args
        assert call_args.kwargs['plan_id'] == 'plan-789'
        assert call_args.kwargs['approval_status'] == 'rejected'
        assert call_args.kwargs['rejection_reason'] == 'Operação muito arriscada para produção'

    @pytest.mark.asyncio
    async def test_process_rejected_plan_does_not_publish(
        self, processor, mongodb_client, plan_producer, sample_ledger_entry
    ):
        """Rejeição NÃO deve publicar plano no Kafka"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-789',
            'intent_id': 'intent-abc',
            'decision': 'rejected',
            'approved_by': 'security@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': 'Risco muito alto'
        }

        await processor.process_approval_response(approval_response, {})

        plan_producer.send_plan.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_rejected_plan_records_metrics(
        self, processor, mongodb_client, metrics, sample_ledger_entry
    ):
        """Rejeição deve registrar métricas"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-789',
            'intent_id': 'intent-abc',
            'decision': 'rejected',
            'approved_by': 'security@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        metrics.record_approval_decision.assert_called_once_with(
            decision='rejected',
            risk_band='critical',
            is_destructive=True
        )


class TestApprovalProcessorIdempotency:
    """Testes para idempotência do processamento"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
        client.update_plan_approval_status = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def plan_producer(self):
        """Mock plan producer"""
        producer = MagicMock()
        producer.send_plan = AsyncMock()
        return producer

    @pytest.fixture
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.mark.asyncio
    async def test_already_approved_plan_is_skipped(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano já aprovado com saga_state='completed' deve ser ignorado"""
        ledger_entry = {
            'plan_id': 'plan-dup',
            'plan_data': {
                'approval_status': 'approved',  # Já aprovado
                'saga_state': 'completed'  # Saga completada com sucesso
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-dup',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Não deve atualizar ledger nem publicar
        mongodb_client.update_plan_approval_status.assert_not_called()
        plan_producer.send_plan.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_rejected_plan_is_skipped(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano já rejeitado deve ser ignorado"""
        ledger_entry = {
            'plan_id': 'plan-dup',
            'plan_data': {
                'approval_status': 'rejected'  # Já rejeitado
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-dup',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        mongodb_client.update_plan_approval_status.assert_not_called()
        plan_producer.send_plan.assert_not_called()


class TestApprovalProcessorErrorHandling:
    """Testes para tratamento de erros"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
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
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.mark.asyncio
    async def test_plan_not_found_in_ledger(
        self, processor, mongodb_client, metrics
    ):
        """Plano não encontrado deve ser ignorado e registrar erro"""
        mongodb_client.query_ledger.return_value = None

        approval_response = {
            'plan_id': 'plan-nonexistent',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        # Não deve lançar exceção
        await processor.process_approval_response(approval_response, {})

        metrics.increment_approval_ledger_error.assert_called_once_with('plan_not_found')

    @pytest.mark.asyncio
    async def test_missing_required_fields(
        self, processor, mongodb_client
    ):
        """Campos obrigatórios ausentes devem ser ignorados"""
        approval_response = {
            'plan_id': None,  # Inválido
            'decision': None  # Inválido
        }

        # Não deve lançar exceção
        await processor.process_approval_response(approval_response, {})

        mongodb_client.query_ledger.assert_not_called()

    @pytest.mark.asyncio
    async def test_ledger_update_failure_raises(
        self, processor, mongodb_client, metrics
    ):
        """Falha ao atualizar ledger na saga deve propagar exceção"""
        ledger_entry = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-x',
            'timestamp': datetime.utcnow(),
            'plan_data': {
                'plan_id': 'plan-123',
                'intent_id': 'intent-x',
                'version': '1.0.0',
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': False,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.5,
                'complexity_score': 0.3,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test',
                'original_domain': 'test',
                'original_priority': 'high',
                'original_security_level': 'internal'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry
        # Saga falha ao iniciar quando ledger não é atualizado
        mongodb_client.update_plan_approval_status.return_value = False

        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        with pytest.raises(RuntimeError):
            await processor.process_approval_response(approval_response, {})


class TestApprovalProcessorTimeToDecision:
    """Testes para cálculo de tempo até decisão"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
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
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.mark.asyncio
    async def test_time_to_decision_calculated(
        self, processor, mongodb_client, metrics
    ):
        """Tempo até decisão deve ser calculado e registrado"""
        # Usar timestamp fixo para controlar o cálculo
        import time
        plan_created_ts = time.time() - 3600  # 1 hora atrás
        plan_created = datetime.utcfromtimestamp(plan_created_ts)
        approved_at_ts = int(time.time() * 1000)  # agora em milissegundos

        ledger_entry = {
            'plan_id': 'plan-123',
            'timestamp': plan_created,
            'plan_data': {
                'plan_id': 'plan-123',
                'intent_id': 'intent-456',
                'version': '1.0.0',
                'approval_status': 'pending',
                'risk_band': 'medium',
                'is_destructive': False,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.5,
                'complexity_score': 0.3,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test',
                'original_domain': 'test',
                'original_priority': 'medium',
                'original_security_level': 'internal'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': approved_at_ts
        }

        await processor.process_approval_response(approval_response, {})

        metrics.observe_approval_time_to_decision.assert_called_once()
        call_args = metrics.observe_approval_time_to_decision.call_args
        duration = call_args.kwargs['duration']

        # Deve ser aproximadamente 1 hora (3600 segundos) com margem de 100s
        assert 3500 <= duration <= 3700
        assert call_args.kwargs['decision'] == 'approved'


class TestApprovalProcessorRetry:
    """Testes para mecanismo de retry na republicação de planos aprovados"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
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
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.fixture
    def sample_ledger_entry(self):
        """Entrada de ledger de exemplo com dados completos"""
        return {
            'plan_id': 'plan-retry-123',
            'intent_id': 'intent-retry-456',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-retry-123',
                'intent_id': 'intent-retry-456',
                'version': '1.0.0',
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': True,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.8,
                'complexity_score': 0.5,
                'explainability_token': 'exp-token',
                'reasoning_summary': 'Test summary',
                'original_domain': 'test',
                'original_priority': 'high',
                'original_security_level': 'confidential'
            }
        }

    @pytest.mark.asyncio
    async def test_republish_succeeds_on_first_attempt(
        self, processor, mongodb_client, plan_producer, metrics, sample_ledger_entry
    ):
        """Republicação bem-sucedida na primeira tentativa não gera erro"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-retry-123',
            'intent_id': 'intent-retry-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        plan_producer.send_plan.assert_called_once()
        metrics.increment_approval_ledger_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_republish_succeeds_after_transient_failure(
        self, processor, mongodb_client, plan_producer, metrics, sample_ledger_entry
    ):
        """Republicação bem-sucedida após falhas transientes"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        # Falha 2 vezes e depois sucesso
        plan_producer.send_plan.side_effect = [
            Exception('Kafka timeout'),
            Exception('Network error'),
            None  # Sucesso na terceira tentativa
        ]

        approval_response = {
            'plan_id': 'plan-retry-123',
            'intent_id': 'intent-retry-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        # Patch para acelerar os testes (sem esperar backoff real)
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            await processor.process_approval_response(approval_response, {})

        assert plan_producer.send_plan.call_count == 3
        # Saga chama ledger 2 vezes: executing e completed
        assert mongodb_client.update_plan_approval_status.call_count == 2
        # Não deve registrar erro de retry esgotado
        assert not any(
            call[0][0] == 'republish_failed_after_retries'
            for call in metrics.increment_approval_ledger_error.call_args_list
        )

    @pytest.mark.asyncio
    async def test_republish_fails_after_max_retries(
        self, processor, mongodb_client, plan_producer, metrics, sample_ledger_entry
    ):
        """Falha após esgotar todas as tentativas de retry aciona compensação"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        # Sempre falha
        plan_producer.send_plan.side_effect = Exception('Persistent Kafka error')

        approval_response = {
            'plan_id': 'plan-retry-123',
            'intent_id': 'intent-retry-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        # Patch para acelerar os testes (sem esperar backoff real)
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(Exception):
                await processor.process_approval_response(approval_response, {})

        # Deve tentar 3 vezes
        assert plan_producer.send_plan.call_count == 3
        # Saga deve executar compensação
        metrics.record_saga_compensation.assert_called_once_with(
            reason='kafka_publish_failed',
            risk_band='high'
        )

    @pytest.mark.asyncio
    async def test_retry_preserves_plan_data(
        self, processor, mongodb_client, plan_producer, metrics, sample_ledger_entry
    ):
        """Dados do plano são preservados em todas as tentativas de retry da saga"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        # Capturar argumentos de todas as chamadas
        captured_plans = []

        async def capture_plan(plan):
            captured_plans.append(plan)
            if len(captured_plans) < 2:
                raise Exception('Transient error')

        plan_producer.send_plan.side_effect = capture_plan

        approval_response = {
            'plan_id': 'plan-retry-123',
            'intent_id': 'intent-retry-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        # Patch para acelerar os testes (saga usa wait_exponential)
        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            await processor.process_approval_response(approval_response, {})

        # Verificar que todas as tentativas receberam o mesmo plano
        assert len(captured_plans) == 2
        for plan in captured_plans:
            assert plan.plan_id == 'plan-retry-123'
            # approval_status pode ser enum ou string dependendo do modelo
            status = plan.approval_status
            if hasattr(status, 'value'):
                status = status.value
            assert status == 'approved'
            assert plan.approved_by == 'admin@example.com'


class TestApprovalProcessorDLQ:
    """Testes para Dead Letter Queue de aprovações"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
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
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.record_saga_compensation = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics, dlq_producer):
        """Create ApprovalProcessor instance with DLQ producer"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(
            mongodb_client, plan_producer, metrics,
            rejection_notifier=None,
            dlq_producer=dlq_producer
        )

    @pytest.fixture
    def sample_ledger_entry(self):
        """Entrada de ledger de exemplo com dados completos"""
        return {
            'plan_id': 'plan-dlq-123',
            'intent_id': 'intent-dlq-456',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-dlq-123',
                'intent_id': 'intent-dlq-456',
                'version': '1.0.0',
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': True,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.8,
                'complexity_score': 0.5,
                'explainability_token': 'exp-token',
                'reasoning_summary': 'Test summary',
                'original_domain': 'test',
                'original_priority': 'high',
                'original_security_level': 'confidential'
            }
        }

    @pytest.mark.asyncio
    async def test_dlq_entry_sent_after_max_retries(
        self, processor, mongodb_client, plan_producer, dlq_producer, metrics, sample_ledger_entry
    ):
        """Plano deve ser enviado para DLQ após esgotar retries via saga"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        # Sempre falha na publicação
        plan_producer.send_plan.side_effect = Exception('Persistent Kafka error')

        approval_response = {
            'plan_id': 'plan-dlq-123',
            'intent_id': 'intent-dlq-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        trace_context = {
            'correlation_id': 'corr-dlq-789',
            'trace_id': 'trace-dlq-001',
            'span_id': 'span-dlq-002'
        }

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(Exception):
                await processor.process_approval_response(approval_response, trace_context)

        # Verificar que DLQ foi chamado
        dlq_producer.send_dlq_entry.assert_called_once()

        # Verificar conteúdo do DLQ entry
        dlq_entry = dlq_producer.send_dlq_entry.call_args[0][0]
        assert dlq_entry.plan_id == 'plan-dlq-123'
        assert dlq_entry.intent_id == 'intent-dlq-456'
        assert dlq_entry.retry_count == 3
        assert dlq_entry.correlation_id == 'corr-dlq-789'
        assert dlq_entry.trace_id == 'trace-dlq-001'
        assert dlq_entry.span_id == 'span-dlq-002'
        assert dlq_entry.approved_by == 'admin@example.com'
        assert dlq_entry.risk_band == 'high'
        assert dlq_entry.is_destructive is True

    @pytest.mark.asyncio
    async def test_dlq_metric_incremented_on_failure(
        self, processor, mongodb_client, plan_producer, dlq_producer, metrics, sample_ledger_entry
    ):
        """Métrica DLQ deve ser incrementada quando saga envia mensagem para DLQ"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry
        plan_producer.send_plan.side_effect = Exception('Kafka error')

        approval_response = {
            'plan_id': 'plan-dlq-123',
            'intent_id': 'intent-dlq-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(Exception):
                await processor.process_approval_response(approval_response, {})

        # Saga usa 'saga_compensation' como reason
        metrics.increment_approval_dlq_messages.assert_called_once_with(
            reason='saga_compensation',
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    async def test_dlq_not_configured_does_not_crash(
        self, mongodb_client, plan_producer, metrics, sample_ledger_entry
    ):
        """Processador sem DLQ configurado não deve crashar - saga executa compensação"""
        from src.services.approval_processor import ApprovalProcessor

        # Criar processor sem DLQ
        processor_no_dlq = ApprovalProcessor(
            mongodb_client, plan_producer, metrics,
            rejection_notifier=None,
            dlq_producer=None  # Sem DLQ
        )

        mongodb_client.query_ledger.return_value = sample_ledger_entry
        plan_producer.send_plan.side_effect = Exception('Kafka error')

        approval_response = {
            'plan_id': 'plan-dlq-123',
            'intent_id': 'intent-dlq-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(Exception):
                await processor_no_dlq.process_approval_response(approval_response, {})

        # Saga deve registrar compensação mesmo sem DLQ
        metrics.record_saga_compensation.assert_called_once_with(
            reason='kafka_publish_failed',
            risk_band='high'
        )

    @pytest.mark.asyncio
    async def test_dlq_failure_does_not_block_processing(
        self, processor, mongodb_client, plan_producer, dlq_producer, metrics, sample_ledger_entry
    ):
        """Falha no envio para DLQ não deve bloquear compensação da saga"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry
        plan_producer.send_plan.side_effect = Exception('Kafka error')
        dlq_producer.send_dlq_entry.side_effect = Exception('DLQ also failed')

        approval_response = {
            'plan_id': 'plan-dlq-123',
            'intent_id': 'intent-dlq-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(Exception) as exc_info:
                await processor.process_approval_response(approval_response, {})

        # A exceção original (RetryError) deve ser propagada, não a falha do DLQ
        assert 'Kafka error' in str(exc_info.value) or 'RetryError' in str(exc_info.value.__class__.__name__)

    @pytest.mark.asyncio
    async def test_dlq_entry_contains_original_approval_response(
        self, processor, mongodb_client, plan_producer, dlq_producer, metrics, sample_ledger_entry
    ):
        """DLQ entry da saga deve conter dados de compensação"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry
        plan_producer.send_plan.side_effect = Exception('Kafka error')

        approval_response = {
            'plan_id': 'plan-dlq-123',
            'intent_id': 'intent-dlq-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        with patch('src.sagas.approval_saga.wait_exponential', return_value=lambda x: 0):
            with pytest.raises(Exception):
                await processor.process_approval_response(approval_response, {})

        dlq_entry = dlq_producer.send_dlq_entry.call_args[0][0]

        # Saga inclui dados de compensação no original_approval_response
        assert dlq_entry.original_approval_response['plan_id'] == 'plan-dlq-123'
        assert dlq_entry.original_approval_response['decision'] == 'approved'
        assert 'cognitive_plan' in dlq_entry.original_approval_response
        assert 'saga_compensation_executed' in dlq_entry.original_approval_response


class TestApprovalProcessorIdempotencyWithSagaState:
    """Testes para idempotência com saga_state - Comment 1"""

    @pytest.fixture
    def mongodb_client(self):
        """Mock MongoDB client"""
        client = MagicMock()
        client.query_ledger = AsyncMock()
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
    def metrics(self):
        """Mock metrics"""
        m = MagicMock()
        m.record_approval_decision = MagicMock()
        m.observe_approval_processing_duration = MagicMock()
        m.observe_approval_time_to_decision = MagicMock()
        m.increment_approval_ledger_error = MagicMock()
        m.observe_saga_duration = MagicMock()
        m.record_saga_compensation = MagicMock()
        m.increment_approval_dlq_messages = MagicMock()
        return m

    @pytest.fixture
    def processor(self, mongodb_client, plan_producer, metrics):
        """Create ApprovalProcessor instance"""
        from src.services.approval_processor import ApprovalProcessor
        return ApprovalProcessor(mongodb_client, plan_producer, metrics)

    @pytest.mark.asyncio
    async def test_approved_with_saga_completed_is_skipped(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano approved com saga_state=completed deve ser ignorado"""
        ledger_entry = {
            'plan_id': 'plan-completed',
            'plan_data': {
                'approval_status': 'approved',
                'saga_state': 'completed'  # Saga já finalizou
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-completed',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Não deve atualizar ledger nem publicar
        mongodb_client.update_plan_approval_status.assert_not_called()
        plan_producer.send_plan.assert_not_called()

    @pytest.mark.asyncio
    async def test_approved_with_saga_executing_is_reprocessed(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano approved com saga_state=executing deve ser reprocessado (crash recovery)"""
        ledger_entry = {
            'plan_id': 'plan-executing',
            'intent_id': 'intent-crash',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-executing',
                'intent_id': 'intent-crash',
                'version': '1.0.0',
                'approval_status': 'approved',
                'saga_state': 'executing',  # Crash aconteceu durante execução
                'risk_band': 'high',
                'is_destructive': True,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.8,
                'complexity_score': 0.5,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test',
                'original_domain': 'test',
                'original_priority': 'high',
                'original_security_level': 'confidential'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-executing',
            'intent_id': 'intent-crash',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Deve continuar com a saga (atualizar ledger e publicar)
        mongodb_client.update_plan_approval_status.assert_called()
        plan_producer.send_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_approved_with_saga_compensated_is_reprocessed(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano approved com saga_state=compensated deve ser reprocessado"""
        ledger_entry = {
            'plan_id': 'plan-compensated',
            'intent_id': 'intent-retry',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-compensated',
                'intent_id': 'intent-retry',
                'version': '1.0.0',
                'approval_status': 'approved',
                'saga_state': 'compensated',  # Compensação foi executada, pode retentar
                'risk_band': 'medium',
                'is_destructive': False,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.5,
                'complexity_score': 0.3,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test',
                'original_domain': 'test',
                'original_priority': 'medium',
                'original_security_level': 'internal'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-compensated',
            'intent_id': 'intent-retry',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Deve continuar com a saga
        mongodb_client.update_plan_approval_status.assert_called()
        plan_producer.send_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_approved_with_saga_failed_is_reprocessed(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano approved com saga_state=failed deve ser reprocessado"""
        ledger_entry = {
            'plan_id': 'plan-failed',
            'intent_id': 'intent-retry',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-failed',
                'intent_id': 'intent-retry',
                'version': '1.0.0',
                'approval_status': 'approved',
                'saga_state': 'failed',  # Saga falhou, pode retentar
                'risk_band': 'low',
                'is_destructive': False,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.3,
                'complexity_score': 0.2,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test',
                'original_domain': 'test',
                'original_priority': 'low',
                'original_security_level': 'public'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-failed',
            'intent_id': 'intent-retry',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Deve continuar com a saga
        mongodb_client.update_plan_approval_status.assert_called()
        plan_producer.send_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_approved_with_no_saga_state_is_reprocessed(
        self, processor, mongodb_client, plan_producer
    ):
        """Plano approved sem saga_state (legacy) deve ser reprocessado"""
        ledger_entry = {
            'plan_id': 'plan-legacy',
            'intent_id': 'intent-legacy',
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'plan_data': {
                'plan_id': 'plan-legacy',
                'intent_id': 'intent-legacy',
                'version': '1.0.0',
                'approval_status': 'approved',
                # Sem saga_state - dados legados ou crash antes de definir
                'risk_band': 'medium',
                'is_destructive': False,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.5,
                'complexity_score': 0.3,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test',
                'original_domain': 'test',
                'original_priority': 'medium',
                'original_security_level': 'internal'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        approval_response = {
            'plan_id': 'plan-legacy',
            'intent_id': 'intent-legacy',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Deve continuar com a saga
        mongodb_client.update_plan_approval_status.assert_called()
        plan_producer.send_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_crash_after_executing_before_publish_recovery(
        self, processor, mongodb_client, plan_producer, metrics
    ):
        """
        Simula crash após setar saga_state='executing' mas antes de publicar.
        Reprocessamento deve executar saga e tentar publicar.
        """
        # Estado do ledger após crash: approved + executing
        ledger_entry = {
            'plan_id': 'plan-crash-001',
            'intent_id': 'intent-crash-001',
            'timestamp': datetime.utcnow() - timedelta(minutes=30),
            'plan_data': {
                'plan_id': 'plan-crash-001',
                'intent_id': 'intent-crash-001',
                'version': '1.0.0',
                'approval_status': 'approved',
                'saga_state': 'executing',  # Crash ocorreu aqui
                'approved_by': 'original-admin',
                'approved_at': datetime.utcnow() - timedelta(minutes=30),
                'risk_band': 'high',
                'is_destructive': True,
                'tasks': [],
                'execution_order': [],
                'risk_score': 0.8,
                'complexity_score': 0.5,
                'explainability_token': 'exp',
                'reasoning_summary': 'Test crash recovery',
                'original_domain': 'test',
                'original_priority': 'high',
                'original_security_level': 'confidential'
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry

        # Mensagem reprocessada (ex: do DLQ)
        approval_response = {
            'plan_id': 'plan-crash-001',
            'intent_id': 'intent-crash-001',
            'decision': 'approved',
            'approved_by': 'original-admin',
            'approved_at': int((datetime.utcnow() - timedelta(minutes=30)).timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        # Deve ter executado a saga completa
        # Saga chama update 2 vezes: executing (reinicia) e completed
        assert mongodb_client.update_plan_approval_status.call_count == 2
        plan_producer.send_plan.assert_called_once()

        # Verificar que saga completou
        calls = mongodb_client.update_plan_approval_status.call_args_list
        assert calls[1].kwargs['saga_state'] == 'completed'
