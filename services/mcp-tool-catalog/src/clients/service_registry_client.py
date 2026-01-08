"""Service Registry client for service discovery com suporte a mTLS via SPIFFE."""
import asyncio
from typing import Dict, List, Optional, Tuple
import time
import grpc
import structlog
from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

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
    """Client for Service Registry integration com suporte a mTLS via SPIFFE."""

    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout_seconds: float = 10.0,
        spiffe_enabled: bool = False,
        spiffe_config: Optional[SPIFFEConfig] = None,
        environment: str = "development",
    ):
        """Initialize Service Registry client.

        Args:
            host: Service Registry host
            port: Service Registry port
            connect_timeout_seconds: Connection/call timeout in seconds
            spiffe_enabled: Habilitar integração SPIFFE/SPIRE
            spiffe_config: Configuração SPIFFE
            environment: Ambiente (development, staging, production)
        """
        self.target = f"{host}:{port}"
        self.connect_timeout_seconds = connect_timeout_seconds
        self.spiffe_enabled = spiffe_enabled
        self.spiffe_config = spiffe_config
        self.environment = environment
        self.service_id: str = None
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def _ensure_connection(self):
        """Ensure gRPC connection is established com suporte a mTLS."""
        if not self.channel:
            # Configure channel options for connection backoff
            options = [
                ('grpc.initial_reconnect_backoff_ms', 1000),
                ('grpc.max_reconnect_backoff_ms', 10000),
                ('grpc.keepalive_time_ms', 30000),
                ('grpc.keepalive_timeout_ms', 10000),
            ]

            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_x509_enabled = (
                self.spiffe_enabled
                and self.spiffe_config
                and getattr(self.spiffe_config, 'enable_x509', False)
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar SPIFFE manager se não existir
                if not self.spiffe_manager:
                    self.spiffe_manager = SPIFFEManager(self.spiffe_config)
                    await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                # Permitir fallback inseguro apenas em ambientes de desenvolvimento
                is_dev_env = self.environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=self.target,
                    spiffe_config=self.spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                logger.info('mtls_channel_configured', target=self.target, environment=self.environment)
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.environment} but SPIFFE X.509 is disabled."
                    )

                logger.warning('using_insecure_channel', target=self.target, environment=self.environment)
                self.channel = grpc.aio.insecure_channel(self.target, options=options)

            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

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

    async def register(
        self,
        service_name: str,
        capabilities: List[str],
        metadata: Dict,
        max_retries: int = 5,
        initial_delay: float = 1.0,
    ):
        """Register service with Service Registry with retry logic.

        Args:
            service_name: Name of the service to register
            capabilities: List of service capabilities
            metadata: Service metadata
            max_retries: Maximum number of registration attempts
            initial_delay: Initial delay between retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "registering_with_service_registry",
                    target=self.target,
                    service_name=service_name,
                    attempt=attempt + 1,
                )

                await self._ensure_connection()

                request = service_registry_pb2.RegisterRequest(
                    agent_type=service_registry_pb2.WORKER,  # Usando WORKER como tipo genérico
                    capabilities=capabilities,
                    metadata=metadata,
                    namespace="production",  # Ajustar conforme ambiente se necessário
                    cluster="neural-hive",
                    version=metadata.get("version", "unknown"),
                )

                # Obter metadata com JWT-SVID
                grpc_metadata = await self._get_grpc_metadata()

                # Apply timeout to avoid blocking indefinitely
                response = await asyncio.wait_for(
                    self.stub.Register(request, metadata=grpc_metadata),
                    timeout=self.connect_timeout_seconds,
                )
                self.service_id = response.agent_id

                logger.info("service_registered", service_id=self.service_id)
                return

            except asyncio.TimeoutError:
                delay = initial_delay * (2**attempt)
                logger.warning(
                    "service_registration_timeout",
                    timeout_seconds=self.connect_timeout_seconds,
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                # Reset connection on failure
                if self.channel:
                    await self.channel.close()
                    self.channel = None
                    self.stub = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("service_registration_exhausted_retries")
                    raise

            except Exception as e:
                delay = initial_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    "service_registration_failed",
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                # Reset connection on failure
                if self.channel:
                    await self.channel.close()
                    self.channel = None
                    self.stub = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("service_registration_exhausted_retries")
                    raise

    async def send_heartbeat(self, health_data: Dict):
        """Send heartbeat to Service Registry."""
        if not self.service_id:
            return
        await self._ensure_connection()
        try:
            telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=health_data.get("success_rate", 1.0),
                avg_duration_ms=health_data.get("avg_duration_ms", 0),
                total_executions=health_data.get("total_executions", 0),
                failed_executions=health_data.get("failed_executions", 0),
                last_execution_at=int(time.time() * 1000)
            )
            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.service_id,
                telemetry=telemetry
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            # Apply timeout to heartbeat calls
            await asyncio.wait_for(
                self.stub.Heartbeat(request, metadata=grpc_metadata),
                timeout=self.connect_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "heartbeat_timeout",
                timeout_seconds=self.connect_timeout_seconds,
            )
        except Exception as e:
            logger.error("heartbeat_failed", error=str(e))

    async def deregister(self):
        """Deregister service from Service Registry."""
        if not self.service_id:
            return
        await self._ensure_connection()
        try:
            request = service_registry_pb2.DeregisterRequest(agent_id=self.service_id)

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            # Apply timeout to deregister call
            await asyncio.wait_for(
                self.stub.Deregister(request, metadata=grpc_metadata),
                timeout=self.connect_timeout_seconds,
            )
            logger.info("service_deregistered", service_id=self.service_id)
        except asyncio.TimeoutError:
            logger.warning(
                "deregister_timeout",
                timeout_seconds=self.connect_timeout_seconds,
            )
        except Exception as e:
            logger.error("deregister_failed", error=str(e))
        finally:
            if self.channel:
                await self.channel.close()
                self.channel = None

            # Fechar SPIFFE manager
            if self.spiffe_manager:
                await self.spiffe_manager.close()
                self.spiffe_manager = None
