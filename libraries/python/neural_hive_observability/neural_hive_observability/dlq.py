"""
Dead Letter Queue (DLQ) com Rate Limiter para Kafka.

Implementa DLQ com controle de taxa para evitar flooding de mensagens malformadas.
Segue padrão W3C Trace Context para correlação distribuída.

Componentes:
- DLQProducer: Producer para tópicos DLQ
- TokenBucketRateLimiter: Rate limiter baseado em token bucket
- DLQHandler: Handler unificado para envio de mensagens com falha para DLQ

Exemplo de uso:
```python
from neural_hive_observability.dlq import DLQHandler, TokenBucketRateLimiter

rate_limiter = TokenBucketRateLimiter(capacity=100, refill_rate=10)
dlq_handler = DLQHandler(
    producer=kafka_producer,
    rate_limiter=rate_limiter,
    dlq_topic="tickets.dlq",
    max_retries=3
)

# No consumer exception handling:
if failure_count >= max_retries:
    await dlq_handler.send_to_dlq(
        original_message=message,
        error=exception,
        failure_count=failure_count
    )
```
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable

from aiokafka import AIOKafkaProducer
from aiokafka.structs import TopicPartition

from neural_hive_observability.context import inject_context_to_metadata

logger = logging.getLogger(__name__)


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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    service: str = "unknown"
    consumer_group: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
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


class TokenBucketRateLimiter:
    """
    Rate limiter usando algoritmo Token Bucket.

    Permite bursts controlados com taxa de refill constante.

    Args:
        capacity: Número máximo de tokens (burst capacity)
        refill_rate: Tokens por segundo (taxa média)
        initial_tokens: Tokens iniciais (default=capacity)
    """

    def __init__(
        self,
        capacity: int = 100,
        refill_rate: float = 10.0,
        initial_tokens: Optional[int] = None,
    ):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """
        Tenta adquirir tokens do bucket.

        Args:
            tokens: Número de tokens a adquirir

        Returns:
            True se tokens foram adquiridos, False caso contrário
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill

            # Refill tokens baseado no tempo decorrido
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def acquire_with_timeout(
        self, tokens: int = 1, timeout: float = 5.0
    ) -> bool:
        """
        Tenta adquirir tokens com timeout e backoff.

        Args:
            tokens: Número de tokens a adquirir
            timeout: Tempo máximo de espera em segundos

        Returns:
            True se tokens foram adquiridos, False caso contrário
        """
        start = time.time()
        backoff = 0.1

        while time.time() - start < timeout:
            if await self.acquire(tokens):
                return True

            # Exponential backoff com cap
            await asyncio.sleep(min(backoff, 1.0))
            backoff *= 2

        return False

    def get_available_tokens(self) -> float:
        """Retorna número aproximado de tokens disponíveis."""
        now = time.time()
        elapsed = now - self.last_refill
        return min(self.capacity, self.tokens + elapsed * self.refill_rate)


class SlidingWindowRateLimiter:
    """
    Rate limiter usando algoritmo Sliding Window Log.

    Mais preciso para limites de taxa janela-based.

    Args:
        max_requests: Número máximo de requisições permitidas
        window_seconds: Janela de tempo em segundos
    """

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        Tenta adquirir permissão para enviar requisição.

        Returns:
            True se permitido, False caso contrário
        """
        async with self._lock:
            now = time.time()

            # Remover requisições fora da janela
            cutoff = now - self.window_seconds
            self.requests = [t for t in self.requests if t > cutoff]

            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True
            return False

    async def acquire_with_timeout(self, timeout: float = 5.0) -> bool:
        """Tenta adquirir permissão com timeout."""
        start = time.time()
        backoff = 0.1

        while time.time() - start < timeout:
            if await self.acquire():
                return True

            await asyncio.sleep(min(backoff, 1.0))
            backoff *= 2

        return False


class DLQProducer:
    """
    Producer Kafka para DLQ com retry e backoff.

    Producer especializado para enviar mensagens com falha para DLQ.
    Inclui tracing context propagation.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        dlq_topic_suffix: str = ".dlq",
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: Optional[str] = None,
        sasl_username: Optional[str] = None,
        sasl_password: Optional[str] = None,
    ):
        """
        Inicializa DLQ producer.

        Args:
            bootstrap_servers: Servidores Kafka
            dlq_topic_suffix: Sufixo para tópicos DLQ (default: ".dlq")
            security_protocol: Protocolo de segurança (PLAINTEXT, SASL_SSL)
            sasl_mechanism: Mecanismo SASL (PLAIN, SCRAM-SHA-256, etc)
            sasl_username: Username SASL
            sasl_password: Password SASL
        """
        self.bootstrap_servers = bootstrap_servers
        self.dlq_topic_suffix = dlq_topic_suffix
        self.producer: Optional[AIOKafkaProducer] = None
        self.security_protocol = security_protocol
        self.sasl_mechanism = sasl_mechanism
        self.sasl_username = sasl_username
        self.sasl_password = sasl_password

    async def start(self):
        """Inicia o producer Kafka."""
        config = {
            "bootstrap_servers": self.bootstrap_servers,
            "acks": "all",  # Esperar confirmação de todos os replicas
            "compression_type": "snappy",  # Comprimir mensagens DLQ
            "max_retries": 3,
            "retry_backoff_ms": 100,
        }

        if self.security_protocol != "PLAINTEXT":
            config.update(
                {
                    "security_protocol": self.security_protocol,
                    "sasl_mechanism": self.sasl_mechanism,
                    "sasl_plain_username": self.sasl_username,
                    "sasl_plain_password": self.sasl_password,
                }
            )

        self.producer = AIOKafkaProducer(**config)
        await self.producer.start()
        logger.info(f"DLQ producer iniciado: bootstrap_servers={self.bootstrap_servers}")

    async def stop(self):
        """Para o producer Kafka."""
        if self.producer:
            await self.producer.stop()
            logger.info("DLQ producer parado")

    def get_dlq_topic(self, original_topic: str) -> str:
        """Retorna nome do tópico DLQ baseado no tópico original."""
        if original_topic.endswith(self.dlq_topic_suffix):
            return original_topic
        return f"{original_topic}{self.dlq_topic_suffix}"

    async def send_dlq_message(
        self,
        dlq_message: DLQMessage,
        tracing_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Envia mensagem para DLQ.

        Args:
            dlq_message: Mensagem DLQ com metadados
            tracing_context: Contexto de tracing para injeção nos headers

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if not self.producer:
            logger.warning("DLQ producer não iniciado")
            return False

        try:
            dlq_topic = self.get_dlq_topic(dlq_message.original_topic)

            # Preparar headers com tracing context
            headers = []
            if tracing_context:
                for key, value in tracing_context.items():
                    headers.append((key, str(value).encode()))

            # Adicionar headers originais preservados
            if dlq_message.original_headers:
                for key, value in dlq_message.original_headers:
                    if key not in {h[0] for h in headers}:
                        headers.append((key, value))

            # Serializar mensagem DLQ
            value = json.dumps(dlq_message.to_dict()).encode("utf-8")

            await self.producer.send_and_wait(
                topic=dlq_topic,
                value=value,
                key=dlq_message.original_key,
                headers=headers if headers else None,
            )

            logger.info(
                f"Mensagem enviada para DLQ: dlq_topic={dlq_topic}, original_topic={dlq_message.original_topic}, original_offset={dlq_message.original_offset}, error_type={dlq_message.error_type}"
            )
            return True

        except Exception as e:
            logger.exception(
                f"Falha ao enviar mensagem para DLQ: dlq_topic={dlq_topic}, error={e}"
            )
            return False


class DLQHandler:
    """
    Handler unificado para DLQ com rate limiting e tracking de falhas.

    Gerencia envio de mensagens com falha para DLQ, controlando taxa
    para evitar flooding de tópicos DLQ.

    Args:
        producer: Instância de DLQProducer ou AIOKafkaProducer
        rate_limiter: Instância de rate limiter
        service_name: Nome do serviço para metadados
        consumer_group: Consumer group para metadados
        max_retries: Número máximo de retries antes de DLQ
        retry_backoff_base: Base para exponential backoff (segundos)
    """

    def __init__(
        self,
        producer: DLQProducer,
        rate_limiter: Optional[TokenBucketRateLimiter | SlidingWindowRateLimiter] = None,
        service_name: str = "unknown",
        consumer_group: str = "unknown",
        max_retries: int = 3,
        retry_backoff_base: float = 1.0,
    ):
        self.producer = producer
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(capacity=100, refill_rate=10)
        self.service_name = service_name
        self.consumer_group = consumer_group
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        # Métricas locais (opcionalmente integrar com Prometheus)
        self._messages_sent_to_dlq = 0
        self._messages_rate_limited = 0

    async def handle_failure(
        self,
        message,
        exception: Exception,
        failure_count: int,
        tracing_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Decide e executa ação para mensagem com falha.

        Args:
            message: Mensagem Kafka original (AIOKafka ConsumerRecord)
            exception: Exceção que causou a falha
            failure_count: Número de falhas já ocorridas
            tracing_context: Contexto de tracing para propagação

        Returns:
            True se mensagem foi enviada para DLQ, False se deve continuar retrying
        """
        # Se ainda não excedeu max_retries, continuar tentando
        if failure_count < self.max_retries:
            logger.debug(
                f"Falha abaixo do limite, continuando retry: failure_count={failure_count}, max_retries={self.max_retries}"
            )
            return False

        # Excedeu limite de retries, tentar enviar para DLQ
        logger.warning(
            f"Mensagem excedeu limite de retries, enviando para DLQ: failure_count={failure_count}, max_retries={self.max_retries}, topic={message.topic}, offset={message.offset}"
        )

        # Criar mensagem DLQ
        dlq_message = DLQMessage(
            original_topic=message.topic,
            original_partition=message.partition,
            original_offset=message.offset,
            original_key=message.key,
            original_value=message.value,
            original_headers=message.headers,
            error_message=str(exception),
            error_type=type(exception).__name__,
            failure_count=failure_count,
            service=self.service_name,
            consumer_group=self.consumer_group,
        )

        # Tentar adquirir permissão do rate limiter
        if not await self.rate_limiter.acquire_with_timeout(tokens=1, timeout=1.0):
            logger.warning(
                f"Rate limiter bloqueou envio para DLQ: available_tokens={self.rate_limiter.get_available_tokens()}"
            )
            self._messages_rate_limited += 1

            # Log estratégico para alerta operacional
            logger.error(
                f"DLQ_RATE_LIMIT_THRESHOLD: service={self.service_name}, dlq_topic={self.producer.get_dlq_topic(message.topic)}, rate_limit_hit=True, action=message_will_be_dropped_after_max_retries"
            )
            return False

        # Enviar para DLQ
        success = await self.producer.send_dlq_message(dlq_message, tracing_context)

        if success:
            self._messages_sent_to_dlq += 1
            logger.info(
                f"DLQ_SEND_SUCCESS: service={self.service_name}, dlq_topic={self.producer.get_dlq_topic(message.topic)}, original_offset={message.offset}, total_sent={self._messages_sent_to_dlq}"
            )
        else:
            logger.error(
                f"DLQ_SEND_FAILED: service={self.service_name}, dlq_topic={self.producer.get_dlq_topic(message.topic)}, original_offset={message.offset}"
            )

        return success

    def calculate_backoff(self, failure_count: int) -> float:
        """
        Calcula backoff exponencial baseado no número de falhas.

        Args:
            failure_count: Número de falhas

        Returns:
            Segundos de espera antes do próximo retry
        """
        return min(self.retry_backoff_base * (2 ** min(failure_count, 10)), 60.0)

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do handler."""
        return {
            "messages_sent_to_dlq": self._messages_sent_to_dlq,
            "messages_rate_limited": self._messages_rate_limited,
            "available_tokens": getattr(self.rate_limiter, "get_available_tokens", lambda: 0)(),
        }


def create_dlq_handler(
    bootstrap_servers: str,
    service_name: str,
    consumer_group: str,
    security_protocol: str = "PLAINTEXT",
    sasl_mechanism: Optional[str] = None,
    sasl_username: Optional[str] = None,
    sasl_password: Optional[str] = None,
    dlq_capacity: int = 100,
    dlq_refill_rate: float = 10.0,
    max_retries: int = 3,
) -> DLQHandler:
    """
    Factory function para criar DLQHandler com configuração padrão.

    Args:
        bootstrap_servers: Servidores Kafka
        service_name: Nome do serviço
        consumer_group: Consumer group ID
        security_protocol: Protocolo de segurança
        sasl_mechanism: Mecanismo SASL
        sasl_username: Username SASL
        sasl_password: Password SASL
        dlq_capacity: Capacidade do rate limiter (mensagens por burst)
        dlq_refill_rate: Taxa de refill do rate limiter (mensagens/seg)
        max_retries: Máximo de retries antes de DLQ

    Returns:
        Instância de DLQHandler configurada
    """
    rate_limiter = TokenBucketRateLimiter(capacity=dlq_capacity, refill_rate=dlq_refill_rate)
    producer = DLQProducer(
        bootstrap_servers=bootstrap_servers,
        security_protocol=security_protocol,
        sasl_mechanism=sasl_mechanism,
        sasl_username=sasl_username,
        sasl_password=sasl_password,
    )

    return DLQHandler(
        producer=producer,
        rate_limiter=rate_limiter,
        service_name=service_name,
        consumer_group=consumer_group,
        max_retries=max_retries,
    )


__all__ = [
    "DLQMessage",
    "TokenBucketRateLimiter",
    "SlidingWindowRateLimiter",
    "DLQProducer",
    "DLQHandler",
    "create_dlq_handler",
]
