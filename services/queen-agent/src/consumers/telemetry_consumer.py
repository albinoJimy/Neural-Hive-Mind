import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from typing import Optional
import json

from ..config import Settings
from ..services import StrategicDecisionEngine


logger = structlog.get_logger()


class TelemetryConsumer:
    """Consumer Kafka para eventos de telemetria agregada"""

    def __init__(
        self,
        settings: Settings,
        decision_engine: StrategicDecisionEngine,
        strategic_producer: 'StrategicDecisionProducer'
    ):
        self.settings = settings
        self.decision_engine = decision_engine
        self.strategic_producer = strategic_producer
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

    async def initialize(self) -> None:
        """Inicializar consumer Kafka"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.settings.KAFKA_TOPICS_TELEMETRY,
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=self.settings.KAFKA_CONSUMER_GROUP,
                auto_offset_reset=self.settings.KAFKA_AUTO_OFFSET_RESET,
                enable_auto_commit=False,
                value_deserializer=lambda v: json.loads(v.decode('utf-8'))
            )

            await self.consumer.start()
            logger.info(
                "telemetry_consumer_initialized",
                topic=self.settings.KAFKA_TOPICS_TELEMETRY
            )

        except Exception as e:
            logger.error("telemetry_consumer_initialization_failed", error=str(e))
            raise

    async def start(self) -> None:
        """Loop principal de consumo"""
        self.running = True

        try:
            logger.info("telemetry_consumer_started")

            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_message(message.value)
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "telemetry_message_processing_failed",
                        error=str(e),
                        offset=message.offset
                    )

        except Exception as e:
            logger.error("telemetry_consumer_loop_failed", error=str(e))

        finally:
            logger.info("telemetry_consumer_stopped")

    async def stop(self) -> None:
        """Parar consumer gracefully"""
        self.running = False

        if self.consumer:
            await self.consumer.stop()
            logger.info("telemetry_consumer_closed")

    async def process_message(self, event: dict) -> None:
        """Processar evento de telemetria"""
        try:
            metric_type = event.get('metric_type')
            value = event.get('value')

            logger.debug("telemetry_event_received", metric_type=metric_type, value=value)

            # Processar via Decision Engine
            strategic_decision = await self.decision_engine.process_telemetry_event(event)

            if strategic_decision:
                logger.info(
                    "strategic_decision_created_from_telemetry",
                    metric_type=metric_type,
                    strategic_decision_id=strategic_decision.decision_id
                )

                # Publicar decisão estratégica no Kafka
                published = await self.strategic_producer.publish_decision(strategic_decision)
                if not published:
                    logger.error(
                        "failed_to_publish_strategic_decision",
                        strategic_decision_id=strategic_decision.decision_id
                    )
                    raise Exception("Failed to publish strategic decision to Kafka")

                # Executar ação da decisão estratégica
                action_executed = await self.decision_engine.execute_decision_action(strategic_decision)
                if not action_executed:
                    logger.error(
                        "failed_to_execute_decision_action",
                        strategic_decision_id=strategic_decision.decision_id,
                        action=strategic_decision.decision.action
                    )
                    raise Exception("Failed to execute decision action")

        except Exception as e:
            logger.error("process_telemetry_message_failed", error=str(e))
            raise
