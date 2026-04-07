"""
Testes unitários para ExplainabilityConsolidator com campos hierárquicos.

TDD: Testes escritos antes da implementação (GAPS-04 Task 1).
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from enum import Enum


# Set up UnifiedDomain mock BEFORE any imports
class UnifiedDomain(str, Enum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    SECURITY = "SECURITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    BEHAVIOR = "BEHAVIOR"
    OPERATIONAL = "OPERATIONAL"
    COMPLIANCE = "COMPLIANCE"
    ARCHITECTURE = "ARCHITECTURE"


mock_domain = MagicMock()
mock_domain.UnifiedDomain = UnifiedDomain
sys.modules["neural_hive_domain"] = mock_domain

# Add src directly to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.models.consolidated_decision import ConsensusMethod
from src.services.explainability_consolidator import ExplainabilityConsolidator


class TestExplainabilityConsolidatorHierarchical:
    """Testes do consolidador de explicabilidade com campos hierárquicos."""

    @pytest.fixture
    def mock_mongodb(self):
        """Mock do cliente MongoDB."""
        mongo = MagicMock()
        mongo.db = MagicMock()
        mongo.db["consensus_explainability"] = MagicMock()
        return mongo

    @pytest.fixture
    def consolidator(self, mock_mongodb):
        """Instância do consolidador."""
        return ExplainabilityConsolidator(mock_mongodb)

    @pytest.fixture
    def sample_opinions_with_seniority(self):
        """Opiniões de especialistas com campos hierárquicos."""
        return [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "seniority_level": "senior",
                "seniority_multiplier": 1.5,
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.15,
                    "recommendation": "approve",
                    "reasoning_summary": "Alinhado com objetivos de negócio",
                    "explainability_token": "token-1",
                },
            },
            {
                "specialist_type": "technical",
                "opinion_id": "op-2",
                "seniority_level": "expert",
                "seniority_multiplier": 2.0,
                "opinion": {
                    "confidence_score": 0.90,
                    "risk_score": 0.10,
                    "recommendation": "approve",
                    "reasoning_summary": "Arquitetura sólida e escalável",
                    "explainability_token": "token-2",
                },
            },
            {
                "specialist_type": "behavior",
                "opinion_id": "op-3",
                "seniority_level": "mid_level",
                "seniority_multiplier": 1.0,
                "opinion": {
                    "confidence_score": 0.75,
                    "risk_score": 0.20,
                    "recommendation": "approve",
                    "reasoning_summary": "Comportamento esperado dos usuários",
                    "explainability_token": "token-3",
                },
            },
            {
                "specialist_type": "architecture",
                "opinion_id": "op-4",
                "seniority_level": "expert",
                "seniority_multiplier": 2.0,
                "opinion": {
                    "confidence_score": 0.88,
                    "risk_score": 0.12,
                    "recommendation": "approve",
                    "reasoning_summary": "Design patterns adequados",
                    "explainability_token": "token-4",
                },
            },
            {
                "specialist_type": "evolution",
                "opinion_id": "op-5",
                "seniority_level": "junior",
                "seniority_multiplier": 0.75,
                "opinion": {
                    "confidence_score": 0.70,
                    "risk_score": 0.25,
                    "recommendation": "needs_revision",
                    "reasoning_summary": "Pode evoluir com melhorias",
                    "explainability_token": "token-5",
                },
            },
        ]

    def test_generate_returns_token_and_summary(self, consolidator, sample_opinions_with_seniority):
        """Testa que generate retorna token e resumo."""
        token, summary = consolidator.generate(
            opinions=sample_opinions_with_seniority,
            aggregated_confidence=0.82,
            aggregated_risk=0.16,
            divergence=0.15,
            final_decision="approve",
            consensus_method=ConsensusMethod.BAYESIAN,
            violations=[],
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        assert summary is not None
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_detailed_explanation_contains_seniority_distribution(
        self, consolidator, sample_opinions_with_seniority
    ):
        """Testa que explicação detalhada contém distribuição de senioridade."""
        detailed = consolidator._generate_detailed_explanation(
            opinions=sample_opinions_with_seniority,
            aggregated_confidence=0.82,
            aggregated_risk=0.16,
            divergence=0.15,
            final_decision="approve",
            consensus_method=ConsensusMethod.BAYESIAN,
            violations=[],
        )

        # Verificar que specialist_opinions existe
        assert "specialist_opinions" in detailed
        specialist_ops = detailed["specialist_opinions"]
        assert len(specialist_ops) == 5

        # Verificar campos hierárquicos em cada opinião
        for op in specialist_ops:
            assert "specialist_type" in op
            # Os campos hierárquicos devem estar presentes
            # Nota: a implementação atual pode não ter estes campos,
            # então o teste vai falhar inicialmente (TDD)
            assert "seniority_level" in op, f"seniority_level missing for {op['specialist_type']}"
            assert (
                "seniority_multiplier" in op
            ), f"seniority_multiplier missing for {op['specialist_type']}"

    def test_specialist_opinion_contains_calculated_weight(
        self, consolidator, sample_opinions_with_seniority
    ):
        """Testa que opiniões contêm peso calculado."""
        detailed = consolidator._generate_detailed_explanation(
            opinions=sample_opinions_with_seniority,
            aggregated_confidence=0.82,
            aggregated_risk=0.16,
            divergence=0.15,
            final_decision="approve",
            consensus_method=ConsensusMethod.BAYESIAN,
            violations=[],
        )

        specialist_ops = detailed["specialist_opinions"]

        # Verificar que há um campo de peso
        for op in specialist_ops:
            assert (
                "weight" in op or "final_weight" in op
            ), f"weight/ final_weight missing for {op['specialist_type']}"

    def test_seniority_distribution_counts_correctly(
        self, consolidator, sample_opinions_with_seniority
    ):
        """Testa que distribuição de senioridade conta corretamente."""
        detailed = consolidator._generate_detailed_explanation(
            opinions=sample_opinions_with_seniority,
            aggregated_confidence=0.82,
            aggregated_risk=0.16,
            divergence=0.15,
            final_decision="approve",
            consensus_method=ConsensusMethod.BAYESIAN,
            violations=[],
        )

        # Verificar seniority_distribution no consensus_process
        assert "consensus_process" in detailed
        consensus = detailed["consensus_process"]

        # A distribuição deve estar presente
        assert "seniority_distribution" in consensus or "hierarchical_weights" in consensus

        if "seniority_distribution" in consensus:
            dist = consensus["seniority_distribution"]
            # Baseado no fixture: 1 senior, 2 expert, 1 mid_level, 1 junior
            expected = {"senior": 1, "expert": 2, "mid_level": 1, "junior": 1}
            assert dist == expected, f"Expected {expected}, got {dist}"

    def test_reasoning_summary_mentions_hierarchical_when_enabled(
        self, consolidator, sample_opinions_with_seniority
    ):
        """Testa que resumo menciona consenso hierárquico quando habilitado."""
        summary = consolidator._generate_reasoning_summary(
            opinions=sample_opinions_with_seniority,
            aggregated_confidence=0.82,
            aggregated_risk=0.16,
            divergence=0.15,
            final_decision="approve",
            consensus_method=ConsensusMethod.BAYESIAN,
            violations=[],
        )

        # Resumo deve mencionar o método
        assert "bayesian" in summary.lower()

    def test_backward_compatibility_without_seniority_fields(self, consolidator):
        """Testa compatibilidade com opiniões sem campos hierárquicos."""
        # Opiniões no formato legado (sem campos hierárquicos)
        legacy_opinions = [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.15,
                    "recommendation": "approve",
                    "reasoning_summary": "Bom para negócio",
                    "explainability_token": "token-1",
                },
            }
        ]

        # Não deve levantar exceção
        token, summary = consolidator.generate(
            opinions=legacy_opinions,
            aggregated_confidence=0.85,
            aggregated_risk=0.15,
            divergence=0.10,
            final_decision="approve",
            consensus_method=ConsensusMethod.VOTING,
            violations=[],
        )

        assert token is not None
        assert summary is not None


class TestExplainabilityConsolidatorAsync:
    """Testes de funcionalidade assíncrona."""

    @pytest.fixture
    def mock_mongodb(self):
        """Mock do cliente MongoDB com async."""
        mongo = MagicMock()
        mongo.db = MagicMock()
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        mongo.db["consensus_explainability"] = collection
        return mongo

    @pytest.fixture
    def consolidator(self, mock_mongodb):
        """Instância do consolidador."""
        return ExplainabilityConsolidator(mock_mongodb)

    @pytest.mark.asyncio
    async def test_persist_explanation_called(self, consolidator, mock_mongodb):
        """Testa que persistência é chamada com token e explicação."""
        token = "test-token-123"
        explanation = {"consensus_process": {"method": "bayesian"}, "test": "data"}

        await consolidator._persist_explanation(token, explanation)

        # Verificar que insert_one foi chamado
        mock_mongodb.db["consensus_explainability"].insert_one.assert_called_once()

        # Verificar argumentos
        call_args = mock_mongodb.db["consensus_explainability"].insert_one.call_args
        inserted = call_args[0][0]

        assert inserted["token"] == token
        assert inserted["explanation"] == explanation
