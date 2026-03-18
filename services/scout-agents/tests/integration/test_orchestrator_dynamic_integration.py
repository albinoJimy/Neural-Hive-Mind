"""
Testes para OrchestratorDynamicIntegration.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime
from typing import Dict, Any

# Import com skip automático se módulo não disponível
OrchestratorDynamicIntegration = pytest.importorskip('src.integration.orchestrator_dynamic_integration').OrchestratorDynamicIntegration


class TestOrchestratorDynamicIntegrationInitialization:
    """Testes de inicialização da integração."""

    def test_integration_initialization(self):
        """Testa que a integração é inicializada corretamente."""
        mock_scout_orchestrator = AsyncMock()
        mock_temporal_client = AsyncMock()

        integration = OrchestratorDynamicIntegration(
            scout_orchestrator=mock_scout_orchestrator,
            temporal_client=mock_temporal_client
        )

        assert integration is not None


class TestRequestScoutExploration:
    """Testes de requisição de exploração ao Scout."""

    @pytest.fixture
    def integration(self):
        mock_scout_orchestrator = AsyncMock()
        mock_scout_orchestrator.coordinate_exploration = AsyncMock(
            return_value={
                'exploration_id': 'scout-exp-1',
                'status': 'running'
            }
        )

        mock_temporal = AsyncMock()

        return OrchestratorDynamicIntegration(
            scout_orchestrator=mock_scout_orchestrator,
            temporal_client=mock_temporal
        )

    @pytest.mark.asyncio
    async def test_request_exploration_returns_id(self, integration):
        """Testa que request retorna exploration_id."""
        result = await integration.request_exploration(
            plan_id='plan-1',
            intent_text='Implementar feature X'
        )

        assert 'exploration_id' in result
        assert result['status'] == 'running'

    @pytest.mark.asyncio
    async def test_request_with_specific_scouts(self, integration):
        """Testa request com scouts específicos."""
        result = await integration.request_exploration(
            plan_id='plan-1',
            intent_text='Analisar código',
            scouts=['codebase_explorer']
        )

        assert 'exploration_id' in result


class TestGetExplorationResults:
    """Testes de obtenção de resultados de exploração."""

    @pytest.fixture
    def integration(self):
        mock_ledger = AsyncMock()
        mock_ledger.get_exploration = AsyncMock(
            return_value={
                'exploration_id': 'scout-exp-1',
                'status': 'completed',
                'results': {
                    'patterns': [{'name': 'repository', 'count': 5}]
                }
            }
        )

        mock_scout_orchestrator = AsyncMock()
        mock_temporal = AsyncMock()

        integration = OrchestratorDynamicIntegration(
            scout_orchestrator=mock_scout_orchestrator,
            temporal_client=mock_temporal,
            scout_ledger=mock_ledger
        )
        return integration

    @pytest.mark.asyncio
    async def test_get_completed_results(self, integration):
        """Testa obtenção de resultados completados."""
        results = await integration.get_exploration_results('scout-exp-1')

        assert results['status'] == 'completed'
        assert 'patterns' in results['results']

    @pytest.mark.asyncio
    async def test_get_running_status(self, integration):
        """Testa obtenção de status de exploração em andamento."""
        mock_ledger = AsyncMock()
        mock_ledger.get_exploration = AsyncMock(
            return_value={
                'exploration_id': 'scout-exp-2',
                'status': 'running'
            }
        )

        integration.scout_ledger = mock_ledger

        results = await integration.get_exploration_results('scout-exp-2')

        assert results['status'] == 'running'


class TestTranslateScoutResultsToTemporalWorkflow:
    """Testes de tradução de resultados para Temporal Workflow."""

    @pytest.fixture
    def integration(self):
        mock_scout_orchestrator = AsyncMock()
        mock_temporal = AsyncMock()
        return OrchestratorDynamicIntegration(
            scout_orchestrator=mock_scout_orchestrator,
            temporal_client=mock_temporal
        )

    def test_translate_pattern_discovery_to_activities(self, integration):
        """Testa tradução de padrões descobertos para atividades."""
        scout_results = {
            'patterns_found': [
                {'name': 'repository', 'count': 5, 'locations': ['a.py', 'b.py']}
            ]
        }

        activities = integration.translate_to_workflow_activities(scout_results)

        assert len(activities) > 0
        assert any('repository' in str(a).lower() for a in activities)

    def test_translate_recommendations_to_tickets(self, integration):
        """Testa tradução de recomendações para tickets."""
        scout_results = {
            'recommendations': [
                {'action': 'Refactor', 'target': 'service.py', 'priority': 'high'}
            ]
        }

        tickets = integration.translate_to_tickets(scout_results)

        assert len(tickets) > 0
        assert tickets[0]['priority'] == 'high'


class TestWorkflowIntegration:
    """Testes de integração com Temporal Workflow."""

    @pytest.fixture
    def integration(self):
        mock_scout_orchestrator = AsyncMock()
        mock_temporal = AsyncMock()

        integration = OrchestratorDynamicIntegration(
            scout_orchestrator=mock_scout_orchestrator,
            temporal_client=mock_temporal
        )
        return integration

    @pytest.mark.asyncio
    async def test_signal_workflow_completion(self, integration):
        """Testa sinalização de conclusão de workflow."""
        result = await integration.signal_workflow_completion(
            workflow_id='workflow-1',
            exploration_id='scout-exp-1'
        )

        assert result['signaled'] is True

    @pytest.mark.asyncio
    async def test_signal_workflow_failure(self, integration):
        """Testa sinalização de falha no workflow."""
        result = await integration.signal_workflow_failure(
            workflow_id='workflow-2',
            error='Timeout exceeded'
        )

        assert result['signaled'] is True


class TestContextEnrichment:
    """Testes de enriquecimento de contexto com scout data."""

    @pytest.fixture
    def integration(self):
        mock_scout_orchestrator = AsyncMock()
        mock_temporal = AsyncMock()
        return OrchestratorDynamicIntegration(
            scout_orchestrator=mock_scout_orchestrator,
            temporal_client=mock_temporal
        )

    def test_enrich_context_with_patterns(self, integration):
        """Testa enriquecimento de contexto com padrões descobertos."""
        base_context = {'plan_id': 'plan-1', 'intent': 'Create API'}
        scout_data = {
            'patterns': [
                {'name': 'service', 'count': 3}
            ]
        }

        enriched = integration.enrich_context(base_context, scout_data)

        assert 'scout_patterns' in enriched
        assert len(enriched['scout_patterns']) == 1

    def test_enrich_context_with_dependencies(self, integration):
        """Testa enriquecimento com dependências."""
        base_context = {'plan_id': 'plan-1'}
        scout_data = {
            'dependencies': {
                'service.py': ['repository.py']
            }
        }

        enriched = integration.enrich_context(base_context, scout_data)

        assert 'dependencies' in enriched
