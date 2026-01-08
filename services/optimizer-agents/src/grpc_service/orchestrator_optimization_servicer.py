"""
Servicer gRPC para extensões de otimização de SLOs.

Implementa os métodos RPC definidos em orchestrator_extensions.proto.
Expõe APIs para que o Orchestrator Dynamic solicite otimizações de SLOs.
"""
import time
from typing import Dict, Optional

import grpc
import structlog

from src.clients.clickhouse_client import ClickHouseClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.orchestrator_grpc_client import OrchestratorGrpcClient
from src.clients.redis_client import RedisClient
from src.config.settings import get_settings
from src.models.optimization_event import OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.services.slo_adjuster import SLOAdjuster

logger = structlog.get_logger()

# Proto imports - disponíveis após `make proto` compilation
try:
    from proto import orchestrator_extensions_pb2, orchestrator_extensions_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    logger.warning("orchestrator_proto_not_compiled", message="Run 'make proto' to compile protocol buffers")


class OrchestratorOptimizationServicer(
    orchestrator_extensions_pb2_grpc.OrchestratorOptimizationServicer if PROTO_AVAILABLE else object
):
    """
    Servicer gRPC para otimização de SLOs.

    Expõe endpoints para que o Orchestrator Dynamic solicite ajustes de SLOs
    baseados em análise RL e métricas de compliance.
    """

    def __init__(
        self,
        slo_adjuster: Optional[SLOAdjuster] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        redis_client: Optional[RedisClient] = None,
        clickhouse_client: Optional[ClickHouseClient] = None,
        orchestrator_client: Optional[OrchestratorGrpcClient] = None,
        load_predictor=None,
        scheduling_optimizer=None,
        settings=None,
        metrics=None,
    ):
        self.slo_adjuster = slo_adjuster
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.clickhouse_client = clickhouse_client
        self.orchestrator_client = orchestrator_client
        self.load_predictor = load_predictor
        self.scheduling_optimizer = scheduling_optimizer
        self.settings = settings or get_settings()
        self.metrics = metrics

        # Cache keys
        self._slo_cache_prefix = "orchestrator:slo:"

    async def GetCurrentSLOs(self, request, context):
        """
        Obter SLOs atuais.

        Args:
            request: GetCurrentSLOsRequest
            context: gRPC context

        Returns:
            GetCurrentSLOsResponse
        """
        try:
            service = request.service if request.HasField("service") else None

            logger.info("get_current_slos_requested", service=service)

            # Verificar cache Redis
            cache_key = f"{self._slo_cache_prefix}{service or 'all'}"
            cached_slos = None

            if self.redis_client:
                try:
                    cached_slos = await self.redis_client.get_json(cache_key)
                    if cached_slos and self.metrics:
                        self.metrics.increment_cache_hit("orchestrator_slos")
                except Exception as e:
                    logger.warning("redis_cache_error", error=str(e))

            slos = {}
            last_updated_at = 0

            if cached_slos:
                slos = cached_slos.get("slos", {})
                last_updated_at = cached_slos.get("last_updated_at", 0)
            elif self.mongodb_client:
                # Buscar do MongoDB
                if self.metrics:
                    self.metrics.increment_cache_miss("orchestrator_slos")

                query = {"active": True}
                if service:
                    query["service"] = service

                cursor = await self.mongodb_client.find(
                    "slo_configs",
                    query,
                    sort=[("last_updated_at", -1)]
                )

                async for doc in cursor:
                    svc = doc.get("service")
                    slos[svc] = {
                        "target_latency_ms": doc.get("target_latency_ms", 1000),
                        "target_availability": doc.get("target_availability", 0.999),
                        "target_error_rate": doc.get("target_error_rate", 0.01),
                        "min_throughput": doc.get("min_throughput"),
                        "latency_percentile": doc.get("latency_percentile", 0.95),
                        "time_window_seconds": doc.get("time_window_seconds", 60),
                        "metadata": doc.get("metadata", {}),
                    }
                    if doc.get("last_updated_at", 0) > last_updated_at:
                        last_updated_at = doc.get("last_updated_at", 0)

                # Atualizar cache
                if self.redis_client and slos:
                    try:
                        await self.redis_client.set_json(
                            cache_key,
                            {"slos": slos, "last_updated_at": last_updated_at},
                            ttl=self.settings.redis_cache_ttl
                        )
                    except Exception as e:
                        logger.warning("redis_cache_set_error", error=str(e))

            # SLOs padrão se não houver registros
            if not slos:
                slos = {
                    "consensus-engine": {
                        "target_latency_ms": 1000,
                        "target_availability": 0.999,
                        "target_error_rate": 0.01,
                        "latency_percentile": 0.95,
                        "time_window_seconds": 60,
                        "metadata": {},
                    },
                    "orchestrator-dynamic": {
                        "target_latency_ms": 2000,
                        "target_availability": 0.995,
                        "target_error_rate": 0.02,
                        "latency_percentile": 0.95,
                        "time_window_seconds": 60,
                        "metadata": {},
                    },
                }
                last_updated_at = int(time.time() * 1000)

            logger.info("current_slos_retrieved", services=list(slos.keys()))

            if PROTO_AVAILABLE:
                slo_configs = {}
                for svc, config in slos.items():
                    slo_config = orchestrator_extensions_pb2.SLOConfig(
                        target_latency_ms=config.get("target_latency_ms", 1000),
                        target_availability=config.get("target_availability", 0.999),
                        target_error_rate=config.get("target_error_rate", 0.01),
                        latency_percentile=config.get("latency_percentile", 0.95),
                        time_window_seconds=config.get("time_window_seconds", 60),
                    )
                    if config.get("min_throughput"):
                        slo_config.min_throughput = config["min_throughput"]
                    if config.get("metadata"):
                        slo_config.metadata.update(config["metadata"])
                    slo_configs[svc] = slo_config

                return orchestrator_extensions_pb2.GetCurrentSLOsResponse(
                    slos=slo_configs,
                    last_updated_at=last_updated_at,
                )
            else:
                return {"slos": slos, "last_updated_at": last_updated_at}

        except Exception as e:
            logger.error("get_current_slos_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter SLOs atuais: {str(e)}")
            raise

    async def UpdateSLOs(self, request, context):
        """
        Atualizar SLOs.

        Args:
            request: UpdateSLOsRequest
            context: gRPC context

        Returns:
            UpdateSLOsResponse
        """
        try:
            slo_updates = {}
            for service, slo_config in request.slo_updates.items():
                slo_updates[service] = {
                    "target_latency_ms": slo_config.target_latency_ms,
                    "target_availability": slo_config.target_availability,
                    "target_error_rate": slo_config.target_error_rate,
                    "latency_percentile": slo_config.latency_percentile,
                    "time_window_seconds": slo_config.time_window_seconds,
                }
                if slo_config.HasField("min_throughput"):
                    slo_updates[service]["min_throughput"] = slo_config.min_throughput
                if slo_config.metadata:
                    slo_updates[service]["metadata"] = dict(slo_config.metadata)

            justification = request.justification
            optimization_id = request.optimization_id
            validate_before_apply = request.validate_before_apply
            gradual_rollout = request.gradual_rollout_percentage if request.HasField("gradual_rollout_percentage") else None

            logger.info(
                "update_slos_requested",
                optimization_id=optimization_id,
                services=list(slo_updates.keys()),
                validate_before_apply=validate_before_apply,
                gradual_rollout=gradual_rollout,
            )

            # Validar se solicitado
            if validate_before_apply:
                validation_result = await self._validate_slos(slo_updates, check_error_budget=True)
                if not validation_result.get("is_valid"):
                    logger.warning(
                        "slo_validation_failed",
                        errors=validation_result.get("errors"),
                    )
                    if PROTO_AVAILABLE:
                        return orchestrator_extensions_pb2.UpdateSLOsResponse(
                            success=False,
                            message=validation_result.get("message", "Validação falhou"),
                            previous_slos={},
                            applied_slos={},
                            applied_at=0,
                            is_gradual_rollout=False,
                        )
                    else:
                        return {"success": False, "message": validation_result.get("message")}

            # Obter SLOs anteriores
            previous_slos = {}
            if self.mongodb_client:
                for service in slo_updates.keys():
                    prev_doc = await self.mongodb_client.find_one(
                        "slo_configs",
                        {"service": service, "active": True},
                        sort=[("last_updated_at", -1)]
                    )
                    if prev_doc:
                        previous_slos[service] = {
                            "target_latency_ms": prev_doc.get("target_latency_ms", 1000),
                            "target_availability": prev_doc.get("target_availability", 0.999),
                            "target_error_rate": prev_doc.get("target_error_rate", 0.01),
                            "latency_percentile": prev_doc.get("latency_percentile", 0.95),
                            "time_window_seconds": prev_doc.get("time_window_seconds", 60),
                        }

            # Prever carga futura com load_predictor
            load_forecast = None
            expected_improvement = 0.1
            if self.load_predictor:
                try:
                    load_forecast = await self.load_predictor.predict_load(
                        horizon_minutes=60,
                        include_confidence_intervals=True
                    )
                    # Ajustar expected_improvement baseado na previsão
                    if load_forecast:
                        forecast_data = load_forecast.get("forecast", [])
                        if forecast_data:
                            avg_load = sum(p.get("predicted_load", 0) for p in forecast_data) / len(forecast_data)
                            expected_improvement = min(0.3, 0.05 + avg_load * 0.001)
                except Exception as e:
                    logger.warning("load_forecast_for_slo_failed", error=str(e))

            # Consultar RL para recomendação
            rl_confidence = 0.8
            if self.scheduling_optimizer:
                try:
                    current_state = self._get_current_state(slo_updates)
                    q_values = self.scheduling_optimizer.get_q_values(current_state)
                    if q_values:
                        max_q = max(q_values.values()) if q_values else 0
                        rl_confidence = min(1.0, 0.5 + max_q * 0.5)
                except Exception as e:
                    logger.warning("rl_q_value_query_failed", error=str(e))

            # Aplicar SLOs via SLOAdjuster ou OrchestratorClient ANTES de persistir
            apply_success = False
            apply_error_message = None

            if self.slo_adjuster:
                # Criar hipótese de otimização para aplicação via SLOAdjuster
                for service, slo_config in slo_updates.items():
                    hypothesis = OptimizationHypothesis(
                        hypothesis_id=optimization_id,
                        optimization_type=OptimizationType.SLO_ADJUSTMENT,
                        target_component=service,
                        hypothesis_text=justification,
                        rationale=justification,
                        proposed_adjustments=[
                            {"parameter": k, "new_value": v}
                            for k, v in slo_config.items()
                            if k in ["target_latency_ms", "target_availability", "target_error_rate"]
                        ],
                        baseline_metrics=previous_slos.get(service, {}),
                        expected_improvement=expected_improvement,
                        confidence=rl_confidence,
                        risk_score=0.2,
                    )

                    try:
                        result = await self.slo_adjuster.apply_slo_adjustment(hypothesis)
                        if result:
                            apply_success = True
                            logger.info(
                                "slo_adjustment_applied_via_adjuster",
                                optimization_id=optimization_id,
                                service=service,
                            )
                        else:
                            apply_error_message = f"SLOAdjuster failed to apply adjustment for {service}"
                            logger.error(
                                "slo_adjustment_via_adjuster_failed",
                                optimization_id=optimization_id,
                                service=service,
                            )
                    except Exception as e:
                        apply_error_message = f"SLOAdjuster error for {service}: {str(e)}"
                        logger.error(
                            "slo_adjustment_via_adjuster_error",
                            optimization_id=optimization_id,
                            service=service,
                            error=str(e),
                        )
            elif self.orchestrator_client:
                # Fallback: aplicar via OrchestratorGrpcClient
                try:
                    apply_success = await self.orchestrator_client.update_slos(
                        slo_updates=slo_updates,
                        justification=justification,
                        optimization_id=optimization_id,
                    )
                    if apply_success:
                        logger.info(
                            "slo_adjustment_applied_via_orchestrator_client",
                            optimization_id=optimization_id,
                            services=list(slo_updates.keys()),
                        )
                    else:
                        apply_error_message = "OrchestratorClient failed to apply SLO update"
                        logger.error(
                            "slo_adjustment_via_orchestrator_client_failed",
                            optimization_id=optimization_id,
                        )
                except Exception as e:
                    apply_error_message = f"OrchestratorClient error: {str(e)}"
                    logger.error(
                        "slo_adjustment_via_orchestrator_client_error",
                        optimization_id=optimization_id,
                        error=str(e),
                    )
            else:
                apply_error_message = "Neither SLOAdjuster nor OrchestratorClient available"
                logger.error(
                    "no_slo_application_mechanism_available",
                    optimization_id=optimization_id,
                )

            # Se a aplicação falhou, retornar erro sem persistir
            if not apply_success:
                logger.error(
                    "slo_update_application_failed",
                    optimization_id=optimization_id,
                    error=apply_error_message,
                )

                if self.metrics:
                    self.metrics.increment_counter(
                        "orchestrator_slo_updates_total",
                        {"service": "all", "status": "application_failed"}
                    )

                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Falha ao aplicar SLOs: {apply_error_message}")

                if PROTO_AVAILABLE:
                    return orchestrator_extensions_pb2.UpdateSLOsResponse(
                        success=False,
                        message=f"Falha ao aplicar SLOs: {apply_error_message}",
                        previous_slos={},
                        applied_slos={},
                        applied_at=0,
                        is_gradual_rollout=False,
                    )
                else:
                    return {"success": False, "message": f"Falha ao aplicar SLOs: {apply_error_message}"}

            applied_at = int(time.time() * 1000)
            is_gradual = gradual_rollout is not None and gradual_rollout < 100

            # Persistir no MongoDB apenas após aplicação bem-sucedida
            if self.mongodb_client:
                for service, slo_config in slo_updates.items():
                    # Desativar SLOs anteriores
                    await self.mongodb_client.update_many(
                        "slo_configs",
                        {"service": service, "active": True},
                        {"$set": {"active": False}}
                    )

                    # Inserir novos SLOs
                    await self.mongodb_client.insert_one(
                        "slo_configs",
                        {
                            "service": service,
                            "optimization_id": optimization_id,
                            **slo_config,
                            "justification": justification,
                            "rl_confidence": rl_confidence,
                            "expected_improvement": expected_improvement,
                            "is_gradual_rollout": is_gradual,
                            "gradual_rollout_percentage": gradual_rollout,
                            "last_updated_at": applied_at,
                            "active": True,
                        }
                    )

                    # Registrar no histórico
                    await self.mongodb_client.insert_one(
                        "slo_adjustments",
                        {
                            "optimization_id": optimization_id,
                            "service": service,
                            "adjusted_at": applied_at,
                            "slo_before": previous_slos.get(service, {}),
                            "slo_after": slo_config,
                            "justification": justification,
                            "rl_confidence": rl_confidence,
                            "load_forecast": load_forecast,
                            "was_rolled_back": False,
                        }
                    )

            # Atualizar cache após aplicação e persistência bem-sucedidas
            if self.redis_client:
                try:
                    # Invalidar caches de cada serviço e o cache geral
                    await self.redis_client.delete(f"{self._slo_cache_prefix}all")
                    for service in slo_updates.keys():
                        await self.redis_client.delete(f"{self._slo_cache_prefix}{service}")
                except Exception as e:
                    logger.warning("redis_cache_invalidation_error", error=str(e))

            # Registrar reward no RL
            if self.scheduling_optimizer:
                try:
                    reward = 0.5 + rl_confidence * 0.5
                    self.scheduling_optimizer.record_reward(reward)
                    if self.metrics:
                        self.metrics.observe_histogram("rl_reward_distribution", reward)
                except Exception as e:
                    logger.warning("rl_reward_record_failed", error=str(e))

            # Métricas
            if self.metrics:
                for service in slo_updates.keys():
                    self.metrics.increment_counter(
                        "orchestrator_slo_updates_total",
                        {"service": service, "status": "success"}
                    )

            logger.info(
                "slos_updated_successfully",
                optimization_id=optimization_id,
                services=list(slo_updates.keys()),
                is_gradual=is_gradual,
            )

            if PROTO_AVAILABLE:
                # Converter previous_slos para proto
                prev_slo_protos = {}
                for svc, config in previous_slos.items():
                    prev_slo_protos[svc] = orchestrator_extensions_pb2.SLOConfig(
                        target_latency_ms=config.get("target_latency_ms", 1000),
                        target_availability=config.get("target_availability", 0.999),
                        target_error_rate=config.get("target_error_rate", 0.01),
                        latency_percentile=config.get("latency_percentile", 0.95),
                        time_window_seconds=config.get("time_window_seconds", 60),
                    )

                # Converter applied_slos para proto
                applied_slo_protos = {}
                for svc, config in slo_updates.items():
                    applied_slo_protos[svc] = orchestrator_extensions_pb2.SLOConfig(
                        target_latency_ms=config.get("target_latency_ms", 1000),
                        target_availability=config.get("target_availability", 0.999),
                        target_error_rate=config.get("target_error_rate", 0.01),
                        latency_percentile=config.get("latency_percentile", 0.95),
                        time_window_seconds=config.get("time_window_seconds", 60),
                    )

                return orchestrator_extensions_pb2.UpdateSLOsResponse(
                    success=True,
                    message="SLOs atualizados com sucesso",
                    previous_slos=prev_slo_protos,
                    applied_slos=applied_slo_protos,
                    applied_at=applied_at,
                    is_gradual_rollout=is_gradual,
                )
            else:
                return {
                    "success": True,
                    "message": "SLOs atualizados com sucesso",
                    "previous_slos": previous_slos,
                    "applied_slos": slo_updates,
                    "applied_at": applied_at,
                    "is_gradual_rollout": is_gradual,
                }

        except Exception as e:
            logger.error("update_slos_failed", optimization_id=request.optimization_id, error=str(e))

            if self.metrics:
                self.metrics.increment_counter(
                    "orchestrator_slo_updates_total",
                    {"service": "all", "status": "error"}
                )

            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao atualizar SLOs: {str(e)}")
            raise

    async def ValidateSLOAdjustment(self, request, context):
        """
        Validar ajuste de SLO antes de aplicar.

        Args:
            request: ValidateSLOAdjustmentRequest
            context: gRPC context

        Returns:
            ValidateSLOAdjustmentResponse
        """
        try:
            proposed_slos = {}
            for service, slo_config in request.proposed_slos.items():
                proposed_slos[service] = {
                    "target_latency_ms": slo_config.target_latency_ms,
                    "target_availability": slo_config.target_availability,
                    "target_error_rate": slo_config.target_error_rate,
                    "latency_percentile": slo_config.latency_percentile,
                    "time_window_seconds": slo_config.time_window_seconds,
                }

            check_error_budget = request.check_error_budget

            logger.info(
                "validate_slo_adjustment_requested",
                services=list(proposed_slos.keys()),
                check_error_budget=check_error_budget,
            )

            result = await self._validate_slos(proposed_slos, check_error_budget=check_error_budget)

            if PROTO_AVAILABLE:
                errors = []
                for error in result.get("errors", []):
                    errors.append(orchestrator_extensions_pb2.SLOValidationError(
                        service=error.get("service", ""),
                        field=error.get("field", ""),
                        description=error.get("description", ""),
                        proposed_value=str(error.get("proposed_value", "")),
                        allowed_range=str(error.get("allowed_range", "")),
                    ))

                impact_assessment = {}
                for service, impact in result.get("impact_assessment", {}).items():
                    impact_assessment[service] = orchestrator_extensions_pb2.ImpactAssessment(
                        service=service,
                        availability_impact=impact.get("availability_impact", 0),
                        latency_impact=impact.get("latency_impact", 0),
                        estimated_risk=impact.get("estimated_risk", 0),
                        affected_dependencies=impact.get("affected_dependencies", []),
                    )

                return orchestrator_extensions_pb2.ValidateSLOAdjustmentResponse(
                    is_valid=result.get("is_valid", False),
                    message=result.get("message", ""),
                    errors=errors,
                    warnings=result.get("warnings", []),
                    impact_assessment=impact_assessment,
                )
            else:
                return result

        except Exception as e:
            logger.error("validate_slo_adjustment_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha na validação: {str(e)}")
            raise

    async def RollbackSLOs(self, request, context):
        """
        Reverter SLOs para versão anterior.

        Args:
            request: RollbackSLOsRequest
            context: gRPC context

        Returns:
            RollbackSLOsResponse
        """
        try:
            optimization_id = request.optimization_id
            services = list(request.services) if request.services else []
            force = request.force

            logger.info(
                "rollback_slos_requested",
                optimization_id=optimization_id,
                services=services,
                force=force,
            )

            if not self.mongodb_client:
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details("MongoDB client não disponível")
                raise Exception("MongoDB não disponível")

            # Buscar ajustes originais
            query = {"optimization_id": optimization_id}
            if services:
                query["service"] = {"$in": services}

            cursor = await self.mongodb_client.find("slo_adjustments", query)
            adjustments = []
            async for doc in cursor:
                adjustments.append(doc)

            if not adjustments:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Otimização {optimization_id} não encontrada")
                raise Exception(f"Otimização {optimization_id} não encontrada")

            restored_slos = {}
            rolled_back_at = int(time.time() * 1000)

            for adjustment in adjustments:
                if adjustment.get("was_rolled_back") and not force:
                    continue

                service = adjustment.get("service")
                slo_before = adjustment.get("slo_before", {})

                if not slo_before:
                    continue

                # Restaurar SLOs anteriores
                await self.mongodb_client.update_many(
                    "slo_configs",
                    {"service": service, "active": True},
                    {"$set": {"active": False}}
                )

                await self.mongodb_client.insert_one(
                    "slo_configs",
                    {
                        "service": service,
                        "optimization_id": f"rollback-{optimization_id}",
                        **slo_before,
                        "justification": f"Rollback da otimização {optimization_id}",
                        "last_updated_at": rolled_back_at,
                        "active": True,
                        "is_rollback": True,
                        "original_optimization_id": optimization_id,
                    }
                )

                # Marcar ajuste como revertido
                await self.mongodb_client.update_one(
                    "slo_adjustments",
                    {"optimization_id": optimization_id, "service": service},
                    {"$set": {"was_rolled_back": True, "rolled_back_at": rolled_back_at}}
                )

                restored_slos[service] = slo_before

            # Invalidar cache
            if self.redis_client:
                try:
                    await self.redis_client.delete(f"{self._slo_cache_prefix}all")
                    for service in restored_slos.keys():
                        await self.redis_client.delete(f"{self._slo_cache_prefix}{service}")
                except Exception as e:
                    logger.warning("redis_cache_invalidation_error", error=str(e))

            # Métricas
            if self.metrics:
                self.metrics.increment_counter(
                    "orchestrator_slo_rollbacks_total",
                    {"optimization_id": optimization_id}
                )

            logger.info(
                "slos_rolled_back",
                optimization_id=optimization_id,
                services=list(restored_slos.keys()),
            )

            if PROTO_AVAILABLE:
                restored_slo_protos = {}
                for svc, config in restored_slos.items():
                    restored_slo_protos[svc] = orchestrator_extensions_pb2.SLOConfig(
                        target_latency_ms=config.get("target_latency_ms", 1000),
                        target_availability=config.get("target_availability", 0.999),
                        target_error_rate=config.get("target_error_rate", 0.01),
                        latency_percentile=config.get("latency_percentile", 0.95),
                        time_window_seconds=config.get("time_window_seconds", 60),
                    )

                return orchestrator_extensions_pb2.RollbackSLOsResponse(
                    success=True,
                    message="SLOs revertidos com sucesso",
                    restored_slos=restored_slo_protos,
                    rolled_back_at=rolled_back_at,
                )
            else:
                return {
                    "success": True,
                    "message": "SLOs revertidos com sucesso",
                    "restored_slos": restored_slos,
                    "rolled_back_at": rolled_back_at,
                }

        except Exception as e:
            logger.error("rollback_slos_failed", optimization_id=request.optimization_id, error=str(e))
            if not context.code():
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Falha no rollback: {str(e)}")
            raise

    async def GetSLOComplianceMetrics(self, request, context):
        """
        Obter métricas de compliance de SLO.

        Args:
            request: GetSLOComplianceMetricsRequest
            context: gRPC context

        Returns:
            GetSLOComplianceMetricsResponse
        """
        try:
            service = request.service
            time_range = request.time_range or "1h"

            logger.info("get_slo_compliance_metrics_requested", service=service, time_range=time_range)

            time_seconds = self._parse_time_range(time_range)

            # Métricas padrão
            metrics_data = {
                "service": service,
                "compliance_percentage": 0.998,
                "average_latency_ms": 850,
                "p95_latency_ms": 1200,
                "p99_latency_ms": 1800,
                "availability": 0.9995,
                "error_rate": 0.008,
                "average_throughput": 1000,
                "slo_violations": 0,
                "metric_compliance": {},
            }

            # Buscar métricas do ClickHouse se disponível
            if self.clickhouse_client:
                try:
                    result = await self.clickhouse_client.query(
                        f"""
                        SELECT
                            avg(latency_ms) as avg_latency,
                            quantile(0.95)(latency_ms) as p95_latency,
                            quantile(0.99)(latency_ms) as p99_latency,
                            1 - (countIf(status_code >= 500) / count()) as availability,
                            countIf(status_code >= 400) / count() as error_rate,
                            count() / {time_seconds} as avg_throughput,
                            countIf(slo_violated = 1) as slo_violations
                        FROM request_metrics
                        WHERE service = '{service}'
                        AND timestamp >= now() - INTERVAL {time_seconds} SECOND
                        """
                    )

                    if result and len(result) > 0:
                        row = result[0]
                        metrics_data["average_latency_ms"] = row.get("avg_latency", 850)
                        metrics_data["p95_latency_ms"] = row.get("p95_latency", 1200)
                        metrics_data["p99_latency_ms"] = row.get("p99_latency", 1800)
                        metrics_data["availability"] = row.get("availability", 0.9995)
                        metrics_data["error_rate"] = row.get("error_rate", 0.008)
                        metrics_data["average_throughput"] = row.get("avg_throughput", 1000)
                        metrics_data["slo_violations"] = int(row.get("slo_violations", 0))

                except Exception as e:
                    logger.warning("clickhouse_compliance_query_failed", error=str(e))

            # Calcular compliance por métrica
            if self.mongodb_client:
                slo_doc = await self.mongodb_client.find_one(
                    "slo_configs",
                    {"service": service, "active": True}
                )
                if slo_doc:
                    target_latency = slo_doc.get("target_latency_ms", 1000)
                    target_availability = slo_doc.get("target_availability", 0.999)
                    target_error_rate = slo_doc.get("target_error_rate", 0.01)

                    # Latency compliance
                    latency_compliance = min(1.0, target_latency / max(metrics_data["p95_latency_ms"], 1))
                    metrics_data["metric_compliance"]["latency"] = {
                        "metric_name": "latency_p95",
                        "target_value": target_latency,
                        "current_value": metrics_data["p95_latency_ms"],
                        "compliance": latency_compliance,
                        "in_violation": metrics_data["p95_latency_ms"] > target_latency,
                    }

                    # Availability compliance
                    availability_compliance = min(1.0, metrics_data["availability"] / target_availability)
                    metrics_data["metric_compliance"]["availability"] = {
                        "metric_name": "availability",
                        "target_value": target_availability,
                        "current_value": metrics_data["availability"],
                        "compliance": availability_compliance,
                        "in_violation": metrics_data["availability"] < target_availability,
                    }

                    # Error rate compliance
                    error_rate_compliance = min(1.0, target_error_rate / max(metrics_data["error_rate"], 0.001))
                    metrics_data["metric_compliance"]["error_rate"] = {
                        "metric_name": "error_rate",
                        "target_value": target_error_rate,
                        "current_value": metrics_data["error_rate"],
                        "compliance": error_rate_compliance,
                        "in_violation": metrics_data["error_rate"] > target_error_rate,
                    }

                    # Compliance total (média)
                    metrics_data["compliance_percentage"] = (
                        latency_compliance + availability_compliance + error_rate_compliance
                    ) / 3

            logger.info("slo_compliance_metrics_retrieved", service=service)

            if PROTO_AVAILABLE:
                metric_compliance_protos = {}
                for key, mc in metrics_data.get("metric_compliance", {}).items():
                    metric_compliance_protos[key] = orchestrator_extensions_pb2.MetricCompliance(
                        metric_name=mc.get("metric_name", key),
                        target_value=mc.get("target_value", 0),
                        current_value=mc.get("current_value", 0),
                        compliance=mc.get("compliance", 1.0),
                        in_violation=mc.get("in_violation", False),
                    )

                return orchestrator_extensions_pb2.GetSLOComplianceMetricsResponse(
                    service=service,
                    compliance_percentage=metrics_data["compliance_percentage"],
                    average_latency_ms=metrics_data["average_latency_ms"],
                    p95_latency_ms=metrics_data["p95_latency_ms"],
                    p99_latency_ms=metrics_data["p99_latency_ms"],
                    availability=metrics_data["availability"],
                    error_rate=metrics_data["error_rate"],
                    average_throughput=metrics_data["average_throughput"],
                    slo_violations=metrics_data["slo_violations"],
                    metric_compliance=metric_compliance_protos,
                )
            else:
                return metrics_data

        except Exception as e:
            logger.error("get_slo_compliance_metrics_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter métricas: {str(e)}")
            raise

    async def GetErrorBudget(self, request, context):
        """
        Obter error budget restante.

        Args:
            request: GetErrorBudgetRequest
            context: gRPC context

        Returns:
            GetErrorBudgetResponse
        """
        try:
            service = request.service

            logger.info("get_error_budget_requested", service=service)

            # Valores padrão
            budget_data = {
                "service": service,
                "remaining_budget_percentage": 0.85,
                "consumed_budget": 0.15,
                "total_budget": 1.0,
                "budget_reset_at": int(time.time() * 1000) + 2592000000,  # +30 dias
                "burn_rate_per_hour": 0.001,
                "estimated_depletion_seconds": None,
            }

            # Calcular error budget baseado em SLO e métricas reais
            if self.mongodb_client:
                slo_doc = await self.mongodb_client.find_one(
                    "slo_configs",
                    {"service": service, "active": True}
                )

                if slo_doc:
                    target_availability = slo_doc.get("target_availability", 0.999)
                    # Error budget = 1 - target_availability
                    total_budget = 1 - target_availability

                    # Buscar violations do último mês
                    month_ago = int(time.time() * 1000) - 2592000000
                    violation_count = await self.mongodb_client.count(
                        "slo_violations",
                        {"service": service, "timestamp": {"$gte": month_ago}}
                    )

                    # Estimar budget consumido (simplificado)
                    consumed = min(total_budget, violation_count * 0.0001)
                    remaining = total_budget - consumed

                    budget_data["total_budget"] = total_budget
                    budget_data["consumed_budget"] = consumed
                    budget_data["remaining_budget_percentage"] = (remaining / total_budget) if total_budget > 0 else 1.0

                    # Calcular burn rate
                    if self.clickhouse_client:
                        try:
                            result = await self.clickhouse_client.query(
                                f"""
                                SELECT countIf(slo_violated = 1) / count() as burn_rate
                                FROM request_metrics
                                WHERE service = '{service}'
                                AND timestamp >= now() - INTERVAL 1 HOUR
                                """
                            )
                            if result and len(result) > 0:
                                budget_data["burn_rate_per_hour"] = result[0].get("burn_rate", 0.001)
                        except Exception as e:
                            logger.warning("clickhouse_burn_rate_query_failed", error=str(e))

                    # Estimar tempo até depleção
                    if budget_data["burn_rate_per_hour"] > 0 and remaining > 0:
                        budget_data["estimated_depletion_seconds"] = int(
                            (remaining / budget_data["burn_rate_per_hour"]) * 3600
                        )

            logger.info("error_budget_retrieved", service=service, remaining=budget_data["remaining_budget_percentage"])

            if PROTO_AVAILABLE:
                response = orchestrator_extensions_pb2.GetErrorBudgetResponse(
                    service=service,
                    remaining_budget_percentage=budget_data["remaining_budget_percentage"],
                    consumed_budget=budget_data["consumed_budget"],
                    total_budget=budget_data["total_budget"],
                    budget_reset_at=budget_data["budget_reset_at"],
                    burn_rate_per_hour=budget_data["burn_rate_per_hour"],
                )
                if budget_data["estimated_depletion_seconds"] is not None:
                    response.estimated_depletion_seconds = budget_data["estimated_depletion_seconds"]
                return response
            else:
                return budget_data

        except Exception as e:
            logger.error("get_error_budget_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter error budget: {str(e)}")
            raise

    async def GetSLOHistory(self, request, context):
        """
        Obter histórico de ajustes de SLO.

        Args:
            request: GetSLOHistoryRequest
            context: gRPC context

        Returns:
            GetSLOHistoryResponse
        """
        try:
            service = request.service if request.HasField("service") else None
            limit = request.limit or 50
            offset = request.offset or 0

            logger.info(
                "get_slo_history_requested",
                service=service,
                limit=limit,
                offset=offset,
            )

            adjustments = []
            total = 0

            if self.mongodb_client:
                query = {}
                if service:
                    query["service"] = service

                total = await self.mongodb_client.count("slo_adjustments", query)

                cursor = await self.mongodb_client.find(
                    "slo_adjustments",
                    query,
                    sort=[("adjusted_at", -1)],
                    skip=offset,
                    limit=limit,
                )

                async for doc in cursor:
                    adjustments.append({
                        "optimization_id": doc.get("optimization_id", ""),
                        "adjusted_at": doc.get("adjusted_at", 0),
                        "service": doc.get("service", ""),
                        "slo_before": doc.get("slo_before", {}),
                        "slo_after": doc.get("slo_after", {}),
                        "justification": doc.get("justification", ""),
                        "compliance_before": doc.get("compliance_before"),
                        "compliance_after": doc.get("compliance_after"),
                        "was_rolled_back": doc.get("was_rolled_back", False),
                    })

            logger.info("slo_history_retrieved", count=len(adjustments), total=total)

            if PROTO_AVAILABLE:
                adjustment_protos = []
                for adj in adjustments:
                    slo_before = adj.get("slo_before", {})
                    slo_after = adj.get("slo_after", {})

                    adjustment_proto = orchestrator_extensions_pb2.SLOAdjustment(
                        optimization_id=adj["optimization_id"],
                        adjusted_at=adj["adjusted_at"],
                        service=adj["service"],
                        justification=adj["justification"],
                        was_rolled_back=adj["was_rolled_back"],
                    )

                    if slo_before:
                        adjustment_proto.slo_before.CopyFrom(orchestrator_extensions_pb2.SLOConfig(
                            target_latency_ms=slo_before.get("target_latency_ms", 1000),
                            target_availability=slo_before.get("target_availability", 0.999),
                            target_error_rate=slo_before.get("target_error_rate", 0.01),
                            latency_percentile=slo_before.get("latency_percentile", 0.95),
                            time_window_seconds=slo_before.get("time_window_seconds", 60),
                        ))

                    if slo_after:
                        adjustment_proto.slo_after.CopyFrom(orchestrator_extensions_pb2.SLOConfig(
                            target_latency_ms=slo_after.get("target_latency_ms", 1000),
                            target_availability=slo_after.get("target_availability", 0.999),
                            target_error_rate=slo_after.get("target_error_rate", 0.01),
                            latency_percentile=slo_after.get("latency_percentile", 0.95),
                            time_window_seconds=slo_after.get("time_window_seconds", 60),
                        ))

                    if adj.get("compliance_before") is not None:
                        adjustment_proto.compliance_before = adj["compliance_before"]
                    if adj.get("compliance_after") is not None:
                        adjustment_proto.compliance_after = adj["compliance_after"]

                    adjustment_protos.append(adjustment_proto)

                return orchestrator_extensions_pb2.GetSLOHistoryResponse(
                    adjustments=adjustment_protos,
                    total=total,
                )
            else:
                return {"adjustments": adjustments, "total": total}

        except Exception as e:
            logger.error("get_slo_history_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha ao obter histórico: {str(e)}")
            raise

    async def _validate_slos(self, proposed_slos: Dict[str, Dict], check_error_budget: bool = True) -> Dict:
        """
        Validar SLOs propostos.

        Args:
            proposed_slos: SLOs propostos
            check_error_budget: Se deve verificar error budget

        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []
        impact_assessment = {}

        for service, slo_config in proposed_slos.items():
            # Validar latência
            latency = slo_config.get("target_latency_ms", 0)
            if latency < 100:
                errors.append({
                    "service": service,
                    "field": "target_latency_ms",
                    "description": "Latência mínima é 100ms",
                    "proposed_value": latency,
                    "allowed_range": ">= 100ms",
                })
            elif latency < 200:
                warnings.append(f"Latência muito baixa ({latency}ms) para {service}, pode causar SLO violations")

            # Validar disponibilidade
            availability = slo_config.get("target_availability", 0)
            if availability < 0.95:
                errors.append({
                    "service": service,
                    "field": "target_availability",
                    "description": "Disponibilidade mínima é 0.95 (95%)",
                    "proposed_value": availability,
                    "allowed_range": ">= 0.95",
                })
            elif availability > 0.9999:
                warnings.append(f"Disponibilidade muito alta ({availability}) para {service}, pode ser inatingível")

            # Validar error rate
            error_rate = slo_config.get("target_error_rate", 0)
            if error_rate > 0.10:
                errors.append({
                    "service": service,
                    "field": "target_error_rate",
                    "description": "Error rate máximo é 0.10 (10%)",
                    "proposed_value": error_rate,
                    "allowed_range": "<= 0.10",
                })
            elif error_rate < 0.001:
                warnings.append(f"Error rate muito baixo ({error_rate}) para {service}, pode ser inatingível")

            # Verificar error budget se solicitado
            if check_error_budget and self.mongodb_client:
                try:
                    # Simplificado: verificar se há budget suficiente
                    month_ago = int(time.time() * 1000) - 2592000000
                    violation_count = await self.mongodb_client.count(
                        "slo_violations",
                        {"service": service, "timestamp": {"$gte": month_ago}}
                    )

                    target_availability = slo_config.get("target_availability", 0.999)
                    total_budget = 1 - target_availability
                    consumed = min(total_budget, violation_count * 0.0001)
                    remaining_pct = (total_budget - consumed) / total_budget if total_budget > 0 else 1.0

                    if remaining_pct < 0.2:
                        warnings.append(
                            f"Error budget de {service} está baixo ({remaining_pct*100:.1f}%), "
                            "ajuste pode causar SLO violations"
                        )
                except Exception as e:
                    logger.warning("error_budget_check_failed", service=service, error=str(e))

            # Calcular impacto
            impact_assessment[service] = {
                "availability_impact": 0.0,
                "latency_impact": 0.0,
                "estimated_risk": 0.1,
                "affected_dependencies": [],
            }

            # Buscar SLO atual para calcular deltas
            if self.mongodb_client:
                current_slo = await self.mongodb_client.find_one(
                    "slo_configs",
                    {"service": service, "active": True}
                )
                if current_slo:
                    current_latency = current_slo.get("target_latency_ms", 1000)
                    current_availability = current_slo.get("target_availability", 0.999)

                    latency_delta = (latency - current_latency) / current_latency if current_latency > 0 else 0
                    availability_delta = (availability - current_availability) / current_availability if current_availability > 0 else 0

                    impact_assessment[service]["latency_impact"] = latency_delta
                    impact_assessment[service]["availability_impact"] = availability_delta
                    impact_assessment[service]["estimated_risk"] = abs(latency_delta) * 0.3 + abs(availability_delta) * 0.7

        is_valid = len(errors) == 0
        message = "Validação bem-sucedida" if is_valid else f"{len(errors)} erro(s) encontrado(s)"

        return {
            "is_valid": is_valid,
            "message": message,
            "errors": errors,
            "warnings": warnings,
            "impact_assessment": impact_assessment,
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

    def _get_current_state(self, slo_updates: Dict) -> str:
        """
        Obter estado atual para consulta de Q-values.

        Args:
            slo_updates: SLOs sendo atualizados

        Returns:
            String representando estado atual
        """
        services = "_".join(sorted(slo_updates.keys()))
        return f"slo_optimization_{services}"
