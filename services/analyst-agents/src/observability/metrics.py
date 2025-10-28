from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger()

# Insights gerados
insights_generated_total = Counter(
    'analyst_insights_generated_total',
    'Total de insights gerados',
    ['insight_type', 'priority']
)

# Tempo de processamento
insight_generation_duration_seconds = Histogram(
    'analyst_insight_generation_duration_seconds',
    'Tempo de geração de insights',
    ['insight_type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Consultas executadas
queries_executed_total = Counter(
    'analyst_queries_executed_total',
    'Total de consultas executadas',
    ['source', 'status']
)

# Tempo de consulta
query_duration_seconds = Histogram(
    'analyst_query_duration_seconds',
    'Tempo de execução de consultas',
    ['source'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
)

# Anomalias detectadas
anomalies_detected_total = Counter(
    'analyst_anomalies_detected_total',
    'Total de anomalias detectadas',
    ['metric_name', 'method']
)

# Cache hits/misses
cache_operations_total = Counter(
    'analyst_cache_operations_total',
    'Operações de cache',
    ['operation', 'result']
)

# Insights em cache
insights_cached_gauge = Gauge(
    'analyst_insights_cached',
    'Número de insights em cache'
)

# Kafka consumer lag
kafka_consumer_lag_gauge = Gauge(
    'analyst_kafka_consumer_lag',
    'Lag do consumer Kafka',
    ['topic', 'partition']
)


def setup_metrics():
    """Configurar métricas Prometheus"""
    logger.info('prometheus_metrics_configured')


def record_insight_generated(insight_type: str, priority: str):
    """Registrar insight gerado"""
    insights_generated_total.labels(insight_type=insight_type, priority=priority).inc()


def record_query_executed(source: str, duration: float, status: str):
    """Registrar consulta executada"""
    queries_executed_total.labels(source=source, status=status).inc()
    query_duration_seconds.labels(source=source).observe(duration)


def record_anomaly_detected(metric_name: str, method: str):
    """Registrar anomalia detectada"""
    anomalies_detected_total.labels(metric_name=metric_name, method=method).inc()


def record_cache_operation(operation: str, result: str):
    """Registrar operação de cache"""
    cache_operations_total.labels(operation=operation, result=result).inc()


def update_insights_cached_count(count: int):
    """Atualizar contagem de insights em cache"""
    insights_cached_gauge.set(count)


def update_kafka_consumer_lag(topic: str, partition: str, lag: int):
    """Atualizar lag do consumer Kafka"""
    kafka_consumer_lag_gauge.labels(topic=topic, partition=partition).set(lag)
