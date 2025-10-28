from typing import Dict, Optional

import grpc
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger()


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

            # TODO: Criar stub quando proto estendido for compilado
            # from orchestrator_pb2_grpc import OrchestratorStub
            # self.stub = OrchestratorStub(self.channel)

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
            # TODO: Implementar quando proto estendido
            # request = GetCurrentSLOsRequest(service=service or "")
            # response = await self.stub.GetCurrentSLOs(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("get_current_slos_stub_called", service=service)
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
            # TODO: Implementar quando proto estendido
            # request = UpdateSLOsRequest(
            #     slo_updates=slo_updates,
            #     justification=justification,
            #     optimization_id=optimization_id
            # )
            # response = await self.stub.UpdateSLOs(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning(
                "update_slos_stub_called",
                services=list(slo_updates.keys()),
                justification=justification,
                optimization_id=optimization_id,
            )

            logger.info(
                "slos_updated",
                optimization_id=optimization_id,
                services=list(slo_updates.keys()),
            )
            return True

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
            # TODO: Implementar quando proto estendido
            # request = GetSLOComplianceMetricsRequest(service=service, time_range=time_range)
            # response = await self.stub.GetSLOComplianceMetrics(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("get_slo_compliance_metrics_stub_called", service=service, time_range=time_range)
            metrics = {
                "compliance_percentage": 0.998,
                "average_latency_ms": 850,
                "availability": 0.9995,
                "error_rate": 0.008,
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
            # TODO: Implementar quando proto estendido
            # request = ValidateSLOAdjustmentRequest(proposed_slos=proposed_slos)
            # response = await self.stub.ValidateSLOAdjustment(request, timeout=self.settings.grpc_timeout)

            # Validações locais temporárias
            for service, slo_config in proposed_slos.items():
                # Verificar se latência é positiva
                if slo_config.get("target_latency_ms", 0) <= 0:
                    logger.warning("invalid_latency", service=service)
                    return False

                # Verificar se availability está entre 0 e 1
                availability = slo_config.get("target_availability", 0)
                if not (0.0 <= availability <= 1.0):
                    logger.warning("invalid_availability", service=service, availability=availability)
                    return False

                # Verificar se error_rate está entre 0 e 1
                error_rate = slo_config.get("target_error_rate", 0)
                if not (0.0 <= error_rate <= 1.0):
                    logger.warning("invalid_error_rate", service=service, error_rate=error_rate)
                    return False

            logger.info("slo_adjustment_validated", services=list(proposed_slos.keys()))
            return True

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
            # TODO: Implementar quando proto estendido
            # request = RollbackSLOsRequest(optimization_id=optimization_id)
            # response = await self.stub.RollbackSLOs(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("rollback_slos_stub_called", optimization_id=optimization_id)

            logger.info("slos_rolled_back", optimization_id=optimization_id)
            return True

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
            # TODO: Implementar quando proto estendido
            # request = GetErrorBudgetRequest(service=service)
            # response = await self.stub.GetErrorBudget(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("get_error_budget_stub_called", service=service)
            budget = {
                "remaining_budget_percentage": 0.85,
                "budget_reset_at": 1699056000000,  # Unix timestamp
            }

            logger.info("error_budget_retrieved", service=service)
            return budget

        except grpc.RpcError as e:
            logger.error("get_error_budget_failed", service=service, error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_error_budget_failed", service=service, error=str(e))
            return None
