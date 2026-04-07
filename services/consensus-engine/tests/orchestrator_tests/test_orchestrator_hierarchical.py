"""
Testes de integração do ConsensusOrchestrator com consenso hierárquico.

TDD: Testes escritos antes da implementação (RED phase).
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from enum import Enum


# Mock neural_hive_domain BEFORE any imports
class UnifiedDomain(str, Enum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    SECURITY = "SECURITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    BEHAVIOR = "BEHAVIOR"
    OPERATIONAL = "OPERATIONAL"
    COMPLIANCE = "COMPLIANCE"
    ARCHITECTURE = "ARCHITECTURE"


class DomainMapper:
    @staticmethod
    def normalize(domain_str, context):
        return UnifiedDomain.BUSINESS


sys.modules["neural_hive_domain"] = MagicMock()
sys.modules["neural_hive_domain"].UnifiedDomain = UnifiedDomain
sys.modules["neural_hive_domain"].DomainMapper = DomainMapper

# Mock neural_hive_observability
mock_observability = MagicMock()
mock_tracer = MagicMock()
mock_tracer.start_as_current_span = MagicMock()
mock_tracer.__enter__ = MagicMock(return_value=mock_tracer)
mock_tracer.__exit__ = MagicMock(return_value=False)
mock_observability.get_tracer = MagicMock(return_value=mock_tracer)
sys.modules["neural_hive_observability"] = mock_observability

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))


class TestConsensusOrchestratorInitialization:
    """Testes de inicialização do ConsensusOrchestrator com hierarquia."""

    def test_orchestrator_has_hierarchical_calculator(self):
        """ConsensusOrchestrator deve inicializar HierarchicalWeightCalculator."""
        # Import directly via importlib to avoid circular import
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "services.consensus_orchestrator", src_path / "services" / "consensus_orchestrator.py"
        )
        consensus_module = importlib.util.module_from_spec(spec)

        # Mock dependencies before loading
        with patch("services.consensus_orchestrator.BayesianAggregator"):
            with patch("services.consensus_orchestrator.VotingEnsemble"):
                with patch("services.consensus_orchestrator.ComplianceFallback"):
                    spec.loader.exec_module(consensus_module)

        ConsensusOrchestrator = consensus_module.ConsensusOrchestrator

        config = Mock()
        config.enable_hierarchical_consensus = True
        config.specialist_seniority = {
            "business": "senior",
            "technical": "senior",
            "architecture": "expert",
        }
        config.domain_specialist_weights = {}

        pheromone_client = Mock()

        orchestrator = ConsensusOrchestrator(config, pheromone_client)

        # Deve ter o calculator inicializado
        assert hasattr(orchestrator, "hierarchical")
        print(f"✅ Hierarchical calculator: {orchestrator.hierarchical}")


class TestDynamicWeightsWithHierarchical:
    """Testes de _calculate_dynamic_weights com pesos hierárquicos."""

    @pytest.mark.asyncio
    async def test_uses_hierarchical_weights_when_enabled(self):
        """Quando habilitado, deve usar HierarchicalWeightCalculator."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "services.consensus_orchestrator", src_path / "services" / "consensus_orchestrator.py"
        )
        consensus_module = importlib.util.module_from_spec(spec)

        # Mock dependencies
        mock_bayesian = MagicMock()
        mock_voting = MagicMock()
        mock_compliance = MagicMock()

        with patch(
            "services.consensus_orchestrator.BayesianAggregator", return_value=mock_bayesian
        ):
            with patch("services.consensus_orchestrator.VotingEnsemble", return_value=mock_voting):
                with patch(
                    "services.consensus_orchestrator.ComplianceFallback",
                    return_value=mock_compliance,
                ):
                    spec.loader.exec_module(consensus_module)

        ConsensusOrchestrator = consensus_module.ConsensusOrchestrator

        config = Mock()
        config.enable_hierarchical_consensus = True
        config.specialist_seniority = {
            "business": "senior",
            "technical": "junior",
        }
        config.domain_specialist_weights = {}
        config.enable_pheromones = False

        pheromone_client = Mock()
        orchestrator = ConsensusOrchestrator(config, pheromone_client)

        cognitive_plan = {
            "plan_id": "plan-123",
            "intent_id": "intent-123",
            "original_domain": "BUSINESS",
        }

        specialist_opinions = [
            {
                "specialist_type": "business",
                "opinion": {"confidence_score": 0.85, "risk_score": 0.2},
            },
            {
                "specialist_type": "technical",
                "opinion": {"confidence_score": 0.75, "risk_score": 0.3},
            },
        ]

        weights = await orchestrator._calculate_dynamic_weights(cognitive_plan, specialist_opinions)

        # Pesos devem refletir senioridade hierárquica
        # business (senior, 1.5x) > technical (junior, 0.75x)
        assert weights["business"] > weights["technical"]
        print(f"✅ Pesos hierárquicos aplicados: {weights}")


class TestSpecialistVotesWithSeniority:
    """Testes de _build_specialist_votes com campos de senioridade."""

    def test_includes_seniority_fields_when_hierarchical_enabled(self):
        """Votos devem incluir campos de senioridade quando habilitado."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "services.consensus_orchestrator", src_path / "services" / "consensus_orchestrator.py"
        )
        consensus_module = importlib.util.module_from_spec(spec)

        with patch("services.consensus_orchestrator.BayesianAggregator"):
            with patch("services.consensus_orchestrator.VotingEnsemble"):
                with patch("services.consensus_orchestrator.ComplianceFallback"):
                    spec.loader.exec_module(consensus_module)

        ConsensusOrchestrator = consensus_module.ConsensusOrchestrator

        config = Mock()
        config.enable_hierarchical_consensus = True
        config.specialist_seniority = {
            "business": "senior",
            "technical": "expert",
        }

        pheromone_client = Mock()
        orchestrator = ConsensusOrchestrator(config, pheromone_client)

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
            },
            {
                "specialist_type": "technical",
                "opinion_id": "op-2",
                "opinion": {
                    "confidence_score": 0.90,
                    "risk_score": 0.1,
                    "recommendation": "approve",
                },
                "seniority_level": "expert",
            },
        ]

        weights = {"business": 0.85, "technical": 0.95}

        votes = orchestrator._build_specialist_votes(specialist_opinions, weights)

        # Verificar campos de senioridade
        assert votes[0].seniority_level == "senior"
        assert votes[0].seniority_multiplier == 1.5
        assert votes[1].seniority_level == "expert"
        assert votes[1].seniority_multiplier == 2.0
        print(f"✅ Campos de senioridade incluídos: seniority_level={votes[0].seniority_level}")
