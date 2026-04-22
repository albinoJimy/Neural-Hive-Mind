"""
Testes de integração para Active Learning com ApprovalService.

Verifica o fluxo E2E:
1. Approval request é processado
2. Caso é enfileirado para active learning se aplica
3. Feedback é marcado com balanced_dataset=True
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.config.settings import Settings
from src.models.approval import ApprovalRequest, ApprovalStatus, RiskBand
from src.services.approval_service import ApprovalService


# Helper function para criar ApprovalRequest válido
def create_test_approval(**kwargs):
    """Cria ApprovalRequest com valores padrão."""
    defaults = {
        "approval_id": "test-approval",
        "plan_id": "test-plan",
        "intent_id": "test-intent",
        "original_intent_text": "Test intent",
        "risk_score": 0.5,
        "risk_band": RiskBand.LOW,
        "is_destructive": False,
        "status": ApprovalStatus.PENDING,
        "requested_at": datetime.now(UTC),
        "cognitive_plan": {"plan_id": "test-plan", "steps": []},
    }
    defaults.update(kwargs)
    return ApprovalRequest(**defaults)


class TestActiveLearningIntegration:
    """Testes de integração de Active Learning."""

    @pytest.fixture()
    def mock_settings(self):
        """Settings mock."""
        settings = MagicMock(spec=Settings)
        settings.enable_active_learning = True
        settings.enable_feedback_collection = True
        settings.active_learning_min_information_value = 0.5
        settings.mongodb_database = "test_nh"
        return settings

    @pytest.fixture()
    def mock_mongodb_client(self):
        """MongoDB client mock."""
        client = AsyncMock()
        client.save_approval_request = AsyncMock()
        client.get_approval_by_plan_id = AsyncMock(return_value=None)
        return client

    @pytest.fixture()
    def mock_balance_analyzer(self):
        """BalanceAnalyzer mock."""
        analyzer = AsyncMock()
        analyzer.calculate_balance_metrics = AsyncMock(
            return_value=MagicMock(
                total_feedbacks=100,
                balance={"approve": {"count": 80, "percentage": 80.0}},
                model_dump=lambda: {
                    "total_feedbacks": 100,
                    "balance": {"approve": {"count": 80, "percentage": 80.0}},
                },
            )
        )
        return analyzer

    @pytest.fixture()
    def mock_learning_strategy(self):
        """ActiveLearningStrategy mock."""
        strategy = AsyncMock()
        strategy.calculate_information_value = AsyncMock(return_value=0.75)
        strategy.should_collect_feedback = AsyncMock(return_value=True)
        return strategy

    @pytest.fixture()
    def mock_priority_queue(self):
        """PriorityFeedbackQueue mock."""
        queue = AsyncMock()
        queue.enqueue_plan_for_review = AsyncMock(return_value="queue-id-123")
        return queue

    @pytest.fixture()
    def approval_service_with_al(
        self,
        mock_settings,
        mock_mongodb_client,
        mock_balance_analyzer,
        mock_learning_strategy,
        mock_priority_queue,
    ):
        """ApprovalService com Active Learning habilitado."""
        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=AsyncMock(),
            metrics=MagicMock(),
            balance_analyzer=mock_balance_analyzer,
            learning_strategy=mock_learning_strategy,
            priority_queue=mock_priority_queue,
        )
        return service

    @pytest.mark.asyncio()
    async def test_approval_request_enqueued_for_active_learning(
        self, approval_service_with_al, mock_learning_strategy, mock_priority_queue
    ):
        """Testa que approval request é enfileirado para active learning."""
        # Patch HAS_ACTIVE_LEARNING para True
        with patch("src.services.approval_service.HAS_ACTIVE_LEARNING", True):
            # Recriar service com patch aplicado
            approval_service_with_al.active_learning_enabled = True

            # Criar approval request
            request = create_test_approval(
                plan_id="plan-1",
                original_intent_text="Implementar nova feature de autenticação",
                risk_band=RiskBand.MEDIUM,
            )

            # Processar request
            await approval_service_with_al.process_approval_request(request)

        # Verificar que valor informacional foi calculado
        mock_learning_strategy.calculate_information_value.assert_called_once()

        # Verificar que caso foi enfileirado
        mock_priority_queue.enqueue_plan_for_review.assert_called_once()
        call_args = mock_priority_queue.enqueue_plan_for_review.call_args
        assert call_args[1]["plan_id"] == "plan-1"
        assert call_args[1]["information_value"] == 0.75

    @pytest.mark.asyncio()
    async def test_feedback_marked_with_balanced_dataset(
        self,
        approval_service_with_al,
        mock_balance_analyzer,
        mock_learning_strategy,
        mock_priority_queue,
    ):
        """Testa que feedback de active learning é marcado com balanced_dataset=True."""
        # Criar feedback collector mock
        feedback_collector = MagicMock()
        feedback_collector.submit_feedback = MagicMock(return_value="feedback-123")
        approval_service_with_al.feedback_collector = feedback_collector

        # Mock ledger client
        ledger_client = AsyncMock()
        ledger_client.get_opinions_by_plan_id = AsyncMock(
            return_value=[
                {
                    "opinion_id": "op-1",
                    "specialist_type": "business",
                    "recommendation": "approve",
                    "confidence_score": 0.5,
                }
            ]
        )
        approval_service_with_al.ledger_client = ledger_client

        # Submeter feedback com from_active_learning=True
        await approval_service_with_al._submit_feedback_for_plan(
            plan_id="plan-1",
            human_decision="approve",
            human_rating=1.0,
            user_id="user@example.com",
            from_active_learning=True,
        )

        # Verificar que feedback foi marcado como balanced
        feedback_collector.submit_feedback.assert_called_once()
        call_args = feedback_collector.submit_feedback.call_args
        feedback_data = call_args[0][0]
        assert feedback_data["balanced_dataset"] is True
        assert feedback_data["collection_method"] == "active_learning"

    @pytest.mark.asyncio()
    async def test_feedback_not_marked_when_not_from_active_learning(
        self, approval_service_with_al
    ):
        """Testa que feedback normal não é marcado como balanced."""
        feedback_collector = MagicMock()
        feedback_collector.submit_feedback = MagicMock(return_value="feedback-123")
        approval_service_with_al.feedback_collector = feedback_collector

        ledger_client = AsyncMock()
        ledger_client.get_opinions_by_plan_id = AsyncMock(
            return_value=[
                {
                    "opinion_id": "op-1",
                    "specialist_type": "business",
                    "recommendation": "approve",
                    "confidence_score": 0.5,
                }
            ]
        )
        approval_service_with_al.ledger_client = ledger_client

        # Submeter feedback sem from_active_learning
        await approval_service_with_al._submit_feedback_for_plan(
            plan_id="plan-1", human_decision="approve", human_rating=1.0, user_id="user@example.com"
        )

        # Verificar que feedback não está marcado
        call_args = feedback_collector.submit_feedback.call_args
        feedback_data = call_args[0][0]
        assert feedback_data["balanced_dataset"] is False
        assert feedback_data["collection_method"] == "automatic"


class TestActiveLearningDisabled:
    """Testes quando Active Learning está desabilitado."""

    @pytest.fixture()
    def mock_settings(self):
        """Settings com AL desabilitado."""
        settings = MagicMock(spec=Settings)
        settings.enable_active_learning = False
        settings.enable_feedback_collection = True
        return settings

    @pytest.fixture()
    def approval_service_no_al(self, mock_settings):
        """ApprovalService sem Active Learning."""
        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=AsyncMock(),
            response_producer=AsyncMock(),
            metrics=MagicMock(),
        )
        return service

    @pytest.mark.asyncio()
    async def test_case_not_enqueued_when_al_disabled(self, approval_service_no_al, mock_settings):
        """Testa que casos não são enfileirados quando AL está desabilitado."""
        request = create_test_approval()

        # Processar não deve levantar erro
        await approval_service_no_al.process_approval_request(request)

        # Verificar que active_learning_enabled está False
        assert approval_service_no_al.active_learning_enabled is False
