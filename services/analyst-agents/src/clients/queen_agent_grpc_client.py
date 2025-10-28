import structlog
import grpc
import asyncio
from typing import Optional, Dict
from ..models.insight import AnalystInsight
from ..proto import queen_agent_pb2, queen_agent_pb2_grpc

logger = structlog.get_logger()

# Configurações de retry
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class QueenAgentGRPCClient:
    """Cliente gRPC para enviar insights estratégicos ao Queen Agent"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None

    async def initialize(self):
        """Inicializar cliente gRPC"""
        try:
            # Criar canal gRPC
            self.channel = grpc.aio.insecure_channel(f'{self.host}:{self.port}')

            # Aguardar canal estar pronto
            await self.channel.channel_ready()

            # Criar stub do Queen Agent
            self.stub = queen_agent_pb2_grpc.QueenAgentStub(self.channel)

            logger.info('queen_agent_grpc_client_initialized', host=self.host, port=self.port)
        except Exception as e:
            logger.error('queen_agent_grpc_client_initialization_failed', error=str(e))
            raise

    async def close(self):
        """Fechar conexão gRPC"""
        if self.channel:
            await self.channel.close()
        logger.info('queen_agent_grpc_client_closed')

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
                # Enviar via gRPC com timeout
                response = await self.stub.SubmitInsight(request, timeout=10.0)

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
                            code=e.code() if hasattr(e, 'code') else 'UNKNOWN',
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
            if not self.channel:
                logger.warning('queen_agent_channel_not_initialized')
                return None

            # TODO: Implementar quando proto do Queen Agent estiver disponível
            logger.info('strategic_decision_request_stub', context_keys=list(context.keys()))
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
            if not self.channel:
                logger.warning('queen_agent_channel_not_initialized')
                return None

            # TODO: Implementar quando proto do Queen Agent estiver disponível
            logger.info('get_strategic_priorities_stub')
            return None

        except grpc.RpcError as e:
            logger.error('grpc_get_priorities_failed', error=str(e))
            return None
        except Exception as e:
            logger.error('get_strategic_priorities_failed', error=str(e))
            return None
