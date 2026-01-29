"""
Testes unitários para FeedbackCollector.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from neural_hive_specialists.feedback import FeedbackCollector, FeedbackDocument
from neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def mock_config():
    """Configuração mock para testes."""
    return SpecialistConfig(
        specialist_type="technical",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="neural_hive_test",
        mongodb_opinions_collection="cognitive_ledger",
        feedback_mongodb_collection="specialist_feedback",
        enable_feedback_collection=True,
        feedback_rating_min=0.0,
        feedback_rating_max=1.0,
    )


@pytest.fixture
def mock_audit_logger():
    """AuditLogger mock."""
    return Mock()


@pytest.fixture
def feedback_collector(mock_config, mock_audit_logger):
    """Instância de FeedbackCollector com mocks."""
    with patch("neural_hive_specialists.feedback.feedback_collector.MongoClient"):
        collector = FeedbackCollector(mock_config, mock_audit_logger)
        collector._collection = MagicMock()
        collector._opinions_collection = MagicMock()
        # Mock circuit breaker para executar chamadas diretamente
        collector.breaker.call = Mock(side_effect=lambda fn: fn())
        return collector


@pytest.fixture
def sample_feedback_data():
    """Dados de feedback de teste."""
    return {
        "opinion_id": "opinion-test123",
        "plan_id": "plan-test456",
        "specialist_type": "technical",
        "human_rating": 0.9,
        "human_recommendation": "approve",
        "feedback_notes": "Análise correta e completa",
        "submitted_by": "reviewer@example.com",
    }


class TestFeedbackDocument:
    """Testes do schema FeedbackDocument."""

    def test_feedback_document_valid(self, sample_feedback_data):
        """Teste de criação de documento válido."""
        doc = FeedbackDocument(**sample_feedback_data)

        assert doc.opinion_id == "opinion-test123"
        assert doc.human_rating == 0.9
        assert doc.human_recommendation == "approve"
        assert doc.feedback_id.startswith("feedback-")

    def test_feedback_document_invalid_recommendation(self, sample_feedback_data):
        """Teste de recomendação inválida."""
        sample_feedback_data["human_recommendation"] = "invalid"

        with pytest.raises(ValueError, match="human_recommendation deve ser um de"):
            FeedbackDocument(**sample_feedback_data)

    def test_feedback_document_default_values(self):
        """Teste de valores padrão."""
        doc = FeedbackDocument(
            opinion_id="test",
            plan_id="test",
            specialist_type="technical",
            human_rating=0.5,
            human_recommendation="approve",
            submitted_by="test",
        )

        assert doc.schema_version == "1.0.0"
        assert doc.feedback_source == "human_expert"
        assert doc.feedback_notes == ""
        assert isinstance(doc.submitted_at, datetime)


class TestFeedbackCollector:
    """Testes do FeedbackCollector."""

    def test_validate_opinion_exists_true(self, feedback_collector):
        """Teste de validação quando opinião existe."""
        feedback_collector._opinions_collection.find_one.return_value = {
            "opinion_id": "test"
        }

        result = feedback_collector.validate_opinion_exists("test")

        assert result is True
        feedback_collector._opinions_collection.find_one.assert_called_once()

    def test_validate_opinion_exists_false(self, feedback_collector):
        """Teste de validação quando opinião não existe."""
        feedback_collector._opinions_collection.find_one.return_value = None

        result = feedback_collector.validate_opinion_exists("test")

        assert result is False

    def test_submit_feedback_success(self, feedback_collector, sample_feedback_data):
        """Teste de submissão bem-sucedida."""
        feedback_collector.validate_opinion_exists = Mock(return_value=True)
        feedback_collector._collection.insert_one = Mock()

        feedback_id = feedback_collector.submit_feedback(sample_feedback_data)

        assert feedback_id.startswith("feedback-")
        feedback_collector._collection.insert_one.assert_called_once()

    def test_submit_feedback_opinion_not_found(
        self, feedback_collector, sample_feedback_data
    ):
        """Teste de submissão quando opinião não existe."""
        feedback_collector.validate_opinion_exists = Mock(return_value=False)

        with pytest.raises(ValueError, match="não encontrada no ledger"):
            feedback_collector.submit_feedback(sample_feedback_data)

    def test_submit_feedback_missing_opinion_id(self, feedback_collector):
        """Teste de submissão sem opinion_id."""
        with pytest.raises(ValueError, match="opinion_id é obrigatório"):
            feedback_collector.submit_feedback({})

    def test_submit_feedback_invalid_rating(
        self, feedback_collector, sample_feedback_data, mock_config
    ):
        """Teste de submissão com rating inválido."""
        feedback_collector.validate_opinion_exists = Mock(return_value=True)
        sample_feedback_data["human_rating"] = 1.5  # Fora do range

        with pytest.raises(ValueError, match="Rating deve estar entre"):
            feedback_collector.submit_feedback(sample_feedback_data)

    def test_submit_feedback_audits_submission(
        self, feedback_collector, sample_feedback_data, mock_audit_logger
    ):
        """Teste de auditoria de submissão."""
        feedback_collector.validate_opinion_exists = Mock(return_value=True)
        feedback_collector._collection.insert_one = Mock()
        feedback_collector.audit_logger = mock_audit_logger

        feedback_collector.submit_feedback(sample_feedback_data)

        mock_audit_logger.log_data_access.assert_called_once()

    def test_get_feedback_by_opinion(self, feedback_collector):
        """Teste de busca de feedbacks por opinião."""
        mock_feedback = {
            "feedback_id": "test",
            "opinion_id": "opinion-test",
            "plan_id": "plan-test",
            "specialist_type": "technical",
            "human_rating": 0.9,
            "human_recommendation": "approve",
            "feedback_notes": "test",
            "submitted_by": "test",
            "submitted_at": datetime.utcnow(),
            "feedback_source": "human_expert",
            "metadata": {},
            "schema_version": "1.0.0",
        }

        feedback_collector._collection.find.return_value = [mock_feedback]

        feedbacks = feedback_collector.get_feedback_by_opinion("opinion-test")

        assert len(feedbacks) == 1
        assert feedbacks[0].opinion_id == "opinion-test"

    def test_count_recent_feedback(self, feedback_collector):
        """Teste de contagem de feedbacks recentes."""
        feedback_collector._collection.count_documents.return_value = 150

        count = feedback_collector.count_recent_feedback("technical", 7)

        assert count == 150
        feedback_collector._collection.count_documents.assert_called_once()

    def test_get_feedback_statistics(self, feedback_collector):
        """Teste de cálculo de estatísticas."""
        mock_feedbacks = [
            FeedbackDocument(
                opinion_id=f"test{i}",
                plan_id="plan",
                specialist_type="technical",
                human_rating=0.8 + i * 0.05,
                human_recommendation="approve" if i % 2 == 0 else "reject",
                submitted_by="test",
            )
            for i in range(5)
        ]

        feedback_collector.get_feedback_by_specialist = Mock(
            return_value=mock_feedbacks
        )

        stats = feedback_collector.get_feedback_statistics("technical", 30)

        assert stats["count"] == 5
        assert 0.0 <= stats["avg_rating"] <= 1.0
        assert "distribution" in stats
        assert "approve" in stats["distribution"]
        assert "reject" in stats["distribution"]

    def test_circuit_breaker_usage_on_insert(
        self, feedback_collector, sample_feedback_data
    ):
        """Teste que circuit breaker é usado em inserts."""
        feedback_collector.validate_opinion_exists = Mock(return_value=True)
        feedback_collector._collection.insert_one = Mock()

        feedback_collector.submit_feedback(sample_feedback_data)

        # Verificar que breaker.call foi chamado
        feedback_collector.breaker.call.assert_called()

    def test_circuit_breaker_usage_on_reads(self, feedback_collector):
        """Teste que circuit breaker é usado em reads."""
        feedback_collector._collection.find.return_value = []

        feedback_collector.get_feedback_by_opinion("test")

        # Verificar que breaker.call foi chamado para find
        feedback_collector.breaker.call.assert_called()

    def test_circuit_breaker_usage_on_count(self, feedback_collector):
        """Teste que circuit breaker é usado em count_documents."""
        feedback_collector._collection.count_documents.return_value = 0

        feedback_collector.count_recent_feedback("technical", 7)

        # Verificar que breaker.call foi chamado
        feedback_collector.breaker.call.assert_called()

    def test_get_opinion_metadata_success(self, feedback_collector):
        """Teste de get_opinion_metadata com sucesso."""
        feedback_collector._opinions_collection.find_one.return_value = {
            "plan_id": "plan-123",
            "specialist_type": "technical",
        }

        metadata = feedback_collector.get_opinion_metadata("opinion-test")

        assert metadata["plan_id"] == "plan-123"
        assert metadata["specialist_type"] == "technical"

    def test_get_opinion_metadata_not_found(self, feedback_collector):
        """Teste de get_opinion_metadata quando opinião não existe."""
        feedback_collector._opinions_collection.find_one.return_value = None

        with pytest.raises(ValueError, match="não encontrada no ledger"):
            feedback_collector.get_opinion_metadata("opinion-invalid")
