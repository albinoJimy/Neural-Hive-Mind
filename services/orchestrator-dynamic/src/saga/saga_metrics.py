"""Métricas para eventos de Saga."""

from collections import defaultdict
from datetime import UTC, datetime

UTC = UTC  # type: ignore
from time import perf_counter
from typing import Any, Optional

from structlog import get_logger

logger = get_logger(__name__)

# Metrics singleton
_metrics: Optional["SagaMetrics"] = None


class SagaMetrics:
    """Métricas para eventos de Saga.

    Mantém contadores e timers para observabilidade de Sagas.
    """

    # Contadores principais
    COUNTER_SAGA_CREATED = "saga_created"
    COUNTER_SAGA_STARTED = "saga_started"
    COUNTER_SAGA_COMPLETED = "saga_completed"
    COUNTER_SAGA_FAILED = "saga_failed"
    COUNTER_SAGA_COMPENSATING = "saga_compensating"
    COUNTER_SAGA_COMPENSATED = "saga_compensated"
    COUNTER_STEP_COMPLETED = "step_completed"
    COUNTER_STEP_FAILED = "step_failed"

    def __init__(self):
        """Inicializa métricas."""
        self._counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._durations: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._enabled = True

    def enable(self) -> None:
        """Habilita coleta de métricas."""
        self._enabled = True
        logger.info("saga_metrics_enabled")

    def disable(self) -> None:
        """Desabilita coleta de métricas."""
        self._enabled = False
        logger.info("saga_metrics_disabled")

    def increment(
        self, metric_name: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        """Incrementa contador.

        Args:
            metric_name: Nome da métrica
            value: Valor a incrementar (default: 1)
            tags: Tags para agregação
        """
        if not self._enabled:
            return

        tag_key = self._tags_to_key(tags)
        self._counters[metric_name][tag_key] += value

        logger.debug(
            "saga_metric_incremented",
            metric_name=metric_name,
            value=value,
            tags=tags,
            total=self._counters[metric_name][tag_key],
        )

    def record_duration(
        self, operation: str, duration_ms: float, tags: dict[str, str] | None = None
    ) -> None:
        """Registra duração de operação.

        Args:
            operation: Nome da operação
            duration_ms: Duração em millis
            tags: Tags para agregação
        """
        if not self._enabled:
            return

        tag_key = self._tags_to_key(tags)
        self._durations[f"{operation}_duration"][tag_key].append(duration_ms)

        logger.debug(
            "saga_duration_recorded",
            operation=operation,
            duration_ms=duration_ms,
            tags=tags,
        )

    def get_counter(self, metric_name: str, tags: dict[str, str] | None = None) -> int:
        """Retorna valor do contador.

        Args:
            metric_name: Nome da métrica
            tags: Tags para filtrar

        Returns:
            Valor do contador
        """
        tag_key = self._tags_to_key(tags)
        return self._counters[metric_name].get(tag_key, 0)

    def get_counters(self) -> dict[str, dict[str, int]]:
        """Retorna todos os contadores.

        Returns:
            Dicionário com todos os contadores por métrica e tags
        """
        return dict(self._counters)

    def get_durations(self, operation: str) -> dict[str, list]:
        """Retorna duracoes registradas para operacao.

        Args:
            operation: Nome da operacao

        Returns:
            Dicionário com listas de durações por tags
        """
        return dict(self._durations.get(f"{operation}_duration", {}))

    def get_duration_stats(
        self, operation: str, tags: dict[str, str] | None = None
    ) -> dict[str, float]:
        """Retorna estatísticas de duração.

        Args:
            operation: Nome da operacao
            tags: Tags para filtrar

        Returns:
            Dicionário com min, max, avg, count
        """
        tag_key = self._tags_to_key(tags)
        durations = self._durations.get(f"{operation}_duration", {}).get(tag_key, [])

        if not durations:
            return {"min": 0, "max": 0, "avg": 0, "count": 0}

        return {
            "min": min(durations),
            "max": max(durations),
            "avg": sum(durations) / len(durations),
            "count": len(durations),
        }

    def reset_counters(self) -> None:
        """Reseta todos os contadores."""
        self._counters.clear()
        self._durations.clear()
        logger.info("saga_metrics_reset")

    def reset_counter(self, metric_name: str) -> None:
        """Reseta contador específico.

        Args:
            metric_name: Nome da métrica a resetar
        """
        if metric_name in self._counters:
            self._counters[metric_name].clear()
            logger.debug("saga_metric_reset", metric_name=metric_name)

    def get_summary(self) -> dict[str, Any]:
        """Retorna resumo das métricas.

        Returns:
            Dicionário com resumo de contadores e durações
        """
        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "counters": {},
            "durations": {},
        }

        # Agregar contadores
        for metric_name, tagged_counters in self._counters.items():
            total = sum(tagged_counters.values())
            summary["counters"][metric_name] = total

        # Adicionar estatísticas de duração
        for operation_key, tagged_durations in self._durations.items():
            operation = operation_key.replace("_duration", "")
            all_durations = []
            for durations in tagged_durations.values():
                all_durations.extend(durations)

            if all_durations:
                summary["durations"][operation] = {
                    "count": len(all_durations),
                    "min": min(all_durations),
                    "max": max(all_durations),
                    "avg": sum(all_durations) / len(all_durations),
                }

        return summary

    def _tags_to_key(self, tags: dict[str, str] | None) -> str:
        """Converte tags para chave de string.

        Args:
            tags: Dicionário de tags

        Returns:
            String representando as tags
        """
        if not tags:
            return "default"

        # Ordenar tags para consistência
        sorted_items = sorted(tags.items())
        return ",".join(f"{k}={v}" for k, v in sorted_items)


class SagaTimer:
    """Context manager para medir duração de operações (sync e async)."""

    def __init__(self, metrics: SagaMetrics, operation: str, tags: dict[str, str] | None = None):
        """Inicializa timer.

        Args:
            metrics: Instância de SagaMetrics
            operation: Nome da operação
            tags: Tags para agregação
        """
        self._metrics = metrics
        self._operation = operation
        self._tags = tags
        self._start_time: float | None = None

    def __enter__(self) -> "SagaTimer":
        """Inicia timer (sync)."""
        self._start_time = perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Finaliza timer e registra duração (sync)."""
        if self._start_time is not None:
            duration_ms = (perf_counter() - self._start_time) * 1000
            self._metrics.record_duration(self._operation, duration_ms, self._tags)

    async def __aenter__(self) -> "SagaTimer":
        """Inicia timer (async)."""
        self._start_time = perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Finaliza timer e registra duração (async)."""
        if self._start_time is not None:
            duration_ms = (perf_counter() - self._start_time) * 1000
            self._metrics.record_duration(self._operation, duration_ms, self._tags)


def get_saga_metrics() -> SagaMetrics:
    """Retorna instância singleton de SagaMetrics.

    Returns:
        Instância de SagaMetrics
    """
    global _metrics
    if _metrics is None:
        _metrics = SagaMetrics()
    return _metrics


def timer(operation: str, tags: dict[str, str] | None = None) -> SagaTimer:
    """Cria context manager para medir duração.

    Args:
        operation: Nome da operação
        tags: Tags para agregação

    Returns:
        SagaTimer context manager

    Example:
        async with timer('saga_execution', {'plan_id': 'plan-123'}):
            await execute_saga()
    """
    return SagaTimer(get_saga_metrics(), operation, tags)
