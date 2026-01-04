import asyncio
import json
from typing import Optional

import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException

from src.config.settings import get_settings

logger = structlog.get_logger()


class TelemetryConsumer:
    """
    Kafka consumer para tópico telemetry.aggregated (métricas agregadas).

    Detecta degradações de performance e identifica componentes com problemas.
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
            conf = {
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "group.id": self.settings.kafka_consumer_group_id,
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
                "max.poll.interval.ms": 300000,
            }

            self.consumer = Consumer(conf)
            self.consumer.subscribe([self.settings.kafka_telemetry_topic])

            self.running = True

            logger.info("telemetry_consumer_started", topic=self.settings.kafka_telemetry_topic)

            asyncio.create_task(self._consume_loop())

        except Exception as e:
            logger.error("telemetry_consumer_start_failed", error=str(e))
            raise

    async def _consume_loop(self):
        """Loop de consumo de mensagens."""
        loop = asyncio.get_event_loop()
        try:
            while self.running:
                # Executar poll em thread separado para não bloquear o event loop
                msg = await loop.run_in_executor(None, lambda: self.consumer.poll(timeout=1.0))

                if msg is None:
                    await asyncio.sleep(0.01)  # Yield para o event loop
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("reached_end_of_partition", partition=msg.partition())
                    else:
                        logger.error("kafka_error", error=msg.error())
                    continue

                await self._process_message(msg)
                # Commit em thread separado
                await loop.run_in_executor(None, lambda: self.consumer.commit(asynchronous=False))

                if self.metrics:
                    self.metrics.increment_counter("telemetry_consumed_total")

        except KafkaException as e:
            logger.error("kafka_consume_loop_error", error=str(e))
        except Exception as e:
            logger.error("consume_loop_error", error=str(e))

    async def _process_message(self, msg):
        """Processar mensagem de telemetria."""
        try:
            telemetry = json.loads(msg.value().decode("utf-8"))

            component = telemetry.get("component", "unknown")
            metrics_data = telemetry.get("metrics", {})

            # Detectar degradações
            degradations = self._detect_degradations(component, metrics_data)

            if degradations:
                logger.warning(
                    "degradations_detected",
                    component=component,
                    count=len(degradations),
                    degradations=degradations,
                )

                # Passar para OptimizationEngine
                if self.optimization_engine:
                    # Criar insight sintético para análise
                    synthetic_insight = {
                        "insight_id": f"telemetry-{component}",
                        "insight_type": "OPERATIONAL",
                        "priority": "HIGH",
                        "metrics": metrics_data,
                        "related_entities": [{"entity_type": "component", "entity_id": component}],
                        "correlation_id": telemetry.get("correlation_id", ""),
                    }

                    hypotheses = await self.optimization_engine.analyze_opportunity(synthetic_insight)

                    if hypotheses:
                        logger.info(
                            "hypotheses_generated_from_telemetry",
                            component=component,
                            count=len(hypotheses),
                        )

        except json.JSONDecodeError as e:
            logger.error("telemetry_deserialization_failed", error=str(e))
        except Exception as e:
            logger.error("telemetry_processing_failed", error=str(e))

    def _detect_degradations(self, component: str, metrics: dict) -> list:
        """
        Detectar degradações de performance.

        Args:
            component: Nome do componente
            metrics: Métricas do componente

        Returns:
            Lista de degradações detectadas
        """
        degradations = []

        # SLO compliance < 99%
        slo_compliance = metrics.get("slo_compliance", 1.0)
        if slo_compliance < 0.99:
            degradations.append({
                "type": "slo_violation",
                "metric": "slo_compliance",
                "value": slo_compliance,
                "threshold": 0.99,
            })

        # Latência P95 > threshold (assumir 1000ms como baseline)
        latency_p95 = metrics.get("latency_p95", 0)
        if latency_p95 > 1000:
            degradations.append({
                "type": "high_latency",
                "metric": "latency_p95",
                "value": latency_p95,
                "threshold": 1000,
            })

        # Error rate > 1%
        error_rate = metrics.get("error_rate", 0.0)
        if error_rate > 0.01:
            degradations.append({
                "type": "high_error_rate",
                "metric": "error_rate",
                "value": error_rate,
                "threshold": 0.01,
            })

        # Divergência de consenso > 5% (para consensus-engine)
        if component == "consensus-engine":
            divergence = metrics.get("divergence", 0.0)
            if divergence > 0.05:
                degradations.append({
                    "type": "high_divergence",
                    "metric": "divergence",
                    "value": divergence,
                    "threshold": 0.05,
                })

        return degradations

    def stop(self):
        """Parar consumer."""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("telemetry_consumer_stopped")
