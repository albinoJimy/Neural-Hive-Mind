"""
Testes unitários para CounterfactualAnalyzer.

TDD: Testes escritos antes da implementação (Explainability API v3 Task 4).
"""

from typing import Dict, Any
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.counterfactual_analyzer import (
    CounterfactualAnalyzer,
    CounterfactualResult,
)


# Multiplicadores de senioridade (mesmos valores do consensus-engine)
SENIORITY_MULTIPLIERS = {
    "trainee": 0.5,
    "junior": 0.75,
    "mid_level": 1.0,
    "senior": 1.5,
    "expert": 2.0,
}


# Helper function para criar votos de teste
def create_vote(
    level: str, vote: str, confidence: float, specialist_id: str = "test"
) -> Dict[str, Any]:
    """
    Cria um voto de especialista para testes.

    Args:
        level: Nível de senioridade (trainee, junior, mid_level, senior, expert)
        vote: Voto (approve, reject)
        confidence: Confiança (0.0 a 1.0)
        specialist_id: ID do especialista

    Returns:
        Dicionário representando um voto
    """
    return {
        "specialist_id": f"{specialist_id}_{level}",
        "specialist_name": f"Test {level.title()}",
        "domain": "TECHNICAL",
        "seniority_level": level,
        "seniority_multiplier": SENIORITY_MULTIPLIERS.get(level, 1.0),
        "vote": vote,
        "confidence": confidence,
        "risk": 1.0 - confidence,
    }


class TestCounterfactualAnalyzerInitialization:
    """Testes de inicialização do analyzer."""

    def test_initialization(self):
        """Testa que o analyzer pode ser inicializado."""
        analyzer = CounterfactualAnalyzer()
        assert analyzer is not None


class TestEqualWeightsScenario:
    """Testes do cenário de pesos iguais."""

    def test_equal_weights_scenario(self):
        """Testa cenário equal weights com votos mistos."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "reject", 0.7, "technical"),
            create_vote("mid_level", "approve", 0.6, "architecture"),
        ]

        result = analyzer.analyze_equal_weights(votes)

        assert result.scenario_name == "equal_weights"
        assert result.outcome in ["approve", "reject", "neutral"]
        assert "weighted_score" in result.to_dict()
        assert len(result.breakdown) == 3

    def test_equal_weights_all_approve(self):
        """Testa equal weights com todos aprovando."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("trainee", "approve", 0.6, "security"),
        ]

        result = analyzer.analyze_equal_weights(votes)

        # Sem multiplicadores, soma deve ser positiva
        assert result.weighted_score > 0
        assert result.decision == "approve"

    def test_equal_weights_ignores_seniority(self):
        """Testa que equal weights ignora multiplicadores de senioridade."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.8, "business"),
            create_vote("trainee", "approve", 0.8, "security"),
        ]

        result = analyzer.analyze_equal_weights(votes)

        # Ambos devem ter multiplier 1.0 no breakdown
        assert all(v["multiplier"] == 1.0 for v in result.breakdown.values())

    def test_equal_weights_empty_votes(self):
        """Testa equal weights com lista vazia."""
        analyzer = CounterfactualAnalyzer()

        result = analyzer.analyze_equal_weights([])

        assert result.scenario_name == "equal_weights"
        assert result.outcome == "no_votes"
        assert result.decision == "neutral"
        assert result.weighted_score == 0.0


class TestNoTraineeScenario:
    """Testes do cenário sem trainees."""

    def test_no_trainee_filters_trainees(self):
        """Testa que no_trainee filtra opiniões de trainees."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("trainee", "reject", 0.7, "security"),
            create_vote("senior", "approve", 0.8, "technical"),
        ]

        result = analyzer.analyze_no_trainee(votes)

        # Apenas 2 especialistas no breakdown (expert e senior)
        assert len(result.breakdown) == 2
        assert "business_expert" in result.breakdown
        assert "technical_senior" in result.breakdown
        assert "security_trainee" not in result.breakdown

    def test_no_trainee_all_trainees(self):
        """Testa no_trainee quando todos são trainees."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("trainee", "approve", 0.7, "security"),
            create_vote("trainee", "approve", 0.6, "business"),
        ]

        result = analyzer.analyze_no_trainee(votes)

        assert result.scenario_name == "no_trainee"
        assert result.outcome == "all_trainees"
        assert result.decision == "neutral"

    def test_no_trainee_preserves_seniority_multipliers(self):
        """Testa que no_trainee mantém multiplicadores corretos."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
        ]

        result = analyzer.analyze_no_trainee(votes)

        # Expert deve ter multiplier 2.0
        assert result.breakdown["business_expert"]["multiplier"] == 2.0
        assert result.breakdown["business_expert"]["seniority_level"] == "expert"

    def test_no_trainee_empty_votes(self):
        """Testa no_trainee com lista vazia."""
        analyzer = CounterfactualAnalyzer()

        result = analyzer.analyze_no_trainee([])

        assert result.scenario_name == "no_trainee"
        assert result.outcome == "no_votes"
        assert result.decision == "neutral"


class TestSeniorityInversionScenario:
    """Testes do cenário de inversão de senioridade."""

    def test_seniority_inversion_flips_decision(self):
        """Testa que inversão pode mudar a decisão."""
        analyzer = CounterfactualAnalyzer()

        # Cenário: expert aprova com baixa confiança, trainee rejeita com alta
        # Com pesos normais: expert domina (approve)
        # Com pesos invertidos: trainee domina (reject)
        votes = [
            create_vote("expert", "approve", 0.6, "business"),
            create_vote("trainee", "reject", 0.9, "security"),
        ]

        result = analyzer.analyze_seniority_inversion(votes)

        assert result.scenario_name == "seniority_inversion"
        # Com inversão, trainee tem peso 2.0 e expert 0.5
        # Trainee: -0.9 * 2.0 = -1.8
        # Expert: 0.6 * 0.5 = 0.3
        # Total: -1.5 (reject)
        assert result.decision == "reject"

    def test_seniority_inversion_uses_inverted_multipliers(self):
        """Testa que inversão usa multiplicadores corretos."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.8, "business"),
            create_vote("trainee", "approve", 0.8, "security"),
        ]

        result = analyzer.analyze_seniority_inversion(votes)

        # Expert deve ter multiplier 0.5 (invertido)
        assert result.breakdown["business_expert"]["inverted_multiplier"] == 0.5
        # Trainee deve ter multiplier 2.0 (invertido)
        assert result.breakdown["security_trainee"]["inverted_multiplier"] == 2.0

    def test_seniority_inversion_shows_both_multipliers(self):
        """Testa que breakdown mostra ambos os multiplicadores."""
        analyzer = CounterfactualAnalyzer()

        votes = [create_vote("expert", "approve", 0.8, "business")]

        result = analyzer.analyze_seniority_inversion(votes)

        breakdown_data = result.breakdown["business_expert"]
        assert "normal_multiplier" in breakdown_data
        assert "inverted_multiplier" in breakdown_data
        assert breakdown_data["normal_multiplier"] == 2.0
        assert breakdown_data["inverted_multiplier"] == 0.5

    def test_seniority_inversion_empty_votes(self):
        """Testa seniority inversion com lista vazia."""
        analyzer = CounterfactualAnalyzer()

        result = analyzer.analyze_seniority_inversion([])

        assert result.scenario_name == "seniority_inversion"
        assert result.outcome == "no_votes"
        assert result.decision == "neutral"


class TestGenerateAllCounterfactuals:
    """Testes da geração de todos os cenários."""

    def test_generate_all_counterfactuals(self):
        """Testa geração de todos os cenários contrafactuais."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
            create_vote("trainee", "reject", 0.7, "security"),
        ]

        result = analyzer.generate_all_counterfactuals(votes)

        assert "scenarios" in result
        assert "original" in result["scenarios"]
        assert "equal_weights" in result["scenarios"]
        assert "no_trainee" in result["scenarios"]
        assert "seniority_inversion" in result["scenarios"]
        assert "sensitivity_analysis" in result

    def test_generate_all_counterfactuals_sensitivity_analysis(self):
        """Testa análise de sensibilidade nos cenários."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
        ]

        result = analyzer.generate_all_counterfactuals(votes)

        sensitivity = result["sensitivity_analysis"]
        assert "is_robust" in sensitivity
        assert "decision_flips" in sensitivity
        assert "flip_count" in sensitivity

    def test_generate_all_counterfactuals_detects_flips(self):
        """Testa que cenários detectam flips de decisão."""
        analyzer = CounterfactualAnalyzer()

        # Cenário onde inversão causa flip
        votes = [
            create_vote("expert", "approve", 0.6, "business"),
            create_vote("trainee", "reject", 0.9, "security"),
        ]

        result = analyzer.generate_all_counterfactuals(votes)

        sensitivity = result["sensitivity_analysis"]
        # Deve detectar pelo menos um flip
        assert sensitivity["flip_count"] >= 0

    def test_generate_all_counterfactuals_empty_votes(self):
        """Testa geração com lista vazia."""
        analyzer = CounterfactualAnalyzer()

        result = analyzer.generate_all_counterfactuals([])

        assert "scenarios" in result
        assert "sensitivity_analysis" in result


class TestCounterfactualResult:
    """Testes da classe CounterfactualResult."""

    def test_counterfactual_result_to_dict(self):
        """Testa conversão para dicionário."""
        result = CounterfactualResult(
            scenario_name="test_scenario",
            outcome="test_outcome",
            weighted_score=1.5,
            decision="approve",
            breakdown={"test": "data"},
        )

        result_dict = result.to_dict()

        assert result_dict["scenario_name"] == "test_scenario"
        assert result_dict["outcome"] == "test_outcome"
        assert result_dict["weighted_score"] == 1.5
        assert result_dict["decision"] == "approve"
        assert result_dict["breakdown"] == {"test": "data"}


class TestDecisionLogic:
    """Testes da lógica de decisão."""

    def test_make_decision_positive_score(self):
        """Testa que score positivo resulta em approve."""
        analyzer = CounterfactualAnalyzer()

        decision = analyzer._make_decision(1.5)
        assert decision == "approve"

    def test_make_decision_negative_score(self):
        """Testa que score negativo resulta em reject."""
        analyzer = CounterfactualAnalyzer()

        decision = analyzer._make_decision(-1.5)
        assert decision == "reject"

    def test_make_decision_zero_score(self):
        """Testa que score zero resulta em neutral."""
        analyzer = CounterfactualAnalyzer()

        decision = analyzer._make_decision(0.0)
        assert decision == "neutral"

    def test_calculate_original_score(self):
        """Testa cálculo de score original com multiplicadores."""
        analyzer = CounterfactualAnalyzer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("trainee", "reject", 0.7, "security"),
        ]

        # Expert: 0.9 * 2.0 = 1.8
        # Trainee: -0.7 * 0.5 = -0.35
        # Total: 1.45
        score = analyzer._calculate_original_score(votes)

        assert abs(score - 1.45) < 0.01
