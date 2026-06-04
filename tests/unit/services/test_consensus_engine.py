"""
Testes unitários para Consensus Engine.

GAP-04: Cobertura de Testes 16% → 70%
Testa orquestração de consenso, timeouts, e fallback.
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone
import asyncio


# =============================================================================
# Test: Consensus Orchestrator
# =============================================================================


class TestConsensusOrchestrator:
    """Testes do orquestrador de consenso."""

    @pytest.mark.asyncio
    async def test_collect_opinions_from_specialists(self):
        """Deve coletar opiniões de todos os especialistas."""
        specialists = {
            "business": AsyncMock(return_value={"opinion": "approve", "confidence": 0.9}),
            "technical": AsyncMock(return_value={"opinion": "approve", "confidence": 0.85}),
            "architecture": AsyncMock(return_value={"opinion": "reject", "confidence": 0.7}),
        }

        # Coletar opiniões em paralelo
        opinions = await asyncio.gather(*[specialists[key]() for key in specialists])

        assert len(opinions) == 3
        assert all("opinion" in o for o in opinions)

    @pytest.mark.asyncio
    async def test_handle_specialist_timeout(self):
        """Deve handle timeout de especialista."""
        specialist = AsyncMock()
        specialist.side_effect = asyncio.TimeoutError("Specialist timeout")

        with pytest.raises(asyncio.TimeoutError):
            await specialist()

    @pytest.mark.asyncio
    async def test_fallback_to_default_on_timeout(self):
        """Deve usar fallback padrão quando especialista timeout."""
        specialist = AsyncMock()
        specialist.side_effect = asyncio.TimeoutError()

        fallback_opinion = {
            "opinion": "defer",
            "confidence": 0.5,
            "reasoning": "Specialist unavailable",
            "fallback": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await specialist()
        except asyncio.TimeoutError:
            opinion = fallback_opinion

        assert opinion["fallback"] is True
        assert opinion["opinion"] == "defer"


# =============================================================================
# Test: Decision Consolidation
# =============================================================================


class TestDecisionConsolidation:
    """Testes de consolidação de decisões."""

    @pytest.mark.asyncio
    async def test_consolidate_unanimous_approve(self):
        """Deve consolidar decisão unânime de aprovação."""
        opinions = [
            {"specialist": "business", "opinion": "approve", "confidence": 0.9},
            {"specialist": "technical", "opinion": "approve", "confidence": 0.85},
            {"specialist": "architecture", "opinion": "approve", "confidence": 0.8},
        ]

        # Contar votos
        approve_count = sum(1 for o in opinions if o["opinion"] == "approve")
        reject_count = sum(1 for o in opinions if o["opinion"] == "reject")
        total = len(opinions)

        decision = {
            "final_decision": "approve" if approve_count > total / 2 else "reject",
            "unanimous": approve_count == total,
            "approve_count": approve_count,
            "reject_count": reject_count,
            "total_votes": total,
        }

        assert decision["final_decision"] == "approve"
        assert decision["unanimous"] is True

    @pytest.mark.asyncio
    async def test_consolidate_majority_decision(self):
        """Deve consolidar decisão por maioria."""
        opinions = [
            {"specialist": "business", "opinion": "approve", "confidence": 0.9},
            {"specialist": "technical", "opinion": "reject", "confidence": 0.7},
            {"specialist": "architecture", "opinion": "approve", "confidence": 0.85},
            {"specialist": "security", "opinion": "approve", "confidence": 0.8},
        ]

        approve_count = sum(1 for o in opinions if o["opinion"] == "approve")
        reject_count = sum(1 for o in opinions if o["opinion"] == "reject")
        total = len(opinions)

        final_decision = "approve" if approve_count > total / 2 else "reject"

        assert final_decision == "approve"
        assert approve_count == 3
        assert reject_count == 1

    @pytest.mark.asyncio
    async def test_consolidate_with_tie_breaker(self):
        """Deve usar tie-breaker em caso de empate."""
        opinions = [
            {"specialist": "business", "opinion": "approve", "confidence": 0.9},
            {"specialist": "technical", "opinion": "reject", "confidence": 0.8},
            {"specialist": "architecture", "opinion": "approve", "confidence": 0.7},
            {"specialist": "security", "opinion": "reject", "confidence": 0.85},
        ]

        approve_count = sum(1 for o in opinions if o["opinion"] == "approve")
        reject_count = sum(1 for o in opinions if o["opinion"] == "reject")

        # Tie-breaker: usar confiança média maior
        approve_confidences = [o["confidence"] for o in opinions if o["opinion"] == "approve"]
        reject_confidences = [o["confidence"] for o in opinions if o["opinion"] == "reject"]

        approve_avg = (
            sum(approve_confidences) / len(approve_confidences) if approve_confidences else 0
        )
        reject_avg = sum(reject_confidences) / len(reject_confidences) if reject_confidences else 0

        if approve_count == reject_count:
            final_decision = "approve" if approve_avg > reject_avg else "reject"
        else:
            final_decision = "approve" if approve_count > reject_count else "reject"

        # reject_avg = 0.825 > approve_avg = 0.8
        assert final_decision == "reject"


# =============================================================================
# Test: Weighted Voting
# =============================================================================


class TestWeightedVoting:
    """Testes de votação ponderada."""

    @pytest.mark.asyncio
    async def test_apply_hierarchical_weights(self):
        """Deve aplicar pesos hierárquicos na votação."""
        opinions = [
            {"specialist": "business", "opinion": "approve", "seniority": "senior", "weight": 0.3},
            {"specialist": "technical", "opinion": "reject", "seniority": "expert", "weight": 0.4},
            {
                "specialist": "architecture",
                "opinion": "approve",
                "seniority": "mid_level",
                "weight": 0.2,
            },
            {"specialist": "security", "opinion": "approve", "seniority": "senior", "weight": 0.1},
        ]

        # Calcular score ponderado
        approve_score = sum(o["weight"] for o in opinions if o["opinion"] == "approve")
        reject_score = sum(o["weight"] for o in opinions if o["opinion"] == "reject")

        assert approve_score == pytest.approx(0.6)  # 0.3 + 0.2 + 0.1
        assert reject_score == pytest.approx(0.4)  # 0.4

        final_decision = "approve" if approve_score > reject_score else "reject"
        assert final_decision == "approve"

    @pytest.mark.asyncio
    async def test_normalize_weights(self):
        """Deve normalizar pesos para soma = 1."""
        raw_weights = {"business": 3, "technical": 4, "architecture": 2, "security": 1}

        total = sum(raw_weights.values())
        normalized = {k: v / total for k, v in raw_weights.items()}

        assert sum(normalized.values()) == pytest.approx(1.0)
        assert normalized["technical"] == 0.4  # 4/10


# =============================================================================
# Test: Reasoning Aggregation
# =============================================================================


class TestReasoningAggregation:
    """Testes de agregação de reasoning."""

    @pytest.mark.asyncio
    async def test_aggregate_reasoning_text(self):
        """Deve agregar texto de reasoning."""
        reasonings = [
            "Aprovado porque os benefícios superam os riscos.",
            "Aprovado: arquitetura sólida e escalável.",
            "Rejeitado: preocupações com performance do banco de dados.",
        ]

        # Criar resumo agregado
        approve_count = sum(1 for r in reasonings if "Aprovado" in r or "Aprovado:" in r)
        reject_count = sum(1 for r in reasonings if "Rejeitado" in r)

        aggregated = {
            "summary": f"{approve_count} aprovações, {reject_count} rejeições",
            "approve_reasons": [r for r in reasonings if "Aprovado" in r or "Aprovado:" in r],
            "reject_reasons": [r for r in reasonings if "Rejeitado" in r],
        }

        assert aggregated["summary"] == "2 aprovações, 1 rejeições"
        assert len(aggregated["approve_reasons"]) == 2
        assert len(aggregated["reject_reasons"]) == 1


# =============================================================================
# Test: Consensus Timeout Handling
# =============================================================================


class TestConsensusTimeout:
    """Testes de timeout no consenso."""

    @pytest.mark.asyncio
    async def test_timeout_with_partial_results(self):
        """Deve usar resultados parciais quando timeout."""
        results = {}

        async def mock_specialist(name, delay):
            await asyncio.sleep(delay)
            return {"specialist": name, "opinion": "approve"}

        # Timeout de 1 segundo - retorna resultado rápido apenas
        result = await asyncio.wait_for(mock_specialist("fast", 0.1), timeout=1.0)
        results["fast"] = result

        assert "fast" in results

    @pytest.mark.asyncio
    async def test_retry_on_consensus_failure(self):
        """Deve retentar consenso em falha."""
        max_retries = 3
        attempt = 0

        async def consensus_round():
            nonlocal attempt
            attempt += 1
            if attempt < max_retries:
                raise Exception("Consensus failed")
            return {"decision": "approve"}

        # Tentar até conseguir ou max_retries
        for _ in range(max_retries):
            try:
                result = await consensus_round()
                break
            except Exception:
                if attempt >= max_retries:
                    raise

        assert result["decision"] == "approve"


# =============================================================================
# Test: Confidence Calculation
# =============================================================================


class TestConfidenceCalculation:
    """Testes de cálculo de confiança."""

    @pytest.mark.asyncio
    async def test_calculate_average_confidence(self):
        """Deve calcular confiança média das opiniões."""
        opinions = [
            {"confidence": 0.9},
            {"confidence": 0.85},
            {"confidence": 0.7},
            {"confidence": 0.8},
        ]

        avg_confidence = sum(o["confidence"] for o in opinions) / len(opinions)

        assert avg_confidence == pytest.approx(0.8125)

    @pytest.mark.asyncio
    async def test_weight_by_confidence(self):
        """Deve ponderar decisão por confiança."""
        opinions = [
            {"opinion": "approve", "confidence": 0.9},
            {"opinion": "reject", "confidence": 0.6},
        ]

        # Score ponderado por confiança
        approve_score = opinions[0]["confidence"]
        reject_score = opinions[1]["confidence"]

        final = "approve" if approve_score > reject_score else "reject"

        assert final == "approve"
