"""Service Registry gRPC client para serviços de engenharia Fluxo G.

Este cliente é compartilhado pelos serviços:
- requirements-engineering (8010)
- documentation-generation (8014)
- knowledge-graph-rag (8016)
- approval-gateway (8017)
- architect-agent (8008)
"""

import asyncio
from typing import Any, Optional

import grpc
import structlog

# Import proto do service-registry (arquivos locais)
from proto import service_registry_pb2, service_registry_pb2_grpc
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class EngineeringServiceRegistryClient:
    """Cliente gRPC para Service Registry para serviços de engenharia."""

    def __init__(self, service_name: str, agent_type):
        """
        Inicializa o cliente.

        Args:
            service_name: Nome do serviço (ex: "approval-gateway")
            agent_type: Tipo do agente/serviço do proto AgentType
        """
        settings = get_settings()
        self.service_name = service_name
        self.agent_type = agent_type
        self.host = getattr(settings, "service_registry_host", "localhost")
        self.port = getattr(settings, "service_registry_port", 8007)
        self.namespace = getattr(settings, "service_registry_namespace", "default")
        self.cluster = getattr(settings, "service_registry_cluster", "neural-hive")
        self.version = getattr(settings, "service_version", "1.0.0")
        self.environment = getattr(settings, "environment", "development")

        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.agent_id: Optional[str] = None
        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self) -> bool:
        """
        Inicializa cliente gRPC.

        Returns:
            True se inicializado com sucesso, False caso contrário
        """
        try:
            target = f"{self.host}:{self.port}"

            self.channel = grpc.aio.insecure_channel(target)
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            # Testar conectividade
            await self.channel.channel_ready()

            logger.info(
                "service_registry_client_initialized",
                service=self.service_name,
                target=target,
                agent_type=str(self.agent_type),
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
        self, capabilities: list[str], metadata: Optional[dict[str, str]] = None
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

            # Metadados padrão
            base_metadata = {
                "service_name": self.service_name,
                "service_type": "engineering",
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
            )

            response = await self.stub.Register(request)
            self.agent_id = response.agent_id
            self._registered = True

            logger.info(
                "service_registered",
                service=self.service_name,
                agent_id=self.agent_id,
                agent_type=str(self.agent_type),
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

    async def send_heartbeat(self, metrics: Optional[dict[str, Any]] = None) -> bool:
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
            telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=metrics.get("success_rate", 1.0) if metrics else 1.0,
                avg_duration_ms=metrics.get("avg_duration_ms", 0) if metrics else 0,
                total_executions=metrics.get("total_executions", 0) if metrics else 0,
                failed_executions=metrics.get("failed_executions", 0) if metrics else 0,
                last_execution_at=metrics.get("last_execution_at", 0) if metrics else 0,
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
        self, interval_seconds: int = 30, metrics_callback: Optional[callable] = None
    ):
        """
        Inicia loop de heartbeat.

        Args:
            interval_seconds: Intervalo entre heartbeats
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

    async def close(self):
        """Fecha conexão com o Service Registry."""
        await self.stop_heartbeat()
        await self.deregister()

        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None

        logger.info("service_registry_client_closed", service=self.service_name)


async def register_engineering_service(
    service_name: str,
    agent_type,
    capabilities: list[str],
    metadata: Optional[dict[str, str]] = None,
):
    """
    Registra um serviço de engenharia no Service Registry.

    Args:
        service_name: Nome do serviço (ex: "approval-gateway")
        agent_type: Tipo do agente do proto AgentType
        capabilities: Lista de capabilities
        metadata: Metadados adicionais

    Returns:
        Cliente registrado ou None se falhou
    """
    client = EngineeringServiceRegistryClient(service_name, agent_type)
    if await client.initialize():
        agent_id = await client.register(capabilities, metadata)
        if agent_id:
            logger.info(
                "engineering_service_registered",
                service=service_name,
                agent_id=agent_id,
            )
            return client
        else:
            logger.error("engineering_service_registration_failed", service=service_name)
            await client.close()
            return None
    else:
        logger.error("engineering_service_client_init_failed", service=service_name)
        return None
