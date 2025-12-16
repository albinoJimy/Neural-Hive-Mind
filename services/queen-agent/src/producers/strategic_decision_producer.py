import structlog
from aiokafka import AIOKafkaProducer
from typing import Optional
import json

from neural_hive_observability import instrument_kafka_producer

from ..config import Settings
from ..models import StrategicDecision


logger = structlog.get_logger()


class StrategicDecisionProducer:
    """Producer Kafka para publicar decisões estratégicas"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.producer: Optional[AIOKafkaProducer] = None

    async def initialize(self) -> None:
        """Inicializar producer Kafka"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',  # Garantir que todos os replicas confirmem
                enable_idempotence=True,  # Evitar duplicatas
                max_in_flight_requests_per_connection=1,  # Garantir ordem
                compression_type='snappy'
            )

            self.producer = instrument_kafka_producer(self.producer)
            await self.producer.start()
            logger.info(
                "strategic_decision_producer_initialized",
                topic=self.settings.KAFKA_TOPICS_STRATEGIC
            )

        except Exception as e:
            logger.error("strategic_decision_producer_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fechar producer"""
        if self.producer:
            await self.producer.stop()
            logger.info("strategic_decision_producer_closed")

    async def publish_decision(self, decision: StrategicDecision) -> bool:
        """
        Publicar decisão estratégica no tópico Kafka

        Returns:
            bool: True se publicado com sucesso
        """
        try:
            # Serializar para dict Avro-compatible
            decision_dict = decision.to_avro_dict()

            # Headers para rastreabilidade
            headers = [
                ('correlation_id', decision.correlation_id.encode('utf-8')),
                ('trace_id', decision.trace_id.encode('utf-8')),
                ('decision_type', decision.decision_type.value.encode('utf-8'))
            ]

            # Enviar com key=decision_id para particionamento consistente
            await self.producer.send_and_wait(
                self.settings.KAFKA_TOPICS_STRATEGIC,
                key=decision.decision_id.encode('utf-8'),
                value=decision_dict,
                headers=headers
            )

            logger.info(
                "strategic_decision_published",
                decision_id=decision.decision_id,
                decision_type=decision.decision_type.value,
                topic=self.settings.KAFKA_TOPICS_STRATEGIC
            )

            return True

        except Exception as e:
            logger.error(
                "strategic_decision_publish_failed",
                decision_id=decision.decision_id,
                error=str(e)
            )
            return False
