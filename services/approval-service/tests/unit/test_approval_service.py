"""
Testes unitarios para ApprovalService

Testa logica de negocio para aprovacao/rejeicao de planos cognitivos.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from pymongo.errors import DuplicateKeyError

from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
    RiskBand
)
from src.services.approval_service import ApprovalService


class TestApprovalServiceProcessRequest:
    """Testes para processamento de requests de aprovacao"""

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Cria instancia de ApprovalService para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_process_approval_request_success(
        self, approval_service, sample_approval_request, mock_mongodb_client, mock_metrics
    ):
        """Teste de processamento bem-sucedido de request com ApprovalRequest"""
        result = await approval_service.process_approval_request(sample_approval_request)

        assert isinstance(result, ApprovalRequest)
        assert result.plan_id == sample_approval_request.plan_id
        assert result.intent_id == sample_approval_request.intent_id
        assert result.risk_score == sample_approval_request.risk_score
        assert result.status == ApprovalStatus.PENDING

        mock_mongodb_client.save_approval_request.assert_called_once_with(sample_approval_request)
        mock_metrics.increment_approval_requests_received.assert_called_once()
        mock_metrics.update_pending_gauge.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_approval_request_missing_plan_id(
        self, approval_service
    ):
        """Teste com plan_id ausente"""
        invalid_request = ApprovalRequest(
            plan_id='',
            intent_id='intent-001',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            cognitive_plan={}
        )

        with pytest.raises(ValueError) as exc_info:
            await approval_service.process_approval_request(invalid_request)

        assert 'plan_id' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_approval_request_missing_intent_id(
        self, approval_service
    ):
        """Teste com intent_id ausente"""
        invalid_request = ApprovalRequest(
            plan_id='plan-001',
            intent_id='',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            cognitive_plan={}
        )

        with pytest.raises(ValueError) as exc_info:
            await approval_service.process_approval_request(invalid_request)

        assert 'intent_id' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_approval_request_duplicate_plan(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Teste com plan_id duplicado"""
        mock_mongodb_client.save_approval_request.side_effect = DuplicateKeyError(
            'Duplicate key error'
        )

        with pytest.raises(DuplicateKeyError):
            await approval_service.process_approval_request(sample_approval_request)

    @pytest.mark.asyncio
    async def test_process_approval_request_with_defaults(
        self, approval_service, mock_mongodb_client
    ):
        """Teste ApprovalRequest com valores padrao"""
        minimal_request = ApprovalRequest(
            plan_id='plan-002',
            intent_id='intent-002',
            risk_score=0.0,
            risk_band=RiskBand.LOW,
            is_destructive=False,
            cognitive_plan={'plan_id': 'plan-002', 'intent_id': 'intent-002'}
        )

        result = await approval_service.process_approval_request(minimal_request)

        assert result.risk_score == 0.0
        assert result.is_destructive == False
        assert result.destructive_tasks == []


class TestApprovalServiceApprovePlan:
    """Testes para aprovacao de planos"""

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Cria instancia de ApprovalService para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_approve_plan_success(
        self, approval_service, sample_approval_request,
        mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Teste de aprovacao bem-sucedida"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        result = await approval_service.approve_plan(
            plan_id='plan-001',
            user_id='admin@example.com',
            comments='Aprovado'
        )

        assert isinstance(result, ApprovalDecision)
        assert result.plan_id == 'plan-001'
        assert result.decision == 'approved'
        assert result.approved_by == 'admin@example.com'
        assert result.comments == 'Aprovado'

        mock_mongodb_client.update_approval_decision.assert_called_once()
        mock_response_producer.send_approval_response.assert_called_once()
        mock_metrics.increment_approvals_total.assert_called_once_with(
            'approved', sample_approval_request.risk_band
        )

    @pytest.mark.asyncio
    async def test_approve_plan_not_found(
        self, approval_service, mock_mongodb_client
    ):
        """Teste com plano nao encontrado"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = None

        with pytest.raises(ValueError) as exc_info:
            await approval_service.approve_plan(
                plan_id='plan-999',
                user_id='admin@example.com'
            )

        assert 'nao encontrado' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_approve_plan_already_approved(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Teste com plano ja aprovado"""
        sample_approval_request.status = ApprovalStatus.APPROVED
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        with pytest.raises(ValueError) as exc_info:
            await approval_service.approve_plan(
                plan_id='plan-001',
                user_id='admin@example.com'
            )

        assert 'nao esta pendente' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_approve_plan_update_fails(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Teste quando atualizacao no MongoDB falha"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_mongodb_client.update_approval_decision.return_value = False

        with pytest.raises(ValueError) as exc_info:
            await approval_service.approve_plan(
                plan_id='plan-001',
                user_id='admin@example.com'
            )

        assert 'Falha ao atualizar' in str(exc_info.value)


class TestApprovalServiceRejectPlan:
    """Testes para rejeicao de planos"""

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Cria instancia de ApprovalService para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_reject_plan_success(
        self, approval_service, sample_approval_request,
        mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Teste de rejeicao bem-sucedida"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        result = await approval_service.reject_plan(
            plan_id='plan-001',
            user_id='admin@example.com',
            reason='Risco muito alto sem justificativa',
            comments='Necessita revisao adicional'
        )

        assert isinstance(result, ApprovalDecision)
        assert result.plan_id == 'plan-001'
        assert result.decision == 'rejected'
        assert result.approved_by == 'admin@example.com'
        assert result.rejection_reason == 'Risco muito alto sem justificativa'

        mock_mongodb_client.update_approval_decision.assert_called_once()
        mock_response_producer.send_approval_response.assert_called_once()
        mock_metrics.increment_approvals_total.assert_called_once_with(
            'rejected', sample_approval_request.risk_band
        )

    @pytest.mark.asyncio
    async def test_reject_plan_empty_reason(
        self, approval_service
    ):
        """Teste com motivo da rejeicao vazio"""
        with pytest.raises(ValueError) as exc_info:
            await approval_service.reject_plan(
                plan_id='plan-001',
                user_id='admin@example.com',
                reason='',
                comments=None
            )

        assert 'obrigatorio' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reject_plan_whitespace_reason(
        self, approval_service
    ):
        """Teste com motivo contendo apenas espacos"""
        with pytest.raises(ValueError) as exc_info:
            await approval_service.reject_plan(
                plan_id='plan-001',
                user_id='admin@example.com',
                reason='   ',
                comments=None
            )

        assert 'obrigatorio' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reject_plan_not_found(
        self, approval_service, mock_mongodb_client
    ):
        """Teste com plano nao encontrado"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = None

        with pytest.raises(ValueError) as exc_info:
            await approval_service.reject_plan(
                plan_id='plan-999',
                user_id='admin@example.com',
                reason='Motivo'
            )

        assert 'nao encontrado' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reject_plan_already_rejected(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Teste com plano ja rejeitado"""
        sample_approval_request.status = ApprovalStatus.REJECTED
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        with pytest.raises(ValueError) as exc_info:
            await approval_service.reject_plan(
                plan_id='plan-001',
                user_id='admin@example.com',
                reason='Motivo'
            )

        assert 'nao esta pendente' in str(exc_info.value)


class TestApprovalServiceQueries:
    """Testes para consultas de aprovacoes"""

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Cria instancia de ApprovalService para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_get_pending_approvals_default(
        self, approval_service, mock_mongodb_client
    ):
        """Teste de listagem de pendentes com parametros padrao"""
        await approval_service.get_pending_approvals()

        mock_mongodb_client.get_pending_approvals.assert_called_once_with(
            limit=50,
            offset=0,
            filters=None
        )

    @pytest.mark.asyncio
    async def test_get_pending_approvals_with_filters(
        self, approval_service, mock_mongodb_client
    ):
        """Teste de listagem com filtros"""
        await approval_service.get_pending_approvals(
            limit=10,
            offset=20,
            risk_band='high',
            is_destructive=True
        )

        mock_mongodb_client.get_pending_approvals.assert_called_once_with(
            limit=10,
            offset=20,
            filters={'risk_band': 'high', 'is_destructive': True}
        )

    @pytest.mark.asyncio
    async def test_get_approval_by_plan_id(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Teste de busca por plan_id"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        result = await approval_service.get_approval_by_plan_id('plan-001')

        assert result == sample_approval_request
        mock_mongodb_client.get_approval_by_plan_id.assert_called_once_with('plan-001')

    @pytest.mark.asyncio
    async def test_get_approval_stats(
        self, approval_service, mock_mongodb_client
    ):
        """Teste de estatisticas"""
        result = await approval_service.get_approval_stats()

        assert result.pending_count == 5
        assert result.approved_count == 100
        assert result.rejected_count == 10
        mock_mongodb_client.get_approval_stats.assert_called_once()
