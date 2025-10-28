from typing import Optional

import structlog
from confluent_kafka import Producer

from src.config.settings import get_settings
from src.models.experiment_request import ExperimentRequest

logger = structlog.get_logger()


class ExperimentProducer:
    """
    Kafka producer para tópico experiments.requests.

    Publica requisições de experimentos para sistema de execução (Argo Workflows).
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
                "client.id": "optimizer-agents-experiment-producer",
                "acks": "all",
                "retries": 3,
                "max.in.flight.requests.per.connection": 5,
                "compression.type": "lz4",
                "linger.ms": 10,
                "batch.size": 32768,
            }

            self.producer = Producer(conf)

            logger.info("experiment_producer_started", bootstrap=self.settings.kafka_bootstrap_servers)

        except Exception as e:
            logger.error("experiment_producer_start_failed", error=str(e))
            raise

    async def publish_experiment_request(self, experiment_request: ExperimentRequest):
        """
        Publicar requisição de experimento.

        Args:
            experiment_request: Requisição de experimento a publicar
        """
        try:
            # Converter para dict Avro
            avro_dict = experiment_request.to_avro_dict()

            # Serializar para JSON (substituir por Avro serializer em produção)
            import json

            message = json.dumps(avro_dict).encode("utf-8")

            # Publicar
            self.producer.produce(
                topic=self.settings.kafka_experiment_requests_topic,
                value=message,
                key=experiment_request.experiment_id.encode("utf-8"),
                callback=self._delivery_callback,
            )

            # Flush para garantir entrega
            self.producer.poll(0)

            logger.info(
                "experiment_request_published",
                experiment_id=experiment_request.experiment_id,
                type=experiment_request.experiment_type.value,
                hypothesis_id=experiment_request.hypothesis.get("hypothesis_id", "unknown"),
            )

            if self.metrics:
                self.metrics.increment_counter(
                    "experiment_requests_published_total",
                    labels={"type": experiment_request.experiment_type.value},
                )

        except Exception as e:
            logger.error(
                "experiment_request_publish_failed",
                experiment_id=experiment_request.experiment_id,
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
            logger.info("experiment_producer_stopped")
