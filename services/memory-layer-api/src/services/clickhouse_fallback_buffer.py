"""
ClickHouse Fallback Buffer

Buffer circular thread-safe para armazenar eventos temporariamente
quando o ClickHouse está indisponível.
"""
import asyncio
import json
from collections import deque
from datetime import datetime, timezone
from typing import Any

import structlog
from prometheus_client import Counter, Gauge

logger = structlog.get_logger(__name__)

# Métricas Prometheus
FALLBACK_BUFFER_SIZE = Gauge(
    "memory_clickhouse_fallback_buffer_size",
    "Número de eventos atualmente no buffer de fallback",
)

EVENTS_ADDED = Counter(
    "memory_clickhouse_fallback_events_added_total",
    "Total de eventos adicionados ao buffer de fallback",
    ["table"],
)

EVENTS_DROPPED = Counter(
    "memory_clickhouse_fallback_events_dropped_total",
    "Total de eventos descartados por buffer cheio",
    ["table"],
)

EVENTS_DRAINED = Counter(
    "memory_clickhouse_fallback_events_drained_total",
    "Total de eventos drenados do buffer para MongoDB",
    ["table"],
)


class ClickHouseFallbackBuffer:
    """
    Buffer circular para eventos ClickHouse quando o serviço está indisponível.

    Estratégia:
    - Buffer em memória com capacidade configurável
    - Persistência Redis para recuperação após restart
    - TTL de 24h para dados históricos
    - Thread-safe com asyncio.Lock
    """

    def __init__(
        self,
        redis_client,
        settings,
        capacity: int = 1000,
        redis_ttl_seconds: int = 86400,  # 24 horas
    ):
        self.redis = redis_client
        self.settings = settings
        self.capacity = capacity
        self.redis_ttl = redis_ttl_seconds

        # Buffer circular em memória
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)

        # Lock para thread-safety
        self._lock = asyncio.Lock()

        # Chave Redis para persistência
        self._redis_key = "clickhouse:fallback:buffer"

    async def initialize(self) -> None:
        """Inicializa o buffer, recuperando eventos do Redis se disponível."""
        try:
            await self._load_from_redis()
            logger.info(
                "ClickHouse fallback buffer initialized",
                capacity=self.capacity,
                redis_ttl=self.redis_ttl,
            )
        except Exception as e:
            logger.warning("Failed to load buffer from Redis", error=str(e))

    async def add_event(
        self,
        table: str,
        rows: list[list[Any]],
        column_names: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Adiciona evento ao buffer de fallback.

        Args:
            table: Nome da tabela ClickHouse
            rows: Linhas a serem inseridas
            column_names: Nomes das colunas
            metadata: Metadados adicionais

        Returns:
            True se adicionado, False se buffer cheio
        """
        async with self._lock:
            event = {
                "table": table,
                "rows": rows,
                "column_names": column_names,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Verifica capacidade
            if len(self._buffer) >= self.capacity:
                EVENTS_DROPPED.labels(table=table).inc()
                logger.warning(
                    "Fallback buffer full, dropping event",
                    table=table,
                    capacity=self.capacity,
                )
                return False

            self._buffer.append(event)
            EVENTS_ADDED.labels(table=table).inc()
            FALLBACK_BUFFER_SIZE.set(len(self._buffer))

            # Persiste no Redis
            await self._persist_to_redis()

            logger.debug(
                "Event added to fallback buffer",
                table=table,
                row_count=len(rows),
                buffer_size=len(self._buffer),
            )
            return True

    async def get_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Retorna eventos do buffer sem removê-los.

        Args:
            limit: Número máximo de eventos a retornar

        Returns:
            Lista de eventos
        """
        async with self._lock:
            events = list(self._buffer)
            if limit:
                events = events[:limit]
            return events

    async def take_events(self, batch_size: int = 100) -> list[dict[str, Any]]:
        """
        Remove e retorna eventos do buffer para drenagem.

        Args:
            batch_size: Número máximo de eventos a remover

        Returns:
            Lista de eventos removidos
        """
        async with self._lock:
            if not self._buffer:
                return []

            # Remove até batch_size eventos do início
            events_to_drain = []
            for _ in range(min(batch_size, len(self._buffer))):
                if self._buffer:
                    event = self._buffer.popleft()
                    events_to_drain.append(event)

            # Atualiza métricas
            for event in events_to_drain:
                EVENTS_DRAINED.labels(table=event["table"]).inc()

            FALLBACK_BUFFER_SIZE.set(len(self._buffer))

            # Persiste estado atualizado
            await self._persist_to_redis()

            logger.info(
                "Events taken from fallback buffer",
                count=len(events_to_drain),
                remaining=len(self._buffer),
            )

            return events_to_drain

    async def size(self) -> int:
        """Retorna número de eventos no buffer."""
        async with self._lock:
            return len(self._buffer)

    async def is_empty(self) -> bool:
        """Verifica se buffer está vazio."""
        async with self._lock:
            return len(self._buffer) == 0

    async def clear(self) -> None:
        """Limpa o buffer."""
        async with self._lock:
            self._buffer.clear()
            FALLBACK_BUFFER_SIZE.set(0)
            await self._persist_to_redis()
            logger.info("Fallback buffer cleared")

    async def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do buffer."""
        async with self._lock:
            # Conta eventos por tabela
            table_counts: dict[str, int] = {}
            oldest_timestamp = None
            newest_timestamp = None

            for event in self._buffer:
                table = event["table"]
                table_counts[table] = table_counts.get(table, 0) + 1

                timestamp = event.get("timestamp")
                if timestamp:
                    if oldest_timestamp is None or timestamp < oldest_timestamp:
                        oldest_timestamp = timestamp
                    if newest_timestamp is None or timestamp > newest_timestamp:
                        newest_timestamp = timestamp

            return {
                "total_events": len(self._buffer),
                "capacity": self.capacity,
                "utilization_percent": round(len(self._buffer) / self.capacity * 100, 2),
                "table_counts": table_counts,
                "oldest_event": oldest_timestamp,
                "newest_event": newest_timestamp,
                "redis_persistence": bool(self.redis),
            }

    async def _persist_to_redis(self) -> None:
        """Persiste buffer atual no Redis."""
        if not self.redis:
            return

        try:
            # Serializa buffer para JSON
            buffer_data = json.dumps(list(self._buffer), default=str)

            # Salva no Redis com TTL
            await self.redis.set(
                key=self._redis_key,
                value={"buffer": buffer_data},
                ttl=self.redis_ttl,
            )
        except Exception as e:
            logger.warning("Failed to persist buffer to Redis", error=str(e))

    async def _load_from_redis(self) -> None:
        """Recupera buffer do Redis após restart."""
        if not self.redis:
            return

        try:
            cached = await self.redis.get(self._redis_key)
            if cached and "buffer" in cached:
                buffer_list = json.loads(cached["buffer"])
                self._buffer.clear()
                self._buffer.extend(buffer_list)
                FALLBACK_BUFFER_SIZE.set(len(self._buffer))
                logger.info(
                    "Buffer recovered from Redis",
                    events_count=len(self._buffer),
                )
        except Exception as e:
            logger.warning("Failed to load buffer from Redis", error=str(e))
