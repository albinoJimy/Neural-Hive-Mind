"""
Métricas customizadas para Motor de Tradução Semântica

Define métricas Prometheus específicas para observabilidade do serviço.
"""

from prometheus_client import Counter, Histogram, Gauge


# Métricas de DAG
dag_complexity_histogram = Histogram(
    'neural_hive_dag_complexity',
    'Distribuição de complexidade dos DAGs gerados',
    ['domain'],
    buckets=[1, 3, 5, 10, 15, 20, 30, 50]
)

dag_depth_histogram = Histogram(
    'neural_hive_dag_depth',
    'Profundidade dos DAGs gerados',
    ['domain'],
    buckets=[1, 2, 3, 4, 5, 7, 10]
)

# Métricas de risco (STE-specific, biblioteca usa neural_hive_risk_score sem risk_band)
risk_score_histogram = Histogram(
    'neural_hive_ste_risk_score',
    'Distribuição de scores de risco (STE)',
    ['domain', 'risk_band'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Métricas de Knowledge Graph
knowledge_graph_query_duration = Histogram(
    'neural_hive_kg_query_duration_seconds',
    'Duração de queries ao Knowledge Graph',
    ['query_type'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Métricas de Ledger
ledger_write_duration = Histogram(
    'neural_hive_ledger_write_duration_seconds',
    'Duração de escritas no ledger',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Métricas de revisão humana
plans_requiring_review_total = Counter(
    'neural_hive_plans_requiring_review_total',
    'Total de planos que requerem revisão humana',
    ['domain', 'reason']
)

# Métricas de explicabilidade
explainability_tokens_generated_total = Counter(
    'neural_hive_explainability_tokens_generated_total',
    'Total de tokens de explicabilidade gerados',
    ['domain']
)

# Métricas de geração de planos
plan_generation_duration = Histogram(
    'neural_hive_plan_generation_duration_seconds',
    'Tempo para gerar planos cognitivos',
    ['channel'],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5]
)

plans_generated_total = Counter(
    'neural_hive_plans_generated_total',
    'Total de planos cognitivos gerados',
    ['channel', 'status']
)

# Métricas NLP
nlp_extraction_duration = Histogram(
    'neural_hive_nlp_extraction_duration_seconds',
    'Duração das operações de extração NLP',
    ['operation'],  # keywords, objectives, entities
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

nlp_cache_hits_total = Counter(
    'neural_hive_nlp_cache_hits_total',
    'Total de cache hits NLP'
)

nlp_cache_misses_total = Counter(
    'neural_hive_nlp_cache_misses_total',
    'Total de cache misses NLP'
)

nlp_extraction_errors_total = Counter(
    'neural_hive_nlp_extraction_errors_total',
    'Total de erros de extração NLP',
    ['operation', 'error_type']
)

nlp_keywords_extracted = Histogram(
    'neural_hive_nlp_keywords_extracted',
    'Quantidade de keywords extraídas por request',
    buckets=[1, 2, 3, 5, 7, 10, 15]
)

nlp_objectives_extracted = Histogram(
    'neural_hive_nlp_objectives_extracted',
    'Quantidade de objectives extraídos por request',
    buckets=[1, 2, 3, 4, 5]
)

nlp_entities_extracted = Histogram(
    'neural_hive_nlp_entities_extracted',
    'Quantidade de entidades extraídas por request',
    buckets=[1, 2, 3, 5, 7, 10, 15, 20]
)


class NeuralHiveMetrics:
    """Wrapper for Neural Hive metrics"""

    def __init__(self, service_name: str, component: str, layer: str):
        self.service_name = service_name
        self.component = component
        self.layer = layer

    def observe_geracao_duration(
        self,
        duration: float,
        channel: str,
        trace_id: str = None,
        span_id: str = None
    ):
        """Record plan generation duration"""
        plan_generation_duration.labels(channel=channel).observe(duration)

    def increment_plans(self, channel: str, status: str):
        """Increment plan counter"""
        plans_generated_total.labels(channel=channel, status=status).inc()


def register_metrics():
    """Register all custom metrics"""
    # Metrics are auto-registered with prometheus_client
    pass
