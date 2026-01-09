"""Cliente gRPC para comunicação com Analyst Agent"""
import grpc
import asyncio
import structlog
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

from ..proto import analyst_agent_pb2, analyst_agent_pb2_grpc

logger = structlog.get_logger()

# Configurações de retry
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class AnalystAgentGRPCClient:
    """Cliente gRPC para comunicação com Analyst Agent

    Suporta:
    - Chamadas gRPC com retry e backoff exponencial
    - mTLS via SPIFFE/SPIRE (quando habilitado)
    - Injeção de contexto de tracing
    """

    def __init__(self, config):
        self.config = config
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[analyst_agent_pb2_grpc.AnalystAgentServiceStub] = None
        self.spiffe_manager: Optional[Any] = None

    async def initialize(self):
        """Inicializar cliente gRPC com suporte a mTLS"""
        host = getattr(self.config, 'analyst_agent_grpc_host', 'analyst-agents')
        port = getattr(self.config, 'analyst_agent_grpc_port', 50051)
        endpoint = f'{host}:{port}'

        # Verificar se mTLS via SPIFFE está habilitado
        spiffe_enabled = getattr(self.config, 'spiffe_enabled', False)
        spiffe_enable_x509 = getattr(self.config, 'spiffe_enable_x509', False)
        environment = getattr(self.config, 'environment', 'development')

        spiffe_x509_enabled = (
            spiffe_enabled
            and spiffe_enable_x509
            and SECURITY_LIB_AVAILABLE
        )

        if spiffe_x509_enabled:
            # Criar configuração SPIFFE
            spiffe_config = SPIFFEConfig(
                workload_api_socket=getattr(
                    self.config, 'spiffe_socket_path',
                    'unix:///run/spire/sockets/agent.sock'
                ),
                trust_domain=getattr(
                    self.config, 'spiffe_trust_domain', 'neural-hive.local'
                ),
                jwt_audience=getattr(
                    self.config, 'spiffe_jwt_audience', 'neural-hive.local'
                ),
                jwt_ttl_seconds=getattr(self.config, 'spiffe_jwt_ttl_seconds', 3600),
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
                'analyst_agent_mtls_channel_configured',
                endpoint=endpoint,
                environment=environment
            )
        else:
            # Fallback para canal inseguro (apenas desenvolvimento)
            if environment in ['production', 'staging', 'prod']:
                logger.warning(
                    'analyst_agent_insecure_channel_in_production',
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
            service_name='analyst-agent'
        )

        # Criar stub
        self.stub = analyst_agent_pb2_grpc.AnalystAgentServiceStub(self.channel)

        # Verificar conectividade
        try:
            await asyncio.wait_for(
                self.channel.channel_ready(),
                timeout=10.0
            )
            logger.info(
                'analyst_agent_grpc_client_initialized',
                endpoint=endpoint
            )
        except asyncio.TimeoutError:
            logger.warning(
                'analyst_agent_grpc_channel_ready_timeout',
                endpoint=endpoint
            )

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação"""
        spiffe_enabled = getattr(self.config, 'spiffe_enabled', False)

        if not spiffe_enabled or not self.spiffe_manager:
            # Incluir contexto de tracing mesmo sem SPIFFE
            return inject_grpc_context()

        try:
            trust_domain = getattr(
                self.config, 'spiffe_trust_domain', 'neural-hive.local'
            )
            environment = getattr(self.config, 'environment', 'development')
            audience = f'analyst-agent.{trust_domain}'

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
            environment = getattr(self.config, 'environment', 'development')
            if environment in ['production', 'staging', 'prod']:
                raise
            return inject_grpc_context()

    async def generate_insight(
        self,
        insight_type: str,
        title: str,
        summary: str,
        detailed_analysis: str = '',
        data_sources: Optional[List[str]] = None,
        metrics: Optional[Dict[str, float]] = None,
        correlation_id: str = '',
        related_entities: Optional[List[Dict[str, str]]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        persist_to_neo4j: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Solicitar geração de insight ao Analyst Agent"""
        if not self.stub:
            logger.warning('analyst_agent_stub_not_initialized')
            return None

        # Construir entidades relacionadas
        proto_related_entities = []
        if related_entities:
            for entity in related_entities:
                proto_related_entities.append(
                    analyst_agent_pb2.RelatedEntity(
                        entity_type=entity.get('entity_type', ''),
                        entity_id=entity.get('entity_id', ''),
                        relationship=entity.get('relationship', '')
                    )
                )

        request = analyst_agent_pb2.GenerateInsightRequest(
            insight_type=insight_type,
            title=title,
            summary=summary,
            detailed_analysis=detailed_analysis,
            data_sources=data_sources or [],
            metrics=metrics or {},
            correlation_id=correlation_id,
            related_entities=proto_related_entities,
            tags=tags or [],
            metadata=metadata or {},
            persist_to_neo4j=persist_to_neo4j
        )

        for attempt in range(MAX_RETRIES):
            try:
                grpc_metadata = await self._get_grpc_metadata()
                response = await self.stub.GenerateInsight(
                    request,
                    metadata=grpc_metadata,
                    timeout=30.0
                )

                if response.success:
                    logger.info(
                        'insight_generated',
                        insight_id=response.insight.insight_id,
                        insight_type=insight_type
                    )
                    return {
                        'success': True,
                        'insight_id': response.insight.insight_id,
                        'insight_type': response.insight.insight_type,
                        'title': response.insight.title,
                        'confidence_score': response.insight.confidence_score,
                        'impact_score': response.insight.impact_score
                    }
                else:
                    logger.warning(
                        'insight_generation_failed',
                        error_message=response.error_message
                    )
                    return {
                        'success': False,
                        'error_message': response.error_message
                    }

            except grpc.RpcError as e:
                should_retry = (
                    attempt < MAX_RETRIES - 1 and
                    e.code() in [
                        grpc.StatusCode.UNAVAILABLE,
                        grpc.StatusCode.DEADLINE_EXCEEDED
                    ]
                )
                logger.error(
                    'grpc_generate_insight_failed',
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                    insight_type=insight_type,
                    attempt=attempt + 1,
                    will_retry=should_retry
                )
                if should_retry:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                return None

        return None

    async def query_insights(
        self,
        insight_type: str = '',
        priority: str = '',
        start_timestamp: int = 0,
        end_timestamp: int = 0,
        limit: int = 100,
        offset: int = 0,
        use_graph_enrichment: bool = False,
        related_entity_id: str = ''
    ) -> Optional[Dict[str, Any]]:
        """Consultar insights com filtros"""
        if not self.stub:
            logger.warning('analyst_agent_stub_not_initialized')
            return None

        request = analyst_agent_pb2.QueryInsightsRequest(
            insight_type=insight_type,
            priority=priority,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit,
            offset=offset,
            use_graph_enrichment=use_graph_enrichment,
            related_entity_id=related_entity_id
        )

        for attempt in range(MAX_RETRIES):
            try:
                grpc_metadata = await self._get_grpc_metadata()
                response = await self.stub.QueryInsights(
                    request,
                    metadata=grpc_metadata,
                    timeout=15.0
                )

                insights = []
                for insight in response.insights:
                    insights.append({
                        'insight_id': insight.insight_id,
                        'insight_type': insight.insight_type,
                        'priority': insight.priority,
                        'title': insight.title,
                        'summary': insight.summary,
                        'confidence_score': insight.confidence_score,
                        'impact_score': insight.impact_score,
                        'created_at': insight.created_at
                    })

                return {
                    'insights': insights,
                    'total_count': response.total_count
                }

            except grpc.RpcError as e:
                should_retry = (
                    attempt < MAX_RETRIES - 1 and
                    e.code() in [
                        grpc.StatusCode.UNAVAILABLE,
                        grpc.StatusCode.DEADLINE_EXCEEDED
                    ]
                )
                logger.error(
                    'grpc_query_insights_failed',
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

        return None

    async def execute_analysis(
        self,
        analysis_type: str,
        parameters: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Executar análise ad-hoc"""
        if not self.stub:
            logger.warning('analyst_agent_stub_not_initialized')
            return None

        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type=analysis_type,
            parameters=parameters or {}
        )

        for attempt in range(MAX_RETRIES):
            try:
                grpc_metadata = await self._get_grpc_metadata()
                response = await self.stub.ExecuteAnalysis(
                    request,
                    metadata=grpc_metadata,
                    timeout=30.0
                )

                return {
                    'analysis_id': response.analysis_id,
                    'results': dict(response.results),
                    'confidence': response.confidence
                }

            except grpc.RpcError as e:
                should_retry = (
                    attempt < MAX_RETRIES - 1 and
                    e.code() in [
                        grpc.StatusCode.UNAVAILABLE,
                        grpc.StatusCode.DEADLINE_EXCEEDED
                    ]
                )
                logger.error(
                    'grpc_execute_analysis_failed',
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                    analysis_type=analysis_type,
                    attempt=attempt + 1,
                    will_retry=should_retry
                )
                if should_retry:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                return None

        return None

    async def get_insight(self, insight_id: str) -> Optional[Dict[str, Any]]:
        """Buscar insight por ID"""
        if not self.stub:
            logger.warning('analyst_agent_stub_not_initialized')
            return None

        request = analyst_agent_pb2.GetInsightRequest(
            insight_id=insight_id
        )

        for attempt in range(MAX_RETRIES):
            try:
                grpc_metadata = await self._get_grpc_metadata()
                response = await self.stub.GetInsight(
                    request,
                    metadata=grpc_metadata,
                    timeout=10.0
                )

                if response.found:
                    return {
                        'found': True,
                        'insight_id': response.insight.insight_id,
                        'insight_type': response.insight.insight_type,
                        'priority': response.insight.priority,
                        'title': response.insight.title,
                        'summary': response.insight.summary,
                        'detailed_analysis': response.insight.detailed_analysis,
                        'confidence_score': response.insight.confidence_score,
                        'impact_score': response.insight.impact_score,
                        'created_at': response.insight.created_at
                    }
                else:
                    return {'found': False}

            except grpc.RpcError as e:
                should_retry = (
                    attempt < MAX_RETRIES - 1 and
                    e.code() in [
                        grpc.StatusCode.UNAVAILABLE,
                        grpc.StatusCode.DEADLINE_EXCEEDED
                    ]
                )
                logger.error(
                    'grpc_get_insight_failed',
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                    insight_id=insight_id,
                    attempt=attempt + 1,
                    will_retry=should_retry
                )
                if should_retry:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                return None

        return None

    async def health_check(self) -> Dict[str, Any]:
        """Verificar saúde do Analyst Agent"""
        if not self.stub:
            return {
                'status': 'NOT_SERVING',
                'error': 'Stub não inicializado'
            }

        try:
            request = analyst_agent_pb2.HealthCheckRequest()
            grpc_metadata = await self._get_grpc_metadata()
            response = await self.stub.HealthCheck(
                request,
                metadata=grpc_metadata,
                timeout=5.0
            )

            return {
                'status': 'SERVING' if response.healthy else 'NOT_SERVING',
                'details': {'status': response.status}
            }
        except Exception as e:
            return {
                'status': 'NOT_SERVING',
                'error': str(e)
            }

    async def close(self):
        """Fechar conexões"""
        if self.channel:
            await self.channel.close()
            logger.info('analyst_agent_grpc_channel_closed')

        if self.spiffe_manager:
            try:
                await self.spiffe_manager.close()
                logger.info('analyst_agent_spiffe_manager_closed')
            except Exception as e:
                logger.warning(
                    'analyst_agent_spiffe_manager_close_error',
                    error=str(e)
                )
