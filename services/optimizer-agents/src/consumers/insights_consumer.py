import asyncio
from typing import Optional

import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException

from src.config.settings import get_settings

logger = structlog.get_logger()


class InsightsConsumer:
    """
    Kafka consumer para tópico insights.generated (publicado por Analyst Agents).

    Consome insights analíticos e identifica oportunidades de otimização.
    """

    def __init__(self, settings=None, optimization_engine=None, metrics=None):
        self.settings = settings or get_settings()
        self.optimization_engine = optimization_engine
        self.metrics = metrics
        self.consumer: Optional[Consumer] = None
        self.running = False

    def start(self):
        """Iniciar consumer Kafka."""
        try:
            # Configurar consumer
            conf = {
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "group.id": self.settings.kafka_consumer_group_id,
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
                "max.poll.interval.ms": 300000,
            }

            self.consumer = Consumer(conf)
            self.consumer.subscribe([self.settings.kafka_insights_topic])

            self.running = True

            logger.info("insights_consumer_started", topic=self.settings.kafka_insights_topic)

            # Loop de consumo
            asyncio.create_task(self._consume_loop())

        except Exception as e:
            logger.error("insights_consumer_start_failed", error=str(e))
            raise

    async def _consume_loop(self):
        """Loop de consumo de mensagens."""
        try:
            while self.running:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("reached_end_of_partition", partition=msg.partition())
                    else:
                        logger.error("kafka_error", error=msg.error())
                    continue

                # Processar mensagem
                await self._process_message(msg)

                # Commit manual
                self.consumer.commit(asynchronous=False)

                # Atualizar métrica
                if self.metrics:
                    self.metrics.increment_counter("insights_consumed_total")

        except KafkaException as e:
            logger.error("kafka_consume_loop_error", error=str(e))
        except Exception as e:
            logger.error("consume_loop_error", error=str(e))

    async def _process_message(self, msg):
        """
        Processar mensagem de insight.

        Args:
            msg: Mensagem Kafka
        """
        try:
            # Deserializar (assumindo JSON por enquanto)
            import json

            insight = json.loads(msg.value().decode("utf-8"))

            insight_id = insight.get("insight_id", "unknown")
            insight_type = insight.get("insight_type", "unknown")
            priority = insight.get("priority", "MEDIUM")

            logger.info(
                "insight_received",
                insight_id=insight_id,
                type=insight_type,
                priority=priority,
            )

            # Filtrar insights por relevância (apenas HIGH e CRITICAL)
            if priority not in ["HIGH", "CRITICAL"]:
                logger.debug("insight_filtered_low_priority", insight_id=insight_id, priority=priority)
                return

            # Passar para OptimizationEngine
            if self.optimization_engine:
                hypotheses = self.optimization_engine.analyze_opportunity(insight)

                if hypotheses:
                    logger.info(
                        "hypotheses_generated_from_insight",
                        insight_id=insight_id,
                        count=len(hypotheses),
                    )

                    # TODO: Submeter hipóteses para validação via ExperimentManager
                    for hypothesis in hypotheses:
                        logger.info(
                            "hypothesis_generated",
                            hypothesis_id=hypothesis.hypothesis_id,
                            type=hypothesis.optimization_type.value,
                            expected_improvement=hypothesis.expected_improvement,
                            risk=hypothesis.risk_score,
                        )

                        if self.metrics:
                            self.metrics.record_hypothesis_generated(hypothesis.optimization_type.value)

        except json.JSONDecodeError as e:
            logger.error("insight_deserialization_failed", error=str(e))
        except Exception as e:
            logger.error("insight_processing_failed", error=str(e))

    def stop(self):
        """Parar consumer."""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("insights_consumer_stopped")
