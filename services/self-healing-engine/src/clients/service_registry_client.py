from typing import Dict, Optional
import structlog

try:
    import grpc  # type: ignore
    from src.proto import service_registry_pb2, service_registry_pb2_grpc  # type: ignore
except Exception:  # noqa: BLE001 - gRPC/protos podem não estar disponíveis no ambiente local
    grpc = None
    service_registry_pb2 = None
    service_registry_pb2_grpc = None

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente gRPC do Service Registry (fail-open)."""

    def __init__(self, host: str, port: int, timeout_seconds: int = 3):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.channel = None
        self.stub = None

    async def initialize(self):
        """Inicializa canal gRPC (fail-open se gRPC não disponível)."""
        if grpc is None or service_registry_pb2_grpc is None:
            logger.warning("service_registry_client.grpc_not_available")
            return

        target = f"{self.host}:{self.port}"
        self.channel = grpc.aio.insecure_channel(target)
        self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
        logger.info("service_registry_client.initialized", target=target)

    async def notify_agent(self, agent_id: str, notification: Dict) -> bool:
        """Envia notificação para agente via gRPC (best-effort)."""
        if not self.stub or service_registry_pb2 is None:
            logger.warning(
                "service_registry_client.stub_unavailable",
                agent_id=agent_id,
                notification=notification
            )
            return False

        request = service_registry_pb2.NotifyAgentRequest(
            agent_id=agent_id,
            notification_type=notification.get("notification_type", "INFO"),
            message=notification.get("message", ""),
            metadata=notification.get("metadata", {})
        )
        try:
            await self.stub.NotifyAgent(request, timeout=self.timeout_seconds)
            logger.info("service_registry_client.notify_agent_sent", agent_id=agent_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "service_registry_client.notify_agent_failed",
                agent_id=agent_id,
                error=str(exc)
            )
            return False

    async def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Obtém informações de um agente (best-effort)."""
        if not self.stub or service_registry_pb2 is None:
            logger.warning("service_registry_client.stub_unavailable", agent_id=agent_id)
            return None

        request = service_registry_pb2.GetAgentRequest(agent_id=agent_id)
        try:
            response = await self.stub.GetAgent(request, timeout=self.timeout_seconds)
            return {
                "agent_id": response.agent.agent_id,
                "status": response.agent.status,
                "capabilities": list(response.agent.capabilities),
                "metadata": dict(response.agent.metadata)
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("service_registry_client.get_agent_failed", agent_id=agent_id, error=str(exc))
            return None

    async def close(self):
        """Fecha canal gRPC (se inicializado)."""
        if self.channel:
            await self.channel.close()
            logger.info("service_registry_client.closed")
