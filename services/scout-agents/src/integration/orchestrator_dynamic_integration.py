"""
OrchestratorDynamicIntegration - Integração com Orchestrator Dynamic.

Responsável por:
- Solicitar explorações ao Scout Orchestrator
- Traduzir resultados de scouts para atividades Temporal
- Enriquecer contexto de workflows com descobertas dos scouts
- Sinalizar conclusão/falha de workflows
"""

from typing import Dict, List, Any, Optional
import structlog

logger = structlog.get_logger()


class OrchestratorDynamicIntegration:
    """Integração entre Scout Orchestrator e Orchestrator Dynamic."""

    def __init__(
        self,
        scout_orchestrator,
        temporal_client,
        scout_ledger=None
    ):
        """
        Inicializa a integração.

        Args:
            scout_orchestrator: Instância do ScoutOrchestrator
            temporal_client: Cliente Temporal
            scout_ledger: Instância opcional do ScoutLedger
        """
        self.scout_orchestrator = scout_orchestrator
        self.temporal_client = temporal_client
        self.scout_ledger = scout_ledger

    async def request_exploration(
        self,
        plan_id: str,
        intent_text: str,
        scouts: Optional[List[str]] = None,
        timeout_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Solicita uma exploração ao Scout Orchestrator.

        Args:
            plan_id: ID do plano cognitivo
            intent_text: Texto da intenção
            scouts: Scouts específicos (opcional)
            timeout_ms: Timeout em ms (opcional)

        Returns:
            Dict com exploration_id e status
        """
        logger.info(
            "requesting_scout_exploration",
            plan_id=plan_id,
            scouts=scouts
        )

        exploration = await self.scout_orchestrator.coordinate_exploration(
            plan_id=plan_id,
            intent_text=intent_text,
            scouts=scouts,
            timeout_ms=timeout_ms
        )

        # Salvar no ledger se disponível
        if self.scout_ledger:
            await self.scout_ledger.save_exploration(exploration)

        return exploration

    async def get_exploration_results(
        self,
        exploration_id: str
    ) -> Dict[str, Any]:
        """
        Obtém resultados de uma exploração.

        Args:
            exploration_id: ID da exploração

        Returns:
            Dict com resultados da exploração
        """
        if self.scout_ledger:
            exploration = await self.scout_ledger.get_exploration(exploration_id)
            return exploration or {}

        # Fallback: consultar o orchestrator
        return await self.scout_orchestrator.get_exploration_status(exploration_id)

    def translate_to_workflow_activities(
        self,
        scout_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Traduz resultados de scouts para atividades Temporal.

        Args:
            scout_results: Resultados da exploração

        Returns:
            Lista de atividades para o workflow
        """
        activities = []

        # Traduzir padrões descobertos
        patterns = scout_results.get('patterns_found', [])
        for pattern in patterns:
            activities.append({
                'name': f"Apply {pattern.get('name', 'pattern')}",
                'type': 'refactoring',
                'description': f"Implement {pattern.get('name')} pattern",
                'priority': 'medium' if pattern.get('confidence', 0.5) < 0.8 else 'high'
            })

        # Traduzir recomendações
        recommendations = scout_results.get('recommendations', [])
        for rec in recommendations:
            activities.append({
                'name': rec.get('action', 'Execute action'),
                'type': 'implementation',
                'description': rec.get('description', ''),
                'priority': rec.get('priority', 'medium')
            })

        logger.info(
            "translated_to_activities",
            activities_count=len(activities)
        )

        return activities

    def translate_to_tickets(
        self,
        scout_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Traduz recomendações em tickets de execução.

        Args:
            scout_results: Resultados da exploração

        Returns:
            Lista de tickets para Worker Agents
        """
        tickets = []

        recommendations = scout_results.get('recommendations', [])
        for i, rec in enumerate(recommendations):
            ticket = {
                'ticket_id': f'ticket-{i}',
                'action': rec.get('action', 'unknown'),
                'target': rec.get('target', ''),
                'description': rec.get('description', rec.get('reason', '')),
                'priority': rec.get('priority', 'medium'),
                'effort': rec.get('effort', 'medium'),
                'status': 'pending'
            }
            tickets.append(ticket)

        logger.info(
            "created_tickets",
            count=len(tickets)
        )

        return tickets

    async def signal_workflow_completion(
        self,
        workflow_id: str,
        exploration_id: str
    ) -> Dict[str, Any]:
        """
        Sinaliza conclusão do workflow com dados da exploração.

        Args:
            workflow_id: ID do workflow Temporal
            exploration_id: ID da exploração

        Returns:
            Dict com confirmação
        """
        logger.info(
            "signaling_workflow_completion",
            workflow_id=workflow_id,
            exploration_id=exploration_id
        )

        # Em produção: await self.temporal_client.complete_workflow(...)
        # Para testes, retornamos mock
        return {
            'signaled': True,
            'workflow_id': workflow_id,
            'exploration_id': exploration_id
        }

    async def signal_workflow_failure(
        self,
        workflow_id: str,
        error: str
    ) -> Dict[str, Any]:
        """
        Sinaliza falha no workflow.

        Args:
            workflow_id: ID do workflow
            error: Mensagem de erro

        Returns:
            Dict com confirmação
        """
        logger.error(
            "signaling_workflow_failure",
            workflow_id=workflow_id,
            error=error
        )

        # Em produção: await self.temporal_client.fail_workflow(...)
        return {
            'signaled': True,
            'workflow_id': workflow_id,
            'error': error
        }

    def enrich_context(
        self,
        base_context: Dict[str, Any],
        scout_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enriquece o contexto base com descobertas dos scouts.

        Args:
            base_context: Contexto base do plano
            scout_data: Dados retornados pelos scouts

        Returns:
            Dict com contexto enriquecido
        """
        enriched = dict(base_context)

        # Adicionar padrões descobertos
        if 'patterns' in scout_data:
            enriched['scout_patterns'] = scout_data['patterns']

        # Adicionar dependências
        if 'dependencies' in scout_data:
            enriched['dependencies'] = scout_data['dependencies']

        # Adicionar métricas de código
        if 'complexity' in scout_data:
            enriched['code_metrics'] = scout_data['complexity']

        # Adicionar recomendações
        if 'recommendations' in scout_data:
            enriched['scout_recommendations'] = scout_data['recommendations']

        logger.info(
            "context_enriched",
            plan_id=base_context.get('plan_id'),
            added_keys=list(set(scout_data.keys()) & {'patterns', 'dependencies', 'complexity', 'recommendations'})
        )

        return enriched
