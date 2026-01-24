"""
ResourceAllocator - Gerencia descoberta e alocação de workers.

Integra com Service Registry para discovery de agentes e balanceamento de carga.
"""

import asyncio
import structlog
from typing import Dict, List, Optional, Set

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
        scheduling_optimizer=None,
        affinity_tracker=None
    ):
        """
        Inicializa o alocador.

        Args:
            registry_client: Cliente gRPC do Service Registry
            config: Configurações do orchestrator
            metrics: Instância de métricas
            scheduling_optimizer: SchedulingOptimizer para ML-enhanced selection (opcional)
            affinity_tracker: AffinityTracker para co-location de tickets (opcional)
        """
        self.registry_client = registry_client
        self.config = config
        self.metrics = metrics
        self.scheduling_optimizer = scheduling_optimizer
        self.affinity_tracker = affinity_tracker
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
        Com affinity habilitado, considera co-location e anti-affinity.

        Args:
            workers: Lista de workers disponíveis
            priority_score: Score de prioridade do ticket
            ticket: Ticket para contexto ML e affinity (opcional)
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

        # Obter dados de affinity se habilitado
        affinity_data = None
        affinity_enabled = getattr(self.config, 'scheduler_enable_affinity', False)

        if affinity_enabled and self.affinity_tracker and ticket:
            try:
                plan_id = ticket.get('plan_id')
                intent_id = ticket.get('intent_id')

                plan_allocations = await self.affinity_tracker.get_plan_allocations(plan_id)
                intent_allocations = await self.affinity_tracker.get_intent_allocations(intent_id)

                # Obter tickets críticos por worker
                critical_tickets = {}
                for worker in available_workers:
                    worker_id = worker.get('agent_id')
                    critical_tickets[worker_id] = await self.affinity_tracker.get_critical_tickets_on_worker(worker_id)

                affinity_data = {
                    'plan_allocations': plan_allocations,
                    'intent_allocations': intent_allocations,
                    'critical_tickets': critical_tickets
                }

                self.logger.debug(
                    "affinity_data_fetched",
                    plan_id=plan_id,
                    intent_id=intent_id,
                    workers_with_plan=len([w for w, c in plan_allocations.items() if c > 0]),
                    workers_with_critical=len([w for w, t in critical_tickets.items() if len(t) > 0])
                )

            except Exception as e:
                self.logger.warning(
                    "affinity_data_fetch_failed_continuing_without",
                    error=str(e)
                )
                affinity_data = None

        # Calcular score composto para cada worker
        scored_workers = []
        for worker in available_workers:
            agent_score = self._calculate_agent_score(worker, ticket, affinity_data)
            composite_score = (agent_score * 0.6) + (priority_score * 0.4)

            scored_workers.append({
                **worker,
                'score': agent_score,
                'composite_score': composite_score,
                'affinity_applied': affinity_data is not None
            })

        # Ordenar por composite_score (maior primeiro)
        scored_workers.sort(key=lambda w: w['composite_score'], reverse=True)

        # Retornar melhor worker
        best_worker = scored_workers[0]

        # Registrar alocação no affinity tracker
        if self.affinity_tracker and ticket:
            try:
                await self.affinity_tracker.record_allocation(ticket, best_worker.get('agent_id'))
            except Exception as e:
                self.logger.warning(
                    "affinity_record_failed",
                    error=str(e)
                )

        self.logger.info(
            'best_worker_selected',
            agent_id=best_worker.get('agent_id'),
            agent_type=best_worker.get('agent_type'),
            agent_score=best_worker.get('score'),
            composite_score=best_worker.get('composite_score'),
            ml_enriched=best_worker.get('ml_enriched', False),
            predicted_queue_ms=best_worker.get('predicted_queue_ms'),
            predicted_load_pct=best_worker.get('predicted_load_pct'),
            affinity_applied=best_worker.get('affinity_applied', False),
            candidates_evaluated=len(scored_workers)
        )

        return best_worker

    def _calculate_agent_score(
        self,
        agent: Dict,
        ticket: Optional[Dict] = None,
        affinity_data: Optional[Dict] = None
    ) -> float:
        """
        Calcula score do agente baseado em status, telemetry, ML predictions e affinity.

        Usa os campos disponíveis no AgentInfo do proto atual:
        - status (HEALTHY, UNHEALTHY, DEGRADED)
        - telemetry (success_rate, avg_duration_ms, total_executions, etc.)
        - predicted_queue_ms (se ML enrichment aplicado)
        - predicted_load_pct (se ML enrichment aplicado)
        - rl_boost (se RL recommendation aplicado)
        - affinity_data (se affinity habilitado)

        Args:
            agent: Informações do agente
            ticket: Ticket sendo alocado (para affinity)
            affinity_data: Dados de affinity (plan/intent allocations, critical tickets)

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
            base_score = (
                (health_score * 0.4) +
                (telemetry_score * 0.3) +
                (queue_score * 0.2) +
                (load_score * 0.1)
            )
        else:
            # Sem ML: health 50%, telemetry 50%
            base_score = (health_score * 0.5) + (telemetry_score * 0.5)

        # Aplicar RL boost se disponível
        # rl_boost é um multiplicador aplicado ao score calculado
        # Valores típicos: 1.0 (sem boost), 1.1-1.2 (boost moderado), >1.2 (boost forte)
        rl_boost = agent.get('rl_boost', 1.0)
        if rl_boost != 1.0:
            base_score = base_score * rl_boost
            self.logger.debug(
                "rl_boost_applied",
                agent_id=agent.get('agent_id'),
                base_score=base_score / rl_boost,
                rl_boost=rl_boost,
                final_score=base_score
            )

        # Aplicar affinity score se habilitado e dados disponíveis
        affinity_enabled = getattr(self.config, 'scheduler_enable_affinity', False)
        agent_score = base_score

        if affinity_enabled and affinity_data and ticket:
            agent_id = agent.get('agent_id')
            affinity_score = self._calculate_affinity_score(
                agent,
                ticket,
                affinity_data.get('plan_allocations', {}),
                affinity_data.get('intent_allocations', {}),
                affinity_data.get('critical_tickets', {}).get(agent_id, set())
            )

            # Affinity atua como multiplicador (0.5-1.5 range para não dominar)
            # Score normalizado: 0.5 = penalização leve, 1.0 = neutro, 1.5 = boost forte
            affinity_multiplier = 0.5 + (affinity_score * 1.0)  # Range [0.5, 1.5]
            agent_score = base_score * affinity_multiplier

            self.logger.debug(
                "affinity_applied",
                agent_id=agent_id,
                base_score=base_score,
                affinity_score=affinity_score,
                affinity_multiplier=affinity_multiplier,
                final_score=agent_score
            )

            # Registrar métrica de affinity score
            self.metrics.record_affinity_score('composite', affinity_score)

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

    def _calculate_affinity_score(
        self,
        agent: Dict,
        ticket: Dict,
        plan_allocations: Dict[str, int],
        intent_allocations: Dict[str, int],
        critical_tickets_on_worker: set
    ) -> float:
        """
        Calcula score de affinity/anti-affinity para um worker.

        Considera:
        - Data locality: Tickets do mesmo plan_id preferem mesmo worker
        - Anti-affinity: Tickets críticos evitam workers com outros críticos
        - Intent affinity: Tickets do mesmo intent_id têm afinidade moderada

        Args:
            agent: Worker candidato
            ticket: Ticket sendo alocado
            plan_allocations: {worker_id: count} para plan_id
            intent_allocations: {worker_id: count} para intent_id
            critical_tickets_on_worker: Set de ticket_ids críticos no worker

        Returns:
            Score normalizado [0.0, 1.0]
        """
        agent_id = agent.get('agent_id')
        risk_band = ticket.get('risk_band', '')
        priority = ticket.get('priority', '')

        # Obter pesos de configuração
        plan_weight = getattr(self.config, 'scheduler_affinity_plan_weight', 0.6)
        anti_weight = getattr(self.config, 'scheduler_affinity_anti_weight', 0.3)
        intent_weight = getattr(self.config, 'scheduler_affinity_intent_weight', 0.1)
        plan_threshold = getattr(self.config, 'scheduler_affinity_plan_threshold', 3)

        # Risk bands e priorities que ativam anti-affinity
        anti_affinity_risk_bands = getattr(
            self.config, 'scheduler_affinity_anti_affinity_risk_bands',
            ['critical', 'high']
        )
        anti_affinity_priorities = getattr(
            self.config, 'scheduler_affinity_anti_affinity_priorities',
            ['CRITICAL', 'HIGH']
        )

        # 1. Plan Affinity (data locality)
        plan_tickets = plan_allocations.get(agent_id, 0)
        if plan_tickets > 0:
            # Worker já tem tickets do mesmo plan: score alto (0.5 + bonus até 1.0)
            # Fórmula: 0.5 (base) + 0.5 * min(1.0, tickets/threshold)
            # 1 ticket = 0.5 + 0.5 * 0.33 = 0.67
            # 3+ tickets = 0.5 + 0.5 * 1.0 = 1.0
            plan_score = 0.5 + (0.5 * min(1.0, plan_tickets / plan_threshold))
            self.metrics.record_affinity_hit('plan')
        else:
            # Worker não tem tickets do plan: score neutro
            plan_score = 0.5
            self.metrics.record_affinity_miss('plan')

        # 2. Anti-Affinity para tickets críticos
        is_critical = (
            risk_band.lower() in [rb.lower() for rb in anti_affinity_risk_bands] or
            priority.upper() in [p.upper() for p in anti_affinity_priorities]
        )

        if is_critical:
            if len(critical_tickets_on_worker) > 0:
                # Worker já tem tickets críticos: evitar (score baixo)
                anti_score = 0.0
            else:
                # Worker não tem tickets críticos: preferir (score alto)
                anti_score = 1.0

            self.metrics.record_anti_affinity_enforced(risk_band, priority)
        else:
            # Ticket não é crítico: neutro
            anti_score = 1.0

        # 3. Intent Affinity (workflow co-location)
        intent_tickets = intent_allocations.get(agent_id, 0)
        if intent_tickets > 0:
            # Worker já tem tickets do mesmo intent: score alto (0.5 + bonus até 1.0)
            intent_score = 0.5 + (0.5 * min(1.0, intent_tickets / plan_threshold))
            self.metrics.record_affinity_hit('intent')
        else:
            # Worker não tem tickets do intent: score neutro
            intent_score = 0.5
            self.metrics.record_affinity_miss('intent')

        # Score composto
        affinity_score = (
            (plan_score * plan_weight) +
            (anti_score * anti_weight) +
            (intent_score * intent_weight)
        )

        # Registrar scores individuais
        self.metrics.record_affinity_score('plan', plan_score)
        self.metrics.record_affinity_score('anti', anti_score)
        self.metrics.record_affinity_score('intent', intent_score)

        self.logger.debug(
            "affinity_score_calculated",
            agent_id=agent_id,
            plan_score=plan_score,
            anti_score=anti_score,
            intent_score=intent_score,
            is_critical=is_critical,
            plan_tickets=plan_tickets,
            critical_tickets=len(critical_tickets_on_worker),
            final_score=affinity_score
        )

        return min(max(affinity_score, 0.0), 1.0)

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
