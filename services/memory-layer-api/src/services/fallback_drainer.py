"""
Fallback Drainer

Task assíncrono que drena eventos do buffer de fallback para o MongoDB.
"""
import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)

# Métricas Prometheus
DRAIN_TASK_STATUS = Gauge(
    "memory_clickhouse_fallback_drainer_running",
    "Status do drainer de fallback (1=running, 0=stopped)",
)

DRAIN_CYCLES_TOTAL = Counter(
    "memory_clickhouse_fallback_drainer_cycles_total",
    "Total de ciclos de drenagem executados",
)

DRAIN_EVENTS_ATTEMPTED = Counter(
    "memory_clickhouse_fallback_drainer_events_attempted_total",
    "Total de eventos tentados para drenagem",
)

DRAIN_EVENTS_SUCCESS = Counter(
    "memory_clickhouse_fallback_drainer_events_success_total",
    "Total de eventos drenados com sucesso",
)

DRAIN_EVENTS_FAILED = Counter(
    "memory_clickhouse_fallback_drainer_events_failed_total",
    "Total de eventos que falharam na drenagem",
)

DRAIN_DURATION_SECONDS = Histogram(
    "memory_clickhouse_fallback_drainer_duration_seconds",
    "Duração dos ciclos de drenagem",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)


class FallbackDrainer:
    """
    Drainer periódico para esvaziar buffer de fallback para MongoDB.

    Funcionamento:
    - Executa a cada intervalo configurado (default: 30s)
    - Drena em batches configuráveis (default: 100 eventos)
    - Insere no MongoDB para recuperação posterior
    - Suporta graceful shutdown
    """

    # Coleção MongoDB para eventos drenados
    DRAINED_COLLECTION = "clickhouse_fallback_drained"

    def __init__(
        self,
        fallback_buffer,
        mongodb_client,
        settings,
        drain_interval_seconds: int = 30,
        batch_size: int = 100,
    ):
        self.buffer = fallback_buffer
        self.mongodb = mongodb_client
        self.settings = settings
        self.drain_interval = drain_interval_seconds
        self.batch_size = batch_size

        # Task control
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._running = False

    async def start(self) -> None:
        """Inicia o drainer em background."""
        if self._running:
            logger.warning("Fallback drainer already running")
            return

        self._running = True
        self._stop_event.clear()
        DRAIN_TASK_STATUS.set(1)

        self._task = asyncio.create_task(self._drain_loop())
        logger.info(
            "Fallback drainer started",
            interval_seconds=self.drain_interval,
            batch_size=self.batch_size,
        )

    async def stop(self) -> None:
        """Para o drainer com graceful shutdown."""
        if not self._running:
            return

        logger.info("Stopping fallback drainer...")
        self._stop_event.set()
        self._running = False

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        DRAIN_TASK_STATUS.set(0)
        logger.info("Fallback drainer stopped")

    async def drain_once(self) -> dict[str, Any]:
        """
        Executa um ciclo de drenagem imediato.

        Returns:
            Estatísticas do ciclo
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Tenta pegar eventos do buffer
            events = await self.buffer.take_events(self.batch_size)

            if not events:
                return {
                    "events_attempted": 0,
                    "events_success": 0,
                    "events_failed": 0,
                    "duration_seconds": 0,
                }

            DRAIN_CYCLES_TOTAL.inc()
            DRAIN_EVENTS_ATTEMPTED.inc(len(events))

            # Processa cada evento
            success_count = 0
            failed_count = 0

            for event in events:
                try:
                    await self._persist_to_mongodb(event)
                    success_count += 1
                    DRAIN_EVENTS_SUCCESS.inc()
                except Exception:
                    failed_count += 1
                    DRAIN_EVENTS_FAILED.inc()
                    logger.exception(
                        "Failed to persist event to MongoDB",
                        extra={"table": event.get("table")},
                    )

            duration = asyncio.get_event_loop().time() - start_time
            DRAIN_DURATION_SECONDS.observe(duration)

            result = {
                "events_attempted": len(events),
                "events_success": success_count,
                "events_failed": failed_count,
                "duration_seconds": round(duration, 3),
            }

            if success_count > 0:
                logger.info(
                    "Drain cycle completed",
                    **result,
                    buffer_size=await self.buffer.size(),
                )

            return result

        except Exception:
            duration = asyncio.get_event_loop().time() - start_time
            logger.exception("Drain cycle failed")
            return {
                "events_attempted": 0,
                "events_success": 0,
                "events_failed": 0,
                "duration_seconds": round(duration, 3),
            }

    async def _drain_loop(self) -> None:
        """Loop principal de drenagem."""
        while not self._stop_event.is_set():
            try:
                # Executa ciclo de drenagem
                await self.drain_once()

                # Aguarda próximo ciclo ou sinal de parada
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.drain_interval,
                    )

            except asyncio.CancelledError:
                logger.info("Drain loop cancelled")
                break
            except Exception:
                logger.exception("Unexpected error in drain loop")
                # Aguarda antes de tentar novamente
                await asyncio.sleep(5)

    async def _persist_to_mongodb(self, event: dict[str, Any]) -> None:
        """
        Persiste evento do buffer no MongoDB.

        Args:
            event: Evento do buffer de fallback
        """
        document = {
            "table": event.get("table"),
            "rows": event.get("rows"),
            "column_names": event.get("column_names"),
            "metadata": event.get("metadata", {}),
            "buffered_at": event.get("timestamp"),
            "drained_at": datetime.now(timezone.utc).isoformat(),
            "drained": False,  # Marcado como não drenado para ClickHouse ainda
        }

        await self.mongodb.insert_one(
            collection=self.DRAINED_COLLECTION,
            document=document,
        )

    async def get_stats(self) -> dict[str, Any]:
        """
        Retorna estatísticas do drainer.

        Returns:
            Estatísticas de execução
        """
        buffer_stats = await self.buffer.get_stats()

        # Conta eventos não drenados no MongoDB
        try:
            pending_drain = await self.mongodb.count(
                collection=self.DRAINED_COLLECTION,
                filter={"drained": False},
            )
        except Exception:
            pending_drain = 0

        return {
            "running": self._running,
            "drain_interval_seconds": self.drain_interval,
            "batch_size": self.batch_size,
            "buffer_stats": buffer_stats,
            "pending_drain_in_mongodb": pending_drain,
        }
