"""Service Registry gRPC client para Doc Ingestion Service.

Este cliente registra o serviço doc-ingestion no Service Registry e gerencia
heartbeat para manter o serviço ativo e descubrível por outros serviços.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional

import grpc
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

# Importar protobufs compilados
try:
    from neural_hive_integration.proto_stubs import (
        service_registry_pb2,
        service_registry_pb2_grpc,
    )
except ImportError:
    # Fallback para import local caso neural_hive_integration não esteja disponível
    logger.warning(
        "neural_hive_integration_not_available",
        message="Using local proto stubs if available",
    )
    service_registry_pb2 = None
    service_registry_pb2_grpc = None


class DocIngestionServiceRegistryClient:
    """Cliente gRPC para Service Registry para o serviço doc-ingestion."""

    def __init__(
        self,
        service_name: str = "doc-ingestion",
        agent_type: Optional[int] = None,  # DOC_INGESTION = 10
    ):
        """
        Inicializa o cliente.

        Args:
            service_name: Nome do serviço (default: "doc-ingestion")
            agent_type: Tipo do agente do proto AgentType (default: DOC_INGESTION)
        """
        settings = get_settings()
        self.service_name = service_name
        self.agent_type = agent_type or 10  # DOC_INGESTION

        # Service Registry connection settings
        self.host = settings.service_registry_grpc_host
        self.port = settings.service_registry_grpc_port
        self.namespace = getattr(settings, "service_registry_namespace", "default")
        self.cluster = getattr(settings, "service_registry_cluster", "neural-hive")
        self.version = settings.service_version
        self.environment = settings.environment

        # gRPC channel e stub
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.agent_id: Optional[str] = None
        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        # Telemetria
        self._metrics: Dict[str, Any] = {
            "success_rate": 1.0,
            "avg_duration_ms": 0,
            "total_executions": 0,
            "failed_executions": 0,
            "last_execution_at": 0,
        }

    async def initialize(self) -> bool:
        """
        Inicializa cliente gRPC.

        Returns:
            True se inicializado com sucesso, False caso contrário
        """
        if service_registry_pb2 is None:
            logger.warning(
                "service_registry_proto_not_available",
                service=self.service_name,
                message="Proto stubs not available, skipping Service Registry",
            )
            return False

        try:
            target = f"{self.host}:{self.port}"

            # Em produção, usar mTLS; em desenvolvimento, canal inseguro
            if self.environment in ["production", "staging"]:
                logger.warning(
                    "mtls_not_implemented_yet",
                    target=target,
                    environment=self.environment,
                    message="Using insecure channel - implement mTLS for production",
                )

            self.channel = grpc.aio.insecure_channel(target)
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            # Testar conectividade
            await self.channel.channel_ready()

            logger.info(
                "service_registry_client_initialized",
                service=self.service_name,
                target=target,
                agent_type=self.agent_type,
            )
            return True

        except Exception as e:
            logger.error(
                "service_registry_client_init_failed",
                service=self.service_name,
                error=str(e),
            )
            return False

    async def register(
        self,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Registra o serviço no Service Registry.

        Args:
            capabilities: Lista de capabilities do serviço
            metadata: Metadados adicionais

        Returns:
            agent_id se registrado com sucesso, None caso contrário
        """
        try:
            if not self.stub:
                logger.warning("register_called_without_connection", service=self.service_name)
                return None

            # Capabilities padrão do doc-ingestion
            default_capabilities = [
                "pdf_parsing",
                "word_parsing",
                "visio_parsing",
                "postman_parsing",
                "entity_extraction",
                "document_upload",
                "document_storage",
            ]
            capabilities = capabilities or default_capabilities

            # Metadados padrão
            base_metadata = {
                "service_name": self.service_name,
                "service_type": "engineering",
                "port": str(get_settings().port),
                "api_prefix": get_settings().api_prefix,
            }
            if metadata:
                base_metadata.update(metadata)

            request = service_registry_pb2.RegisterRequest(
                agent_type=self.agent_type,
                capabilities=capabilities,
                metadata=base_metadata,
                namespace=self.namespace,
                cluster=self.cluster,
                version=self.version,
                telemetry=service_registry_pb2.AgentTelemetry(
                    success_rate=self._metrics["success_rate"],
                    avg_duration_ms=self._metrics["avg_duration_ms"],
                    total_executions=self._metrics["total_executions"],
                    failed_executions=self._metrics["failed_executions"],
                    last_execution_at=self._metrics["last_execution_at"],
                ),
            )

            response = await self.stub.Register(request)
            self.agent_id = response.agent_id
            self._registered = True

            logger.info(
                "service_registered",
                service=self.service_name,
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                capabilities=capabilities,
            )
            return self.agent_id

        except grpc.RpcError as e:
            logger.error(
                "service_registration_failed",
                service=self.service_name,
                error=str(e),
                code=e.code(),
            )
            return None
        except Exception as e:
            logger.error(
                "service_registration_failed",
                service=self.service_name,
                error=str(e),
            )
            return None

    async def deregister(self) -> bool:
        """
        Remove registro do serviço do Service Registry.

        Returns:
            True se removido com sucesso, False caso contrário
        """
        if not self._registered or not self.stub:
            return True

        try:
            request = service_registry_pb2.DeregisterRequest(agent_id=self.agent_id)
            response = await self.stub.Deregister(request)
            self._registered = False

            logger.info(
                "service_deregistered",
                service=self.service_name,
                agent_id=self.agent_id,
                success=response.success,
            )
            return response.success

        except Exception as e:
            logger.error(
                "service_deregister_failed",
                service=self.service_name,
                error=str(e),
            )
            return False

    async def send_heartbeat(self, metrics: Optional[Dict[str, Any]] = None) -> bool:
        """
        Envia heartbeat para o Service Registry.

        Args:
            metrics: Métricas opcionais (success_rate, total_executions, etc.)

        Returns:
            True se heartbeat enviado com sucesso, False caso contrário
        """
        if not self._registered or not self.stub:
            return False

        try:
            # Atualizar métricas
            if metrics:
                self._metrics.update(metrics)

            telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=self._metrics["success_rate"],
                avg_duration_ms=self._metrics["avg_duration_ms"],
                total_executions=self._metrics["total_executions"],
                failed_executions=self._metrics["failed_executions"],
                last_execution_at=self._metrics["last_execution_at"],
            )

            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.agent_id, telemetry=telemetry
            )

            response = await self.stub.Heartbeat(request)

            logger.debug(
                "heartbeat_sent",
                service=self.service_name,
                agent_id=self.agent_id,
                status=str(response.status),
            )
            return True

        except Exception as e:
            logger.warning(
                "heartbeat_failed",
                service=self.service_name,
                error=str(e),
            )
            return False

    async def start_heartbeat(
        self,
        interval_seconds: int = 30,
        metrics_callback: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        """
        Inicia loop de heartbeat.

        Args:
            interval_seconds: Intervalo entre heartbeats (default: 30s)
            metrics_callback: Função opcional para obter métricas atuais
        """
        if self._running:
            return

        self._running = True

        async def heartbeat_loop():
            while self._running:
                try:
                    metrics = metrics_callback() if metrics_callback else None
                    await self.send_heartbeat(metrics)
                except Exception as e:
                    logger.warning("heartbeat_loop_error", error=str(e))
                await asyncio.sleep(interval_seconds)

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())
        logger.info(
            "heartbeat_started",
            service=self.service_name,
            interval=interval_seconds,
        )

    async def stop_heartbeat(self):
        """Para o loop de heartbeat."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        logger.info("heartbeat_stopped", service=self.service_name)

    async def discover_agents(
        self,
        capabilities: Optional[List[str]] = None,
        filters: Optional[Dict[str, str]] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Descobre outros agentes baseado em capabilities e filtros.

        Args:
            capabilities: Lista de capabilities requeridas
            filters: Filtros adicionais (namespace, status, etc.)
            max_results: Máximo de resultados

        Returns:
            Lista de AgentInfo convertidos para dict
        """
        if not self.stub:
            return []

        try:
            request = service_registry_pb2.DiscoverRequest(
                capabilities=capabilities or [],
                filters=filters or {},
                max_results=max_results,
            )

            response = await self.stub.DiscoverAgents(request)

            agents = []
            for agent_info in response.agents:
                agents.append(self._convert_agent_info(agent_info))

            logger.info(
                "agents_discovered",
                service=self.service_name,
                count=len(agents),
                capabilities=capabilities,
            )
            return agents

        except Exception as e:
            logger.error(
                "discover_agents_failed",
                service=self.service_name,
                error=str(e),
            )
            return []

    def _convert_agent_info(self, agent_info) -> Dict[str, Any]:
        """
        Converte AgentInfo protobuf para dict.

        Args:
            agent_info: Mensagem AgentInfo do proto

        Returns:
            Dict com informações do agente
        """
        # Extrair telemetria se disponível
        telemetry_data = {}
        if agent_info.telemetry:
            telemetry_data = {
                "success_rate": agent_info.telemetry.success_rate,
                "avg_duration_ms": agent_info.telemetry.avg_duration_ms,
                "total_executions": agent_info.telemetry.total_executions,
                "failed_executions": agent_info.telemetry.failed_executions,
                "last_execution_at": agent_info.telemetry.last_execution_at,
            }

        # Converter AgentStatus enum para string
        status_map = {
            0: "AGENT_STATUS_UNSPECIFIED",
            1: "HEALTHY",
            2: "UNHEALTHY",
            3: "DEGRADED",
        }
        status_str = status_map.get(agent_info.status, "UNKNOWN")

        return {
            "agent_id": agent_info.agent_id,
            "agent_type": agent_info.agent_type,
            "capabilities": list(agent_info.capabilities),
            "namespace": agent_info.namespace,
            "cluster": agent_info.cluster,
            "version": agent_info.version,
            "metadata": dict(agent_info.metadata) if agent_info.metadata else {},
            "status": status_str,
            "registered_at": agent_info.registered_at,
            "last_seen": agent_info.last_seen,
            "telemetry": telemetry_data,
        }

    async def close(self):
        """Fecha conexão com o Service Registry."""
        await self.stop_heartbeat()
        await self.deregister()

        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None

        logger.info("service_registry_client_closed", service=self.service_name)


async def register_doc_ingestion_service(
    service_name: str = "doc-ingestion",
    capabilities: Optional[List[str]] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> Optional[DocIngestionServiceRegistryClient]:
    """
    Registra o serviço doc-ingestion no Service Registry.

    Args:
        service_name: Nome do serviço (default: "doc-ingestion")
        capabilities: Lista de capabilities
        metadata: Metadados adicionais

    Returns:
        Cliente registrado ou None se falhou
    """
    client = DocIngestionServiceRegistryClient(service_name)
    if await client.initialize():
        agent_id = await client.register(capabilities, metadata)
        if agent_id:
            logger.info(
                "doc_ingestion_service_registered",
                service=service_name,
                agent_id=agent_id,
            )
            return client
        else:
            logger.error("doc_ingestion_service_registration_failed", service=service_name)
            await client.close()
            return None
    else:
        logger.error("doc_ingestion_service_client_init_failed", service=service_name)
        return None
