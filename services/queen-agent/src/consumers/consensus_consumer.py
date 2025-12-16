import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from typing import Optional
import json

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import (
    extract_context_from_headers,
    set_baggage
)

from ..config import Settings
from ..services import StrategicDecisionEngine


logger = structlog.get_logger()


class ConsensusConsumer:
    """Consumer Kafka para decisões consolidadas do Consensus Engine"""

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
                self.settings.KAFKA_TOPICS_CONSENSUS,
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=self.settings.KAFKA_CONSUMER_GROUP,
                auto_offset_reset=self.settings.KAFKA_AUTO_OFFSET_RESET,
                enable_auto_commit=False,  # Commit manual para controle transacional
                value_deserializer=lambda v: json.loads(v.decode('utf-8'))
            )

            self.consumer = instrument_kafka_consumer(self.consumer)
            await self.consumer.start()
            logger.info(
                "consensus_consumer_initialized",
                topic=self.settings.KAFKA_TOPICS_CONSENSUS,
                group=self.settings.KAFKA_CONSUMER_GROUP
            )

        except Exception as e:
            logger.error("consensus_consumer_initialization_failed", error=str(e))
            raise

    async def start(self) -> None:
        """Loop principal de consumo"""
        self.running = True

        try:
            logger.info("consensus_consumer_started")

            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_message(message)

                    # Commit manual após processamento bem-sucedido
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "consensus_message_processing_failed",
                        error=str(e),
                        offset=message.offset
                    )
                    # Não commitar em caso de erro - mensagem será reprocessada

        except Exception as e:
            logger.error("consensus_consumer_loop_failed", error=str(e))

        finally:
            logger.info("consensus_consumer_stopped")

    async def stop(self) -> None:
        """Parar consumer gracefully"""
        self.running = False

        if self.consumer:
            await self.consumer.stop()
            logger.info("consensus_consumer_closed")

    async def process_message(self, message) -> None:
        """Processar mensagem de decisão consolidada"""
        try:
            headers_dict = {k: v for k, v in (message.headers or [])}
            extract_context_from_headers(headers_dict)

            decision_data = message.value
            decision_id = decision_data.get('decision_id')
            intent_id = decision_data.get("intent_id")
            plan_id = decision_data.get("plan_id")
            if intent_id:
                set_baggage("intent_id", intent_id)
            if plan_id:
                set_baggage("plan_id", plan_id)

            logger.info("consensus_decision_received", decision_id=decision_id)

            # Processar via Decision Engine
            strategic_decision = await self.decision_engine.process_consolidated_decision(decision_data)

            if strategic_decision:
                logger.info(
                    "strategic_decision_created_from_consensus",
                    decision_id=decision_id,
                    strategic_decision_id=strategic_decision.decision_id,
                    decision_type=strategic_decision.decision_type.value
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

            else:
                logger.debug(
                    "consensus_decision_no_strategic_action",
                    decision_id=decision_id
                )

        except Exception as e:
            logger.error("process_consensus_message_failed", error=str(e))
            raise
