"""Service Registry gRPC client for Guard Agents com suporte a mTLS via SPIFFE."""
import asyncio
import time
from typing import List, Optional, Tuple
import grpc
import structlog
from datetime import datetime
from prometheus_client import Counter, Histogram

from neural_hive_integration.proto_stubs import (
    service_registry_pb2,
    service_registry_pb2_grpc
)

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


# Metricas Prometheus para discovery
discovery_requests_total = Counter(
    'guard_agent_discovery_requests_total',
    'Total de requisicoes de descoberta feitas pelo Guard Agent',
    ['status']
)

discovery_agents_found = Histogram(
    'guard_agent_discovery_agents_found',
    'Numero de agentes encontrados por requisicao de descoberta',
    buckets=[0, 1, 2, 5, 10, 20, 50, 100]
)

discovery_duration_seconds = Histogram(
    'guard_agent_discovery_duration_seconds',
    'Duracao das requisicoes de descoberta em segundos',
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)


class ServiceRegistryClient:
    """Cliente para comunicacao com Service Registry com suporte a mTLS via SPIFFE."""

    def __init__(
        self,
        host: str,
        port: int,
        agent_type: str = "GUARD",
        capabilities: list[str] = None,
        metadata: dict[str, str] = None,
        heartbeat_interval: int = 30,
        spiffe_enabled: bool = False,
        spiffe_config: Optional[SPIFFEConfig] = None,
        environment: str = "development",
    ):
        self.host = host
        self.port = port
        self.agent_type = agent_type
        self.capabilities = capabilities or []
        self.metadata = metadata or {}
        self.heartbeat_interval = heartbeat_interval
        self.spiffe_enabled = spiffe_enabled
        self.spiffe_config = spiffe_config
        self.environment = environment

        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.agent_id: Optional[str] = None
        self.registration_token: Optional[str] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def connect(self):
        """Conecta ao Service Registry com suporte a mTLS."""
        try:
            target = f"{self.host}:{self.port}"

            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_x509_enabled = (
                self.spiffe_enabled
                and self.spiffe_config
                and getattr(self.spiffe_config, 'enable_x509', False)
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar SPIFFE manager
                self.spiffe_manager = SPIFFEManager(self.spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=self.spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=(self.environment == 'dev')
                )

                logger.info('mtls_channel_configured', target=target, environment=self.environment)
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.environment} but SPIFFE X.509 is disabled."
                    )

                logger.warning('using_insecure_channel', target=target, environment=self.environment)
                self.channel = grpc.aio.insecure_channel(target)

            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            logger.info("service_registry.connected", host=self.host, port=self.port)
        except Exception as e:
            logger.error("service_registry.connection_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        if not self.spiffe_enabled or not self.spiffe_manager:
            return []

        try:
            trust_domain = self.spiffe_config.trust_domain if self.spiffe_config else "neural-hive.local"
            audience = f"service-registry.{trust_domain}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=self.environment
            )
        except Exception as e:
            logger.warning('jwt_svid_fetch_failed', error=str(e))
            if self.environment in ['production', 'staging', 'prod']:
                raise
            return []

    async def register(self) -> str:
        """Registra agente no Service Registry"""
        try:
            agent_type_map = {
                "GUARD": service_registry_pb2.GUARD,
                "WORKER": service_registry_pb2.WORKER,
                "SCOUT": service_registry_pb2.SCOUT,
            }

            request = service_registry_pb2.RegisterRequest(
                agent_type=agent_type_map.get(self.agent_type, service_registry_pb2.GUARD),
                capabilities=self.capabilities,
                metadata=self.metadata,
                namespace=self.metadata.get('namespace', 'default'),
                cluster=self.metadata.get('cluster', 'default'),
                version=self.metadata.get('version', '1.0.0')
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Register(request, metadata=grpc_metadata)
            self.agent_id = response.agent_id
            self.registration_token = response.registration_token

            logger.info("service_registry.registered", agent_id=self.agent_id)
            return self.agent_id
        except grpc.RpcError as e:
            logger.error("service_registry.registration_failed", error=str(e), code=e.code())
            raise
        except Exception as e:
            logger.error("service_registry.registration_failed", error=str(e))
            raise

    async def start_heartbeat(self):
        """Inicia envio periodico de heartbeats"""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("service_registry.heartbeat_started", interval=self.heartbeat_interval)

    async def _heartbeat_loop(self):
        """Loop de heartbeat"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                telemetry = service_registry_pb2.AgentTelemetry(
                    success_rate=0.95,
                    avg_duration_ms=100,
                    total_executions=0,
                    failed_executions=0,
                )

                request = service_registry_pb2.HeartbeatRequest(
                    agent_id=self.agent_id,
                    telemetry=telemetry,
                )

                # Obter metadata com JWT-SVID
                grpc_metadata = await self._get_grpc_metadata()

                response = await self.stub.Heartbeat(request, metadata=grpc_metadata)
                logger.debug(
                    "service_registry.heartbeat_sent",
                    agent_id=self.agent_id,
                    status=response.status
                )
            except grpc.RpcError as e:
                logger.error("service_registry.heartbeat_failed", error=str(e), code=e.code())
            except Exception as e:
                logger.error("service_registry.heartbeat_failed", error=str(e))

    async def deregister(self):
        """Desregistra agente do Service Registry"""
        try:
            if self.agent_id and self.stub:
                request = service_registry_pb2.DeregisterRequest(agent_id=self.agent_id)

                # Obter metadata com JWT-SVID
                grpc_metadata = await self._get_grpc_metadata()

                response = await self.stub.Deregister(request, metadata=grpc_metadata)

                if response.success:
                    logger.info("service_registry.deregistered", agent_id=self.agent_id)
                else:
                    logger.warning("service_registry.deregister_failed", agent_id=self.agent_id)
        except grpc.RpcError as e:
            logger.error("service_registry.deregister_failed", error=str(e), code=e.code())
        except Exception as e:
            logger.error("service_registry.deregister_failed", error=str(e))

    async def discover_agents(
        self,
        capabilities: list[str],
        filters: Optional[dict[str, str]] = None,
        max_results: int = 5
    ) -> list[dict]:
        """
        Descobre agentes baseado em capabilities

        Args:
            capabilities: Lista de capabilities requeridas
            filters: Filtros adicionais (namespace, cluster, version)
            max_results: Numero maximo de resultados

        Returns:
            Lista de agentes descobertos
        """
        start_time = time.perf_counter()

        try:
            request = service_registry_pb2.DiscoverRequest(
                capabilities=capabilities,
                filters=filters or {},
                max_results=max_results
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.DiscoverAgents(request, metadata=grpc_metadata)

            # Converter AgentInfo proto para dicionarios Python
            agents = []
            for agent_proto in response.agents:
                agent_dict = {
                    'agent_id': agent_proto.agent_id,
                    'agent_type': service_registry_pb2.AgentType.Name(agent_proto.agent_type),
                    'capabilities': list(agent_proto.capabilities),
                    'metadata': dict(agent_proto.metadata),
                    'status': service_registry_pb2.AgentStatus.Name(agent_proto.status),
                    'telemetry': {
                        'success_rate': agent_proto.telemetry.success_rate,
                        'avg_duration_ms': agent_proto.telemetry.avg_duration_ms,
                        'total_executions': agent_proto.telemetry.total_executions,
                    },
                    'namespace': agent_proto.namespace,
                    'cluster': agent_proto.cluster,
                    'version': agent_proto.version,
                }
                agents.append(agent_dict)

            # Registrar metricas de sucesso
            duration = time.perf_counter() - start_time
            discovery_duration_seconds.observe(duration)
            discovery_requests_total.labels(status='success').inc()
            discovery_agents_found.observe(len(agents))

            logger.info(
                "service_registry.agents_discovered",
                capabilities=capabilities,
                filters=filters,
                agents_found=len(agents),
                ranked=response.ranked
            )

            return agents

        except grpc.RpcError as e:
            # Registrar metricas de erro
            duration = time.perf_counter() - start_time
            discovery_duration_seconds.observe(duration)
            discovery_requests_total.labels(status='error').inc()
            discovery_agents_found.observe(0)

            logger.error(
                "service_registry.discover_failed",
                capabilities=capabilities,
                error=str(e),
                code=e.code()
            )
            return []
        except Exception as e:
            # Registrar metricas de erro
            duration = time.perf_counter() - start_time
            discovery_duration_seconds.observe(duration)
            discovery_requests_total.labels(status='error').inc()
            discovery_agents_found.observe(0)

            logger.error(
                "service_registry.discover_failed",
                capabilities=capabilities,
                error=str(e)
            )
            return []

    async def close(self):
        """Fecha conexoes, SPIFFE manager e para heartbeat"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        await self.deregister()

        if self.channel:
            await self.channel.close()

        # Fechar SPIFFE manager
        if self.spiffe_manager:
            await self.spiffe_manager.close()

        # Limpar estado apos fechar
        self.channel = None
        self.stub = None
        self.agent_id = None
        self.registration_token = None
        self.spiffe_manager = None

        logger.info("service_registry.client_closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente esta saudavel"""
        return self.channel is not None and self.agent_id is not None
