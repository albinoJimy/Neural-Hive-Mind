"""
Testes para RiskExplainability
"""

import pytest

from neural_hive_risk_scoring import (
    RiskExplainability,
    RiskExplanation,
    FactorContribution,
    WhatIfScenario,
    RiskScoringConfig,
    RiskBand,
    RiskAssessment,
    UnifiedDomain
)


@pytest.fixture
def config():
    """Configuração de teste."""
    return RiskScoringConfig()


@pytest.fixture
def explainability(config):
    """Serviço de explicabilidade de teste."""
    return RiskExplainability(config)


@pytest.fixture
def sample_assessment():
    """Avaliação de exemplo."""
    return RiskAssessment(
        score=0.75,
        band=RiskBand.HIGH,
        domain=UnifiedDomain.BUSINESS,
        factors={
            'priority': 0.9,
            'cost': 0.8,
            'complexity': 0.6,
            'kpi_alignment': 0.5
        },
        reasoning='High business risk due to priority and cost'
    )


class TestRiskExplainability:
    """Testes para RiskExplainability."""

    def test_init(self, explainability):
        """Testa inicialização."""
        assert explainability.config is not None

    def test_explain_assessment(self, explainability, sample_assessment):
        """Testa geração de explicação."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment,
            entity_id='test-entity'
        )

        assert explanation.entity_id == 'test-entity'
        assert explanation.domain == UnifiedDomain.BUSINESS
        assert explanation.final_score == 0.75
        assert explanation.final_band == RiskBand.HIGH
        assert len(explanation.factors) == 4

    def test_factor_contributions_ordering(self, explainability, sample_assessment):
        """Testa ordenação de fatores por contribuição."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment,
            entity_id='test-entity'
        )

        # Fatores devem estar ordenados por contribuição
        contributions = [f.contribution for f in explanation.factors]

        # Primeiro deve ter maior contribuição absoluta
        assert abs(contributions[0]) >= abs(contributions[-1])

    def test_factor_direction(self, explainability):
        """Testa direção dos fatores."""
        assessment = RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.TECHNICAL,
            factors={
                'code_quality': 0.9,  # Aumenta risco
                'scalability': 0.1,   # Diminui risco
                'performance': 0.5    # Neutro
            },
            reasoning='test'
        )

        explanation = explainability.explain_assessment(
            assessment=assessment,
            entity_id='test-entity'
        )

        # Verificar direções
        factor_dict = {f.name: f for f in explanation.factors}

        assert factor_dict['code_quality'].direction == 'increases_risk'
        assert factor_dict['scalability'].direction == 'decreases_risk'
        # performance pode ser neutral dependendo do peso

    def test_what_if_analysis(self, explainability, sample_assessment):
        """Testa análise what-if."""
        scenarios = {
            'reduce_priority': {'priority': 0.3},
            'reduce_cost': {'cost': 0.4},
            'both': {'priority': 0.3, 'cost': 0.4}
        }

        results = explainability.what_if_analysis(
            assessment=sample_assessment,
            entity_id='test-entity',
            scenarios=scenarios
        )

        assert len(results) == 3

        # Verificar estrutura
        for result in results:
            assert result.original_score == 0.75
            assert 0.0 <= result.new_score <= 1.0
            assert result.impact in ['significant', 'moderate', 'minimal']

    def test_compare_assessments(self, explainability):
        """Testa comparação de avaliações."""
        assessment1 = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={'priority': 0.5, 'cost': 0.5},
            reasoning='Medium risk'
        )

        assessment2 = RiskAssessment(
            score=0.8,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={'priority': 0.9, 'cost': 0.7},
            reasoning='High risk'
        )

        comparison = explainability.compare_assessments(
            assessment1=assessment1,
            assessment2=assessment2,
            entity_id='test-entity'
        )

        assert comparison['entity_id'] == 'test-entity'
        assert comparison['score1'] == 0.5
        assert comparison['score2'] == 0.8
        assert abs(comparison['score_delta'] - 0.3) < 0.0001  # Precisão de ponto flutuante
        assert comparison['band_changed'] == True

    def test_get_feature_importance(self, explainability):
        """Testa obtenção de importância de features."""
        importance = explainability.get_feature_importance(UnifiedDomain.BUSINESS)

        assert isinstance(importance, list)
        assert len(importance) > 0

        # Deve ter tuplas (feature, weight)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in importance)

        # Deve incluir fatores conhecidos
        feature_names = [name for name, _ in importance]
        assert 'priority' in feature_names
        assert 'cost' in feature_names

    def test_generate_recommendations(self, explainability, sample_assessment):
        """Testa geração de recomendações."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment,
            entity_id='test-entity'
        )

        recommendations = explainability.generate_recommendations(explanation)

        assert isinstance(recommendations, list)
        # Deve ter pelo menos uma recomendação para risco alto
        assert len(recommendations) >= 1

    def test_create_summary_report(self, explainability, sample_assessment):
        """Testa criação de relatório resumido."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment,
            entity_id='test-entity'
        )

        report = explainability.create_summary_report(explanation)

        assert isinstance(report, str)
        assert 'test-entity' in report
        assert '0.75' in report
        assert 'HIGH' in report
        assert '=== RELATÓRIO DE AVALIAÇÃO DE RISCO ===' in report

    def test_factor_contributions_sum(self, explainability, sample_assessment):
        """Testa que contribuições somam corretamente."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment,
            entity_id='test-entity'
        )

        # A soma das contribuições deve aproximar o ajuste total
        total_contribution = sum(f.contribution for f in explanation.factors)

        # Ajuste total deve ser próximo da soma das contribuições
        assert abs(total_contribution - explanation.total_adjustment) < 0.01

    def test_what_if_scenario_band_change(self, explainability):
        """Testa mudança de band em cenário what-if."""
        assessment = RiskAssessment(
            score=0.75,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={'priority': 0.9, 'cost': 0.9},
            reasoning='High risk'
        )

        scenarios = {
            'dramatic_reduction': {'priority': 0.1, 'cost': 0.1}
        }

        results = explainability.what_if_analysis(
            assessment=assessment,
            entity_id='test-entity',
            scenarios=scenarios
        )

        result = results[0]

        # Deve ter mudança significativa
        assert result.score_delta < 0  # Score diminuiu

    def test_explanation_with_low_risk(self, explainability):
        """Testa explicação com risco baixo."""
        assessment = RiskAssessment(
            score=0.2,
            band=RiskBand.LOW,
            domain=UnifiedDomain.SECURITY,
            factors={
                'security_level': 0.1,
                'pii_exposure': 0.2,
                'authentication': 0.3,
                'encryption': 0.2
            },
            reasoning='Low security risk'
        )

        explanation = explainability.explain_assessment(
            assessment=assessment,
            entity_id='test-entity'
        )

        assert explanation.final_band == RiskBand.LOW
        # A maioria dos fatores deve diminuir risco
        decreasing_factors = [
            f for f in explanation.factors
            if f.direction == 'decreases_risk'
        ]
        assert len(decreasing_factors) >= 2
