"""Testes unitários para ApprovalService."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pymongo.errors import DuplicateKeyError
from src.config.settings import Settings
from src.models.approval import ApprovalDecision, ApprovalRequest
from src.services.approval_service import ApprovalService


@pytest.fixture()
def mock_settings():
    """Mock Settings."""
    settings = Mock(spec=Settings)
    settings.enable_feedback_collection = True
    settings.feedback_on_approval_failure_mode = "log_and_continue"
    settings.enable_active_learning = False
    settings.active_learning_min_information_value = 0.5
    settings.active_learning_enqueue_rate = 0.2
    return settings


@pytest.fixture()
def mock_mongodb_client():
    """Mock MongoDBClient."""
    client = AsyncMock()
    client.save_approval_request = AsyncMock()
    client.get_approval_by_plan_id = AsyncMock()
    client.update_approval_status = AsyncMock()
    client.get_approval_stats = AsyncMock(
        return_value={"total": 100, "pending": 10, "approved": 80, "rejected": 10}
    )
    return client


@pytest.fixture()
def mock_response_producer():
    """Mock ApprovalResponseProducer."""
    producer = AsyncMock()
    producer.publish_approval_response = AsyncMock()
    return producer


@pytest.fixture()
def mock_metrics():
    """Mock NeuralHiveMetrics."""
    metrics = Mock()
    metrics.increment_approval_requests_received = Mock()
    metrics.update_pending_gauge = Mock()
    metrics.record_approval_decision = Mock()
    metrics.record_decision_latency_ms = Mock()
    return metrics


@pytest.fixture()
def mock_ledger_client():
    """Mock CognitiveLedgerClient."""
    ledger = AsyncMock()
    ledger.get_opinions_by_plan_id = AsyncMock(
        return_value=[
            {
                "opinion_id": "op-1",
                "specialist_type": "business",
                "recommendation": "approve",
                "confidence_score": 0.8,
            }
        ]
    )
    return ledger


@pytest.fixture()
def mock_feedback_collector():
    """Mock FeedbackCollector."""
    collector = Mock()
    collector.submit_feedback = Mock(return_value="feedback-123")
    return collector


@pytest.fixture()
def mock_ml_predictor():
    """Mock MLPredictor."""
    predictor = AsyncMock()
    predictor.is_enabled = Mock(return_value=True)
    predictor.predict_from_text = AsyncMock(
        return_value={"decision": "approve", "confidence": 0.75, "model_version": "v8"}
    )
    predictor.get_auto_decision = AsyncMock(
        return_value={"auto_decision": "approve", "confidence": 0.75, "reason": "high_confidence"}
    )
    return predictor


@pytest.fixture()
def approval_service(
    mock_settings,
    mock_mongodb_client,
    mock_response_producer,
    mock_metrics,
    mock_ledger_client,
    mock_feedback_collector,
    mock_ml_predictor,
):
    """Fixture para ApprovalService."""
    return ApprovalService(
        settings=mock_settings,
        mongodb_client=mock_mongodb_client,
        response_producer=mock_response_producer,
        metrics=mock_metrics,
        ledger_client=mock_ledger_client,
        feedback_collector=mock_feedback_collector,
        ml_predictor=mock_ml_predictor,
    )


@pytest.fixture()
def sample_approval_request():
    """ApprovalRequest de exemplo."""
    return ApprovalRequest(
        plan_id="plan-123",
        intent_id="intent-123",
        risk_band="medium",
        is_destructive=False,
        original_intent_text="Test intent for approval",
        submitted_by="user-123",
        submitted_at=datetime.now(),
    )


class TestProcessApprovalRequest:
    """Testes para process_approval_request."""

    @pytest.mark.asyncio()
    async def test_process_approval_request_success(
        self, approval_service, sample_approval_request, mock_mongodb_client, mock_metrics
    ):
        """Testa processamento bem-sucedido de approval request."""
        result = await approval_service.process_approval_request(sample_approval_request)

        assert result.plan_id == "plan-123"
        mock_mongodb_client.save_approval_request.assert_called_once_with(sample_approval_request)
        mock_metrics.increment_approval_requests_received.assert_called_once()

    @pytest.mark.asyncio()
    async def test_process_approval_request_duplicate(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Testa erro de duplicata ao processar approval request."""
        mock_mongodb_client.save_approval_request.side_effect = DuplicateKeyError("E11000")

        with pytest.raises(DuplicateKeyError):
            await approval_service.process_approval_request(sample_approval_request)

    @pytest.mark.asyncio()
    async def test_process_approval_request_missing_fields(
        self, approval_service, mock_mongodb_client
    ):
        """Testa erro quando campos obrigatórios estão faltando."""
        invalid_request = ApprovalRequest(
            plan_id="",  # Inválido
            intent_id="",  # Inválido
            risk_band="low",
            is_destructive=False,
            submitted_by="user-123",
            submitted_at=datetime.now(),
        )

        with pytest.raises(ValueError, match="plan_id e intent_id sao obrigatorios"):
            await approval_service.process_approval_request(invalid_request)

        mock_mongodb_client.save_approval_request.assert_not_called()


class TestGetMLPrediction:
    """Testes para get_ml_prediction."""

    @pytest.mark.asyncio()
    async def test_get_ml_prediction_success(
        self, approval_service, mock_mongodb_client, mock_ml_predictor
    ):
        """Testa obtenção de predição ML com sucesso."""
        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        result = await approval_service.get_ml_prediction("plan-123")

        assert result is not None
        assert result["decision"] == "approve"
        assert result["confidence"] == 0.75

    @pytest.mark.asyncio()
    async def test_get_ml_prediction_no_approval(self, approval_service, mock_mongodb_client):
        """Testa quando approval não é encontrado."""
        mock_mongodb_client.get_approval_by_plan_id.return_value = None

        result = await approval_service.get_ml_prediction("plan-123")

        assert result is None

    @pytest.mark.asyncio()
    async def test_get_ml_prediction_no_intent_text(self, approval_service, mock_mongodb_client):
        """Testa quando approval não tem intent_text."""
        mock_approval = Mock()
        mock_approval.original_intent_text = None
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        result = await approval_service.get_ml_prediction("plan-123")

        assert result is None

    @pytest.mark.asyncio()
    async def test_get_ml_prediction_disabled(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Testa quando ML predictor está desabilitado."""
        mock_ml_predictor = AsyncMock()
        mock_ml_predictor.is_enabled = Mock(return_value=False)

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics,
            ml_predictor=mock_ml_predictor,
        )

        result = await service.get_ml_prediction("plan-123")

        assert result is None


class TestGetAutoDecision:
    """Testes para get_auto_decision."""

    @pytest.mark.asyncio()
    async def test_get_auto_decision_success(
        self, approval_service, mock_mongodb_client, mock_ml_predictor
    ):
        """Testa obtenção de decisão automática com sucesso."""
        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_approval.risk_band = "low"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        result = await approval_service.get_auto_decision("plan-123")

        assert result is not None
        assert result["auto_decision"] == "approve"
        assert result["confidence"] == 0.75

    @pytest.mark.asyncio()
    async def test_get_auto_decision_not_found(self, approval_service, mock_mongodb_client):
        """Testa quando approval não é encontrado."""
        mock_mongodb_client.get_approval_by_plan_id.return_value = None

        result = await approval_service.get_auto_decision("plan-123")

        assert result is None


class TestSubmitFeedbackForPlan:
    """Testes para _submit_feedback_for_plan."""

    @pytest.mark.asyncio()
    async def test_submit_feedback_success(
        self, approval_service, mock_mongodb_client, mock_ledger_client, mock_feedback_collector
    ):
        """Testa submissão de feedback com sucesso."""
        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        await approval_service._submit_feedback_for_plan(
            plan_id="plan-123",
            human_decision="approve",
            human_rating=0.8,
            user_id="user-123",
            comments="Good decision",
        )

        mock_feedback_collector.submit_feedback.assert_called_once()

    @pytest.mark.asyncio()
    async def test_submit_feedback_disabled(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Testa quando feedback collection está desabilitado."""
        mock_settings.enable_feedback_collection = False

        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics,
        )

        # Não deve chamar ledger_client nem feedback_collector
        await service._submit_feedback_for_plan(
            plan_id="plan-123", human_decision="approve", human_rating=0.8, user_id="user-123"
        )

    @pytest.mark.asyncio()
    async def test_submit_feedback_no_opinions(
        self, approval_service, mock_mongodb_client, mock_ledger_client
    ):
        """Testa quando não há opiniões para o plano."""
        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval
        mock_ledger_client.get_opinions_by_plan_id.return_value = []

        # Não deve levantar erro, apenas retornar
        await approval_service._submit_feedback_for_plan(
            plan_id="plan-123", human_decision="approve", human_rating=0.8, user_id="user-123"
        )

    @pytest.mark.asyncio()
    async def test_submit_feedback_from_active_learning(
        self, approval_service, mock_mongodb_client, mock_ledger_client, mock_feedback_collector
    ):
        """Testa submissão de feedback marcado como active learning."""
        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        await approval_service._submit_feedback_for_plan(
            plan_id="plan-123",
            human_decision="approve",
            human_rating=0.8,
            user_id="user-123",
            from_active_learning=True,
        )

        # Verificar que balanced_dataset=True foi passado
        call_args = mock_feedback_collector.submit_feedback.call_args
        assert call_args[0][0]["balanced_dataset"] is True
        assert call_args[0][0]["collection_method"] == "active_learning"


class TestExtractDomainFromText:
    """Testes para _extract_domain_from_text."""

    @pytest.mark.asyncio()
    async def test_extract_domain_success(self, approval_service):
        """Testa extração de domínio com sucesso."""
        with patch.object(approval_service, "_nlp_extractor") as mock_extractor:
            mock_extractor.extract_features.return_value = {"primary_domain": "security"}

            result = approval_service._extract_domain_from_text(
                "Enable authentication for all API endpoints"
            )

            assert result == "security"

    @pytest.mark.asyncio()
    async def test_extract_domain_no_text(self, approval_service):
        """Testa quando não há texto de intenção."""
        result = approval_service._extract_domain_from_text(None)

        assert result is None

    @pytest.mark.asyncio()
    async def test_extract_domain_no_extractor(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Testa quando NLP extractor não está disponível."""
        service = ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics,
        )
        service._nlp_extractor = None

        result = service._extract_domain_from_text("Test text")

        assert result is None

    @pytest.mark.asyncio()
    async def test_extract_domain_extractor_error(self, approval_service):
        """Testa erro na extração de domínio."""
        with patch.object(approval_service, "_nlp_extractor") as mock_extractor:
            mock_extractor.extract_features.side_effect = Exception("Extraction failed")

            result = approval_service._extract_domain_from_text("Test text")

            assert result is None


class TestGetPriorityReason:
    """Testes para _get_priority_reason."""

    def test_get_priority_reason_high_value_low_confidence(self, approval_service):
        """Testa razão com alto valor informacional e baixa confiança."""
        result = approval_service._get_priority_reason(0.8, 0.3)

        assert "valor informacional muito alto" in result
        assert "baixa confiança" in result

    def test_get_priority_reason_moderate_value_moderate_confidence(self, approval_service):
        """Testa razão com valores moderados."""
        result = approval_service._get_priority_reason(0.6, 0.5)

        assert "valor informacional alto" in result
        assert "confiança moderada" in result

    def test_get_priority_reason_default(self, approval_service):
        """Testa razão padrão quando valores são limítrofes."""
        result = approval_service._get_priority_reason(0.4, 0.7)

        assert result == "active learning"


class TestMaybeEnqueueForActiveLearning:
    """Testes para _maybe_enqueue_for_active_learning."""

    @pytest.mark.asyncio()
    async def test_enqueue_disabled(self, approval_service, sample_approval_request):
        """Testa quando active learning está desabilitado."""
        approval_service.active_learning_enabled = False

        await approval_service._maybe_enqueue_for_active_learning(sample_approval_request)

        # Não deve levantar erro

    @pytest.mark.asyncio()
    async def test_enqueue_high_information_value(self, approval_service, sample_approval_request):
        """Testa enfileiramento quando valor informacional é alto."""
        approval_service.active_learning_enabled = True
        approval_service.priority_queue = AsyncMock()
        approval_service.learning_strategy = AsyncMock()
        approval_service.learning_strategy.calculate_information_value = AsyncMock(return_value=0.8)

        await approval_service._maybe_enqueue_for_active_learning(sample_approval_request)

        approval_service.priority_queue.enqueue_plan_for_review.assert_called_once()

    @pytest.mark.asyncio()
    async def test_enqueue_below_threshold(self, approval_service, sample_approval_request):
        """Testa quando valor informacional está abaixo do threshold."""
        approval_service.active_learning_enabled = True
        approval_service.learning_strategy = AsyncMock()
        approval_service.learning_strategy.calculate_information_value = AsyncMock(return_value=0.3)

        await approval_service._maybe_enqueue_for_active_learning(sample_approval_request)

        # Não deve enfileirar


class TestGetApprovalStats:
    """Testes para get_approval_stats."""

    @pytest.mark.asyncio()
    async def test_get_approval_stats_success(self, approval_service, mock_mongodb_client):
        """Testa obtenção de estatísticas com sucesso."""
        result = await approval_service.get_approval_stats()

        assert result["total"] == 100
        assert result["pending"] == 10
        assert result["approved"] == 80
        assert result["rejected"] == 10


class TestProcessApprovalDecision:
    """Testes para process_approval_decision."""

    @pytest.mark.asyncio()
    async def test_process_approval_decision_approve(
        self,
        approval_service,
        mock_mongodb_client,
        mock_response_producer,
        mock_metrics,
        mock_feedback_collector,
        mock_ledger_client,
    ):
        """Testa processamento de decisão de aprovação."""
        decision = ApprovalDecision(
            plan_id="plan-123",
            decision="approve",
            decided_by="user-123",
            decided_at=datetime.now(),
            reasoning="Good plan",
            rating=0.8,
        )

        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        result = await approval_service.process_approval_decision(decision)

        mock_mongodb_client.update_approval_status.assert_called_once()
        mock_response_producer.publish_approval_response.assert_called_once()
        mock_feedback_collector.submit_feedback.assert_called_once()

    @pytest.mark.asyncio()
    async def test_process_approval_decision_reject(
        self,
        approval_service,
        mock_mongodb_client,
        mock_response_producer,
        mock_metrics,
        mock_feedback_collector,
    ):
        """Testa processamento de decisão de rejeição."""
        decision = ApprovalDecision(
            plan_id="plan-123",
            decision="reject",
            decided_by="user-123",
            decided_at=datetime.now(),
            reasoning="Too risky",
            rating=0.2,
        )

        mock_approval = Mock()
        mock_approval.original_intent_text = "Test intent"
        mock_mongodb_client.get_approval_by_plan_id.return_value = mock_approval

        result = await approval_service.process_approval_decision(decision)

        mock_mongodb_client.update_approval_status.assert_called_once()
        mock_response_producer.publish_approval_response.assert_called_once()
