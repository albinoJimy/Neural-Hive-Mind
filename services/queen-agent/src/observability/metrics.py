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
