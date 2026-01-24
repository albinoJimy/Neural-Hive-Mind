"""
IntelligentScheduler - Orquestrador principal de scheduling de tickets.

Coordena PriorityCalculator e ResourceAllocator para alocação otimizada de recursos.
Implementa cache de descobertas e fallback para Service Registry indisponível.
"""

import asyncio
import httpx
import structlog
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Set
from functools import lru_cache
from enum import Enum

from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics
from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError
from .priority_calculator import PriorityCalculator
from .resource_allocator import ResourceAllocator

# Import centralized ML predictors
try:
    from neural_hive_ml.predictive_models import SchedulingPredictor, LoadPredictor
    ML_AVAILABLE = True
except ImportError:
    SchedulingPredictor = None
    LoadPredictor = None
    ML_AVAILABLE = False

logger = structlog.get_logger(__name__)


class Priority(Enum):
    """Task priority levels for preemption logic."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class IntelligentScheduler:
    """
    Scheduler inteligente para alocação otimizada de tickets.

    Coordena cálculo de prioridade e descoberta de workers para alocar
    tickets de execução nos agentes mais adequados.
    """

    def __init__(
        self,
        config: OrchestratorSettings,
        metrics: OrchestratorMetrics,
        priority_calculator: PriorityCalculator,
        resource_allocator: ResourceAllocator,
        scheduling_optimizer=None,
        scheduling_predictor: Optional[SchedulingPredictor] = None,
        load_predictor: Optional[LoadPredictor] = None,
        anomaly_detector=None
    ):
        """
        Inicializa o scheduler.

        Args:
            config: Configurações do orchestrator
            metrics: Instância de métricas
            priority_calculator: Calculador de prioridades
            resource_allocator: Alocador de recursos
            scheduling_optimizer: SchedulingOptimizer para ML-enhanced scheduling (opcional)
            scheduling_predictor: Preditor de duração/recursos (ML centralizado)
            load_predictor: Preditor de carga do sistema (ML centralizado)
            anomaly_detector: Detector de anomalias (ML centralizado)
        """
        self.config = config
        self.metrics = metrics
        self.priority_calculator = priority_calculator
        self.resource_allocator = resource_allocator
        self.scheduling_optimizer = scheduling_optimizer
        self.scheduling_predictor = scheduling_predictor
        self.load_predictor = load_predictor
        self.anomaly_detector = anomaly_detector
        self.logger = logger.bind(component='intelligent_scheduler')
        self.registry_breaker = None
        if getattr(config, "CIRCUIT_BREAKER_ENABLED", False):
            self.registry_breaker = MonitoredCircuitBreaker(
                service_name=config.service_name,
                circuit_name="service_registry_discovery",
                fail_max=config.CIRCUIT_BREAKER_FAIL_MAX,
                timeout_duration=config.CIRCUIT_BREAKER_TIMEOUT,
                recovery_timeout=getattr(
                    config,
                    "CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
                    config.CIRCUIT_BREAKER_TIMEOUT,
                ),
                expected_exception=Exception,
            )

        # Cache de descobertas: {cache_key: (workers, timestamp)}
        self._discovery_cache: Dict[str, tuple[List[Dict], datetime]] = {}
        self._cache_ttl = timedelta(seconds=config.service_registry_cache_ttl_seconds)

        # Cache de prioridades de workflows: {workflow_id: priority}
        self._workflow_priorities: Dict[str, int] = {}

        # Cache de alocações de recursos: {workflow_id: allocation_dict}
        self._workflow_allocations: Dict[str, Dict] = {}

        # Preemption tracking
        self._preemption_cooldowns: Dict[str, datetime] = {}  # worker_id -> cooldown_end_time
        self._active_preemptions: Set[str] = set()  # Set of ticket_ids being preempted

    async def schedule_ticket(self, ticket: Dict) -> Dict:
        """
        Agenda um ticket para execução.

        Calcula prioridade, descobre workers disponíveis, seleciona o melhor
        e atualiza o ticket com metadata de alocação.
        Feedback loop de allocation outcomes é acionado em result_consolidation.py após conclusão do ticket.

        Args:
            ticket: Execution ticket a ser agendado

        Returns:
            Ticket atualizado com allocation_metadata (sempre inclui agent_id/agent_type;
            fallbacks também preenchem agent_id='worker-agent-pool')
        """
        start_time = datetime.now()
        ticket_id = ticket.get('ticket_id', 'unknown')
        fallback_used = False

        self.logger.info(
            'scheduling_ticket',
            ticket_id=ticket_id,
            risk_band=ticket.get('risk_band'),
            required_capabilities=ticket.get('required_capabilities')
        )

        try:
            # Etapa 0: Enriquecer ticket com predições ML
            if self.config.enable_ml_enhanced_scheduling:
                ticket = await self._enrich_ticket_with_predictions(ticket)
            else:
                self.logger.debug("ml_enhanced_scheduling_disabled", ticket_id=ticket_id)

            # Etapa 1: Calcular priority score
            priority_score = self.priority_calculator.calculate_priority_score(ticket)

            # Ajusta prioridade com ML predictions se disponível
            predictions = ticket.get('predictions', {})
            boosted = False
            has_predictions = bool(predictions)

            if predictions:
                # Boost por duração prevista
                predicted_duration = predictions.get('duration_ms', 0)
                estimated_duration = ticket.get('estimated_duration_ms', 0)

                if predicted_duration > 0 and estimated_duration > 0:
                    duration_ratio = predicted_duration / estimated_duration

                    # Boost prioridade se duração prevista > 150% da estimada
                    if duration_ratio > 1.5:
                        priority_score = min(priority_score * 1.2, 1.0)
                        boosted = True
                        self.logger.info(
                            'priority_boosted_by_ml_duration',
                            ticket_id=ticket_id,
                            duration_ratio=duration_ratio,
                            new_priority=priority_score
                        )

                # Boost por anomalia detectada
                anomaly = predictions.get('anomaly', {})
                if anomaly.get('is_anomaly', False):
                    priority_score = min(priority_score * 1.2, 1.0)
                    boosted = True
                    self.logger.info(
                        'priority_boosted_by_anomaly',
                        ticket_id=ticket_id,
                        anomaly_type=anomaly.get('type'),
                        anomaly_score=anomaly.get('score'),
                        new_priority=priority_score
                    )

            # Registrar priority score com flag boosted
            self.metrics.record_priority_score(
                ticket.get('risk_band', 'unknown'),
                priority_score,
                boosted=boosted
            )

            self.logger.info(
                'priority_calculated',
                ticket_id=ticket_id,
                priority_score=priority_score,
                boosted=boosted
            )

            # Obter load forecast se optimizer disponível
            load_forecast = None
            ml_optimization_attempted = False

            if self.scheduling_optimizer:
                try:
                    load_forecast = await self.scheduling_optimizer.get_load_forecast(
                        horizon_minutes=self.config.optimizer_forecast_horizon_minutes
                    )

                    ml_optimization_attempted = True

                    if load_forecast:
                        self.logger.info(
                            "load_forecast_obtained",
                            ticket_id=ticket_id,
                            forecast_points=len(load_forecast.get('forecast', []))
                        )
                except Exception as e:
                    self.logger.warning(
                        "load_forecast_error",
                        ticket_id=ticket_id,
                        error=str(e)
                    )

            # Etapa 2: Descobrir workers disponíveis
            workers = await self._discover_workers_cached(ticket)

            if not workers:
                # Attempt preemption for high-priority tickets
                ticket_priority = ticket.get('priority', 'MEDIUM')
                if self._can_preempt(ticket_priority, 'LOW'):
                    self.logger.info(
                        'attempting_preemption_no_workers',
                        ticket_id=ticket_id,
                        priority=ticket_priority
                    )
                    freed_workers = await self.preempt_low_priority_tasks(ticket, required_workers=1)
                    if freed_workers:
                        # Re-discover workers after preemption
                        workers = await self._discover_workers_cached(ticket)

                if not workers:
                    self.logger.error(
                        'no_workers_discovered_ticket_rejected',
                        ticket_id=ticket_id,
                        required_capabilities=ticket.get('required_capabilities'),
                        namespace=ticket.get('namespace', 'default')
                    )
                    # Registrar rejeição e marcar ticket como rejeitado
                    self.metrics.record_scheduler_rejection('no_workers')
                    return self._reject_ticket(ticket, 'no_workers', 'Nenhum worker disponível para o ticket')

            self.metrics.record_workers_discovered(len(workers))

            # Etapa 3: Selecionar melhor worker (com ML optimization se disponível)
            best_worker = await self.resource_allocator.select_best_worker(
                workers=workers,
                priority_score=priority_score,
                ticket=ticket,
                load_forecast=load_forecast
            )

            if not best_worker:
                self.logger.error(
                    'no_suitable_worker_ticket_rejected',
                    ticket_id=ticket_id,
                    workers_count=len(workers),
                    required_capabilities=ticket.get('required_capabilities'),
                    namespace=ticket.get('namespace', 'default')
                )
                # Registrar rejeição e marcar ticket como rejeitado
                self.metrics.record_scheduler_rejection('no_suitable_worker')
                return self._reject_ticket(
                    ticket,
                    'no_suitable_worker',
                    f'Nenhum worker adequado entre {len(workers)} candidatos'
                )

            # Etapa 4: Atualizar ticket com allocation metadata
            allocation_metadata = {
                'allocated_at': int(datetime.now().timestamp() * 1000),
                'agent_id': best_worker.get('agent_id'),
                'agent_type': best_worker.get('agent_type'),
                'priority_score': priority_score,
                'agent_score': best_worker.get('score', 0.0),
                'composite_score': self._calculate_composite_score(
                    priority_score,
                    best_worker.get('score', 0.0)
                ),
                'allocation_method': 'intelligent_scheduler',
                'workers_evaluated': len(workers),
                'ml_optimization_attempted': ml_optimization_attempted
            }

            # Adiciona dados de ML predictions se disponíveis
            if predictions:
                allocation_metadata['predicted_duration_ms'] = predictions.get('duration_ms')

                # Processa detecção de anomalia
                anomaly = predictions.get('anomaly', {})
                is_anomaly = anomaly.get('is_anomaly', False)
                allocation_metadata['anomaly_detected'] = is_anomaly

                # Registra métricas de anomalia se detectada
                if is_anomaly and self.metrics:
                    self.metrics.record_ml_anomaly(
                        anomaly_type=anomaly.get('type', 'unknown')
                    )
                    allocation_metadata['anomaly_type'] = anomaly.get('type')
                    allocation_metadata['anomaly_score'] = anomaly.get('score')

            # Adiciona ML scheduling optimization metadata
            if best_worker.get('ml_enriched', False):
                allocation_metadata['ml_scheduling_enriched'] = True
                allocation_metadata['predicted_queue_ms'] = best_worker.get('predicted_queue_ms')
                allocation_metadata['predicted_load_pct'] = best_worker.get('predicted_load_pct')
                # Esses campos serão usados para feedback loop em result_consolidation.py

            ticket['allocation_metadata'] = allocation_metadata

            duration = (datetime.now() - start_time).total_seconds()
            self.metrics.record_scheduler_allocation(
                status='success',
                fallback=False,
                duration_seconds=duration,
                has_predictions=has_predictions
            )

            self.logger.info(
                'ticket_scheduled',
                ticket_id=ticket_id,
                agent_id=best_worker.get('agent_id'),
                agent_type=best_worker.get('agent_type'),
                priority_score=priority_score,
                duration_seconds=duration
            )

            return ticket

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.error(
                'scheduling_error_ticket_rejected',
                ticket_id=ticket_id,
                error=str(e),
                error_type=type(e).__name__
            )

            # Verificar se tem predictions antes de registrar erro
            has_predictions = bool(ticket.get('predictions', {}))

            self.metrics.record_scheduler_allocation(
                status='error',
                fallback=False,
                duration_seconds=duration,
                has_predictions=has_predictions
            )

            return self._reject_ticket(ticket, 'scheduling_error', str(e))

    async def _discover_workers_cached(self, ticket: Dict) -> List[Dict]:
        """
        Descobre workers com cache.

        Timeout centralizado nesta camada (5s) para evitar timeouts aninhados.
        O timeout gRPC do ServiceRegistryClient atua como fallback adicional.

        Args:
            ticket: Ticket para descoberta

        Returns:
            Lista de workers disponíveis
        """
        cache_key = self._build_cache_key(ticket)

        cached = self._discovery_cache.get(cache_key)
        if cached:
            workers, timestamp = cached
            if datetime.now() - timestamp < self._cache_ttl:
                self.metrics.record_cache_hit()
                self.logger.debug(
                    'cache_hit',
                    cache_key=cache_key,
                    workers_count=len(workers)
                )
                return workers
            del self._discovery_cache[cache_key]

        try:
            if self.registry_breaker:
                workers = await asyncio.wait_for(
                    self.registry_breaker.call_async(
                        self.resource_allocator.discover_workers,
                        ticket
                    ),
                    timeout=5.0
                )
            else:
                workers = await asyncio.wait_for(
                    self.resource_allocator.discover_workers(ticket),
                    timeout=5.0
                )

            self._discovery_cache[cache_key] = (workers, datetime.now())
            return workers

        except CircuitBreakerError:
            if cached:
                self.logger.warning(
                    'service_registry_circuit_open_using_cache',
                    cache_key=cache_key,
                    workers_cached=len(cached[0])
                )
                return cached[0]

            self.logger.warning(
                'service_registry_circuit_open_no_cache',
                cache_key=cache_key
            )
            self.metrics.record_discovery_failure('circuit_open')
            return []
        except asyncio.TimeoutError:
            self.logger.warning(
                'discovery_timeout',
                cache_key=cache_key,
                timeout_seconds=5.0
            )
            self.metrics.record_discovery_failure('timeout')
            return []
        except Exception as e:
            self.logger.error(
                'discovery_error',
                cache_key=cache_key,
                error=str(e),
                error_type=type(e).__name__
            )
            self.metrics.record_discovery_failure(type(e).__name__)
            return []

    def _build_cache_key(self, ticket: Dict) -> str:
        """
        Constrói chave de cache baseada em capabilities e namespace.

        Args:
            ticket: Ticket para construir chave

        Returns:
            Chave de cache
        """
        capabilities = sorted(ticket.get('required_capabilities', []))
        namespace = ticket.get('namespace', 'default')
        security_level = ticket.get('security_level', 'standard')

        return f"{namespace}:{security_level}:{':'.join(capabilities)}"

    def _calculate_composite_score(
        self,
        priority_score: float,
        agent_score: float
    ) -> float:
        """
        Calcula score composto combinando prioridade e score do agente.

        Args:
            priority_score: Score de prioridade do ticket
            agent_score: Score do agente

        Returns:
            Score composto normalizado [0.0, 1.0]
        """
        # Priority score tem peso 40%, agent score tem peso 60%
        composite = (agent_score * 0.6) + (priority_score * 0.4)
        return min(max(composite, 0.0), 1.0)

    def _reject_ticket(self, ticket: Dict, rejection_reason: str, rejection_message: str) -> Dict:
        """
        Rejeita ticket quando não é possível alocar um worker válido.

        Marca o ticket como rejeitado em vez de retornar alocação fictícia.
        O ticket rejeitado não deve ser publicado no Kafka.

        Args:
            ticket: Ticket a ser rejeitado
            rejection_reason: Código do motivo da rejeição (no_workers, no_suitable_worker, scheduling_error)
            rejection_message: Mensagem descritiva da rejeição

        Returns:
            Ticket com status 'rejected' e metadata de rejeição
        """
        ticket_id = ticket.get('ticket_id', 'unknown')

        # Marcar ticket como rejeitado
        ticket['status'] = 'rejected'
        ticket['rejection_metadata'] = {
            'rejected_at': int(datetime.now().timestamp() * 1000),
            'rejection_reason': rejection_reason,
            'rejection_message': rejection_message,
            'required_capabilities': ticket.get('required_capabilities', []),
            'namespace': ticket.get('namespace', 'default'),
            'allocation_method': 'rejected'
        }

        # Não incluir allocation_metadata válido para evitar publicação
        ticket['allocation_metadata'] = None

        self.logger.warning(
            'ticket_rejected',
            ticket_id=ticket_id,
            rejection_reason=rejection_reason,
            rejection_message=rejection_message
        )

        # Emitir evento/alerta de rejeição
        if self.metrics:
            self.metrics.record_ticket_rejected(rejection_reason)

        return ticket

    async def _enrich_ticket_with_predictions(self, ticket: Dict) -> Dict:
        """
        Enriquece ticket com predições ML (duração, recursos, anomalia).
        Enriquece ticket com predições ML antes da alocação (usado para priority boosting e feedback loop).

        Args:
            ticket: Ticket a enriquecer

        Returns:
            Ticket com campo 'predictions' adicionado
        """
        predictions = {}

        # Predições de duração e recursos
        if self.scheduling_predictor:
            try:
                duration_pred = await self.scheduling_predictor.predict_duration(ticket)
                resources_pred = await self.scheduling_predictor.predict_resources(ticket)

                predictions.update({
                    'duration_ms': duration_pred.get('predicted_duration_ms', 0),
                    'confidence': duration_pred.get('confidence', 0.0),
                    'duration_confidence': duration_pred.get('confidence', 0.0),
                    'cpu_cores': resources_pred.get('cpu_cores', 1.0),
                    'memory_mb': resources_pred.get('memory_mb', 512),
                    'resources_confidence': resources_pred.get('confidence', 0.0),
                    'model_type': duration_pred.get('model_type', 'unknown')
                })

                self.logger.debug(
                    'ticket_enriched_with_scheduling_predictions',
                    ticket_id=ticket.get('ticket_id'),
                    predicted_duration_ms=predictions['duration_ms'],
                    confidence=predictions['duration_confidence']
                )

            except Exception as e:
                self.logger.warning(
                    'scheduling_prediction_failed',
                    ticket_id=ticket.get('ticket_id'),
                    error=str(e)
                )

        # Detecção de anomalias
        if self.anomaly_detector:
            try:
                anomaly_result = await self.anomaly_detector.detect_anomaly(ticket)

                predictions['anomaly'] = {
                    'is_anomaly': anomaly_result.get('is_anomaly', False),
                    'score': anomaly_result.get('anomaly_score', 0.0),
                    'type': anomaly_result.get('anomaly_type', 'unknown')
                }

                if anomaly_result.get('is_anomaly'):
                    self.logger.info(
                        'anomaly_detected_in_ticket',
                        ticket_id=ticket.get('ticket_id'),
                        anomaly_type=anomaly_result.get('anomaly_type'),
                        score=anomaly_result.get('anomaly_score')
                    )

            except Exception as e:
                self.logger.warning(
                    'anomaly_detection_failed',
                    ticket_id=ticket.get('ticket_id'),
                    error=str(e)
                )

        # Atualizar ticket apenas se houver predições
        if predictions:
            ticket['predictions'] = predictions

        return ticket

    def _can_preempt(self, preemptor_priority: str, preemptable_priority: str) -> bool:
        """
        Check if a task with preemptor_priority can preempt a task with preemptable_priority.

        Args:
            preemptor_priority: Priority of the incoming high-priority ticket
            preemptable_priority: Priority of the running task

        Returns:
            True if preemption is allowed
        """
        if not self.config.scheduler_enable_preemption:
            return False

        priority_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'CRITICAL': 4}

        preemptor_level = priority_order.get(preemptor_priority.upper(), 0)
        preemptable_level = priority_order.get(preemptable_priority.upper(), 0)

        min_preemptor = priority_order.get(
            self.config.scheduler_preemption_min_preemptor_priority.upper(), 3
        )
        max_preemptable = priority_order.get(
            self.config.scheduler_preemption_max_preemptable_priority.upper(), 1
        )

        return preemptor_level >= min_preemptor and preemptable_level <= max_preemptable

    async def preempt_low_priority_tasks(
        self,
        high_priority_ticket: Dict,
        required_workers: int = 1
    ) -> List[str]:
        """
        Preempt low-priority tasks to make room for high-priority ticket.

        Args:
            high_priority_ticket: The high-priority ticket that needs resources
            required_workers: Number of workers needed

        Returns:
            List of freed worker IDs
        """
        if not self.config.scheduler_enable_preemption:
            self.logger.debug("preemption_disabled")
            return []

        # Check concurrent preemption limit
        if len(self._active_preemptions) >= self.config.scheduler_preemption_max_concurrent:
            self.logger.warning(
                "max_concurrent_preemptions_reached",
                active_preemptions=len(self._active_preemptions),
                limit=self.config.scheduler_preemption_max_concurrent
            )
            self.metrics.record_preemption_attempt(success=False, reason="max_concurrent")
            return []

        ticket_priority = high_priority_ticket.get('priority', 'MEDIUM')

        # Find preemptable tasks
        preemptable_tasks = await self._find_preemptable_tasks(
            high_priority_ticket,
            limit=required_workers
        )

        if not preemptable_tasks:
            self.logger.info(
                "no_preemptable_tasks_found",
                ticket_id=high_priority_ticket.get('ticket_id'),
                priority=ticket_priority
            )
            return []

        freed_workers = []
        for task in preemptable_tasks:
            if len(freed_workers) >= required_workers:
                break

            worker_id = task.get('worker_id')

            # Check cooldown
            if worker_id in self._preemption_cooldowns:
                cooldown_end = self._preemption_cooldowns[worker_id]
                if datetime.now() < cooldown_end:
                    self.logger.debug(
                        "worker_in_cooldown",
                        worker_id=worker_id,
                        cooldown_remaining_seconds=(cooldown_end - datetime.now()).total_seconds()
                    )
                    continue

            # Attempt preemption
            success = await self._preempt_task(task, high_priority_ticket)

            if success:
                freed_workers.append(worker_id)

                # Set cooldown
                cooldown_seconds = self.config.scheduler_preemption_worker_cooldown_seconds
                self._preemption_cooldowns[worker_id] = datetime.now() + timedelta(seconds=cooldown_seconds)

                self.logger.info(
                    "task_preempted_successfully",
                    preempted_ticket_id=task.get('ticket_id'),
                    worker_id=worker_id,
                    preemptor_ticket_id=high_priority_ticket.get('ticket_id'),
                    preemptor_priority=ticket_priority
                )

        self.metrics.record_preemption_attempt(
            success=len(freed_workers) > 0,
            reason="success" if freed_workers else "preemption_failed"
        )

        return freed_workers

    async def _find_preemptable_tasks(
        self,
        high_priority_ticket: Dict,
        limit: int = 5
    ) -> List[Dict]:
        """
        Find tasks that can be preempted based on priority and matching capabilities.

        Args:
            high_priority_ticket: The ticket needing resources
            limit: Maximum number of preemptable tasks to return

        Returns:
            List of preemptable task metadata
        """
        preemptable = []
        ticket_priority = high_priority_ticket.get('priority', 'MEDIUM')
        required_capabilities = set(high_priority_ticket.get('required_capabilities', []))

        try:
            # Query running tasks from worker agents via Service Registry
            workers = await self._discover_workers_cached(high_priority_ticket)

            for worker in workers:
                worker_id = worker.get('agent_id')

                # Skip workers in cooldown
                if worker_id in self._preemption_cooldowns:
                    if datetime.now() < self._preemption_cooldowns[worker_id]:
                        continue

                # Check if worker has matching capabilities
                worker_capabilities = set(worker.get('capabilities', []))
                if not required_capabilities.issubset(worker_capabilities):
                    continue

                # Get running task info from worker
                running_task = worker.get('running_task', {})
                if not running_task:
                    continue

                running_priority = running_task.get('priority', 'MEDIUM')

                # Check if can preempt
                if self._can_preempt(ticket_priority, running_priority):
                    preemptable.append({
                        'ticket_id': running_task.get('ticket_id'),
                        'worker_id': worker_id,
                        'worker_endpoint': worker.get('endpoint'),
                        'priority': running_priority,
                        'started_at': running_task.get('started_at'),
                        'progress_pct': running_task.get('progress_pct', 0)
                    })

                if len(preemptable) >= limit:
                    break

            # Sort by priority (lowest first) then by progress (lowest first - less work lost)
            priority_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'CRITICAL': 4}
            preemptable.sort(
                key=lambda x: (
                    priority_order.get(x['priority'], 2),
                    x.get('progress_pct', 0)
                )
            )

        except Exception as e:
            self.logger.error(
                "find_preemptable_tasks_error",
                error=str(e),
                ticket_id=high_priority_ticket.get('ticket_id')
            )

        return preemptable[:limit]

    async def _preempt_task(
        self,
        task: Dict,
        preemptor_ticket: Dict
    ) -> bool:
        """
        Send cancellation signal to worker agent to preempt a task.

        Args:
            task: Task metadata to preempt
            preemptor_ticket: The high-priority ticket causing preemption

        Returns:
            True if preemption signal was sent successfully
        """
        ticket_id = task.get('ticket_id')
        worker_endpoint = task.get('worker_endpoint')

        if not worker_endpoint:
            self.logger.error(
                "preemption_failed_no_endpoint",
                ticket_id=ticket_id
            )
            return False

        self._active_preemptions.add(ticket_id)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{worker_endpoint}/api/v1/tasks/{ticket_id}/cancel",
                    json={
                        "reason": "preemption",
                        "preempted_by": preemptor_ticket.get('ticket_id'),
                        "grace_period_seconds": self.config.scheduler_preemption_grace_period_seconds
                    }
                )

                if response.status_code == 200:
                    self.metrics.record_task_preempted(
                        preempted_priority=task.get('priority'),
                        preemptor_priority=preemptor_ticket.get('priority')
                    )
                    return True
                else:
                    self.logger.warning(
                        "preemption_request_failed",
                        ticket_id=ticket_id,
                        status_code=response.status_code,
                        response=response.text
                    )
                    self.metrics.record_preemption_failure(reason="worker_rejected")
                    return False

        except httpx.TimeoutException:
            self.logger.error(
                "preemption_timeout",
                ticket_id=ticket_id,
                worker_endpoint=worker_endpoint
            )
            self.metrics.record_preemption_failure(reason="timeout")
            return False
        except Exception as e:
            self.logger.error(
                "preemption_error",
                ticket_id=ticket_id,
                error=str(e)
            )
            self.metrics.record_preemption_failure(reason="error")
            return False
        finally:
            self._active_preemptions.discard(ticket_id)

    async def update_workflow_priority(
        self,
        workflow_id: str,
        new_priority: int,
        reason: str = ''
    ) -> bool:
        """
        Atualiza a prioridade de um workflow no scheduler.

        Afeta o cálculo de priority_score para tickets subsequentes do workflow.

        Args:
            workflow_id: ID do workflow
            new_priority: Nova prioridade (1-10)
            reason: Razão do ajuste

        Returns:
            True se atualizado com sucesso
        """
        try:
            old_priority = self._workflow_priorities.get(workflow_id, 5)
            self._workflow_priorities[workflow_id] = new_priority

            self.logger.info(
                'workflow_priority_updated',
                workflow_id=workflow_id,
                old_priority=old_priority,
                new_priority=new_priority,
                reason=reason
            )

            # Registrar métrica de ajuste de prioridade
            if self.metrics:
                self.metrics.record_priority_adjustment(
                    workflow_id=workflow_id,
                    old_priority=old_priority,
                    new_priority=new_priority
                )

            return True

        except Exception as e:
            self.logger.error(
                'workflow_priority_update_failed',
                workflow_id=workflow_id,
                new_priority=new_priority,
                error=str(e)
            )
            return False

    async def reallocate_resources(
        self,
        workflow_id: str,
        target_allocation: Dict
    ) -> Dict:
        """
        Realoca recursos para um workflow específico.

        Atualiza o cache de alocações e notifica o ResourceAllocator.

        Args:
            workflow_id: ID do workflow
            target_allocation: Dict com cpu_millicores, memory_mb, max_parallel_tickets, scheduling_priority

        Returns:
            Dict com resultado da realocação
        """
        try:
            old_allocation = self._workflow_allocations.get(workflow_id, {})

            # Armazenar nova alocação
            self._workflow_allocations[workflow_id] = {
                'cpu_millicores': target_allocation.get('cpu_millicores', 1000),
                'memory_mb': target_allocation.get('memory_mb', 2048),
                'max_parallel_tickets': target_allocation.get('max_parallel_tickets', 10),
                'scheduling_priority': target_allocation.get('scheduling_priority', 5),
                'updated_at': datetime.now()
            }

            self.logger.info(
                'workflow_resources_reallocated',
                workflow_id=workflow_id,
                old_allocation=old_allocation,
                new_allocation=self._workflow_allocations[workflow_id]
            )

            # Registrar métrica de realocação
            if self.metrics:
                self.metrics.record_resource_reallocation(
                    workflow_id=workflow_id,
                    cpu_millicores=target_allocation.get('cpu_millicores', 1000),
                    memory_mb=target_allocation.get('memory_mb', 2048)
                )

            return {
                'success': True,
                'workflow_id': workflow_id,
                'previous_allocation': old_allocation,
                'applied_allocation': self._workflow_allocations[workflow_id],
                'message': 'Recursos realocados com sucesso'
            }

        except Exception as e:
            self.logger.error(
                'workflow_resource_reallocation_failed',
                workflow_id=workflow_id,
                error=str(e)
            )
            return {
                'success': False,
                'workflow_id': workflow_id,
                'message': f'Falha na realocação: {str(e)}'
            }

    def get_workflow_priority(self, workflow_id: str) -> int:
        """
        Obtém a prioridade atual de um workflow.

        Args:
            workflow_id: ID do workflow

        Returns:
            Prioridade do workflow (default: 5)
        """
        return self._workflow_priorities.get(workflow_id, 5)

    def get_workflow_allocation(self, workflow_id: str) -> Dict:
        """
        Obtém a alocação de recursos atual de um workflow.

        Args:
            workflow_id: ID do workflow

        Returns:
            Dict com alocação de recursos (default values se não definido)
        """
        return self._workflow_allocations.get(workflow_id, {
            'cpu_millicores': 1000,
            'memory_mb': 2048,
            'max_parallel_tickets': 10,
            'scheduling_priority': 5
        })
