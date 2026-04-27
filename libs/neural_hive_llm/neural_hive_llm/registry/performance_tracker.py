"""
Performance Tracker - Monitoriza performance de modelos em tempo real.

Coleta métricas de latência, throughput e successo para cada modelo.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np


@dataclass
class RequestMetric:
    """Métrica de uma única requisição."""

    model_id: str
    success: bool
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: str | None = None


class PerformanceTracker:
    """
    Tracker de performance para modelos LLM.

    Mantém histórico de requisições e calcula métricas agregadas
    como latência percentis, sucesso rate, tokens por segundo.
    """

    def __init__(
        self,
        max_history_size: int = 1000,
        window_minutes: int = 60,
    ) -> None:
        """
        Inicializa o tracker.

        Args:
            max_history_size: Máximo de requisições no histórico
            window_minutes: Janela temporal em minutos para cálculos
        """
        self._metrics: dict[str, deque[RequestMetric]] = {}
        self._max_history_size = max_history_size
        self._window = timedelta(minutes=window_minutes)
        self._lock = asyncio.Lock()

    async def record_request(self, metric: RequestMetric) -> None:
        """
        Registra métrica de uma requisição.

        Args:
            metric: Métrica da requisição
        """
        async with self._lock:
            if metric.model_id not in self._metrics:
                self._metrics[metric.model_id] = deque(maxlen=self._max_history_size)

            self._metrics[metric.model_id].append(metric)

            # Limpa métricas antigas fora da janela
            self._cleanup_old_metrics(metric.model_id)

    async def get_metrics(
        self,
        model_id: str,
        window_minutes: int | None = None,
    ) -> dict:
        """
        Retorna métricas agregadas para um modelo.

        Args:
            model_id: ID do modelo
            window_minutes: Janela personalizada (usa default se None)

        Returns:
            Dict com métricas agregadas
        """
        async with self._lock:
            if model_id not in self._metrics:
                return self._empty_metrics(model_id)

            window = timedelta(minutes=window_minutes) if window_minutes else self._window
            cutoff = datetime.now(timezone.utc) - window

            # Filtra métricas na janela
            recent_metrics = [m for m in self._metrics[model_id] if m.timestamp >= cutoff]

            if not recent_metrics:
                return self._empty_metrics(model_id)

            # Calcula latências
            latencies = [m.latency_ms for m in recent_metrics if m.success and m.latency_ms > 0]
            successes = [m for m in recent_metrics if m.success]
            failures = [m for m in recent_metrics if not m.success]

            # Métricas de sucesso
            success_count = len(successes)
            failure_count = len(failures)
            total_count = len(recent_metrics)
            success_rate = success_count / total_count if total_count > 0 else 0.0

            # Métricas de latência
            avg_latency = np.mean(latencies) if latencies else 0.0
            p50_latency = float(np.percentile(latencies, 50)) if len(latencies) > 0 else 0.0
            p95_latency = float(np.percentile(latencies, 95)) if len(latencies) > 0 else 0.0
            p99_latency = float(np.percentile(latencies, 99)) if len(latencies) > 0 else 0.0

            # Métricas de custo
            total_cost = sum(m.estimated_cost_usd for m in successes)
            total_tokens_in = sum(m.prompt_tokens for m in successes)
            total_tokens_out = sum(m.completion_tokens for m in successes)

            # Métricas de throughput
            avg_tokens_per_sec = (
                np.mean(
                    [
                        m.completion_tokens / (m.latency_ms / 1000)
                        for m in successes
                        if m.latency_ms > 0
                    ]
                )
                if successes
                else 0.0
            )

            return {
                "model_id": model_id,
                "window_minutes": int(window.total_seconds() / 60),
                "request_count": total_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": success_rate,
                "avg_latency_ms": float(avg_latency),
                "p50_latency_ms": p50_latency,
                "p95_latency_ms": p95_latency,
                "p99_latency_ms": p99_latency,
                "avg_tokens_per_second": float(avg_tokens_per_sec),
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "total_cost_usd": total_cost,
                "avg_cost_per_1k_tokens": (
                    (total_cost / ((total_tokens_in + total_tokens_out) / 1000))
                    if (total_tokens_in + total_tokens_out) > 0
                    else 0.0
                ),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    async def compare_models(self, model_ids: list[str], window_minutes: int | None = None) -> dict:
        """
        Compara métricas entre múltiplos modelos.

        Args:
            model_ids: Lista de IDs dos modelos
            window_minutes: Janela personalizada

        Returns:
            Dict comparativo entre modelos
        """
        metrics = {}
        for model_id in model_ids:
            metrics[model_id] = await self.get_metrics(model_id, window_minutes)

        return {
            "models": metrics,
            "best_performance": self._find_best_performance(metrics),
            "best_cost": self._find_best_cost(metrics),
            "comparison_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _find_best_performance(self, metrics: dict) -> str | None:
        """Encontra modelo com melhor performance."""
        candidates = {
            mid: data
            for mid, data in metrics.items()
            if data.get("success_rate", 0) >= 0.95 and data.get("request_count", 0) >= 10
        }

        if not candidates:
            return None

        # Minimiza latência média
        return min(candidates.items(), key=lambda x: x[1].get("avg_latency_ms", float("inf")))[0]

    def _find_best_cost(self, metrics: dict) -> str | None:
        """Encontra modelo com melhor custo."""
        candidates = {
            mid: data
            for mid, data in metrics.items()
            if data.get("success_rate", 0) >= 0.95 and data.get("request_count", 0) >= 10
        }

        if not candidates:
            return None

        # Minimiza custo por 1k tokens
        return min(
            candidates.items(),
            key=lambda x: x[1].get("avg_cost_per_1k_tokens", float("inf")),
        )[0]

    async def get_health_status(self, model_id: str) -> dict:
        """
        Retorna status de saúde de um modelo.

        Args:
            model_id: ID do modelo

        Returns:
            Dict com status de saúde
        """
        metrics = await self.get_metrics(model_id)

        success_rate = metrics.get("success_rate", 1.0)
        request_count = metrics.get("request_count", 0)

        if request_count < 5:
            health = "unknown"
        elif success_rate >= 0.99:
            health = "healthy"
        elif success_rate >= 0.95:
            health = "degraded"
        else:
            health = "unhealthy"

        return {
            "model_id": model_id,
            "health": health,
            "success_rate": success_rate,
            "request_count": request_count,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def _cleanup_old_metrics(self, model_id: str) -> None:
        """Remove métricas antigas fora da janela."""
        cutoff = datetime.now(timezone.utc) - self._window

        while self._metrics[model_id] and self._metrics[model_id][0].timestamp < cutoff:
            self._metrics[model_id].popleft()

    @staticmethod
    def _empty_metrics(model_id: str = "unknown") -> dict:
        """Retorna dict de métricas vazio."""
        return {
            "model_id": model_id,
            "window_minutes": 0,
            "request_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "avg_tokens_per_second": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_cost_usd": 0.0,
            "avg_cost_per_1k_tokens": 0.0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    async def cleanup(self) -> None:
        """Limpa todos os dados do tracker."""
        async with self._lock:
            self._metrics.clear()


# Singleton global
_tracker: PerformanceTracker | None = None


def get_tracker() -> PerformanceTracker:
    """
    Retorna o tracker global (singleton).

    Returns:
        PerformanceTracker: Instância global do tracker
    """
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker


def reset_tracker() -> None:
    """Reseta o tracker (útil para testes)."""
    global _tracker
    _tracker = None
