"""
Servicer gRPC para extensões de otimização de consenso.

Implementa os métodos RPC definidos em consensus_engine_extensions.proto.
Expõe APIs para que o Consensus Engine solicite otimizações de pesos.
"""
import time
from typing import Dict, Optional

import grpc
import structlog

from src.clients.clickhouse_client import ClickHouseClient
from src.clients.consensus_engine_grpc_client import ConsensusEngineGrpcClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.config.settings import get_settings
from src.models.optimization_event import OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.services.weight_recalibrator import WeightRecalibrator

logger = structlog.get_logger()

# Proto imports - disponíveis após `make proto` compilation
try:
    from proto import consensus_engine_extensions_pb2, consensus_engine_extensions_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    logger.warning("consensus_proto_not_compiled", message="Run 'make proto' to compile protocol buffers")


class ConsensusOptimizationServicer(
    consensus_engine_extensions_pb2_grpc.ConsensusOptimizationServicer if PROTO_AVAILABLE else object
):
    """
    Servicer gRPC para otimização de pesos de especialistas.

    Expõe endpoints para que o Consensus Engine solicite ajustes de pesos
    baseados em análise RL e métricas de performance.
    """

    def __init__(
        self,
        weight_recalibrator: Optional[WeightRecalibrator] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        redis_client: Optional[RedisClient] = None,
        clickhouse_client: Optional[ClickHouseClient] = None,
        consensus_client: Optional[ConsensusEngineGrpcClient] = None,
        scheduling_optimizer=None,
        settings=None,
        metrics=None,
    ):
        self.weight_recalibrator = weight_recalibrator
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.clickhouse_client = clickhouse_client
        self.consensus_client = consensus_client
        self.scheduling_optimizer = scheduling_optimizer
        self.settings = settings or get_settings()
        self.metrics = metrics

        # Cache keys
        self._weights_cache_key = "consensus:current_weights"

    async def GetCurrentWeights(self, request, context):
        """
        Obter pesos atuais dos especialistas.

        Args:
            request: GetCurrentWeightsRequest
            context: gRPC context

        Returns:
            GetCurrentWeightsResponse
        """
        try:
            specialist_type = request.specialist_type if request.HasField("specialist_type") else None

            logger.info("get_current_weights_requested", specialist_type=specialist_type)

            # Verificar cache Redis
            cached_weights = None
            if self.redis_client:
                try:
                    cached_weights = await self.redis_client.get_json(self._weights_cache_key)
                    if cached_weights and self.metrics:
                        self.metrics.increment_cache_hit("consensus_weights")
                except Exception as e:
                    logger.warning("redis_cache_error", error=str(e))

            weights = {}
            last_updated_at = 0
            optimization_id = ""

            if cached_weights:
                weights = cached_weights.get("weights", {})
                last_updated_at = cached_weights.get("last_updated_at", 0)
                optimization_id = cached_weights.get("optimization_id", "")
            elif self.mongodb_client:
                # Buscar do MongoDB
                if self.metrics:
                    self.metrics.increment_cache_miss("consensus_weights")

                weight_doc = await self.mongodb_client.find_one(
                    "consensus_weights",
                    {"active": True},
                    sort=[("last_updated_at", -1)]
                )

                if weight_doc:
                    weights = weight_doc.get("weights", {})
                    last_updated_at = weight_doc.get("last_updated_at", 0)
                    optimization_id = weight_doc.get("optimization_id", "")

                    # Atualizar cache
                    if self.redis_client:
                        try:
                            await self.redis_client.set_json(
                                self._weights_cache_key,
                                {"weights": weights, "last_updated_at": last_updated_at, "optimization_id": optimization_id},
                                ttl=self.settings.redis_cache_ttl
                            )
                        except Exception as e:
                            logger.warning("redis_cache_set_error", error=str(e))
                else:
                    # Pesos padrão se não houver registro
                    weights = {
                        "technical": 0.20,
                        "safety": 0.20,
                        "business": 0.20,
                        "ethical": 0.20,
                        "legal": 0.20,
                    }
                    last_updated_at = int(time.time() * 1000)
                    optimization_id = "default"

            # Filtrar por specialist_type se especificado
            if specialist_type and specialist_type in weights:
                weights = {specialist_type: weights[specialist_type]}

            logger.info("current_weights_retrieved", weights=weights, optimization_id=optimization_id)

            if PROTO_AVAILABLE:
                return consensus_engine_extensions_pb2.GetCurrentWeightsResponse(
                    weights=weights,
                    last_updated_at=last_updated_at,
                    optimization_id=optimization_id,
                )
            else:
                return {"weights": weights, "last_updated_at": last_updated_at, "optimization_id": optimization_id}

        except Exception as e:
            logger.error("get_current_weights_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter pesos atuais: {str(e)}")
            raise

    async def UpdateWeights(self, request, context):
        """
        Atualizar pesos dos especialistas.

        Args:
            request: UpdateWeightsRequest
            context: gRPC context

        Returns:
            UpdateWeightsResponse
        """
        try:
            weights = dict(request.weights)
            justification = request.justification
            optimization_id = request.optimization_id
            validate_before_apply = request.validate_before_apply
            metadata = dict(request.metadata) if request.metadata else {}

            logger.info(
                "update_weights_requested",
                optimization_id=optimization_id,
                weights=weights,
                validate_before_apply=validate_before_apply,
            )

            # Validar se solicitado
            if validate_before_apply:
                validation_result = await self._validate_weights(weights)
                if not validation_result.get("is_valid"):
                    logger.warning(
                        "weight_validation_failed",
                        errors=validation_result.get("errors"),
                    )
                    if PROTO_AVAILABLE:
                        return consensus_engine_extensions_pb2.UpdateWeightsResponse(
                            success=False,
                            message=validation_result.get("message", "Validação falhou"),
                            previous_weights={},
                            applied_weights={},
                            applied_at=0,
                        )
                    else:
                        return {"success": False, "message": validation_result.get("message")}

            # Obter pesos anteriores
            previous_weights = {}
            if self.mongodb_client:
                prev_doc = await self.mongodb_client.find_one(
                    "consensus_weights",
                    {"active": True},
                    sort=[("last_updated_at", -1)]
                )
                if prev_doc:
                    previous_weights = prev_doc.get("weights", {})

            # Consultar RL Q-table para confidence (se disponível)
            rl_confidence = 0.8
            if self.scheduling_optimizer:
                try:
                    # Usar estado atual para obter Q-value
                    current_state = self._get_current_state()
                    q_values = self.scheduling_optimizer.get_q_values(current_state)
                    if q_values:
                        max_q = max(q_values.values()) if q_values else 0
                        rl_confidence = min(1.0, 0.5 + max_q * 0.5)
                except Exception as e:
                    logger.warning("rl_q_value_query_failed", error=str(e))

            # Criar hipótese de otimização
            hypothesis = OptimizationHypothesis(
                hypothesis_id=optimization_id,
                optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
                target_component="consensus-engine",
                hypothesis_text=justification,
                rationale=justification,
                proposed_adjustments=[
                    {"parameter": k, "new_value": v - previous_weights.get(k, 0.2)}
                    for k, v in weights.items()
                ],
                baseline_metrics={"previous_weights": previous_weights},
                expected_improvement=0.1,
                confidence=rl_confidence,
                risk_score=0.2,
            )

            # Aplicar pesos via WeightRecalibrator ou ConsensusEngineGrpcClient ANTES de persistir
            apply_success = False
            apply_error_message = None

            if self.weight_recalibrator:
                # Aplicar via WeightRecalibrator
                try:
                    result = await self.weight_recalibrator.apply_weight_recalibration(hypothesis)
                    if result:
                        apply_success = True
                        logger.info(
                            "weight_recalibration_applied_via_recalibrator",
                            optimization_id=optimization_id,
                        )
                    else:
                        apply_error_message = "WeightRecalibrator failed to apply weight recalibration"
                        logger.error(
                            "weight_recalibration_via_recalibrator_failed",
                            optimization_id=optimization_id,
                        )
                except Exception as e:
                    apply_error_message = f"WeightRecalibrator error: {str(e)}"
                    logger.error(
                        "weight_recalibration_via_recalibrator_error",
                        optimization_id=optimization_id,
                        error=str(e),
                    )
            elif self.consensus_client:
                # Fallback: aplicar via ConsensusEngineGrpcClient
                try:
                    apply_success = await self.consensus_client.update_weights(
                        weights=weights,
                        justification=justification,
                        optimization_id=optimization_id,
                    )
                    if apply_success:
                        logger.info(
                            "weight_recalibration_applied_via_consensus_client",
                            optimization_id=optimization_id,
                        )
                    else:
                        apply_error_message = "ConsensusEngineGrpcClient failed to apply weight update"
                        logger.error(
                            "weight_recalibration_via_consensus_client_failed",
                            optimization_id=optimization_id,
                        )
                except Exception as e:
                    apply_error_message = f"ConsensusEngineGrpcClient error: {str(e)}"
                    logger.error(
                        "weight_recalibration_via_consensus_client_error",
                        optimization_id=optimization_id,
                        error=str(e),
                    )
            else:
                apply_error_message = "Neither WeightRecalibrator nor ConsensusEngineGrpcClient available"
                logger.error(
                    "no_weight_application_mechanism_available",
                    optimization_id=optimization_id,
                )

            # Se a aplicação falhou, retornar erro sem persistir
            if not apply_success:
                logger.error(
                    "weight_update_application_failed",
                    optimization_id=optimization_id,
                    error=apply_error_message,
                )

                if self.metrics:
                    self.metrics.increment_counter(
                        "consensus_weight_updates_total",
                        {"specialist_type": "all", "status": "application_failed"}
                    )

                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Falha ao aplicar pesos: {apply_error_message}")

                if PROTO_AVAILABLE:
                    return consensus_engine_extensions_pb2.UpdateWeightsResponse(
                        success=False,
                        message=f"Falha ao aplicar pesos: {apply_error_message}",
                        previous_weights={},
                        applied_weights={},
                        applied_at=0,
                    )
                else:
                    return {"success": False, "message": f"Falha ao aplicar pesos: {apply_error_message}"}

            applied_at = int(time.time() * 1000)

            # Persistir no MongoDB apenas após aplicação bem-sucedida
            if self.mongodb_client:
                # Desativar pesos anteriores
                await self.mongodb_client.update_many(
                    "consensus_weights",
                    {"active": True},
                    {"$set": {"active": False}}
                )

                # Inserir novos pesos
                await self.mongodb_client.insert_one(
                    "consensus_weights",
                    {
                        "optimization_id": optimization_id,
                        "weights": weights,
                        "previous_weights": previous_weights,
                        "justification": justification,
                        "metadata": metadata,
                        "rl_confidence": rl_confidence,
                        "last_updated_at": applied_at,
                        "active": True,
                    }
                )

                # Registrar no histórico
                await self.mongodb_client.insert_one(
                    "weight_adjustments",
                    {
                        "optimization_id": optimization_id,
                        "adjusted_at": applied_at,
                        "weights_before": previous_weights,
                        "weights_after": weights,
                        "justification": justification,
                        "rl_confidence": rl_confidence,
                        "was_rolled_back": False,
                    }
                )

            # Atualizar cache após aplicação e persistência bem-sucedidas
            if self.redis_client:
                try:
                    await self.redis_client.set_json(
                        self._weights_cache_key,
                        {"weights": weights, "last_updated_at": applied_at, "optimization_id": optimization_id},
                        ttl=self.settings.redis_cache_ttl
                    )
                except Exception as e:
                    logger.warning("redis_cache_update_error", error=str(e))

            # Registrar reward no RL
            if self.scheduling_optimizer:
                try:
                    # Reward positivo por aplicação bem-sucedida
                    reward = 0.5 + rl_confidence * 0.5
                    self.scheduling_optimizer.record_reward(reward)
                    if self.metrics:
                        self.metrics.observe_histogram("rl_reward_distribution", reward)
                except Exception as e:
                    logger.warning("rl_reward_record_failed", error=str(e))

            # Métricas
            if self.metrics:
                self.metrics.increment_counter(
                    "consensus_weight_updates_total",
                    {"specialist_type": "all", "status": "success"}
                )

            logger.info(
                "weights_updated_successfully",
                optimization_id=optimization_id,
                previous_weights=previous_weights,
                applied_weights=weights,
            )

            if PROTO_AVAILABLE:
                return consensus_engine_extensions_pb2.UpdateWeightsResponse(
                    success=True,
                    message="Pesos atualizados com sucesso",
                    previous_weights=previous_weights,
                    applied_weights=weights,
                    applied_at=applied_at,
                )
            else:
                return {
                    "success": True,
                    "message": "Pesos atualizados com sucesso",
                    "previous_weights": previous_weights,
                    "applied_weights": weights,
                    "applied_at": applied_at,
                }

        except Exception as e:
            logger.error("update_weights_failed", optimization_id=request.optimization_id, error=str(e))

            if self.metrics:
                self.metrics.increment_counter(
                    "consensus_weight_updates_total",
                    {"specialist_type": "all", "status": "error"}
                )

            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao atualizar pesos: {str(e)}")
            raise

    async def ValidateWeightAdjustment(self, request, context):
        """
        Validar ajuste de pesos antes de aplicar.

        Args:
            request: ValidateWeightAdjustmentRequest
            context: gRPC context

        Returns:
            ValidateWeightAdjustmentResponse
        """
        try:
            proposed_weights = dict(request.proposed_weights)

            logger.info("validate_weight_adjustment_requested", proposed_weights=proposed_weights)

            result = await self._validate_weights(proposed_weights)

            if PROTO_AVAILABLE:
                errors = []
                for error in result.get("errors", []):
                    errors.append(consensus_engine_extensions_pb2.ValidationError(
                        field=error.get("field", ""),
                        description=error.get("description", ""),
                        current_value=str(error.get("current_value", "")),
                        expected_value=str(error.get("expected_value", "")),
                    ))

                return consensus_engine_extensions_pb2.ValidateWeightAdjustmentResponse(
                    is_valid=result.get("is_valid", False),
                    message=result.get("message", ""),
                    errors=errors,
                    warnings=result.get("warnings", []),
                )
            else:
                return result

        except Exception as e:
            logger.error("validate_weight_adjustment_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha na validação: {str(e)}")
            raise

    async def RollbackWeights(self, request, context):
        """
        Reverter pesos para versão anterior.

        Args:
            request: RollbackWeightsRequest
            context: gRPC context

        Returns:
            RollbackWeightsResponse
        """
        try:
            optimization_id = request.optimization_id
            force = request.force

            logger.info("rollback_weights_requested", optimization_id=optimization_id, force=force)

            if not self.mongodb_client:
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details("MongoDB client não disponível")
                raise Exception("MongoDB não disponível")

            # Buscar ajuste original
            adjustment = await self.mongodb_client.find_one(
                "weight_adjustments",
                {"optimization_id": optimization_id}
            )

            if not adjustment:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Otimização {optimization_id} não encontrada")
                raise Exception(f"Otimização {optimization_id} não encontrada")

            if adjustment.get("was_rolled_back") and not force:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("Esta otimização já foi revertida")
                raise Exception("Otimização já foi revertida")

            weights_before = adjustment.get("weights_before", {})
            rolled_back_at = int(time.time() * 1000)

            # Restaurar pesos anteriores
            await self.mongodb_client.update_many(
                "consensus_weights",
                {"active": True},
                {"$set": {"active": False}}
            )

            await self.mongodb_client.insert_one(
                "consensus_weights",
                {
                    "optimization_id": f"rollback-{optimization_id}",
                    "weights": weights_before,
                    "previous_weights": adjustment.get("weights_after", {}),
                    "justification": f"Rollback da otimização {optimization_id}",
                    "last_updated_at": rolled_back_at,
                    "active": True,
                    "is_rollback": True,
                    "original_optimization_id": optimization_id,
                }
            )

            # Marcar ajuste como revertido
            await self.mongodb_client.update_one(
                "weight_adjustments",
                {"optimization_id": optimization_id},
                {"$set": {"was_rolled_back": True, "rolled_back_at": rolled_back_at}}
            )

            # Invalidar cache
            if self.redis_client:
                try:
                    await self.redis_client.delete(self._weights_cache_key)
                except Exception as e:
                    logger.warning("redis_cache_invalidation_error", error=str(e))

            # Métricas
            if self.metrics:
                self.metrics.increment_counter(
                    "consensus_weight_rollbacks_total",
                    {"optimization_id": optimization_id}
                )

            logger.info(
                "weights_rolled_back",
                optimization_id=optimization_id,
                restored_weights=weights_before,
            )

            if PROTO_AVAILABLE:
                return consensus_engine_extensions_pb2.RollbackWeightsResponse(
                    success=True,
                    message="Pesos revertidos com sucesso",
                    restored_weights=weights_before,
                    rolled_back_at=rolled_back_at,
                )
            else:
                return {
                    "success": True,
                    "message": "Pesos revertidos com sucesso",
                    "restored_weights": weights_before,
                    "rolled_back_at": rolled_back_at,
                }

        except Exception as e:
            logger.error("rollback_weights_failed", optimization_id=request.optimization_id, error=str(e))
            if not context.code():
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Falha no rollback: {str(e)}")
            raise

    async def GetConsensusMetrics(self, request, context):
        """
        Obter métricas de consenso.

        Args:
            request: GetConsensusMetricsRequest
            context: gRPC context

        Returns:
            GetConsensusMetricsResponse
        """
        try:
            time_range = request.time_range or "1h"

            logger.info("get_consensus_metrics_requested", time_range=time_range)

            # Converter time_range para segundos
            time_seconds = self._parse_time_range(time_range)

            # Métricas padrão
            average_divergence = 0.12
            average_confidence = 0.85
            average_risk = 0.15
            specialist_accuracy = {}
            total_decisions = 0
            specialist_metrics = {}

            # Buscar métricas do ClickHouse se disponível
            if self.clickhouse_client:
                try:
                    metrics_data = await self.clickhouse_client.query(
                        f"""
                        SELECT
                            avg(divergence) as avg_divergence,
                            avg(confidence) as avg_confidence,
                            avg(risk_score) as avg_risk,
                            count() as total_decisions,
                            specialist_type,
                            avg(accuracy) as accuracy,
                            avg(confidence) as specialist_confidence,
                            count() as contributions
                        FROM consensus_decisions
                        WHERE timestamp >= now() - INTERVAL {time_seconds} SECOND
                        GROUP BY specialist_type
                        """
                    )

                    if metrics_data:
                        for row in metrics_data:
                            specialist_type = row.get("specialist_type", "unknown")
                            specialist_accuracy[specialist_type] = row.get("accuracy", 0.85)
                            specialist_metrics[specialist_type] = {
                                "specialist_type": specialist_type,
                                "accuracy": row.get("accuracy", 0.85),
                                "average_confidence": row.get("specialist_confidence", 0.85),
                                "total_contributions": row.get("contributions", 0),
                            }

                        # Usar primeira linha para métricas agregadas
                        if metrics_data:
                            first_row = metrics_data[0]
                            average_divergence = first_row.get("avg_divergence", 0.12)
                            average_confidence = first_row.get("avg_confidence", 0.85)
                            average_risk = first_row.get("avg_risk", 0.15)
                            total_decisions = sum(r.get("contributions", 0) for r in metrics_data)

                except Exception as e:
                    logger.warning("clickhouse_metrics_query_failed", error=str(e))

            # Adicionar pesos atuais às métricas de especialistas
            if self.mongodb_client:
                weight_doc = await self.mongodb_client.find_one(
                    "consensus_weights",
                    {"active": True},
                    sort=[("last_updated_at", -1)]
                )
                if weight_doc:
                    current_weights = weight_doc.get("weights", {})
                    for specialist_type, weight in current_weights.items():
                        if specialist_type not in specialist_metrics:
                            specialist_metrics[specialist_type] = {
                                "specialist_type": specialist_type,
                                "accuracy": 0.85,
                                "average_confidence": 0.85,
                                "total_contributions": 0,
                            }
                        specialist_metrics[specialist_type]["current_weight"] = weight

            logger.info(
                "consensus_metrics_retrieved",
                time_range=time_range,
                total_decisions=total_decisions,
            )

            if PROTO_AVAILABLE:
                specialist_metrics_proto = {}
                for k, v in specialist_metrics.items():
                    specialist_metrics_proto[k] = consensus_engine_extensions_pb2.SpecialistMetrics(
                        specialist_type=v.get("specialist_type", k),
                        current_weight=v.get("current_weight", 0.2),
                        accuracy=v.get("accuracy", 0.85),
                        average_confidence=v.get("average_confidence", 0.85),
                        total_contributions=v.get("total_contributions", 0),
                        consensus_agreement_rate=v.get("consensus_agreement_rate", 0.9),
                    )

                return consensus_engine_extensions_pb2.GetConsensusMetricsResponse(
                    average_divergence=average_divergence,
                    average_confidence=average_confidence,
                    average_risk=average_risk,
                    specialist_accuracy=specialist_accuracy,
                    total_decisions=total_decisions,
                    specialist_metrics=specialist_metrics_proto,
                )
            else:
                return {
                    "average_divergence": average_divergence,
                    "average_confidence": average_confidence,
                    "average_risk": average_risk,
                    "specialist_accuracy": specialist_accuracy,
                    "total_decisions": total_decisions,
                    "specialist_metrics": specialist_metrics,
                }

        except Exception as e:
            logger.error("get_consensus_metrics_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter métricas: {str(e)}")
            raise

    async def GetWeightHistory(self, request, context):
        """
        Obter histórico de ajustes de peso.

        Args:
            request: GetWeightHistoryRequest
            context: gRPC context

        Returns:
            GetWeightHistoryResponse
        """
        try:
            specialist_type = request.specialist_type if request.HasField("specialist_type") else None
            limit = request.limit or 50
            offset = request.offset or 0

            logger.info(
                "get_weight_history_requested",
                specialist_type=specialist_type,
                limit=limit,
                offset=offset,
            )

            adjustments = []
            total = 0

            if self.mongodb_client:
                # Construir filtro
                query = {}
                if specialist_type:
                    query[f"weights_after.{specialist_type}"] = {"$exists": True}

                # Contar total
                total = await self.mongodb_client.count("weight_adjustments", query)

                # Buscar com paginação
                cursor = await self.mongodb_client.find(
                    "weight_adjustments",
                    query,
                    sort=[("adjusted_at", -1)],
                    skip=offset,
                    limit=limit,
                )

                async for doc in cursor:
                    adjustments.append({
                        "optimization_id": doc.get("optimization_id", ""),
                        "adjusted_at": doc.get("adjusted_at", 0),
                        "weights_before": doc.get("weights_before", {}),
                        "weights_after": doc.get("weights_after", {}),
                        "justification": doc.get("justification", ""),
                        "improvement": doc.get("improvement"),
                        "was_rolled_back": doc.get("was_rolled_back", False),
                    })

            logger.info("weight_history_retrieved", count=len(adjustments), total=total)

            if PROTO_AVAILABLE:
                adjustment_protos = []
                for adj in adjustments:
                    adjustment_proto = consensus_engine_extensions_pb2.WeightAdjustment(
                        optimization_id=adj["optimization_id"],
                        adjusted_at=adj["adjusted_at"],
                        weights_before=adj["weights_before"],
                        weights_after=adj["weights_after"],
                        justification=adj["justification"],
                        was_rolled_back=adj["was_rolled_back"],
                    )
                    if adj.get("improvement") is not None:
                        adjustment_proto.improvement = adj["improvement"]
                    adjustment_protos.append(adjustment_proto)

                return consensus_engine_extensions_pb2.GetWeightHistoryResponse(
                    adjustments=adjustment_protos,
                    total=total,
                )
            else:
                return {"adjustments": adjustments, "total": total}

        except Exception as e:
            logger.error("get_weight_history_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter histórico: {str(e)}")
            raise

    async def _validate_weights(self, proposed_weights: Dict[str, float]) -> Dict:
        """
        Validar pesos propostos.

        Args:
            proposed_weights: Pesos propostos

        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []

        # Verificar se somam 1.0 (±0.01 tolerância)
        total = sum(proposed_weights.values())
        if not (0.99 <= total <= 1.01):
            errors.append({
                "field": "weights_total",
                "description": "Soma dos pesos deve ser 1.0",
                "current_value": str(round(total, 4)),
                "expected_value": "1.0 (±0.01)",
            })

        # Verificar range individual [0, 1]
        for specialist, weight in proposed_weights.items():
            if weight < 0 or weight > 1:
                errors.append({
                    "field": specialist,
                    "description": "Peso deve estar entre 0 e 1",
                    "current_value": str(weight),
                    "expected_value": "0.0 - 1.0",
                })

            # Warning se peso muito baixo ou muito alto
            if weight < 0.05:
                warnings.append(f"Peso de {specialist} muito baixo ({weight}), pode prejudicar consenso")
            elif weight > 0.5:
                warnings.append(f"Peso de {specialist} muito alto ({weight}), pode dominar consenso")

        # Verificar delta máximo (se tivermos pesos anteriores)
        if self.mongodb_client:
            prev_doc = await self.mongodb_client.find_one(
                "consensus_weights",
                {"active": True},
                sort=[("last_updated_at", -1)]
            )
            if prev_doc:
                previous_weights = prev_doc.get("weights", {})
                max_delta = self.settings.max_weight_adjustment

                for specialist, new_weight in proposed_weights.items():
                    old_weight = previous_weights.get(specialist, 0.2)
                    delta = abs(new_weight - old_weight)

                    if delta > max_delta:
                        errors.append({
                            "field": specialist,
                            "description": f"Delta de ajuste excede máximo permitido ({max_delta})",
                            "current_value": str(round(delta, 4)),
                            "expected_value": f"<= {max_delta}",
                        })

        is_valid = len(errors) == 0
        message = "Validação bem-sucedida" if is_valid else f"{len(errors)} erro(s) encontrado(s)"

        return {
            "is_valid": is_valid,
            "message": message,
            "errors": errors,
            "warnings": warnings,
        }

    def _parse_time_range(self, time_range: str) -> int:
        """
        Converter string de intervalo de tempo para segundos.

        Args:
            time_range: String como "1h", "24h", "7d"

        Returns:
            Intervalo em segundos
        """
        try:
            if time_range.endswith("h"):
                return int(time_range[:-1]) * 3600
            elif time_range.endswith("d"):
                return int(time_range[:-1]) * 86400
            elif time_range.endswith("m"):
                return int(time_range[:-1]) * 60
            else:
                return int(time_range)
        except ValueError:
            return 3600  # Default: 1 hora

    def _get_current_state(self) -> str:
        """
        Obter estado atual para consulta de Q-values.

        Returns:
            String representando estado atual
        """
        # Estado simplificado para RL
        return "consensus_optimization"
