"""Service Registry gRPC client for Self-Healing Engine (fail-open) com suporte a mTLS via SPIFFE."""
from typing import Dict, List, Optional, Tuple
import structlog

import grpc
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
    """Cliente gRPC do Service Registry (fail-open) com suporte a mTLS via SPIFFE."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: int = 3,
        spiffe_enabled: bool = False,
        spiffe_config: Optional[SPIFFEConfig] = None,
        environment: str = "development",
    ):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.spiffe_enabled = spiffe_enabled
        self.spiffe_config = spiffe_config
        self.environment = environment
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def initialize(self):
        """Inicializa canal gRPC com suporte a mTLS."""
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
            logger.info("service_registry_client.initialized", target=target)
        except Exception as e:
            logger.warning("service_registry_client.init_failed", error=str(e))
            # Fail-open: continuar sem Service Registry

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

    async def notify_agent(self, agent_id: str, notification: Dict) -> bool:
        """Envia notificacao para agente via gRPC (best-effort)."""
        if not self.stub:
            logger.warning(
                "service_registry_client.stub_unavailable",
                agent_id=agent_id,
                notification=notification
            )
            return False

        try:
            request = service_registry_pb2.NotifyAgentRequest(
                agent_id=agent_id,
                notification_type=notification.get("notification_type", "INFO"),
                message=notification.get("message", ""),
                metadata=notification.get("metadata", {})
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            await self.stub.NotifyAgent(request, timeout=self.timeout_seconds, metadata=grpc_metadata)
            logger.info("service_registry_client.notify_agent_sent", agent_id=agent_id)
            return True
        except grpc.RpcError as e:
            logger.warning(
                "service_registry_client.notify_agent_grpc_failed",
                agent_id=agent_id,
                error=str(e),
                code=e.code()
            )
            return False
        except Exception as e:
            logger.warning(
                "service_registry_client.notify_agent_failed",
                agent_id=agent_id,
                error=str(e)
            )
            return False

    async def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Obtem informacoes de um agente (best-effort)."""
        if not self.stub:
            logger.warning("service_registry_client.stub_unavailable", agent_id=agent_id)
            return None

        try:
            request = service_registry_pb2.GetAgentRequest(agent_id=agent_id)

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.GetAgent(request, timeout=self.timeout_seconds, metadata=grpc_metadata)

            # Converter AgentStatus enum para string
            status_map = {
                service_registry_pb2.AGENT_STATUS_UNSPECIFIED: 'UNSPECIFIED',
                service_registry_pb2.HEALTHY: 'HEALTHY',
                service_registry_pb2.UNHEALTHY: 'UNHEALTHY',
                service_registry_pb2.DEGRADED: 'DEGRADED'
            }

            return {
                "agent_id": response.agent.agent_id,
                "status": status_map.get(response.agent.status, 'UNKNOWN'),
                "capabilities": list(response.agent.capabilities),
                "metadata": dict(response.agent.metadata),
                "namespace": response.agent.namespace,
                "cluster": response.agent.cluster,
                "version": response.agent.version,
                "telemetry": {
                    "success_rate": response.agent.telemetry.success_rate if response.agent.telemetry else 0.0,
                    "avg_duration_ms": response.agent.telemetry.avg_duration_ms if response.agent.telemetry else 0,
                    "total_executions": response.agent.telemetry.total_executions if response.agent.telemetry else 0,
                }
            }
        except grpc.RpcError as e:
            logger.warning(
                "service_registry_client.get_agent_grpc_failed",
                agent_id=agent_id,
                error=str(e),
                code=e.code()
            )
            return None
        except Exception as e:
            logger.warning("service_registry_client.get_agent_failed", agent_id=agent_id, error=str(e))
            return None

    async def close(self):
        """Fecha canal gRPC e SPIFFE manager (se inicializado)."""
        if self.channel:
            await self.channel.close()

        # Fechar SPIFFE manager
        if self.spiffe_manager:
            await self.spiffe_manager.close()
            self.spiffe_manager = None

        logger.info("service_registry_client.closed")
