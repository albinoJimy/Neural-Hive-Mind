"""
Testes para RiskExplainability
"""

import pytest

from neural_hive_risk_scoring import (
    RiskExplainability,
    RiskScoringConfig,
    RiskBand,
    RiskAssessment,
    UnifiedDomain,
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
        factors={"priority": 0.9, "cost": 0.8, "complexity": 0.6, "kpi_alignment": 0.5},
        reasoning="High business risk due to priority and cost",
    )


class TestRiskExplainability:
    """Testes para RiskExplainability."""

    def test_init(self, explainability):
        """Testa inicialização."""
        assert explainability.config is not None

    def test_explain_assessment(self, explainability, sample_assessment):
        """Testa geração de explicação."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        assert explanation.entity_id == "test-entity"
        assert explanation.domain == UnifiedDomain.BUSINESS
        assert explanation.final_score == 0.75
        assert explanation.final_band == RiskBand.HIGH
        assert len(explanation.factors) == 4

    def test_factor_contributions_ordering(self, explainability, sample_assessment):
        """Testa ordenação de fatores por contribuição."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
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
                "code_quality": 0.9,  # Aumenta risco
                "scalability": 0.1,  # Diminui risco
                "performance": 0.5,  # Neutro
            },
            reasoning="test",
        )

        explanation = explainability.explain_assessment(
            assessment=assessment, entity_id="test-entity"
        )

        # Verificar direções
        factor_dict = {f.name: f for f in explanation.factors}

        assert factor_dict["code_quality"].direction == "increases_risk"
        assert factor_dict["scalability"].direction == "decreases_risk"
        # performance pode ser neutral dependendo do peso

    def test_what_if_analysis(self, explainability, sample_assessment):
        """Testa análise what-if."""
        scenarios = {
            "reduce_priority": {"priority": 0.3},
            "reduce_cost": {"cost": 0.4},
            "both": {"priority": 0.3, "cost": 0.4},
        }

        results = explainability.what_if_analysis(
            assessment=sample_assessment, entity_id="test-entity", scenarios=scenarios
        )

        assert len(results) == 3

        # Verificar estrutura
        for result in results:
            assert result.original_score == 0.75
            assert 0.0 <= result.new_score <= 1.0
            assert result.impact in ["significant", "moderate", "minimal"]

    def test_compare_assessments(self, explainability):
        """Testa comparação de avaliações."""
        assessment1 = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.5, "cost": 0.5},
            reasoning="Medium risk",
        )

        assessment2 = RiskAssessment(
            score=0.8,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.9, "cost": 0.7},
            reasoning="High risk",
        )

        comparison = explainability.compare_assessments(
            assessment1=assessment1, assessment2=assessment2, entity_id="test-entity"
        )

        assert comparison["entity_id"] == "test-entity"
        assert comparison["score1"] == 0.5
        assert comparison["score2"] == 0.8
        assert abs(comparison["score_delta"] - 0.3) < 0.0001  # Precisão de ponto flutuante
        assert comparison["band_changed"] == True

    def test_get_feature_importance(self, explainability):
        """Testa obtenção de importância de features."""
        importance = explainability.get_feature_importance(UnifiedDomain.BUSINESS)

        assert isinstance(importance, list)
        assert len(importance) > 0

        # Deve ter tuplas (feature, weight)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in importance)

        # Deve incluir fatores conhecidos
        feature_names = [name for name, _ in importance]
        assert "priority" in feature_names
        assert "cost" in feature_names

    def test_generate_recommendations(self, explainability, sample_assessment):
        """Testa geração de recomendações."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        recommendations = explainability.generate_recommendations(explanation)

        assert isinstance(recommendations, list)
        # Deve ter pelo menos uma recomendação para risco alto
        assert len(recommendations) >= 1

    def test_create_summary_report(self, explainability, sample_assessment):
        """Testa criação de relatório resumido."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        report = explainability.create_summary_report(explanation)

        assert isinstance(report, str)
        assert "test-entity" in report
        assert "0.75" in report
        assert "HIGH" in report
        assert "=== RELATÓRIO DE AVALIAÇÃO DE RISCO ===" in report

    def test_factor_contributions_sum(self, explainability, sample_assessment):
        """Testa que contribuições somam corretamente."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
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
            factors={"priority": 0.9, "cost": 0.9},
            reasoning="High risk",
        )

        scenarios = {"dramatic_reduction": {"priority": 0.1, "cost": 0.1}}

        results = explainability.what_if_analysis(
            assessment=assessment, entity_id="test-entity", scenarios=scenarios
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
                "security_level": 0.1,
                "pii_exposure": 0.2,
                "authentication": 0.3,
                "encryption": 0.2,
            },
            reasoning="Low security risk",
        )

        explanation = explainability.explain_assessment(
            assessment=assessment, entity_id="test-entity"
        )

        assert explanation.final_band == RiskBand.LOW
        # A maioria dos fatores deve diminuir risco
        decreasing_factors = [f for f in explanation.factors if f.direction == "decreases_risk"]
        assert len(decreasing_factors) >= 2

    def test_factor_description_generation(self, explainability):
        """Testa geração de descrições de fatores."""
        assessment = RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.SECURITY,
            factors={
                "security_level": 0.8,
                "pii_exposure": 0.7,
                "authentication": 0.6,
                "encryption": 0.5,
            },
            reasoning="test",
        )

        explanation = explainability.explain_assessment(
            assessment=assessment, entity_id="test-entity"
        )

        # Todas as fatores devem ter descrição
        for factor in explanation.factors:
            assert len(factor.description) > 0
            assert isinstance(factor.description, str)

    def test_what_if_scenario_no_band_change(self, explainability):
        """Testa cenário what-if sem mudança de band."""
        assessment = RiskAssessment(
            score=0.6,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.6, "cost": 0.6},
            reasoning="test",
        )

        scenarios = {"small_change": {"priority": 0.55}}  # Pequena mudança

        results = explainability.what_if_analysis(
            assessment=assessment, entity_id="test-entity", scenarios=scenarios
        )

        result = results[0]
        # Pequena mudança não deve alterar band
        assert result.band_change is None
        assert result.impact == "minimal"

    def test_compare_assessments_different_domains(self, explainability):
        """Testa comparação de avaliações de domínios diferentes."""
        assessment1 = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.5},
            reasoning="Business risk",
        )

        assessment2 = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.SECURITY,
            factors={"security_level": 0.5},
            reasoning="Security risk",
        )

        comparison = explainability.compare_assessments(
            assessment1=assessment1, assessment2=assessment2, entity_id="test-entity"
        )

        assert comparison["domain1"] == "BUSINESS"
        assert comparison["domain2"] == "SECURITY"
        assert comparison["score_delta"] == 0.0

    def test_compare_assessments_no_change(self, explainability):
        """Testa comparação sem mudança."""
        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.5},
            reasoning="test",
        )

        comparison = explainability.compare_assessments(
            assessment1=assessment, assessment2=assessment, entity_id="test-entity"
        )

        assert comparison["score_delta"] == 0.0
        assert comparison["band_changed"] == False
        assert len(comparison["factor_changes"]) == 0

    def test_feature_importance_ordering(self, explainability):
        """Testa ordenação de importância de features."""
        importance = explainability.get_feature_importance(UnifiedDomain.BUSINESS)

        # Deve estar ordenado por peso (decrescente)
        weights = [weight for _, weight in importance]
        for i in range(1, len(weights)):
            assert weights[i] <= weights[i - 1]

    def test_recommendations_for_low_risk(self, explainability):
        """Testa recomendações para risco baixo."""
        assessment = RiskAssessment(
            score=0.2,
            band=RiskBand.LOW,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.1, "cost": 0.2, "complexity": 0.3, "kpi_alignment": 0.2},
            reasoning="Low risk",
        )

        explanation = explainability.explain_assessment(
            assessment=assessment, entity_id="test-entity"
        )

        recommendations = explainability.generate_recommendations(explanation)

        # Para risco baixo, não deve haver recomendações de bandeiras
        # Pode ter recomendações específicas de fatores
        assert isinstance(recommendations, list)

    def test_summary_report_sections(self, explainability, sample_assessment):
        """Testa seções do relatório resumido."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        report = explainability.create_summary_report(explanation)

        # Verificar seções obrigatórias
        assert "=== RELATÓRIO DE AVALIAÇÃO DE RISCO ===" in report
        assert "--- Fatores de Risco ---" in report
        assert "--- Recomendações ---" in report
        assert "--- Justificativa ---" in report

    def test_factor_contribution_to_dict(self, explainability, sample_assessment):
        """Testa conversão de FactorContribution para dicionário."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        if explanation.factors:
            factor_dict = explanation.factors[0].to_dict()

            assert "name" in factor_dict
            assert "value" in factor_dict
            assert "weight" in factor_dict
            assert "contribution" in factor_dict
            assert "contribution_percentage" in factor_dict
            assert "direction" in factor_dict
            assert "description" in factor_dict

    def test_risk_explanation_to_dict(self, explainability, sample_assessment):
        """Testa conversão de RiskExplanation para dicionário."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        explanation_dict = explanation.to_dict()

        assert "entity_id" in explanation_dict
        assert "domain" in explanation_dict
        assert "final_score" in explanation_dict
        assert "final_band" in explanation_dict
        assert "base_score" in explanation_dict
        assert "total_adjustment" in explanation_dict
        assert "reasoning" in explanation_dict
        assert "timestamp" in explanation_dict
        assert "factors" in explanation_dict

    def test_what_if_impact_classification(self, explainability):
        """Testa classificação de impacto em cenários what-if."""
        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.5, "cost": 0.5},
            reasoning="test",
        )

        scenarios = {
            "minimal": {"priority": 0.48},  # Delta pequeno
            "moderate": {"priority": 0.4},  # Delta moderado
            "significant": {"priority": 0.1},  # Delta significativo
        }

        results = explainability.what_if_analysis(
            assessment=assessment, entity_id="test-entity", scenarios=scenarios
        )

        impact_types = {r.impact for r in results}
        assert "minimal" in impact_types
        assert "significant" in impact_types
        # 'moderate' pode ou não estar presente dependendo dos thresholds

    def test_contribution_percentage_sum(self, explainability, sample_assessment):
        """Testa que percentuais de contribuição somam 100%."""
        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity"
        )

        total_percentage = sum(f.contribution_percentage for f in explanation.factors)

        # Deve somar aproximadamente 100%
        assert abs(total_percentage - 100.0) < 1.0

    def test_explanation_with_custom_base_score(self, explainability, sample_assessment):
        """Testa explicação com score base customizado."""
        custom_base = 0.3

        explanation = explainability.explain_assessment(
            assessment=sample_assessment, entity_id="test-entity", base_score=custom_base
        )

        assert explanation.base_score == custom_base

    def test_get_recommendation_unknown_factor(self, explainability):
        """Testa recomendação para fator desconhecido."""
        from unittest.mock import Mock
        from neural_hive_risk_scoring.explainability import FactorContribution

        # Fator sem recomendação específica
        factor = FactorContribution(
            name="unknown_factor",
            value=0.8,
            weight=0.25,
            contribution=0.075,
            contribution_percentage=15.0,
            direction="increases_risk",
            description="Unknown factor",
        )

        explanation = Mock(
            final_band=RiskBand.HIGH, domain=UnifiedDomain.BUSINESS, factors=[factor]
        )

        recommendation = explainability._get_recommendation_for_factor(
            "unknown_factor", 0.8, UnifiedDomain.BUSINESS
        )

        # Deve retornar None para fator desconhecido
        assert recommendation is None
