from prometheus_client import Counter, Gauge, Histogram, REGISTRY


def _get_or_create_counter(name: str, description: str, labelnames=None):
    """Get existing counter or create new one to avoid duplicate registration errors"""
    try:
        return Counter(name, description, labelnames or [])
    except ValueError:
        return REGISTRY._names_to_collectors.get(name)


def _get_or_create_gauge(name: str, description: str, labelnames=None):
    """Get existing gauge or create new one to avoid duplicate registration errors"""
    try:
        return Gauge(name, description, labelnames or [])
    except ValueError:
        return REGISTRY._names_to_collectors.get(name)


def _get_or_create_histogram(name: str, description: str, labelnames=None):
    """Get existing histogram or create new one to avoid duplicate registration errors"""
    try:
        return Histogram(name, description, labelnames or [])
    except ValueError:
        return REGISTRY._names_to_collectors.get(name)


class RegistryMetrics:
    """Métricas Prometheus para o Service Registry"""

    # Métricas de registro
    agents_registered_total = _get_or_create_counter(
        'agents_registered_total',
        'Total de agentes registrados',
        ['agent_type']
    )

    agents_deregistered_total = _get_or_create_counter(
        'agents_deregistered_total',
        'Total de agentes desregistrados',
        ['agent_type']
    )

    agents_active = _get_or_create_gauge(
        'agents_active',
        'Número de agentes ativos',
        ['agent_type', 'status']
    )

    # Métricas de heartbeat
    heartbeats_received_total = _get_or_create_counter(
        'heartbeats_received_total',
        'Total de heartbeats recebidos',
        ['agent_type', 'status']
    )

    heartbeat_latency_seconds = _get_or_create_histogram(
        'heartbeat_latency_seconds',
        'Latência de processamento de heartbeat'
    )

    # Métricas de discovery
    discovery_requests_total = _get_or_create_counter(
        'discovery_requests_total',
        'Total de requisições de discovery',
        ['agent_type']
    )

    discovery_duration_seconds = _get_or_create_histogram(
        'discovery_duration_seconds',
        'Duração de requisições de discovery'
    )

    matching_candidates_evaluated = _get_or_create_histogram(
        'matching_candidates_evaluated',
        'Número de candidatos avaliados no matching'
    )

    agents_matched = _get_or_create_histogram(
        'agents_matched',
        'Número de agentes retornados no matching'
    )

    # Métricas de health checks
    health_checks_total = _get_or_create_counter(
        'health_checks_total',
        'Total de health checks executados'
    )

    agents_marked_unhealthy_total = _get_or_create_counter(
        'agents_marked_unhealthy_total',
        'Total de agentes marcados como unhealthy',
        ['agent_type']
    )

    agents_removed_total = _get_or_create_counter(
        'agents_removed_total',
        'Total de agentes removidos por inatividade',
        ['agent_type']
    )

    # Métricas de etcd
    etcd_operations_total = _get_or_create_counter(
        'etcd_operations_total',
        'Total de operações no etcd',
        ['operation', 'status']
    )

    etcd_operation_duration_seconds = _get_or_create_histogram(
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
