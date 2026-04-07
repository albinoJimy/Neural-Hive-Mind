"""
Testes unitários para HierarchicalExplainer.

TDD: Testes escritos antes da implementação (Explainability API v3 Task 3).
"""

from typing import Dict, Any
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.hierarchical_explainer import HierarchicalExplainer


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


class TestHierarchicalExplainerInitialization:
    """Testes de inicialização do explainer."""

    def test_initialization(self):
        """Testa que o explainer pode ser inicializado."""
        explainer = HierarchicalExplainer()
        assert explainer is not None


class TestByLevelBreakdown:
    """Testes do breakdown por nível de senioridade."""

    def test_calculate_by_level_breakdown_single_level(self):
        """Testa breakdown com opiniões de único nível."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("expert", "approve", 0.85, "technical"),
        ]

        result = explainer._calculate_by_level_breakdown(votes)

        assert "expert" in result
        assert result["expert"]["count"] == 2
        assert result["expert"]["weight_multiplier"] == 2.0
        assert result["expert"]["weighted_contribution"] > 0

    def test_calculate_by_level_breakdown_multiple_levels(self):
        """Testa breakdown com múltiplos níveis de senioridade."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
            create_vote("mid_level", "reject", 0.7, "architecture"),
        ]

        result = explainer._calculate_by_level_breakdown(votes)

        # Verificar que todos os níveis estão presentes
        assert "expert" in result
        assert "senior" in result
        assert "mid_level" in result

        # Verificar contagens
        assert result["expert"]["count"] == 1
        assert result["senior"]["count"] == 1
        assert result["mid_level"]["count"] == 1

        # Verificar multiplicadores
        assert result["expert"]["weight_multiplier"] == 2.0
        assert result["senior"]["weight_multiplier"] == 1.5
        assert result["mid_level"]["weight_multiplier"] == 1.0

    def test_calculate_by_level_breakdown_with_mixed_votes(self):
        """Testa breakdown com votos mistos (approve e reject)."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("expert", "reject", 0.7, "security"),
        ]

        result = explainer._calculate_by_level_breakdown(votes)

        assert result["expert"]["count"] == 2
        # weighted_contribution deve refletir o saldo dos votos
        assert "weighted_contribution" in result["expert"]

    def test_calculate_by_level_breakdown_empty_votes(self):
        """Testa breakdown com lista vazia de votos."""
        explainer = HierarchicalExplainer()

        result = explainer._calculate_by_level_breakdown([])

        assert result == {}

    def test_calculate_by_level_breakdown_includes_specialist_ids(self):
        """Testa que breakdown inclui IDs dos especialistas."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
        ]

        result = explainer._calculate_by_level_breakdown(votes)

        assert "business_expert" in result["expert"]["specialists"]
        assert "technical_senior" in result["senior"]["specialists"]

    def test_calculate_by_level_breakdown_includes_raw_votes(self):
        """Testa que breakdown inclui contagem de votos brutos."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("expert", "reject", 0.7, "security"),
        ]

        result = explainer._calculate_by_level_breakdown(votes)

        assert "raw_votes" in result["expert"]
        assert result["expert"]["raw_votes"]["approve"] == 1
        assert result["expert"]["raw_votes"]["reject"] == 1


class TestConsensusStrength:
    """Testes do cálculo de força de consenso."""

    def test_consensus_strength_unanimous(self):
        """Testa que consenso unânime retorna 1.0."""
        explainer = HierarchicalExplainer()

        by_level = {
            "expert": {
                "count": 1,
                "weighted_contribution": 1.8,
                "influence_direction": "approve",
            },
            "senior": {
                "count": 1,
                "weighted_contribution": 1.2,
                "influence_direction": "approve",
            },
        }

        strength = explainer._calculate_consensus_strength(by_level)

        assert strength == 1.0, f"Unanimous consensus should be 1.0, got {strength}"

    def test_consensus_strength_divided(self):
        """Testa que consenso dividido retorna valor aproximado a 0.33."""
        explainer = HierarchicalExplainer()

        by_level = {
            "expert": {
                "count": 1,
                "weighted_contribution": 1.8,
                "influence_direction": "approve",
            },
            "senior": {
                "count": 1,
                "weighted_contribution": -1.2,
                "influence_direction": "reject",
            },
            "mid_level": {
                "count": 1,
                "weighted_contribution": 0.0,
                "influence_direction": "neutral",
            },
        }

        strength = explainer._calculate_consensus_strength(by_level)

        # 3 níveis, 1 em cada direção (approve, reject, neutral) = 1/3 ≈ 0.33
        assert 0.32 <= strength <= 0.34, f"Divided consensus should be ~0.33, got {strength}"

    def test_consensus_strength_two_approve_one_reject(self):
        """Testa força de consenso com 2 approve e 1 reject."""
        explainer = HierarchicalExplainer()

        by_level = {
            "expert": {
                "count": 1,
                "weighted_contribution": 1.8,
                "influence_direction": "approve",
            },
            "senior": {
                "count": 1,
                "weighted_contribution": 1.2,
                "influence_direction": "approve",
            },
            "mid_level": {
                "count": 1,
                "weighted_contribution": -0.7,
                "influence_direction": "reject",
            },
        }

        strength = explainer._calculate_consensus_strength(by_level)

        # 2 approve, 1 reject = 2/3 ≈ 0.67
        assert 0.66 <= strength <= 0.68, f"2-1 consensus should be ~0.67, got {strength}"

    def test_consensus_strength_all_neutral(self):
        """Testa que todos neutrais retorna 1.0."""
        explainer = HierarchicalExplainer()

        by_level = {
            "expert": {
                "count": 1,
                "weighted_contribution": 0.0,
                "influence_direction": "neutral",
            },
            "senior": {
                "count": 1,
                "weighted_contribution": 0.0,
                "influence_direction": "neutral",
            },
        }

        strength = explainer._calculate_consensus_strength(by_level)

        assert strength == 1.0

    def test_consensus_strength_empty_by_level(self):
        """Testa que by_level vazio retorna 0.0."""
        explainer = HierarchicalExplainer()

        strength = explainer._calculate_consensus_strength({})

        assert strength == 0.0


class TestIndividualContributions:
    """Testes do cálculo de contribuições individuais."""

    def test_calculate_individual_contributions_single_specialist(self):
        """Testa contribuições com único especialista."""
        explainer = HierarchicalExplainer()

        votes = [create_vote("expert", "approve", 0.9, "business")]

        contributions = explainer._calculate_individual_contributions(votes)

        assert len(contributions) == 1
        assert contributions[0]["specialist_id"] == "business_expert"
        assert contributions[0]["seniority_level"] == "expert"
        assert contributions[0]["multiplier"] == 2.0
        assert contributions[0]["vote"] == "approve"
        assert contributions[0]["confidence"] == 0.9
        assert contributions[0]["rank"] == 1

    def test_calculate_individual_contributions_ranking(self):
        """Testa que especialistas são rankeados por contribuição."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("trainee", "approve", 0.8, "security"),
        ]

        contributions = explainer._calculate_individual_contributions(votes)

        # Expert com multiplier 2.0 deve ter rank mais alto que trainee com 0.5
        assert contributions[0]["rank"] == 1
        assert contributions[0]["seniority_level"] == "expert"
        assert contributions[1]["rank"] == 2
        assert contributions[1]["seniority_level"] == "trainee"

    def test_calculate_individual_contributions_includes_contribution_score(self):
        """Testa que contribuições incluem score calculado."""
        explainer = HierarchicalExplainer()

        votes = [create_vote("expert", "approve", 0.9, "business")]

        contributions = explainer._calculate_individual_contributions(votes)

        assert "contribution_score" in contributions[0]
        # Score deve ser positive para approve com alta confiança
        assert contributions[0]["contribution_score"] > 0

    def test_calculate_individual_contributions_empty_votes(self):
        """Testa que votos vazios retornam lista vazia."""
        explainer = HierarchicalExplainer()

        contributions = explainer._calculate_individual_contributions([])

        assert contributions == []


class TestFullExplanation:
    """Testes do pipeline completo de explicação hierárquica."""

    def test_explain_returns_hierarchical_breakdown(self):
        """Testa que explain retorna breakdown hierárquico completo."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
        ]

        result = explainer.explain(votes)

        assert "hierarchical_breakdown" in result
        assert "by_level" in result["hierarchical_breakdown"]
        assert "dominant_level" in result["hierarchical_breakdown"]
        assert "consensus_strength" in result["hierarchical_breakdown"]

    def test_explain_returns_individual_contributions(self):
        """Testa que explain retorna contribuições individuais."""
        explainer = HierarchicalExplainer()

        votes = [create_vote("expert", "approve", 0.9, "business")]

        result = explainer.explain(votes)

        assert "individual_contributions" in result
        assert len(result["individual_contributions"]) == 1
        assert result["individual_contributions"][0]["rank"] == 1

    def test_explain_handles_legacy_votes_without_seniority(self):
        """Testa que votos legados (sem seniority_level) usam default."""
        explainer = HierarchicalExplainer()

        # Voto legado sem campo de senioridade
        legacy_vote = {
            "specialist_id": "legacy_specialist",
            "specialist_name": "Legacy Specialist",
            "domain": "TECHNICAL",
            "vote": "approve",
            "confidence": 0.8,
            "risk": 0.2,
        }

        result = explainer.explain([legacy_vote])

        # Deve usar mid_level como default
        assert "hierarchical_breakdown" in result
        assert "mid_level" in result["hierarchical_breakdown"]["by_level"]
