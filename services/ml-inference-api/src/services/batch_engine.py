"""
Engine de inferência em batch para processamento eficiente.

Processa múltiplas predições em paralelo com otimizações de batching.
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog

from ..config import get_settings
from ..models.schemas import (
    BatchPredictResponse,
    DecisionType,
    PredictRequest,
    PredictResponse,
)
from ..observability.metrics import MLInferenceMetrics
from .predictor_service import PredictorService

logger = structlog.get_logger()
settings = get_settings()


class BatchInferenceEngine:
    """
    Engine para inferência em batch.

    Processa múltiplas predições em paralelo com:
    - Thread pool para CPU-bound tasks
    - Agregação de estatísticas
    - Tratamento de erros individual por item
    """

    def __init__(
        self,
        predictor_service: PredictorService,
        metrics: MLInferenceMetrics | None = None,
        max_workers: int | None = None,
    ):
        """
        Inicializa engine de batch.

        Args:
            predictor_service: Serviço de predição
            metrics: Métricas Prometheus (opcional, para testes)
            max_workers: Número máximo de workers (default: CPU count)
        """
        self.predictor_service = predictor_service
        self.metrics = metrics
        self.max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    async def process_batch(
        self,
        requests: list[PredictRequest],
        parallel: bool = True,
    ) -> BatchPredictResponse:
        """
        Processa batch de requests de predição.

        Args:
            requests: Lista de requests
            parallel: Se True, processa em paralelo

        Returns:
            BatchPredictResponse com resultados e estatísticas
        """
        start_time = time.time()
        total_requests = len(requests)

        if total_requests > settings.batch_max_size:
            raise ValueError(
                f"Batch size {total_requests} exceeds maximum {settings.batch_max_size}"
            )

        logger.info(
            "starting_batch_inference",
            batch_size=total_requests,
            parallel=parallel,
        )

        if parallel:
            results = await self._process_parallel(requests)
        else:
            results = await self._process_sequential(requests)

        # Compilar estatísticas
        successful = sum(1 for r in results if isinstance(r, PredictResponse))
        failed = total_requests - successful

        # Calcular estatísticas agregadas
        aggregate_stats = self._calculate_aggregate_stats(
            [r for r in results if isinstance(r, PredictResponse)]
        )

        total_time = (time.time() - start_time) * 1000  # ms
        avg_latency = total_time / total_requests if total_requests > 0 else 0

        # Registrar métricas (se disponível)
        if self.metrics:
            self.metrics.batch_predictions_total.inc()
            self.metrics.batch_size.observe(total_requests)
            self.metrics.batch_duration_seconds.observe(time.time() - start_time)
            self.metrics.batch_avg_latency_ms.observe(avg_latency)

        logger.info(
            "batch_inference_completed",
            batch_size=total_requests,
            successful=successful,
            failed=failed,
            total_time_ms=total_time,
            avg_latency_ms=avg_latency,
        )

        return BatchPredictResponse(
            results=[r for r in results if isinstance(r, PredictResponse)],
            total_processed=total_requests,
            successful=successful,
            failed=failed,
            aggregate_stats=aggregate_stats,
            total_inference_time_ms=total_time,
        )

    async def _process_sequential(
        self,
        requests: list[PredictRequest],
    ) -> list[PredictResponse | None]:
        """Processa requests sequencialmente."""
        results: list[PredictResponse | None] = []

        for request in requests:
            try:
                result = await self._predict_single(request)
                results.append(result)
            except Exception as e:
                logger.warning(
                    "single_prediction_failed_in_batch",
                    intent_text=request.intent_text[:50],
                    error=str(e),
                )
                results.append(None)

        return results

    async def _process_parallel(
        self,
        requests: list[PredictRequest],
    ) -> list[PredictResponse | None]:
        """Processa requests em paralelo usando asyncio tasks."""
        # Criar tasks para cada request
        tasks = [self._predict_single(req) for req in requests]

        # Executar em paralelo com gather, capturando exceções
        results_or_exceptions = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        # Processar resultados, convertendo exceções em None
        ordered_results: list[PredictResponse | None] = []
        for i, result_or_exc in enumerate(results_or_exceptions):
            if isinstance(result_or_exc, Exception):
                logger.warning(
                    "parallel_prediction_failed_in_batch",
                    request_index=i,
                    error=str(result_or_exc),
                    error_type=type(result_or_exc).__name__,
                )
                ordered_results.append(None)
            else:
                ordered_results.append(result_or_exc)

        return ordered_results

    async def _predict_single(
        self,
        request: PredictRequest,
    ) -> PredictResponse:
        """
        Executa predição para um único request.

        Args:
            request: PredictRequest

        Returns:
            PredictResponse
        """
        start_time = time.time()

        # Chamar predictor service
        result = await self.predictor_service.predict(
            intent_text=request.intent_text,
            specialist_confidence=request.specialist_confidence,
            specialist_type=request.specialist_type,
        )

        inference_time = (time.time() - start_time) * 1000  # ms

        # Aplicar opções
        probabilities = (
            result.get("probabilities") if request.options and request.options.return_probabilities else None
        )
        features = (
            result.get("features") if request.options and request.options.return_features else None
        )

        # Aplicar threshold customizado se especificado
        decision = result["decision"]
        if request.options and request.options.threshold is not None:
            threshold = request.options.threshold
            if result["confidence"] < threshold:
                decision = DecisionType.REVIEW_REQUIRED

        return PredictResponse(
            decision=DecisionType(decision),
            confidence=result["confidence"],
            probabilities=probabilities,
            features=features,
            model_version=result.get("model_version", "unknown"),
            inference_time_ms=inference_time,
        )

    def _calculate_aggregate_stats(
        self,
        results: list[PredictResponse],
    ) -> dict[str, Any]:
        """
        Calcula estatísticas agregadas dos resultados.

        Args:
            results: Lista de PredictResponse

        Returns:
            Dicionário com estatísticas
        """
        if not results:
            return {}

        # Contar decisões
        decision_counts: dict[str, int] = {}
        confidence_sum = 0.0
        inference_time_sum = 0.0

        for r in results:
            decision_counts[r.decision.value] = decision_counts.get(r.decision.value, 0) + 1
            confidence_sum += r.confidence
            inference_time_sum += r.inference_time_ms

        return {
            "decision_counts": decision_counts,
            "average_confidence": confidence_sum / len(results),
            "average_inference_time_ms": inference_time_sum / len(results),
            "total_inference_time_ms": inference_time_sum,
        }

    async def __aenter__(self):
        """Entry point para context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit point para context manager."""
        if self._executor:
            self._executor.shutdown(wait=True)

    def close(self) -> None:
        """Libera recursos."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


# Singleton
_batch_engine: BatchInferenceEngine | None = None


def get_batch_engine(
    predictor_service: PredictorService,
    metrics: MLInferenceMetrics,
) -> BatchInferenceEngine:
    """
    Retorna instância singleton do BatchInferenceEngine.

    Args:
        predictor_service: Serviço de predição
        metrics: Métricas Prometheus

    Returns:
        Instância de BatchInferenceEngine
    """
    global _batch_engine
    if _batch_engine is None:
        _batch_engine = BatchInferenceEngine(predictor_service, metrics)
    return _batch_engine
