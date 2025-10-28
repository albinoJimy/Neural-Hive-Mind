import grpc
import structlog
from uuid import UUID
from typing import Iterator
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from src.services import RegistryService, MatchingEngine
from src.models import AgentType, AgentTelemetry


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class ServiceRegistryServicer:
    """Implementação do serviço gRPC ServiceRegistry"""

    def __init__(
        self,
        registry_service: RegistryService,
        matching_engine: MatchingEngine
    ):
        self.registry_service = registry_service
        self.matching_engine = matching_engine

    async def Register(self, request, context):
        """RPC: Registrar novo agente"""
        with tracer.start_as_current_span("register_agent") as span:
            try:
                # Converter proto para tipos Python
                agent_type = AgentType(request.agent_type)
                capabilities = list(request.capabilities)
                metadata = dict(request.metadata)
                namespace = request.namespace or "default"
                cluster = request.cluster or "local"
                version = request.version or "1.0.0"

                # Validações
                if not capabilities:
                    context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "Capabilities não podem estar vazias"
                    )

                # Registrar agente
                agent_id, registration_token = await self.registry_service.register_agent(
                    agent_type=agent_type,
                    capabilities=capabilities,
                    metadata=metadata,
                    namespace=namespace,
                    cluster=cluster,
                    version=version
                )

                # Criar response
                from src.proto import service_registry_pb2
                response = service_registry_pb2.RegisterResponse(
                    agent_id=str(agent_id),
                    registration_token=registration_token,
                    registered_at=int(datetime.now(timezone.utc).timestamp())
                )

                span.set_status(Status(StatusCode.OK))
                span.set_attribute("agent_id", str(agent_id))
                span.set_attribute("agent_type", agent_type.value)

                return response

            except ValueError as e:
                logger.error("register_validation_error", error=str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

            except Exception as e:
                logger.error("register_internal_error", error=str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")

    async def Heartbeat(self, request, context):
        """RPC: Enviar heartbeat"""
        with tracer.start_as_current_span("heartbeat") as span:
            try:
                agent_id = UUID(request.agent_id)

                # Converter telemetria
                telemetry = None
                if request.HasField('telemetry'):
                    telemetry = AgentTelemetry(
                        success_rate=request.telemetry.success_rate,
                        avg_duration_ms=request.telemetry.avg_duration_ms,
                        total_executions=request.telemetry.total_executions,
                        failed_executions=request.telemetry.failed_executions,
                        last_execution_at=request.telemetry.last_execution_at or None
                    )

                # Atualizar heartbeat
                status = await self.registry_service.update_heartbeat(
                    agent_id=agent_id,
                    telemetry=telemetry
                )

                # Criar response
                from src.proto import service_registry_pb2
                from datetime import datetime, timezone
                response = service_registry_pb2.HeartbeatResponse(
                    status=status.value,
                    last_seen=int(datetime.now(timezone.utc).timestamp())
                )

                span.set_attribute("agent_id", str(agent_id))
                span.set_attribute("status", status.value)

                return response

            except ValueError as e:
                logger.error("heartbeat_validation_error", error=str(e))
                context.abort(grpc.StatusCode.NOT_FOUND, str(e))

            except Exception as e:
                logger.error("heartbeat_internal_error", error=str(e))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")

    async def Deregister(self, request, context):
        """RPC: Deregistrar agente"""
        with tracer.start_as_current_span("deregister_agent") as span:
            try:
                agent_id = UUID(request.agent_id)

                # Deregistrar
                success = await self.registry_service.deregister_agent(agent_id)

                # Criar response
                from src.proto import service_registry_pb2
                response = service_registry_pb2.DeregisterResponse(
                    success=success
                )

                span.set_attribute("agent_id", str(agent_id))
                span.set_attribute("success", success)

                return response

            except Exception as e:
                logger.error("deregister_internal_error", error=str(e))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")

    async def DiscoverAgents(self, request, context):
        """RPC: Descobrir agentes baseado em capabilities"""
        with tracer.start_as_current_span("discover_agents") as span:
            try:
                capabilities_required = list(request.capabilities)
                filters = dict(request.filters) if request.filters else None
                max_results = request.max_results or 5

                # Matching
                agents = await self.matching_engine.match_agents(
                    capabilities_required=capabilities_required,
                    filters=filters,
                    max_results=max_results
                )

                # Converter para proto
                from src.proto import service_registry_pb2
                agent_protos = []
                for agent in agents:
                    agent_dict = agent.to_proto_dict()
                    agent_proto = service_registry_pb2.AgentInfo(**agent_dict)
                    agent_protos.append(agent_proto)

                response = service_registry_pb2.DiscoverResponse(
                    agents=agent_protos,
                    ranked=True
                )

                span.set_attribute("capabilities_count", len(capabilities_required))
                span.set_attribute("agents_found", len(agents))

                return response

            except Exception as e:
                logger.error("discover_agents_error", error=str(e))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")

    async def GetAgent(self, request, context):
        """RPC: Obter informações de um agente específico"""
        with tracer.start_as_current_span("get_agent") as span:
            try:
                agent_id = UUID(request.agent_id)

                # Buscar agente
                agent = await self.registry_service.get_agent(agent_id)

                if not agent:
                    context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Agente {agent_id} não encontrado"
                    )

                # Converter para proto
                from src.proto import service_registry_pb2
                agent_dict = agent.to_proto_dict()
                agent_proto = service_registry_pb2.AgentInfo(**agent_dict)

                response = service_registry_pb2.GetAgentResponse(
                    agent=agent_proto
                )

                span.set_attribute("agent_id", str(agent_id))

                return response

            except ValueError as e:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

            except Exception as e:
                logger.error("get_agent_error", error=str(e))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")

    async def ListAgents(self, request, context):
        """RPC: Listar todos os agentes"""
        with tracer.start_as_current_span("list_agents") as span:
            try:
                agent_type = AgentType(request.agent_type) if request.agent_type else None
                filters = dict(request.filters) if request.filters else None

                # Listar agentes
                agents = await self.registry_service.list_agents(
                    agent_type=agent_type,
                    filters=filters
                )

                # Converter para proto
                from src.proto import service_registry_pb2
                agent_protos = []
                for agent in agents:
                    agent_dict = agent.to_proto_dict()
                    agent_proto = service_registry_pb2.AgentInfo(**agent_dict)
                    agent_protos.append(agent_proto)

                response = service_registry_pb2.ListAgentsResponse(
                    agents=agent_protos
                )

                span.set_attribute("agents_count", len(agents))

                return response

            except Exception as e:
                logger.error("list_agents_error", error=str(e))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")

    async def WatchAgents(self, request, context) -> Iterator:
        """RPC: Observar mudanças em agentes (server streaming)"""
        with tracer.start_as_current_span("watch_agents") as span:
            try:
                # TODO: Implementar watch usando etcd watch API
                # Por enquanto, retornar stream vazio
                logger.warning("watch_agents_not_implemented")
                return iter([])

            except Exception as e:
                logger.error("watch_agents_error", error=str(e))
                context.abort(grpc.StatusCode.INTERNAL, f"Erro interno: {str(e)}")
