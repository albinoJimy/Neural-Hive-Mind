from typing import Dict, List, Optional

import grpc
import structlog

from neural_hive_observability import instrument_grpc_channel
from src.config.settings import get_settings

logger = structlog.get_logger()


class ServiceRegistryClient:
    """
    Cliente gRPC para Service Registry.

    Responsável por registro e descoberta de serviços.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.agent_id: Optional[str] = None

    async def connect(self):
        """Estabelecer canal gRPC com Service Registry."""
        try:
            self.channel = grpc.aio.insecure_channel(
                self.settings.service_registry_endpoint,
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                ],
            )
            self.channel = instrument_grpc_channel(self.channel, service_name='service-registry')

            # TODO: Criar stub quando proto estendido for compilado
            # from service_registry_pb2_grpc import ServiceRegistryStub
            # self.stub = ServiceRegistryStub(self.channel)

            await self.channel.channel_ready()

            logger.info("service_registry_grpc_connected", endpoint=self.settings.service_registry_endpoint)
        except Exception as e:
            logger.error("service_registry_grpc_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Fechar canal gRPC."""
        if self.channel:
            # Deregistrar antes de desconectar
            if self.agent_id:
                await self.deregister()

            await self.channel.close()
            logger.info("service_registry_grpc_disconnected")

    async def register(self, capabilities: List[str], metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Registrar Optimizer Agent no Service Registry.

        Args:
            capabilities: Lista de capacidades
            metadata: Metadados adicionais

        Returns:
            Agent ID ou None se falhou
        """
        try:
            # TODO: Implementar quando proto estendido
            # request = RegisterAgentRequest(
            #     agent_type="OPTIMIZER",
            #     capabilities=capabilities,
            #     metadata=metadata or {}
            # )
            # response = await self.stub.RegisterAgent(request, timeout=self.settings.grpc_timeout)
            # self.agent_id = response.agent_id

            # Stub temporário
            logger.warning("register_stub_called", capabilities=capabilities)

            self.agent_id = "optimizer-agent-001"

            logger.info("agent_registered", agent_id=self.agent_id, capabilities=capabilities)
            return self.agent_id

        except grpc.RpcError as e:
            logger.error("register_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("register_failed", error=str(e))
            return None

    async def deregister(self) -> bool:
        """
        Deregistrar Optimizer Agent do Service Registry.

        Returns:
            True se bem-sucedido
        """
        try:
            if not self.agent_id:
                logger.warning("deregister_called_without_agent_id")
                return False

            # TODO: Implementar quando proto estendido
            # request = DeregisterAgentRequest(agent_id=self.agent_id)
            # response = await self.stub.DeregisterAgent(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("deregister_stub_called", agent_id=self.agent_id)

            logger.info("agent_deregistered", agent_id=self.agent_id)
            self.agent_id = None
            return True

        except grpc.RpcError as e:
            logger.error("deregister_failed", agent_id=self.agent_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("deregister_failed", agent_id=self.agent_id, error=str(e))
            return False

    async def heartbeat(self, health_status: str = "HEALTHY", metrics: Optional[Dict] = None) -> bool:
        """
        Enviar heartbeat ao Service Registry.

        Args:
            health_status: Status de saúde
            metrics: Métricas atuais

        Returns:
            True se bem-sucedido
        """
        try:
            if not self.agent_id:
                logger.warning("heartbeat_called_without_agent_id")
                return False

            # TODO: Implementar quando proto estendido
            # request = HeartbeatRequest(
            #     agent_id=self.agent_id,
            #     health_status=health_status,
            #     metrics=metrics or {}
            # )
            # response = await self.stub.Heartbeat(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.debug("heartbeat_stub_called", agent_id=self.agent_id, health_status=health_status)

            return True

        except grpc.RpcError as e:
            logger.error("heartbeat_failed", agent_id=self.agent_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("heartbeat_failed", agent_id=self.agent_id, error=str(e))
            return False

    async def discover_agents(self, capabilities: List[str], filters: Optional[Dict] = None) -> Optional[List[Dict]]:
        """
        Descobrir agentes com capacidades específicas.

        Args:
            capabilities: Capacidades requeridas
            filters: Filtros adicionais

        Returns:
            Lista de agentes ou None se falhou
        """
        try:
            # TODO: Implementar quando proto estendido
            # request = DiscoverAgentsRequest(
            #     capabilities=capabilities,
            #     filters=filters or {}
            # )
            # response = await self.stub.DiscoverAgents(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("discover_agents_stub_called", capabilities=capabilities)

            # Retornar lista simulada
            agents = [
                {
                    "agent_id": "analyst-001",
                    "agent_type": "ANALYST",
                    "capabilities": ["causal_analysis", "anomaly_detection"],
                    "health_status": "HEALTHY",
                    "composite_score": 0.95,
                },
                {
                    "agent_id": "consensus-001",
                    "agent_type": "CONSENSUS",
                    "capabilities": ["decision_making", "weight_calibration"],
                    "health_status": "HEALTHY",
                    "composite_score": 0.88,
                },
            ]

            logger.info("agents_discovered", count=len(agents), capabilities=capabilities)
            return agents

        except grpc.RpcError as e:
            logger.error("discover_agents_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("discover_agents_failed", error=str(e))
            return None

    async def update_health_status(self, health_status: str, metrics: Optional[Dict] = None) -> bool:
        """
        Atualizar status de saúde.

        Args:
            health_status: Novo status de saúde
            metrics: Métricas atualizadas

        Returns:
            True se bem-sucedido
        """
        try:
            if not self.agent_id:
                logger.warning("update_health_status_called_without_agent_id")
                return False

            # TODO: Implementar quando proto estendido
            # request = UpdateHealthStatusRequest(
            #     agent_id=self.agent_id,
            #     health_status=health_status,
            #     metrics=metrics or {}
            # )
            # response = await self.stub.UpdateHealthStatus(request, timeout=self.settings.grpc_timeout)

            # Stub temporário
            logger.warning("update_health_status_stub_called", agent_id=self.agent_id, health_status=health_status)

            logger.info("health_status_updated", agent_id=self.agent_id, health_status=health_status)
            return True

        except grpc.RpcError as e:
            logger.error("update_health_status_failed", agent_id=self.agent_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("update_health_status_failed", agent_id=self.agent_id, error=str(e))
            return False
