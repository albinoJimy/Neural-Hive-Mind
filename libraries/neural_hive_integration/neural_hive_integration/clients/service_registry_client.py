"""
Service Registry client for agent discovery and health management.

This client uses pre-compiled proto stubs bundled with the neural_hive_integration
library, ensuring consistent imports across all services.

Suporta mTLS via SPIFFE/SPIRE para comunicação segura em produção.
"""

import grpc
import json
import hashlib
import structlog
from typing import List, Dict, Any, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge

# Redis para cache (opcional)
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

# Import gRPC stubs from bundled proto_stubs package
# This ensures consistent imports regardless of deployment context
from neural_hive_integration.proto_stubs import (
    service_registry_pb2,
    service_registry_pb2_grpc,
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
registry_cache_hits = Counter(
    "neural_hive_service_registry_cache_hits_total",
    "Service Registry cache hits",
)
registry_cache_misses = Counter(
    "neural_hive_service_registry_cache_misses_total",
    "Service Registry cache misses",
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
    """Client for Service Registry gRPC service com suporte a mTLS via SPIFFE."""

    def __init__(
        self,
        host: str = "service-registry.neural-hive.svc.cluster.local",
        port: int = 50051,
        spiffe_enabled: bool = False,
        spiffe_config: Optional[Any] = None,
        environment: str = "development",
        redis_url: Optional[str] = None,
        cache_ttl: int = 60,
    ):
        """
        Inicializa o cliente do Service Registry.

        Args:
            host: Hostname do Service Registry
            port: Porta gRPC do Service Registry
            spiffe_enabled: Habilitar mTLS via SPIFFE
            spiffe_config: Configuração SPIFFE (SPIFFEConfig)
            environment: Ambiente de execução (development, staging, production)
            redis_url: URL do Redis para cache (opcional)
            cache_ttl: TTL do cache em segundos (default: 60s)
        """
        self.host = host
        self.port = port
        self.logger = logger.bind(service="service_registry_client")
        self.address = f"{host}:{port}"
        self.spiffe_enabled = spiffe_enabled
        self.spiffe_config = spiffe_config
        self.environment = environment
        self.channel = None
        self.stub = None
        self.spiffe_manager = None
        self._initialized = False
        
        # Cache Redis (opcional)
        self.redis_url = redis_url
        self.cache_ttl = cache_ttl
        self.redis: Optional[Any] = None

    async def initialize(self):
        """Inicializar conexão gRPC com suporte a mTLS via SPIFFE."""
        if self._initialized:
            return

        try:
            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_x509_enabled = (
                self.spiffe_enabled
                and self.spiffe_config
                and getattr(self.spiffe_config, 'enable_x509', False)
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar canal seguro com mTLS via helper function
                self.spiffe_manager = SPIFFEManager(self.spiffe_config)
                await self.spiffe_manager.initialize()

                # Permitir fallback inseguro apenas em ambientes de desenvolvimento
                is_dev_env = self.environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=self.address,
                    spiffe_config=self.spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                self.logger.info(
                    'mtls_channel_configured',
                    target=self.address,
                    environment=self.environment
                )
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.environment} but SPIFFE X.509 is disabled. "
                        "Set spiffe_enabled=True and configure spiffe_config with enable_x509=True."
                    )

                self.logger.warning(
                    'using_insecure_channel',
                    target=self.address,
                    environment=self.environment,
                    warning='mTLS disabled - not for production use'
                )
                self.channel = grpc.aio.insecure_channel(self.address)

            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            self._initialized = True

            # Inicializar Redis cache se configurado
            if self.redis_url and REDIS_AVAILABLE:
                try:
                    self.redis = await aioredis.from_url(
                        self.redis_url,
                        decode_responses=True
                    )
                    await self.redis.ping()
                    self.logger.info('redis_cache_initialized', redis_url=self.redis_url)
                except Exception as redis_error:
                    self.logger.warning(
                        'redis_cache_init_failed',
                        error=str(redis_error),
                        message='Continuando sem cache'
                    )
                    self.redis = None

            self.logger.info('service_registry_client_initialized', target=self.address)

        except Exception as e:
            self.logger.error('service_registry_client_init_failed', error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """
        Obter metadata gRPC com JWT-SVID para autenticação.

        Returns:
            Lista de tuplas (key, value) para metadata gRPC
        """
        if not self.spiffe_enabled or not self.spiffe_manager:
            return []

        try:
            audience = f"service-registry.{self.spiffe_config.trust_domain}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=self.environment
            )
        except Exception as e:
            self.logger.warning('jwt_svid_fetch_failed', error=str(e))
            if self.environment in ['production', 'staging', 'prod']:
                raise
            return []

    async def _ensure_initialized(self):
        """Garantir que o cliente foi inicializado."""
        if not self._initialized:
            await self.initialize()

    async def close(self):
        """Close gRPC channel and SPIFFE manager."""
        if self.spiffe_manager:
            await self.spiffe_manager.close()
        if self.channel:
            await self.channel.close()
        self._initialized = False

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
        await self._ensure_initialized()

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
                    'analyst': service_registry_pb2.ANALYST if hasattr(service_registry_pb2, 'ANALYST') else service_registry_pb2.WORKER,
                    'specialist': service_registry_pb2.SPECIALIST if hasattr(service_registry_pb2, 'SPECIALIST') else service_registry_pb2.WORKER,
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

                # Obter metadata com JWT-SVID
                metadata = await self._get_grpc_metadata()

                response = await self.stub.Register(request, metadata=metadata)

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
        await self._ensure_initialized()

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

                # Obter metadata com JWT-SVID
                metadata = await self._get_grpc_metadata()

                response = await self.stub.DiscoverAgents(request, metadata=metadata)

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

    async def discover_agents_cached(
        self,
        capabilities: List[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[AgentInfo]:
        """
        Discover agents with Redis caching layer.

        Tenta obter do cache primeiro. Em caso de miss, chama o gRPC
        e armazena o resultado no cache.

        Args:
            capabilities: Required capabilities
            filters: Additional filters

        Returns:
            List of matching agents
        """
        # Gerar cache key baseada em capabilities e filters
        cache_key = self._generate_cache_key(capabilities, filters)

        # Tentar obter do cache
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    registry_cache_hits.inc()
                    self.logger.debug(
                        "discovery_cache_hit",
                        cache_key=cache_key,
                        capabilities=capabilities,
                    )
                    agents_data = json.loads(cached_data)
                    return [AgentInfo(**agent) for agent in agents_data]
            except Exception as cache_error:
                self.logger.warning(
                    "cache_read_failed",
                    error=str(cache_error),
                    cache_key=cache_key,
                )

        # Cache miss - chamar gRPC
        registry_cache_misses.inc()
        agents = await self.discover_agents(capabilities, filters)

        # Armazenar no cache
        if self.redis and agents:
            try:
                agents_data = [agent.model_dump() for agent in agents]
                await self.redis.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(agents_data)
                )
                self.logger.debug(
                    "discovery_cached",
                    cache_key=cache_key,
                    agents_count=len(agents),
                    ttl=self.cache_ttl,
                )
            except Exception as cache_error:
                self.logger.warning(
                    "cache_write_failed",
                    error=str(cache_error),
                    cache_key=cache_key,
                )

        return agents

    def _generate_cache_key(
        self,
        capabilities: List[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Gerar cache key determinística para discovery."""
        key_data = {
            "capabilities": sorted(capabilities),
            "filters": filters or {},
        }
        key_str = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.md5(key_str.encode()).hexdigest()[:16]
        return f"discovery:{key_hash}"

    def _agent_type_to_string(self, agent_type: int) -> str:
        """Converter enum AgentType para string."""
        type_map = {
            service_registry_pb2.WORKER: 'worker',
            service_registry_pb2.SCOUT: 'scout',
            service_registry_pb2.GUARD: 'guard',
        }
        # Adicionar ANALYST se disponível no proto
        if hasattr(service_registry_pb2, 'ANALYST'):
            type_map[service_registry_pb2.ANALYST] = 'analyst'
        # Adicionar SPECIALIST se disponível no proto
        if hasattr(service_registry_pb2, 'SPECIALIST'):
            type_map[service_registry_pb2.SPECIALIST] = 'specialist'
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
        await self._ensure_initialized()

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

                # Obter metadata com JWT-SVID
                metadata = await self._get_grpc_metadata()

                response = await self.stub.Heartbeat(request, metadata=metadata)

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
        await self._ensure_initialized()

        with registry_latency.labels(operation="deregister").time():
            self.logger.info("deregistering_agent", agent_id=agent_id)

            try:
                request = service_registry_pb2.DeregisterRequest(
                    agent_id=agent_id,
                )

                # Obter metadata com JWT-SVID
                metadata = await self._get_grpc_metadata()

                response = await self.stub.Deregister(request, metadata=metadata)

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
