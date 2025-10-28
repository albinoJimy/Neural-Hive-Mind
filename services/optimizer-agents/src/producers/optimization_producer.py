from typing import Optional

import structlog
from confluent_kafka import Producer

from src.config.settings import get_settings
from src.models.optimization_event import OptimizationEvent

logger = structlog.get_logger()


class OptimizationProducer:
    """
    Kafka producer para tópico optimization.applied.

    Publica eventos de otimização aplicados para consumo por outros serviços.
    """

    def __init__(self, settings=None, metrics=None):
        self.settings = settings or get_settings()
        self.metrics = metrics
        self.producer: Optional[Producer] = None

    def start(self):
        """Iniciar producer Kafka."""
        try:
            conf = {
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "client.id": "optimizer-agents-producer",
                "acks": "all",
                "retries": 3,
                "max.in.flight.requests.per.connection": 5,
                "compression.type": "lz4",
                "linger.ms": 10,
                "batch.size": 32768,
            }

            self.producer = Producer(conf)

            logger.info("optimization_producer_started", bootstrap=self.settings.kafka_bootstrap_servers)

        except Exception as e:
            logger.error("optimization_producer_start_failed", error=str(e))
            raise

    async def publish_optimization(self, optimization_event: OptimizationEvent):
        """
        Publicar evento de otimização.

        Args:
            optimization_event: Evento de otimização a publicar
        """
        try:
            # Converter para dict Avro
            avro_dict = optimization_event.to_avro_dict()

            # Serializar para JSON (substituir por Avro serializer em produção)
            import json

            message = json.dumps(avro_dict).encode("utf-8")

            # Publicar
            self.producer.produce(
                topic=self.settings.kafka_optimization_topic,
                value=message,
                key=optimization_event.optimization_id.encode("utf-8"),
                callback=self._delivery_callback,
            )

            # Flush para garantir entrega
            self.producer.poll(0)

            logger.info(
                "optimization_published",
                optimization_id=optimization_event.optimization_id,
                type=optimization_event.optimization_type.value,
                target=optimization_event.target_component,
            )

            if self.metrics:
                self.metrics.increment_counter(
                    "optimizations_published_total",
                    labels={"type": optimization_event.optimization_type.value},
                )

        except Exception as e:
            logger.error(
                "optimization_publish_failed",
                optimization_id=optimization_event.optimization_id,
                error=str(e),
            )
            raise

    def _delivery_callback(self, err, msg):
        """
        Callback de entrega Kafka.

        Args:
            err: Erro (se houver)
            msg: Mensagem enviada
        """
        if err:
            logger.error(
                "kafka_delivery_failed",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                error=str(err),
            )
        else:
            logger.debug(
                "kafka_delivery_success",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )

    def flush(self, timeout: float = 10.0):
        """
        Flush de mensagens pendentes.

        Args:
            timeout: Timeout em segundos
        """
        if self.producer:
            remaining = self.producer.flush(timeout=timeout)
            if remaining > 0:
                logger.warning("kafka_flush_incomplete", remaining_messages=remaining)
            else:
                logger.debug("kafka_flush_complete")

    def stop(self):
        """Parar producer."""
        if self.producer:
            self.flush()
            logger.info("optimization_producer_stopped")
