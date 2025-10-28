"""Cliente gRPC para Service Registry"""
from typing import Optional, Dict, List, Any
import time
import structlog
import grpc
from tenacity import retry, stop_after_attempt, wait_exponential
import sys
from pathlib import Path

from ..config import get_settings

# Adicionar caminho para os protos do service-registry
service_registry_proto_path = Path(__file__).parent.parent.parent.parent / 'service-registry' / 'src'
sys.path.insert(0, str(service_registry_proto_path))

from proto import service_registry_pb2, service_registry_pb2_grpc

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente para registro e heartbeat no Service Registry"""

    def __init__(self, scout_agent_id: str):
        self.scout_agent_id = scout_agent_id
        self.settings = get_settings()
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self.agent_id: Optional[str] = None
        self._registered = False

    async def start(self):
        """Inicializa conexão gRPC com Service Registry"""
        try:
            service_registry_url = (
                f"{self.settings.service_registry.host}:"
                f"{self.settings.service_registry.port}"
            )

            # Cria canal gRPC assíncrono
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

    async def stop(self):
        """Encerra conexão gRPC"""
        if self.channel:
            await self.channel.close()
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

            response = await self.stub.Register(request)
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

            response = await self.stub.Heartbeat(request)

            logger.debug(
                "heartbeat_sent",
                agent_id=self.agent_id,
                status=service_registry_pb2.AgentStatus.Name(response.status),
                last_seen=int(time.time())
            )

            return True

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

            response = await self.stub.Deregister(request)
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
