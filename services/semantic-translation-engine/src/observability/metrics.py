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

# Métricas de Detecção Destrutiva
destructive_operations_detected_total = Counter(
    'neural_hive_destructive_operations_detected_total',
    'Total de operações destrutivas detectadas',
    ['severity', 'detection_type']
)

destructive_tasks_per_plan = Histogram(
    'neural_hive_destructive_tasks_per_plan',
    'Número de tasks destrutivas por plano',
    buckets=[1, 2, 3, 5, 10, 20]
)

# Métricas de Workflow de Aprovação
plans_blocked_for_approval_total = Counter(
    'neural_hive_plans_blocked_for_approval_total',
    'Total de planos bloqueados aguardando aprovação',
    ['risk_band', 'is_destructive', 'channel']
)

approval_decision_duration_seconds = Histogram(
    'neural_hive_approval_decision_duration_seconds',
    'Tempo gasto avaliando critérios de aprovação',
    ['decision'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
)

# Métricas de Processamento de Respostas de Aprovação
approval_decisions_processed_total = Counter(
    'neural_hive_approval_decisions_processed_total',
    'Total de decisões de aprovação processadas',
    ['decision', 'risk_band', 'is_destructive']
)

approval_processing_duration_seconds = Histogram(
    'neural_hive_approval_processing_duration_seconds',
    'Tempo para processar resposta de aprovação',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)

approval_time_to_decision_seconds = Histogram(
    'neural_hive_approval_time_to_decision_seconds',
    'Tempo desde request até decisão de aprovação',
    ['decision'],
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 28800]  # 1min a 8h
)

approval_ledger_update_errors_total = Counter(
    'neural_hive_approval_ledger_update_errors_total',
    'Total de erros ao atualizar ledger com decisão de aprovação',
    ['error_type']
)

# Métricas de Task Splitting
tasks_split_total = Counter(
    'neural_hive_tasks_split_total',
    'Total de tasks que foram divididas em subtasks',
    ['split_reason', 'depth_level']
)

subtasks_generated_total = Counter(
    'neural_hive_subtasks_generated_total',
    'Total de subtasks geradas por splitting',
    ['parent_task_type']
)

task_splitting_depth = Histogram(
    'neural_hive_task_splitting_depth',
    'Profundidade de splitting recursivo alcançada',
    buckets=[1, 2, 3, 4, 5]
)

task_complexity_score = Histogram(
    'neural_hive_task_complexity_score',
    'Score de complexidade calculado para tasks',
    ['task_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

task_splitting_duration_seconds = Histogram(
    'neural_hive_task_splitting_duration_seconds',
    'Tempo gasto em operações de task splitting',
    ['split_type'],  # pattern_based, heuristic_based
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
)

# Métricas de DAG Generation Avançado
dag_generation_pattern_matches_total = Counter(
    'neural_hive_dag_generation_pattern_matches_total',
    'Total de pattern matches durante geração de DAG',
    ['pattern_id']
)

dag_generation_parallel_groups_total = Histogram(
    'neural_hive_dag_generation_parallel_groups',
    'Número de grupos paralelos detectados por DAG',
    buckets=[0, 1, 2, 3, 5, 7, 10, 15]
)

dag_generation_entity_dependencies_added = Counter(
    'neural_hive_dag_generation_entity_dependencies_added',
    'Total de dependências adicionadas por análise de entidades'
)

dag_generation_duration_seconds = Histogram(
    'neural_hive_dag_generation_duration_seconds',
    'Tempo de geração de DAG por tipo de decomposição',
    ['decomposition_type'],  # legacy, pattern, heuristic
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)

# Métricas de Detecção de Conflitos
dag_generation_conflicts_detected_total = Counter(
    'neural_hive_dag_generation_conflicts_detected_total',
    'Total de conflitos detectados na análise de entidades',
    ['conflict_type', 'severity']
)

dag_generation_conflicts_resolved_total = Counter(
    'neural_hive_dag_generation_conflicts_resolved_total',
    'Total de conflitos resolvidos',
    ['resolution_strategy']
)

dag_generation_entity_matching_fuzzy_total = Counter(
    'neural_hive_dag_generation_entity_matching_fuzzy_total',
    'Total de matches fuzzy de entidades'
)

dag_generation_visualization_generated_total = Counter(
    'neural_hive_dag_generation_visualization_generated_total',
    'Total de visualizações geradas',
    ['format']  # mermaid, matrix, report
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

    def record_plan_blocked_for_approval(
        self,
        risk_band: str,
        is_destructive: bool,
        channel: str
    ):
        """Record metric for plans blocked awaiting approval"""
        plans_blocked_for_approval_total.labels(
            risk_band=risk_band,
            is_destructive=str(is_destructive).lower(),
            channel=channel
        ).inc()

    def observe_approval_decision_duration(
        self,
        duration: float,
        decision: str
    ):
        """Record time spent evaluating approval criteria"""
        approval_decision_duration_seconds.labels(decision=decision).observe(duration)

    def record_approval_decision(
        self,
        decision: str,
        risk_band: str,
        is_destructive: bool
    ):
        """Registra decisão de aprovação processada"""
        approval_decisions_processed_total.labels(
            decision=decision,
            risk_band=risk_band,
            is_destructive=str(is_destructive).lower()
        ).inc()

    def observe_approval_processing_duration(self, duration: float):
        """Registra tempo de processamento de aprovação"""
        approval_processing_duration_seconds.observe(duration)

    def observe_approval_time_to_decision(
        self,
        duration: float,
        decision: str
    ):
        """Registra tempo desde request até decisão"""
        approval_time_to_decision_seconds.labels(decision=decision).observe(duration)

    def increment_approval_ledger_error(self, error_type: str):
        """Registra erro ao atualizar ledger com decisão de aprovação"""
        approval_ledger_update_errors_total.labels(error_type=error_type).inc()


def register_metrics():
    """Register all custom metrics"""
    # Metrics are auto-registered with prometheus_client
    pass
