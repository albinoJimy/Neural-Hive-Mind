import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import json
from typing import Optional
from ..models.insight import AnalystInsight, InsightType
from ..observability.metrics import record_insight_generated

logger = structlog.get_logger()


class InsightProducer:
    def __init__(self, bootstrap_servers: str, default_topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.default_topic = default_topic
        self.producer = None
        self.topic_mapping = {
            InsightType.STRATEGIC: 'insights.strategic',
            InsightType.OPERATIONAL: 'insights.operational',
            InsightType.PREDICTIVE: 'insights.analyzed',
            InsightType.CAUSAL: 'insights.analyzed',
            InsightType.ANOMALY: 'insights.analyzed'
        }

    async def initialize(self):
        """Inicializar producer Kafka"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                enable_idempotence=True,
                acks='all',
                compression_type='snappy'
            )
            await self.producer.start()
            logger.info('insight_producer_initialized', bootstrap_servers=self.bootstrap_servers)
        except Exception as e:
            logger.error('insight_producer_initialization_failed', error=str(e))
            raise

    async def close(self):
        """Fechar producer"""
        if self.producer:
            await self.producer.stop()
        logger.info('insight_producer_closed')

    async def publish_insight(self, insight: AnalystInsight, topic_override: Optional[str] = None) -> bool:
        """Publicar insight no Kafka"""
        try:
            # Determinar tópico baseado no tipo de insight
            topic = topic_override or self.topic_mapping.get(insight.insight_type, self.default_topic)

            # Validar insight
            if not insight.hash:
                insight.hash = insight.calculate_hash()

            # Serializar para dict
            message = insight.model_dump()

            # Usar insight_id como chave para particionamento consistente
            key = insight.insight_id

            # Adicionar headers OpenTelemetry
            headers = [
                ('trace_id', insight.trace_id.encode('utf-8')),
                ('span_id', insight.span_id.encode('utf-8')),
                ('correlation_id', insight.correlation_id.encode('utf-8'))
            ]

            # Publicar
            await self.producer.send_and_wait(
                topic,
                value=message,
                key=key,
                headers=headers
            )

            # Registrar métrica
            record_insight_generated(insight.insight_type.value, insight.priority.value)

            logger.info(
                'insight_published',
                insight_id=insight.insight_id,
                topic=topic,
                type=insight.insight_type.value,
                priority=insight.priority.value
            )

            return True

        except KafkaError as e:
            logger.error('kafka_publish_failed', error=str(e), insight_id=insight.insight_id)
            return False
        except Exception as e:
            logger.error('publish_insight_failed', error=str(e), insight_id=insight.insight_id)
            return False

    async def publish_batch(self, insights: list[AnalystInsight]) -> int:
        """Publicar lote de insights"""
        success_count = 0

        try:
            for insight in insights:
                if await self.publish_insight(insight):
                    success_count += 1

            logger.info('batch_published', total=len(insights), success=success_count)
            return success_count

        except Exception as e:
            logger.error('publish_batch_failed', error=str(e))
            return success_count
