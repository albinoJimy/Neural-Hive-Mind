"""
Testes de integracao para metricas de republicacao
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from prometheus_client import REGISTRY

from src.config.settings import Settings
from src.models.approval import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    RiskBand
)
from src.services.approval_service import ApprovalService
from src.observability.metrics import (
    NeuralHiveMetrics,
    approval_republish_total,
    approval_republish_failures_total,
    approval_republish_duration_seconds
)


class TestRepublishMetrics:
    """Testes para metricas de republicacao"""

    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        """Reset metrics before each test"""
        # Clear metric samples by re-initializing labels
        for labels in list(approval_republish_total._metrics.keys()):
            approval_republish_total._metrics[labels]._value.set(0)
        for labels in list(approval_republish_failures_total._metrics.keys()):
            approval_republish_failures_total._metrics[labels]._value.set(0)
        yield

    @pytest.fixture
    def mock_settings(self):
        """Mock settings"""
        settings = MagicMock(spec=Settings)
        settings.enable_feedback_collection = False
        return settings

    @pytest.fixture
    def mock_metrics(self):
        """Metricas reais para teste"""
        return NeuralHiveMetrics()

    @pytest.fixture
    def sample_cognitive_plan(self):
        """Plano cognitivo de exemplo"""
        return {
            'plan_id': 'plan-001',
            'intent_id': 'intent-001',
            'tasks': [
                {'task_id': 'task-1', 'action': 'read_file'},
                {'task_id': 'task-2', 'action': 'delete_file'}
            ]
        }

    @pytest.fixture
    def approved_approval_request(self, sample_cognitive_plan):
        """ApprovalRequest ja aprovado"""
        return ApprovalRequest(
            approval_id='approval-001',
            plan_id='plan-001',
            intent_id='intent-001',
            risk_score=0.85,
            risk_band=RiskBand.HIGH,
            is_destructive=True,
            destructive_tasks=['task-2'],
            status=ApprovalStatus.APPROVED,
            approved_by='original-admin@test.com',
            approved_at=datetime.utcnow(),
            cognitive_plan=sample_cognitive_plan
        )

    @pytest.fixture
    def mock_mongodb_with_approval(self, approved_approval_request):
        """MongoDB client com plano aprovado"""
        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(
            return_value=approved_approval_request
        )
        return client

    @pytest.fixture
    def mock_producer(self):
        """Producer mock"""
        producer = MagicMock()
        producer.send_approval_response = AsyncMock()
        return producer

    @pytest.fixture
    def approval_service(
        self,
        mock_settings,
        mock_mongodb_with_approval,
        mock_producer,
        mock_metrics
    ):
        """Service configurado para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_with_approval,
            response_producer=mock_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_republish_success_increments_metrics(
        self,
        approval_service,
        mock_metrics
    ):
        """Teste que republicacao bem-sucedida incrementa metricas"""
        # Executar republicacao
        await approval_service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin@test.com',
            force=False
        )

        # Verificar que metrica de sucesso foi incrementada
        success_metric = approval_republish_total.labels(
            outcome='success',
            force='false'
        )
        assert success_metric._value.get() >= 1

    @pytest.mark.asyncio
    async def test_republish_forced_increments_force_label(
        self,
        mock_settings,
        mock_producer,
        mock_metrics,
        sample_cognitive_plan
    ):
        """Teste que republicacao forcada usa label force=true"""
        # Setup: plano pendente
        pending_request = ApprovalRequest(
            approval_id='approval-002',
            plan_id='plan-002',
            intent_id='intent-002',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            is_destructive=False,
            status=ApprovalStatus.PENDING,
            cognitive_plan=sample_cognitive_plan
        )

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(return_value=pending_request)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer,
            metrics=mock_metrics
        )

        # Executar republicacao forcada
        await service.republish_approved_plan(
            plan_id='plan-002',
            user_id='admin@test.com',
            force=True
        )

        # Verificar que metrica de sucesso com force=true foi incrementada
        forced_metric = approval_republish_total.labels(
            outcome='success',
            force='true'
        )
        assert forced_metric._value.get() >= 1

    @pytest.mark.asyncio
    async def test_republish_not_found_increments_failure_metric(
        self,
        mock_settings,
        mock_producer,
        mock_metrics
    ):
        """Teste que plano nao encontrado incrementa metrica de falha"""
        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(return_value=None)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer,
            metrics=mock_metrics
        )

        # Tentar republicar plano inexistente
        with pytest.raises(ValueError) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-999',
                user_id='admin@test.com'
            )

        assert 'nao encontrado' in str(exc_info.value)

        # Verificar que metrica de falha foi incrementada
        not_found_metric = approval_republish_failures_total.labels(
            failure_reason='not_found'
        )
        assert not_found_metric._value.get() >= 1

    @pytest.mark.asyncio
    async def test_republish_not_approved_increments_failure_metric(
        self,
        mock_settings,
        mock_producer,
        mock_metrics,
        sample_cognitive_plan
    ):
        """Teste que plano nao aprovado incrementa metrica de falha"""
        pending_request = ApprovalRequest(
            approval_id='approval-003',
            plan_id='plan-003',
            intent_id='intent-003',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            is_destructive=False,
            status=ApprovalStatus.PENDING,
            cognitive_plan=sample_cognitive_plan
        )

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(return_value=pending_request)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer,
            metrics=mock_metrics
        )

        # Tentar republicar sem force
        with pytest.raises(ValueError) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-003',
                user_id='admin@test.com',
                force=False
            )

        assert 'nao esta aprovado' in str(exc_info.value)

        # Verificar que metrica de falha foi incrementada
        not_approved_metric = approval_republish_failures_total.labels(
            failure_reason='not_approved'
        )
        assert not_approved_metric._value.get() >= 1

    @pytest.mark.asyncio
    async def test_republish_no_cognitive_plan_increments_failure_metric(
        self,
        mock_settings,
        mock_producer,
        mock_metrics
    ):
        """Teste que plano sem cognitive_plan incrementa metrica de falha"""
        # Simular approval sem cognitive_plan usando MagicMock
        approval = MagicMock()
        approval.status = ApprovalStatus.APPROVED
        approval.cognitive_plan = None
        approval.approved_by = 'admin@test.com'
        approval.approved_at = datetime.utcnow()
        approval.intent_id = 'intent-004'

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(return_value=approval)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer,
            metrics=mock_metrics
        )

        # Tentar republicar
        with pytest.raises(ValueError) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-004',
                user_id='admin@test.com'
            )

        assert 'nao possui cognitive_plan' in str(exc_info.value)

        # Verificar que metrica de falha foi incrementada
        no_plan_metric = approval_republish_failures_total.labels(
            failure_reason='no_cognitive_plan'
        )
        assert no_plan_metric._value.get() >= 1

    @pytest.mark.asyncio
    async def test_republish_kafka_error_increments_failure_metrics(
        self,
        mock_settings,
        mock_mongodb_with_approval,
        mock_metrics
    ):
        """Teste que erro de Kafka incrementa metricas de falha"""
        # Producer que falha
        failing_producer = MagicMock()
        failing_producer.send_approval_response = AsyncMock(
            side_effect=Exception("Kafka connection failed")
        )

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_with_approval,
            response_producer=failing_producer,
            metrics=mock_metrics
        )

        # Tentar republicar
        with pytest.raises(Exception) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-001',
                user_id='admin@test.com'
            )

        assert 'Kafka' in str(exc_info.value)

        # Verificar que metricas de falha foram incrementadas
        kafka_error_metric = approval_republish_failures_total.labels(
            failure_reason='kafka_error'
        )
        assert kafka_error_metric._value.get() >= 1

        failure_metric = approval_republish_total.labels(
            outcome='failure',
            force='false'
        )
        assert failure_metric._value.get() >= 1

    @pytest.mark.asyncio
    async def test_republish_duration_is_observed(
        self,
        approval_service
    ):
        """Teste que duracao da republicacao e registrada"""
        # Executar republicacao
        await approval_service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin@test.com'
        )

        # Verificar que histogram foi observado
        # Histograms em prometheus_client usam _sum para verificar se foi observado
        histogram_sum = approval_republish_duration_seconds._sum.get()
        assert histogram_sum > 0  # Se foi observado, a soma deve ser maior que 0

    @pytest.mark.asyncio
    async def test_multiple_republishes_accumulate_metrics(
        self,
        approval_service,
        mock_metrics
    ):
        """Teste que multiplas republicacoes acumulam nas metricas"""
        # Executar 3 republicacoes
        for _ in range(3):
            await approval_service.republish_approved_plan(
                plan_id='plan-001',
                user_id='admin@test.com'
            )

        # Verificar que metrica acumulou
        success_metric = approval_republish_total.labels(
            outcome='success',
            force='false'
        )
        assert success_metric._value.get() >= 3
