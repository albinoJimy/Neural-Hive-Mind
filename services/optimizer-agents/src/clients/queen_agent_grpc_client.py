from typing import Dict, Optional

import grpc
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger()


class QueenAgentGrpcClient:
    """
    Cliente gRPC para Queen Agent.

    Responsável por solicitar aprovação de otimizações de alto risco.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None

    async def connect(self):
        """Estabelecer canal gRPC com Queen Agent."""
        try:
            self.channel = grpc.aio.insecure_channel(
                self.settings.queen_agent_endpoint,
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                ],
            )

            # TODO: Criar stub quando proto estendido for compilado
            # from queen_agent_pb2_grpc import QueenAgentStub
            # self.stub = QueenAgentStub(self.channel)

            await self.channel.channel_ready()

            logger.info("queen_agent_grpc_connected", endpoint=self.settings.queen_agent_endpoint)
        except Exception as e:
            logger.error("queen_agent_grpc_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Fechar canal gRPC."""
        if self.channel:
            await self.channel.close()
            logger.info("queen_agent_grpc_disconnected")

    async def request_approval(
        self, optimization_id: str, optimization_type: str, hypothesis: Dict, risk_score: float
    ) -> Optional[Dict]:
        """
        Solicitar aprovação de otimização.

        Args:
            optimization_id: ID da otimização
            optimization_type: Tipo de otimização
            hypothesis: Hipótese de otimização
            risk_score: Score de risco (0-1)

        Returns:
            Decisão de aprovação ou None se falhou
        """
        try:
            # TODO: Implementar quando proto estendido
            # request = RequestApprovalRequest(
            #     optimization_id=optimization_id,
            #     optimization_type=optimization_type,
            #     hypothesis=hypothesis,
            #     risk_score=risk_score
            # )
            # response = await self.stub.RequestApproval(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning(
                "request_approval_stub_called",
                optimization_id=optimization_id,
                optimization_type=optimization_type,
                risk_score=risk_score,
            )

            # Auto-aprovar se risco baixo, caso contrário requer aprovação manual
            if risk_score < 0.5:
                decision = {
                    "approved": True,
                    "approval_type": "AUTO_APPROVED",
                    "decision_id": f"decision-{optimization_id}",
                    "rationale": "Low risk optimization auto-approved",
                    "conditions": [],
                }
            else:
                decision = {
                    "approved": False,
                    "approval_type": "PENDING_REVIEW",
                    "decision_id": f"decision-{optimization_id}",
                    "rationale": "High risk optimization requires manual approval",
                    "conditions": ["Manual review by operations team", "Gradual rollout required"],
                }

            logger.info(
                "approval_decision_received",
                optimization_id=optimization_id,
                approved=decision["approved"],
                approval_type=decision["approval_type"],
            )
            return decision

        except grpc.RpcError as e:
            logger.error("request_approval_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("request_approval_failed", optimization_id=optimization_id, error=str(e))
            return None

    async def notify_optimization_result(self, optimization_id: str, result: Dict) -> bool:
        """
        Notificar Queen Agent sobre resultado de otimização.

        Args:
            optimization_id: ID da otimização
            result: Resultado da otimização

        Returns:
            True se notificação bem-sucedida
        """
        try:
            # TODO: Implementar quando proto estendido
            # request = NotifyOptimizationResultRequest(
            #     optimization_id=optimization_id,
            #     result=result
            # )
            # response = await self.stub.NotifyOptimizationResult(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning(
                "notify_optimization_result_stub_called",
                optimization_id=optimization_id,
                success=result.get("success", False),
            )

            logger.info("optimization_result_notified", optimization_id=optimization_id)
            return True

        except grpc.RpcError as e:
            logger.error("notify_optimization_result_failed", optimization_id=optimization_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("notify_optimization_result_failed", optimization_id=optimization_id, error=str(e))
            return False

    async def get_strategic_priorities(self) -> Optional[Dict]:
        """
        Obter prioridades estratégicas atuais.

        Returns:
            Prioridades estratégicas ou None se falhou
        """
        try:
            # TODO: Implementar quando proto estendido
            # request = GetStrategicPrioritiesRequest()
            # response = await self.stub.GetStrategicPriorities(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("get_strategic_priorities_stub_called")

            priorities = {
                "current_focus": "PERFORMANCE_OPTIMIZATION",
                "priorities": [
                    {"area": "latency_reduction", "weight": 0.4},
                    {"area": "cost_optimization", "weight": 0.3},
                    {"area": "reliability", "weight": 0.3},
                ],
                "constraints": ["maintain_slo_compliance", "no_breaking_changes"],
                "updated_at": 1696377600000,
            }

            logger.info("strategic_priorities_retrieved", focus=priorities["current_focus"])
            return priorities

        except grpc.RpcError as e:
            logger.error("get_strategic_priorities_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("get_strategic_priorities_failed", error=str(e))
            return None
