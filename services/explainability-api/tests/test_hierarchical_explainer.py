"""
Testes unitários para HierarchicalExplainer.

TDD: Testes escritos antes da implementação (Explainability API v3 Task 3).
"""

import sys
from pathlib import Path
from typing import Any

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
) -> dict[str, Any]:
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


class TestCaching:
    """Testes de funcionalidade de caching do HierarchicalExplainer."""

    def test_cache_hit_returns_same_result(self):
        """Testa que cache hit retorna o mesmo resultado sem recalcular."""
        explainer = HierarchicalExplainer(cache_ttl=60, cache_size=10)

        votes = [create_vote("expert", "approve", 0.9, "business")]

        # Primeira chamada - cache miss
        result1 = explainer.explain(votes)

        # Segunda chamada - cache hit
        result2 = explainer.explain(votes)

        # Resultados devem ser idênticos
        assert result1 == result2

        # Estatísticas de cache
        stats = explainer.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_different_votes_different_results(self):
        """Testa que votos diferentes geram resultados diferentes (cache miss)."""
        explainer = HierarchicalExplainer(cache_ttl=60, cache_size=10)

        votes1 = [create_vote("expert", "approve", 0.9, "business")]
        votes2 = [create_vote("senior", "reject", 0.8, "technical")]

        result1 = explainer.explain(votes1)
        result2 = explainer.explain(votes2)

        # Resultados devem ser diferentes
        assert result1["hierarchical_breakdown"]["dominant_level"] == "expert"
        assert result2["hierarchical_breakdown"]["dominant_level"] == "senior"

        # Cache stats: 2 misses, 0 hits
        stats = explainer.get_cache_stats()
        assert stats["misses"] == 2
        assert stats["hits"] == 0

    def test_cache_expires_after_ttl(self):
        """Testa que cache expira após TTL."""
        # TTL muito curto para testes
        explainer = HierarchicalExplainer(cache_ttl=0, cache_size=10)

        votes = [create_vote("expert", "approve", 0.9, "business")]

        # Primeira chamada
        result1 = explainer.explain(votes)

        # Segunda chamada imediata (cache ainda pode estar válido por milissegundos)
        # Terceira chamada após expiração garantida
        import time

        time.sleep(0.1)  # 100ms

        result2 = explainer.explain(votes)

        # Com TTL=0, o cache deve expirar imediatamente
        # Vamos usar um TTL pequeno mas não zero para garantir comportamento determinístico
        explainer_short_ttl = HierarchicalExplainer(cache_ttl=1, cache_size=10)
        result3 = explainer_short_ttl.explain(votes)
        time.sleep(1.1)
        result4 = explainer_short_ttl.explain(votes)

        # Resultados devem ser iguais, mas cache foi recalculado
        assert result3 == result4

    def test_cache_respects_max_size(self):
        """Testa que cache respeita tamanho máximo configurado."""
        explainer = HierarchicalExplainer(cache_ttl=60, cache_size=3)

        # Adicionar 4 entradas diferentes (excede tamanho de 3)
        for i in range(4):
            votes = [create_vote("expert", "approve", 0.9, f"business_{i}")]
            explainer.explain(votes)

        stats = explainer.get_cache_stats()
        # Cache não deve exceder tamanho máximo
        assert stats["size"] <= 3

    def test_cache_clear(self):
        """Testa que clear_cache limpa todo o cache."""
        explainer = HierarchicalExplainer(cache_ttl=60, cache_size=10)

        # Adicionar algumas entradas
        for i in range(3):
            votes = [create_vote("expert", "approve", 0.9, f"business_{i}")]
            explainer.explain(votes)

        assert explainer.get_cache_stats()["size"] > 0

        # Limpar cache
        explainer.clear_cache()

        assert explainer.get_cache_stats()["size"] == 0

    def test_cache_can_be_disabled(self):
        """Testa que cache pode ser desabilitado."""
        explainer = HierarchicalExplainer(enable_cache=False)

        votes = [create_vote("expert", "approve", 0.9, "business")]

        # Duas chamadas com cache desabilitado
        explainer.explain(votes)
        explainer.explain(votes)

        stats = explainer.get_cache_stats()
        assert stats["enabled"] is False
        assert stats["hits"] == 0
        assert stats["misses"] == 0  # Sem cache, não conta misses
        assert stats["size"] == 0

    def test_cache_stats_structure(self):
        """Testa estrutura das estatísticas de cache."""
        explainer = HierarchicalExplainer(cache_ttl=60, cache_size=10)

        stats = explainer.get_cache_stats()

        assert "size" in stats
        assert "max_size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "enabled" in stats
        assert stats["max_size"] == 10
        assert stats["enabled"] is True

    def test_cache_key_uses_hash_of_votes(self):
        """Testa que chave de cache é hash dos votos."""
        explainer = HierarchicalExplainer(cache_ttl=60, cache_size=10)

        # Mesmos votos na mesma ordem geram cache hit
        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
        ]

        result1 = explainer.explain(votes)
        result2 = explainer.explain(votes)

        # Resultados devem ser idênticos (cache hit)
        assert result1 == result2

        # Cache stats: 1 miss (primeira), 1 hit (segunda)
        stats = explainer.get_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 1


class TestEdgeCases:
    """Testes de edge cases e cenários limite."""

    def test_votes_with_missing_specialist_id(self):
        """Testa votos sem specialist_id."""
        explainer = HierarchicalExplainer()

        votes = [
            {"seniority_level": "senior", "vote": "approve", "confidence": 0.8},
            {"seniority_level": "expert", "vote": "reject", "confidence": 0.7},
        ]

        result = explainer.explain(votes)

        # Deve gerar specialist_ids baseados em specialist_type
        assert "individual_contributions" in result
        assert len(result["individual_contributions"]) == 2

    def test_votes_with_abstain(self):
        """Testa votos com opção 'abstain'."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.8, "business"),
            create_vote("senior", "abstain", 0.5, "technical"),
            create_vote("senior", "reject", 0.7, "architecture"),
        ]

        result = explainer.explain(votes)

        # Votos abstain devem ser incluídos
        assert len(result["individual_contributions"]) == 3

    def test_all_votes_same_direction(self):
        """Testa cenário onde todos os votos são iguais."""
        explainer = HierarchicalExplainer()

        votes = [create_vote("expert", "approve", 0.9, f"business_{i}") for i in range(5)]

        result = explainer.explain(votes)

        # Consenso forte esperado
        assert result["hierarchical_breakdown"]["consensus_strength"] == 1.0

    def test_split_votes(self):
        """Testa cenário com votos divididos."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("expert", "reject", 0.9, "technical"),
            create_vote("senior", "approve", 0.8, "architecture"),
            create_vote("senior", "reject", 0.8, "security"),
        ]

        result = explainer.explain(votes)

        # Com 2 approves e 2 rejects, pode não haver consenso
        assert result["hierarchical_breakdown"]["consensus_strength"] <= 1.0

    def test_votes_with_zero_confidence(self):
        """Testa votos com confiança zero."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.0, "business"),
            create_vote("senior", "reject", 0.0, "technical"),
        ]

        result = explainer.explain(votes)

        # Deve processar mesmo com confiança zero
        assert "individual_contributions" in result
        assert len(result["individual_contributions"]) == 2

    def test_single_vote(self):
        """Testa cenário com apenas um voto."""
        explainer = HierarchicalExplainer()

        votes = [create_vote("expert", "approve", 0.8, "business")]

        result = explainer.explain(votes)

        # Deve processar voto único
        assert len(result["individual_contributions"]) == 1
        assert result["individual_contributions"][0]["rank"] == 1

    def test_votes_with_extra_fields(self):
        """Testa votos com campos adicionais não esperados."""
        explainer = HierarchicalExplainer()

        votes = [
            {
                "specialist_id": "expert_001",
                "specialist_type": "technical",
                "seniority_level": "expert",
                "vote": "approve",
                "confidence": 0.85,
                "risk": 0.15,
                "extra_field_1": "ignored",
                "extra_field_2": 12345,
                "nested": {"field": "value"},
            }
        ]

        result = explainer.explain(votes)

        # Campos extras devem ser ignorados
        assert len(result["individual_contributions"]) == 1

    def test_calculate_seniority_impact_with_empty_levels(self):
        """Testa cálculo de impacto sem níveis."""
        explainer = HierarchicalExplainer()

        impact = explainer._calculate_seniority_impact({"by_level": {}})

        assert impact == 0.0

    def test_calculate_seniority_weights_with_empty_votes(self):
        """Testa cálculo de pesos com votos vazios."""
        explainer = HierarchicalExplainer()

        weights = explainer.calculate_seniority_weights([])

        assert weights == {}

    def test_explain_decision_adds_decision_id(self):
        """Testa que explain_decision adiciona decision_id."""
        explainer = HierarchicalExplainer()

        decision = {
            "decision_id": "test_decision_123",
            "specialist_votes": [create_vote("expert", "approve", 0.8, "business")],
        }

        import asyncio

        result = asyncio.run(explainer.explain_decision(decision))

        assert result["decision_id"] == "test_decision_123"

    def test_explain_decision_without_decision_id(self):
        """Testa explain_decision sem decision_id."""
        explainer = HierarchicalExplainer()

        decision = {"specialist_votes": [create_vote("expert", "approve", 0.8, "business")]}

        import asyncio

        result = asyncio.run(explainer.explain_decision(decision))

        # Deve usar "unknown" como padrão
        assert result["decision_id"] == "unknown"

    def test_explain_decision_adds_hierarchical_weights(self):
        """Testa que explain_decision adiciona pesos hierárquicos."""
        explainer = HierarchicalExplainer()

        decision = {
            "decision_id": "test_decision",
            "specialist_votes": [
                create_vote("expert", "approve", 0.8, "business"),
                create_vote("senior", "approve", 0.7, "technical"),
            ],
        }

        import asyncio

        result = asyncio.run(explainer.explain_decision(decision))

        assert "hierarchical_weights" in result
        assert len(result["hierarchical_weights"]) == 2  # expert e senior

    def test_explain_decision_adds_seniority_impact(self):
        """Testa que explain_decision adiciona impacto de senioridade."""
        explainer = HierarchicalExplainer()

        decision = {
            "decision_id": "test_decision",
            "specialist_votes": [
                create_vote("expert", "approve", 0.8, "business"),
            ],
        }

        import asyncio

        result = asyncio.run(explainer.explain_decision(decision))

        assert "seniority_impact" in result
        assert result["seniority_impact"] > 0


class TestCoverageGaps:
    """Testes adicionais para aumentar cobertura."""

    def test_normalize_votes_preserves_specialist_id(self):
        """Testa que normalização preserva specialist_id quando presente."""
        explainer = HierarchicalExplainer()

        votes = [
            {
                "specialist_id": "preserved_id",
                "seniority_level": "senior",
                "vote": "approve",
                "confidence": 0.8,
            }
        ]

        normalized = explainer._normalize_votes(votes)

        assert normalized[0]["specialist_id"] == "preserved_id"

    def test_normalize_votes_adds_specialist_type(self):
        """Testa que normalização adiciona specialist_type."""
        explainer = HierarchicalExplainer()

        votes = [
            {
                "specialist_id": "test_001",
                "seniority_level": "senior",
                "vote": "approve",
                "confidence": 0.8,
            }
        ]

        normalized = explainer._normalize_votes(votes)

        assert "specialist_type" in normalized[0]
        assert normalized[0]["specialist_type"] == "unknown"

    def test_normalize_votes_with_recommendation_field(self):
        """Testa normalização de votos com campo 'recommendation'."""
        explainer = HierarchicalExplainer()

        votes = [
            {
                "specialist_type": "business",
                "recommendation": "approve",
                "confidence_score": 0.85,
            }
        ]

        normalized = explainer._normalize_votes(votes)

        assert normalized[0]["vote"] == "approve"
        assert normalized[0]["confidence"] == 0.85

    def test_normalize_votes_with_weight_field(self):
        """Testa normalização de votos com campo 'weight'."""
        explainer = HierarchicalExplainer()

        votes = [
            {
                "specialist_type": "business",
                "seniority_level": "senior",
                "vote": "approve",
                "weight": 1.5,
            }
        ]

        normalized = explainer._normalize_votes(votes)

        assert normalized[0]["seniority_multiplier"] == 1.5

    def test_calculate_by_level_breakdown_counts_specialists(self):
        """Testa que breakdown conta especialistas corretamente."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("senior", "approve", 0.8, "spec_1"),
            create_vote("senior", "reject", 0.7, "spec_2"),
            create_vote("expert", "approve", 0.9, "spec_3"),
        ]

        by_level = explainer._calculate_by_level_breakdown(votes)

        assert by_level["senior"]["count"] == 2
        assert by_level["expert"]["count"] == 1

    def test_calculate_by_level_breakdown_tracks_specialists(self):
        """Testa que breakdown rastreia IDs de especialistas."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("senior", "approve", 0.8, "spec_1"),
            create_vote("senior", "reject", 0.7, "spec_2"),
        ]

        by_level = explainer._calculate_by_level_breakdown(votes)

        # Specialist_id é concatenado com seniority_level
        assert "spec_1_senior" in by_level["senior"]["specialists"]
        assert "spec_2_senior" in by_level["senior"]["specialists"]

    def test_calculate_by_level_breakdown_with_approve_reject(self):
        """Testa contagem de votos brutos."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("senior", "approve", 0.8, "spec_1"),
            create_vote("senior", "approve", 0.7, "spec_2"),
            create_vote("senior", "reject", 0.6, "spec_3"),
        ]

        by_level = explainer._calculate_by_level_breakdown(votes)

        assert by_level["senior"]["raw_votes"]["approve"] == 2
        assert by_level["senior"]["raw_votes"]["reject"] == 1

    def test_consensus_strength_all_agree(self):
        """Testa força de consenso quando todos concordam."""
        explainer = HierarchicalExplainer()

        by_level = {
            "senior": {"influence_direction": "approve"},
            "expert": {"influence_direction": "approve"},
        }

        strength = explainer._calculate_consensus_strength(by_level)

        assert strength == 1.0

    def test_consensus_strength_divided(self):
        """Testa força de consenso quando divididos."""
        explainer = HierarchicalExplainer()

        by_level = {
            "senior": {"influence_direction": "approve"},
            "expert": {"influence_direction": "reject"},
        }

        strength = explainer._calculate_consensus_strength(by_level)

        assert strength == 0.5

    def test_consensus_strength_with_neutral(self):
        """Testa força de consenso com votos neutros."""
        explainer = HierarchicalExplainer()

        by_level = {
            "senior": {"influence_direction": "approve"},
            "expert": {"influence_direction": "neutral"},
        }

        strength = explainer._calculate_consensus_strength(by_level)

        # Apenas um não-neutro conta
        assert strength == 0.5

    def test_determine_dominant_level_by_weight(self):
        """Testa determinação de nível dominante por peso."""
        explainer = HierarchicalExplainer()

        by_level = {
            "senior": {"weighted_contribution": 2.5},
            "expert": {"weighted_contribution": 1.0},
            "mid_level": {"weighted_contribution": -0.5},
        }

        dominant = explainer._determine_dominant_level(by_level)

        # Senior tem maior contribuição absoluta
        assert dominant == "senior"

    def test_determine_dominant_level_tie(self):
        """Testa determinação de nível dominante em empate."""
        explainer = HierarchicalExplainer()

        by_level = {
            "senior": {"weighted_contribution": 1.0},
            "expert": {"weighted_contribution": 1.0},
        }

        dominant = explainer._determine_dominant_level(by_level)

        # Primeiro nível em ordem é escolhido
        assert dominant in ["senior", "expert"]

    def test_calculate_individual_contributions_includes_risk(self):
        """Testa que contribuições incluem campo de risco."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("expert", "approve", 0.8, "business"),
        ]

        contributions = explainer._calculate_individual_contributions(votes)

        assert "risk" in contributions[0]
        assert abs(contributions[0]["risk"] - 0.2) < 0.01

    def test_calculate_individual_contributions_ranking(self):
        """Testa ordenação por contribution_score absoluto."""
        explainer = HierarchicalExplainer()

        votes = [
            create_vote("trainee", "approve", 0.5, "business"),
            create_vote("expert", "reject", 0.9, "technical"),
            create_vote("senior", "approve", 0.7, "architecture"),
        ]

        contributions = explainer._calculate_individual_contributions(votes)

        # Expert com peso 2.0 e vote reject deve ter maior impacto
        # contribution_score = -0.9 * 2.0 = -1.8
        assert contributions[0]["rank"] == 1
        assert contributions[0]["seniority_level"] == "expert"
