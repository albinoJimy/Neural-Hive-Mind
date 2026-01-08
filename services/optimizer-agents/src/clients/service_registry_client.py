"""Service Registry gRPC client for Optimizer Agents com suporte a mTLS via SPIFFE."""
import asyncio
from typing import Dict, List, Optional, Tuple

import grpc
import structlog

from neural_hive_observability import instrument_grpc_channel
from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc
from src.config.settings import get_settings

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
    """
    Cliente gRPC para Service Registry com suporte a mTLS via SPIFFE.

    Responsavel por registro e descoberta de servicos.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.agent_id: Optional[str] = None
        self._registered = False
        self.spiffe_manager: Optional[SPIFFEManager] = None

    async def connect(self):
        """Estabelecer canal gRPC com Service Registry com suporte a mTLS."""
        try:
            target = self.settings.service_registry_endpoint

            # Verificar se mTLS via SPIFFE está habilitado
            spiffe_x509_enabled = (
                getattr(self.settings, 'spiffe_enabled', False)
                and getattr(self.settings, 'spiffe_enable_x509', False)
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar configuração SPIFFE
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=self.settings.spiffe_socket_path,
                    trust_domain=self.settings.spiffe_trust_domain,
                    jwt_audience=self.settings.spiffe_jwt_audience,
                    jwt_ttl_seconds=self.settings.spiffe_jwt_ttl_seconds,
                    enable_x509=True,
                    environment=self.settings.environment
                )

                # Criar SPIFFE manager
                self.spiffe_manager = SPIFFEManager(spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                # Permitir fallback inseguro apenas em ambientes de desenvolvimento
                is_dev_env = self.settings.environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                logger.info(
                    'mtls_channel_configured',
                    target=target,
                    environment=self.settings.environment
                )
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.settings.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.settings.environment} but SPIFFE X.509 is disabled. "
                        "Set spiffe_enabled=True and spiffe_enable_x509=True."
                    )

                logger.warning(
                    'using_insecure_channel',
                    target=target,
                    environment=self.settings.environment,
                    warning='mTLS disabled - not for production use'
                )
                self.channel = grpc.aio.insecure_channel(
                    target,
                    options=[
                        ("grpc.max_send_message_length", 100 * 1024 * 1024),
                        ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                        ("grpc.keepalive_time_ms", 30000),
                    ],
                )

            self.channel = instrument_grpc_channel(self.channel, service_name='service-registry')
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            try:
                await asyncio.wait_for(self.channel.channel_ready(), timeout=5.0)
                logger.info("service_registry_grpc_connected", endpoint=target)
            except asyncio.TimeoutError:
                logger.warning("service_registry_grpc_connection_timeout", endpoint=target)
        except Exception as e:
            logger.error("service_registry_grpc_connection_failed", error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        if not getattr(self.settings, 'spiffe_enabled', False) or not self.spiffe_manager:
            return []

        try:
            audience = f"service-registry.{self.settings.spiffe_trust_domain}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=self.settings.environment
            )
        except Exception as e:
            logger.warning('jwt_svid_fetch_failed', error=str(e))
            if self.settings.environment in ['production', 'staging', 'prod']:
                raise
            return []

    async def disconnect(self):
        """Fechar canal gRPC e SPIFFE manager."""
        if self.channel:
            if self.agent_id:
                await self.deregister()

            await self.channel.close()
            logger.info("service_registry_grpc_disconnected")

        if self.spiffe_manager:
            await self.spiffe_manager.close()

    async def register(self, capabilities: List[str], metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Registrar Optimizer Agent no Service Registry.

        Args:
            capabilities: Lista de capacidades
            metadata: Metadados adicionais

        Returns:
            Agent ID ou None se falhou
        """
        try:
            if not self.stub:
                logger.warning("register_called_without_connection")
                return None

            request = service_registry_pb2.RegisterRequest(
                agent_type=service_registry_pb2.WORKER,  # Usando WORKER para optimizer
                capabilities=capabilities,
                metadata=metadata or {},
                namespace=getattr(self.settings, 'namespace', 'default'),
                cluster=getattr(self.settings, 'cluster', 'neural-hive'),
                version=getattr(self.settings, 'service_version', '1.0.0')
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Register(request, metadata=grpc_metadata)
            self.agent_id = response.agent_id
            self._registered = True

            logger.info("agent_registered", agent_id=self.agent_id, capabilities=capabilities)
            return self.agent_id

        except grpc.RpcError as e:
            logger.error("register_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("register_failed", error=str(e))
            return None

    async def deregister(self) -> bool:
        """
        Deregistrar Optimizer Agent do Service Registry.

        Returns:
            True se bem-sucedido
        """
        try:
            if not self.agent_id or not self.stub:
                logger.warning("deregister_called_without_agent_id")
                return False

            request = service_registry_pb2.DeregisterRequest(agent_id=self.agent_id)

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Deregister(request, metadata=grpc_metadata)
            self._registered = False

            logger.info("agent_deregistered", agent_id=self.agent_id, success=response.success)
            self.agent_id = None
            return response.success

        except grpc.RpcError as e:
            logger.error("deregister_failed", agent_id=self.agent_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("deregister_failed", agent_id=self.agent_id, error=str(e))
            return False

    async def heartbeat(self, health_status: str = "HEALTHY", metrics: Optional[Dict] = None) -> bool:
        """
        Enviar heartbeat ao Service Registry.

        Args:
            health_status: Status de saude
            metrics: Metricas atuais

        Returns:
            True se bem-sucedido
        """
        try:
            if not self.agent_id or not self.stub:
                logger.warning("heartbeat_called_without_agent_id")
                return False

            metrics = metrics or {}
            telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=metrics.get('success_rate', 1.0),
                avg_duration_ms=int(metrics.get('avg_duration_ms', 0)),
                total_executions=int(metrics.get('total_executions', 0)),
                failed_executions=int(metrics.get('failed_executions', 0)),
            )

            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.agent_id,
                telemetry=telemetry
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.Heartbeat(request, metadata=grpc_metadata)
            logger.debug("heartbeat_sent", agent_id=self.agent_id, status=response.status)
            return True

        except grpc.RpcError as e:
            logger.error("heartbeat_failed", agent_id=self.agent_id, error=str(e), code=e.code())
            return False
        except Exception as e:
            logger.error("heartbeat_failed", agent_id=self.agent_id, error=str(e))
            return False

    async def discover_agents(self, capabilities: List[str], filters: Optional[Dict] = None) -> Optional[List[Dict]]:
        """
        Descobrir agentes com capacidades especificas.

        Args:
            capabilities: Capacidades requeridas
            filters: Filtros adicionais

        Returns:
            Lista de agentes ou None se falhou
        """
        try:
            if not self.stub:
                logger.warning("discover_agents_called_without_connection")
                return None

            request = service_registry_pb2.DiscoverRequest(
                capabilities=capabilities,
                filters=filters or {},
                max_results=100
            )

            # Obter metadata com JWT-SVID
            grpc_metadata = await self._get_grpc_metadata()

            response = await self.stub.DiscoverAgents(request, metadata=grpc_metadata)

            agents = []
            for agent in response.agents:
                if agent.status == service_registry_pb2.HEALTHY:
                    agents.append({
                        "agent_id": agent.agent_id,
                        "agent_type": self._agent_type_to_string(agent.agent_type),
                        "capabilities": list(agent.capabilities),
                        "status": "HEALTHY",
                        "metadata": dict(agent.metadata),
                        "telemetry": {
                            "success_rate": agent.telemetry.success_rate if agent.telemetry else 0.0,
                            "avg_duration_ms": agent.telemetry.avg_duration_ms if agent.telemetry else 0,
                        }
                    })

            logger.info("agents_discovered", count=len(agents), capabilities=capabilities)
            return agents

        except grpc.RpcError as e:
            logger.error("discover_agents_failed", error=str(e), code=e.code())
            return None
        except Exception as e:
            logger.error("discover_agents_failed", error=str(e))
            return None

    def _agent_type_to_string(self, agent_type: int) -> str:
        """Converter enum AgentType para string."""
        type_map = {
            service_registry_pb2.WORKER: 'WORKER',
            service_registry_pb2.SCOUT: 'SCOUT',
            service_registry_pb2.GUARD: 'GUARD',
        }
        return type_map.get(agent_type, 'UNKNOWN')

    async def update_health_status(self, health_status: str, metrics: Optional[Dict] = None) -> bool:
        """
        Atualizar status de saude.

        Args:
            health_status: Novo status de saude
            metrics: Metricas atualizadas

        Returns:
            True se bem-sucedido
        """
        return await self.heartbeat(health_status, metrics)
