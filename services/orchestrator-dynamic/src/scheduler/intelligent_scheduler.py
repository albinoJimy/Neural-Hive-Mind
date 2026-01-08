"""
IntelligentScheduler - Orquestrador principal de scheduling de tickets.

Coordena PriorityCalculator e ResourceAllocator para alocação otimizada de recursos.
Implementa cache de descobertas e fallback para Service Registry indisponível.
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from functools import lru_cache

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
