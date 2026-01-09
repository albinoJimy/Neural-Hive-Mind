import time
from datetime import datetime
from typing import Optional

import grpc
import structlog
from prometheus_client import Counter, Histogram

from src.clients.mongodb_client import MongoDBClient
from src.models.optimization_event import OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.services.experiment_manager import ExperimentManager
from src.services.optimization_engine import OptimizationEngine
from src.services.slo_adjuster import SLOAdjuster
from src.services.weight_recalibrator import WeightRecalibrator

logger = structlog.get_logger()

# Metricas Prometheus para gRPC
GRPC_REQUESTS_TOTAL = Counter(
    'optimizer_grpc_requests_total',
    'Total de requisicoes gRPC',
    ['method', 'status']
)

GRPC_REQUEST_DURATION_SECONDS = Histogram(
    'optimizer_grpc_request_duration_seconds',
    'Duracao das requisicoes gRPC em segundos',
    ['method'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Proto imports - will be available after `make proto` compilation
try:
    from src.proto import optimizer_agent_pb2, optimizer_agent_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    logger.warning("proto_not_compiled", message="Run 'make proto' to compile protocol buffers")


class OptimizerServicer(optimizer_agent_pb2_grpc.OptimizerAgentServicer if PROTO_AVAILABLE else object):
    """
    gRPC servicer para Optimizer Agent.

    Implementa os métodos RPC definidos em optimizer_agent.proto.
    """

    def __init__(
        self,
        optimization_engine: Optional[OptimizationEngine] = None,
        experiment_manager: Optional[ExperimentManager] = None,
        weight_recalibrator: Optional[WeightRecalibrator] = None,
        slo_adjuster: Optional[SLOAdjuster] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        load_predictor=None,
        scheduling_optimizer=None,
        settings=None,
    ):
        self.optimization_engine = optimization_engine
        self.experiment_manager = experiment_manager
        self.weight_recalibrator = weight_recalibrator
        self.slo_adjuster = slo_adjuster
        self.mongodb_client = mongodb_client
        self.load_predictor = load_predictor
        self.scheduling_optimizer = scheduling_optimizer
        self.settings = settings

    async def TriggerOptimization(self, request, context):
        """
        Trigger manual de otimização.

        Args:
            request: TriggerOptimizationRequest
            context: gRPC context

        Returns:
            TriggerOptimizationResponse
        """
        start_time = time.time()
        method = 'TriggerOptimization'
        try:
            logger.info(
                "trigger_optimization_requested",
                component=request.component,
                optimization_type=request.optimization_type,
            )

            # Criar hipótese sintética
            hypothesis = OptimizationHypothesis(
                hypothesis_id=f"grpc-{request.component}-{request.optimization_type}",
                optimization_type=OptimizationType(request.optimization_type),
                target_component=request.component,
                hypothesis_text=request.context.get('justification', 'Manual trigger via gRPC'),
                rationale=request.context.get('justification', 'Manual trigger via gRPC'),
                proposed_adjustments=[],
                baseline_metrics={},
                expected_improvement=0.1,
                confidence=0.8,
                risk_score=0.3,
            )

            # Aplicar otimização
            optimization_event = None

            if request.optimization_type == "WEIGHT_RECALIBRATION":
                if self.weight_recalibrator is None:
                    GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                    context.abort(grpc.StatusCode.UNAVAILABLE, "WeightRecalibrator not initialized")
                optimization_event = await self.weight_recalibrator.apply_weight_recalibration(hypothesis)
            elif request.optimization_type == "SLO_ADJUSTMENT":
                if self.slo_adjuster is None:
                    GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                    context.abort(grpc.StatusCode.UNAVAILABLE, "SLOAdjuster not initialized")
                optimization_event = await self.slo_adjuster.apply_slo_adjustment(hypothesis)

            if not optimization_event:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.INTERNAL, "Failed to apply optimization")

            logger.info("optimization_triggered", optimization_id=optimization_event.optimization_id)
            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            # Return proto response when available
            if PROTO_AVAILABLE:
                return optimizer_agent_pb2.TriggerOptimizationResponse(
                    experiment_id=optimization_event.optimization_id,
                    status="APPLIED",
                    message="Optimization applied successfully"
                )
            else:
                return {"experiment_id": optimization_event.optimization_id, "status": "APPLIED"}

        except Exception as e:
            logger.error("trigger_optimization_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to trigger optimization: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def GetOptimizationStatus(self, request, context):
        """
        Obter status de uma otimização.

        Args:
            request: GetOptimizationStatusRequest
            context: gRPC context

        Returns:
            GetOptimizationStatusResponse
        """
        start_time = time.time()
        method = 'GetOptimizationStatus'
        try:
            logger.info("get_optimization_status_requested", optimization_id=request.optimization_id)

            if not self.mongodb_client:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            optimization = await self.mongodb_client.get_optimization(request.optimization_id)

            if not optimization:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='not_found').inc()
                context.abort(grpc.StatusCode.NOT_FOUND, f"Optimization {request.optimization_id} not found")

            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                # Extrair métricas do documento MongoDB
                metrics = {}
                if "baseline_metrics" in optimization:
                    metrics.update(optimization.get("baseline_metrics", {}))
                if "achieved_metrics" in optimization:
                    metrics.update(optimization.get("achieved_metrics", {}))

                return optimizer_agent_pb2.GetOptimizationStatusResponse(
                    optimization_id=optimization.get("optimization_id", ""),
                    status=optimization.get("approval_status", "UNKNOWN"),
                    improvement_percentage=optimization.get("improvement_percentage", 0.0),
                    metrics=metrics
                )
            else:
                return optimization

        except Exception as e:
            logger.error("get_optimization_status_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to get optimization status: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def ListOptimizations(self, request, context):
        """
        Listar otimizações.

        Args:
            request: ListOptimizationsRequest
            context: gRPC context

        Returns:
            ListOptimizationsResponse (stream)
        """
        start_time = time.time()
        method = 'ListOptimizations'
        try:
            logger.info("list_optimizations_requested", page_size=request.page_size)

            if not self.mongodb_client:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            # Construir filtros
            filters = {}
            if request.component:
                filters["component"] = request.component
            if request.optimization_type:
                filters["optimization_type"] = request.optimization_type

            # Buscar otimizações
            optimizations = await self.mongodb_client.list_optimizations(
                filters=filters, skip=0, limit=request.page_size or 50
            )

            logger.info("optimizations_listed", count=len(optimizations))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                summaries = []
                for opt in optimizations:
                    summaries.append(optimizer_agent_pb2.OptimizationSummary(
                        optimization_id=opt.get("optimization_id", ""),
                        optimization_type=opt.get("optimization_type", ""),
                        component=opt.get("target_component", ""),
                        improvement_percentage=opt.get("improvement_percentage", 0.0),
                        applied_at=opt.get("applied_at", 0),
                        status=opt.get("approval_status", "UNKNOWN")
                    ))
                return optimizer_agent_pb2.ListOptimizationsResponse(
                    optimizations=summaries,
                    total=len(optimizations)
                )
            else:
                return {"optimizations": optimizations, "total": len(optimizations)}

        except Exception as e:
            logger.error("list_optimizations_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to list optimizations: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def RollbackOptimization(self, request, context):
        """
        Reverter otimização.

        Args:
            request: RollbackOptimizationRequest
            context: gRPC context

        Returns:
            RollbackOptimizationResponse
        """
        start_time = time.time()
        method = 'RollbackOptimization'
        try:
            logger.info("rollback_optimization_requested", optimization_id=request.optimization_id)

            if not self.mongodb_client:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            # Obter otimização
            optimization = await self.mongodb_client.get_optimization(request.optimization_id)

            if not optimization:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='not_found').inc()
                context.abort(grpc.StatusCode.NOT_FOUND, f"Optimization {request.optimization_id} not found")

            optimization_type = OptimizationType(optimization.get("optimization_type"))

            # Executar rollback
            success = False

            if optimization_type == OptimizationType.WEIGHT_RECALIBRATION:
                if self.weight_recalibrator is None:
                    GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                    context.abort(grpc.StatusCode.UNAVAILABLE, "WeightRecalibrator not initialized")
                success = await self.weight_recalibrator.rollback_weight_recalibration(request.optimization_id)
            elif optimization_type == OptimizationType.SLO_ADJUSTMENT:
                if self.slo_adjuster is None:
                    GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                    context.abort(grpc.StatusCode.UNAVAILABLE, "SLOAdjuster not initialized")
                success = await self.slo_adjuster.rollback_slo_adjustment(request.optimization_id)

            if not success:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.INTERNAL, "Failed to rollback optimization")

            logger.info("optimization_rolled_back", optimization_id=request.optimization_id)
            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                return optimizer_agent_pb2.RollbackOptimizationResponse(
                    status="ROLLED_BACK",
                    message="Optimization rolled back successfully"
                )
            else:
                return {"status": "ROLLED_BACK", "message": "Rolled back successfully"}

        except Exception as e:
            logger.error("rollback_optimization_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to rollback optimization: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def GetStatistics(self, request, context):
        """
        Obter estatísticas de otimizações.

        Args:
            request: GetStatisticsRequest
            context: gRPC context

        Returns:
            GetStatisticsResponse
        """
        start_time = time.time()
        method = 'GetStatistics'
        try:
            logger.info("get_statistics_requested")

            if not self.mongodb_client:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            # Buscar todas otimizações
            all_optimizations = await self.mongodb_client.list_optimizations(filters={}, skip=0, limit=1000)

            total = len(all_optimizations)
            success_count = sum(1 for opt in all_optimizations if opt.get("improvement_percentage", 0) >= 0)
            success_rate = success_count / total if total > 0 else 0.0

            improvements = [opt.get("improvement_percentage", 0) for opt in all_optimizations]
            average_improvement = sum(improvements) / len(improvements) if improvements else 0.0

            # Agrupar por tipo
            by_type = {}
            for opt in all_optimizations:
                opt_type = opt.get("optimization_type", "UNKNOWN")
                by_type[opt_type] = by_type.get(opt_type, 0) + 1

            # Agrupar por componente
            by_component = {}
            for opt in all_optimizations:
                component = opt.get("target_component", "UNKNOWN")
                by_component[component] = by_component.get(component, 0) + 1

            logger.info("statistics_retrieved", total=total, success_rate=success_rate)
            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                return optimizer_agent_pb2.GetStatisticsResponse(
                    total_optimizations=total,
                    success_rate=success_rate,
                    average_improvement=average_improvement,
                    by_type=by_type,
                    by_component=by_component
                )
            else:
                return {
                    "total_optimizations": total,
                    "success_rate": success_rate,
                    "average_improvement": average_improvement,
                    "by_type": by_type,
                    "by_component": by_component
                }

        except Exception as e:
            logger.error("get_statistics_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to get statistics: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def HealthCheck(self, request, context):
        """
        Health check.

        Args:
            request: HealthCheckRequest
            context: gRPC context

        Returns:
            HealthCheckResponse
        """
        start_time = time.time()
        method = 'HealthCheck'
        try:
            # Verificar componentes críticos
            healthy = True
            message = "All systems operational"

            if not self.optimization_engine:
                healthy = False
                message = "OptimizationEngine not initialized"
            elif not self.mongodb_client:
                healthy = False
                message = "MongoDB client not initialized"

            status = 'healthy' if healthy else 'unhealthy'
            GRPC_REQUESTS_TOTAL.labels(method=method, status=status).inc()

            if PROTO_AVAILABLE:
                return optimizer_agent_pb2.HealthCheckResponse(
                    status="HEALTHY" if healthy else "UNHEALTHY",
                    version="1.0.0"
                )
            else:
                return {"healthy": healthy, "message": message, "version": "1.0.0"}

        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Health check failed: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def GetLoadForecast(self, request, context):
        """
        Obter previsão de carga futura.

        Args:
            request: LoadForecastRequest
            context: gRPC context

        Returns:
            LoadForecastResponse com forecast e metadata
        """
        start_time = time.time()
        method = 'GetLoadForecast'
        try:
            if not self.load_predictor:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "LoadPredictor não inicializado")

            horizon_minutes = request.horizon_minutes
            include_ci = request.include_confidence_intervals

            logger.info("get_load_forecast_request", horizon_minutes=horizon_minutes, include_ci=include_ci)

            # Gerar forecast
            forecast_data = await self.load_predictor.predict_load(
                horizon_minutes=horizon_minutes,
                include_confidence_intervals=include_ci
            )

            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                forecast_points = []
                for point in forecast_data.get("forecast", []):
                    # Converter timestamp para string ISO 8601 se for int
                    timestamp = point.get("timestamp", 0)
                    if isinstance(timestamp, (int, float)):
                        timestamp_str = datetime.fromtimestamp(timestamp).isoformat()
                    else:
                        timestamp_str = str(timestamp)

                    # Mapear campos para proto
                    ticket_count = int(point.get("predicted_load", 0))
                    confidence_lower = int(point.get("lower_bound", 0))
                    confidence_upper = int(point.get("upper_bound", 0))

                    # Criar ResourceDemand (estimativa baseada na carga)
                    resource_demand = optimizer_agent_pb2.ResourceDemand(
                        cpu_cores=round(ticket_count * 0.1, 2),  # Estimativa: 0.1 core por ticket
                        memory_mb=ticket_count * 50  # Estimativa: 50MB por ticket
                    )

                    forecast_points.append(optimizer_agent_pb2.ForecastPoint(
                        timestamp=timestamp_str,
                        ticket_count=ticket_count,
                        resource_demand=resource_demand,
                        confidence_lower=confidence_lower,
                        confidence_upper=confidence_upper
                    ))

                metadata = forecast_data.get("metadata", {})
                return optimizer_agent_pb2.LoadForecastResponse(
                    forecast=forecast_points,
                    metadata=optimizer_agent_pb2.ForecastMetadata(
                        model_horizon=metadata.get("model_horizon", horizon_minutes),
                        horizon_requested=horizon_minutes,
                        forecast_generated_at=datetime.utcnow().isoformat(),
                        data_points_used=metadata.get("data_points_used", len(forecast_points)),
                        confidence_level=metadata.get("confidence_level", 0.95)
                    )
                )
            else:
                return {
                    "forecast": forecast_data.get("forecast", []),
                    "metadata": forecast_data.get("metadata", {})
                }

        except ValueError as e:
            logger.warning("invalid_forecast_request", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='invalid_argument').inc()
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("get_load_forecast_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Forecast failed: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def GetSchedulingRecommendation(self, request, context):
        """
        Obter recomendação de otimização de agendamento.

        Args:
            request: SchedulingRecommendationRequest
            context: gRPC context

        Returns:
            SchedulingRecommendationResponse com ação e justificativa
        """
        start_time = time.time()
        method = 'GetSchedulingRecommendation'
        try:
            if not self.scheduling_optimizer:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "SchedulingOptimizer não inicializado")

            # Construir estado atual
            current_state = {
                "current_load": request.current_load,
                "worker_utilization": request.worker_utilization,
                "queue_depth": request.queue_depth,
                "sla_compliance": request.sla_compliance,
            }

            logger.info("get_scheduling_recommendation_request", state=current_state)

            # Gerar recomendação (com forecast opcional)
            load_forecast = None
            if self.load_predictor:
                try:
                    load_forecast = await self.load_predictor.predict_load(
                        horizon_minutes=60,
                        include_confidence_intervals=False
                    )
                except Exception as e:
                    logger.warning("forecast_for_recommendation_failed", error=str(e))

            recommendation = await self.scheduling_optimizer.optimize_scheduling(
                current_state=current_state,
                load_forecast=load_forecast
            )

            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                return optimizer_agent_pb2.SchedulingRecommendationResponse(
                    action=recommendation.get("action", "NO_ACTION"),
                    justification=recommendation.get("justification", ""),
                    expected_improvement=recommendation.get("expected_improvement", 0.0),
                    risk_score=recommendation.get("risk_score", 0.0),
                    confidence=recommendation.get("confidence", 0.0)
                )
            else:
                return {
                    "action": recommendation.get("action", "NO_ACTION"),
                    "justification": recommendation.get("justification", ""),
                    "expected_improvement": recommendation.get("expected_improvement", 0.0),
                    "risk_score": recommendation.get("risk_score", 0.0),
                    "confidence": recommendation.get("confidence", 0.0),
                }

        except ValueError as e:
            logger.warning("invalid_scheduling_request", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='invalid_argument').inc()
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("get_scheduling_recommendation_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Recommendation failed: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)

    async def GetSchedulingMetrics(self, request, context):
        """
        Obter métricas de performance da política de agendamento.

        Args:
            request: SchedulingMetricsRequest
            context: gRPC context

        Returns:
            SchedulingMetricsResponse com métricas agregadas
        """
        start_time = time.time()
        method = 'GetSchedulingMetrics'
        try:
            if not self.scheduling_optimizer:
                GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
                context.abort(grpc.StatusCode.UNAVAILABLE, "SchedulingOptimizer não inicializado")

            time_range_hours = request.time_range_hours or 24

            logger.info("get_scheduling_metrics_request", time_range_hours=time_range_hours)

            # Calcular métricas da política
            recent_rewards = self.scheduling_optimizer.recent_rewards
            if recent_rewards:
                average_reward = sum(recent_rewards) / len(recent_rewards)
            else:
                average_reward = 0.0

            # Contar ações aplicadas (approximado)
            action_counts = {}
            for action in self.scheduling_optimizer.recent_actions:
                action_counts[action.value] = action_counts.get(action.value, 0) + 1

            # Success rate (recompensas positivas)
            if recent_rewards:
                success_rate = sum(1 for r in recent_rewards if r > 0) / len(recent_rewards)
            else:
                success_rate = 0.0

            states_explored = len(self.scheduling_optimizer.q_table)

            GRPC_REQUESTS_TOTAL.labels(method=method, status='success').inc()

            if PROTO_AVAILABLE:
                return optimizer_agent_pb2.SchedulingMetricsResponse(
                    average_reward=average_reward,
                    policy_success_rate=success_rate,
                    action_counts=action_counts,
                    states_explored=states_explored
                )
            else:
                return {
                    "average_reward": average_reward,
                    "policy_success_rate": success_rate,
                    "action_counts": action_counts,
                    "states_explored": states_explored,
                }

        except Exception as e:
            logger.error("get_scheduling_metrics_failed", error=str(e))
            GRPC_REQUESTS_TOTAL.labels(method=method, status='error').inc()
            context.abort(grpc.StatusCode.INTERNAL, f"Metrics failed: {str(e)}")
        finally:
            GRPC_REQUEST_DURATION_SECONDS.labels(method=method).observe(time.time() - start_time)
