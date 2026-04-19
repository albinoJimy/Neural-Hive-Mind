"""
Reconnection Manager para Kafka Consumers.

Implementa lógica de reconexão com exponential backoff para consumidores
Kafka que precisam se recuperar de falhas de conexão.

Autor: Neural Hive Mind
Criado: 2026-04-19 (BUG-H-001)
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Optional,
    TypeVar,
)

import structlog

from src.config.settings import get_settings

__all__ = [
    "ReconnectionConfig",
    "ReconnectionStats",
    "ReconnectionManager",
    "consume_with_reconnection",
]

logger = structlog.get_logger()

T = TypeVar("T")


@dataclass(frozen=True)
class ReconnectionConfig:
    """
    Configuração para reconexão com exponential backoff.

    Attributes:
        max_retries: Número máximo de tentativas de reconexão (-1 = infinito)
        initial_delay_ms: Delay inicial em milissegundos
        max_delay_ms: Delay máximo em milissegundos
        backoff_multiplier: Multiplicador para exponential backoff
        reset_after_seconds: Reset contador após sucesso (segundos)
    """

    max_retries: int = 50
    initial_delay_ms: int = 1000
    max_delay_ms: int = 300000  # 5 minutos
    backoff_multiplier: float = 2.0
    reset_after_seconds: int = 60

    def calculate_delay(self, retry_count: int) -> float:
        """
        Calcula delay baseado no número de tentativas.

        Usa exponential backoff com limites configurados.

        Args:
            retry_count: Número da tentativa atual

        Returns:
            Delay em segundos
        """
        delay_ms = self.initial_delay_ms * (self.backoff_multiplier**retry_count)
        delay_ms = min(delay_ms, self.max_delay_ms)
        return delay_ms / 1000.0


@dataclass
class ReconnectionStats:
    """
    Estatísticas de reconexão.

    Attributes:
        total_reconnections: Total de reconexões desde início
        current_retry_count: Tentativas na sequência atual
        last_success_at: Timestamp do último sucesso
        last_error_at: Timestamp do último erro
        last_error_message: Mensagem do último erro
        is_connected: Se está conectado atualmente
    """

    total_reconnections: int = 0
    current_retry_count: int = 0
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    is_connected: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "total_reconnections": self.total_reconnections,
            "current_retry_count": self.current_retry_count,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "last_error_message": self.last_error_message,
            "is_connected": self.is_connected,
        }


class ReconnectionManager:
    """
    Gerencia reconexão Kafka com exponential backoff.

    Permite que consumidores Kafka se reconectem automaticamente
    após falhas de conexão, com backoff exponencial para evitar
    sobrecarregar o cluster.

    Example:
        manager = ReconnectionManager()

        async def message_handler(msg):
            await process_message(msg)

        async for msg in manager.consume_with_reconnection(
            consumer=consumer,
            handler=message_handler,
            topic="cdc.events",
        ):
            # Process mensagem normalmente
            pass
    """

    def __init__(
        self,
        config: Optional[ReconnectionConfig] = None,
        stats: Optional[ReconnectionStats] = None,
    ):
        """
        Inicializa o gerenciador de reconexão.

        Args:
            config: Configuração de reconexão (usa padrão se None)
            stats: Estatísticas (cria novas se None)
        """
        self._config = config or ReconnectionConfig()
        self._stats = stats or ReconnectionStats()

    @property
    def stats(self) -> ReconnectionStats:
        """Retorna estatísticas de reconexão."""
        return self._stats

    async def consume_with_reconnection(
        self,
        consumer: AsyncIterator[T],
        handler: Callable[[T], Awaitable[None]],
        *,
        topic: Optional[str] = None,
        on_reconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> AsyncIterator[T]:
        """
        Consome mensagens com reconexão automática.

        Args:
            consumer: AsyncIterator que produz mensagens
            handler: Função async para processar cada mensagem
            topic: Nome do topic (para logging)
            on_reconnect: Callback após reconexão bem-sucedida

        Yields:
            Mensagens consumidas

        Raises:
            ConnectionError: Após esgotar tentativas de reconexão
        """
        retry_count = 0
        max_retries = self._config.max_retries

        while True:
            try:
                # Tentar consumir
                async for msg in consumer:
                    try:
                        # Processar mensagem
                        await handler(msg)

                        # Reset contador após sucesso
                        if self._stats.current_retry_count > 0:
                            self._stats.current_retry_count = 0
                            self._stats.last_success_at = datetime.now(timezone.utc)
                            self._stats.is_connected = True
                            logger.info(
                                "kafka_reconnection_success",
                                topic=topic,
                                total_reconnections=self._stats.total_reconnections,
                            )

                            # Chamar callback se fornecido
                            if on_reconnect:
                                await on_reconnect()

                        yield msg

                    except Exception as e:
                        # Erro no processamento da mensagem (não de conexão)
                        # Log e continuar - não reconectar
                        logger.error(
                            "message_processing_error",
                            error=str(e),
                            topic=topic,
                        )
                        continue

                # Consumer encerrou normalmente (sem exceção)
                break

            except (ConnectionError, OSError) as e:
                # Erro de conexão Kafka
                retry_count += 1
                self._stats.current_retry_count = retry_count
                self._stats.last_error_at = datetime.now(timezone.utc)
                self._stats.last_error_message = str(e)
                self._stats.is_connected = False

                # Verificar limite de tentativas
                if max_retries >= 0 and retry_count > max_retries:
                    self._stats.total_reconnections += retry_count
                    logger.error(
                        "kafka_reconnection_failed_max_retries",
                        topic=topic,
                        retry_count=retry_count,
                        max_retries=max_retries,
                        last_error=str(e),
                    )
                    raise ConnectionError(
                        f"Falha ao reconectar após {retry_count} tentativas"
                    ) from e

                # Calcular delay com exponential backoff
                delay = self._config.calculate_delay(retry_count - 1)

                logger.warning(
                    "kafka_connection_lost_retrying",
                    topic=topic,
                    retry_count=retry_count,
                    delay_seconds=delay,
                    error=str(e),
                )

                # Aguardar antes de tentar novamente
                await asyncio.sleep(delay)

                # Tentar reconectar (consumer será recriado externamente)
                # O loop tentará consumir novamente
                continue

            except Exception as e:
                # Outro erro não esperado
                logger.error(
                    "kafka_unexpected_error",
                    topic=topic,
                    error=str(e),
                )
                raise

    async def consume_messages_with_retry(
        self,
        consume_func: Callable[[], AsyncIterator[T]],
        handler: Callable[[T], Awaitable[None]],
        *,
        topic: Optional[str] = None,
        on_reconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        """
        Consome mensagens com reconexão total (recria consumer).

        Diferente de consume_with_reconnection, esta função recria
        o consumer a cada tentativa de reconexão.

        Args:
            consume_func: Função que retorna novo AsyncIterator (consumer)
            handler: Função async para processar cada mensagem
            topic: Nome do topic (para logging)
            on_reconnect: Callback após reconexão bem-sucedida

        Raises:
            ConnectionError: Após esgotar tentativas de reconexão
        """
        retry_count = 0
        max_retries = self._config.max_retries

        while True:
            try:
                # Criar novo consumer
                consumer = consume_func()

                # Consumir mensagens
                async for msg in consumer:
                    await handler(msg)

                    # Reset após sucesso
                    if self._stats.current_retry_count > 0:
                        self._stats.total_reconnections += self._stats.current_retry_count
                        self._stats.current_retry_count = 0
                        self._stats.last_success_at = datetime.now(timezone.utc)
                        self._stats.is_connected = True

                        if on_reconnect:
                            await on_reconnect()

                # Consumer encerrou normalmente
                break

            except (ConnectionError, OSError) as e:
                retry_count += 1
                self._stats.current_retry_count = retry_count
                self._stats.last_error_at = datetime.now(timezone.utc)
                self._stats.last_error_message = str(e)
                self._stats.is_connected = False

                if max_retries >= 0 and retry_count > max_retries:
                    raise ConnectionError(
                        f"Falha ao reconectar após {retry_count} tentativas"
                    ) from e

                delay = self._config.calculate_delay(retry_count - 1)

                logger.warning(
                    "kafka_connection_lost_recreating_consumer",
                    topic=topic,
                    retry_count=retry_count,
                    delay_seconds=delay,
                )

                await asyncio.sleep(delay)
                # Loop continua, recriando consumer
                continue


def get_reconnection_manager() -> ReconnectionManager:
    """
    Factory para criar ReconnectionManager com configurações do Settings.

    Returns:
        ReconnectionManager configurado
    """
    settings = get_settings()

    config = ReconnectionConfig(
        max_retries=getattr(settings, "kafka_reconnect_max_attempts", 50),
        initial_delay_ms=getattr(settings, "kafka_reconnect_initial_delay_ms", 1000),
        max_delay_ms=getattr(settings, "kafka_reconnect_max_delay_ms", 300000),
        backoff_multiplier=getattr(settings, "kafka_reconnect_backoff_multiplier", 2.0),
    )

    return ReconnectionManager(config=config)


async def consume_with_reconnection(
    consumer: AsyncIterator[T],
    handler: Callable[[T], Awaitable[None]],
    *,
    topic: Optional[str] = None,
) -> AsyncIterator[T]:
    """
    Função helper para consumir com reconexão automática.

    Usa ReconnectionManager padrão do Settings.

    Args:
        consumer: AsyncIterator que produz mensagens
        handler: Função async para processar cada mensagem
        topic: Nome do topic (para logging)

    Yields:
        Mensagens consumidas
    """
    manager = get_reconnection_manager()
    async for msg in manager.consume_with_reconnection(consumer, handler, topic=topic):
        yield msg
