"""
Testes unitarios para API REST do Approval Service

Testa endpoints, autenticacao e validacoes.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStats,
    ApprovalStatus,
    ApprovalResponse,
    RiskBand
)
from src.api.routers.approvals import (
    list_pending_approvals,
    get_approval_stats,
    get_approval,
    approve_plan,
    reject_plan,
    republish_approved_plan
)


class TestListPendingApprovals:
    """Testes para endpoint GET /pending"""

    @pytest.fixture
    def mock_service(self, sample_approval_request):
        """Mock do ApprovalService"""
        service = MagicMock()
        service.get_pending_approvals = AsyncMock(return_value=[sample_approval_request])
        return service

    @pytest.mark.asyncio
    async def test_list_pending_success(
        self, mock_service, admin_user, sample_approval_request
    ):
        """Teste listagem bem-sucedida"""
        result = await list_pending_approvals(
            limit=50,
            offset=0,
            risk_band=None,
            is_destructive=None,
            user=admin_user,
            service=mock_service
        )

        assert len(result) == 1
        assert result[0].plan_id == sample_approval_request.plan_id
        mock_service.get_pending_approvals.assert_called_once_with(
            limit=50,
            offset=0,
            risk_band=None,
            is_destructive=None
        )

    @pytest.mark.asyncio
    async def test_list_pending_with_filters(
        self, mock_service, admin_user
    ):
        """Teste listagem com filtros"""
        await list_pending_approvals(
            limit=10,
            offset=20,
            risk_band=RiskBand.HIGH,
            is_destructive=True,
            user=admin_user,
            service=mock_service
        )

        mock_service.get_pending_approvals.assert_called_once_with(
            limit=10,
            offset=20,
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    async def test_list_pending_empty_list(
        self, admin_user
    ):
        """Teste listagem vazia"""
        mock_service = MagicMock()
        mock_service.get_pending_approvals = AsyncMock(return_value=[])

        result = await list_pending_approvals(
            limit=50,
            offset=0,
            risk_band=None,
            is_destructive=None,
            user=admin_user,
            service=mock_service
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_list_pending_service_error(
        self, admin_user
    ):
        """Teste erro no servico"""
        mock_service = MagicMock()
        mock_service.get_pending_approvals = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await list_pending_approvals(
                limit=50,
                offset=0,
                risk_band=None,
                is_destructive=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 500


class TestGetApproval:
    """Testes para endpoint GET /{plan_id}"""

    @pytest.mark.asyncio
    async def test_get_approval_success(
        self, sample_approval_request, admin_user
    ):
        """Teste busca bem-sucedida"""
        mock_service = MagicMock()
        mock_service.get_approval_by_plan_id = AsyncMock(
            return_value=sample_approval_request
        )

        result = await get_approval(
            plan_id='plan-001',
            user=admin_user,
            service=mock_service
        )

        assert result.plan_id == 'plan-001'
        mock_service.get_approval_by_plan_id.assert_called_once_with('plan-001')

    @pytest.mark.asyncio
    async def test_get_approval_not_found(
        self, admin_user
    ):
        """Teste plano nao encontrado"""
        mock_service = MagicMock()
        mock_service.get_approval_by_plan_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_approval(
                plan_id='plan-999',
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 404
        assert 'nao encontrado' in exc_info.value.detail


class TestApprovePlan:
    """Testes para endpoint POST /{plan_id}/approve"""

    @pytest.mark.asyncio
    async def test_approve_success(
        self, sample_approval_decision, admin_user
    ):
        """Teste aprovacao bem-sucedida"""
        mock_service = MagicMock()
        mock_service.approve_plan = AsyncMock(return_value=sample_approval_decision)

        from src.models.approval import ApproveRequestBody
        body = ApproveRequestBody(comments='Aprovado')

        result = await approve_plan(
            plan_id='plan-001',
            body=body,
            user=admin_user,
            service=mock_service
        )

        assert result.decision == 'approved'
        mock_service.approve_plan.assert_called_once_with(
            plan_id='plan-001',
            user_id='user-001',
            comments='Aprovado'
        )

    @pytest.mark.asyncio
    async def test_approve_without_comments(
        self, sample_approval_decision, admin_user
    ):
        """Teste aprovacao sem comentarios"""
        mock_service = MagicMock()
        mock_service.approve_plan = AsyncMock(return_value=sample_approval_decision)

        result = await approve_plan(
            plan_id='plan-001',
            body=None,
            user=admin_user,
            service=mock_service
        )

        assert result.decision == 'approved'
        mock_service.approve_plan.assert_called_once_with(
            plan_id='plan-001',
            user_id='user-001',
            comments=None
        )

    @pytest.mark.asyncio
    async def test_approve_not_found(
        self, admin_user
    ):
        """Teste plano nao encontrado"""
        mock_service = MagicMock()
        mock_service.approve_plan = AsyncMock(
            side_effect=ValueError('Plano nao encontrado: plan-999')
        )

        with pytest.raises(HTTPException) as exc_info:
            await approve_plan(
                plan_id='plan-999',
                body=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_already_decided(
        self, admin_user
    ):
        """Teste plano ja aprovado/rejeitado"""
        mock_service = MagicMock()
        mock_service.approve_plan = AsyncMock(
            side_effect=ValueError('Plano nao esta pendente. Status atual: approved')
        )

        with pytest.raises(HTTPException) as exc_info:
            await approve_plan(
                plan_id='plan-001',
                body=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 409


class TestRejectPlan:
    """Testes para endpoint POST /{plan_id}/reject"""

    @pytest.mark.asyncio
    async def test_reject_success(
        self, admin_user
    ):
        """Teste rejeicao bem-sucedida"""
        mock_service = MagicMock()
        decision = ApprovalDecision(
            plan_id='plan-001',
            decision='rejected',
            approved_by='user-001',
            approved_at=datetime.utcnow(),
            rejection_reason='Risco muito alto'
        )
        mock_service.reject_plan = AsyncMock(return_value=decision)

        from src.models.approval import RejectRequestBody
        body = RejectRequestBody(reason='Risco muito alto', comments=None)

        result = await reject_plan(
            plan_id='plan-001',
            body=body,
            user=admin_user,
            service=mock_service
        )

        assert result.decision == 'rejected'
        mock_service.reject_plan.assert_called_once_with(
            plan_id='plan-001',
            user_id='user-001',
            reason='Risco muito alto',
            comments=None
        )

    @pytest.mark.asyncio
    async def test_reject_not_found(
        self, admin_user
    ):
        """Teste plano nao encontrado"""
        mock_service = MagicMock()
        mock_service.reject_plan = AsyncMock(
            side_effect=ValueError('Plano nao encontrado: plan-999')
        )

        from src.models.approval import RejectRequestBody
        body = RejectRequestBody(reason='Motivo')

        with pytest.raises(HTTPException) as exc_info:
            await reject_plan(
                plan_id='plan-999',
                body=body,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_empty_reason(
        self, admin_user
    ):
        """Teste rejeicao com motivo vazio"""
        mock_service = MagicMock()
        mock_service.reject_plan = AsyncMock(
            side_effect=ValueError('Motivo da rejeicao e obrigatorio')
        )

        from src.models.approval import RejectRequestBody
        body = RejectRequestBody(reason='obrigatorio')  # Will be caught by pydantic min_length

        # Simular que passou pela validacao mas servico rejeitou
        mock_service.reject_plan.side_effect = ValueError('Motivo da rejeicao e obrigatorio')

        with pytest.raises(HTTPException) as exc_info:
            await reject_plan(
                plan_id='plan-001',
                body=body,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 400


class TestGetApprovalStats:
    """Testes para endpoint GET /stats"""

    @pytest.mark.asyncio
    async def test_get_stats_success(
        self, admin_user
    ):
        """Teste obtencao de estatisticas"""
        mock_service = MagicMock()
        stats = ApprovalStats(
            pending_count=5,
            approved_count=100,
            rejected_count=10,
            avg_approval_time_seconds=120.5,
            by_risk_band={'high': 3, 'critical': 2}
        )
        mock_service.get_approval_stats = AsyncMock(return_value=stats)

        result = await get_approval_stats(
            user=admin_user,
            service=mock_service
        )

        assert result.pending_count == 5
        assert result.approved_count == 100
        assert result.rejected_count == 10
        mock_service.get_approval_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats_service_error(
        self, admin_user
    ):
        """Teste erro no servico de estatisticas"""
        mock_service = MagicMock()
        mock_service.get_approval_stats = AsyncMock(
            side_effect=Exception("Aggregation error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_approval_stats(
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 500


class TestRepublishApprovedPlan:
    """Testes para endpoint POST /{plan_id}/republish"""

    @pytest.mark.asyncio
    async def test_republish_success(self, admin_user):
        """Teste republicacao bem-sucedida"""
        mock_service = MagicMock()
        response = ApprovalResponse(
            plan_id='plan-001',
            intent_id='intent-001',
            decision='approved',
            approved_by='original-admin',
            approved_at=datetime.utcnow(),
            cognitive_plan={'plan_id': 'plan-001'}
        )
        mock_service.republish_approved_plan = AsyncMock(return_value=response)

        from src.models.approval import RepublishRequestBody
        body = RepublishRequestBody(force=False, comments='Reprocessando')

        result = await republish_approved_plan(
            plan_id='plan-001',
            body=body,
            user=admin_user,
            service=mock_service
        )

        assert result.plan_id == 'plan-001'
        assert result.decision == 'approved'
        mock_service.republish_approved_plan.assert_called_once_with(
            plan_id='plan-001',
            user_id='user-001',
            force=False,
            comments='Reprocessando'
        )

    @pytest.mark.asyncio
    async def test_republish_without_body(self, admin_user):
        """Teste republicacao sem body (force=False, comments=None)"""
        mock_service = MagicMock()
        response = ApprovalResponse(
            plan_id='plan-001',
            intent_id='intent-001',
            decision='approved',
            approved_by='original-admin',
            approved_at=datetime.utcnow(),
            cognitive_plan={'plan_id': 'plan-001'}
        )
        mock_service.republish_approved_plan = AsyncMock(return_value=response)

        result = await republish_approved_plan(
            plan_id='plan-001',
            body=None,
            user=admin_user,
            service=mock_service
        )

        assert result.plan_id == 'plan-001'
        mock_service.republish_approved_plan.assert_called_once_with(
            plan_id='plan-001',
            user_id='user-001',
            force=False,
            comments=None
        )

    @pytest.mark.asyncio
    async def test_republish_with_force(self, admin_user):
        """Teste republicacao forcada"""
        mock_service = MagicMock()
        response = ApprovalResponse(
            plan_id='plan-001',
            intent_id='intent-001',
            decision='approved',
            approved_by='admin',
            approved_at=datetime.utcnow(),
            cognitive_plan={'plan_id': 'plan-001'}
        )
        mock_service.republish_approved_plan = AsyncMock(return_value=response)

        from src.models.approval import RepublishRequestBody
        body = RepublishRequestBody(force=True, comments='Forcando republicacao')

        result = await republish_approved_plan(
            plan_id='plan-001',
            body=body,
            user=admin_user,
            service=mock_service
        )

        mock_service.republish_approved_plan.assert_called_once_with(
            plan_id='plan-001',
            user_id='user-001',
            force=True,
            comments='Forcando republicacao'
        )

    @pytest.mark.asyncio
    async def test_republish_not_found(self, admin_user):
        """Teste plano nao encontrado"""
        mock_service = MagicMock()
        mock_service.republish_approved_plan = AsyncMock(
            side_effect=ValueError('Plano nao encontrado: plan-999')
        )

        with pytest.raises(HTTPException) as exc_info:
            await republish_approved_plan(
                plan_id='plan-999',
                body=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_republish_not_approved(self, admin_user):
        """Teste plano nao aprovado sem force"""
        mock_service = MagicMock()
        mock_service.republish_approved_plan = AsyncMock(
            side_effect=ValueError(
                'Plano nao esta aprovado. Status atual: pending. '
                'Use force=true para republicar mesmo assim.'
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await republish_approved_plan(
                plan_id='plan-001',
                body=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 400
        assert 'nao esta aprovado' in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_republish_missing_cognitive_plan(self, admin_user):
        """Teste plano sem cognitive_plan"""
        mock_service = MagicMock()
        mock_service.republish_approved_plan = AsyncMock(
            side_effect=ValueError(
                'Plano nao possui cognitive_plan para republicar: plan-001'
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await republish_approved_plan(
                plan_id='plan-001',
                body=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_republish_kafka_error(self, admin_user):
        """Teste erro ao publicar no Kafka"""
        mock_service = MagicMock()
        mock_service.republish_approved_plan = AsyncMock(
            side_effect=Exception("Kafka connection failed")
        )

        with pytest.raises(HTTPException) as exc_info:
            await republish_approved_plan(
                plan_id='plan-001',
                body=None,
                user=admin_user,
                service=mock_service
            )

        assert exc_info.value.status_code == 500
