"""
SchedulingOptimizer - Orquestrador de otimização de scheduling ML.

Coordena predições remotas (optimizer-agents) com fallbacks locais (LoadPredictor)
para enriquecer decisões de alocação de workers.
"""

import time
import structlog
from typing import Dict, Any, Optional, List
from neural_hive_observability import get_tracer
from opentelemetry import trace

from src.config.settings import OrchestratorSettings
from src.clients.optimizer_grpc_client import OptimizerGrpcClient
from src.ml.load_predictor import LoadPredictor
from src.observability.metrics import OrchestratorMetrics

logger = structlog.get_logger(__name__)


class SchedulingOptimizer:
    """
    Facade para otimização de scheduling com ML.

    Arquitetura dual-mode:
    1. Tenta usar optimizer-agents remoto (Prophet/ARIMA + Q-learning RL)
    2. Fallback para LoadPredictor local (heurísticas leves)

    Responsabilidades:
    - Obter load forecasts de optimizer-agents
    - Enriquecer workers com predições de queue time e load
    - Aplicar recomendações de RL policy
    - Coletar feedback de allocation outcomes para treinamento RL
    """

    def __init__(
        self,
        config: OrchestratorSettings,
        optimizer_client: Optional[OptimizerGrpcClient],
        local_predictor: LoadPredictor,
        kafka_producer,
        metrics: OrchestratorMetrics
    ):
        """
        Inicializa SchedulingOptimizer.

        Args:
            config: Configurações do orchestrator
            optimizer_client: Cliente gRPC para optimizer-agents (opcional)
            local_predictor: LoadPredictor local para fallback
            kafka_producer: Producer Kafka para feedback loop
            metrics: OrchestratorMetrics para observabilidade
        """
        self.config = config
        self.optimizer_client = optimizer_client
        self.local_predictor = local_predictor
        self.kafka_producer = kafka_producer
        self.metrics = metrics
        self.logger = logger.bind(component="scheduling_optimizer")
        self.tracer = get_tracer()

        # Thresholds
        self.confidence_threshold = 0.6  # Mínimo para aplicar recomendações RL
        self.optimization_timeout = config.ml_optimization_timeout_seconds

    async def get_load_forecast(
        self,
        horizon_minutes: int = 60
    ) -> Optional[Dict]:
        """
        Obtém previsão de carga futura.

        Tenta usar optimizer-agents remoto, fallback para None se indisponível.

        Args:
            horizon_minutes: Horizonte de previsão

        Returns:
            Dict com forecast ou None
        """
        start_time = time.time()

        with self.tracer.start_as_current_span(
            "scheduling.get_load_forecast",
            attributes={
                "neural.hive.ml.horizon_minutes": horizon_minutes,
                "neural.hive.ml.source": "remote" if self.optimizer_client else "none"
            }
        ) as span:
            try:
                # Se optimizer integration desabilitado, retornar None
                if not self.config.enable_optimizer_integration:
                    self.logger.debug("optimizer_integration_disabled")
                    return None

                # Se cliente não disponível, retornar None
                if not self.optimizer_client:
                    self.logger.debug("optimizer_client_not_available")
                    self.metrics.update_optimizer_availability(available=False)
                    return None

                # Tentar obter forecast do remote optimizer
                forecast = await self.optimizer_client.get_load_forecast(
                    horizon_minutes=horizon_minutes,
                    include_confidence_intervals=True
                )

                # Métricas
                duration_seconds = time.time() - start_time

                if forecast:
                    span.set_attribute("neural.hive.ml.forecast_points", len(forecast.get('forecast', [])))
                    self.metrics.update_optimizer_availability(available=True)
                    self.metrics.record_ml_optimization(
                        optimization_type='load_forecast',
                        source='remote',
                        duration_seconds=duration_seconds
                    )

                    self.logger.info(
                        "load_forecast_obtained_from_remote",
                        horizon_minutes=horizon_minutes,
                        points=len(forecast.get('forecast', [])),
                        latency_ms=duration_seconds * 1000
                    )
                else:
                    self.metrics.update_optimizer_availability(available=False)
                    self.logger.warning("load_forecast_remote_unavailable")

                return forecast

            except Exception as e:
                self.logger.error(
                    "load_forecast_error",
                    error=str(e)
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                self.metrics.update_optimizer_availability(available=False)
                return None

    async def optimize_allocation(
        self,
        ticket: Dict[str, Any],
        workers: List[Dict],
        load_forecast: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Enriquece workers com predições ML para otimizar alocação.

        Args:
            ticket: Execution ticket
            workers: Lista de workers candidatos
            load_forecast: Forecast de carga (opcional)

        Returns:
            Workers enriquecidos com predicted_queue_ms e predicted_load_pct
        """
        start_time = time.time()

        with self.tracer.start_as_current_span(
            "scheduling.optimize_allocation",
            attributes={
                "neural.hive.ticket.id": ticket.get('ticket_id'),
                "neural.hive.ml.workers_count": len(workers)
            }
        ) as span:
            try:
                # Coletar estado atual para RL recommendation
                current_state = await self._build_current_state(ticket, workers)

                # Tentar obter recomendação de RL policy
                recommendation = None
                if (self.config.enable_optimizer_integration and
                    self.optimizer_client):

                    try:
                        recommendation = await self.optimizer_client.get_scheduling_recommendation(
                            current_state=current_state
                        )

                        if recommendation:
                            self.logger.info(
                                "rl_recommendation_obtained",
                                action=recommendation.get('action'),
                                confidence=recommendation.get('confidence')
                            )
                    except Exception as e:
                        self.logger.warning(
                            "rl_recommendation_error",
                            error=str(e)
                        )

                # Enriquecer cada worker com predições
                enriched_workers = []
                for worker in workers:
                    enriched = await self._enrich_worker_with_predictions(
                        worker=worker,
                        ticket=ticket,
                        load_forecast=load_forecast
                    )
                    enriched_workers.append(enriched)

                # Aplicar recomendação de RL se disponível e confiável
                if recommendation and recommendation.get('confidence', 0) >= self.confidence_threshold:
                    enriched_workers = self._apply_scheduling_recommendation(
                        recommendation=recommendation,
                        workers=enriched_workers
                    )

                    source = 'remote'
                    optimization_type = 'rl_recommendation'
                else:
                    source = 'local'
                    optimization_type = 'heuristic'

                # Métricas
                duration_seconds = time.time() - start_time
                span.set_attribute("neural.hive.ml.optimization_source", source)
                span.set_attribute("neural.hive.ml.workers_enriched", len(enriched_workers))
                self.metrics.record_ml_optimization(
                    optimization_type=optimization_type,
                    source=source,
                    duration_seconds=duration_seconds
                )

                self.logger.info(
                    "allocation_optimization_complete",
                    ticket_id=ticket.get('ticket_id'),
                    workers_enriched=len(enriched_workers),
                    optimization_source=source,
                    latency_ms=duration_seconds * 1000
                )

                return enriched_workers

            except Exception as e:
                self.logger.error(
                    "optimize_allocation_error",
                    ticket_id=ticket.get('ticket_id'),
                    error=str(e)
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                self.metrics.record_ml_error('allocation_optimization')

                # Fallback: retornar workers originais
                return workers

    async def _enrich_worker_with_predictions(
        self,
        worker: Dict,
        ticket: Dict[str, Any],
        load_forecast: Optional[Dict]
    ) -> Dict:
        """
        Enriquece worker com predições de queue time e load.

        Args:
            worker: Informações do worker
            ticket: Execution ticket
            load_forecast: Forecast de carga (opcional)

        Returns:
            Worker enriquecido
        """
        worker_id = worker.get('agent_id', 'unknown')

        with self.tracer.start_as_current_span(
            "scheduling.enrich_worker",
            attributes={
                "neural.hive.worker.id": worker_id
            }
        ) as span:
            try:
                # Predizer queue time usando local predictor
                predicted_queue_ms = await self.local_predictor.predict_queue_time(
                    worker_id=worker_id,
                    ticket=ticket
                )

                # Predizer worker load
                predicted_load_pct = await self.local_predictor.predict_worker_load(
                    worker_id=worker_id
                )

                # Adicionar campos ao worker dict
                enriched = {
                    **worker,
                    'predicted_queue_ms': predicted_queue_ms,
                    'predicted_load_pct': predicted_load_pct,
                    'ml_enriched': True
                }

                span.set_attribute("neural.hive.ml.predicted_queue_ms", predicted_queue_ms)
                span.set_attribute("neural.hive.ml.predicted_load_pct", predicted_load_pct)

                self.logger.debug(
                    "worker_enriched_with_predictions",
                    worker_id=worker_id,
                    predicted_queue_ms=predicted_queue_ms,
                    predicted_load_pct=predicted_load_pct
                )

                return enriched

            except Exception as e:
                self.logger.error(
                    "worker_enrichment_error",
                    worker_id=worker_id,
                    error=str(e)
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                # Fallback: retornar worker sem enrichment
                return {
                    **worker,
                    'predicted_queue_ms': 2000.0,
                    'predicted_load_pct': 0.5,
                    'ml_enriched': False
                }

    def _apply_scheduling_recommendation(
        self,
        recommendation: Dict,
        workers: List[Dict]
    ) -> List[Dict]:
        """
        Aplica recomendação de RL policy aos worker scores.

        Define o campo 'rl_boost' nos workers, que será usado pelo ResourceAllocator
        como multiplicador do score calculado.

        Estratégias por ação:
        - SCALE_UP: Prefere workers com baixa carga (<30%) para distribuir tarefas
          e incentivar escalonamento horizontal. Boost: 1.2x (20%).
        - CONSOLIDATE: Prefere workers com carga moderada (>50%) para consolidar
          tarefas e otimizar utilização de recursos. Boost: 1.1x (10%).
        - MAINTAIN: Sem ajuste, usa score base do ResourceAllocator.

        Args:
            recommendation: Recomendação do RL agent
            workers: Workers enriquecidos

        Returns:
            Workers com rl_boost aplicado
        """
        action = recommendation.get('action', 'MAINTAIN')
        confidence = recommendation.get('confidence', 0.0)

        self.logger.info(
            "applying_rl_recommendation",
            action=action,
            confidence=confidence
        )

        # Aplicar ação de RL com boost conforme estratégia
        workers_boosted = 0

        if action == 'SCALE_UP':
            # Preferir workers com menos carga para distribuir tarefas
            for worker in workers:
                load = worker.get('predicted_load_pct', 0.5)
                if load < 0.3:
                    worker['rl_boost'] = 1.2  # Boost 20%
                    workers_boosted += 1
                else:
                    worker['rl_boost'] = 1.0  # Sem boost
        elif action == 'CONSOLIDATE':
            # Preferir workers com mais carga para consolidação
            for worker in workers:
                load = worker.get('predicted_load_pct', 0.5)
                if load > 0.5:
                    worker['rl_boost'] = 1.1  # Boost 10%
                    workers_boosted += 1
                else:
                    worker['rl_boost'] = 1.0  # Sem boost
        else:
            # MAINTAIN ou ação desconhecida: sem ajuste
            for worker in workers:
                worker['rl_boost'] = 1.0

        self.logger.info(
            "rl_recommendation_applied",
            action=action,
            workers_total=len(workers),
            workers_boosted=workers_boosted
        )

        return workers

    async def record_allocation_outcome(
        self,
        ticket: Dict[str, Any],
        worker: Dict,
        actual_duration_ms: float
    ):
        """
        Registra outcome de alocação para feedback loop de RL.

        Publica mensagem em Kafka para treinamento assíncrono.

        Args:
            ticket: Ticket executado
            worker: Worker alocado
            actual_duration_ms: Duração real de execução
        """
        try:
            if not self.config.ml_allocation_outcomes_enabled:
                return

            # Construir outcome event
            outcome = {
                'ticket_id': ticket.get('ticket_id'),
                'worker_id': worker.get('agent_id'),
                'predicted_queue_ms': worker.get('predicted_queue_ms', 0),
                'predicted_load_pct': worker.get('predicted_load_pct', 0),
                'actual_duration_ms': actual_duration_ms,
                'timestamp': time.time(),
                'success': ticket.get('status') == 'COMPLETED',
                'risk_band': ticket.get('risk_band'),
                'priority_score': ticket.get('priority_score')
            }

            # Publicar no tópico Kafka (async, non-blocking)
            topic = self.config.ml_allocation_outcomes_topic

            if self.kafka_producer:
                await self.kafka_producer.send(
                    topic=topic,
                    value=outcome,
                    key=ticket.get('ticket_id')
                )

                self.logger.info(
                    "allocation_outcome_recorded",
                    ticket_id=ticket.get('ticket_id'),
                    worker_id=worker.get('agent_id'),
                    topic=topic
                )

                # Calcular e registrar allocation quality
                quality_score = self._calculate_allocation_quality(
                    predicted_queue_ms=outcome['predicted_queue_ms'],
                    actual_duration_ms=actual_duration_ms,
                    success=outcome['success']
                )

                self.metrics.record_allocation_quality(
                    quality_score=quality_score,
                    used_ml_optimization=worker.get('ml_enriched', False)
                )

                # Registrar erro de predição de queue
                if outcome['predicted_queue_ms'] > 0:
                    # Usar duração real como proxy de tempo real de fila
                    self.metrics.record_queue_prediction_error(
                        predicted_ms=outcome['predicted_queue_ms'],
                        actual_ms=actual_duration_ms
                    )

        except Exception as e:
            self.logger.error(
                "record_outcome_error",
                ticket_id=ticket.get('ticket_id'),
                error=str(e)
            )

    def _calculate_allocation_quality(
        self,
        predicted_queue_ms: float,
        actual_duration_ms: float,
        success: bool
    ) -> float:
        """
        Calcula score de qualidade da alocação.

        Args:
            predicted_queue_ms: Queue time previsto
            actual_duration_ms: Duração real
            success: Se ticket foi bem-sucedido

        Returns:
            Quality score (0-1)
        """
        # Base: sucesso vale 0.7
        base_score = 0.7 if success else 0.3

        # Penalizar erro de predição grande
        if predicted_queue_ms > 0:
            error_ratio = abs(predicted_queue_ms - actual_duration_ms) / predicted_queue_ms
            prediction_accuracy = max(0.0, 1.0 - error_ratio)
        else:
            prediction_accuracy = 0.5

        # Score composto
        quality = base_score * 0.7 + prediction_accuracy * 0.3

        return min(max(quality, 0.0), 1.0)

    async def _build_current_state(
        self,
        ticket: Dict[str, Any],
        workers: List[Dict]
    ) -> Dict:
        """
        Constrói estado atual para RL recommendation.

        Args:
            ticket: Execution ticket
            workers: Workers candidatos

        Returns:
            Dict com current_load, worker_utilization, queue_depth, sla_compliance
        """
        try:
            # Current load: número de tickets ativos
            current_load = await self._get_current_ticket_count()

            # Worker utilization: média de carga dos workers
            loads = []
            for worker in workers:
                load = await self.local_predictor.predict_worker_load(
                    worker.get('agent_id', 'unknown')
                )
                loads.append(load)

            avg_utilization = sum(loads) / len(loads) if loads else 0.5

            # Queue depth: soma de queue depths
            queue_depth = sum([
                await self.local_predictor._estimate_queue_depth(
                    worker.get('agent_id', 'unknown')
                )
                for worker in workers
            ])

            # SLA compliance: assumir 0.95 (a ser integrado com SLA Management)
            sla_compliance = 0.95

            return {
                'current_load': current_load,
                'worker_utilization': avg_utilization,
                'queue_depth': queue_depth,
                'sla_compliance': sla_compliance
            }

        except Exception as e:
            self.logger.error("build_state_error", error=str(e))
            # Fallback state
            return {
                'current_load': 10,
                'worker_utilization': 0.5,
                'queue_depth': 5,
                'sla_compliance': 0.95
            }

    async def _get_current_ticket_count(self) -> int:
        """
        Obtém número de tickets ativos no sistema.

        Returns:
            Contagem de tickets ativos
        """
        # Verificar se MongoDB está disponível
        if not self.local_predictor.mongodb_client:
            self.logger.debug("get_ticket_count_skipped_no_mongodb")
            return 10  # Default sem MongoDB

        try:
            count = await self.local_predictor.mongodb_client.db[
                self.config.mongodb_collection_tickets
            ].count_documents({
                'status': {'$in': ['PENDING', 'EXECUTING']}
            })

            return count

        except Exception as e:
            self.logger.error("get_ticket_count_error", error=str(e))
            return 10  # Default
