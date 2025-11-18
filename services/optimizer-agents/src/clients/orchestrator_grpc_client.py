from typing import Dict, Optional

import grpc
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger()

# Proto imports - will be available after `make proto` compilation
try:
    from proto import orchestrator_extensions_pb2, orchestrator_extensions_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    logger.warning("orchestrator_proto_not_compiled", message="Run 'make proto' to compile protocol buffers")


class OrchestratorGrpcClient:
    """
    Cliente gRPC para Orchestrator Dynamic.

    Responsável por ajuste de SLOs e gestão de workflows.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None

    async def connect(self):
        """Estabelecer canal gRPC com Orchestrator."""
        try:
            self.channel = grpc.aio.insecure_channel(
                self.settings.orchestrator_endpoint,
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                ],
            )

            # Criar stub quando proto estiver compilado
            if PROTO_AVAILABLE:
                self.stub = orchestrator_extensions_pb2_grpc.OrchestratorOptimizationStub(self.channel)
                logger.info("orchestrator_stub_created")
            else:
                logger.warning("orchestrator_stub_not_created", reason="proto_not_compiled")

            await self.channel.channel_ready()

            logger.info("orchestrator_grpc_connected", endpoint=self.settings.orchestrator_endpoint)
        except Exception as e:
            logger.error("orchestrator_grpc_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Fechar canal gRPC."""
        if self.channel:
            await self.channel.close()
            logger.info("orchestrator_grpc_disconnected")

    async def get_current_slos(self, service: Optional[str] = None) -> Optional[Dict]:
        """
        Obter SLOs atuais.

        Args:
            service: Nome do serviço (opcional, retorna todos se None)

        Returns:
            Dict com {service: SLOConfig}
        """
        try:
            if not PROTO_AVAILABLE or not self.stub:
                logger.warning("get_current_slos_proto_unavailable", service=service)
                # Fallback para stub temporário
                slos = {
                    "consensus-engine": {
                        "target_latency_ms": 1000,
                        "target_availability": 0.999,
                        "target_error_rate": 0.01,
                        "last_updated": 1696377600000,
                    },
                    "orchestrator-dynamic": {
                        "target_latency_ms": 2000,
                        "target_availability": 0.995,
                        "target_error_rate": 0.02,
                        "last_updated": 1696377600000,
                    },
                }
                if service:
                    slos = {service: slos.get(service, {})}
                return slos

            # Chamada gRPC real
            request = orchestrator_extensions_pb2.GetCurrentSLOsRequest(service=service or "")
            response = await self.stub.GetCurrentSLOs(request, timeout=self.settings.grpc_timeout)

            # Converter resposta proto para dict
            slos = {}
            for svc, slo_config in response.slos.items():
                slos[svc] = {
                    "target_latency_ms": slo_config.target_latency_ms,
                    "target_availability": slo_config.target_availability,
                    "target_error_rate": slo_config.target_error_rate,
                    "min_throughput": slo_config.min_throughput if slo_config.HasField("min_throughput") else None,
                    "latency_percentile": slo_config.latency_percentile,
                    "time_window_seconds": slo_config.time_window_seconds,
                    "metadata": dict(slo_config.metadata),
                    "last_updated": response.last_updated_at,
                }

            logger.info("current_slos_retrieved", service=service, count=len(slos))
            return slos

        except grpc.RpcError as e:
            logger.error("get_current_slos_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_current_slos_failed", error=str(e))
            return None

    async def update_slos(
        self, slo_updates: Dict[str, Dict], justification: str, optimization_id: str
    ) -> bool:
        """
        Atualizar SLOs.

        Args:
            slo_updates: Dict com {service: {slo_config}}
            justification: Justificativa da mudança
            optimization_id: ID da otimização

        Returns:
            True se bem-sucedido
        """
        try:
            if not PROTO_AVAILABLE or not self.stub:
                logger.warning(
                    "update_slos_proto_unavailable",
                    services=list(slo_updates.keys()),
                    optimization_id=optimization_id,
                )
                return True  # Fallback: simular sucesso

            # Converter dict para proto
            slo_configs = {}
            for service, config in slo_updates.items():
                slo_config = orchestrator_extensions_pb2.SLOConfig(
                    target_latency_ms=config.get("target_latency_ms", 0),
                    target_availability=config.get("target_availability", 0),
                    target_error_rate=config.get("target_error_rate", 0),
                    latency_percentile=config.get("latency_percentile", 0.95),
                    time_window_seconds=config.get("time_window_seconds", 60),
                )
                if "min_throughput" in config:
                    slo_config.min_throughput = config["min_throughput"]
                if "metadata" in config:
                    slo_config.metadata.update(config["metadata"])
                slo_configs[service] = slo_config

            # Chamada gRPC real
            request = orchestrator_extensions_pb2.UpdateSLOsRequest(
                slo_updates=slo_configs,
                justification=justification,
                optimization_id=optimization_id,
                validate_before_apply=True
            )
            response = await self.stub.UpdateSLOs(request, timeout=self.settings.grpc_timeout)

            if response.success:
                logger.info(
                    "slos_updated",
                    optimization_id=optimization_id,
                    services=list(slo_updates.keys()),
                    applied_at=response.applied_at
                )
            return response.success

        except grpc.RpcError as e:
            logger.error(
                "update_slos_failed",
                optimization_id=optimization_id,
                error=str(e),
                code=e.code(),
            )
            return False
        except Exception as e:
            logger.error("update_slos_failed", optimization_id=optimization_id, error=str(e))
            return False

    async def get_slo_compliance_metrics(self, service: str, time_range: str = "1h") -> Optional[Dict]:
        """
        Obter métricas de compliance de SLO.

        Args:
            service: Nome do serviço
            time_range: Intervalo de tempo

        Returns:
            Dict com métricas de compliance
        """
        try:
            if not PROTO_AVAILABLE or not self.stub:
                logger.warning("get_slo_compliance_metrics_proto_unavailable", service=service)
                # Fallback para stub temporário
                return {
                    "compliance_percentage": 0.998,
                    "average_latency_ms": 850,
                    "availability": 0.9995,
                    "error_rate": 0.008,
                }

            # Chamada gRPC real
            request = orchestrator_extensions_pb2.GetSLOComplianceMetricsRequest(
                service=service,
                time_range=time_range
            )
            response = await self.stub.GetSLOComplianceMetrics(request, timeout=self.settings.grpc_timeout)

            # Converter resposta proto para dict
            metrics = {
                "compliance_percentage": response.compliance_percentage,
                "average_latency_ms": response.average_latency_ms,
                "p95_latency_ms": response.p95_latency_ms,
                "p99_latency_ms": response.p99_latency_ms,
                "availability": response.availability,
                "error_rate": response.error_rate,
                "average_throughput": response.average_throughput,
                "slo_violations": response.slo_violations,
                "metric_compliance": {
                    k: {
                        "metric_name": v.metric_name,
                        "target_value": v.target_value,
                        "current_value": v.current_value,
                        "compliance": v.compliance,
                        "in_violation": v.in_violation,
                    }
                    for k, v in response.metric_compliance.items()
                }
            }

            logger.info("slo_compliance_metrics_retrieved", service=service)
            return metrics

        except grpc.RpcError as e:
            logger.error("get_slo_compliance_metrics_failed", service=service, error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_slo_compliance_metrics_failed", service=service, error=str(e))
            return None

    async def validate_slo_adjustment(self, proposed_slos: Dict) -> bool:
        """
        Validar se ajuste de SLO é seguro.

        Args:
            proposed_slos: SLOs propostos

        Returns:
            True se válido
        """
        try:
            if not PROTO_AVAILABLE or not self.stub:
                logger.warning("validate_slo_adjustment_proto_unavailable")
                # Validações locais como fallback
                for service, slo_config in proposed_slos.items():
                    if slo_config.get("target_latency_ms", 0) <= 0:
                        logger.warning("invalid_latency", service=service)
                        return False
                    availability = slo_config.get("target_availability", 0)
                    if not (0.0 <= availability <= 1.0):
                        logger.warning("invalid_availability", service=service, availability=availability)
                        return False
                    error_rate = slo_config.get("target_error_rate", 0)
                    if not (0.0 <= error_rate <= 1.0):
                        logger.warning("invalid_error_rate", service=service, error_rate=error_rate)
                        return False
                return True

            # Converter dict para proto
            slo_configs = {}
            for service, config in proposed_slos.items():
                slo_config = orchestrator_extensions_pb2.SLOConfig(
                    target_latency_ms=config.get("target_latency_ms", 0),
                    target_availability=config.get("target_availability", 0),
                    target_error_rate=config.get("target_error_rate", 0),
                    latency_percentile=config.get("latency_percentile", 0.95),
                    time_window_seconds=config.get("time_window_seconds", 60),
                )
                if "min_throughput" in config:
                    slo_config.min_throughput = config["min_throughput"]
                if "metadata" in config:
                    slo_config.metadata.update(config["metadata"])
                slo_configs[service] = slo_config

            # Chamada gRPC real
            request = orchestrator_extensions_pb2.ValidateSLOAdjustmentRequest(
                proposed_slos=slo_configs,
                check_error_budget=True
            )
            response = await self.stub.ValidateSLOAdjustment(request, timeout=self.settings.grpc_timeout)

            if not response.is_valid:
                logger.warning("slo_adjustment_invalid", message=response.message, errors=len(response.errors))
                for error in response.errors:
                    logger.warning(
                        "slo_validation_error",
                        service=error.service,
                        field=error.field,
                        description=error.description
                    )

            logger.info("slo_adjustment_validated", services=list(proposed_slos.keys()), is_valid=response.is_valid)
            return response.is_valid

        except grpc.RpcError as e:
            logger.error("validate_slo_adjustment_failed", error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("validate_slo_adjustment_failed", error=str(e))
            return False

    async def rollback_slos(self, optimization_id: str) -> bool:
        """
        Reverter SLOs para versão anterior.

        Args:
            optimization_id: ID da otimização a reverter

        Returns:
            True se bem-sucedido
        """
        try:
            if not PROTO_AVAILABLE or not self.stub:
                logger.warning("rollback_slos_proto_unavailable", optimization_id=optimization_id)
                return True  # Fallback: simular sucesso

            # Chamada gRPC real
            request = orchestrator_extensions_pb2.RollbackSLOsRequest(
                optimization_id=optimization_id,
                force=False
            )
            response = await self.stub.RollbackSLOs(request, timeout=self.settings.grpc_timeout)

            if response.success:
                logger.info(
                    "slos_rolled_back",
                    optimization_id=optimization_id,
                    services=list(response.restored_slos.keys()),
                    rolled_back_at=response.rolled_back_at
                )
            return response.success

        except grpc.RpcError as e:
            logger.error("rollback_slos_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("rollback_slos_failed", optimization_id=optimization_id, error=str(e))
            return False

    async def get_error_budget(self, service: str) -> Optional[Dict]:
        """
        Obter error budget restante.

        Args:
            service: Nome do serviço

        Returns:
            Dict com error budget info
        """
        try:
            if not PROTO_AVAILABLE or not self.stub:
                logger.warning("get_error_budget_proto_unavailable", service=service)
                # Fallback para stub temporário
                return {
                    "remaining_budget_percentage": 0.85,
                    "consumed_budget": 0.15,
                    "total_budget": 1.0,
                    "budget_reset_at": 1699056000000,
                }

            # Chamada gRPC real
            request = orchestrator_extensions_pb2.GetErrorBudgetRequest(service=service)
            response = await self.stub.GetErrorBudget(request, timeout=self.settings.grpc_timeout)

            # Converter resposta proto para dict
            budget = {
                "remaining_budget_percentage": response.remaining_budget_percentage,
                "consumed_budget": response.consumed_budget,
                "total_budget": response.total_budget,
                "budget_reset_at": response.budget_reset_at,
                "burn_rate_per_hour": response.burn_rate_per_hour,
            }
            if response.HasField("estimated_depletion_seconds"):
                budget["estimated_depletion_seconds"] = response.estimated_depletion_seconds

            logger.info("error_budget_retrieved", service=service)
            return budget

        except grpc.RpcError as e:
            logger.error("get_error_budget_failed", service=service, error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_error_budget_failed", service=service, error=str(e))
            return None
