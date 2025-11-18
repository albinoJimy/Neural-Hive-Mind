"""
ResourceAllocator - Gerencia descoberta e alocação de workers.

Integra com Service Registry para discovery de agentes e balanceamento de carga.
"""

import asyncio
import structlog
from typing import Dict, List, Optional

from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics

logger = structlog.get_logger(__name__)


class ResourceAllocator:
    """
    Alocador de recursos para execution tickets.

    Responsável por:
    - Descobrir workers via Service Registry
    - Selecionar melhor worker baseado em score composto
    - Implementar fallback quando registry indisponível
    """

    def __init__(
        self,
        registry_client,
        config: OrchestratorSettings,
        metrics: OrchestratorMetrics,
        scheduling_optimizer=None
    ):
        """
        Inicializa o alocador.

        Args:
            registry_client: Cliente gRPC do Service Registry
            config: Configurações do orchestrator
            metrics: Instância de métricas
            scheduling_optimizer: SchedulingOptimizer para ML-enhanced selection (opcional)
        """
        self.registry_client = registry_client
        self.config = config
        self.metrics = metrics
        self.scheduling_optimizer = scheduling_optimizer
        self.logger = logger.bind(component='resource_allocator')

    async def discover_workers(self, ticket: Dict) -> List[Dict]:
        """
        Descobre workers disponíveis para um ticket.

        Args:
            ticket: Execution ticket

        Returns:
            Lista de workers disponíveis (AgentInfo convertido para dict)
        """
        ticket_id = ticket.get('ticket_id', 'unknown')
        required_capabilities = ticket.get('required_capabilities', [])
        namespace = ticket.get('namespace', 'default')
        security_level = ticket.get('security_level', 'standard')

        self.logger.info(
            'discovering_workers',
            ticket_id=ticket_id,
            capabilities=required_capabilities,
            namespace=namespace,
            security_level=security_level
        )

        try:
            # Criar filtros para Service Registry
            filters = {
                'namespace': namespace,
                'status': 'HEALTHY',
                'security_level': security_level
            }

            # Chamar Service Registry (timeout aplicado via gRPC client config)
            # O timeout é gerenciado pela camada do IntelligentScheduler
            workers = await self.registry_client.discover_agents(
                capabilities=required_capabilities,
                filters=filters,
                max_results=self.config.service_registry_max_results
            )

            self.logger.info(
                'workers_discovered',
                ticket_id=ticket_id,
                workers_count=len(workers)
            )

            return workers

        except Exception as e:
            self.logger.error(
                'discovery_error',
                ticket_id=ticket_id,
                error=str(e),
                error_type=type(e).__name__
            )
            self.metrics.record_discovery_failure(type(e).__name__)
            return []

    async def select_best_worker(
        self,
        workers: List[Dict],
        priority_score: float,
        ticket: Optional[Dict] = None,
        load_forecast: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Seleciona melhor worker baseado em score composto.

        Com ML optimization, enriquece workers com predições de queue time e load.

        Args:
            workers: Lista de workers disponíveis
            priority_score: Score de prioridade do ticket
            ticket: Ticket para contexto ML (opcional)
            load_forecast: Load forecast para contexto (opcional)

        Returns:
            Worker selecionado ou None se nenhum disponível
        """
        if not workers:
            return None

        # Se scheduling_optimizer disponível, enriquecer workers com ML predictions
        if self.scheduling_optimizer and ticket:
            try:
                workers = await self.scheduling_optimizer.optimize_allocation(
                    ticket=ticket,
                    workers=workers,
                    load_forecast=load_forecast
                )

                self.logger.debug(
                    "workers_enriched_with_ml_predictions",
                    workers_count=len(workers)
                )
            except Exception as e:
                self.logger.warning(
                    "ml_enrichment_failed_using_fallback",
                    error=str(e)
                )

        # Filtrar workers disponíveis
        available_workers = [
            w for w in workers
            if self._is_worker_available(w)
        ]

        if not available_workers:
            self.logger.warning(
                'no_available_workers',
                total_workers=len(workers)
            )
            return None

        # Calcular score composto para cada worker
        scored_workers = []
        for worker in available_workers:
            agent_score = self._calculate_agent_score(worker)
            composite_score = (agent_score * 0.6) + (priority_score * 0.4)

            scored_workers.append({
                **worker,
                'score': agent_score,
                'composite_score': composite_score
            })

        # Ordenar por composite_score (maior primeiro)
        scored_workers.sort(key=lambda w: w['composite_score'], reverse=True)

        # Retornar melhor worker
        best_worker = scored_workers[0]

        self.logger.info(
            'best_worker_selected',
            agent_id=best_worker.get('agent_id'),
            agent_type=best_worker.get('agent_type'),
            agent_score=best_worker.get('score'),
            composite_score=best_worker.get('composite_score'),
            ml_enriched=best_worker.get('ml_enriched', False),
            predicted_queue_ms=best_worker.get('predicted_queue_ms'),
            predicted_load_pct=best_worker.get('predicted_load_pct'),
            candidates_evaluated=len(scored_workers)
        )

        return best_worker

    def _calculate_agent_score(self, agent: Dict) -> float:
        """
        Calcula score do agente baseado em status, telemetry e ML predictions.

        Usa os campos disponíveis no AgentInfo do proto atual:
        - status (HEALTHY, UNHEALTHY, DEGRADED)
        - telemetry (success_rate, avg_duration_ms, total_executions, etc.)
        - predicted_queue_ms (se ML enrichment aplicado)
        - predicted_load_pct (se ML enrichment aplicado)
        - rl_boost (se RL recommendation aplicado)

        Args:
            agent: Informações do agente

        Returns:
            Score normalizado [0.0, 1.0]
        """
        # Health score (0-1 baseado em status)
        status = agent.get('status', 'UNKNOWN')
        health_score = self._calculate_health_score(status)

        # Telemetry score (0-1 baseado em success_rate e performance)
        telemetry = agent.get('telemetry', {})
        telemetry_score = self._calculate_telemetry_score(telemetry)

        # ML prediction scores (se disponíveis)
        queue_score = 1.0
        load_score = 1.0

        if agent.get('ml_enriched', False):
            # Queue score: penalizar filas longas (> 5s)
            predicted_queue_ms = agent.get('predicted_queue_ms', 0)
            queue_score = max(0.0, 1.0 - (predicted_queue_ms / 10000.0))  # Normalizar até 10s

            # Load score: penalizar alta carga
            predicted_load_pct = agent.get('predicted_load_pct', 0)
            load_score = 1.0 - predicted_load_pct

        # Score composto com pesos ajustados para ML predictions
        if agent.get('ml_enriched', False):
            # Com ML: health 40%, telemetry 30%, queue 20%, load 10%
            agent_score = (
                (health_score * 0.4) +
                (telemetry_score * 0.3) +
                (queue_score * 0.2) +
                (load_score * 0.1)
            )
        else:
            # Sem ML: health 50%, telemetry 50%
            agent_score = (health_score * 0.5) + (telemetry_score * 0.5)

        # Aplicar RL boost se disponível
        # rl_boost é um multiplicador aplicado ao score calculado
        # Valores típicos: 1.0 (sem boost), 1.1-1.2 (boost moderado), >1.2 (boost forte)
        rl_boost = agent.get('rl_boost', 1.0)
        if rl_boost != 1.0:
            agent_score = agent_score * rl_boost
            self.logger.debug(
                "rl_boost_applied",
                agent_id=agent.get('agent_id'),
                base_score=agent_score / rl_boost,
                rl_boost=rl_boost,
                final_score=agent_score
            )

        return min(max(agent_score, 0.0), 1.0)

    def _calculate_health_score(self, status: str) -> float:
        """
        Calcula score de health baseado no status do agente.

        Args:
            status: Status do agente (HEALTHY, UNHEALTHY, DEGRADED, etc.)

        Returns:
            Score normalizado [0.0, 1.0]
        """
        if status == 'HEALTHY':
            return 1.0
        elif status == 'DEGRADED':
            return 0.6
        elif status == 'UNHEALTHY':
            return 0.3
        else:
            return 0.5

    def _calculate_telemetry_score(self, telemetry: Dict) -> float:
        """
        Calcula score de telemetry baseado nos campos disponíveis no proto atual.

        Usa:
        - success_rate: Taxa de sucesso das execuções
        - avg_duration_ms: Duração média de execução (menor é melhor)
        - total_executions: Total de execuções (experiência)
        - failed_executions: Total de falhas

        Args:
            telemetry: Dados de telemetria do AgentTelemetry proto

        Returns:
            Score normalizado [0.0, 1.0]
        """
        if not telemetry:
            # Se não há telemetria, retornar score neutro
            return 0.5

        # Success rate (peso 60%)
        success_rate = telemetry.get('success_rate', 0.0)

        # Performance baseada em duração média (peso 20%)
        # Normalizar: assume 0-5000ms como range esperado
        avg_duration_ms = telemetry.get('avg_duration_ms', 2500)
        # Inverter: menor duração = melhor score
        duration_score = max(0.0, 1.0 - (avg_duration_ms / 5000.0))

        # Experiência baseada em total de execuções (peso 20%)
        # Normalizar: 0-1000 execuções como range esperado
        total_executions = telemetry.get('total_executions', 0)
        experience_score = min(1.0, total_executions / 1000.0)

        # Score composto
        score = (success_rate * 0.6) + (duration_score * 0.2) + (experience_score * 0.2)

        return min(max(score, 0.0), 1.0)

    def _is_worker_available(self, agent: Dict) -> bool:
        """
        Verifica se worker está disponível para receber tarefas.

        Usa apenas campos disponíveis no proto atual.
        CPU/memória/active_tasks podem ser adicionados futuramente via metadata.
        Com ML predictions, considera predicted_load_pct.

        Args:
            agent: Informações do agente

        Returns:
            True se disponível, False caso contrário
        """
        # Verificar status (campo direto do AgentInfo)
        status = agent.get('status', 'UNKNOWN')
        if status not in ['HEALTHY', 'DEGRADED']:
            return False

        # Se há ML prediction de carga, verificar threshold
        if agent.get('ml_enriched', False):
            predicted_load_pct = agent.get('predicted_load_pct', 0)
            if predicted_load_pct > 0.9:  # Rejeitar se > 90% de carga
                self.logger.debug(
                    "worker_rejected_high_predicted_load",
                    agent_id=agent.get('agent_id'),
                    predicted_load_pct=predicted_load_pct
                )
                return False

        # Se há metadata com informações de capacidade, usar
        metadata = agent.get('metadata', {})
        if 'active_tasks' in metadata and 'max_concurrent_tasks' in metadata:
            try:
                active_tasks = int(metadata['active_tasks'])
                max_tasks = int(metadata['max_concurrent_tasks'])
                if active_tasks >= max_tasks:
                    return False
            except (ValueError, TypeError):
                # Se conversão falhar, ignorar e considerar disponível
                pass

        return True
