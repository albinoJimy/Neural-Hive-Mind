from typing import Optional

import grpc
import structlog

from src.clients.mongodb_client import MongoDBClient
from src.models.optimization_event import OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.services.experiment_manager import ExperimentManager
from src.services.optimization_engine import OptimizationEngine
from src.services.slo_adjuster import SLOAdjuster
from src.services.weight_recalibrator import WeightRecalibrator

logger = structlog.get_logger()

# TODO: Import generated proto files when compiled
# from src.proto import optimizer_agent_pb2, optimizer_agent_pb2_grpc


class OptimizerServicer:
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
    ):
        self.optimization_engine = optimization_engine
        self.experiment_manager = experiment_manager
        self.weight_recalibrator = weight_recalibrator
        self.slo_adjuster = slo_adjuster
        self.mongodb_client = mongodb_client

    async def TriggerOptimization(self, request, context):
        """
        Trigger manual de otimização.

        Args:
            request: TriggerOptimizationRequest
            context: gRPC context

        Returns:
            TriggerOptimizationResponse
        """
        try:
            logger.info(
                "trigger_optimization_requested",
                target_component=request.target_component,
                optimization_type=request.optimization_type,
            )

            # Criar hipótese sintética
            hypothesis = OptimizationHypothesis(
                hypothesis_id=f"grpc-{request.target_component}-{request.optimization_type}",
                optimization_type=OptimizationType(request.optimization_type),
                target_component=request.target_component,
                hypothesis_text=request.justification,
                rationale=request.justification,
                proposed_adjustments=[],
                baseline_metrics={},
                expected_improvement=0.1,
                confidence=0.8,
                risk_score=0.3,
            )

            # Aplicar otimização
            optimization_event = None

            if request.optimization_type == "WEIGHT_RECALIBRATION":
                optimization_event = await self.weight_recalibrator.apply_weight_recalibration(hypothesis)
            elif request.optimization_type == "SLO_ADJUSTMENT":
                optimization_event = await self.slo_adjuster.apply_slo_adjustment(hypothesis)

            if not optimization_event:
                context.abort(grpc.StatusCode.INTERNAL, "Failed to apply optimization")

            # TODO: Return proper proto response when compiled
            # return optimizer_agent_pb2.TriggerOptimizationResponse(
            #     optimization_id=optimization_event.optimization_id,
            #     status="APPLIED",
            #     message="Optimization applied successfully"
            # )

            logger.info("optimization_triggered", optimization_id=optimization_event.optimization_id)

            # Placeholder return
            return {"optimization_id": optimization_event.optimization_id, "status": "APPLIED"}

        except Exception as e:
            logger.error("trigger_optimization_failed", error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to trigger optimization: {str(e)}")

    async def GetOptimizationStatus(self, request, context):
        """
        Obter status de uma otimização.

        Args:
            request: GetOptimizationStatusRequest
            context: gRPC context

        Returns:
            GetOptimizationStatusResponse
        """
        try:
            logger.info("get_optimization_status_requested", optimization_id=request.optimization_id)

            if not self.mongodb_client:
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            optimization = await self.mongodb_client.get_optimization(request.optimization_id)

            if not optimization:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Optimization {request.optimization_id} not found")

            # TODO: Return proper proto response when compiled
            # return optimizer_agent_pb2.GetOptimizationStatusResponse(
            #     optimization_id=optimization.get("optimization_id"),
            #     status=optimization.get("approval_status"),
            #     target_component=optimization.get("target_component"),
            #     improvement_percentage=optimization.get("improvement_percentage"),
            #     applied_at=optimization.get("applied_at")
            # )

            return optimization

        except Exception as e:
            logger.error("get_optimization_status_failed", error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to get optimization status: {str(e)}")

    async def ListOptimizations(self, request, context):
        """
        Listar otimizações.

        Args:
            request: ListOptimizationsRequest
            context: gRPC context

        Returns:
            ListOptimizationsResponse (stream)
        """
        try:
            logger.info("list_optimizations_requested", page_size=request.page_size)

            if not self.mongodb_client:
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            # Construir filtros
            filters = {}
            if request.target_component:
                filters["target_component"] = request.target_component
            if request.optimization_type:
                filters["optimization_type"] = request.optimization_type

            # Buscar otimizações
            optimizations = await self.mongodb_client.list_optimizations(
                filters=filters, skip=0, limit=request.page_size or 50
            )

            # TODO: Stream proto responses when compiled
            # for optimization in optimizations:
            #     yield optimizer_agent_pb2.OptimizationInfo(
            #         optimization_id=optimization.get("optimization_id"),
            #         ...
            #     )

            logger.info("optimizations_listed", count=len(optimizations))

            return {"optimizations": optimizations}

        except Exception as e:
            logger.error("list_optimizations_failed", error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to list optimizations: {str(e)}")

    async def RollbackOptimization(self, request, context):
        """
        Reverter otimização.

        Args:
            request: RollbackOptimizationRequest
            context: gRPC context

        Returns:
            RollbackOptimizationResponse
        """
        try:
            logger.info("rollback_optimization_requested", optimization_id=request.optimization_id)

            if not self.mongodb_client:
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            # Obter otimização
            optimization = await self.mongodb_client.get_optimization(request.optimization_id)

            if not optimization:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Optimization {request.optimization_id} not found")

            optimization_type = OptimizationType(optimization.get("optimization_type"))

            # Executar rollback
            success = False

            if optimization_type == OptimizationType.WEIGHT_RECALIBRATION:
                success = await self.weight_recalibrator.rollback_weight_recalibration(request.optimization_id)
            elif optimization_type == OptimizationType.SLO_ADJUSTMENT:
                success = await self.slo_adjuster.rollback_slo_adjustment(request.optimization_id)

            if not success:
                context.abort(grpc.StatusCode.INTERNAL, "Failed to rollback optimization")

            # TODO: Return proper proto response when compiled
            # return optimizer_agent_pb2.RollbackOptimizationResponse(
            #     success=True,
            #     message="Optimization rolled back successfully"
            # )

            logger.info("optimization_rolled_back", optimization_id=request.optimization_id)

            return {"success": True, "message": "Rolled back successfully"}

        except Exception as e:
            logger.error("rollback_optimization_failed", error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to rollback optimization: {str(e)}")

    async def GetStatistics(self, request, context):
        """
        Obter estatísticas de otimizações.

        Args:
            request: GetStatisticsRequest
            context: gRPC context

        Returns:
            GetStatisticsResponse
        """
        try:
            logger.info("get_statistics_requested")

            if not self.mongodb_client:
                context.abort(grpc.StatusCode.UNAVAILABLE, "MongoDB client not available")

            # Buscar todas otimizações
            all_optimizations = await self.mongodb_client.list_optimizations(filters={}, skip=0, limit=1000)

            total = len(all_optimizations)
            success_count = sum(1 for opt in all_optimizations if opt.get("approval_status") == "APPROVED")
            success_rate = success_count / total if total > 0 else 0.0

            improvements = [opt.get("improvement_percentage", 0) for opt in all_optimizations]
            average_improvement = sum(improvements) / len(improvements) if improvements else 0.0

            # TODO: Return proper proto response when compiled
            # return optimizer_agent_pb2.GetStatisticsResponse(
            #     total_optimizations=total,
            #     success_rate=success_rate,
            #     average_improvement=average_improvement
            # )

            logger.info("statistics_retrieved", total=total, success_rate=success_rate)

            return {"total_optimizations": total, "success_rate": success_rate, "average_improvement": average_improvement}

        except Exception as e:
            logger.error("get_statistics_failed", error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, f"Failed to get statistics: {str(e)}")

    async def HealthCheck(self, request, context):
        """
        Health check.

        Args:
            request: HealthCheckRequest
            context: gRPC context

        Returns:
            HealthCheckResponse
        """
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

            # TODO: Return proper proto response when compiled
            # return optimizer_agent_pb2.HealthCheckResponse(
            #     healthy=healthy,
            #     message=message
            # )

            return {"healthy": healthy, "message": message}

        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, f"Health check failed: {str(e)}")
