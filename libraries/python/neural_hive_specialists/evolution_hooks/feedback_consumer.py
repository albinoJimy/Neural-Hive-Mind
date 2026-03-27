"""
Evolution Feedback Consumer - Kafka consumer for feedback processing.

Este módulo implementa o consumer Kafka que processa mensagens de feedback
do Approval Service e atualiza o Pattern Registry com os resultados.
"""

import asyncio
import json
from typing import Optional, Dict, Any
import structlog

try:
    from aiokafka import AIOKafkaConsumer
    from aiokafka.errors import KafkaError

    AIOKAFKA_AVAILABLE = True
except ImportError:
    AIOKafkaConsumer = None
    AIOKAFKA_AVAILABLE = False

from .models import FeedbackMessage, FeedbackData, FeedbackOutcome, FeedbackSource
from .pattern_registry import PatternRegistry

logger = structlog.get_logger()


class EvolutionFeedbackConsumer:
    """
    Consumer Kafka para feedback do Evolution Specialist.

    Responsável por:
    - Consumir mensagens do tópico evolution.feedback.topic
    - Validar mensagens usando FeedbackMessage (Pydantic)
    - Atualizar PatternRegistry com feedback recebido
    - Suportar graceful shutdown e retry
    """

    # Configurações defaults
    DEFAULT_POLL_TIMEOUT_MS = 1000
    DEFAULT_MAX_POLL_RECORDS = 10
    DEFAULT_AUTO_COMMIT = False

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        pattern_registry: PatternRegistry,
        max_poll_records: int = DEFAULT_MAX_POLL_RECORDS,
        poll_timeout_ms: int = DEFAULT_POLL_TIMEOUT_MS,
        enable_auto_commit: bool = DEFAULT_AUTO_COMMIT,
    ):
        """
        Inicializa o EvolutionFeedbackConsumer.

        Args:
            bootstrap_servers: Servidores Kafka (ex: "localhost:9092")
            topic: Tópico Kafka para consumir (ex: "evolution.feedback.topic")
            group_id: ID do consumer group Kafka
            pattern_registry: Instância de PatternRegistry para atualizar
            max_poll_records: Máximo de registros por poll (default: 10)
            poll_timeout_ms: Timeout para poll em ms (default: 1000)
            enable_auto_commit: Habilitar auto commit (default: False)

        Raises:
            ImportError: Se aiokafka não estiver instalado
        """
        if not AIOKAFKA_AVAILABLE:
            raise ImportError(
                "aiokafka is required for EvolutionFeedbackConsumer. "
                "Install it with: pip install aiokafka"
            )

        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.pattern_registry = pattern_registry
        self.max_poll_records = max_poll_records
        self.poll_timeout_ms = poll_timeout_ms
        self.enable_auto_commit = enable_auto_commit

        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None

        # Métricas internas
        self._messages_processed = 0
        self._messages_failed = 0

        logger.info(
            "evolution_feedback_consumer.created",
            bootstrap_servers=bootstrap_servers,
            topic=topic,
            group_id=group_id,
        )

    async def start(self) -> None:
        """
        Inicia o consumer Kafka e o loop de consumo.

        Cria o consumer Kafka, inicia a conexão e lança o loop de
        consumo em background como uma asyncio.Task.
        """
        if self._running:
            logger.warning("evolution_feedback_consumer.already_running")
            return

        await self._create_consumer()
        await self._start_consumer()

        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())

        logger.info(
            "evolution_feedback_consumer.started",
            topic=self.topic,
            group_id=self.group_id,
        )

    async def stop(self) -> None:
        """
        Para o consumer gracefulmente.

        Sinaliza o loop para parar, cancela a task, e fecha o consumer.
        """
        if not self._running:
            logger.warning("evolution_feedback_consumer.not_running")
            return

        logger.info("evolution_feedback_consumer.stopping")

        self._running = False

        # Cancelar task de consumo
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # Parar consumer Kafka
        if self.consumer:
            await self.consumer.stop()
            logger.info("evolution_feedback_consumer.kafka_stopped")

        logger.info(
            "evolution_feedback_consumer.stopped",
            messages_processed=self._messages_processed,
            messages_failed=self._messages_failed,
        )

    async def _create_consumer(self) -> None:
        """Cria e configura o consumer Kafka."""
        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=self.enable_auto_commit,
            max_poll_records=self.max_poll_records,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        logger.debug(
            "evolution_feedback_consumer.consumer_created",
            auto_offset_reset="earliest",
            enable_auto_commit=self.enable_auto_commit,
            max_poll_records=self.max_poll_records,
        )

    async def _start_consumer(self) -> None:
        """Inicia a conexão do consumer com o Kafka."""
        try:
            await self.consumer.start()
            logger.info(
                "evolution_feedback_consumer.kafka_started",
                bootstrap_servers=self.bootstrap_servers,
            )
        except KafkaError as e:
            logger.error("evolution_feedback_consumer.kafka_start_failed", error=str(e))
            raise

    async def _consume_loop(self) -> None:
        """
        Loop principal de consumo de mensagens.

        Continua consumindo até _running seja False. Usa getmany()
        com timeout para permitir verificações periódicas do flag.
        """
        try:
            while self._running:
                try:
                    # Poll com timeout para permitir shutdown gracefully
                    messages = await self._poll_with_timeout()

                    if not messages:
                        continue

                    # Processar mensagens
                    for tp, msgs in messages.items():
                        for message in msgs:
                            await self._process_message(message)

                            # Commit manual se não auto-commit
                            if not self.enable_auto_commit:
                                await self.consumer.commit()

                except asyncio.TimeoutError:
                    # Timeout normal, continuar loop
                    continue

                except KafkaError as e:
                    logger.error(
                        "evolution_feedback_consumer.kafka_error", error=str(e)
                    )
                    # Backoff antes de retry
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("evolution_feedback_consumer.consume_loop_cancelled")
            raise

        except Exception as e:
            logger.error("evolution_feedback_consumer.consume_loop_error", error=str(e))
            self._running = False

    async def _poll_with_timeout(
        self, timeout_ms: Optional[int] = None
    ) -> Dict[Any, Any]:
        """
        Poll mensagens do Kafka com timeout.

        Usa asyncio.wait_for para cancelar o poll caso _running mude.

        Args:
            timeout_ms: Timeout em ms (usa default se não especificado)

        Returns:
            Dicionário de TopicPartition para lista de mensagens

        Raises:
            asyncio.TimeoutError: Se nenhuma mensagem recebida no timeout
        """
        if timeout_ms is None:
            timeout_ms = self.poll_timeout_ms

        timeout_sec = timeout_ms / 1000.0

        try:
            messages = await asyncio.wait_for(
                self.consumer.getmany(timeout_ms=timeout_ms),
                timeout=timeout_sec + 0.1,  # Pequena margem
            )
            return messages if messages else {}

        except asyncio.TimeoutError:
            # Retornar dict vazio em vez de propagar
            return {}

    async def _process_message(self, message) -> None:
        """
        Processa uma mensagem Kafka individual.

        1. Extrai valor da mensagem
        2. Valida com FeedbackMessage (Pydantic)
        3. Atualiza PatternRegistry via add_feedback()

        Args:
            message: Mensagem Kafka (aiokafka.ConsumerRecord)
        """
        try:
            # Extrair valor da mensagem
            raw_data = message.value

            # Validar com Pydantic
            feedback_msg = FeedbackMessage(**raw_data)

            logger.debug(
                "evolution_feedback_consumer.message_received",
                plan_id=feedback_msg.plan_id,
                outcome=feedback_msg.feedback.outcome.value,
            )

            # Atualizar PatternRegistry
            success = await self.pattern_registry.add_feedback(
                plan_id=feedback_msg.plan_id,
                feedback=feedback_msg.feedback,
                corrected_weights=feedback_msg.feedback.corrected_weights,
            )

            if success:
                self._messages_processed += 1

                logger.info(
                    "evolution_feedback_consumer.feedback_added",
                    plan_id=feedback_msg.plan_id,
                    outcome=feedback_msg.feedback.outcome.value,
                    source=feedback_msg.feedback.source.value,
                )
            else:
                logger.warning(
                    "evolution_feedback_consumer.pattern_not_found",
                    plan_id=feedback_msg.plan_id,
                )

        except Exception as e:
            self._messages_failed += 1

            logger.error(
                "evolution_feedback_consumer.process_message_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    async def process_message(self, message_data: Dict[str, Any]) -> bool:
        """
        Processa uma mensagem de feedback (método público).

        Útil para testes ou processamento manual de mensagens.

        Args:
            message_data: Dicionário com dados da mensagem feedback

        Returns:
            True se processado com sucesso, False caso contrário

        Raises:
            ValidationError: Se mensagem não for válida para FeedbackMessage
        """
        try:
            # Validar com Pydantic
            feedback_msg = FeedbackMessage(**message_data)

            # Atualizar PatternRegistry
            success = await self.pattern_registry.add_feedback(
                plan_id=feedback_msg.plan_id,
                feedback=feedback_msg.feedback,
                corrected_weights=feedback_msg.feedback.corrected_weights,
            )

            if success:
                self._messages_processed += 1

            return success

        except Exception as e:
            self._messages_failed += 1
            logger.error(
                "evolution_feedback_consumer.process_message_failed", error=str(e)
            )
            raise

    @property
    def is_running(self) -> bool:
        """Retorna True se o consumer está rodando."""
        return self._running

    @property
    def messages_processed(self) -> int:
        """Retorna número de mensagens processadas com sucesso."""
        return self._messages_processed

    @property
    def messages_failed(self) -> int:
        """Retorna número de mensagens que falharam."""
        return self._messages_failed


def create_feedback_consumer(
    bootstrap_servers: str,
    topic: str,
    group_id: str,
    pattern_registry: PatternRegistry,
    **kwargs
) -> EvolutionFeedbackConsumer:
    """
    Factory function para criar EvolutionFeedbackConsumer.

    Args:
        bootstrap_servers: Servidores Kafka
        topic: Tópico Kafka
        group_id: ID do consumer group
        pattern_registry: Instância de PatternRegistry
        **kwargs: Argumentos adicionais para EvolutionFeedbackConsumer

    Returns:
        Instância de EvolutionFeedbackConsumer configurada
    """
    return EvolutionFeedbackConsumer(
        bootstrap_servers=bootstrap_servers,
        topic=topic,
        group_id=group_id,
        pattern_registry=pattern_registry,
        **kwargs
    )
