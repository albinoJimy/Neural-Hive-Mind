"""
Testes unitários para ApprovalProcessor

Testa processamento de aprovações/rejeições, atualização de ledger,
publicação de planos aprovados e métricas.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch


class TestApprovalProcessorApproved:
    """Testes para processamento de planos aprovados"""

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
        """Aprovação deve atualizar status no ledger"""
        mongodb_client.query_ledger.return_value = sample_ledger_entry

        approval_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'decision': 'approved',
            'approved_by': 'admin@example.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        mongodb_client.update_plan_approval_status.assert_called_once()
        call_args = mongodb_client.update_plan_approval_status.call_args
        assert call_args.kwargs['plan_id'] == 'plan-123'
        assert call_args.kwargs['approval_status'] == 'approved'
        assert call_args.kwargs['approved_by'] == 'admin@example.com'

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
        """Plano já aprovado deve ser ignorado"""
        ledger_entry = {
            'plan_id': 'plan-dup',
            'plan_data': {
                'approval_status': 'approved'  # Já aprovado
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
        """Falha ao atualizar ledger deve propagar exceção"""
        ledger_entry = {
            'plan_id': 'plan-123',
            'timestamp': datetime.utcnow(),
            'plan_data': {
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': False
            }
        }
        mongodb_client.query_ledger.return_value = ledger_entry
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
    async def test_time_to_decision_calculated(
        self, processor, mongodb_client, metrics
    ):
        """Tempo até decisão deve ser calculado corretamente"""
        plan_created = datetime.utcnow() - timedelta(hours=2)
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
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        await processor.process_approval_response(approval_response, {})

        metrics.observe_approval_time_to_decision.assert_called_once()
        call_args = metrics.observe_approval_time_to_decision.call_args
        duration = call_args.kwargs['duration']

        # Deve ser aproximadamente 2 horas (7200 segundos)
        assert 7100 <= duration <= 7400
        assert call_args.kwargs['decision'] == 'approved'
