"""
Training Data Producer - Kafka producer para dados de treinamento (EPIC 3.3)

Publica feedbacks continuos enriquecidos com features NLP no topico de treinamento ML.
"""

import json
from typing import Optional

import structlog
from confluent_kafka import Producer

from neural_hive_observability.context import ContextManager
from src.config.settings import Settings
from src.models.continuous_feedback import TrainingDataKafkaMessage

logger = structlog.get_logger()


class TrainingDataProducer:
    """
    Kafka producer para enviar dados de treinamento ML.

    Publica mensagens no topico ml.training_data com feedbacks
    enriquecidos com features NLP para treinamento continuo.
    """

    def __init__(self, settings: Settings, context_manager: Optional[ContextManager] = None):
        self.settings = settings
        self.producer: Optional[Producer] = None
        self.context_manager = context_manager

    async def initialize(self):
        """Inicializa producer Kafka com configuracoes do approval service"""
        producer_config = {
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "enable.idempotence": self.settings.kafka_enable_idempotence,
            "acks": "all",
            "compression.type": "snappy",
            "linger.ms": 10,
            "batch.size": 32768,
        }

        # Adiciona configuracao de seguranca se necessario
        if self.settings.kafka_security_protocol != "PLAINTEXT":
            producer_config.update(
                {
                    "security.protocol": self.settings.kafka_security_protocol,
                    "sasl.mechanism": self.settings.kafka_sasl_mechanism,
                    "sasl.username": self.settings.kafka_sasl_username,
                    "sasl.password": self.settings.kafka_sasl_password,
                }
            )

        self.producer = Producer(producer_config)

        logger.info(
            "Training Data Producer inicializado",
            topic="ml.training_data",
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
        )

    async def send_training_data(
        self,
        message: TrainingDataKafkaMessage,
        correlation_id: Optional[str] = None,
    ):
        """
        Envia dados de treinamento para Kafka.

        Args:
            message: TrainingDataKafkaMessage com feedback enriquecido
            correlation_id: ID de correlacao opcional
        """
        topic = "ml.training_data"

        try:
            # Serializa mensagem como JSON
            value = json.dumps(message.to_kafka_dict(), default=str).encode("utf-8")

            # Prepara headers
            headers = {
                "prediction-id": message.prediction_id,
                "content-type": "application/json",
                "source": "approval-service",
            }

            # Adiciona correlation_id
            if correlation_id:
                headers["correlation-id"] = correlation_id

            # Injeta contexto OpenTelemetry se disponivel
            if self.context_manager:
                headers_dict = self.context_manager.inject_http_headers(headers)
                headers = [
                    (k, v.encode("utf-8") if isinstance(v, str) else v)
                    for k, v in headers_dict.items()
                ]
            else:
                headers = [
                    (k, v.encode("utf-8") if isinstance(v, str) else v) for k, v in headers.items()
                ]

            # Partition key pelo prediction_id
            key = message.prediction_id.encode("utf-8")

            # Produz mensagem
            self.producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers=headers,
                on_delivery=self._delivery_callback,
            )

            # Flush assincrono (nao bloqueia)
            self.producer.poll(0)

            logger.info(
                "Training data publicado",
                prediction_id=message.prediction_id,
                prediction=message.prediction,
                actual=message.actual_result,
                has_nlp_features=message.nlp_features is not None,
                topic=topic,
            )

        except Exception as e:
            logger.error(
                "Erro ao publicar training data",
                prediction_id=message.prediction_id,
                error=str(e),
            )
            raise

    def _delivery_callback(self, err, msg):
        """Callback de entrega de mensagens"""
        if err:
            logger.error("Falha na entrega do training data", error=err, topic=msg.topic())
        else:
            logger.debug(
                "Training data entregue",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )

    async def flush(self):
        """Forca flush de mensagens pendentes"""
        if self.producer:
            self.producer.flush(timeout=10)

    async def close(self):
        """Fecha producer gracefulmente"""
        if self.producer:
            self.producer.flush(timeout=30)
            logger.info("Training Data Producer fechado")
