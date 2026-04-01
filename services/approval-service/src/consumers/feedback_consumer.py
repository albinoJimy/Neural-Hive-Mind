"""
Feedback Consumer - Kafka consumer para feedback de especialistas

Consome mensagens do topico specialist_feedback e as envia para o
IncrementalLearner para aprendizado online incremental.
"""

import asyncio
import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog
from confluent_kafka import Consumer, KafkaError, Message
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.config.settings import Settings

logger = structlog.get_logger()


# Schema Avro para SpecialistFeedback (inline para evitar dependencias externas)
SPECIALIST_FEEDBACK_SCHEMA = """
{
  "type": "record",
  "name": "SpecialistFeedback",
  "namespace": "com.neuralhive.specialist",
  "fields": [
    {"name": "feedback_id", "type": "string"},
    {"name": "opinion_id", "type": "string"},
    {"name": "plan_id", "type": "string"},
    {"name": "specialist_type", "type": "string"},
    {"name": "human_rating", "type": "double"},
    {"name": "human_recommendation", "type": ["null", "string"], "default": null},
    {"name": "feedback_notes", "type": ["null", "string"], "default": null},
    {"name": "submitted_at", "type": ["null", "long"], "default": null},
    {"name": "submitted_by", "type": ["null", "string"], "default": null},
    {"name": "intent_raw_text", "type": ["null", "string"], "default": null},
    {"name": "nlp_features", "type": ["null", {
      "type": "record",
      "name": "NLPFeatures",
      "fields": [
        {"name": "sentiment_score", "type": ["null", "double"], "default": null},
        {"name": "urgency_score", "type": ["null", "double"], "default": null},
        {"name": "complexity_score", "type": ["null", "double"], "default": null},
        {"name": "primary_domain", "type": ["null", "string"], "default": null}
      ]
    }}, "default": null},
    {"name": "specialist_recommendation", "type": ["null", "string"], "default": null},
    {"name": "specialist_confidence", "type": ["null", "double"], "default": null}
  ]
}
"""


class FeedbackBuffer:
    """
    Buffer circular para armazenar feedbacks antes do envio ao IncrementalLearner.

    Caracteristicas:
    - Tamanho maximo configuravel
    - Thread-safe para uso com asyncio
    - Mantem ordem de insercao
    """

    def __init__(self, max_size: int = 100):
        """
        Inicializa buffer de feedbacks.

        Args:
            max_size: Tamanho maximo do buffer
        """
        self._buffer: deque = deque(maxlen=max_size)
        self._max_size = max_size
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        """Retorna numero de itens no buffer."""
        return len(self._buffer)

    @property
    def is_full(self) -> bool:
        """Retorna se buffer esta cheio."""
        return len(self._buffer) >= self._max_size

    async def add(self, feedback: Dict[str, Any]) -> bool:
        """
        Adiciona feedback ao buffer.

        Args:
            feedback: Dicionario com dados do feedback

        Returns:
            True se adicionado, False se buffer cheio
        """
        async with self._lock:
            if self.is_full:
                return False
            self._buffer.append(feedback)
            return True

    async def get_batch(self, batch_size: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retorna um lote de feedbacks do buffer.

        Args:
            batch_size: Tamanho do lote (default: todos)

        Returns:
            Lista de feedbacks
        """
        async with self._lock:
            if batch_size is None:
                batch = list(self._buffer)
                self._buffer.clear()
            else:
                batch = []
                for _ in range(min(batch_size, len(self._buffer))):
                    if self._buffer:
                        batch.append(self._buffer.popleft())
            return batch

    async def peek(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        Espia feedbacks sem remove-los do buffer.

        Args:
            count: Numero de feedbacks para espiar

        Returns:
            Lista de feedbacks (max count)
        """
        async with self._lock:
            return list(self._buffer)[:count]

    def clear(self):
        """Limpa o buffer."""
        self._buffer.clear()


class FeedbackConsumer:
    """
    Kafka consumer para feedback de especialistas com suporte a online learning.

    Funcionalidades:
    - Consumo do topico specialist_feedback
    - Buffer configuravel para batch processing
    - Conversao de feedbacks para features do IncrementalLearner
    - Envio para callback de processamento quando buffer enche
    """

    def __init__(self, settings: Settings, buffer_size: Optional[int] = None):
        """
        Inicializa Feedback Consumer.

        Args:
            settings: Configuracoes do Approval Service
            buffer_size: Tamanho do buffer (usa config se nao fornecido)
        """
        self.settings = settings
        self.consumer: Optional[Consumer] = None
        self.running: bool = False
        self._last_poll_time: Optional[datetime] = None
        self._buffer_size = buffer_size or settings.online_learning_buffer_size
        self._buffer = FeedbackBuffer(max_size=self._buffer_size)
        self._mongodb_client: Optional[MongoClient] = None

        logger.info(
            "feedback_consumer_initialized",
            buffer_size=self._buffer_size,
            topic=settings.kafka_specialist_feedback_topic,
        )

    async def initialize(self):
        """Inicializa consumer Kafka."""
        consumer_config = {
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "group.id": f"{self.settings.kafka_consumer_group_id}-feedback",
            "auto.offset.reset": self.settings.kafka_auto_offset_reset,
            "enable.auto.commit": self.settings.kafka_enable_auto_commit,
            "session.timeout.ms": self.settings.kafka_session_timeout_ms,
            "max.poll.interval.ms": self.settings.kafka_max_poll_interval_ms,
            "isolation.level": "read_committed",
        }

        # Adiciona configuracao de seguranca
        if self.settings.kafka_security_protocol != "PLAINTEXT":
            consumer_config.update(
                {
                    "security.protocol": self.settings.kafka_security_protocol,
                    "sasl.mechanism": self.settings.kafka_sasl_mechanism,
                    "sasl.username": self.settings.kafka_sasl_username,
                    "sasl.password": self.settings.kafka_sasl_password,
                }
            )

        self.consumer = Consumer(consumer_config)

        # Subscribe no topico de feedback
        self.consumer.subscribe([self.settings.kafka_specialist_feedback_topic])

        # Inicializa cliente MongoDB para buscar features adicionais
        try:
            self._mongodb_client = MongoClient(
                self.settings.mongodb_uri, serverSelectionTimeoutMS=self.settings.mongodb_timeout_ms
            )
            # Testar conexao
            self._mongodb_client.admin.command("ping")
            logger.info(
                "mongodb_client_initialized_for_feedback_consumer", uri=self.settings.mongodb_uri
            )
        except Exception as e:
            logger.warning("mongodb_connection_failed_for_feedback_consumer", error=str(e))
            self._mongodb_client = None

        logger.info(
            "Feedback Consumer inicializado",
            group_id=f"{self.settings.kafka_consumer_group_id}-feedback",
            topic=self.settings.kafka_specialist_feedback_topic,
        )

    async def start_consuming(
        self,
        process_callback: Callable[[List[Dict[str, Any]]], Awaitable[Any]],
        poll_timeout: float = 1.0,
    ):
        """
        Inicia consumo de mensagens de feedback.

        Args:
            process_callback: Funcao async para processar batch de feedbacks
            poll_timeout: Timeout para poll (segundos)
        """
        self.running = True
        logger.info(
            "Iniciando consumo de feedbacks", topic=self.settings.kafka_specialist_feedback_topic
        )

        while self.running:
            try:
                # Poll com timeout
                msg: Optional[Message] = self.consumer.poll(timeout=poll_timeout)
                self._last_poll_time = datetime.now(timezone.utc)

                if msg is None:
                    await asyncio.sleep(0.1)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Fim da particao atingido", partition=msg.partition())
                    else:
                        logger.error("Erro no consumer Kafka", error=str(msg.error()))
                    continue

                # Deserializa mensagem
                try:
                    feedback = await self._deserialize_message(msg)
                    if feedback:
                        # Adiciona ao buffer
                        added = await self._buffer.add(feedback)

                        if not added:
                            logger.warning("feedback_buffer_cheio", buffer_size=self._buffer_size)

                        # Verifica se buffer atingiu threshold para processamento
                        if self._buffer.size >= self._buffer_size:
                            batch = await self._buffer.get_batch()
                            await self._process_batch(batch, process_callback)
                            self.consumer.commit(message=msg)

                        logger.debug(
                            "feedback_adicionado_ao_buffer",
                            feedback_id=feedback.get("feedback_id"),
                            buffer_size=self._buffer.size,
                        )
                except Exception as e:
                    logger.error(
                        "Erro ao processar mensagem de feedback", error=str(e), offset=msg.offset()
                    )
                    # Commit para pular mensagem problematica
                    self.consumer.commit(message=msg)

            except Exception as e:
                logger.error("Erro no loop de consumo de feedback", error=str(e))
                await asyncio.sleep(1.0)

    async def _process_batch(
        self,
        batch: List[Dict[str, Any]],
        process_callback: Callable[[List[Dict[str, Any]]], Awaitable[Any]],
    ):
        """
        Processa lote de feedbacks.

        Args:
            batch: Lote de feedbacks
            process_callback: Callback para processamento
        """
        if not batch:
            return

        logger.info("processando_lote_feedbacks", batch_size=len(batch))

        try:
            await process_callback(batch)
            logger.info("lote_feedbacks_processado", batch_size=len(batch))
        except Exception as e:
            logger.error("erro_ao_processar_lote_feedbacks", batch_size=len(batch), error=str(e))
            raise

    async def _deserialize_message(self, msg: Message) -> Optional[Dict[str, Any]]:
        """
        Deserializa mensagem Kafka para dicionario de feedback.

        Args:
            msg: Mensagem Kafka

        Returns:
            Dicionario com dados do feedback ou None se falhar
        """
        try:
            # Tenta JSON primeiro
            feedback_data = json.loads(msg.value().decode("utf-8"))

            # Extrai headers
            headers = {}
            if msg.headers():
                headers = {k: v.decode("utf-8") if v else None for k, v in msg.headers()}

            # Enriquece com metadata do Kafka
            feedback_data["_kafka_metadata"] = {
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
                "timestamp": msg.timestamp()[1] if msg.timestamp() else None,
                "headers": headers,
            }

            # Busca features NLP adicionais do MongoDB se disponivel
            if self._mongodb_client and feedback_data.get("feedback_id"):
                enriched = await self._enrich_from_mongodb(feedback_data)
                feedback_data.update(enriched)

            logger.debug(
                "feedback_deserializado",
                feedback_id=feedback_data.get("feedback_id"),
                plan_id=feedback_data.get("plan_id"),
                specialist_type=feedback_data.get("specialist_type"),
            )

            return feedback_data

        except Exception as e:
            logger.error("falha_ao_deserializar_feedback", error=str(e), offset=msg.offset())
            return None

    async def _enrich_from_mongodb(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriquece feedback com features adicionais do MongoDB.

        Args:
            feedback_data: Dados do feedback

        Returns:
            Dicionario com features adicionais
        """
        if not self._mongodb_client:
            return {}

        try:
            db = self._mongodb_client[self.settings.mongodb_database]
            collection = db[self.settings.feedback_mongodb_collection]

            # Busca documento completo do feedback
            doc = await asyncio.to_thread(
                collection.find_one, {"feedback_id": feedback_data["feedback_id"]}
            )

            if not doc:
                return {}

            # Extrai nlp_features se presente
            enrichment = {}
            if "nlp_features" in doc:
                enrichment["nlp_features"] = doc["nlp_features"]

            # Extrai features de specialist opinion se presente
            if "metadata" in doc and isinstance(doc["metadata"], dict):
                enrichment["specialist_recommendation"] = doc["metadata"].get(
                    "specialist_recommendation"
                )
                enrichment["specialist_confidence"] = doc["metadata"].get("specialist_confidence")

            return enrichment

        except PyMongoError as e:
            logger.warning(
                "erro_ao_enriquecer_feedback_do_mongodb",
                feedback_id=feedback_data.get("feedback_id"),
                error=str(e),
            )
            return {}

    async def flush_buffer(
        self, process_callback: Callable[[List[Dict[str, Any]]], Awaitable[Any]]
    ):
        """
        Forca processamento do buffer atual.

        Args:
            process_callback: Callback para processamento
        """
        batch = await self._buffer.get_batch()
        if batch:
            await self._process_batch(batch, process_callback)
            logger.info("buffer_flushed", items_processed=len(batch))

    async def get_buffer_stats(self) -> Dict[str, Any]:
        """
        Retorna estatisticas do buffer.

        Returns:
            Dicionario com estatisticas
        """
        return {
            "buffer_size": self._buffer.size,
            "buffer_max_size": self._buffer_size,
            "buffer_utilization": self._buffer.size / self._buffer_size,
            "is_full": self._buffer.is_full,
        }

    def is_healthy(self, max_poll_age_seconds: float = 60.0) -> tuple:
        """
        Verifica saude do consumer.

        Args:
            max_poll_age_seconds: Idade maxima do ultimo poll

        Returns:
            Tuple (is_healthy: bool, reason: str)
        """
        if not self.running:
            return False, "Consumer nao esta rodando"

        if not self.consumer:
            return False, "Consumer nao inicializado"

        if self._last_poll_time:
            age = (datetime.now(timezone.utc) - self._last_poll_time).total_seconds()
            if age > max_poll_age_seconds:
                return False, f"Ultimo poll ha {age:.1f}s (max: {max_poll_age_seconds}s)"

        return True, "Consumer saudavel"

    async def close(self):
        """Fecha consumer graceful."""
        self.running = False
        if self.consumer:
            self.consumer.close()
        if self._mongodb_client:
            self._mongodb_client.close()
        logger.info("Feedback Consumer fechado")
