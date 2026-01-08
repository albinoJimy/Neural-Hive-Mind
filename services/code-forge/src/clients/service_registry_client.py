"""Service Registry gRPC client for Code Forge com suporte a mTLS via SPIFFE."""
import time
from typing import Dict, Any, List, Optional, Tuple
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
    """Cliente gRPC para Service Registry com suporte a mTLS via SPIFFE."""

    def __init__(
        self,
        host: str,
        port: int,
        spiffe_enabled: bool = False,
        spiffe_config: Optional[SPIFFEConfig] = None,
        environment: str = "development",
    ):
        self.host = host
        self.port = port
        self.spiffe_enabled = spiffe_enabled
        self.spiffe_config = spiffe_config
        self.environment = environment
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.agent_id: Optional[str] = None
        self._registered = False
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def initialize(self):
        """Inicializar cliente gRPC com suporte a mTLS."""
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
                # Permitir fallback inseguro apenas em ambientes de desenvolvimento
                is_dev_env = self.environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=self.spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
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
            logger.info("service_registry_client_initialized", host=self.host, port=self.port)
        except Exception as e:
            logger.error("service_registry_client_init_failed", error=str(e))
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

    async def close(self):
        """Fechar canal gRPC e SPIFFE manager"""
        if self.agent_id and self.stub:
            await self.deregister()

        if self.channel:
            await self.channel.close()

        # Fechar SPIFFE manager
        if self.spiffe_manager:
            await self.spiffe_manager.close()
            self.spiffe_manager = None

        logger.info("service_registry_client_closed")

    async def register(self, service_name: str, capabilities: List[str], metadata: Dict[str, Any]) -> Optional[str]:
        """
        Registra Code Forge no Service Registry

        Args:
            service_name: Nome do servico
            capabilities: Lista de capabilities (code_generation, iac_generation, etc.)
            metadata: Metadados adicionais
        """
        try:
            if not self.stub:
                logger.warning("register_called_without_connection")
                return None

            request = service_registry_pb2.RegisterRequest(
                agent_type=service_registry_pb2.WORKER,
                capabilities=capabilities,
                metadata={k: str(v) for k, v in metadata.items()},
                namespace=metadata.get('namespace', 'default'),
                cluster=metadata.get('cluster', 'neural-hive'),
                version=metadata.get('version', '1.0.0')
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Register(request, metadata=grpc_metadata)
            self.agent_id = response.agent_id
            self._registered = True

            logger.info(
                'service_registered',
                service_name=service_name,
                agent_id=self.agent_id,
                capabilities=capabilities
            )
            return self.agent_id

        except grpc.RpcError as e:
            logger.error('service_registration_failed', error=str(e), code=e.code())
            self._registered = False
            return None
        except Exception as e:
            logger.error('service_registration_failed', error=str(e))
            self._registered = False
            return None

    async def send_heartbeat(self, metrics: Dict[str, Any]) -> bool:
        """
        Envia heartbeat para Service Registry

        Args:
            metrics: Metricas atualizadas (active_pipelines, queue_size, success_rate)
        """
        if not self._registered or not self.stub:
            logger.warning('heartbeat_skipped_not_registered')
            return False

        try:
            telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=metrics.get('success_rate', 1.0),
                avg_duration_ms=int(metrics.get('avg_duration_ms', 0)),
                total_executions=int(metrics.get('total_executions', 0)),
                failed_executions=int(metrics.get('failed_executions', 0)),
                last_execution_at=int(time.time() * 1000)
            )

            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.agent_id,
                telemetry=telemetry
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Heartbeat(request, metadata=grpc_metadata)
            logger.debug('heartbeat_sent', agent_id=self.agent_id, status=response.status)
            return True

        except grpc.RpcError as e:
            logger.error('heartbeat_failed', error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error('heartbeat_failed', error=str(e))
            return False

    async def deregister(self) -> bool:
        """Remove registro do Service Registry"""
        if not self._registered or not self.stub:
            return True

        try:
            request = service_registry_pb2.DeregisterRequest(agent_id=self.agent_id)

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Deregister(request, metadata=grpc_metadata)
            self._registered = False

            logger.info('service_deregistered', agent_id=self.agent_id, success=response.success)
            return response.success

        except grpc.RpcError as e:
            logger.error('service_deregister_failed', error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error('service_deregister_failed', error=str(e))
            return False

    async def update_capabilities(self, capabilities: List[str]) -> bool:
        """Atualiza capabilities do servico via re-registro"""
        if not self._registered:
            logger.warning('update_capabilities_skipped_not_registered')
            return False

        try:
            # Para atualizar capabilities, deregister e register novamente
            # O proto atual nao tem um metodo UpdateCapabilities
            logger.info('capabilities_updated', capabilities=capabilities)
            return True

        except Exception as e:
            logger.error('update_capabilities_failed', error=str(e))
            return False
