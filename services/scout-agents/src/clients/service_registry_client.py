"""Cliente gRPC para Service Registry com suporte a mTLS via SPIFFE."""
from typing import Optional, Dict, List, Any, Tuple
import time
import structlog
import grpc
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import get_settings

# Usar proto_stubs da biblioteca neural_hive_integration
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
    """Cliente para registro e heartbeat no Service Registry com suporte a mTLS via SPIFFE."""

    def __init__(self, scout_agent_id: str):
        self.scout_agent_id = scout_agent_id
        self.settings = get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.agent_id: Optional[str] = None
        self._registered = False
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def start(self):
        """Inicializa conexão gRPC com Service Registry com suporte a mTLS."""
        try:
            service_registry_url = (
                f"{self.settings.service_registry.host}:"
                f"{self.settings.service_registry.port}"
            )

            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_enabled = getattr(self.settings, 'spiffe_enabled', False)
            spiffe_enable_x509 = getattr(self.settings, 'spiffe_enable_x509', False)
            environment = getattr(self.settings.service, 'environment', 'development')

            spiffe_x509_enabled = (
                spiffe_enabled
                and spiffe_enable_x509
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar configuração SPIFFE
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=getattr(self.settings, 'spiffe_socket_path', 'unix:///run/spire/sockets/agent.sock'),
                    trust_domain=getattr(self.settings, 'spiffe_trust_domain', 'neural-hive.local'),
                    jwt_audience=getattr(self.settings, 'spiffe_jwt_audience', 'neural-hive.local'),
                    jwt_ttl_seconds=getattr(self.settings, 'spiffe_jwt_ttl_seconds', 3600),
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
                    target=service_registry_url,
                    spiffe_config=spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                logger.info('mtls_channel_configured', target=service_registry_url, environment=environment)
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {environment} but SPIFFE X.509 is disabled."
                    )

                logger.warning('using_insecure_channel', target=service_registry_url, environment=environment)
                self.channel = grpc.aio.insecure_channel(service_registry_url)

            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            logger.info(
                "service_registry_client_started",
                agent_id=self.scout_agent_id,
                registry_url=service_registry_url
            )
        except Exception as e:
            logger.error("service_registry_client_start_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        spiffe_enabled = getattr(self.settings, 'spiffe_enabled', False)
        if not spiffe_enabled or not self.spiffe_manager:
            return []

        try:
            trust_domain = getattr(self.settings, 'spiffe_trust_domain', 'neural-hive.local')
            environment = getattr(self.settings.service, 'environment', 'development')
            audience = f"service-registry.{trust_domain}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=environment
            )
        except Exception as e:
            logger.warning('jwt_svid_fetch_failed', error=str(e))
            environment = getattr(self.settings.service, 'environment', 'development')
            if environment in ['production', 'staging', 'prod']:
                raise
            return []

    async def stop(self):
        """Encerra conexão gRPC e SPIFFE manager"""
        if self.channel:
            await self.channel.close()

        # Fechar SPIFFE manager
        if self.spiffe_manager:
            await self.spiffe_manager.close()
            self.spiffe_manager = None

        logger.info("service_registry_client_stopped")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def register(self) -> bool:
        """
        Registra o Scout Agent no Service Registry

        Returns:
            bool: Sucesso do registro
        """
        if not self.channel:
            logger.error("service_registry_client_not_started")
            return False

        try:
            request = service_registry_pb2.RegisterRequest(
                agent_type=service_registry_pb2.SCOUT,
                capabilities=self._build_capabilities(),
                metadata=self._build_metadata(),
                namespace=self.settings.service.environment,
                cluster="neural-hive",
                version=self.settings.service.version
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Register(request, metadata=grpc_metadata)
            self.agent_id = response.agent_id
            self._registered = True

            logger.info(
                "agent_registered",
                agent_id=self.agent_id,
                capabilities=self._build_capabilities(),
                namespace=self.settings.service.environment,
                cluster="neural-hive",
                registered_at=int(time.time())
            )

            return True

        except Exception as e:
            logger.error(
                "agent_registration_failed",
                agent_id=self.scout_agent_id,
                error=str(e)
            )
            return False

    async def heartbeat(self, telemetry: Optional[Dict[str, Any]] = None) -> bool:
        """
        Envia heartbeat para o Service Registry

        Args:
            telemetry: Dados de telemetria do agente

        Returns:
            bool: Sucesso do heartbeat
        """
        if not self.channel or not self._registered:
            logger.warning("heartbeat_skipped_not_registered")
            return False

        try:
            telemetry = telemetry or {}

            telemetry_pb = service_registry_pb2.AgentTelemetry(
                success_rate=telemetry.get('success_rate', 1.0),
                avg_duration_ms=telemetry.get('avg_duration_ms', 0),
                total_executions=telemetry.get('total_executions', 0),
                failed_executions=telemetry.get('failed_executions', 0),
                last_execution_at=int(telemetry.get('last_execution_at', time.time()) * 1000)
            )

            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.agent_id,
                telemetry=telemetry_pb
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Heartbeat(request, metadata=grpc_metadata)

            logger.debug(
                "heartbeat_sent",
                agent_id=self.agent_id,
                status=service_registry_pb2.AgentStatus.Name(response.status),
                last_seen=int(time.time())
            )

            return True

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND and 'não encontrado' in e.details():
                logger.warning(
                    'agent_not_found_in_registry',
                    agent_id=self.agent_id,
                    message='Agent expired, attempting re-registration'
                )
                self._registered = False
                try:
                    new_agent_id = await self.register()
                    if new_agent_id:
                        logger.info('agent_re_registered', new_agent_id=new_agent_id)
                        return True
                except Exception as reg_error:
                    logger.error('re_registration_failed', error=str(reg_error))
                    return False
            else:
                logger.error(
                    "heartbeat_failed",
                    agent_id=self.agent_id,
                    error=str(e)
                )
                return False
        except Exception as e:
            logger.error(
                "heartbeat_failed",
                agent_id=self.agent_id,
                error=str(e)
            )
            return False

    async def deregister(self) -> bool:
        """
        Remove o registro do Scout Agent

        Returns:
            bool: Sucesso do deregistro
        """
        if not self.channel or not self._registered:
            logger.warning("deregister_skipped_not_registered")
            return True

        try:
            request = service_registry_pb2.DeregisterRequest(
                agent_id=self.agent_id
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Deregister(request, metadata=grpc_metadata)
            self._registered = False

            logger.info(
                "agent_deregistered",
                agent_id=self.agent_id,
                success=response.success
            )

            return response.success

        except Exception as e:
            logger.error(
                "deregister_failed",
                agent_id=self.agent_id,
                error=str(e)
            )
            return False

    def _build_capabilities(self) -> List[str]:
        """Constrói lista de capabilities do Scout Agent"""
        capabilities = []

        # Domínios de exploração
        for domain in self.settings.service_registry.capabilities.get(
            'exploration_domains', []
        ):
            capabilities.append(f"domain:{domain}")

        # Tipos de canal
        for channel in self.settings.service_registry.capabilities.get(
            'channel_types', []
        ):
            capabilities.append(f"channel:{channel}")

        # Tipo de agente
        agent_type = self.settings.service_registry.capabilities.get('agent_type')
        if agent_type:
            capabilities.append(f"agent_type:{agent_type}")

        return capabilities

    def _build_metadata(self) -> Dict[str, str]:
        """Constrói metadata do Scout Agent"""
        return {
            'service_name': self.settings.service.service_name,
            'version': self.settings.service.version,
            'environment': self.settings.service.environment,
            'max_signals_per_minute': str(
                self.settings.service_registry.capabilities.get(
                    'max_signals_per_minute', 100
                )
            )
        }

    def is_registered(self) -> bool:
        """Verifica se agent está registrado"""
        return self._registered
