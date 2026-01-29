"""
Testes unitários para validação de propagação de correlation_id no ConsensusOrchestrator.

Verifica que o correlation_id é corretamente propagado do plano cognitivo para a
decisão consolidada, com geração de UUID fallback quando ausente ou vazio.
"""

import pytest
import uuid

from src.services.consensus_orchestrator import ConsensusOrchestrator
from src.models.consolidated_decision import ConsolidatedDecision, DecisionType


# Fixtures específicas para testes de correlation_id (não duplicadas do conftest.py)

@pytest.fixture
def cognitive_plan_with_correlation_id():
    """Plano cognitivo com correlation_id válido."""
    return {
        'plan_id': str(uuid.uuid4()),
        'intent_id': str(uuid.uuid4()),
        'correlation_id': str(uuid.uuid4()),
        'original_domain': 'BUSINESS',  # FIX BUG-002: Campo correto do schema Avro
        'trace_id': str(uuid.uuid4()),
        'span_id': str(uuid.uuid4())
    }


@pytest.fixture
def cognitive_plan_with_whitespace_correlation_id():
    """Plano cognitivo com correlation_id apenas com espaços."""
    return {
        'plan_id': str(uuid.uuid4()),
        'intent_id': str(uuid.uuid4()),
        'correlation_id': '   ',
        'original_domain': 'BUSINESS'  # FIX BUG-002: Campo correto do schema Avro
    }


@pytest.mark.unit
@pytest.mark.asyncio
class TestConsensusOrchestratorCorrelationId:
    """Testes para propagação de correlation_id no ConsensusOrchestrator."""

    async def test_process_consensus_propagates_valid_correlation_id(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions,
        cognitive_plan_with_correlation_id,
        caplog
    ):
        """Verifica que correlation_id válido é propagado corretamente."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        original_correlation_id = cognitive_plan_with_correlation_id['correlation_id']

        decision = await orchestrator.process_consensus(
            cognitive_plan=cognitive_plan_with_correlation_id,
            specialist_opinions=sample_specialist_opinions
        )

        assert decision.correlation_id == original_correlation_id
        assert 'correlation_id ausente no cognitive_plan' not in caplog.text

    async def test_process_consensus_generates_fallback_when_none(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions,
        cognitive_plan_without_correlation_id,
        caplog
    ):
        """Verifica que UUID fallback é gerado quando correlation_id é None."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        decision = await orchestrator.process_consensus(
            cognitive_plan=cognitive_plan_without_correlation_id,
            specialist_opinions=sample_specialist_opinions
        )

        assert decision.correlation_id is not None
        assert len(decision.correlation_id) > 0
        assert 'correlation_id ausente no cognitive_plan - gerado fallback UUID' in caplog.text

    async def test_process_consensus_generates_fallback_when_empty_string(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions,
        cognitive_plan_with_empty_correlation_id,
        caplog
    ):
        """Verifica que UUID fallback é gerado quando correlation_id é string vazia."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        decision = await orchestrator.process_consensus(
            cognitive_plan=cognitive_plan_with_empty_correlation_id,
            specialist_opinions=sample_specialist_opinions
        )

        assert decision.correlation_id is not None
        assert decision.correlation_id != ''
        assert len(decision.correlation_id) > 0
        assert 'correlation_id ausente no cognitive_plan - gerado fallback UUID' in caplog.text

    async def test_process_consensus_generates_fallback_when_whitespace(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions,
        cognitive_plan_with_whitespace_correlation_id,
        caplog
    ):
        """Verifica que UUID fallback é gerado quando correlation_id é apenas espaços."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        decision = await orchestrator.process_consensus(
            cognitive_plan=cognitive_plan_with_whitespace_correlation_id,
            specialist_opinions=sample_specialist_opinions
        )

        assert decision.correlation_id is not None
        assert decision.correlation_id.strip() != ''
        assert 'correlation_id ausente no cognitive_plan - gerado fallback UUID' in caplog.text

    async def test_correlation_id_is_valid_uuid_format(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions,
        cognitive_plan_without_correlation_id
    ):
        """Verifica que correlation_id gerado é um UUID válido."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        decision = await orchestrator.process_consensus(
            cognitive_plan=cognitive_plan_without_correlation_id,
            specialist_opinions=sample_specialist_opinions
        )

        # Tentar parsear como UUID - lança exceção se inválido
        parsed_uuid = uuid.UUID(decision.correlation_id)
        assert str(parsed_uuid) == decision.correlation_id

    async def test_correlation_id_propagated_to_cognitive_plan_field(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions,
        cognitive_plan_with_correlation_id
    ):
        """Verifica que correlation_id mantém valor original no cognitive_plan incluído."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        original_correlation_id = cognitive_plan_with_correlation_id['correlation_id']

        decision = await orchestrator.process_consensus(
            cognitive_plan=cognitive_plan_with_correlation_id,
            specialist_opinions=sample_specialist_opinions
        )

        assert decision.cognitive_plan['correlation_id'] == original_correlation_id
        assert decision.correlation_id == original_correlation_id

    async def test_multiple_calls_generate_unique_fallback_ids(
        self,
        mock_consensus_orchestrator_config,
        mock_pheromone_client,
        sample_specialist_opinions
    ):
        """Verifica que chamadas múltiplas geram correlation_ids únicos."""
        orchestrator = ConsensusOrchestrator(
            config=mock_consensus_orchestrator_config,
            pheromone_client=mock_pheromone_client
        )

        correlation_ids = set()

        for _ in range(3):
            plan = {
                'plan_id': str(uuid.uuid4()),
                'intent_id': str(uuid.uuid4()),
                'original_domain': 'BUSINESS'  # FIX BUG-002: Campo correto do schema Avro
                # Sem correlation_id
            }

            decision = await orchestrator.process_consensus(
                cognitive_plan=plan,
                specialist_opinions=sample_specialist_opinions
            )

            correlation_ids.add(decision.correlation_id)

        # Todos os 3 devem ser únicos
        assert len(correlation_ids) == 3
