"""Service Registry gRPC client for Self-Healing Engine (fail-open)."""
from typing import Dict, Optional
import structlog

import grpc
from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente gRPC do Service Registry (fail-open)."""

    def __init__(self, host: str, port: int, timeout_seconds: int = 3):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None

    async def initialize(self):
        """Inicializa canal gRPC."""
        try:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.aio.insecure_channel(target)
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            logger.info("service_registry_client.initialized", target=target)
        except Exception as e:
            logger.warning("service_registry_client.init_failed", error=str(e))
            # Fail-open: continuar sem Service Registry

    async def notify_agent(self, agent_id: str, notification: Dict) -> bool:
        """Envia notificacao para agente via gRPC (best-effort)."""
        if not self.stub:
            logger.warning(
                "service_registry_client.stub_unavailable",
                agent_id=agent_id,
                notification=notification
            )
            return False

        try:
            request = service_registry_pb2.NotifyAgentRequest(
                agent_id=agent_id,
                notification_type=notification.get("notification_type", "INFO"),
                message=notification.get("message", ""),
                metadata=notification.get("metadata", {})
            )
            await self.stub.NotifyAgent(request, timeout=self.timeout_seconds)
            logger.info("service_registry_client.notify_agent_sent", agent_id=agent_id)
            return True
        except grpc.RpcError as e:
            logger.warning(
                "service_registry_client.notify_agent_grpc_failed",
                agent_id=agent_id,
                error=str(e),
                code=e.code()
            )
            return False
        except Exception as e:
            logger.warning(
                "service_registry_client.notify_agent_failed",
                agent_id=agent_id,
                error=str(e)
            )
            return False

    async def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Obtem informacoes de um agente (best-effort)."""
        if not self.stub:
            logger.warning("service_registry_client.stub_unavailable", agent_id=agent_id)
            return None

        try:
            request = service_registry_pb2.GetAgentRequest(agent_id=agent_id)
            response = await self.stub.GetAgent(request, timeout=self.timeout_seconds)

            # Converter AgentStatus enum para string
            status_map = {
                service_registry_pb2.AGENT_STATUS_UNSPECIFIED: 'UNSPECIFIED',
                service_registry_pb2.HEALTHY: 'HEALTHY',
                service_registry_pb2.UNHEALTHY: 'UNHEALTHY',
                service_registry_pb2.DEGRADED: 'DEGRADED'
            }

            return {
                "agent_id": response.agent.agent_id,
                "status": status_map.get(response.agent.status, 'UNKNOWN'),
                "capabilities": list(response.agent.capabilities),
                "metadata": dict(response.agent.metadata),
                "namespace": response.agent.namespace,
                "cluster": response.agent.cluster,
                "version": response.agent.version,
                "telemetry": {
                    "success_rate": response.agent.telemetry.success_rate if response.agent.telemetry else 0.0,
                    "avg_duration_ms": response.agent.telemetry.avg_duration_ms if response.agent.telemetry else 0,
                    "total_executions": response.agent.telemetry.total_executions if response.agent.telemetry else 0,
                }
            }
        except grpc.RpcError as e:
            logger.warning(
                "service_registry_client.get_agent_grpc_failed",
                agent_id=agent_id,
                error=str(e),
                code=e.code()
            )
            return None
        except Exception as e:
            logger.warning("service_registry_client.get_agent_failed", agent_id=agent_id, error=str(e))
            return None

    async def close(self):
        """Fecha canal gRPC (se inicializado)."""
        if self.channel:
            await self.channel.close()
            logger.info("service_registry_client.closed")
