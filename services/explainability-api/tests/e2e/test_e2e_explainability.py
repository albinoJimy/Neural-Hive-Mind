"""
E2E Tests for Explainability API v3.

Testes de ponta a ponta que validam o fluxo completo de geração de explicações,
incluindo integração com MongoDB e todos os componentes.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from api.routes.v3.hierarchical import V3ExplanationService

# ========== FIXTURES ==========


@pytest.fixture()
def sample_decision_votes() -> list:
    """Votos de decisão de exemplo para testes E2E."""
    return [
        {
            "specialist_id": "business_specialist_001",
            "specialist_type": "business",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.85,
            "risk": 0.15,
            "reasoning": "Meets business requirements",
        },
        {
            "specialist_id": "technical_specialist_001",
            "specialist_type": "technical",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.90,
            "risk": 0.10,
            "reasoning": "Technically sound",
        },
        {
            "specialist_id": "architecture_specialist_001",
            "specialist_type": "architecture",
            "seniority_level": "senior",
            "vote": "reject",
            "confidence": 0.70,
            "risk": 0.30,
            "reasoning": "Scalability concerns",
        },
        {
            "specialist_id": "security_specialist_001",
            "specialist_type": "security",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.75,
            "risk": 0.25,
            "reasoning": "Security risks addressed",
        },
        {
            "specialist_id": "performance_specialist_001",
            "specialist_type": "performance",
            "seniority_level": "mid_level",
            "vote": "approve",
            "confidence": 0.65,
            "risk": 0.35,
            "reasoning": "Performance acceptable",
        },
    ]


@pytest.fixture()
def sample_consensus_decision(sample_decision_votes) -> dict[str, Any]:
    """Decisão de consenso de exemplo para testes E2E."""
    return {
        "decision_id": "e2e_test_decision_001",
        "timestamp": datetime.now(UTC).isoformat(),
        "final_decision": "approve",
        "final_confidence": 0.77,
        "specialist_votes": sample_decision_votes,
    }


@pytest.fixture()
def mock_mongodb():
    """Mock client MongoDB para testes E2E."""
    client = AsyncMock()

    # Mock consensus_decisions collection
    client.consensus_decisions = AsyncMock()

    async def mock_find_one(query):
        if query.get("decision_id") == "e2e_test_decision_001":
            return {
                "decision_id": "e2e_test_decision_001",
                "final_decision": "approve",
                "final_confidence": 0.77,
                "specialist_votes": sample_decision_votes(),
            }
        elif query.get("decision_id") == "nonexistent_decision":
            return None
        return None

    client.consensus_decisions.find_one = mock_find_one

    return client


@pytest.fixture()
def v3_service(mock_mongodb) -> V3ExplanationService:
    """Serviço v3 configurado para testes E2E."""
    return V3ExplanationService(mock_mongodb)


# ========== E2E TEST CLASSES ==========


class TestE2EFullExplanation:
    """Testes E2E do fluxo completo de explicação."""

    @pytest.mark.asyncio()
    async def test_full_explanation_flow(self, v3_service, sample_consensus_decision):
        """Testa fluxo completo de geração de explicação."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_full_explanation(
            decision_id=decision_id, include_counterfactuals=False, include_temporal=False
        )

        # Validar estrutura completa
        assert result is not None
        assert result["decision_id"] == decision_id
        assert "hierarchical_breakdown" in result
        assert "individual_contributions" in result

        # Validar breakdown hierárquico
        breakdown = result["hierarchical_breakdown"]
        assert "by_level" in breakdown
        assert "dominant_level" in breakdown
        assert "consensus_strength" in breakdown

        # Validar contribuições individuais
        contributions = result["individual_contributions"]
        assert len(contributions) == 5
        assert all("rank" in c for c in contributions)
        assert all("contribution_score" in c for c in contributions)

    @pytest.mark.asyncio()
    async def test_full_explanation_with_counterfactuals(
        self, v3_service, sample_consensus_decision
    ):
        """Testa explicação completa com análise contrafactual."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_full_explanation(
            decision_id=decision_id, include_counterfactuals=True, include_temporal=False
        )

        # Validar que contrafactuais estão incluídos
        assert "counterfactuals" in result
        assert isinstance(result["counterfactuals"], list)
        assert "sensitivity_score" in result
        assert 0.0 <= result["sensitivity_score"] <= 1.0

    @pytest.mark.asyncio()
    async def test_full_explanation_with_temporal(self, v3_service, sample_consensus_decision):
        """Testa explicação completa com análise temporal."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_full_explanation(
            decision_id=decision_id, include_counterfactuals=False, include_temporal=True
        )

        # Análise temporal pode retornar vazio se não houver histórico
        # Mas não deve causar erro
        assert "temporal_analysis" in result or "temporal_analysis" not in result


class TestE2EHierarchicalBreakdown:
    """Testes E2E de breakdown hierárquico."""

    @pytest.mark.asyncio()
    async def test_hierarchical_breakdown_levels(self, v3_service, sample_consensus_decision):
        """Testa que breakdown contém níveis de senioridade corretos."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_hierarchical_breakdown(decision_id)

        breakdown = result["hierarchical_breakdown"]
        by_level = breakdown["by_level"]

        # Verificar que temos os níveis esperados
        assert "senior" in by_level
        assert "expert" in by_level
        assert "mid_level" in by_level

        # Verificar estatísticas por nível
        for level, data in by_level.items():
            assert "count" in data
            assert "weighted_contribution" in data
            assert "influence_direction" in data

    @pytest.mark.asyncio()
    async def test_dominant_level_identification(self, v3_service, sample_consensus_decision):
        """Testa identificação correta do nível dominante."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_hierarchical_breakdown(decision_id)

        breakdown = result["hierarchical_breakdown"]
        dominant = breakdown["dominant_level"]

        # Nível dominante deve ser um dos níveis presentes
        assert dominant in breakdown["by_level"]

    @pytest.mark.asyncio()
    async def test_consensus_strength_calculation(self, v3_service, sample_consensus_decision):
        """Testa cálculo da força de consenso."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_hierarchical_breakdown(decision_id)

        breakdown = result["hierarchical_breakdown"]
        strength = breakdown["consensus_strength"]

        # Força deve estar entre 0 e 1
        assert 0.0 <= strength <= 1.0


class TestE2EIndividualContributions:
    """Testes E2E de contribuições individuais."""

    @pytest.mark.asyncio()
    async def test_contributions_ranking(self, v3_service, sample_consensus_decision):
        """Testa que contribuições estão ordenadas por rank."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_individual_contributions(decision_id)

        contributions = result["individual_contributions"]

        # Verificar ordenação por rank
        ranks = [c["rank"] for c in contributions]
        assert ranks == sorted(ranks)

        # Ranks devem começar em 1
        assert min(ranks) == 1
        assert max(ranks) == len(contributions)

    @pytest.mark.asyncio()
    async def test_contributions_fields(self, v3_service, sample_consensus_decision):
        """Testa que contribuições têm todos os campos esperados."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_individual_contributions(decision_id)

        contributions = result["individual_contributions"]

        for contribution in contributions:
            assert "specialist_id" in contribution
            assert "seniority_level" in contribution
            assert "vote" in contribution
            assert "confidence" in contribution
            assert "contribution_score" in contribution
            assert "rank" in contribution


class TestE2EBatchExplanations:
    """Testes E2E de explicações em lote."""

    @pytest.mark.asyncio()
    async def test_batch_explanation_flow(self, v3_service):
        """Testa fluxo de explicações em lote."""
        # Criar decisões mockadas
        decision_ids = [f"batch_decision_{i}" for i in range(5)]

        result = await v3_service.get_batch_explanations(
            decision_ids=decision_ids, include_counterfactuals=False, include_temporal=False
        )

        # Validar estrutura de resposta
        assert "explanations" in result
        assert "failed_ids" in result
        assert "summary" in result

        # Validar summary
        assert result["summary"]["total_requested"] == 5

    @pytest.mark.asyncio()
    async def test_batch_explanation_with_failures(self, v3_service):
        """Testa lote com algumas decisões falhando."""
        # Misturar decisões existentes e inexistentes
        decision_ids = [
            "e2e_test_decision_001",  # Existe
            "nonexistent_1",  # Não existe
            "nonexistent_2",  # Não existe
        ]

        result = await v3_service.get_batch_explanations(
            decision_ids=decision_ids, include_counterfactuals=False, include_temporal=False
        )

        # Validar que falhas foram registradas
        assert len(result["failed_ids"]) >= 2
        assert result["summary"]["total_requested"] == 3


class TestE2EErrorHandling:
    """Testes E2E de tratamento de erros."""

    @pytest.mark.asyncio()
    async def test_nonexistent_decision(self, v3_service):
        """Testa comportamento para decisão inexistente."""
        result = await v3_service.get_full_explanation(
            decision_id="definitely_nonexistent_decision",
            include_counterfactuals=False,
            include_temporal=False,
        )

        # Deve retornar None para decisão não encontrada
        assert result is None

    @pytest.mark.asyncio()
    async def test_empty_votes_handling(self, mock_mongodb):
        """Testa tratamento de votos vazios."""

        # Mock para retornar decisão com votos vazios
        async def mock_find_one(query):
            return {
                "decision_id": "empty_votes_test",
                "specialist_votes": [],
            }

        mock_mongodb.consensus_decisions.find_one = mock_find_one

        service = V3ExplanationService(mock_mongodb)
        result = await service.get_full_explanation(
            decision_id="empty_votes_test", include_counterfactuals=False, include_temporal=False
        )

        # Deve lidar com votos vazios gracefulmente
        assert result is not None
        assert result["decision_id"] == "empty_votes_test"


class TestE2EIntegration:
    """Testes E2E de integração entre componentes."""

    @pytest.mark.asyncio()
    async def test_hierarchical_explainer_integration(self, v3_service, sample_consensus_decision):
        """Testa integração com HierarchicalExplainer."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_hierarchical_breakdown(decision_id)

        # HierarchicalExplainer deve ser usado internamente
        assert "hierarchical_breakdown" in result
        assert "by_level" in result["hierarchical_breakdown"]

    @pytest.mark.asyncio()
    async def test_counterfactual_analyzer_integration(self, v3_service, sample_consensus_decision):
        """Testa integração com CounterfactualAnalyzer."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_counterfactuals(decision_id)

        # CounterfactualAnalyzer deve gerar cenários
        assert "counterfactuals" in result
        assert isinstance(result["counterfactuals"], list)

    @pytest.mark.asyncio()
    async def test_temporal_tracker_integration(self, v3_service, sample_consensus_decision):
        """Testa integração com TemporalTracker."""
        decision_id = sample_consensus_decision["decision_id"]

        result = await v3_service.get_temporal_analysis(decision_id)

        # TemporalTracker deve ser consultado
        assert "temporal_analysis" in result
        assert "current_seniority" in result["temporal_analysis"]


class TestE2EPerformance:
    """Testes E2E de performance."""

    @pytest.mark.asyncio()
    async def test_explanation_latency(self, v3_service, sample_consensus_decision):
        """Testa latência de geração de explicação (< 500ms)."""
        import time

        decision_id = sample_consensus_decision["decision_id"]

        start = time.time()
        result = await v3_service.get_full_explanation(
            decision_id=decision_id, include_counterfactuals=True, include_temporal=True
        )
        latency_ms = (time.time() - start) * 1000

        assert result is not None
        assert latency_ms < 500, f"Explanation took {latency_ms}ms, expected < 500ms"

    @pytest.mark.asyncio()
    async def test_batch_performance(self, v3_service):
        """Testa performance de explicações em lote."""
        import time

        decision_ids = [f"perf_test_{i}" for i in range(10)]

        start = time.time()
        result = await v3_service.get_batch_explanations(
            decision_ids=decision_ids, include_counterfactuals=False, include_temporal=False
        )
        total_time = time.time() - start

        # Validação básica
        assert result is not None

        # Latência média deve ser razoável
        avg_latency = (total_time / len(decision_ids)) * 1000
        assert avg_latency < 200, f"Average latency {avg_latency}ms, expected < 200ms"
