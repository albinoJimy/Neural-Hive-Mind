import grpc
import structlog
from typing import Dict, Any, Optional
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential
import sys
from pathlib import Path

# Adicionar caminho para os protos do service-registry
service_registry_proto_path = Path(__file__).parent.parent.parent.parent / 'service-registry' / 'src'
sys.path.insert(0, str(service_registry_proto_path))

from proto import service_registry_pb2, service_registry_pb2_grpc

logger = structlog.get_logger()


class ServiceRegistryClient:
    '''Cliente gRPC para Service Registry'''

    def __init__(self, config):
        self.config = config
        self.logger = logger.bind(service='service_registry_client')
        self.channel = None
        self.stub = None
        self.agent_id = None
        self._registered = False

    async def initialize(self):
        '''Inicializar conexão gRPC'''
        try:
            target = f'{self.config.service_registry_host}:{self.config.service_registry_port}'

            if self.config.enable_mtls:
                # TODO: Implementar mTLS quando pronto
                self.channel = grpc.aio.insecure_channel(target)
            else:
                self.channel = grpc.aio.insecure_channel(target)

            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            self.logger.info('service_registry_client_initialized', target=target)
        except Exception as e:
            self.logger.error('service_registry_client_init_failed', error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def register(self) -> str:
        '''Registrar Worker Agent no Service Registry'''
        try:
            request = service_registry_pb2.RegisterRequest(
                agent_type=service_registry_pb2.WORKER,
                capabilities=self.config.supported_task_types,
                metadata={
                    'agent_id': self.config.agent_id,
                    'http_port': str(self.config.http_port),
                    'grpc_port': str(self.config.grpc_port),
                    'max_concurrent_tasks': str(self.config.max_concurrent_tasks)
                },
                namespace=self.config.namespace,
                cluster=self.config.cluster,
                version=self.config.service_version
            )

            response = await self.stub.Register(request)
            self.agent_id = response.agent_id
            self._registered = True

            self.logger.info(
                'worker_agent_registered',
                agent_id=self.agent_id,
                capabilities=self.config.supported_task_types,
                namespace=self.config.namespace,
                cluster=self.config.cluster
            )

            # TODO: Incrementar métrica worker_agent_registered_total
            return self.agent_id

        except Exception as e:
            self.logger.error('registration_failed', error=str(e))
            raise

    async def heartbeat(self, telemetry: Dict[str, Any]) -> bool:
        '''Enviar heartbeat ao Service Registry'''
        try:
            if not self._registered:
                self.logger.warning('heartbeat_skipped_not_registered')
                return False

            agent_telemetry = service_registry_pb2.AgentTelemetry(
                success_rate=telemetry.get('success_rate', 1.0),
                avg_duration_ms=telemetry.get('avg_duration_ms', 0),
                total_executions=telemetry.get('total_executions', 0),
                failed_executions=telemetry.get('failed_executions', 0),
                last_execution_at=int(telemetry.get('timestamp', 0) * 1000)
            )

            request = service_registry_pb2.HeartbeatRequest(
                agent_id=self.agent_id,
                telemetry=agent_telemetry
            )

            response = await self.stub.Heartbeat(request)

            self.logger.debug(
                'heartbeat_sent',
                agent_id=self.agent_id,
                status=service_registry_pb2.AgentStatus.Name(response.status)
            )

            # TODO: Incrementar métrica worker_agent_heartbeat_total{status=...}
            return True

        except Exception as e:
            self.logger.error('heartbeat_failed', error=str(e))
            return False

    async def deregister(self) -> bool:
        '''Deregistrar Worker Agent do Service Registry'''
        try:
            if not self._registered:
                return True

            request = service_registry_pb2.DeregisterRequest(
                agent_id=self.agent_id
            )

            response = await self.stub.Deregister(request)
            self._registered = False

            self.logger.info(
                'worker_agent_deregistered',
                agent_id=self.agent_id,
                success=response.success
            )

            # TODO: Incrementar métrica worker_agent_deregistered_total
            return response.success

        except Exception as e:
            self.logger.error('deregister_failed', error=str(e))
            return False

    async def close(self):
        '''Fechar conexão gRPC'''
        if self.channel:
            await self.channel.close()
            self.logger.info('service_registry_client_closed')

    def is_registered(self) -> bool:
        '''Verificar se agent está registrado'''
        return self._registered
