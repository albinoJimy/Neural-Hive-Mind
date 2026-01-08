"""Service Registry gRPC client for Queen Agent com suporte a mTLS via SPIFFE."""
import structlog
from typing import List, Dict, Any, Optional, Tuple
import grpc

from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

from ..config import Settings

# Importar SPIFFE/mTLS se disponível
try:
    from neural_hive_security import (
        SPIFFEManager,
        SPIFFEConfig,
        create_secure_grpc_channel,
        get_grpc_metadata_with_jwt,
    )
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None
    SPIFFEConfig = None


logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente gRPC para Service Registry com suporte a mTLS via SPIFFE."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.grpc_host = settings.SERVICE_REGISTRY_GRPC_HOST
        self.grpc_port = settings.SERVICE_REGISTRY_GRPC_PORT
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def initialize(self) -> None:
        """Inicializar cliente gRPC com suporte a mTLS."""
        try:
            target = f"{self.grpc_host}:{self.grpc_port}"

            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_enabled = getattr(self.settings, 'SPIFFE_ENABLED', False)
            spiffe_enable_x509 = getattr(self.settings, 'SPIFFE_ENABLE_X509', False)
            environment = getattr(self.settings, 'ENVIRONMENT', 'development')

            spiffe_x509_enabled = (
                spiffe_enabled
                and spiffe_enable_x509
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar configuração SPIFFE
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=getattr(self.settings, 'SPIFFE_SOCKET_PATH', 'unix:///run/spire/sockets/agent.sock'),
                    trust_domain=getattr(self.settings, 'SPIFFE_TRUST_DOMAIN', 'neural-hive.local'),
                    jwt_audience=getattr(self.settings, 'SPIFFE_JWT_AUDIENCE', 'neural-hive.local'),
                    jwt_ttl_seconds=getattr(self.settings, 'SPIFFE_JWT_TTL_SECONDS', 3600),
                    enable_x509=True,
                    environment=environment
                )

                # Criar SPIFFE manager
                self.spiffe_manager = SPIFFEManager(spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                # Permitir fallback inseguro apenas em ambientes de desenvolvimento
                is_dev_env = environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                logger.info('mtls_channel_configured', target=target, environment=environment)
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {environment} but SPIFFE X.509 is disabled."
                    )

                logger.warning('using_insecure_channel', target=target, environment=environment)
                self.channel = grpc.aio.insecure_channel(target)

            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            logger.info("service_registry_client_initialized", host=self.grpc_host, port=self.grpc_port)
        except Exception as e:
            logger.error("service_registry_client_init_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        spiffe_enabled = getattr(self.settings, 'SPIFFE_ENABLED', False)
        if not spiffe_enabled or not self.spiffe_manager:
            return []

        try:
            trust_domain = getattr(self.settings, 'SPIFFE_TRUST_DOMAIN', 'neural-hive.local')
            environment = getattr(self.settings, 'ENVIRONMENT', 'development')
            audience = f"service-registry.{trust_domain}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=environment
            )
        except Exception as e:
            logger.warning('jwt_svid_fetch_failed', error=str(e))
            environment = getattr(self.settings, 'ENVIRONMENT', 'development')
            if environment in ['production', 'staging', 'prod']:
                raise
            return []

    async def close(self) -> None:
        """Fechar canal gRPC e SPIFFE manager"""
        if self.channel:
            await self.channel.close()

        # Fechar SPIFFE manager
        if self.spiffe_manager:
            await self.spiffe_manager.close()
            self.spiffe_manager = None

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

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.DiscoverAgents(request, metadata=grpc_metadata)

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

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.ListAgents(request, metadata=grpc_metadata)

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
