"""Métricas Prometheus customizadas para o serviço."""

from prometheus_client import Counter, Gauge, Histogram, Summary
from prometheus_client import CollectorRegistry
from typing import Literal


# Registry customizada para métricas da aplicação
custom_registry = CollectorRegistry()


# Contadores
pipeline_runs_total = Counter(
    "pipeline_runs_total",
    "Total number of pipeline runs",
    ["repo_url", "status", "provider"],
    registry=custom_registry,
)

pipeline_anomalies_total = Counter(
    "pipeline_anomalies_total",
    "Total number of detected anomalies",
    ["repo_url", "type", "severity"],
    registry=custom_registry,
)

pipeline_anomalies_resolved = Counter(
    "pipeline_anomalies_resolved_total",
    "Total number of resolved anomalies",
    ["repo_url"],
    registry=custom_registry,
)

api_requests_total = Counter(
    "api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
    registry=custom_registry,
)

# Gauges
active_runs = Gauge(
    "active_pipeline_runs",
    "Number of currently active pipeline runs",
    ["repo_url"],
    registry=custom_registry,
)

queue_size = Gauge(
    "pipeline_queue_size",
    "Number of pipeline runs waiting to execute",
    registry=custom_registry,
)

success_rate = Gauge(
    "pipeline_success_rate",
    "Success rate of pipeline runs per repository",
    ["repo_url"],
    registry=custom_registry,
)

average_duration = Gauge(
    "pipeline_average_duration_seconds",
    "Average duration of pipeline runs per repository",
    ["repo_url"],
    registry=custom_registry,
)

unresolved_anomalies = Gauge(
    "unresolved_anomalies",
    "Number of unresolved anomalies per repository",
    ["repo_url", "severity"],
    registry=custom_registry,
)

# Histograms para duração
pipeline_duration = Histogram(
    "pipeline_run_duration_seconds",
    "Pipeline run duration in seconds",
    ["repo_url", "status"],
    buckets=[60, 300, 600, 1800, 3600, 7200],  # 1m, 5m, 10m, 30m, 1h, 2h
    registry=custom_registry,
)

api_request_duration = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=custom_registry,
)

# Summary para duração de estágios específicos
stage_duration = Summary(
    "pipeline_stage_duration_seconds",
    "Pipeline stage duration in seconds",
    ["stage", "repo_url"],
    registry=custom_registry,
)


class MetricsHelper:
    """Helper para registrar métricas."""

    @staticmethod
    def record_pipeline_run(
        repo_url: str,
        status: Literal["success", "failed", "cancelled"],
        provider: str,
        duration_seconds: float | None = None,
    ) -> None:
        """Registra uma execução de pipeline."""
        pipeline_runs_total.labels(
            repo_url=repo_url, status=status, provider=provider
        ).inc()

        if duration_seconds is not None:
            pipeline_duration.labels(repo_url=repo_url, status=status).observe(
                duration_seconds
            )

    @staticmethod
    def record_anomaly(
        repo_url: str,
        anomaly_type: str,
        severity: Literal["low", "medium", "high", "critical"],
    ) -> None:
        """Registra uma anomalia detectada."""
        pipeline_anomalies_total.labels(
            repo_url=repo_url, type=anomaly_type, severity=severity
        ).inc()

        # Incrementa gauge de anomalias não resolvidas
        unresolved_anomalies.labels(repo_url=repo_url, severity=severity).inc()

    @staticmethod
    def record_anomaly_resolved(repo_url: str, severity: str) -> None:
        """Registra uma anomalia resolvida."""
        pipeline_anomalies_resolved.labels(repo_url=repo_url).inc()

        # Decrementa gauge de anomalias não resolvidas
        unresolved_anomalies.labels(repo_url=repo_url, severity=severity).dec()

    @staticmethod
    def update_active_runs(repo_url: str, count: int) -> None:
        """Atualiza o número de execuções ativas."""
        active_runs.labels(repo_url=repo_url).set(count)

    @staticmethod
    def update_queue_size(count: int) -> None:
        """Atualiza o tamanho da fila."""
        queue_size.set(count)

    @staticmethod
    def update_success_rate(repo_url: str, rate: float) -> None:
        """Atualiza a taxa de sucesso."""
        success_rate.labels(repo_url=repo_url).set(rate)

    @staticmethod
    def update_average_duration(repo_url: str, duration: float) -> None:
        """Atualiza a duração média."""
        average_duration.labels(repo_url=repo_url).set(duration)

    @staticmethod
    def record_stage_duration(stage: str, repo_url: str, duration: float) -> None:
        """Registra a duração de um estágio."""
        stage_duration.labels(stage=stage, repo_url=repo_url).observe(duration)

    @staticmethod
    def record_api_request(
        method: str, endpoint: str, status: int, duration: float
    ) -> None:
        """Registra uma requisição da API."""
        api_requests_total.labels(
            method=method, endpoint=endpoint, status=str(status)
        ).inc()

        api_request_duration.labels(method=method, endpoint=endpoint).observe(duration)


# Função para obter métricas em formato de exposição
def get_metrics_text() -> str:
    """Retorna todas as métricas em formato de texto Prometheus."""
    from prometheus_client import generate_latest, REGISTRY

    # Métricas padrão do Prometheus
    default_metrics = generate_latest(REGISTRY)

    # Métricas customizadas
    custom_metrics = generate_latest(custom_registry)

    return default_metrics + custom_metrics


# Inicializa contadores de anomalias com valor zero para começar
def init_metrics_for_repo(repo_url: str) -> None:
    """Inicializa gauges para um repositório."""
    success_rate.labels(repo_url=repo_url).set(0)
    average_duration.labels(repo_url=repo_url).set(0)
    active_runs.labels(repo_url=repo_url).set(0)

    for severity in ["low", "medium", "high", "critical"]:
        unresolved_anomalies.labels(repo_url=repo_url, severity=severity).set(0)
