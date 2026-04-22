"""Métricas Prometheus para Data Migration Service.

Autor: Neural Hive Mind
Criado: 2026-04-19 (REFACTOR-H-007)
"""

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client import start_http_server as prometheus_start_http_server

# Contadores
cdc_events_processed = Counter(
    "cdc_events_processed_total",
    "Total CDC events processed",
    ["job_id", "operation_type"],
    namespace="data_migration",
)

migration_batches_completed = Counter(
    "migration_batches_completed_total",
    "Total migration batches completed",
    ["job_id", "status"],
    namespace="data_migration",
)

rollback_operations = Counter(
    "rollback_operations_total",
    "Total rollback operations executed",
    ["job_id", "outcome"],
    namespace="data_migration",
)

# Gauges
cdc_consumer_lag = Gauge(
    "cdc_consumer_lag_ms",
    "CDC consumer lag in milliseconds",
    ["job_id"],
    namespace="data_migration",
)

migration_progress = Gauge(
    "migration_progress_percentage",
    "Migration progress percentage",
    ["job_id"],
    namespace="data_migration",
)

active_migrations = Gauge(
    "active_migrations",
    "Number of currently active migrations",
    ["status"],
    namespace="data_migration",
)

postgresql_pool_size = Gauge(
    "postgresql_pool_size",
    "PostgreSQL connection pool size",
    ["pool_type"],
    namespace="data_migration",
)

# Histograms
cdc_processing_duration = Histogram(
    "cdc_processing_duration_seconds",
    "CDC event processing duration",
    ["job_id"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    namespace="data_migration",
)

migration_batch_duration = Histogram(
    "migration_batch_duration_seconds",
    "Migration batch processing duration",
    ["job_id", "batch_size"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0),
    namespace="data_migration",
)

rollback_duration = Histogram(
    "rollback_duration_seconds",
    "Rollback operation duration",
    ["job_id"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
    namespace="data_migration",
)


def increment_cdc_events(job_id: str, operation_type: str) -> None:
    """Incrementa contador de eventos CDC processados."""
    cdc_events_processed.labels(job_id=job_id, operation_type=operation_type).inc()


def set_cdc_consumer_lag(job_id: str, lag_ms: float) -> None:
    """Atualiza lag do consumidor CDC."""
    cdc_consumer_lag.labels(job_id=job_id).set(lag_ms)


def set_migration_progress(job_id: str, progress: float) -> None:
    """Atualiza progresso da migração (0-100)."""
    migration_progress.labels(job_id=job_id).set(progress)


def increment_migration_batch(job_id: str, status: str) -> None:
    """Incrementa contador de batches completados."""
    migration_batches_completed.labels(job_id=job_id, status=status).inc()


def observe_cdc_processing(job_id: str, duration_sec: float) -> None:
    """Registra duração do processamento CDC."""
    cdc_processing_duration.labels(job_id=job_id).observe(duration_sec)


def observe_batch_processing(job_id: str, batch_size: int, duration_sec: float) -> None:
    """Registra duração do processamento de batch."""
    migration_batch_duration.labels(job_id=job_id, batch_size=str(batch_size)).observe(duration_sec)


def observe_rollback(job_id: str, duration_sec: float, outcome: str) -> None:
    """Registra duração e resultado do rollback."""
    rollback_duration.labels(job_id=job_id).observe(duration_sec)
    rollback_operations.labels(job_id=job_id, outcome=outcome).inc()


def set_active_migrations(count: int, status: str) -> None:
    """Atualiza contador de migrações ativas."""
    active_migrations.labels(status=status).set(count)


def set_postgresql_pool_size(pool_type: str, size: int) -> None:
    """Atualiza tamanho do pool de conexões PostgreSQL."""
    postgresql_pool_size.labels(pool_type=pool_type).set(size)


def start_metrics_server(port: int = 9090) -> None:
    """Inicia servidor HTTP para métricas Prometheus."""
    prometheus_start_http_server(port)
