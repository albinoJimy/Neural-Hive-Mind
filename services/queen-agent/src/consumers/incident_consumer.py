import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from typing import Optional
import json

from ..config import Settings
from ..services import StrategicDecisionEngine
from ..clients import RedisClient


logger = structlog.get_logger()


class IncidentConsumer:
    """Consumer Kafka para incidentes críticos dos Guard Agents"""

    def __init__(
        self,
        settings: Settings,
        decision_engine: StrategicDecisionEngine,
        redis_client: RedisClient,
        strategic_producer: 'StrategicDecisionProducer'
    ):
        self.settings = settings
        self.decision_engine = decision_engine
        self.redis_client = redis_client
        self.strategic_producer = strategic_producer
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

    async def initialize(self) -> None:
        """Inicializar consumer Kafka"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.settings.KAFKA_TOPICS_INCIDENTS,
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=self.settings.KAFKA_CONSUMER_GROUP,
                auto_offset_reset=self.settings.KAFKA_AUTO_OFFSET_RESET,
                enable_auto_commit=False,
                value_deserializer=lambda v: json.loads(v.decode('utf-8'))
            )

            await self.consumer.start()
            logger.info(
                "incident_consumer_initialized",
                topic=self.settings.KAFKA_TOPICS_INCIDENTS
            )

        except Exception as e:
            logger.error("incident_consumer_initialization_failed", error=str(e))
            raise

    async def start(self) -> None:
        """Loop principal de consumo"""
        self.running = True

        try:
            logger.info("incident_consumer_started")

            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_message(message.value)
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "incident_message_processing_failed",
                        error=str(e),
                        offset=message.offset
                    )

        except Exception as e:
            logger.error("incident_consumer_loop_failed", error=str(e))

        finally:
            logger.info("incident_consumer_stopped")

    async def stop(self) -> None:
        """Parar consumer gracefully"""
        self.running = False

        if self.consumer:
            await self.consumer.stop()
            logger.info("incident_consumer_closed")

    async def process_message(self, incident: dict) -> None:
        """Processar incidente crítico"""
        try:
            incident_id = incident.get('incident_id')
            severity = incident.get('severity')

            logger.info(
                "incident_received",
                incident_id=incident_id,
                severity=severity
            )

            # Verificar deduplicação
            if await self._is_already_processed(incident_id):
                logger.debug("incident_already_processed", incident_id=incident_id)
                return

            # Processar via Decision Engine
            strategic_decision = await self.decision_engine.process_critical_incident(incident)

            if strategic_decision:
                # Marcar como processado
                await self._mark_as_processed(incident_id)

                logger.info(
                    "strategic_decision_created_from_incident",
                    incident_id=incident_id,
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
            logger.error("process_incident_message_failed", error=str(e))
            raise

    async def _is_already_processed(self, incident_id: str) -> bool:
        """Verificar se incidente já foi processado (deduplicação)"""
        try:
            key = f"incident:processed:{incident_id}"
            data = await self.redis_client.get_cached_context(key)
            return data is not None

        except Exception as e:
            logger.error("incident_dedup_check_failed", error=str(e))
            return False

    async def _mark_as_processed(self, incident_id: str) -> None:
        """Marcar incidente como processado"""
        try:
            key = f"incident:processed:{incident_id}"
            await self.redis_client.cache_strategic_context(
                key,
                {'processed_at': int(asyncio.get_event_loop().time() * 1000)},
                ttl_seconds=3600  # 1 hora
            )

        except Exception as e:
            logger.error("incident_mark_processed_failed", error=str(e))
