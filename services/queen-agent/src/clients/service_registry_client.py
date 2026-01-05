"""Service Registry gRPC client for Queen Agent"""
import structlog
from typing import List, Dict, Any, Optional
import grpc

from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

from ..config import Settings


logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente gRPC para Service Registry"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.grpc_host = settings.SERVICE_REGISTRY_GRPC_HOST
        self.grpc_port = settings.SERVICE_REGISTRY_GRPC_PORT
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None

    async def initialize(self) -> None:
        """Inicializar cliente gRPC"""
        try:
            target = f"{self.grpc_host}:{self.grpc_port}"
            self.channel = grpc.aio.insecure_channel(target)
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            logger.info("service_registry_client_initialized", host=self.grpc_host, port=self.grpc_port)
        except Exception as e:
            logger.error("service_registry_client_init_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fechar canal gRPC"""
        if self.channel:
            await self.channel.close()
        logger.info("service_registry_client_closed")

    async def discover_agents(
        self,
        capabilities: List[str],
        filters: Dict[str, Any],
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Descobrir agentes com capabilities especificas"""
        try:
            if not self.stub:
                logger.warning("discover_agents_called_without_connection")
                return []

            request = service_registry_pb2.DiscoverRequest(
                capabilities=capabilities,
                filters={k: str(v) for k, v in filters.items()},
                max_results=max_results
            )

            response = await self.stub.DiscoverAgents(request)

            agents = []
            for agent in response.agents:
                if agent.status == service_registry_pb2.HEALTHY:
                    agents.append({
                        'agent_id': agent.agent_id,
                        'agent_type': self._agent_type_to_string(agent.agent_type),
                        'capabilities': list(agent.capabilities),
                        'status': 'HEALTHY',
                        'metadata': dict(agent.metadata),
                        'namespace': agent.namespace,
                        'cluster': agent.cluster,
                        'version': agent.version
                    })

            logger.info("agent_discovery_completed", capabilities=capabilities, count=len(agents))
            return agents

        except grpc.RpcError as e:
            logger.error("discover_agents_grpc_failed", error=str(e), code=e.code())
            return []
        except Exception as e:
            logger.error("discover_agents_failed", error=str(e))
            return []

    async def get_healthy_agents(self, agent_type: str) -> List[Dict[str, Any]]:
        """Listar agentes saudaveis por tipo"""
        try:
            if not self.stub:
                logger.warning("get_healthy_agents_called_without_connection")
                return []

            agent_type_map = {
                'WORKER': service_registry_pb2.WORKER,
                'SCOUT': service_registry_pb2.SCOUT,
                'GUARD': service_registry_pb2.GUARD,
            }

            request = service_registry_pb2.ListAgentsRequest(
                agent_type=agent_type_map.get(agent_type.upper(), service_registry_pb2.AGENT_TYPE_UNSPECIFIED),
                filters={'status': 'healthy'}
            )

            response = await self.stub.ListAgents(request)

            agents = []
            for agent in response.agents:
                if agent.status == service_registry_pb2.HEALTHY:
                    agents.append({
                        'agent_id': agent.agent_id,
                        'agent_type': self._agent_type_to_string(agent.agent_type),
                        'capabilities': list(agent.capabilities),
                        'status': 'HEALTHY',
                        'metadata': dict(agent.metadata),
                        'telemetry': {
                            'success_rate': agent.telemetry.success_rate if agent.telemetry else 0.0,
                            'avg_duration_ms': agent.telemetry.avg_duration_ms if agent.telemetry else 0,
                            'total_executions': agent.telemetry.total_executions if agent.telemetry else 0,
                        }
                    })

            logger.info("healthy_agents_retrieved", agent_type=agent_type, count=len(agents))
            return agents

        except grpc.RpcError as e:
            logger.error("get_healthy_agents_grpc_failed", error=str(e), code=e.code())
            return []
        except Exception as e:
            logger.error("get_healthy_agents_failed", error=str(e))
            return []

    def _agent_type_to_string(self, agent_type: int) -> str:
        """Converter enum AgentType para string."""
        type_map = {
            service_registry_pb2.WORKER: 'WORKER',
            service_registry_pb2.SCOUT: 'SCOUT',
            service_registry_pb2.GUARD: 'GUARD',
        }
        return type_map.get(agent_type, 'UNKNOWN')
