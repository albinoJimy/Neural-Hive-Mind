"""
Testes de integracao para feedback ML no Approval Service.

Valida integracao entre decisoes humanas (aprovacao/rejeicao) e
submissao de feedback para continuous learning dos specialists.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from src.services.approval_service import ApprovalService
from src.models.approval import ApprovalStatus


class TestFeedbackIntegration:
    """Testes de integracao do feedback ML."""

    @pytest.fixture
    def approval_service_with_feedback(
        self,
        mock_settings,
        mock_mongodb_client,
        mock_response_producer,
        mock_metrics,
        mock_feedback_collector,
        mock_ledger_client
    ):
        """ApprovalService configurado com feedback collection."""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics,
            feedback_collector=mock_feedback_collector,
            ledger_client=mock_ledger_client
        )

    @pytest.fixture
    def approval_service_without_feedback(
        self,
        mock_settings,
        mock_mongodb_client,
        mock_response_producer,
        mock_metrics
    ):
        """ApprovalService sem feedback collection."""
        mock_settings.enable_feedback_collection = False
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics,
            feedback_collector=None,
            ledger_client=None
        )

    @pytest.mark.asyncio
    async def test_approve_plan_with_feedback_success(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Aprovacao deve submeter feedback ML para cada specialist."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        # Act
        decision = await approval_service_with_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com',
            comments='Aprovado'
        )

        # Assert
        assert decision.decision == 'approved'

        # Verificar que ledger foi consultado
        mock_ledger_client.get_opinions_by_plan_id.assert_called_once_with(
            sample_approval_request.plan_id
        )

        # Verificar que feedback foi submetido para cada specialist
        assert mock_feedback_collector.submit_feedback.call_count == 2

        # Verificar conteudo do primeiro feedback
        first_call = mock_feedback_collector.submit_feedback.call_args_list[0]
        feedback_data = first_call[0][0]
        assert feedback_data['human_rating'] == 1.0
        assert feedback_data['human_recommendation'] == 'approve'
        assert feedback_data['submitted_by'] == 'admin@example.com'
        assert feedback_data['metadata']['source'] == 'approval_service'

    @pytest.mark.asyncio
    async def test_reject_plan_with_feedback_success(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Rejeicao deve submeter feedback ML com rating zero."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        # Act
        decision = await approval_service_with_feedback.reject_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com',
            reason='Risco de seguranca alto',
            comments='Necessita revisao da arquitetura'
        )

        # Assert
        assert decision.decision == 'rejected'

        # Verificar que ledger foi consultado
        mock_ledger_client.get_opinions_by_plan_id.assert_called_once()

        # Verificar que feedback foi submetido com rating zero
        assert mock_feedback_collector.submit_feedback.call_count == 2

        first_call = mock_feedback_collector.submit_feedback.call_args_list[0]
        feedback_data = first_call[0][0]
        assert feedback_data['human_rating'] == 0.0
        assert feedback_data['human_recommendation'] == 'reject'

    @pytest.mark.asyncio
    async def test_approve_without_opinions_graceful_degradation(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Aprovacao deve continuar mesmo sem opinioes no ledger."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_ledger_client.get_opinions_by_plan_id.return_value = []

        # Act
        decision = await approval_service_with_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com'
        )

        # Assert - aprovacao deve funcionar
        assert decision.decision == 'approved'

        # Feedback nao deve ser submetido (sem opinioes)
        mock_feedback_collector.submit_feedback.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_when_feedback_collector_fails(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Aprovacao nao deve falhar se FeedbackCollector lancar excecao."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_feedback_collector.submit_feedback.side_effect = Exception('MongoDB connection error')

        # Act - nao deve lancar excecao
        decision = await approval_service_with_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com'
        )

        # Assert - aprovacao deve funcionar
        assert decision.decision == 'approved'

    @pytest.mark.asyncio
    async def test_approve_when_ledger_fails(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Aprovacao nao deve falhar se consulta ao ledger falhar."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_ledger_client.get_opinions_by_plan_id.side_effect = Exception('Ledger unavailable')

        # Act - nao deve lancar excecao
        decision = await approval_service_with_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com'
        )

        # Assert - aprovacao deve funcionar
        assert decision.decision == 'approved'

        # Feedback nao deve ser chamado (ledger falhou antes)
        mock_feedback_collector.submit_feedback.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_without_feedback_collection_enabled(
        self,
        approval_service_without_feedback,
        mock_mongodb_client,
        sample_approval_request
    ):
        """Aprovacao funciona normalmente sem feedback collection."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        # Act
        decision = await approval_service_without_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com'
        )

        # Assert
        assert decision.decision == 'approved'

    @pytest.mark.asyncio
    async def test_feedback_for_multiple_specialists(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Feedback deve ser submetido para cada specialist individualmente."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_ledger_client.get_opinions_by_plan_id.return_value = [
            {'opinion_id': 'op-1', 'specialist_type': 'technical', 'plan_id': 'plan-001',
             'recommendation': 'approve', 'confidence_score': 0.9},
            {'opinion_id': 'op-2', 'specialist_type': 'security', 'plan_id': 'plan-001',
             'recommendation': 'review_required', 'confidence_score': 0.7},
            {'opinion_id': 'op-3', 'specialist_type': 'business', 'plan_id': 'plan-001',
             'recommendation': 'approve', 'confidence_score': 0.85}
        ]

        # Act
        await approval_service_with_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com'
        )

        # Assert - feedback para cada specialist
        assert mock_feedback_collector.submit_feedback.call_count == 3

        # Verificar opinion_ids unicos
        opinion_ids = [
            call[0][0]['opinion_id']
            for call in mock_feedback_collector.submit_feedback.call_args_list
        ]
        assert opinion_ids == ['op-1', 'op-2', 'op-3']

    @pytest.mark.asyncio
    async def test_feedback_continues_if_one_submission_fails(
        self,
        approval_service_with_feedback,
        mock_mongodb_client,
        mock_feedback_collector,
        mock_ledger_client,
        sample_approval_request
    ):
        """Falha em um feedback nao deve impedir outros."""
        # Arrange
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request

        # Primeiro feedback falha, segundo sucesso
        mock_feedback_collector.submit_feedback.side_effect = [
            Exception('First fails'),
            'feedback-002'
        ]

        # Act - nao deve lancar excecao
        decision = await approval_service_with_feedback.approve_plan(
            plan_id=sample_approval_request.plan_id,
            user_id='admin@example.com'
        )

        # Assert
        assert decision.decision == 'approved'

        # Ambos feedbacks foram tentados
        assert mock_feedback_collector.submit_feedback.call_count == 2
