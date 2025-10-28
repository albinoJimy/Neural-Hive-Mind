"""
Service Registry client for agent discovery and health management.
"""

import grpc
import structlog
import sys
import os
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel
from prometheus_client import Counter, Histogram

# Importar stubs gRPC gerados
proto_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'services', 'service-registry', 'src', 'proto')
if proto_path not in sys.path:
    sys.path.insert(0, proto_path)

try:
    import service_registry_pb2
    import service_registry_pb2_grpc
except ImportError as e:
    raise ImportError(f"Failed to import gRPC stubs. Ensure proto files are compiled: {e}")

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

# Metrics
registry_calls = Counter(
    "neural_hive_service_registry_calls_total",
    "Total Service Registry calls",
    ["operation", "status"],
)
registry_latency = Histogram(
    "neural_hive_service_registry_latency_seconds",
    "Service Registry call latency",
    ["operation"],
)


class AgentInfo(BaseModel):
    """Agent registration information."""
    agent_id: str
    agent_type: str
    capabilities: List[str]
    endpoint: str
    metadata: Dict[str, Any] = {}


class HealthStatus(BaseModel):
    """Agent health status."""
    status: str  # healthy, degraded, unhealthy
    last_heartbeat: str
    metrics: Dict[str, float] = {}


class ServiceRegistryClient:
    """Client for Service Registry gRPC service."""

    def __init__(
        self,
        host: str = "service-registry.neural-hive-orchestration",
        port: int = 50051,
    ):
        self.host = host
        self.port = port
        self.logger = logger.bind(service="service_registry_client")
        self.address = f"{host}:{port}"
        self.channel = grpc.aio.insecure_channel(self.address)
        self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

    async def close(self):
        """Close gRPC channel."""
        if self.channel:
            await self.channel.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("service_registry.register_agent")
    async def register_agent(self, agent_info: AgentInfo) -> bool:
        """
        Register agent in Service Registry.

        Args:
            agent_info: Agent registration data

        Returns:
            True if registered successfully
        """
        with registry_latency.labels(operation="register").time():
            self.logger.info(
                "registering_agent",
                agent_id=agent_info.agent_id,
                agent_type=agent_info.agent_type,
            )

            try:
                # Mapear agent_type string para enum
                agent_type_map = {
                    'worker': service_registry_pb2.WORKER,
                    'scout': service_registry_pb2.SCOUT,
                    'guard': service_registry_pb2.GUARD,
                }
                agent_type_enum = agent_type_map.get(
                    agent_info.agent_type.lower(),
                    service_registry_pb2.AGENT_TYPE_UNSPECIFIED
                )

                request = service_registry_pb2.RegisterRequest(
                    agent_type=agent_type_enum,
                    capabilities=agent_info.capabilities,
                    metadata=agent_info.metadata,
                    namespace=agent_info.metadata.get('namespace', 'default'),
                    cluster=agent_info.metadata.get('cluster', 'default'),
                    version=agent_info.metadata.get('version', '1.0.0'),
                )

                response = await self.stub.Register(request)

                # Atualizar agent_id com o ID retornado pelo registry
                agent_info.agent_id = response.agent_id

                self.logger.info(
                    "agent_registered",
                    agent_id=response.agent_id,
                    registered_at=response.registered_at,
                )

                registry_calls.labels(operation="register", status="success").inc()
                return True
            except grpc.RpcError as e:
                registry_calls.labels(operation="register", status="error").inc()
                self.logger.error(
                    "register_failed",
                    error=str(e),
                    code=e.code(),
                    details=e.details(),
                )
                raise
            except Exception as e:
                registry_calls.labels(operation="register", status="error").inc()
                self.logger.error("register_failed", error=str(e))
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("service_registry.discover_agents")
    async def discover_agents(
        self,
        capabilities: List[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[AgentInfo]:
        """
        Discover agents by capabilities and filters.

        Args:
            capabilities: Required capabilities
            filters: Additional filters (e.g., health status, load)

        Returns:
            List of matching agents (filtrados por status=healthy por padrão)
        """
        with registry_latency.labels(operation="discover").time():
            self.logger.info(
                "discovering_agents",
                capabilities=capabilities,
                filters=filters,
            )

            try:
                # Preparar filtros gRPC
                grpc_filters = filters or {}

                # Por padrão, filtrar apenas agentes saudáveis
                if 'status' not in grpc_filters:
                    grpc_filters['status'] = 'healthy'

                request = service_registry_pb2.DiscoverRequest(
                    capabilities=capabilities,
                    filters=grpc_filters,
                    max_results=100,  # Limite padrão
                )

                response = await self.stub.DiscoverAgents(request)

                # Converter AgentInfo proto para nosso modelo Pydantic
                agents = []
                for agent_proto in response.agents:
                    # Filtrar apenas agentes com status HEALTHY
                    if agent_proto.status == service_registry_pb2.HEALTHY:
                        agent = AgentInfo(
                            agent_id=agent_proto.agent_id,
                            agent_type=self._agent_type_to_string(agent_proto.agent_type),
                            capabilities=list(agent_proto.capabilities),
                            endpoint=agent_proto.metadata.get('endpoint', ''),
                            metadata=dict(agent_proto.metadata),
                        )
                        agents.append(agent)

                self.logger.info(
                    "agents_discovered",
                    count=len(agents),
                    capabilities=capabilities,
                )

                registry_calls.labels(operation="discover", status="success").inc()
                return agents
            except grpc.RpcError as e:
                registry_calls.labels(operation="discover", status="error").inc()
                self.logger.error(
                    "discover_failed",
                    error=str(e),
                    code=e.code(),
                    details=e.details(),
                )
                raise
            except Exception as e:
                registry_calls.labels(operation="discover", status="error").inc()
                self.logger.error("discover_failed", error=str(e))
                raise

    def _agent_type_to_string(self, agent_type: int) -> str:
        """Converter enum AgentType para string."""
        type_map = {
            service_registry_pb2.WORKER: 'worker',
            service_registry_pb2.SCOUT: 'scout',
            service_registry_pb2.GUARD: 'guard',
        }
        return type_map.get(agent_type, 'unknown')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("service_registry.update_health")
    async def update_health(
        self,
        agent_id: str,
        health_status: HealthStatus,
    ) -> None:
        """
        Update agent health status via Heartbeat.

        Args:
            agent_id: Agent identifier
            health_status: Current health status
        """
        with registry_latency.labels(operation="health_update").time():
            try:
                # Criar telemetria a partir das métricas
                telemetry = service_registry_pb2.AgentTelemetry(
                    success_rate=health_status.metrics.get('success_rate', 0.0),
                    avg_duration_ms=int(health_status.metrics.get('avg_duration_ms', 0)),
                    total_executions=int(health_status.metrics.get('total_executions', 0)),
                    failed_executions=int(health_status.metrics.get('failed_executions', 0)),
                    last_execution_at=int(health_status.metrics.get('last_execution_at', 0)),
                )

                request = service_registry_pb2.HeartbeatRequest(
                    agent_id=agent_id,
                    telemetry=telemetry,
                )

                response = await self.stub.Heartbeat(request)

                self.logger.debug(
                    "health_updated",
                    agent_id=agent_id,
                    status=response.status,
                    last_seen=response.last_seen,
                )

                registry_calls.labels(operation="health_update", status="success").inc()
            except grpc.RpcError as e:
                registry_calls.labels(operation="health_update", status="error").inc()
                self.logger.error(
                    "health_update_failed",
                    agent_id=agent_id,
                    error=str(e),
                    code=e.code(),
                    details=e.details(),
                )
                raise
            except Exception as e:
                registry_calls.labels(operation="health_update", status="error").inc()
                self.logger.error("health_update_failed", error=str(e))
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("service_registry.deregister_agent")
    async def deregister_agent(self, agent_id: str) -> None:
        """
        Deregister agent from Service Registry.

        Args:
            agent_id: Agent identifier
        """
        with registry_latency.labels(operation="deregister").time():
            self.logger.info("deregistering_agent", agent_id=agent_id)

            try:
                request = service_registry_pb2.DeregisterRequest(
                    agent_id=agent_id,
                )

                response = await self.stub.Deregister(request)

                if response.success:
                    self.logger.info("agent_deregistered", agent_id=agent_id)
                else:
                    self.logger.warning("deregister_not_successful", agent_id=agent_id)

                registry_calls.labels(operation="deregister", status="success").inc()
            except grpc.RpcError as e:
                registry_calls.labels(operation="deregister", status="error").inc()
                self.logger.error(
                    "deregister_failed",
                    agent_id=agent_id,
                    error=str(e),
                    code=e.code(),
                    details=e.details(),
                )
                raise
            except Exception as e:
                registry_calls.labels(operation="deregister", status="error").inc()
                self.logger.error("deregister_failed", error=str(e))
                raise
