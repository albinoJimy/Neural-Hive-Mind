"""Service Registry gRPC client for Worker Agents com suporte a mTLS via SPIFFE"""
import grpc
import structlog
from typing import Dict, Any, Optional, List, Tuple
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

from neural_hive_observability import instrument_grpc_channel
from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc

# Importar SPIFFE manager se disponivel
try:
    from neural_hive_security import SPIFFEManager, SPIFFEConfig
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None
    SPIFFEConfig = None

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente gRPC para Service Registry com suporte a mTLS via SPIFFE"""

    def __init__(self, config):
        self.config = config
        self.logger = logger.bind(service='service_registry_client')
        self.channel = None
        self.stub = None
        self.agent_id = None
        self._registered = False
        self.spiffe_manager = None

    async def initialize(self):
        """Inicializar conexao gRPC com suporte a mTLS via SPIFFE"""
        try:
            target = f'{self.config.service_registry_host}:{self.config.service_registry_port}'

            # Verificar se SPIFFE esta habilitado e X.509 disponivel
            spiffe_x509_enabled = (
                self.config.spiffe_enabled
                and getattr(self.config, 'spiffe_enable_x509', False)
                and SECURITY_LIB_AVAILABLE
            )

            if spiffe_x509_enabled:
                # Criar SPIFFE manager se nao existir
                if self.spiffe_manager is None:
                    spiffe_config = SPIFFEConfig(
                        workload_api_socket=self.config.spiffe_socket_path,
                        trust_domain=self.config.spiffe_trust_domain,
                        jwt_audience=self.config.spiffe_jwt_audience,
                        jwt_ttl_seconds=self.config.spiffe_jwt_ttl_seconds,
                        enable_x509=True,
                        environment=self.config.environment
                    )
                    self.spiffe_manager = SPIFFEManager(spiffe_config)
                    await self.spiffe_manager.initialize()

                # Buscar X.509-SVID do SPIRE Workload API
                x509_svid = await self.spiffe_manager.fetch_x509_svid()

                # Criar credenciais SSL com certificados SPIFFE
                credentials = grpc.ssl_channel_credentials(
                    root_certificates=x509_svid.ca_bundle.encode('utf-8'),
                    private_key=x509_svid.private_key.encode('utf-8'),
                    certificate_chain=x509_svid.certificate.encode('utf-8')
                )

                # Criar canal seguro com mTLS
                self.channel = grpc.aio.secure_channel(target, credentials)

                self.logger.info(
                    'mtls_channel_configured',
                    target=target,
                    spiffe_id=x509_svid.spiffe_id,
                    expires_at=x509_svid.expires_at.isoformat()
                )
            else:
                # Fallback para canal inseguro (apenas desenvolvimento)
                if self.config.environment in ['production', 'staging', 'prod']:
                    raise RuntimeError(
                        f"mTLS is required in {self.config.environment} but SPIFFE X.509 is disabled. "
                        "Set spiffe_enabled=True and spiffe_enable_x509=True."
                    )

                self.logger.warning(
                    'using_insecure_channel',
                    environment=self.config.environment,
                    warning='mTLS disabled - not for production use'
                )
                self.channel = grpc.aio.insecure_channel(target)

            # Instrumentar canal com observabilidade
            self.channel = instrument_grpc_channel(self.channel, service_name='service-registry')

            # Criar stub
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            self.logger.info('service_registry_client_initialized', target=target)
        except Exception as e:
            self.logger.error('service_registry_client_init_failed', error=str(e))
            raise

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """
        Obter metadata gRPC com JWT-SVID para autenticacao

        Returns:
            Lista de tuplas (key, value) para metadata gRPC
        """
        metadata: List[Tuple[str, str]] = []

        # Adicionar JWT-SVID se SPIFFE estiver habilitado
        if self.config.spiffe_enabled and self.spiffe_manager:
            try:
                # Buscar JWT-SVID para audience do Service Registry
                # Usar audience configurado, com fallback para valor derivado
                audience = getattr(self.config, 'spiffe_jwt_audience', None)
                if not audience:
                    audience = f"service-registry.{self.config.spiffe_trust_domain}"

                jwt_svid = await self.spiffe_manager.fetch_jwt_svid(
                    audience=audience
                )

                # Adicionar como Bearer token
                metadata.append(('authorization', f'Bearer {jwt_svid.token}'))

                self.logger.debug(
                    'jwt_svid_added_to_metadata',
                    spiffe_id=jwt_svid.spiffe_id,
                    expiry=jwt_svid.expiry.isoformat()
                )
            except Exception as e:
                self.logger.warning('jwt_svid_fetch_failed', error=str(e))
                # Continuar sem JWT em desenvolvimento, falhar em producao
                if self.config.environment in ['production', 'staging', 'prod']:
                    raise

        return metadata

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def register(self) -> str:
        """Registrar Worker Agent no Service Registry"""
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

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            # Chamar RPC com metadata
            response = await self.stub.Register(request, metadata=metadata)
            self.agent_id = response.agent_id
            self._registered = True

            self.logger.info(
                'worker_agent_registered',
                agent_id=self.agent_id,
                capabilities=self.config.supported_task_types,
                namespace=self.config.namespace,
                cluster=self.config.cluster
            )

            return self.agent_id

        except Exception as e:
            self.logger.error('registration_failed', error=str(e))
            raise

    async def heartbeat(self, telemetry: Dict[str, Any]) -> bool:
        """Enviar heartbeat ao Service Registry"""
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

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            # Chamar RPC com metadata
            response = await self.stub.Heartbeat(request, metadata=metadata)

            self.logger.debug(
                'heartbeat_sent',
                agent_id=self.agent_id,
                status=service_registry_pb2.AgentStatus.Name(response.status)
            )

            return True

        except Exception as e:
            self.logger.error('heartbeat_failed', error=str(e))
            return False

    async def deregister(self) -> bool:
        """Deregistrar Worker Agent do Service Registry"""
        try:
            if not self._registered:
                return True

            request = service_registry_pb2.DeregisterRequest(
                agent_id=self.agent_id
            )

            # Obter metadata com JWT-SVID
            metadata = await self._get_grpc_metadata()

            # Chamar RPC com metadata
            response = await self.stub.Deregister(request, metadata=metadata)
            self._registered = False

            self.logger.info(
                'worker_agent_deregistered',
                agent_id=self.agent_id,
                success=response.success
            )

            return response.success

        except Exception as e:
            self.logger.error('deregister_failed', error=str(e))
            return False

    async def close(self):
        """Fechar conexao gRPC"""
        if self.channel:
            await self.channel.close()
            self.logger.info('service_registry_client_closed')

    def is_registered(self) -> bool:
        """Verificar se agent esta registrado"""
        return self._registered
