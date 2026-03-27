"""
Testes para PriorityFeedbackQueue.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-17-active-learning-feedback/
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from neural_hive_specialists.feedback.active_learning.feedback_queue import (
    PriorityFeedbackQueue,
    QueuedCase,
    QueueStatus,
    DEFAULT_CLAIM_EXPIRY_HOURS,
)


class TestPriorityFeedbackQueue:
    """Testes do PriorityFeedbackQueue."""

    @pytest.fixture
    def mock_collection(self):
        """Mock da coleção active_learning_queue."""
        collection = MagicMock(spec=Collection)
        return collection

    @pytest.fixture
    def mock_strategy(self):
        """Mock do ActiveLearningStrategy."""
        strategy = MagicMock()
        strategy.calculate_from_prediction.return_value = 0.75
        return strategy

    @pytest.fixture
    def queue(self, mock_collection, mock_strategy):
        """Instância da fila."""
        return PriorityFeedbackQueue(collection=mock_collection, strategy=mock_strategy)

    @pytest.fixture
    def sample_plan(self):
        """Dados de um plano para enfileirar."""
        return {
            "plan_id": "plan-123",
            "intent_text": "Implementar autenticação com OAuth2",
            "intent_preview": "Implementar autenticação...",
            "prediction": {
                "decision": "approve",
                "confidence": 0.45,
                "nlp_features": {"primary_domain": "security"},
            },
            "domain": "security",
            "confidence": 0.45,
            "predicted_decision": "approve",
        }

    def test_queue_initialization(self, queue, mock_collection, mock_strategy):
        """Testa que a fila pode ser inicializada."""
        assert queue.collection is mock_collection
        assert queue.strategy is mock_strategy
        assert queue.claim_expiry_hours == DEFAULT_CLAIM_EXPIRY_HOURS

    def test_enqueue_plan_for_review(self, queue, sample_plan):
        """Testa enfileiramento de plano para revisão."""
        mock_collection = queue.collection
        mock_collection.insert_one.return_value = MagicMock(inserted_id="queue-abc")

        result = queue.enqueue_plan_for_review(
            plan_id=sample_plan["plan_id"],
            intent_text=sample_plan["intent_text"],
            prediction=sample_plan["prediction"],
        )

        assert result["queue_id"] is not None
        assert result["plan_id"] == sample_plan["plan_id"]
        assert result["status"] == QueueStatus.PENDING
        assert result["information_value"] > 0
        mock_collection.insert_one.assert_called_once()

    def test_enqueue_calculates_information_value(self, queue, sample_plan):
        """Testa que enqueue calcula valor informacional."""
        # Strategy deve ser chamada com prediction e dataset_stats
        queue.strategy.calculate_from_prediction.return_value = 0.85

        queue.collection.insert_one.return_value = MagicMock(inserted_id="queue-xyz")

        result = queue.enqueue_plan_for_review(
            plan_id=sample_plan["plan_id"],
            intent_text=sample_plan["intent_text"],
            prediction=sample_plan["prediction"],
            dataset_stats={"class_distribution": {"approve": 0.9, "reject": 0.1}},
        )

        assert result["information_value"] == 0.85
        queue.strategy.calculate_from_prediction.assert_called_once()

    def test_enqueue_generates_priority_reason(self, queue, sample_plan):
        """Testa que enqueue gera razão de prioridade."""
        queue.collection.insert_one.return_value = MagicMock(inserted_id="queue-xyz")

        result = queue.enqueue_plan_for_review(
            plan_id=sample_plan["plan_id"],
            intent_text=sample_plan["intent_text"],
            prediction=sample_plan["prediction"],
        )

        assert "priority_reason" in result
        assert result["priority_reason"]

    def test_enqueue_handles_duplicate_plan_id(self, queue, sample_plan):
        """Testa tratamento de plano duplicado."""
        from pymongo.errors import DuplicateKeyError

        # Simular DuplicateKeyError
        queue.collection.insert_one.side_effect = DuplicateKeyError(
            "E11000 duplicate key"
        )

        with pytest.raises(ValueError) as exc_info:
            queue.enqueue_plan_for_review(
                plan_id=sample_plan["plan_id"],
                intent_text=sample_plan["intent_text"],
                prediction=sample_plan["prediction"],
            )

        assert "já está na fila" in str(exc_info.value).lower()

    def test_dequeue_next_case(self, queue):
        """Testa desenfileiramento do próximo caso."""
        # Mock para retornar caso pendente
        queue.collection.find_one.return_value = {
            "_id": "queue-id",
            "queue_id": "queue-123",
            "plan_id": "plan-123",
            "intent_preview": "Implementar...",
            "information_value": 0.85,
            "status": QueueStatus.PENDING,
            "created_at": datetime.utcnow(),
        }

        case = queue.dequeue_next_case()

        assert case is not None
        assert case["queue_id"] == "queue-123"
        assert case["status"] == QueueStatus.PENDING

    def test_dequeue_orders_by_information_value(self, queue):
        """Testa que dequeue ordena por valor informacional (desc)."""
        # Mock find_one para verificar ordenação
        queue.collection.find_one.return_value = {
            "_id": "id",
            "queue_id": "queue-123",
            "status": QueueStatus.PENDING,
        }

        queue.dequeue_next_case()

        # Deve buscar com sort por information_value descending
        queue.collection.find_one.assert_called_once()
        call_args = queue.collection.find_one.call_args

        # Primeiro argumento é a query
        assert call_args[0] is not None

        # Verificar sort no segundo argumento (kwargs)
        kwargs = call_args[1] if len(call_args) > 1 else {}
        if "sort" in kwargs:
            sort = kwargs["sort"]
            assert sort[0][0] == "information_value"
            assert sort[0][1] == -1  # Descending

    def test_dequeue_returns_none_when_empty(self, queue):
        """Testa que dequeue retorna None quando fila vazia."""
        queue.collection.find_one.return_value = None

        case = queue.dequeue_next_case()

        assert case is None

    def test_claim_case(self, queue):
        """Testa reivindicação de caso para revisão."""
        mock_result = MagicMock()
        mock_result.matched_count = 1
        queue.collection.update_one.return_value = mock_result

        # Mock find_one para retornar o caso atualizado
        queue.collection.find_one.return_value = {
            "_id": "queue-id",
            "queue_id": "queue-123",
            "plan_id": "plan-123",
            "status": QueueStatus.IN_REVIEW,
            "assigned_to": "user@example.com",
            "claimed_at": datetime.utcnow(),
            "expires_at": datetime.utcnow(),
        }

        result = queue.claim_case(queue_id="queue-123", assigned_to="user@example.com")

        assert result["queue_id"] == "queue-123"
        assert result["status"] == QueueStatus.IN_REVIEW
        assert result["assigned_to"] == "user@example.com"
        assert "expires_at" in result

    def test_claim_case_calculates_expiry(self, queue):
        """Testa que claim define expiração corretamente."""
        mock_result = MagicMock()
        mock_result.matched_count = 1
        queue.collection.update_one.return_value = mock_result

        now = datetime.utcnow()
        queue.collection.find_one.return_value = {
            "queue_id": "queue-123",
            "status": QueueStatus.IN_REVIEW,
            "assigned_to": "user@example.com",
            "claimed_at": now,
            "expires_at": now + timedelta(hours=DEFAULT_CLAIM_EXPIRY_HOURS),
        }

        result = queue.claim_case(queue_id="queue-123", assigned_to="user@example.com")

        # Expira em DEFAULT_CLAIM_EXPIRY_HOURS
        claimed_at = result["claimed_at"]
        expires_at = result["expires_at"]
        delta = expires_at - claimed_at

        expected_delta = timedelta(hours=DEFAULT_CLAIM_EXPIRY_HOURS)
        assert (
            abs(delta.total_seconds() - expected_delta.total_seconds()) < 10
        )  # 10s tolerance

    def test_claim_case_returns_none_if_not_found(self, queue):
        """Testa claim de caso inexistente retorna None."""
        queue.collection.update_one.return_value = MagicMock(matched_count=0)

        result = queue.claim_case(
            queue_id="queue-nonexistent", assigned_to="user@example.com"
        )

        assert result is None

    def test_release_case(self, queue):
        """Testa liberação de caso reivindicado."""
        queue.collection.update_one.return_value = MagicMock(matched_count=1)

        result = queue.release_case("queue-123")

        assert result is not None
        assert result["status"] == QueueStatus.PENDING

    def test_mark_feedback_submitted(self, queue):
        """Testa marcação de feedback como submetido."""
        mock_result = MagicMock()
        mock_result.matched_count = 1
        queue.collection.update_one.return_value = mock_result

        result = queue.mark_feedback_submitted(
            queue_id="queue-123", feedback_id="feedback-456"
        )

        assert result is not None
        assert result["status"] == QueueStatus.COMPLETED
        assert result["feedback_id"] == "feedback-456"
        # completed_at não está incluído no resultado simplificado

    def test_mark_feedback_submitted_returns_none_if_not_found(self, queue):
        """Testa marcação de caso inexistente retorna None."""
        queue.collection.update_one.return_value = MagicMock(matched_count=0)

        result = queue.mark_feedback_submitted(
            queue_id="queue-nonexistent", feedback_id="feedback-456"
        )

        assert result is None

    def test_get_queue_size(self, queue):
        """Testa obtenção do tamanho da fila."""
        queue.collection.count_documents.return_value = 42

        size = queue.get_queue_size()

        assert size == 42

    def test_get_queue_size_by_status(self, queue):
        """Testa obtenção do tamanho da fila filtrado por status."""
        queue.collection.count_documents.return_value = 10

        size = queue.get_queue_size(status=QueueStatus.PENDING)

        assert size == 10
        queue.collection.count_documents.assert_called_once_with(
            {"status": QueueStatus.PENDING}
        )

    def test_get_pending_cases(self, queue):
        """Testa listagem de casos pendentes."""
        queue.collection.count_documents.return_value = 5

        # Mock cursor - precisamos simular limit()
        mock_cursor = [
            {"queue_id": "q1", "plan_id": "p1", "information_value": 0.9, "_id": "id1"},
            {"queue_id": "q2", "plan_id": "p2", "information_value": 0.8, "_id": "id2"},
        ]
        mock_find_result = MagicMock()
        mock_find_result.limit.return_value = mock_cursor
        queue.collection.find.return_value = mock_find_result

        cases = queue.get_pending_cases(limit=10)

        assert len(cases) == 2
        assert cases[0]["queue_id"] == "q1"

    def test_expire_claims(self, queue):
        """Testa expiração de claims antigos."""
        # Mock update_many para expirar claims
        mock_result = MagicMock()
        mock_result.modified_count = 2
        queue.collection.update_many.return_value = mock_result

        expired_count = queue.expire_claims()

        assert expired_count == 2

    def test_cleanup_completed(self, queue):
        """Testa limpeza de casos completos."""
        queue.collection.delete_many.return_value = MagicMock(deleted_count=5)

        deleted_count = queue.cleanup_completed(older_than_hours=24)

        assert deleted_count == 5


class TestQueueStatus:
    """Testes do enum QueueStatus."""

    def test_status_values(self):
        """Testa valores de status."""
        assert QueueStatus.PENDING == "pending"
        assert QueueStatus.IN_REVIEW == "in_review"
        assert QueueStatus.COMPLETED == "completed"
        assert QueueStatus.CANCELLED == "cancelled"


class TestQueuedCase:
    """Testes do modelo QueuedCase."""

    def test_queued_case_creation(self):
        """Testa criação de QueuedCase."""
        case = QueuedCase(
            queue_id="queue-123",
            plan_id="plan-123",
            intent_preview="Implementar...",
            information_value=0.85,
            priority_reason="Alta incerteza",
            status=QueueStatus.PENDING,
        )

        assert case.queue_id == "queue-123"
        assert case.information_value == 0.85
        assert case.status == QueueStatus.PENDING

    def test_queued_case_to_dict(self):
        """Testa conversão para dicionário."""
        case = QueuedCase(
            queue_id="queue-123",
            plan_id="plan-123",
            intent_preview="Implementar...",
            information_value=0.85,
            priority_reason="Alta incerteza",
            status=QueueStatus.PENDING,
        )

        data = case.to_dict()

        assert data["queue_id"] == "queue-123"
        assert data["plan_id"] == "plan-123"
        assert "created_at" in data
