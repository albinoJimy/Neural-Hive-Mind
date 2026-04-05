"""
Métricas Prometheus para ML Inference API.
"""
from prometheus_client import Counter, Gauge, Histogram, Info, Summary


class MLInferenceMetrics:
    """Métricas customizadas do serviço de inferência ML."""

    def __init__(self, service_name: str = "ml-inference-api"):
        """Inicializa métricas."""

        # Service Info
        self.service_info = Info("service", "Service information")
        self.service_info.info({"name": service_name, "version": "1.0.0"})

        # Model
        self.model_loaded = Gauge(
            "model_loaded", "Se o modelo ML está carregado"
        )
        self.model_loading_duration_seconds = Histogram(
            "model_loading_duration_seconds",
            "Duração do carregamento do modelo",
        )
        self.model_version_info = Info(
            "model_version", "Informações da versão do modelo"
        )

        # Inference
        self.predictions_total = Counter(
            "predictions_total",
            "Total de predições realizadas",
            ["decision"],  # approve, reject, review_required
        )
        self.prediction_duration_seconds = Histogram(
            "prediction_duration_seconds",
            "Duração da predição",
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )
        self.prediction_confidence = Histogram(
            "prediction_confidence",
            "Distribuição de confiança das predições",
            buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        # Batch Inference
        self.batch_predictions_total = Counter(
            "batch_predictions_total",
            "Total de batch predictions realizadas",
        )
        self.batch_size = Histogram(
            "batch_size",
            "Tamanho dos batches processados",
            buckets=[1, 5, 10, 25, 50, 75, 100],
        )
        self.batch_duration_seconds = Histogram(
            "batch_duration_seconds",
            "Duração do processamento em batch",
        )
        self.batch_avg_latency_ms = Summary(
            "batch_avg_latency_ms",
            "Latência média por item em batch (ms)",
        )

        # API
        self.api_requests_total = Counter(
            "api_requests_total",
            "Total de requests REST API",
            ["method", "endpoint", "status_code"],
        )
        self.api_request_duration_seconds = Histogram(
            "api_request_duration_seconds",
            "Latência de requests API",
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        self.api_errors_total = Counter(
            "api_errors_total",
            "Total de erros na API",
            ["endpoint", "error_type"],
        )

        # Circuit Breaker
        self.circuit_breaker_state = Gauge(
            "circuit_breaker_state",
            "Estado do circuit breaker (0=closed, 1=open, 2=half_open)",
        )
        self.circuit_breaker_failures_total = Counter(
            "circuit_breaker_failures_total",
            "Total de falhas que triggeraram o circuit breaker",
        )
        self.circuit_breaker_recoveries_total = Counter(
            "circuit_breaker_recoveries_total",
            "Total de recuperações do circuit breaker",
        )

        # Rate Limiting
        self.rate_limit_hits_total = Counter(
            "rate_limit_hits_total",
            "Total de requests bloqueados por rate limit",
        )

        # Feature Extraction
        self.feature_extraction_duration_seconds = Histogram(
            "feature_extraction_duration_seconds",
            "Duração da extração de features NLP",
        )

        # Model Cache (se implementado)
        self.cache_hits_total = Counter(
            "cache_hits_total",
            "Total de cache hits",
            ["cache_type"],
        )
        self.cache_misses_total = Counter(
            "cache_misses_total",
            "Total de cache misses",
            ["cache_type"],
        )
