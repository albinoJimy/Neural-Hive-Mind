"""
Testes de integracao para endpoint de republicacao
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from src.config.settings import Settings
from src.models.approval import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    RiskBand
)
from src.services.approval_service import ApprovalService


class TestRepublishEndpointIntegration:
    """Testes de integracao para republicacao"""

    @pytest.fixture
    def approved_plan_storage(self, sample_cognitive_plan):
        """Storage com plano ja aprovado"""
        approval = ApprovalRequest(
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
        return {'plan-001': approval}

    @pytest.fixture
    def mock_mongodb_client_with_approved(self, approved_plan_storage):
        """MongoDB client com plano aprovado"""
        async def get_by_plan_id(plan_id):
            return approved_plan_storage.get(plan_id)

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(side_effect=get_by_plan_id)
        return client

    @pytest.fixture
    def mock_producer_with_capture(self):
        """Producer que captura mensagens republicadas"""
        messages = []

        async def send_response(response, **kwargs):
            messages.append(response)

        producer = MagicMock()
        producer.send_approval_response = AsyncMock(side_effect=send_response)
        producer._messages = messages
        return producer

    @pytest.fixture
    def approval_service(
        self,
        mock_settings,
        mock_mongodb_client_with_approved,
        mock_producer_with_capture,
        mock_metrics
    ):
        """Service configurado para testes de republicacao"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client_with_approved,
            response_producer=mock_producer_with_capture,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_republish_approved_plan_success(
        self,
        approval_service,
        mock_producer_with_capture
    ):
        """Teste republicacao de plano aprovado"""
        response = await approval_service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin@test.com',
            force=False,
            comments='Reprocessando apos falha'
        )

        # Verificar resposta
        assert response.plan_id == 'plan-001'
        assert response.intent_id == 'intent-001'
        assert response.decision == 'approved'
        assert response.approved_by == 'original-admin@test.com'
        assert response.cognitive_plan is not None

        # Verificar que mensagem foi publicada
        assert len(mock_producer_with_capture._messages) == 1
        kafka_msg = mock_producer_with_capture._messages[0]
        assert kafka_msg.plan_id == 'plan-001'
        assert kafka_msg.decision == 'approved'

    @pytest.mark.asyncio
    async def test_republish_pending_plan_without_force(
        self,
        mock_settings,
        mock_producer_with_capture,
        mock_metrics,
        sample_approval_request
    ):
        """Teste republicacao de plano pendente sem force"""
        # Setup: plano pendente
        sample_approval_request.status = ApprovalStatus.PENDING

        async def get_pending(plan_id):
            return sample_approval_request

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(side_effect=get_pending)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer_with_capture,
            metrics=mock_metrics
        )

        # Deve falhar
        with pytest.raises(ValueError) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-001',
                user_id='admin@test.com',
                force=False
            )

        assert 'nao esta aprovado' in str(exc_info.value)
        assert 'Use force=true' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_republish_pending_plan_with_force(
        self,
        mock_settings,
        mock_producer_with_capture,
        mock_metrics,
        sample_approval_request,
        sample_cognitive_plan
    ):
        """Teste republicacao forcada de plano pendente"""
        # Setup: plano pendente mas com cognitive_plan
        sample_approval_request.status = ApprovalStatus.PENDING
        sample_approval_request.cognitive_plan = sample_cognitive_plan

        async def get_pending(plan_id):
            return sample_approval_request

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(side_effect=get_pending)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer_with_capture,
            metrics=mock_metrics
        )

        # Deve funcionar com force=True
        response = await service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin@test.com',
            force=True,
            comments='Republicacao forcada'
        )

        assert response.plan_id == 'plan-001'
        assert len(mock_producer_with_capture._messages) == 1

    @pytest.mark.asyncio
    async def test_republish_plan_not_found(
        self,
        mock_settings,
        mock_producer_with_capture,
        mock_metrics
    ):
        """Teste republicacao de plano inexistente"""
        async def get_none(plan_id):
            return None

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(side_effect=get_none)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer_with_capture,
            metrics=mock_metrics
        )

        with pytest.raises(ValueError) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-999',
                user_id='admin@test.com'
            )

        assert 'nao encontrado' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_republish_plan_without_cognitive_plan(
        self,
        mock_settings,
        mock_producer_with_capture,
        mock_metrics
    ):
        """Teste republicacao de plano sem cognitive_plan (vazio/falsy)"""
        # Simula um approval com cognitive_plan None retornado pelo mock
        # Como o modelo requer cognitive_plan como dict, mockamos diretamente
        approval = MagicMock()
        approval.status = ApprovalStatus.APPROVED
        approval.cognitive_plan = None  # Simula ausencia de cognitive_plan
        approval.approved_by = 'admin@test.com'
        approval.approved_at = datetime.utcnow()
        approval.intent_id = 'intent-001'

        async def get_without_plan(plan_id):
            return approval

        client = MagicMock()
        client.get_approval_by_plan_id = AsyncMock(side_effect=get_without_plan)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=client,
            response_producer=mock_producer_with_capture,
            metrics=mock_metrics
        )

        with pytest.raises(ValueError) as exc_info:
            await service.republish_approved_plan(
                plan_id='plan-001',
                user_id='admin@test.com'
            )

        assert 'nao possui cognitive_plan' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_republish_multiple_times(
        self,
        approval_service,
        mock_producer_with_capture
    ):
        """Teste republicacao multipla do mesmo plano"""
        # Primeira republicacao
        await approval_service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin1@test.com'
        )

        # Segunda republicacao
        await approval_service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin2@test.com'
        )

        # Terceira republicacao
        await approval_service.republish_approved_plan(
            plan_id='plan-001',
            user_id='admin3@test.com'
        )

        # Verificar que 3 mensagens foram publicadas
        assert len(mock_producer_with_capture._messages) == 3

        # Todas devem ter mesmo plan_id
        for msg in mock_producer_with_capture._messages:
            assert msg.plan_id == 'plan-001'
            assert msg.decision == 'approved'
