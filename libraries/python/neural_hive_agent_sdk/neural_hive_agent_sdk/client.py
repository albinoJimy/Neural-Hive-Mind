import grpc
import asyncio
import structlog
from typing import Dict, List, Optional
from datetime import datetime, timezone
from enum import Enum

from .config import AgentConfig


logger = structlog.get_logger()


class AgentType(str, Enum):
    """Tipos de agentes"""
    WORKER = "WORKER"
    SCOUT = "SCOUT"
    GUARD = "GUARD"


class AgentTelemetry:
    """Telemetria do agente"""

    def __init__(
        self,
        success_rate: float = 0.0,
        avg_duration_ms: int = 0,
        total_executions: int = 0,
        failed_executions: int = 0
    ):
        self.success_rate = success_rate
        self.avg_duration_ms = avg_duration_ms
        self.total_executions = total_executions
        self.failed_executions = failed_executions
        self.last_execution_at = int(datetime.now(timezone.utc).timestamp())

    def to_proto(self):
        """Converte para formato protobuf"""
        # TODO: Usar proto gerado
        return {
            'success_rate': self.success_rate,
            'avg_duration_ms': self.avg_duration_ms,
            'total_executions': self.total_executions,
            'failed_executions': self.failed_executions,
            'last_execution_at': self.last_execution_at
        }


class AgentClient:
    """Cliente para integração com Service Registry"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.agent_id: Optional[str] = None
        self.registration_token: Optional[str] = None
        self.telemetry = AgentTelemetry()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    async def __aenter__(self):
        """Context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - auto-deregister"""
        await self.deregister()

    async def _create_channel(self) -> grpc.aio.Channel:
        """Cria canal gRPC com retry"""
        for attempt in range(self.config.GRPC_MAX_RETRIES):
            try:
                channel = grpc.aio.insecure_channel(
                    self.config.REGISTRY_GRPC_ENDPOINT,
                    options=[
                        ('grpc.max_send_message_length', 50 * 1024 * 1024),
                        ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                    ]
                )

                # Testar conexão
                await asyncio.wait_for(
                    channel.channel_ready(),
                    timeout=self.config.GRPC_TIMEOUT_SECONDS
                )

                logger.info(
                    "grpc_channel_created",
                    endpoint=self.config.REGISTRY_GRPC_ENDPOINT
                )
                return channel

            except Exception as e:
                logger.warning(
                    "grpc_channel_creation_failed",
                    attempt=attempt + 1,
                    error=str(e)
                )

                if attempt == self.config.GRPC_MAX_RETRIES - 1:
                    raise

                await asyncio.sleep(2 ** attempt)  # Backoff exponencial

    async def register(
        self,
        agent_type: AgentType,
        capabilities: List[str],
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Registra o agente no Service Registry.

        Args:
            agent_type: Tipo do agente (WORKER, SCOUT, GUARD)
            capabilities: Lista de capabilities do agente
            metadata: Metadados adicionais

        Returns:
            agent_id do agente registrado
        """
        try:
            # Criar canal gRPC
            self.channel = await self._create_channel()

            # TODO: Criar stub real quando proto estiver gerado
            # self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            # Preparar metadata
            if metadata is None:
                metadata = {}

            metadata.update({
                'namespace': self.config.AGENT_NAMESPACE,
                'cluster': self.config.AGENT_CLUSTER,
                'version': self.config.AGENT_VERSION
            })

            # Criar request
            # TODO: Usar proto real
            # request = service_registry_pb2.RegisterRequest(
            #     agent_type=agent_type.value,
            #     capabilities=capabilities,
            #     metadata=metadata,
            #     namespace=self.config.AGENT_NAMESPACE,
            #     cluster=self.config.AGENT_CLUSTER,
            #     version=self.config.AGENT_VERSION
            # )

            # Chamar RPC Register
            # response = await self.stub.Register(
            #     request,
            #     timeout=self.config.GRPC_TIMEOUT_SECONDS
            # )

            # Mock response para desenvolvimento
            import uuid
            self.agent_id = str(uuid.uuid4())
            self.registration_token = f"token-{self.agent_id}"

            # Iniciar heartbeat automático
            await self.start_heartbeat()

            logger.info(
                "agent_registered",
                agent_id=self.agent_id,
                agent_type=agent_type.value,
                capabilities=capabilities
            )

            return self.agent_id

        except Exception as e:
            logger.error("agent_registration_failed", error=str(e))
            raise

    async def start_heartbeat(self):
        """Inicia loop de heartbeat automático"""
        if self._heartbeat_task is not None:
            logger.warning("heartbeat_already_running")
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(
            "heartbeat_started",
            interval_seconds=self.config.HEARTBEAT_INTERVAL_SECONDS
        )

    async def _heartbeat_loop(self):
        """Loop de heartbeat"""
        while self._running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.config.HEARTBEAT_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))
                await asyncio.sleep(self.config.HEARTBEAT_INTERVAL_SECONDS)

    async def _send_heartbeat(self):
        """Envia heartbeat com telemetria"""
        if not self.agent_id or not self.stub:
            logger.warning("heartbeat_skipped_not_registered")
            return

        try:
            # TODO: Usar proto real
            # request = service_registry_pb2.HeartbeatRequest(
            #     agent_id=self.agent_id,
            #     telemetry=self.telemetry.to_proto()
            # )

            # response = await self.stub.Heartbeat(
            #     request,
            #     timeout=self.config.GRPC_TIMEOUT_SECONDS
            # )

            logger.debug(
                "heartbeat_sent",
                agent_id=self.agent_id,
                telemetry=self.telemetry.to_proto()
            )

        except Exception as e:
            logger.error("heartbeat_send_failed", error=str(e))

    def update_telemetry(self, telemetry: AgentTelemetry):
        """Atualiza telemetria local para próximo heartbeat"""
        self.telemetry = telemetry

        logger.debug(
            "telemetry_updated",
            success_rate=telemetry.success_rate,
            total_executions=telemetry.total_executions
        )

    async def deregister(self):
        """Deregistra o agente do Service Registry"""
        if not self.agent_id:
            logger.warning("deregister_skipped_not_registered")
            return

        try:
            # Parar heartbeat
            self._running = False
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            # Chamar RPC Deregister
            if self.stub:
                # TODO: Usar proto real
                # request = service_registry_pb2.DeregisterRequest(
                #     agent_id=self.agent_id
                # )

                # await self.stub.Deregister(
                #     request,
                #     timeout=self.config.GRPC_TIMEOUT_SECONDS
                # )

                logger.info("agent_deregistered", agent_id=self.agent_id)

            # Fechar canal
            if self.channel:
                await self.channel.close()

        except Exception as e:
            logger.error("agent_deregistration_failed", error=str(e))
