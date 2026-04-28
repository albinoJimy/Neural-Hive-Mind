"""
Dead Letter Queue (DLQ) Producer para consensus-engine usando confluent-kafka.

Implementa DLQ com retry e backoff exponencial para mensagens que falham
no processamento do plan_consumer. Compatível com confluent-kafka (síncrono).

Gap P0-1: DLQ Não Implementada no consensus-engine.
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from confluent_kafka import Producer

UTC = timezone.utc

logger = structlog.get_logger()


@dataclass
class DLQMessage:
    """Mensagem DLQ com metadados de falha."""

    original_topic: str
    original_partition: int
    original_offset: int
    original_key: Optional[bytes]
    original_value: bytes
    original_headers: Optional[list[tuple[str, bytes]]]
    error_message: str
    error_type: str
    failure_count: int
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    service: str = "consensus-engine"
    consumer_group: str = "consensus-engine"

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict para serialização JSON."""
        return {
            "original_topic": self.original_topic,
            "original_partition": self.original_partition,
            "original_offset": self.original_offset,
            "original_key": self.original_key.hex() if self.original_key else None,
            "original_value": self.original_value.decode("utf-8", errors="replace"),
            "original_headers": [
                (k, v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v)
                for k, v in (self.original_headers or [])
            ],
            "error_message": self.error_message,
            "error_type": self.error_type,
            "failure_count": self.failure_count,
            "timestamp": self.timestamp,
            "service": self.service,
            "consumer_group": self.consumer_group,
        }


class DLQProducer:
    """
    Producer Kafka para DLQ usando confluent-kafka.

    Producer especializado para enviar mensagens com falha para DLQ.
    Implementa retry com backoff exponencial e rate limiting básico.
    """

    def __init__(
        self,
        config,
        dlq_topic_suffix: str = ".dlq",
    ):
        """
        Inicializa DLQ producer.

        Args:
            config: Configurações do consensus-engine (Settings)
            dlq_topic_suffix: Sufixo para tópicos DLQ (default: ".dlq")
        """
        self.config = config
        self.dlq_topic_suffix = dlq_topic_suffix
        self.producer: Optional[Producer] = None
        self._enabled = config.consumer_enable_dlq
        self._dlq_topic = config.kafka_dlq_topic
        self._max_retries = config.consumer_max_retries_before_dlq

        # Rate limiting simples (mensagens por segundo)
        self._rate_limit_window = 60  # janela de 60 segundos
        self._rate_limit_max = 100  # máximo de 100 mensagens DLQ por minuto
        self._rate_limit_timestamps: list[float] = []

        # Métricas
        self._messages_sent_to_dlq = 0
        self._messages_rate_limited = 0

    async def initialize(self):
        """Inicializa producer Kafka para DLQ."""
        if not self._enabled:
            logger.info("DLQ desabilitado nas configurações", dlq_enabled=False)
            return

        producer_config = {
            "bootstrap.servers": self.config.kafka_bootstrap_servers,
            "enable.idempotence": True,
            "acks": "all",
            "retries": 3,
            "max.in.flight.requests.per.connection": 1,
            "compression.type": "snappy",
        }

        # Configuração de segurança SASL (se não for PLAINTEXT)
        if self.config.kafka_security_protocol != "PLAINTEXT":
            producer_config["security.protocol"] = self.config.kafka_security_protocol
            if self.config.kafka_sasl_mechanism:
                producer_config["sasl.mechanism"] = self.config.kafka_sasl_mechanism
            if self.config.kafka_sasl_username:
                producer_config["sasl.username"] = self.config.kafka_sasl_username
            if self.config.kafka_sasl_password:
                producer_config["sasl.password"] = self.config.kafka_sasl_password

        self.producer = Producer(producer_config)

        logger.info(
            "DLQ producer inicializado",
            dlq_topic=self._dlq_topic,
            dlq_enabled=self._enabled,
            max_retries=self._max_retries,
            rate_limit_max=self._rate_limit_max,
        )

    async def stop(self):
        """Para o producer Kafka."""
        if self.producer:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.producer.flush(timeout=10.0)
            )
            logger.info("DLQ producer parado")

    def get_dlq_topic(self, original_topic: str) -> str:
        """Retorna nome do tópico DLQ."""
        # Se o tópico configurado for específico, usar ele
        if self._dlq_topic and not self._dlq_topic.endswith(".dlq"):
            return self._dlq_topic
        # Caso contrário, usar o sufixo padrão
        if original_topic.endswith(self.dlq_topic_suffix):
            return original_topic
        return f"{original_topic}{self.dlq_topic_suffix}"

    def _check_rate_limit(self) -> bool:
        """
        Verifica rate limit usando sliding window.

        Returns:
            True se permitido enviar, False se rate limitado
        """
        now = time.time()
        # Remover timestamps fora da janela
        cutoff = now - self._rate_limit_window
        self._rate_limit_timestamps = [
            ts for ts in self._rate_limit_timestamps if ts > cutoff
        ]

        if len(self._rate_limit_timestamps) < self._rate_limit_max:
            self._rate_limit_timestamps.append(now)
            return True

        return False

    async def send_to_dlq(
        self,
        message,
        exception: Exception,
        failure_count: int,
        tracing_context: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Envia mensagem para DLQ após exceder limite de retries.

        Args:
            message: Mensagem Kafka original (confluent_kafka.Message)
            exception: Exceção que causou a falha
            failure_count: Número de falhas já ocorridas
            tracing_context: Contexto de tracing para propagação

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if not self._enabled:
            logger.debug(
                "DLQ desabilitado - mensagem não enviada para DLQ",
                failure_count=failure_count,
                max_retries=self._max_retries,
            )
            return False

        if not self.producer:
            logger.warning("DLQ producer não inicializado")
            return False

        # Verificar rate limit
        if not self._check_rate_limit():
            self._messages_rate_limited += 1
            logger.warning(
                "DLQ rate limit atingido - mensagem dropada",
                available_tokens=self._rate_limit_max - len(self._rate_limit_timestamps),
                total_rate_limited=self._messages_rate_limited,
            )
            return False

        try:
            dlq_topic = self.get_dlq_topic(message.topic())

            # Criar mensagem DLQ
            dlq_message = DLQMessage(
                original_topic=message.topic(),
                original_partition=message.partition(),
                original_offset=message.offset(),
                original_key=message.key(),
                original_value=message.value(),
                original_headers=message.headers(),
                error_message=str(exception),
                error_type=type(exception).__name__,
                failure_count=failure_count,
                service=self.config.service_name,
                consumer_group=self.config.kafka_consumer_group_id,
            )

            # Preparar headers com tracing context
            headers = []
            if tracing_context:
                for key, value in tracing_context.items():
                    headers.append((key, str(value).encode()))

            # Adicionar headers originais preservados (sem duplicar)
            existing_keys = {h[0] for h in headers}
            if message.headers():
                for key, value in message.headers():
                    if key not in existing_keys:
                        headers.append((key, value))

            # Serializar mensagem DLQ
            value = json.dumps(dlq_message.to_dict()).encode("utf-8")
            key_bytes = message.key()

            # Enviar de forma assíncrona (não-bloqueante)
            def _produce():
                self.producer.produce(
                    topic=dlq_topic,
                    key=key_bytes,
                    value=value,
                    headers=headers if headers else None,
                )
                self.producer.poll(0)  # Processar delivery callbacks

            await asyncio.get_event_loop().run_in_executor(None, _produce)

            self._messages_sent_to_dlq += 1

            logger.info(
                "mensagem_enviada_para_DLQ",
                dlq_topic=dlq_topic,
                original_topic=dlq_message.original_topic,
                original_offset=dlq_message.original_offset,
                error_type=dlq_message.error_type,
                failure_count=failure_count,
                total_sent=self._messages_sent_to_dlq,
            )

            # Atualizar métricas Prometheus (se disponível)
            try:
                from src.observability.metrics import ConsensusMetrics
                ConsensusMetrics.increment_dlq_message_sent(dlq_message.error_type)
            except ImportError:
                pass

            return True

        except Exception as e:
            logger.error(
                "falha_envio_DLQ",
                dlq_topic=dlq_topic,
                error=str(e),
                error_type=type(e).__name__,
                original_offset=message.offset(),
            )
            return False

    def calculate_backoff(self, failure_count: int) -> float:
        """
        Calcula backoff exponencial baseado no número de falhas.

        Args:
            failure_count: Número de falhas

        Returns:
            Segundos de espera antes do próximo retry
        """
        base_backoff = self.config.consumer_base_backoff_seconds
        max_backoff = self.config.consumer_max_backoff_seconds
        return min(base_backoff * (2 ** min(failure_count, 10)), max_backoff)

    def should_send_to_dlq(self, failure_count: int, is_systemic: bool) -> bool:
        """
        Determina se mensagem deve ser enviada para DLQ.

        Args:
            failure_count: Número de falhas
            is_systemic: Se é erro sistêmico (vs erro de negócio)

        Returns:
            True se deve enviar para DLQ
        """
        if not self._enabled:
            return False

        # Erros sistêmicos vão para DLQ mais rápido
        threshold = self._max_retries if is_systemic else self._max_retries * 2
        return failure_count >= threshold

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do DLQ producer."""
        return {
            "enabled": self._enabled,
            "dlq_topic": self._dlq_topic,
            "messages_sent_to_dlq": self._messages_sent_to_dlq,
            "messages_rate_limited": self._messages_rate_limited,
            "max_retries": self._max_retries,
        }
