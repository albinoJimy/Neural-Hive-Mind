"""
Testes para RiskCalculator
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from neural_hive_risk_scoring import (
    RiskCalculator,
    RiskScoringConfig,
    RiskBand,
    RiskAssessment,
    AggregationStrategy,
    UnifiedDomain
)


@pytest.fixture
def config():
    """Configuração de teste."""
    return RiskScoringConfig()


@pytest.fixture
def calculator(config):
    """Calculadora de teste."""
    return RiskCalculator(
        config=config,
        aggregation_strategy=AggregationStrategy.WEIGHTED_AVERAGE
    )


@pytest.fixture
def sample_assessments():
    """Avaliações de exemplo."""
    return [
        RiskAssessment(
            score=0.3,
            band=RiskBand.LOW,
            domain=UnifiedDomain.BUSINESS,
            factors={'priority': 0.2, 'cost': 0.4},
            reasoning='Low business risk'
        ),
        RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.TECHNICAL,
            factors={'code_quality': 0.7, 'performance': 0.7},
            reasoning='High technical risk'
        ),
        RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.SECURITY,
            factors={'security_level': 0.5, 'pii_exposure': 0.5},
            reasoning='Medium security risk'
        )
    ]


class TestRiskCalculator:
    """Testes para RiskCalculator."""

    def test_init(self, calculator):
        """Testa inicialização."""
        assert calculator.aggregation_strategy == AggregationStrategy.WEIGHTED_AVERAGE
        assert calculator.domain_weights is not None

    def test_calculate_aggregate_risk(self, calculator, sample_assessments):
        """Testa cálculo de risco agregado."""
        matrix = calculator.calculate_aggregate_risk(
            assessments=sample_assessments,
            entity_id='test-entity',
            entity_type='plan'
        )

        assert matrix.entity_id == 'test-entity'
        assert matrix.entity_type == 'plan'
        assert 0.0 <= matrix.overall_score <= 1.0
        assert matrix.overall_band in RiskBand
        assert len(matrix.assessments) == 3

    def test_empty_assessments(self, calculator):
        """Testa comportamento com avaliações vazias."""
        matrix = calculator.calculate_aggregate_risk(
            assessments=[],
            entity_id='empty-entity',
            entity_type='plan'
        )

        assert matrix.entity_id == 'empty-entity'
        assert matrix.overall_score == 0.0
        assert matrix.overall_band == RiskBand.LOW

    def test_weighted_average_aggregation(self, config):
        """Testa agregação por média ponderada."""
        calculator = RiskCalculator(
            config=config,
            aggregation_strategy=AggregationStrategy.WEIGHTED_AVERAGE
        )

        assessments = [
            RiskAssessment(
                score=0.2,
                band=RiskBand.LOW,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            ),
            RiskAssessment(
                score=0.8,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.TECHNICAL,
                factors={},
                reasoning='test'
            )
        ]

        matrix = calculator.calculate_aggregate_risk(
            assessments=assessments,
            entity_id='test',
            entity_type='plan'
        )

        # Com pesos padrão (0.25 cada), resultado deve ser próximo de 0.5
        assert 0.4 <= matrix.overall_score <= 0.6

    def test_maximum_aggregation(self, config):
        """Testa agregação por máximo."""
        calculator = RiskCalculator(
            config=config,
            aggregation_strategy=AggregationStrategy.MAXIMUM
        )

        assessments = [
            RiskAssessment(
                score=0.3,
                band=RiskBand.LOW,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            ),
            RiskAssessment(
                score=0.9,
                band=RiskBand.CRITICAL,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning='test'
            )
        ]

        matrix = calculator.calculate_aggregate_risk(
            assessments=assessments,
            entity_id='test',
            entity_type='plan'
        )

        # Máximo deve prevalecer
        assert matrix.overall_score == 0.9

    def test_calculate_domain_contribution(self, calculator, sample_assessments):
        """Testa cálculo de contribuição por domínio."""
        matrix = calculator.calculate_aggregate_risk(
            assessments=sample_assessments,
            entity_id='test',
            entity_type='plan'
        )

        contributions = calculator.calculate_domain_contribution(matrix)

        assert 'BUSINESS' in contributions
        assert 'TECHNICAL' in contributions
        assert 'SECURITY' in contributions

        for domain, contrib in contributions.items():
            assert 'score' in contrib
            assert 'contribution_ratio' in contrib
            assert 'contribution_percentage' in contrib

    def test_calculate_risk_velocity(self, calculator):
        """Testa cálculo de velocidade de risco."""
        now = datetime.utcnow()
        historical_scores = [
            (now, 0.3),
            (now + timedelta(hours=1), 0.5),
            (now + timedelta(hours=2), 0.7)
        ]

        velocity = calculator.calculate_risk_velocity(historical_scores)

        assert 'velocity' in velocity
        assert 'acceleration' in velocity
        assert 'trend_direction' in velocity
        assert velocity['trend_direction'] == 'increasing'

    def test_calculate_risk_velocity_insufficient_data(self, calculator):
        """Testa velocidade com dados insuficientes."""
        historical_scores = [(datetime.utcnow(), 0.5)]

        velocity = calculator.calculate_risk_velocity(historical_scores)

        assert velocity['velocity'] == 0.0
        assert velocity['trend_direction'] == 'stable'

    def test_geometric_mean_aggregation(self, config):
        """Testa agregação por média geométrica."""
        calculator = RiskCalculator(
            config=config,
            aggregation_strategy=AggregationStrategy.GEOMETRIC_MEAN
        )

        assessments = [
            RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            ),
            RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.TECHNICAL,
                factors={},
                reasoning='test'
            )
        ]

        matrix = calculator.calculate_aggregate_risk(
            assessments=assessments,
            entity_id='test',
            entity_type='plan'
        )

        # Média geométrica de 0.5 e 0.5 é 0.5
        assert abs(matrix.overall_score - 0.5) < 0.01

    def test_harmonic_mean_aggregation(self, config):
        """Testa agregação por média harmônica."""
        calculator = RiskCalculator(
            config=config,
            aggregation_strategy=AggregationStrategy.HARMONIC_MEAN
        )

        assessments = [
            RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            ),
            RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.TECHNICAL,
                factors={},
                reasoning='test'
            )
        ]

        matrix = calculator.calculate_aggregate_risk(
            assessments=assessments,
            entity_id='test',
            entity_type='plan'
        )

        # Média harmônica de 0.5 e 0.5 é 0.5
        assert abs(matrix.overall_score - 0.5) < 0.01
