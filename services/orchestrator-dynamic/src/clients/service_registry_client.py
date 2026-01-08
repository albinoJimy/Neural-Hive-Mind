"""
ServiceRegistryClient - Cliente gRPC para Service Registry.

Cliente assincrono para descoberta de agentes via Service Registry.
"""

import grpc
import structlog
from typing import List, Dict, Optional, TYPE_CHECKING
from tenacity import retry, stop_after_attempt, wait_exponential
from prometheus_client import Counter

from neural_hive_integration.proto_stubs import service_registry_pb2, service_registry_pb2_grpc
from src.config.settings import OrchestratorSettings

if TYPE_CHECKING:
    from neural_hive_security import SPIFFEManager

logger = structlog.get_logger(__name__)

grpc_jwt_auth_attempts_total = Counter(
    "grpc_jwt_auth_attempts_total",
    "Tentativas de autenticacao JWT-SVID em chamadas gRPC",
    ["service", "status"]
)
grpc_jwt_auth_failures_total = Counter(
    "grpc_jwt_auth_failures_total",
    "Falhas de autenticacao JWT-SVID",
    ["service", "reason"]
)


class ServiceRegistryClient:
    """
    Cliente gRPC para Service Registry.

    Fornece discovery de agentes baseado em capabilities e filtros.
    """

    def __init__(
        self,
        config: OrchestratorSettings,
        spiffe_manager: Optional['SPIFFEManager'] = None
    ):
        """
        Inicializa o cliente.

        Args:
            config: Configuracoes do orchestrator
            spiffe_manager: Gerenciador SPIFFE opcional para autenticacao mTLS/JWT
        """
        self.config = config
        self.spiffe_manager = spiffe_manager
        self.logger = logger.bind(component='service_registry_client')
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[service_registry_pb2_grpc.ServiceRegistryStub] = None

    async def initialize(self):
        """Inicializa canal gRPC e stub."""
        host = self.config.service_registry_host
        port = self.config.service_registry_port
        target = f'{host}:{port}'

        self.logger.info('initializing_grpc_channel', target=target)

        try:
            # Verificar se SPIFFE esta habilitado para mTLS
            use_mtls = (
                self.spiffe_manager is not None
                and self.config.spiffe_enabled
                and self.config.spiffe_enable_x509
            )

            if use_mtls:
                self.logger.info('configuring_mtls_channel', target=target)

                try:
                    # Obter X.509-SVID do SPIRE Agent
                    x509_svid = await self.spiffe_manager.fetch_x509_svid()

                    # Verificar se e placeholder (nao deveria acontecer em producao)
                    if hasattr(x509_svid, 'is_placeholder') and x509_svid.is_placeholder:
                        self.logger.warning(
                            'x509_svid_is_placeholder',
                            target=target,
                            warning='Using placeholder certificate - insecure in production'
                        )

                    # Criar credenciais SSL com certificado cliente
                    credentials = grpc.ssl_channel_credentials(
                        root_certificates=x509_svid.ca_bundle.encode('utf-8'),
                        private_key=x509_svid.private_key.encode('utf-8'),
                        certificate_chain=x509_svid.certificate.encode('utf-8')
                    )

                    # Criar canal seguro
                    self.channel = grpc.aio.secure_channel(target, credentials)

                    self.logger.info(
                        'mtls_channel_configured',
                        target=target,
                        spiffe_id=x509_svid.spiffe_id,
                        expires_at=x509_svid.expires_at
                    )

                except Exception as e:
                    # Importar excecao SPIFFE
                    from neural_hive_security.spiffe_manager import SPIFFEFetchError

                    if isinstance(e, SPIFFEFetchError):
                        # SPIFFE fetch falhou - decisao critica
                        self.logger.error(
                            'spiffe_x509_fetch_failed',
                            error=str(e),
                            target=target,
                            message='X.509-SVID fetch failed - check SPIRE agent availability'
                        )

                        # Verificar se fallback e permitido
                        fallback_allowed = getattr(self.config, 'spiffe_fallback_allowed', False)
                        # Obter ambiente atual
                        environment = getattr(self.config, 'environment', 'development')
                        is_dev_environment = environment.lower() in ('dev', 'development')

                        # Fallback inseguro so e permitido em ambiente de desenvolvimento
                        if not fallback_allowed or not is_dev_environment:
                            # Fail-closed: nao permitir fallback insecure em prod/staging
                            self.logger.error(
                                'mtls_required_fallback_disabled',
                                target=target,
                                environment=environment,
                                error='mTLS required but SPIFFE unavailable'
                            )
                            raise RuntimeError(
                                f"mTLS authentication required but SPIFFE unavailable in {environment}: {e}"
                            )

                        # Fallback permitido (apenas em desenvolvimento)
                        self.logger.warning(
                            'mtls_fallback_to_insecure',
                            target=target,
                            environment=environment,
                            warning='Falling back to insecure channel - NOT FOR PRODUCTION'
                        )
                        self.channel = grpc.aio.insecure_channel(target)
                    else:
                        # Outro erro - re-raise
                        raise

            else:
                # Fallback para canal insecure (compatibilidade reversa)
                self.logger.info('using_insecure_channel', target=target)
                self.channel = grpc.aio.insecure_channel(target)

            # Criar stub
            self.stub = service_registry_pb2_grpc.ServiceRegistryStub(self.channel)

            # Testar conectividade
            await self.channel.channel_ready()

            self.logger.info(
                'grpc_channel_ready',
                target=target,
                secure=use_mtls
            )

        except Exception as e:
            self.logger.error(
                'grpc_initialization_error',
                error=str(e),
                target=target
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.5, max=2)
    )
    async def discover_agents(
        self,
        capabilities: List[str],
        filters: Dict,
        max_results: int = 5
    ) -> List[Dict]:
        """
        Descobre agentes baseado em capabilities e filtros.

        Args:
            capabilities: Lista de capabilities requeridas
            filters: Filtros adicionais (namespace, status, security_level)
            max_results: Maximo de resultados

        Returns:
            Lista de AgentInfo convertidos para dict
        """
        if self.stub is None:
            self.logger.error('stub_not_initialized')
            raise RuntimeError('ServiceRegistryClient not initialized')

        self.logger.info(
            'discovering_agents',
            capabilities=capabilities,
            filters=filters,
            max_results=max_results
        )

        try:
            # Construir mapa de filtros conforme proto
            proto_filters = {}

            # Adicionar namespace como filtro se fornecido
            if 'namespace' in filters:
                proto_filters['namespace'] = filters['namespace']

            # Adicionar status como filtro se fornecido
            if 'status' in filters:
                proto_filters['status'] = filters['status']

            # Adicionar security_level como filtro se fornecido
            if 'security_level' in filters:
                proto_filters['security_level'] = filters['security_level']

            # Criar request usando campos corretos do proto
            request = service_registry_pb2.DiscoverRequest(
                capabilities=capabilities,
                filters=proto_filters,
                max_results=max_results
            )

            # Preparar metadata para autenticacao JWT-SVID se disponivel
            metadata = []
            if self.spiffe_manager and self.config.spiffe_enabled:
                try:
                    # Obter JWT-SVID para autenticacao
                    audience = self.config.spiffe_jwt_audience or 'service-registry.neural-hive.local'
                    jwt_svid = await self.spiffe_manager.fetch_jwt_svid(audience=audience)

                    # Verificar se e placeholder
                    if hasattr(jwt_svid, 'is_placeholder') and jwt_svid.is_placeholder:
                        self.logger.warning(
                            'jwt_svid_is_placeholder',
                            audience=audience,
                            warning='Using placeholder JWT - authentication will likely fail in production'
                        )

                    # Adicionar token JWT ao metadata
                    metadata.append(('authorization', f'Bearer {jwt_svid.token}'))
                    grpc_jwt_auth_attempts_total.labels(service="service_registry", status="success").inc()

                    self.logger.debug(
                        'jwt_svid_attached',
                        audience=audience,
                        spiffe_id=jwt_svid.spiffe_id
                    )

                except Exception as e:
                    # Importar excecao SPIFFE
                    from neural_hive_security.spiffe_manager import SPIFFEFetchError

                    grpc_jwt_auth_attempts_total.labels(service="service_registry", status="error").inc()
                    grpc_jwt_auth_failures_total.labels(service="service_registry", reason="fetch_failed").inc()

                    if isinstance(e, SPIFFEFetchError):
                        # SPIFFE fetch falhou
                        self.logger.error(
                            'jwt_svid_fetch_failed',
                            error=str(e),
                            audience=audience,
                            message='JWT-SVID fetch failed - check SPIRE agent availability'
                        )

                        # Verificar se fallback e permitido
                        fallback_allowed = getattr(self.config, 'spiffe_fallback_allowed', False)
                        # Obter ambiente atual
                        jwt_environment = getattr(self.config, 'environment', 'development')
                        is_jwt_dev_env = jwt_environment.lower() in ('dev', 'development')

                        # Fallback so e permitido em ambiente de desenvolvimento
                        if not fallback_allowed or not is_jwt_dev_env:
                            # Fail-closed: autenticacao e obrigatoria em prod/staging
                            self.logger.error(
                                'jwt_auth_required_fallback_disabled',
                                environment=jwt_environment,
                                error='JWT-SVID authentication required but SPIFFE unavailable'
                            )
                            raise RuntimeError(
                                f"JWT-SVID authentication required but SPIFFE unavailable in {jwt_environment}: {e}"
                            )

                        # Fallback permitido: continuar sem metadata (apenas em desenvolvimento)
                        self.logger.warning(
                            'jwt_auth_fallback_unauthenticated',
                            environment=jwt_environment,
                            warning='Proceeding without JWT-SVID - NOT FOR PRODUCTION'
                        )
                        grpc_jwt_auth_attempts_total.labels(service="service_registry", status="fallback").inc()
                    else:
                        # Outro erro - apenas log warning e continua
                        self.logger.warning(
                            'jwt_svid_fetch_error_unexpected',
                            error=str(e),
                            fallback='unauthenticated'
                        )

            # Chamar gRPC com timeout e metadata
            response = await self.stub.DiscoverAgents(
                request,
                metadata=metadata if metadata else None,
                timeout=self.config.service_registry_timeout_seconds
            )

            # Converter AgentInfo para dict
            agents = []
            for agent_info in response.agents:
                agents.append(self._convert_agent_info(agent_info))

            self.logger.info(
                'agents_discovered',
                count=len(agents),
                capabilities=capabilities
            )

            return agents

        except grpc.RpcError as e:
            # Log especifico para erros de autenticacao
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                grpc_jwt_auth_failures_total.labels(service="service_registry", reason="unauthenticated").inc()
                self.logger.error(
                    'authentication_failed',
                    error=str(e),
                    details=e.details(),
                    hint='Verifique se JWT-SVID esta sendo enviado corretamente'
                )
            elif e.code() == grpc.StatusCode.PERMISSION_DENIED:
                grpc_jwt_auth_failures_total.labels(service="service_registry", reason="permission_denied").inc()
                self.logger.error(
                    'authorization_failed',
                    error=str(e),
                    details=e.details(),
                    hint='Verifique se SPIFFE ID esta autorizado no Service Registry'
                )
            else:
                self.logger.error(
                    'grpc_discovery_error',
                    error=str(e),
                    code=e.code(),
                    details=e.details()
                )
            raise

        except Exception as e:
            self.logger.error(
                'discovery_error',
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def _convert_agent_info(self, agent_info) -> Dict:
        """
        Converte AgentInfo protobuf para dict.

        Mapeia campos do proto service_registry.proto conforme definido:
        - agent_id, agent_type, capabilities, metadata, telemetry, status,
          registered_at, last_seen, namespace, cluster, version, schema_version

        Args:
            agent_info: Mensagem AgentInfo do proto

        Returns:
            Dict com informacoes do agente mapeadas para o modelo usado pelo scheduler
        """
        # Extrair telemetria se disponivel
        telemetry_data = {}
        if agent_info.telemetry:
            telemetry_data = {
                'success_rate': agent_info.telemetry.success_rate,
                'avg_duration_ms': agent_info.telemetry.avg_duration_ms,
                'total_executions': agent_info.telemetry.total_executions,
                'failed_executions': agent_info.telemetry.failed_executions,
                'last_execution_at': agent_info.telemetry.last_execution_at
            }

        # Converter AgentStatus enum para string
        status_map = {
            0: 'AGENT_STATUS_UNSPECIFIED',
            1: 'HEALTHY',
            2: 'UNHEALTHY',
            3: 'DEGRADED'
        }
        status_str = status_map.get(agent_info.status, 'UNKNOWN')

        # Converter AgentType enum para string
        type_map = {
            0: 'AGENT_TYPE_UNSPECIFIED',
            1: 'WORKER',
            2: 'SCOUT',
            3: 'GUARD'
        }
        type_str = type_map.get(agent_info.agent_type, 'UNKNOWN')

        return {
            'agent_id': agent_info.agent_id,
            'agent_type': type_str,
            'capabilities': list(agent_info.capabilities),
            'namespace': agent_info.namespace,
            'cluster': agent_info.cluster,
            'version': agent_info.version,
            'schema_version': agent_info.schema_version,
            'metadata': dict(agent_info.metadata) if agent_info.metadata else {},
            'status': status_str,
            'registered_at': agent_info.registered_at,
            'last_seen': agent_info.last_seen,
            'telemetry': telemetry_data
        }

    async def close(self):
        """Fecha canal gRPC gracefully."""
        if self.channel:
            self.logger.info('closing_grpc_channel')
            await self.channel.close()
            self.channel = None
            self.stub = None
