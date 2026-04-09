"""Kafka Producer para publicar eventos de documento gerado

Publica no tópico learning.doc.generated quando um novo documento
de aprendizado é criado.
"""

import asyncio
import json
from typing import Any, Optional

import structlog
from aiokafka import AIOKafkaProducer

from src.config import get_settings

logger = structlog.get_logger()


class KafkaLearningDocProducer:
    """Producer Kafka para eventos de documento gerado"""

    def __init__(self):
        """Inicializa o producer"""
        self.settings = get_settings()
        self._producer: Optional[AIOKafkaProducer] = None
        self._topic = self.settings.kafka_learning_doc_generated_topic

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0) -> None:
        """Inicia o producer Kafka

        Args:
            max_retries: Máximo de tentativas de conexão
            initial_delay: Delay inicial entre tentativas
        """
        logger.info(
            "iniciando_kafka_producer",
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            topic=self._topic,
        )

        producer_config = {
            "bootstrap_servers": self.settings.kafka_bootstrap_servers,
            "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
            "key_serializer": lambda k: k.encode("utf-8") if k else None,
            "acks": "all",
            "compression_type": "gzip",
            "linger_ms": 10,
            "max_request_size": 1048576,  # 1MB
        }

        # Configurar SASL se necessário
        if self.settings.kafka_security_protocol != "PLAINTEXT":
            producer_config.update(
                {
                    "security_protocol": self.settings.kafka_security_protocol,
                    "sasl_mechanism": self.settings.kafka_sasl_mechanism,
                    "sasl_plain_username": self.settings.kafka_sasl_username,
                    "sasl_plain_password": self.settings.kafka_sasl_password,
                }
            )

        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                self._producer = AIOKafkaProducer(**producer_config)
                await self._producer.start()

                logger.info(
                    "kafka_producer_iniciado",
                    bootstrap_servers=self.settings.kafka_bootstrap_servers,
                    topic=self._topic,
                )
                return

            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(
                    "kafka_producer_start_falhou",
                    error=str(e),
                    retry_count=retry_count,
                    max_retries=max_retries,
                )
                if retry_count < max_retries:
                    await asyncio.sleep(initial_delay * (2 ** (retry_count - 1)))

        # Todas as tentativas falharam
        logger.error(
            "kafka_producer_start_falhou_todas_tentativas",
            error=str(last_error),
            max_retries=max_retries,
        )
        raise RuntimeError(
            f"Falha ao iniciar Kafka producer após {max_retries} tentativas: {last_error}"
        )

    async def stop(self) -> None:
        """Para o producer gracefulmente"""
        if self._producer:
            logger.info("parando_kafka_producer")
            await self._producer.stop()
            logger.info("kafka_producer_parado")
        self._producer = None

    async def publish_doc_generated(
        self,
        doc_id: str,
        doc_type: str,
        title: str,
        metadata: dict[str, Any],
        key: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> bool:
        """Publica evento de documento gerado

        Args:
            doc_id: ID do documento
            doc_type: Tipo do documento
            title: Título do documento
            metadata: Metadados adicionais
            key: Chave para partição (default: doc_id)
            timeout_ms: Timeout para publicação

        Returns:
            True se publicado com sucesso
        """
        if not self._producer:
            logger.warning("kafka_producer_nao_inicializado", doc_id=doc_id)
            return False

        if key is None:
            key = doc_id

        event = {
            "event_type": "learning.doc.generated",
            "doc_id": doc_id,
            "doc_type": doc_type,
            "title": title,
            "generated_at": metadata.get("generated_at"),
            "metadata": metadata,
        }

        try:
            await asyncio.wait_for(
                self._producer.send_and_wait(self._topic, value=event, key=key),
                timeout=timeout_ms / 1000.0,
            )

            logger.info(
                "doc_generated_event_published",
                doc_id=doc_id,
                doc_type=doc_type,
                topic=self._topic,
            )
            return True

        except asyncio.TimeoutError:
            logger.error(
                "doc_generated_publish_timeout",
                doc_id=doc_id,
                timeout_ms=timeout_ms,
            )
            return False

        except Exception as e:
            logger.error(
                "doc_generated_publish_failed",
                doc_id=doc_id,
                error=str(e),
            )
            return False

    async def health_check(self) -> bool:
        """Verifica se o producer está saudável

        Returns:
            True se saudável
        """
        return self._producer is not None


# Instância global
_producer: Optional[KafkaLearningDocProducer] = None


async def get_kafka_producer() -> KafkaLearningDocProducer:
    """Obtém ou cria a instância global do producer

    Returns:
        Instância do KafkaLearningDocProducer

    Raises:
        RuntimeError: Se o producer falhar ao inicializar
    """
    global _producer

    if _producer is None:
        _producer = KafkaLearningDocProducer()
        await _producer.start()

    return _producer


async def close_kafka_producer() -> None:
    """Fecha a instância global do producer"""
    global _producer

    if _producer:
        await _producer.stop()
        _producer = None
