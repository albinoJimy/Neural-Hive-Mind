"""Service Registry gRPC client for Guard Agents"""
import asyncio
from typing import Optional
import grpc
import structlog
from datetime import datetime

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente para comunicação com Service Registry"""

    def __init__(
        self,
        host: str,
        port: int,
        agent_type: str = "GUARD",
        capabilities: list[str] = None,
        metadata: dict[str, str] = None,
        heartbeat_interval: int = 30
    ):
        self.host = host
        self.port = port
        self.agent_type = agent_type
        self.capabilities = capabilities or []
        self.metadata = metadata or {}
        self.heartbeat_interval = heartbeat_interval

        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.agent_id: Optional[str] = None
        self.registration_token: Optional[str] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    async def connect(self):
        """Conecta ao Service Registry"""
        try:
            self.channel = grpc.aio.insecure_channel(f"{self.host}:{self.port}")
            # TODO: Import stub when proto is compiled
            # from src.proto import service_registry_pb2_grpc
            # self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            logger.info("service_registry.connected", host=self.host, port=self.port)
        except Exception as e:
            logger.error("service_registry.connection_failed", error=str(e))
            raise

    async def register(self) -> str:
        """Registra agente no Service Registry"""
        try:
            # TODO: Implement with actual proto
            # request = service_registry_pb2.RegisterRequest(
            #     agent_type=self.agent_type,
            #     capabilities=self.capabilities,
            #     metadata=self.metadata
            # )
            # response = await self.stub.Register(request)
            # self.agent_id = response.agent_id
            # self.registration_token = response.registration_token

            # Placeholder implementation
            self.agent_id = f"guard-agent-{datetime.utcnow().timestamp()}"
            logger.info("service_registry.registered", agent_id=self.agent_id)
            return self.agent_id
        except Exception as e:
            logger.error("service_registry.registration_failed", error=str(e))
            raise

    async def start_heartbeat(self):
        """Inicia envio periódico de heartbeats"""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("service_registry.heartbeat_started", interval=self.heartbeat_interval)

    async def _heartbeat_loop(self):
        """Loop de heartbeat"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                # TODO: Implement with actual proto
                # request = service_registry_pb2.HeartbeatRequest(
                #     agent_id=self.agent_id,
                #     telemetry=...
                # )
                # await self.stub.Heartbeat(request)
                logger.debug("service_registry.heartbeat_sent", agent_id=self.agent_id)
            except Exception as e:
                logger.error("service_registry.heartbeat_failed", error=str(e))

    async def deregister(self):
        """Desregistra agente do Service Registry"""
        try:
            if self.agent_id:
                # TODO: Implement with actual proto
                # request = service_registry_pb2.DeregisterRequest(agent_id=self.agent_id)
                # await self.stub.Deregister(request)
                logger.info("service_registry.deregistered", agent_id=self.agent_id)
        except Exception as e:
            logger.error("service_registry.deregister_failed", error=str(e))

    async def close(self):
        """Fecha conexões e para heartbeat"""
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

        logger.info("service_registry.client_closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente está saudável"""
        return self.channel is not None and self.agent_id is not None
