"""
Serviço de predição que wrapper o ApprovalPredictor.

Este serviço fornece uma interface assíncrona para o ApprovalPredictor
com suporte a circuit breaker, métricas e tracing.
"""
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

from ..config import get_settings
from ..observability.metrics import MLInferenceMetrics
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


logger = structlog.get_logger()
settings = get_settings()


# Importação tardia para evitar falha se ML não estiver disponível
ApprovalPredictor = None


class PredictorService:
    """
    Serviço wrapper para ApprovalPredictor com circuit breaker.

    Carrega o modelo ML e fornece métodos de predição com:
    - Circuit breaker para proteção
    - Métricas Prometheus
    - Logging estruturado
    - Cache opcional de predições
    """

    def __init__(self, metrics: MLInferenceMetrics):
        """
        Inicializa serviço de predição.

        Args:
            metrics: Instância de métricas Prometheus
        """
        self.metrics = metrics
        self.model_path: Optional[Path] = None
        self.approval_predictor: Optional[Any] = None
        self.model_info: Dict[str, Any] = {}
        self._circuit_breaker = CircuitBreaker(
            name="ml_inference",
            threshold=settings.circuit_breaker_threshold,
            timeout_seconds=settings.circuit_breaker_timeout_seconds,
        )
        self._load_lock = asyncio.Lock()

    async def load_model(self) -> None:
        """
        Carrega o modelo ML de forma assíncrona.

        Usa lock para evitar carregamentos concorrentes.
        """
        async with self._load_lock:
            if self.approval_predictor is not None:
                return  # Já carregado

            start_time = time.time()
            logger.info("loading_ml_model", path=settings.local_model_path)

            try:
                # Importar ApprovalPredictor
                global ApprovalPredictor
                if ApprovalPredictor is None:
                    from ml_pipelines.inference.approval_predictor import (
                        ApprovalPredictor as AP,
                    )
                    ApprovalPredictor = AP

                # Carregar em thread separado para não bloquear event loop
                loop = asyncio.get_event_loop()
                self.approval_predictor = await loop.run_in_executor(
                    None, self._load_model_sync
                )

                # Obter informações do modelo
                self.model_info = self.approval_predictor.get_model_info()
                self.model_path = Path(self.approval_predictor.model_path)

                # Atualizar métricas
                loading_time = time.time() - start_time
                self.metrics.model_loaded.set(1)
                self.metrics.model_version_info.info(
                    {
                        "version": str(self.model_info.get("version", "unknown")),
                        "type": str(type(self.approval_predictor.model).__name__),
                        "path": str(self.model_path),
                    }
                )
                self.metrics.model_loading_duration_seconds.observe(loading_time)

                logger.info(
                    "ml_model_loaded",
                    version=self.model_info.get("version"),
                    path=str(self.model_path),
                    loading_time_seconds=loading_time,
                )

            except Exception as e:
                logger.error(
                    "ml_model_load_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self.metrics.model_loaded.set(0)
                raise RuntimeError(f"Failed to load ML model: {e}") from e

    def _load_model_sync(self) -> Any:
        """Carrega modelo de forma síncrona (executado em executor)."""
        if ApprovalPredictor is None:
            raise ImportError("ApprovalPredictor not imported")

        return ApprovalPredictor()

    async def predict(
        self,
        intent_text: str,
        specialist_confidence: float = 0.5,
        specialist_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Faz predição usando o modelo ML com circuit breaker.

        Args:
            intent_text: Texto da intenção
            specialist_confidence: Confiança do especialista (0.0-1.0)
            specialist_type: Tipo de especialista (para tracing)

        Returns:
            Dicionário com decision, confidence, probabilities

        Raises:
            CircuitBreakerOpenError: Se circuit breaker está aberto
            RuntimeError: Se modelo não está carregado
        """
        if self.approval_predictor is None:
            await self.load_model()

        start_time = time.time()

        try:
            # Usar circuit breaker para proteção
            result = await self._circuit_breaker.acall(
                self._predict_sync,
                intent_text,
                specialist_confidence,
            )

            # Registrar métricas
            inference_time = (time.time() - start_time) * 1000  # ms
            self.metrics.predictions_total.labels(decision=result["decision"]).inc()
            self.metrics.prediction_duration_seconds.observe(time.time() - start_time)
            self.metrics.prediction_confidence.observe(result["confidence"])

            logger.debug(
                "prediction_completed",
                decision=result["decision"],
                confidence=result["confidence"],
                inference_time_ms=inference_time,
                specialist_type=specialist_type,
            )

            return result

        except CircuitBreakerOpenError:
            # Re-levanta com contexto adicional
            logger.error("circuit_breaker_open_rejecting_prediction")
            self.metrics.api_errors_total.labels(
                endpoint="/predict", error_type="circuit_breaker_open"
            ).inc()
            raise

        except Exception as e:
            logger.error(
                "prediction_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.metrics.api_errors_total.labels(
                endpoint="/predict", error_type=type(e).__name__
            ).inc()
            raise

    def _predict_sync(
        self,
        intent_text: str,
        specialist_confidence: float,
    ) -> Dict[str, Any]:
        """Executa predição de forma síncrona."""
        if self.approval_predictor is None:
            raise RuntimeError("Model not loaded")

        return self.approval_predictor.predict_from_text(
            text=intent_text,
            specialist_confidence=specialist_confidence,
        )

    async def predict_from_nlp_features(
        self,
        nlp_features: Dict[str, float],
        specialist_confidence: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Faz predição a partir de features NLP já extraídas.

        Args:
            nlp_features: Dicionário com features NLP
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com decision, confidence, probabilities
        """
        if self.approval_predictor is None:
            await self.load_model()

        start_time = time.time()

        try:
            result = await self._circuit_breaker.acall(
                self._predict_from_features_sync,
                nlp_features,
                specialist_confidence,
            )

            inference_time = (time.time() - start_time) * 1000
            self.metrics.predictions_total.labels(decision=result["decision"]).inc()
            self.metrics.prediction_confidence.observe(result["confidence"])

            return result

        except CircuitBreakerOpenError:
            logger.error("circuit_breaker_open_rejecting_prediction")
            raise

    def _predict_from_features_sync(
        self,
        nlp_features: Dict[str, float],
        specialist_confidence: float,
    ) -> Dict[str, Any]:
        """Executa predição de forma síncrona."""
        if self.approval_predictor is None:
            raise RuntimeError("Model not loaded")

        return self.approval_predictor.predict_from_nlp_features(
            nlp_features=nlp_features,
            specialist_confidence=specialist_confidence,
        )

    def get_model_info(self) -> Dict[str, Any]:
        """Retorna informações sobre o modelo carregado."""
        if not self.model_info:
            return {
                "is_loaded": False,
                "name": settings.mlflow_model_name,
            }

        return {
            "is_loaded": True,
            "name": settings.mlflow_model_name,
            **self.model_info,
        }

    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        """Retorna estado atual do circuit breaker."""
        return self._circuit_breaker.get_state_info()

    def reset_circuit_breaker(self) -> None:
        """Reseta circuit breaker manualmente."""
        self._circuit_breaker.reset()
        logger.info("circuit_breaker_reset_manually")

    @property
    def is_healthy(self) -> bool:
        """Verifica se serviço está saudável."""
        return (
            self.approval_predictor is not None
            and self._circuit_breaker.state.value == 1  # CLOSED
        )


# Singleton global
_predictor_service: Optional[PredictorService] = None


async def get_predictor_service(metrics: MLInferenceMetrics) -> PredictorService:
    """
    Retorna instância singleton do PredictorService.

    Args:
        metrics: Instância de métricas Prometheus

    Returns:
        Instância de PredictorService
    """
    global _predictor_service
    if _predictor_service is None:
        _predictor_service = PredictorService(metrics)
        await _predictor_service.load_model()
    return _predictor_service
