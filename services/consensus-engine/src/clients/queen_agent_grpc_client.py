"""Cliente gRPC para comunicação com Queen Agent"""
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

from ..proto import queen_agent_pb2, queen_agent_pb2_grpc

logger = structlog.get_logger()

# Configurações de retry
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class QueenAgentGRPCClient:
    """Cliente gRPC para comunicação com Queen Agent

    Suporta:
    - Chamadas gRPC com retry e backoff exponencial
    - mTLS via SPIFFE/SPIRE (quando habilitado)
    - Injeção de contexto de tracing
    """

    def __init__(self, config):
        self.config = config
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[queen_agent_pb2_grpc.QueenAgentStub] = None
        self.spiffe_manager: Optional[Any] = None

    async def initialize(self):
        """Inicializar cliente gRPC com suporte a mTLS"""
        host = getattr(self.config, 'queen_agent_grpc_host', 'queen-agent')
        port = getattr(self.config, 'queen_agent_grpc_port', 50051)
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
                'queen_agent_mtls_channel_configured',
                endpoint=endpoint,
                environment=environment
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
            service_name='queen-agent'
        )

        # Criar stub
        self.stub = queen_agent_pb2_grpc.QueenAgentStub(self.channel)

        # Verificar conectividade
        try:
            await asyncio.wait_for(
                self.channel.channel_ready(),
                timeout=10.0
            )
            logger.info(
                'queen_agent_grpc_client_initialized',
                endpoint=endpoint
            )
        except asyncio.TimeoutError:
            logger.warning(
                'queen_agent_grpc_channel_ready_timeout',
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
            environment = getattr(self.config, 'environment', 'development')
            if environment in ['production', 'staging', 'prod']:
                raise
            return inject_grpc_context()

    async def get_strategic_decision(
        self,
        decision_id: str
    ) -> Optional[Dict[str, Any]]:
        """Buscar decisão estratégica por ID"""
        if not self.stub:
            logger.warning('queen_agent_stub_not_initialized')
            return None

        request = queen_agent_pb2.GetStrategicDecisionRequest(
            decision_id=decision_id
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
                    'target_entities': list(response.target_entities),
                    'created_at': response.created_at
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
                    'grpc_get_strategic_decision_failed',
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                    decision_id=decision_id,
                    attempt=attempt + 1,
                    will_retry=should_retry
                )
                if should_retry:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                return None

        return None

    async def make_strategic_decision(
        self,
        event_type: str,
        source_id: str,
        trigger_data: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Solicitar criação de nova decisão estratégica"""
        if not self.stub:
            logger.warning('queen_agent_stub_not_initialized')
            return None

        request = queen_agent_pb2.MakeStrategicDecisionRequest(
            event_type=event_type,
            source_id=source_id,
            trigger_data=trigger_data or {}
        )

        for attempt in range(MAX_RETRIES):
            try:
                metadata = await self._get_grpc_metadata()
                response = await self.stub.MakeStrategicDecision(
                    request,
                    metadata=metadata,
                    timeout=30.0  # Timeout maior para decisões
                )

                if response.success:
                    logger.info(
                        'strategic_decision_created',
                        decision_id=response.decision_id,
                        decision_type=response.decision_type
                    )
                    return {
                        'success': True,
                        'decision_id': response.decision_id,
                        'decision_type': response.decision_type,
                        'confidence_score': response.confidence_score,
                        'risk_score': response.risk_score,
                        'reasoning_summary': response.reasoning_summary,
                        'message': response.message
                    }
                else:
                    logger.warning(
                        'strategic_decision_creation_failed',
                        message=response.message
                    )
                    return {
                        'success': False,
                        'message': response.message
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
                    'grpc_make_strategic_decision_failed',
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'UNKNOWN',
                    event_type=event_type,
                    attempt=attempt + 1,
                    will_retry=should_retry
                )
                if should_retry:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                return None

        return None

    async def get_system_status(self) -> Optional[Dict[str, Any]]:
        """Obter status geral do sistema via Queen Agent"""
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
                    e.code() in [
                        grpc.StatusCode.UNAVAILABLE,
                        grpc.StatusCode.DEADLINE_EXCEEDED
                    ]
                )
                logger.error(
                    'grpc_get_system_status_failed',
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

    async def list_strategic_decisions(
        self,
        decision_type: Optional[str] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Listar decisões estratégicas com filtros"""
        if not self.stub:
            logger.warning('queen_agent_stub_not_initialized')
            return None

        request = queen_agent_pb2.ListStrategicDecisionsRequest(
            decision_type=decision_type or '',
            start_date=start_date or 0,
            end_date=end_date or 0,
            limit=limit,
            offset=offset
        )

        for attempt in range(MAX_RETRIES):
            try:
                metadata = await self._get_grpc_metadata()
                response = await self.stub.ListStrategicDecisions(
                    request,
                    metadata=metadata,
                    timeout=15.0
                )

                decisions = []
                for dec in response.decisions:
                    decisions.append({
                        'decision_id': dec.decision_id,
                        'decision_type': dec.decision_type,
                        'confidence_score': dec.confidence_score,
                        'risk_score': dec.risk_score,
                        'reasoning_summary': dec.reasoning_summary,
                        'action': dec.action,
                        'target_entities': list(dec.target_entities),
                        'created_at': dec.created_at
                    })

                return {
                    'decisions': decisions,
                    'total': response.total
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
                    'grpc_list_strategic_decisions_failed',
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

    async def health_check(self) -> Dict[str, Any]:
        """Verificar saúde do Queen Agent"""
        try:
            status = await self.get_system_status()
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

    async def close(self):
        """Fechar conexões"""
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
