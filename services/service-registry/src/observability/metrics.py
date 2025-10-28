from prometheus_client import Counter, Gauge, Histogram


class RegistryMetrics:
    """Métricas Prometheus para o Service Registry"""

    # Métricas de registro
    agents_registered_total = Counter(
        'agents_registered_total',
        'Total de agentes registrados',
        ['agent_type']
    )

    agents_deregistered_total = Counter(
        'agents_deregistered_total',
        'Total de agentes desregistrados',
        ['agent_type']
    )

    agents_active = Gauge(
        'agents_active',
        'Número de agentes ativos',
        ['agent_type', 'status']
    )

    # Métricas de heartbeat
    heartbeats_received_total = Counter(
        'heartbeats_received_total',
        'Total de heartbeats recebidos',
        ['agent_type', 'status']
    )

    heartbeat_latency_seconds = Histogram(
        'heartbeat_latency_seconds',
        'Latência de processamento de heartbeat'
    )

    # Métricas de discovery
    discovery_requests_total = Counter(
        'discovery_requests_total',
        'Total de requisições de discovery',
        ['agent_type']
    )

    discovery_duration_seconds = Histogram(
        'discovery_duration_seconds',
        'Duração de requisições de discovery'
    )

    matching_candidates_evaluated = Histogram(
        'matching_candidates_evaluated',
        'Número de candidatos avaliados no matching'
    )

    agents_matched = Histogram(
        'agents_matched',
        'Número de agentes retornados no matching'
    )

    # Métricas de health checks
    health_checks_total = Counter(
        'health_checks_total',
        'Total de health checks executados'
    )

    agents_marked_unhealthy_total = Counter(
        'agents_marked_unhealthy_total',
        'Total de agentes marcados como unhealthy',
        ['agent_type']
    )

    agents_removed_total = Counter(
        'agents_removed_total',
        'Total de agentes removidos por inatividade',
        ['agent_type']
    )

    # Métricas de etcd
    etcd_operations_total = Counter(
        'etcd_operations_total',
        'Total de operações no etcd',
        ['operation', 'status']
    )

    etcd_operation_duration_seconds = Histogram(
        'etcd_operation_duration_seconds',
        'Duração de operações no etcd',
        ['operation']
    )

    @staticmethod
    def record_agent_registered(agent_type: str):
        """Registra métrica de agente registrado"""
        RegistryMetrics.agents_registered_total.labels(agent_type=agent_type).inc()

    @staticmethod
    def record_agent_deregistered(agent_type: str):
        """Registra métrica de agente desregistrado"""
        RegistryMetrics.agents_deregistered_total.labels(agent_type=agent_type).inc()

    @staticmethod
    def record_heartbeat(agent_type: str, status: str):
        """Registra métrica de heartbeat"""
        RegistryMetrics.heartbeats_received_total.labels(
            agent_type=agent_type,
            status=status
        ).inc()

    @staticmethod
    def record_discovery_request(agent_type: str):
        """Registra métrica de requisição de discovery"""
        RegistryMetrics.discovery_requests_total.labels(agent_type=agent_type).inc()

    @staticmethod
    def record_health_check():
        """Registra métrica de health check"""
        RegistryMetrics.health_checks_total.inc()

    @staticmethod
    def record_agent_marked_unhealthy(agent_type: str):
        """Registra métrica de agente marcado como unhealthy"""
        RegistryMetrics.agents_marked_unhealthy_total.labels(agent_type=agent_type).inc()

    @staticmethod
    def record_agent_removed(agent_type: str):
        """Registra métrica de agente removido"""
        RegistryMetrics.agents_removed_total.labels(agent_type=agent_type).inc()

    @staticmethod
    def record_etcd_operation(operation: str, status: str):
        """Registra métrica de operação etcd"""
        RegistryMetrics.etcd_operations_total.labels(
            operation=operation,
            status=status
        ).inc()
