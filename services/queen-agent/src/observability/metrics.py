from prometheus_client import Counter, Histogram, Gauge


class QueenAgentMetrics:
    """Métricas Prometheus customizadas do Queen Agent"""

    # Decisões Estratégicas
    strategic_decisions_total = Counter(
        'strategic_decisions_total',
        'Total de decisões estratégicas tomadas',
        ['decision_type', 'status']
    )

    strategic_decision_duration_seconds = Histogram(
        'strategic_decision_duration_seconds',
        'Duração de processamento de decisões',
        ['decision_type']
    )

    strategic_decision_confidence = Histogram(
        'strategic_decision_confidence',
        'Distribuição de confidence scores',
        ['decision_type']
    )

    strategic_decision_risk = Histogram(
        'strategic_decision_risk',
        'Distribuição de risk scores',
        ['decision_type']
    )

    # Conflitos
    conflicts_detected_total = Counter(
        'conflicts_detected_total',
        'Total de conflitos detectados',
        ['conflict_domain']
    )

    conflicts_resolved_total = Counter(
        'conflicts_resolved_total',
        'Total de conflitos resolvidos',
        ['conflict_domain', 'resolution_strategy']
    )

    # Replanning
    replannings_triggered_total = Counter(
        'replannings_triggered_total',
        'Total de replanejamentos acionados',
        ['reason']
    )

    replannings_rejected_cooldown_total = Counter(
        'replannings_rejected_cooldown_total',
        'Replanejamentos rejeitados por cooldown'
    )

    active_replannings = Gauge(
        'active_replannings',
        'Replanejamentos ativos no momento'
    )

    # Exceções
    exception_requests_total = Counter(
        'exception_requests_total',
        'Total de solicitações de exceção',
        ['exception_type']
    )

    exception_approvals_total = Counter(
        'exception_approvals_total',
        'Total de exceções aprovadas',
        ['exception_type']
    )

    exception_rejections_total = Counter(
        'exception_rejections_total',
        'Total de exceções rejeitadas',
        ['exception_type']
    )

    # QoS
    qos_adjustments_total = Counter(
        'qos_adjustments_total',
        'Total de ajustes de QoS',
        ['adjustment_type', 'status']
    )

    # Telemetria
    system_health_score = Gauge(
        'system_health_score',
        'Score geral de saúde do sistema (0-1)'
    )

    sla_compliance_ratio = Gauge(
        'sla_compliance_ratio',
        'Ratio de compliance de SLA'
    )

    active_incidents = Gauge(
        'active_incidents',
        'Número de incidentes ativos'
    )

    # Kafka
    kafka_messages_consumed_total = Counter(
        'kafka_messages_consumed_total',
        'Total de mensagens consumidas',
        ['topic']
    )

    kafka_messages_published_total = Counter(
        'kafka_messages_published_total',
        'Total de mensagens publicadas',
        ['topic']
    )

    # gRPC
    grpc_requests_total = Counter(
        'queen_agent_grpc_requests_total',
        'Total de requisições gRPC',
        ['method', 'status']
    )

    grpc_request_duration_seconds = Histogram(
        'queen_agent_grpc_request_duration_seconds',
        'Duração de requisições gRPC em segundos',
        ['method'],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    active_decisions = Gauge(
        'queen_agent_active_decisions',
        'Número de decisões estratégicas ativas no sistema'
    )

    system_status_queries_total = Counter(
        'queen_agent_system_status_queries_total',
        'Total de queries de status do sistema'
    )

    insights_received_total = Counter(
        'queen_agent_insights_received_total',
        'Total de insights recebidos do Analyst Agent',
        ['insight_type', 'priority', 'accepted']
    )

    # OPA Policy Engine
    opa_evaluations_total = Counter(
        'queen_agent_opa_evaluations_total',
        'Total de avaliações OPA realizadas',
        ['policy', 'result']
    )

    opa_denials_total = Counter(
        'queen_agent_opa_denials_total',
        'Total de decisões negadas por OPA policies',
        ['policy', 'rule', 'severity']
    )

    opa_warnings_total = Counter(
        'queen_agent_opa_warnings_total',
        'Total de warnings gerados por OPA',
        ['policy', 'rule']
    )

    opa_evaluation_duration_seconds = Histogram(
        'queen_agent_opa_evaluation_duration_seconds',
        'Tempo de avaliação de políticas OPA',
        buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
    )

    # Guardrails
    guardrails_validated_total = Counter(
        'queen_agent_guardrails_validated_total',
        'Total de guardrails validados',
        ['guardrail_type']
    )

    guardrails_violations_total = Counter(
        'queen_agent_guardrails_violations_total',
        'Total de violações de guardrails',
        ['violation_type', 'severity']
    )

    # Pheromone Trails
    pheromone_trails_scan_duration_seconds = Histogram(
        'queen_agent_pheromone_trails_scan_duration_seconds',
        'Duração de scans de trilhas de feromônio em segundos',
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
    )

    pheromone_trails_cache_hits_total = Counter(
        'queen_agent_pheromone_trails_cache_hits_total',
        'Total de cache hits para trilhas de feromônio'
    )

    pheromone_trails_cache_misses_total = Counter(
        'queen_agent_pheromone_trails_cache_misses_total',
        'Total de cache misses para trilhas de feromônio'
    )

    pheromone_trails_keys_scanned_total = Counter(
        'queen_agent_pheromone_trails_keys_scanned_total',
        'Total de chaves escaneadas para trilhas de feromônio'
    )
