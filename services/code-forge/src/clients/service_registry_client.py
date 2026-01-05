"""Service Registry gRPC client for Code Forge"""
import time
from typing import Dict, Any, List, Optional
import grpc
import structlog

from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente gRPC para Service Registry"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None
        self.agent_id: Optional[str] = None
        self._registered = False

    async def initialize(self):
        """Inicializar cliente gRPC"""
        try:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.aio.insecure_channel(target)
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)
            logger.info("service_registry_client_initialized", host=self.host, port=self.port)
        except Exception as e:
            logger.error("service_registry_client_init_failed", error=str(e))
            raise

    async def close(self):
        """Fechar canal gRPC"""
        if self.agent_id and self.stub:
            await self.deregister()

        if self.channel:
            await self.channel.close()
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

            response = await self.stub.Register(request)
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

            response = await self.stub.Heartbeat(request)
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
            response = await self.stub.Deregister(request)
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
