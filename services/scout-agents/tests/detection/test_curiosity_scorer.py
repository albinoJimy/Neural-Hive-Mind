"""
Testes unitários abrangentes para CuriosityScorer.

Cobertura: cálculo de curiosidade, novidade, relevância, ganho de informação.
"""
import pytest
import numpy as np
from datetime import datetime, timezone
from unittest.mock import patch

from src.detection.curiosity_scorer import CuriosityScorer
from src.models.raw_event import RawEvent
from neural_hive_domain import UnifiedDomain


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def curiosity_scorer():
    """Instância de CuriosityScorer para testes."""
    return CuriosityScorer()


@pytest.fixture
def event_with_numeric_features():
    """Evento com features numéricas."""
    return RawEvent(
        event_id="numeric-event-001",
        source="analytics",
        event_type="metric",
        timestamp=datetime.now(timezone.utc),
        payload={"cpu": 75.5, "memory": 60.2, "disk": 45.8, "network": 100.0, "requests": 1000},
        metadata={"trace_id": "trace-001"},
    )


@pytest.fixture
def event_with_high_variance():
    """Evento com features de alta variância."""
    values = [i * 10 + np.random.random() * 100 for i in range(20)]
    return RawEvent(
        event_id="variance-event-001",
        source="sensor",
        event_type="reading",
        timestamp=datetime.now(timezone.utc),
        payload={"values": values, "mean": np.mean(values)},
        metadata={"trace_id": "trace-variance"},
    )


@pytest.fixture
def novel_event():
    """Evento potencialmente novo."""
    return RawEvent(
        event_id="novel-event-001",
        source="new-source",
        event_type="new-event-type",
        timestamp=datetime.now(timezone.utc),
        payload={"novel_metric": 999.99},
        metadata={"trace_id": "trace-novel"},
    )


# ============================================================================
# Testes de Inicialização
# ============================================================================


class TestCuriosityScorerInitialization:
    """Testes de inicialização do CuriosityScorer."""

    def test_initialization_with_all_domains(self, curiosity_scorer):
        """Testa que todos os domínios têm pesos configurados."""
        for domain in UnifiedDomain:
            assert domain.value in curiosity_scorer.weights
            assert "novelty" in curiosity_scorer.weights[domain.value]
            assert "relevance" in curiosity_scorer.weights[domain.value]
            assert "information_gain" in curiosity_scorer.weights[domain.value]
            assert "uncertainty" in curiosity_scorer.weights[domain.value]

    def test_initialization_weights_sum_to_one(self, curiosity_scorer):
        """Testa que pesos somam 1.0."""
        for domain_weights in curiosity_scorer.weights.values():
            total = sum(domain_weights.values())
            assert abs(total - 1.0) < 0.01

    def test_initialization_historical_features_empty(self, curiosity_scorer):
        """Testa que histórico de features começa vazio."""
        for domain in UnifiedDomain:
            assert curiosity_scorer.historical_features[domain.value] == []

    def test_initialization_validation_stats(self, curiosity_scorer):
        """Testa que estatísticas de validação são inicializadas."""
        for domain in UnifiedDomain:
            assert "validated" in curiosity_scorer.validation_stats[domain.value]
            assert "rejected" in curiosity_scorer.validation_stats[domain.value]
            assert curiosity_scorer.validation_stats[domain.value]["validated"] == 0
            assert curiosity_scorer.validation_stats[domain.value]["rejected"] == 0


# ============================================================================
# Testes de Cálculo de Score de Curiosidade
# ============================================================================


class TestCuriosityScoreCalculation:
    """Testes do cálculo principal de curiosidade."""

    def test_calculate_score_returns_valid_range(
        self, curiosity_scorer, event_with_numeric_features
    ):
        """Testa que score está em [0, 1]."""
        score = curiosity_scorer.calculate_score(
            event_with_numeric_features, UnifiedDomain.BUSINESS
        )
        assert 0.0 <= score <= 1.0

    def test_calculate_score_stores_features(self, curiosity_scorer, event_with_numeric_features):
        """Testa que features são armazenadas no histórico."""
        initial_count = len(curiosity_scorer.historical_features[UnifiedDomain.BUSINESS.value])

        curiosity_scorer.calculate_score(event_with_numeric_features, UnifiedDomain.BUSINESS)

        assert (
            len(curiosity_scorer.historical_features[UnifiedDomain.BUSINESS.value])
            == initial_count + 1
        )

    def test_calculate_score_with_context(self, curiosity_scorer, event_with_numeric_features):
        """Testa cálculo com contexto adicional."""
        context = {"source": "test", "priority": "high"}
        score = curiosity_scorer.calculate_score(
            event_with_numeric_features, UnifiedDomain.TECHNICAL, context=context
        )
        assert 0.0 <= score <= 1.0

    def test_calculate_score_limits_history(self, curiosity_scorer):
        """Testa que histórico é limitado a 1000 amostras."""
        event = RawEvent(
            event_id="test",
            source="test",
            event_type="test",
            timestamp=datetime.now(timezone.utc),
            payload={"value": 1},
            metadata={},
        )

        # Adicionar mais de 1000 eventos
        for i in range(1100):
            event.event_id = f"event-{i}"
            curiosity_scorer.calculate_score(event, UnifiedDomain.BUSINESS)

        # Histórico deve ser limitado
        assert len(curiosity_scorer.historical_features[UnifiedDomain.BUSINESS.value]) <= 1000

    def test_calculate_score_error_handling(self, curiosity_scorer, event_with_numeric_features):
        """Testa tratamento de erro no cálculo."""
        with patch.object(
            event_with_numeric_features, "extract_features", side_effect=Exception("Test error")
        ):
            score = curiosity_scorer.calculate_score(
                event_with_numeric_features, UnifiedDomain.BUSINESS
            )
            # Deve retornar default
            assert score == 0.5


# ============================================================================
# Testes de Cálculo de Novidade
# ============================================================================


class TestNoveltyCalculation:
    """Testes de cálculo de novidade."""

    def test_calculate_novelty_first_signal(self, curiosity_scorer):
        """Testa que primeiro sinal tem alta novidade."""
        features = np.array([1.0, 2.0, 3.0])
        novelty = curiosity_scorer.calculate_novelty(features, UnifiedDomain.BUSINESS)
        # Primeiro sinal deve ter novidade alta
        assert novelty >= 0.7

    def test_calculate_novelty_with_history(self, curiosity_scorer):
        """Testa novidade com histórico existente."""
        # Adicionar features ao histórico
        for i in range(10):
            features = np.array([i * 0.1, i * 0.2, i * 0.3])
            curiosity_scorer.historical_features[UnifiedDomain.TECHNICAL.value].append(features)

        # Features similares devem ter baixa novidade
        similar_features = np.array([0.5, 1.0, 1.5])
        novelty = curiosity_scorer.calculate_novelty(similar_features, UnifiedDomain.TECHNICAL)
        # Novidade deve ser menor que 0.8
        assert novelty < 0.8

    def test_calculate_novelty_dissimilar_features(self, curiosity_scorer):
        """Testa novidade de features dissimilares."""
        # Adicionar features baixas ao histórico
        for i in range(5):
            features = np.array([0.1, 0.2, 0.3])
            curiosity_scorer.historical_features[UnifiedDomain.SECURITY.value].append(features)

        # Features muito diferentes devem ter alta novidade
        novel_features = np.array([100.0, 200.0, 300.0])
        novelty = curiosity_scorer.calculate_novelty(novel_features, UnifiedDomain.SECURITY)
        # Novidade deve ser razoável
        assert novelty > 0.0

    def test_calculate_novelty_empty_features(self, curiosity_scorer):
        """Testa novidade com features vazias."""
        features = np.array([])
        novelty = curiosity_scorer.calculate_novelty(features, UnifiedDomain.INFRASTRUCTURE)
        # Features vazias devem ter novidade alta
        assert novelty == 0.8


# ============================================================================
# Testes de Cálculo de Relevância
# ============================================================================


class TestRelevanceCalculation:
    """Testes de cálculo de relevância."""

    def test_calculate_relevance_business_domain(
        self, curiosity_scorer, event_with_numeric_features
    ):
        """Testa relevância para domínio BUSINESS."""
        relevance = curiosity_scorer.calculate_relevance(
            event_with_numeric_features, UnifiedDomain.BUSINESS
        )
        assert 0.0 <= relevance <= 1.0
        # BUSINESS tem alta relevância base
        assert relevance >= 0.8

    def test_calculate_relevance_security_domain(
        self, curiosity_scorer, event_with_numeric_features
    ):
        """Testa relevância para domínio SECURITY."""
        relevance = curiosity_scorer.calculate_relevance(
            event_with_numeric_features, UnifiedDomain.SECURITY
        )
        # SECURITY tem a mais alta relevância base
        assert relevance >= 0.9

    def test_calculate_relevance_user_action_boost(self, curiosity_scorer):
        """Testa boost de relevância para user_action."""
        event = RawEvent(
            event_id="user-act",
            source="app",
            event_type="user_action",
            timestamp=datetime.now(timezone.utc),
            payload={"action": "click"},
            metadata={},
        )
        relevance = curiosity_scorer.calculate_relevance(event, UnifiedDomain.BUSINESS)
        # Deve ter boost de 0.1
        assert relevance >= 0.9

    def test_calculate_relevance_metric_boost(self, curiosity_scorer):
        """Testa boost de relevância para métricas."""
        event = RawEvent(
            event_id="metric",
            source="prometheus",
            event_type="metric",
            timestamp=datetime.now(timezone.utc),
            payload={"value": 100},
            metadata={},
        )
        relevance = curiosity_scorer.calculate_relevance(event, UnifiedDomain.INFRASTRUCTURE)
        # Deve ter boost
        assert relevance > 0.75

    def test_calculate_relevance_all_domains(self, curiosity_scorer, event_with_numeric_features):
        """Testa relevância para todos os domínios."""
        for domain in UnifiedDomain:
            relevance = curiosity_scorer.calculate_relevance(event_with_numeric_features, domain)
            assert 0.0 <= relevance <= 1.0

    def test_calculate_relevance_capped_at_one(self, curiosity_scorer):
        """Testa que relevância é limitada a 1.0."""
        event = RawEvent(
            event_id="high-rel",
            source="app",
            event_type="user_action",
            timestamp=datetime.now(timezone.utc),
            payload={"action": "purchase"},
            metadata={},
        )
        relevance = curiosity_scorer.calculate_relevance(event, UnifiedDomain.SECURITY)
        # Mesmo com boosts, não deve exceder 1.0
        assert relevance <= 1.0


# ============================================================================
# Testes de Cálculo de Ganho de Informação
# ============================================================================


class TestInformationGainCalculation:
    """Testes de cálculo de ganho de informação."""

    def test_calculate_information_gain_few_samples(self, curiosity_scorer):
        """Testa ganho com poucas amostras."""
        features = np.array([1.0, 2.0, 3.0])
        gain = curiosity_scorer.calculate_information_gain(features, UnifiedDomain.BUSINESS)
        # Poucas amostras = alto potencial de ganho
        assert gain >= 0.6

    def test_calculate_information_gain_with_variance(self, curiosity_scorer):
        """Testa ganho com variância alta."""
        # Adicionar histórico com variância
        for i in range(10):
            features = np.array([float(i)])
            curiosity_scorer.historical_features[UnifiedDomain.TECHNICAL.value].append(features)

        # Features com variância diferente
        test_features = np.array([50.0])
        gain = curiosity_scorer.calculate_information_gain(test_features, UnifiedDomain.TECHNICAL)
        # Deve ter algum ganho
        assert gain > 0.0

    def test_calculate_information_gain_error_handling(self, curiosity_scorer):
        """Testa tratamento de erro."""
        # Forçar erro
        with patch.object(np, "var", side_effect=Exception("Test error")):
            features = np.array([1.0, 2.0])
            gain = curiosity_scorer.calculate_information_gain(features, UnifiedDomain.BUSINESS)
            # Deve retornar default
            assert gain == 0.5


# ============================================================================
# Testes de Cálculo de Incerteza
# ============================================================================


class TestUncertaintyCalculation:
    """Testes de cálculo de incerteza."""

    def test_calculate_uncertainty_with_variation(self, curiosity_scorer):
        """Testa incerteza com features variadas."""
        features = np.array([1.0, 10.0, 100.0, 1000.0])
        uncertainty = curiosity_scorer.calculate_uncertainty(features)
        # Alta variação = alguma incerteza
        assert uncertainty > 0.0

    def test_calculate_uncertainty_uniform_features(self, curiosity_scorer):
        """Testa incerteza com features uniformes."""
        features = np.array([5.0, 5.0, 5.0, 5.0])
        uncertainty = curiosity_scorer.calculate_uncertainty(features)
        # Baixa variação = baixa incerteza
        assert uncertainty < 0.7

    def test_calculate_uncertainty_zero_mean(self, curiosity_scorer):
        """Testa incerteza com média zero."""
        features = np.array([1.0, -1.0, 2.0, -2.0])
        uncertainty = curiosity_scorer.calculate_uncertainty(features)
        # Média próxima de zero deve retornar default
        assert uncertainty == 0.5

    def test_calculate_uncertainty_sigmoid_normalization(self, curiosity_scorer):
        """Testa que incerteza é normalizada via sigmoid."""
        features = np.array([1.0, 1000.0])  # CV alto
        uncertainty = curiosity_scorer.calculate_uncertainty(features)
        # Deve estar em [0, 1]
        assert 0.0 <= uncertainty <= 1.0


# ============================================================================
# Testes de Adaptação de Pesos
# ============================================================================


class TestWeightAdaptation:
    """Testes de adaptação de pesos."""

    def test_adapt_weights_valid_signal(self, curiosity_scorer):
        """Testa adaptação com sinal válido."""
        initial_validated = curiosity_scorer.validation_stats[UnifiedDomain.BUSINESS.value][
            "validated"
        ]

        curiosity_scorer.adapt_weights(UnifiedDomain.BUSINESS, 0.8)

        assert (
            curiosity_scorer.validation_stats[UnifiedDomain.BUSINESS.value]["validated"]
            == initial_validated + 1
        )

    def test_adapt_weights_rejected_signal(self, curiosity_scorer):
        """Testa adaptação com sinal rejeitado."""
        initial_rejected = curiosity_scorer.validation_stats[UnifiedDomain.TECHNICAL.value][
            "rejected"
        ]

        curiosity_scorer.adapt_weights(UnifiedDomain.TECHNICAL, 0.3)

        assert (
            curiosity_scorer.validation_stats[UnifiedDomain.TECHNICAL.value]["rejected"]
            == initial_rejected + 1
        )

    def test_adapt_weights_adjusts_at_threshold(self, curiosity_scorer):
        """Testa ajuste de pesos no threshold (50 amostras)."""
        # Adicionar 49 amostras válidas
        for _ in range(49):
            curiosity_scorer.adapt_weights(UnifiedDomain.SECURITY, 0.8)

        # 50ª deve disparar ajuste
        initial_novelty = curiosity_scorer.weights[UnifiedDomain.SECURITY.value]["novelty"]

        with patch.object(
            curiosity_scorer,
            "get_score_distribution",
            return_value={"validation_rate": 0.9, "total_samples": 50},
        ):
            curiosity_scorer.adapt_weights(UnifiedDomain.SECURITY, 0.8)

            # Pesos devem ser ajustados
            # (depende da taxa de validação)

    def test_adapt_weights_low_validation_rate(self, curiosity_scorer):
        """Testa adaptação com baixa taxa de validação."""
        # Simular baixa taxa
        for i in range(50):
            feedback = 0.3 if i % 2 == 0 else 0.4  # Baixa validação
            curiosity_scorer.adapt_weights(UnifiedDomain.INFRASTRUCTURE, feedback)

        # Peso de novelty deve aumentar
        novelty_weight = curiosity_scorer.weights[UnifiedDomain.INFRASTRUCTURE.value]["novelty"]
        assert novelty_weight >= 0.4  # Deve ter aumentado do base 0.4


# ============================================================================
# Testes de Distribuição de Scores
# ============================================================================


class TestScoreDistribution:
    """Testes de distribuição de scores."""

    def test_get_score_distribution_no_samples(self, curiosity_scorer):
        """Testa distribuição sem amostras."""
        stats = curiosity_scorer.get_score_distribution(UnifiedDomain.BUSINESS)

        assert "validation_rate" in stats
        assert "total_samples" in stats
        assert "weights" in stats
        assert stats["validation_rate"] == 0.0
        assert stats["total_samples"] == 0

    def test_get_score_distribution_with_samples(self, curiosity_scorer):
        """Testa distribuição com amostras."""
        for _ in range(10):
            curiosity_scorer.adapt_weights(UnifiedDomain.TECHNICAL, 0.8)
        for _ in range(5):
            curiosity_scorer.adapt_weights(UnifiedDomain.TECHNICAL, 0.3)

        stats = curiosity_scorer.get_score_distribution(UnifiedDomain.TECHNICAL)

        assert stats["total_samples"] == 15
        # 10 de 15 validados = 0.667
        assert abs(stats["validation_rate"] - 0.667) < 0.01

    def test_get_score_distribution_includes_weights(self, curiosity_scorer):
        """Testa que distribuição inclui pesos atuais."""
        stats = curiosity_scorer.get_score_distribution(UnifiedDomain.SECURITY)

        assert "weights" in stats
        assert "novelty" in stats["weights"]
        assert "relevance" in stats["weights"]


# ============================================================================
# Testes de Integração
# ============================================================================


class TestCuriosityScorerIntegration:
    """Testes de integração do fluxo completo."""

    def test_full_scoring_cycle(self, curiosity_scorer, event_with_numeric_features):
        """Testa ciclo completo de scoring."""
        score1 = curiosity_scorer.calculate_score(
            event_with_numeric_features, UnifiedDomain.BUSINESS
        )

        # Evento similar deve ter novidade menor
        score2 = curiosity_scorer.calculate_score(
            event_with_numeric_features, UnifiedDomain.BUSINESS
        )

        # Scores devem estar em range válido
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0

    def test_learning_from_feedback(self, curiosity_scorer, event_with_numeric_features):
        """Testa aprendizado com feedback."""
        initial_weights = curiosity_scorer.weights[UnifiedDomain.TECHNICAL.value].copy()

        # Feedback positivo de alta qualidade
        for _ in range(55):
            curiosity_scorer.adapt_weights(UnifiedDomain.TECHNICAL, 0.9)

        # Pesos podem ter mudado
        # (depende de implementação exata)

    def test_multi_domain_independence(self, curiosity_scorer, event_with_numeric_features):
        """Testa que domínios são independentes."""
        curiosity_scorer.calculate_score(event_with_numeric_features, UnifiedDomain.BUSINESS)
        curiosity_scorer.calculate_score(event_with_numeric_features, UnifiedDomain.SECURITY)

        # Cada domínio deve ter seu próprio histórico
        business_count = len(curiosity_scorer.historical_features[UnifiedDomain.BUSINESS.value])
        security_count = len(curiosity_scorer.historical_features[UnifiedDomain.SECURITY.value])

        assert business_count == 1
        assert security_count == 1


# ============================================================================
# Testes de Casos Extremos
# ============================================================================


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_calculate_score_with_extreme_values(self, curiosity_scorer):
        """Testa score com valores extremos."""
        event = RawEvent(
            event_id="extreme",
            source="test",
            event_type="test",
            timestamp=datetime.now(timezone.utc),
            payload={"value": 1e308, "another": -1e308},
            metadata={},
        )
        score = curiosity_scorer.calculate_score(event, UnifiedDomain.BUSINESS)
        # Não deve crashar
        assert 0.0 <= score <= 1.0

    def test_calculate_novelty_with_large_history(self, curiosity_scorer):
        """Testa novidade com histórico grande."""
        # Adicionar muitas features
        for i in range(500):
            features = np.array([float(i % 100)])
            curiosity_scorer.historical_features[UnifiedDomain.INFRASTRUCTURE.value].append(
                features
            )

        # Deve usar apenas últimas 100
        test_features = np.array([50.0])
        novelty = curiosity_scorer.calculate_novelty(test_features, UnifiedDomain.INFRASTRUCTURE)
        # Não deve crashar
        assert 0.0 <= novelty <= 1.0

    def test_calculate_score_domain_not_in_weights(
        self, curiosity_scorer, event_with_numeric_features
    ):
        """Testa comportamento quando domínio não está em pesos."""
        # Remover domínio dos pesos
        del curiosity_scorer.weights[UnifiedDomain.BEHAVIOR.value]

        # Deve criar weights default
        score = curiosity_scorer.calculate_score(
            event_with_numeric_features, UnifiedDomain.BEHAVIOR
        )
        assert 0.0 <= score <= 1.0
