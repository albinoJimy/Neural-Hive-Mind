"""
Testes de integração para Consenso Hierárquico (GAPS-03-06).

Estes testes validam o fluxo completo:
CognitivePlan → ConsensusOrchestrator → ConsolidatedDecision
com pesos hierárquicos aplicados.
"""

import sys
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest


# Mock neural_hive_domain BEFORE imports
class UnifiedDomain(str, Enum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    ARCHITECTURE = "ARCHITECTURE"
    SECURITY = "SECURITY"
    BEHAVIOR = "BEHAVIOR"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    OPERATIONAL = "OPERATIONAL"
    COMPLIANCE = "COMPLIANCE"


class DomainMapper:
    @staticmethod
    def normalize(domain_str, context):
        domain_map = {
            "BUSINESS": UnifiedDomain.BUSINESS,
            "business": UnifiedDomain.BUSINESS,
            "TECHNICAL": UnifiedDomain.TECHNICAL,
            "technical": UnifiedDomain.TECHNICAL,
            "ARCHITECTURE": UnifiedDomain.ARCHITECTURE,
            "architecture": UnifiedDomain.ARCHITECTURE,
            "BEHAVIOR": UnifiedDomain.BEHAVIOR,
            "behavior": UnifiedDomain.BEHAVIOR,
        }
        return domain_map.get(domain_str, UnifiedDomain.BUSINESS)


sys.modules["neural_hive_domain"] = MagicMock()
sys.modules["neural_hive_domain"].UnifiedDomain = UnifiedDomain
sys.modules["neural_hive_domain"].DomainMapper = DomainMapper

# Mock neural_hive_observability
mock_observability = MagicMock()
mock_tracer = MagicMock()
mock_span = MagicMock()
mock_span.__enter__ = MagicMock(return_value=mock_span)
mock_span.__exit__ = MagicMock(return_value=False)
mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
mock_observability.get_tracer = MagicMock(return_value=mock_tracer)
sys.modules["neural_hive_observability"] = mock_observability

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.models.consolidated_decision import (
    ConsensusMethod,
    DecisionType,
)
from src.services.consensus_orchestrator import ConsensusOrchestrator


@pytest.fixture()
def mock_config():
    """Configuração mock com consenso hierárquico habilitado."""
    config = Mock()
    config.enable_hierarchical_consensus = True
    config.specialist_seniority = {
        "business": "senior",
        "technical": "junior",
        "architecture": "expert",
        "behavior": "mid_level",
        "evolution": "mid_level",
    }
    config.domain_specialist_weights = {
        "business_BUSINESS": 0.25,
        "technical_TECHNICAL": 0.25,
        "architecture_ARCHITECTURE": 0.30,
    }
    config.min_confidence_score = 0.7
    config.max_divergence_threshold = 0.3
    config.critical_risk_threshold = 0.9
    config.enable_bayesian_averaging = True
    config.enable_pheromones = False  # Desabilitar para teste isolado
    config.bayesian_prior_weight = 0.1
    config.voting_weight_decay = 0.95
    config.require_unanimous_for_critical = True
    config.fallback_to_deterministic = True
    return config


@pytest.fixture()
def mock_pheromone_client():
    """Cliente de feromônios mock."""
    client = AsyncMock()
    client.calculate_dynamic_weight = AsyncMock(return_value=0.2)
    client.get_aggregated_pheromone = AsyncMock(return_value={"net_strength": 0.8})
    client.publish_pheromone = AsyncMock()
    return client


class TestHierarchicalConsensusIntegration:
    """Testes de integração do fluxo completo de consenso hierárquico."""

    @pytest.mark.asyncio()
    async def test_hierarchical_weights_applied_in_consensus(
        self, mock_config, mock_pheromone_client
    ):
        """Pesos hierárquicos devem ser aplicados corretamente no consenso."""
        orchestrator = ConsensusOrchestrator(mock_config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-hierarchical-001",
            "intent_id": "intent-001",
            "original_domain": "BUSINESS",
            "correlation_id": "corr-001",
            "trace_id": "trace-001",
        }

        specialist_opinions = [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.2,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
            {
                "specialist_type": "technical",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.75,
                    "risk_score": 0.3,
                    "recommendation": "approve",
                },
                "seniority_level": "junior",
                "processing_time_ms": 120,
            },
        ]

        # Act
        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        # Assert - Deve incluir campos hierárquicos
        assert decision.consensus_metrics.weighted_by_seniority is True
        assert decision.consensus_metrics.consensus_method_hierarchical is True
        assert decision.consensus_metrics.seniority_distribution == {"senior": 1, "junior": 1}

        # Votos devem ter campos de senioridade
        business_vote = next(
            v for v in decision.specialist_votes if v.specialist_type == "business"
        )
        technical_vote = next(
            v for v in decision.specialist_votes if v.specialist_type == "technical"
        )

        assert business_vote.seniority_level == "senior"
        assert business_vote.seniority_multiplier == 1.5
        assert technical_vote.seniority_level == "junior"
        assert technical_vote.seniority_multiplier == 0.75

        # Business (senior) deve ter peso maior que technical (junior)
        assert business_vote.weight > technical_vote.weight

    @pytest.mark.asyncio()
    async def test_expert_architecture_has_highest_weight(self, mock_config, mock_pheromone_client):
        """Expert architecture deve ter o maior peso no consenso."""
        orchestrator = ConsensusOrchestrator(mock_config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-arch-001",
            "intent_id": "intent-002",
            "original_domain": "ARCHITECTURE",
            "correlation_id": "corr-002",
        }

        specialist_opinions = [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.80,
                    "risk_score": 0.25,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
            {
                "specialist_type": "architecture",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.80,
                    "risk_score": 0.25,
                    "recommendation": "approve",
                },
                "seniority_level": "expert",
                "processing_time_ms": 150,
            },
        ]

        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        architecture_vote = next(
            v for v in decision.specialist_votes if v.specialist_type == "architecture"
        )
        business_vote = next(
            v for v in decision.specialist_votes if v.specialist_type == "business"
        )

        # Architecture (expert, no own domain) vs business (senior, no domain)
        # expert (2.0) vs senior (1.5)
        assert architecture_vote.seniority_multiplier == 2.0
        assert architecture_vote.weight > business_vote.weight

    @pytest.mark.asyncio()
    async def test_seniority_distribution_in_metrics(self, mock_config, mock_pheromone_client):
        """Métricas devem refletir distribuição de senioridade corretamente."""
        orchestrator = ConsensusOrchestrator(mock_config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-dist-001",
            "intent_id": "intent-003",
            "original_domain": "BUSINESS",
            "correlation_id": "corr-003",
        }

        specialist_opinions = [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.2,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
            {
                "specialist_type": "technical",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.75,
                    "risk_score": 0.3,
                    "recommendation": "approve",
                },
                "seniority_level": "junior",
                "processing_time_ms": 120,
            },
            {
                "specialist_type": "architecture",
                "opinion_id": "op-3",
                "opinion": {
                    "confidence_score": 0.90,
                    "risk_score": 0.1,
                    "recommendation": "approve",
                },
                "seniority_level": "expert",
                "processing_time_ms": 150,
            },
            {
                "specialist_type": "behavior",
                "opinion_id": "op-4",
                "opinion": {
                    "confidence_score": 0.70,
                    "risk_score": 0.3,
                    "recommendation": "approve",
                },
                "seniority_level": "mid_level",
                "processing_time_ms": 110,
            },
        ]

        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        # Verificar distribuição de senioridade
        assert decision.consensus_metrics.seniority_distribution == {
            "senior": 1,
            "junior": 1,
            "expert": 1,
            "mid_level": 1,
        }

    @pytest.mark.asyncio()
    async def test_hierarchical_disabled_uses_base_weights(self, mock_pheromone_client):
        """Quando hierarquia desabilitada, deve usar pesos base."""
        config = Mock()
        config.enable_hierarchical_consensus = False
        config.specialist_seniority = {}
        config.domain_specialist_weights = {}
        config.min_confidence_score = 0.7
        config.max_divergence_threshold = 0.3
        config.critical_risk_threshold = 0.9
        config.enable_bayesian_averaging = True
        config.enable_pheromones = False
        config.bayesian_prior_weight = 0.1
        config.voting_weight_decay = 0.95
        config.require_unanimous_for_critical = True
        config.fallback_to_deterministic = True

        orchestrator = ConsensusOrchestrator(config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-no-hier-001",
            "intent_id": "intent-004",
            "original_domain": "BUSINESS",
            "correlation_id": "corr-004",
        }

        specialist_opinions = [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.2,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
            {
                "specialist_type": "technical",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.75,
                    "risk_score": 0.3,
                    "recommendation": "approve",
                },
                "seniority_level": "trainee",
                "processing_time_ms": 120,
            },
        ]

        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        # Não deve usar pesos hierárquicos
        assert decision.consensus_metrics.weighted_by_seniority is False
        assert decision.consensus_metrics.consensus_method_hierarchical is False

        # Pesos devem ser iguais (base 0.2)
        business_vote = next(
            v for v in decision.specialist_votes if v.specialist_type == "business"
        )
        technical_vote = next(
            v for v in decision.specialist_votes if v.specialist_type == "technical"
        )

        assert business_vote.weight == technical_vote.weight == 0.2

    @pytest.mark.asyncio()
    async def test_avro_serialization_includes_hierarchical_fields(
        self, mock_config, mock_pheromone_client
    ):
        """Serialização Avro deve incluir campos hierárquicos."""
        orchestrator = ConsensusOrchestrator(mock_config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-avro-001",
            "intent_id": "intent-005",
            "original_domain": "BUSINESS",
            "correlation_id": "corr-005",
        }

        specialist_opinions = [
            {
                "specialist_type": "business",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.2,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
        ]

        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        # Converter para Avro
        avro_dict = decision.to_avro_dict()

        # Verificar campos hierárquicos nos votos
        vote_dict = avro_dict["specialist_votes"][0]
        assert "seniority_level" in vote_dict
        assert vote_dict["seniority_level"] == "senior"
        assert "seniority_multiplier" in vote_dict
        assert vote_dict["seniority_multiplier"] == 1.5

        # Verificar campos hierárquicos nas métricas
        metrics_dict = avro_dict["consensus_metrics"]
        assert "weighted_by_seniority" in metrics_dict
        assert metrics_dict["weighted_by_seniority"] is True
        assert "seniority_distribution" in metrics_dict
        assert metrics_dict["seniority_distribution"] == {"senior": 1}
        assert "consensus_method_hierarchical" in metrics_dict
        assert metrics_dict["consensus_method_hierarchical"] is True


class TestHierarchicalConsensusScenarios:
    """Cenários realísticos de consenso hierárquico."""

    @pytest.mark.asyncio()
    async def test_unanimous_experts_approve_quickly(self, mock_config, mock_pheromone_client):
        """Cenário: Especialistas experts unanimam aprovação."""
        orchestrator = ConsensusOrchestrator(mock_config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-unanimous-001",
            "intent_id": "intent-006",
            "original_domain": "ARCHITECTURE",
            "correlation_id": "corr-006",
        }

        specialist_opinions = [
            {
                "specialist_type": "architecture",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.95,
                    "risk_score": 0.05,
                    "recommendation": "approve",
                },
                "seniority_level": "expert",
                "processing_time_ms": 150,
            },
            {
                "specialist_type": "business",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.90,
                    "risk_score": 0.1,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
        ]

        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        # Deve ser APPROVE com alta confiança
        assert decision.final_decision == DecisionType.APPROVE
        assert decision.aggregated_confidence >= 0.85
        assert decision.consensus_method == ConsensusMethod.UNANIMOUS
        assert decision.consensus_metrics.unanimous is True

    @pytest.mark.asyncio()
    async def test_mixed_seniority_divergent_opinions(self, mock_config, mock_pheromone_client):
        """Cenário: Senioridade mista com opiniões divergentes."""
        orchestrator = ConsensusOrchestrator(mock_config, mock_pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-mixed-001",
            "intent_id": "intent-007",
            "original_domain": "BUSINESS",
            "correlation_id": "corr-007",
        }

        specialist_opinions = [
            {
                "specialist_type": "architecture",
                "opinion_id": "op-1",
                "opinion": {
                    "confidence_score": 0.60,
                    "risk_score": 0.4,
                    "recommendation": "review_required",
                },
                "seniority_level": "expert",
                "processing_time_ms": 150,
            },
            {
                "specialist_type": "business",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.90,
                    "risk_score": 0.1,
                    "recommendation": "approve",
                },
                "seniority_level": "senior",
                "processing_time_ms": 100,
            },
            {
                "specialist_type": "technical",
                "opinion_id": "op-3",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.15,
                    "recommendation": "approve",
                },
                "seniority_level": "junior",
                "processing_time_ms": 120,
            },
        ]

        decision = await orchestrator.process_consensus(cognitive_plan, specialist_opinions)

        # Expert tem peso maior, então divergência deve influenciar
        # Mas maioria aprova, então deve ser approve ou review_required
        assert decision.final_decision in [DecisionType.APPROVE, DecisionType.REVIEW_REQUIRED]
        assert not decision.consensus_metrics.unanimous
        assert decision.consensus_metrics.divergence_score > 0
