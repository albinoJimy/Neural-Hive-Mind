"""
Testes para DatasetBalanceAnalyzer.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-17-active-learning-feedback/
"""

from unittest.mock import MagicMock

import pytest
from pymongo.collection import Collection

from neural_hive_specialists.feedback.active_learning.balance_analyzer import (
    BalanceMetrics,
    DatasetBalanceAnalyzer,
    PriorityRecommendation,
)


class TestDatasetBalanceAnalyzer:
    """Testes do DatasetBalanceAnalyzer."""

    @pytest.fixture()
    def mock_collection(self):
        """Mock da coleção specialist_feedback."""
        collection = MagicMock(spec=Collection)
        return collection

    @pytest.fixture()
    def analyzer(self, mock_collection):
        """Instância do DatasetBalanceAnalyzer."""
        return DatasetBalanceAnalyzer(mock_collection)

    @pytest.fixture()
    def sample_feedbacks(self):
        """Dados de feedback para testes."""
        return [
            # Approve cases (450 total = 93%)
            *[
                {
                    "feedback_id": f"f-{i}",
                    "human_recommendation": "approve",
                    "opinion_confidence": 0.8,
                    "nlp_features": {"primary_domain": "technical"},
                    "reasoning_factors": [{"factor_name": "semantic_security_analysis"}],
                }
                for i in range(10)
            ],
            # Reject cases (34 total = 7%)
            *[
                {
                    "feedback_id": f"r-{i}",
                    "human_recommendation": "reject",
                    "opinion_confidence": 0.5,
                    "nlp_features": {"primary_domain": "security"},
                    "reasoning_factors": [],
                }
                for i in range(3)
            ],
            # Low confidence (0.0-0.3)
            {
                "feedback_id": "low-1",
                "human_recommendation": "approve",
                "opinion_confidence": 0.2,
                "nlp_features": {"primary_domain": "business"},
                "reasoning_factors": [],
            },
            # Medium confidence (0.3-0.7)
            {
                "feedback_id": "med-1",
                "human_recommendation": "reject",
                "opinion_confidence": 0.5,
                "nlp_features": {"primary_domain": "technical"},
                "reasoning_factors": [],
            },
            # High confidence (0.7-1.0)
            {
                "feedback_id": "high-1",
                "human_recommendation": "approve",
                "opinion_confidence": 0.9,
                "nlp_features": {"primary_domain": "architecture"},
                "reasoning_factors": [{"factor_name": "semantic_architecture_analysis"}],
            },
        ]

    def test_analyzer_initialization(self, mock_collection):
        """Testa que o analyzer pode ser inicializado."""
        analyzer = DatasetBalanceAnalyzer(mock_collection)

        assert analyzer.collection is mock_collection
        assert analyzer.target_balance == pytest.approx(1.0 / 3.0)

    def test_calculate_balance_metrics_returns_metrics(self, analyzer, mock_collection):
        """Testa que calculate_balance_metrics retorna BalanceMetrics."""
        mock_collection.count_documents.return_value = 15

        # Setup aggregate para retornar dados válidos para cada chamada
        # Chamada 1: distribuição por classe
        # Chamada 2: distribuição por confiança
        # Chamada 3: distribuição por domínio
        # Chamada 4: features semânticas
        mock_collection.aggregate.side_effect = [
            # Chamada 1 (classe): retorna iterator
            iter([{"_id": "approve", "count": 10}, {"_id": "reject", "count": 5}]),
            # Chamada 2 (confiança): retorna iterator
            iter(
                [
                    {"opinion_confidence": 0.2},
                    {"opinion_confidence": 0.5},
                    {"opinion_confidence": 0.8},
                ]
            ),
            # Chamada 3 (domínio): retorna iterator
            iter(
                [
                    {"nlp_features": {"primary_domain": "technical"}},
                    {"nlp_features": {"primary_domain": "business"}},
                ]
            ),
            # Chamada 4 (semântica): retorna iterator
            iter(
                [
                    {"reasoning_factors": [{"factor_name": "semantic_security_analysis"}]},
                    {"reasoning_factors": []},
                ]
            ),
        ]

        metrics = analyzer.calculate_balance_metrics()

        assert isinstance(metrics, BalanceMetrics)
        assert metrics.total_feedbacks == 15
        assert "balance" in metrics.model_dump()
        assert "confidence_distribution" in metrics.model_dump()
        assert "domain_distribution" in metrics.model_dump()

    def test_balance_metrics_calculates_class_distribution(self, analyzer, mock_collection):
        """Testa cálculo de distribuição por classe (approve/reject)."""
        mock_collection.count_documents.return_value = 484

        # Mock aggregate para retornar contagem por classe
        mock_collection.aggregate.side_effect = [
            iter([{"_id": "approve", "count": 450}, {"_id": "reject", "count": 34}]),
            iter([]),  # confidence
            iter([]),  # domain
            iter([]),  # semantic
        ]

        metrics = analyzer.calculate_balance_metrics()

        assert metrics.balance["approve"]["count"] == 450
        assert metrics.balance["approve"]["percentage"] == pytest.approx(93.0, rel=0.1)
        assert metrics.balance["reject"]["count"] == 34
        assert metrics.balance["reject"]["percentage"] == pytest.approx(7.0, rel=0.1)
        assert metrics.balance["reject"]["gap"] > 0

    def test_confidence_distribution_calculates_correctly(self, analyzer, mock_collection):
        """Testa cálculo de distribuição por faixa de confiança."""
        # Mock aggregate para retornar feedbacks com confiança
        mock_collection.aggregate.return_value = [
            {"opinion_confidence": 0.2},  # low
            {"opinion_confidence": 0.5},  # medium
            {"opinion_confidence": 0.9},  # high
            {"opinion_confidence": None},  # sem confiança
        ]

        metrics = analyzer.calculate_balance_metrics()

        assert "low" in metrics.confidence_distribution
        assert "medium" in metrics.confidence_distribution
        assert "high" in metrics.confidence_distribution

    def test_domain_distribution_identifies_domains(self, analyzer, mock_collection):
        """Testa identificação de distribuição por domínio."""
        mock_collection.count_documents.return_value = 4

        mock_collection.aggregate.side_effect = [
            iter([]),  # class
            iter([]),  # confidence
            # domain - mas o projection retorna 'domain' não 'nlp_features'
            iter([{"domain": "technical"}, {"domain": "technical"}, {"domain": "security"}]),
            iter([]),  # semantic
        ]

        metrics = analyzer.calculate_balance_metrics()

        assert metrics.domain_distribution["technical"]["count"] == 2
        assert metrics.domain_distribution["technical"]["percentage"] == pytest.approx(
            50.0, rel=0.1
        )
        assert metrics.domain_distribution["security"]["count"] == 1

    def test_semantic_features_count_identifies_enriched_feedbacks(self, analyzer, mock_collection):
        """Testa contagem de feedbacks com features semânticas."""
        # 2 de 4 têm reasoning_factors com prefixo semantic_
        mock_collection.count_documents.return_value = 4

        mock_collection.aggregate.side_effect = [
            iter([]),  # class
            iter([]),  # confidence
            iter([]),  # domain
            # semantic
            iter(
                [
                    {"reasoning_factors": [{"factor_name": "semantic_security_analysis"}]},
                    {"reasoning_factors": [{"factor_name": "semantic_architecture_analysis"}]},
                    {"reasoning_factors": []},
                    {"reasoning_factors": [{"factor_name": "other_factor"}]},
                ]
            ),
        ]

        metrics = analyzer.calculate_balance_metrics()

        assert metrics.semantic_features_count == 2

    def test_priority_recommendations_identifies_underrepresented_classes(
        self, analyzer, mock_collection
    ):
        """Testa identificação de classes sub-representadas."""
        mock_collection.count_documents.return_value = 480

        # Configure mocks para aprovar muito, rejeitar pouco
        mock_collection.aggregate.side_effect = [
            # Primeira chamada: distribuição por classe
            iter([{"_id": "approve", "count": 450}, {"_id": "reject", "count": 30}]),
            # Segunda chamada: distribuição por confiança
            iter([]),
            # Terceira chamada: distribuição por domínio
            iter([]),
            # Quarta chamada: features semânticas
            iter([]),
        ]

        recommendations = analyzer.get_priority_recommendations()

        # Deve recomendar coletar mais rejects (gap > 3%)
        reject_recs = [r for r in recommendations if r.value == "reject"]
        assert len(reject_recs) > 0
        assert reject_recs[0].gap > 0

    def test_priority_recommendations_identifies_underrepresented_domains(
        self, analyzer, mock_collection
    ):
        """Testa identificação de domínios sub-representados."""
        mock_collection.count_documents.return_value = 100

        mock_collection.aggregate.side_effect = [
            iter([]),  # classes
            iter([]),  # confidence
            [  # domains - security com apenas 1 amostra
                {"domain": "technical"},
                {"domain": "technical"},
                {"domain": "security"},
            ],
            iter([]),  # semantic
        ]

        recommendations = analyzer.get_priority_recommendations()

        # Security deve ter alto gap (representado apenas 1x vs meta de 10%)
        domain_recs = [r for r in recommendations if r.type == "domain"]
        assert len(domain_recs) > 0

    def test_priority_recommendations_includes_confidence_gaps(self, analyzer, mock_collection):
        """Testa identificação de faixas de confiança sub-representadas."""
        mock_collection.aggregate.side_effect = [
            [],  # classes
            [  # confidence - nenhum high confidence
                {"opinion_confidence": 0.2},
                {"opinion_confidence": 0.5},
                {"opinion_confidence": 0.4},
            ],
            [],  # domains
        ]

        recommendations = analyzer.get_priority_recommendations()

        # Deve recomendar coletar mais high confidence
        confidence_recs = [r for r in recommendations if r.type == "confidence"]
        assert any(r.value == "high" for r in confidence_recs)

    def test_calculate_balance_metrics_handles_empty_collection(self, analyzer, mock_collection):
        """Testa comportamento com coleção vazia."""
        mock_collection.count_documents.return_value = 0
        mock_collection.aggregate.return_value = []

        metrics = analyzer.calculate_balance_metrics()

        assert metrics.total_feedbacks == 0
        assert metrics.balance == {}
        assert metrics.confidence_distribution == {}
        assert metrics.domain_distribution == {}
        assert metrics.semantic_features_count == 0

    def test_calculate_balance_metrics_handles_missing_fields(self, analyzer, mock_collection):
        """Testa tratamento de campos faltantes."""
        mock_collection.count_documents.return_value = 5
        mock_collection.aggregate.return_value = [
            {"human_recommendation": "approve", "opinion_confidence": None, "nlp_features": None},
            {"human_recommendation": None, "opinion_confidence": 0.5, "nlp_features": {}},
            {
                "human_recommendation": "reject",
                "opinion_confidence": 0.3,
                "nlp_features": {"primary_domain": "test"},
            },
            {"human_recommendation": "approve", "opinion_confidence": 0.8, "nlp_features": None},
            {"reasoning_factors": None},  # sem campos principais
        ]

        metrics = analyzer.calculate_balance_metrics()

        # Não deve crashar, deve tratar None como "unknown" ou ignorar
        assert metrics.total_feedbacks == 5


class TestBalanceMetrics:
    """Testes do modelo BalanceMetrics."""

    def test_balance_metrics_serialization(self):
        """Testa serialização para dict."""
        metrics = BalanceMetrics(
            total_feedbacks=100,
            balance={
                "approve": {"count": 70, "percentage": 70.0, "gap": 0.0},
                "reject": {"count": 30, "percentage": 30.0, "gap": 3.0},
            },
            confidence_distribution={
                "low": {"count": 20, "percentage": 20.0},
                "medium": {"count": 50, "percentage": 50.0},
                "high": {"count": 30, "percentage": 30.0},
            },
            domain_distribution={
                "technical": {"count": 40, "percentage": 40.0},
                "business": {"count": 30, "percentage": 30.0},
            },
            semantic_features_count=15,
            semantic_features_percentage=15.0,
            priority_recommendations=[],
        )

        data = metrics.model_dump()

        assert data["total_feedbacks"] == 100
        assert "balance" in data
        assert "priority_recommendations" in data


class TestPriorityRecommendation:
    """Testes do modelo PriorityRecommendation."""

    def test_priority_recommendation_creation(self):
        """Testa criação de recomendação de prioridade."""
        rec = PriorityRecommendation(
            type="class", value="reject", gap=40.0, reason="Sub-representado no dataset"
        )

        assert rec.type == "class"
        assert rec.value == "reject"
        assert rec.gap == 40.0
        assert rec.reason == "Sub-representado no dataset"

    def test_priority_recommendation_ordering_by_gap(self):
        """Testa ordenação de recomendações por gap."""
        recs = [
            PriorityRecommendation("class", "reject", gap=40.0),
            PriorityRecommendation("domain", "security", gap=20.0),
            PriorityRecommendation("confidence", "high", gap=50.0),
        ]

        sorted_recs = sorted(recs, key=lambda r: r.gap, reverse=True)

        assert sorted_recs[0].value == "high"
        assert sorted_recs[1].value == "reject"
        assert sorted_recs[2].value == "security"
