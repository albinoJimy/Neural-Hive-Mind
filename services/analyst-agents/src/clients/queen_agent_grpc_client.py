import structlog
import grpc
import asyncio
from typing import Optional, Dict, Any, List, Tuple

from neural_hive_observability import instrument_grpc_channel
from neural_hive_observability.grpc_instrumentation import inject_grpc_context

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

from ..models.insight import AnalystInsight
from ..proto import queen_agent_pb2, queen_agent_pb2_grpc
from ..config import get_settings

logger = structlog.get_logger()

# Configurações de retry
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class QueenAgentGRPCClient:
    """Cliente gRPC para enviar insights estratégicos ao Queen Agent

    Suporta:
    - Chamadas gRPC com retry e backoff exponencial
    - mTLS via SPIFFE/SPIRE (quando habilitado)
    - Injeção de contexto de tracing e autenticação
    """

    def __init__(self, host: str = None, port: int = None):
        settings = get_settings()
        self.host = host or settings.QUEEN_AGENT_GRPC_HOST
        self.port = port or settings.QUEEN_AGENT_GRPC_PORT
        self.channel = None
        self.stub = None
        self.spiffe_manager: Optional[Any] = None
        self._settings = settings

    async def initialize(self):
        """Inicializar cliente gRPC com suporte a mTLS"""
        endpoint = f'{self.host}:{self.port}'
        settings = self._settings

        # Verificar se mTLS via SPIFFE está habilitado
        spiffe_enabled = settings.SPIFFE_ENABLED
        spiffe_enable_x509 = settings.SPIFFE_ENABLE_X509
        environment = settings.ENVIRONMENT

        spiffe_x509_enabled = (
            spiffe_enabled
            and spiffe_enable_x509
            and SECURITY_LIB_AVAILABLE
        )

        if spiffe_x509_enabled:
            try:
                # Criar configuração SPIFFE
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=settings.SPIFFE_SOCKET_PATH,
                    trust_domain=settings.SPIFFE_TRUST_DOMAIN,
                    jwt_audience=f'queen-agent.{settings.SPIFFE_TRUST_DOMAIN}',
                    jwt_ttl_seconds=3600,
                    enable_x509=True,
                    environment=environment
                )

                # Criar SPIFFE manager
                self.spiffe_manager = SPIFFEManager(spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                is_dev_env = environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=endpoint,
                    spiffe_config=spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )
                logger.info(
                    'queen_agent_mtls_channel_configured',
                    endpoint=endpoint,
                    environment=environment
                )
            except Exception as e:
                logger.error('queen_agent_mtls_setup_failed', error=str(e))
                # Em produção, falha na configuração mTLS deve ser fatal
                if environment in ['production', 'staging', 'prod']:
                    raise
                # Em desenvolvimento, fallback para insecure
                logger.warning(
                    'queen_agent_falling_back_to_insecure',
                    endpoint=endpoint
                )
                self.channel = grpc.aio.insecure_channel(
                    endpoint,
                    options=[
                        ('grpc.max_send_message_length', 4 * 1024 * 1024),
                        ('grpc.max_receive_message_length', 4 * 1024 * 1024),
                        ('grpc.keepalive_time_ms', 30000),
                        ('grpc.keepalive_timeout_ms', 10000),
                    ]
                )
        else:
            # Fallback para canal inseguro (apenas desenvolvimento)
            if environment in ['production', 'staging', 'prod']:
                logger.warning(
                    'queen_agent_insecure_channel_in_production',
                    endpoint=endpoint,
                    environment=environment
                )

            self.channel = grpc.aio.insecure_channel(
                endpoint,
                options=[
                    ('grpc.max_send_message_length', 4 * 1024 * 1024),
                    ('grpc.max_receive_message_length', 4 * 1024 * 1024),
                    ('grpc.keepalive_time_ms', 30000),
                    ('grpc.keepalive_timeout_ms', 10000),
                ]
            )

        # Instrumentar canal com tracing
        self.channel = instrument_grpc_channel(
            self.channel,
            service_name='analyst-agents',
            target_service='queen-agent'
        )

        # Criar stub do Queen Agent
        self.stub = queen_agent_pb2_grpc.QueenAgentStub(self.channel)

        # Verificar conectividade
        try:
            await asyncio.wait_for(
                self.channel.channel_ready(),
                timeout=10.0
            )
            logger.info(
                'queen_agent_grpc_client_initialized',
                host=self.host,
                port=self.port
            )
        except asyncio.TimeoutError:
            logger.warning(
                'queen_agent_grpc_channel_ready_timeout',
                endpoint=endpoint
            )

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação"""
        settings = self._settings
        spiffe_enabled = settings.SPIFFE_ENABLED

        if not spiffe_enabled or not self.spiffe_manager:
            # Incluir contexto de tracing mesmo sem SPIFFE
            return inject_grpc_context()

        try:
            trust_domain = settings.SPIFFE_TRUST_DOMAIN
            environment = settings.ENVIRONMENT
            audience = f'queen-agent.{trust_domain}'

            jwt_metadata = await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=environment
            )
            # Combinar com metadata de tracing
            tracing_metadata = inject_grpc_context()
            return list(jwt_metadata) + list(tracing_metadata)

        except Exception as e:
            logger.warning('jwt_svid_fetch_failed', error=str(e))
            environment = settings.ENVIRONMENT
            if environment in ['production', 'staging', 'prod']:
                raise
            return inject_grpc_context()

    async def close(self):
        """Fechar conexão gRPC"""
        if self.channel:
            await self.channel.close()
            logger.info('queen_agent_grpc_channel_closed')

        if self.spiffe_manager:
            try:
                await self.spiffe_manager.close()
                logger.info('queen_agent_spiffe_manager_closed')
            except Exception as e:
                logger.warning(
                    'queen_agent_spiffe_manager_close_error',
                    error=str(e)
                )

    async def send_strategic_insight(self, insight: AnalystInsight) -> bool:
        """Enviar insight estratégico ao Queen Agent com retry e backoff exponencial"""
        if not self.stub:
            logger.warning('queen_agent_stub_not_initialized')
            return False

        # Construir request proto uma vez
        request = queen_agent_pb2.SubmitInsightRequest(
            insight_id=insight.insight_id,
            version=insight.version,
            correlation_id=insight.correlation_id,
            trace_id=insight.trace_id,
            span_id=insight.span_id,
            insight_type=insight.insight_type.value,
            priority=insight.priority.value,
            title=insight.title,
            summary=insight.summary,
            detailed_analysis=insight.detailed_analysis,
            data_sources=insight.data_sources,
            metrics=insight.metrics,
            confidence_score=insight.confidence_score,
            impact_score=insight.impact_score,
            recommendations=[
                queen_agent_pb2.Recommendation(
                    action=rec.action,
                    priority=rec.priority,
                    estimated_impact=rec.estimated_impact
                ) for rec in insight.recommendations
            ],
            related_entities=[
                queen_agent_pb2.RelatedEntity(
                    entity_type=entity.entity_type,
                    entity_id=entity.entity_id,
                    relationship=entity.relationship
                ) for entity in insight.related_entities
            ],
            time_window=queen_agent_pb2.TimeWindow(
                start_timestamp=insight.time_window.start_timestamp,
                end_timestamp=insight.time_window.end_timestamp
            ),
            created_at=insight.created_at,
            valid_until=insight.valid_until,
            tags=insight.tags,
            metadata=insight.metadata,
            hash=insight.hash,
            schema_version=insight.schema_version
        )

        # Tentar enviar com retry e backoff exponencial
        for attempt in range(MAX_RETRIES):
            try:
                # Obter metadata com autenticação
                metadata = await self._get_grpc_metadata()

                # Enviar via gRPC com timeout e metadata
                response = await self.stub.SubmitInsight(
                    request,
                    metadata=metadata,
                    timeout=10.0
                )

                if response.accepted:
                    logger.info('strategic_insight_sent',
                               insight_id=insight.insight_id,
                               message=response.message,
                               attempt=attempt + 1)
                    return True
                else:
                    logger.warning('strategic_insight_rejected',
                                  insight_id=insight.insight_id,
                                  message=response.message,
                                  attempt=attempt + 1)
                    return False

            except grpc.RpcError as e:
                # Verificar se deve fazer retry
                should_retry = (
                    attempt < MAX_RETRIES - 1 and
                    e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]
                )

                logger.error('grpc_send_insight_failed',
                            error=str(e),
                            code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                            insight_id=insight.insight_id,
                            attempt=attempt + 1,
                            will_retry=should_retry)

                if should_retry:
                    # Backoff exponencial: 1s, 2s, 4s
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                else:
                    return False

            except Exception as e:
                logger.error('send_strategic_insight_failed',
                            error=str(e),
                            insight_id=insight.insight_id,
                            attempt=attempt + 1)
                return False

        return False

    async def send_operational_insight(self, insight: AnalystInsight) -> bool:
        """Enviar insight operacional ao Queen Agent (usa mesma implementação que strategic)"""
        return await self.send_strategic_insight(insight)

    async def request_strategic_decision(self, context: Dict) -> Optional[Dict]:
        """Solicitar decisão estratégica ao Queen Agent"""
        try:
            if not self.stub:
                logger.warning('queen_agent_stub_not_initialized')
                return None

            request = queen_agent_pb2.GetStrategicDecisionRequest(
                decision_id=context.get('decision_id', '')
            )

            for attempt in range(MAX_RETRIES):
                try:
                    metadata = await self._get_grpc_metadata()
                    response = await self.stub.GetStrategicDecision(
                        request,
                        metadata=metadata,
                        timeout=10.0
                    )
                    return {
                        'decision_id': response.decision_id,
                        'decision_type': response.decision_type,
                        'confidence_score': response.confidence_score,
                        'risk_score': response.risk_score,
                        'reasoning_summary': response.reasoning_summary,
                        'action': response.action,
                        'target_entities': list(response.target_entities)
                    }
                except grpc.RpcError as e:
                    should_retry = (
                        attempt < MAX_RETRIES - 1 and
                        e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]
                    )
                    logger.error(
                        'grpc_request_decision_failed',
                        error=str(e),
                        code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                        attempt=attempt + 1,
                        will_retry=should_retry
                    )
                    if should_retry:
                        backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                        await asyncio.sleep(backoff)
                        continue
                    return None

        except grpc.RpcError as e:
            logger.error('grpc_request_decision_failed', error=str(e))
            return None
        except Exception as e:
            logger.error('request_strategic_decision_failed', error=str(e))
            return None

    async def notify_anomaly(self, anomaly: Dict) -> bool:
        """Notificar anomalia detectada"""
        try:
            if not self.channel:
                logger.warning('queen_agent_channel_not_initialized')
                return False

            logger.info(
                'anomaly_notification_stub',
                metric=anomaly.get('metric_name'),
                severity=anomaly.get('severity', 'MEDIUM')
            )
            return True

        except Exception as e:
            logger.error('notify_anomaly_failed', error=str(e))
            return False

    async def get_strategic_priorities(self) -> Optional[Dict]:
        """Obter prioridades estratégicas atuais"""
        try:
            if not self.stub:
                logger.warning('queen_agent_stub_not_initialized')
                return None

            request = queen_agent_pb2.GetSystemStatusRequest()

            for attempt in range(MAX_RETRIES):
                try:
                    metadata = await self._get_grpc_metadata()
                    response = await self.stub.GetSystemStatus(
                        request,
                        metadata=metadata,
                        timeout=10.0
                    )
                    return {
                        'system_score': response.system_score,
                        'sla_compliance': response.sla_compliance,
                        'error_rate': response.error_rate,
                        'resource_saturation': response.resource_saturation,
                        'active_incidents': response.active_incidents,
                        'timestamp': response.timestamp
                    }
                except grpc.RpcError as e:
                    should_retry = (
                        attempt < MAX_RETRIES - 1 and
                        e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]
                    )
                    logger.error(
                        'grpc_get_priorities_failed',
                        error=str(e),
                        code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                        attempt=attempt + 1,
                        will_retry=should_retry
                    )
                    if should_retry:
                        backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                        await asyncio.sleep(backoff)
                        continue
                    return None

        except grpc.RpcError as e:
            logger.error('grpc_get_priorities_failed', error=str(e))
            return None
        except Exception as e:
            logger.error('get_strategic_priorities_failed', error=str(e))
            return None

    async def health_check(self) -> Dict[str, Any]:
        """Verificar saúde do Queen Agent"""
        try:
            status = await self.get_strategic_priorities()
            if status:
                return {
                    'status': 'SERVING',
                    'details': status
                }
            return {
                'status': 'NOT_SERVING',
                'error': 'Falha ao obter status do sistema'
            }
        except Exception as e:
            return {
                'status': 'NOT_SERVING',
                'error': str(e)
            }
