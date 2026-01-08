"""
Configurações para o módulo de Chaos Engineering.

Define constantes, limites e configurações padrão para experimentos de chaos.
"""

from typing import Dict, List, Set

# Namespaces protegidos que não podem ser alvos de chaos experiments
PROTECTED_NAMESPACES: Set[str] = {
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "calico-system",
    "istio-system",
}

# Serviços críticos que requerem aprovação especial em produção
CRITICAL_SERVICES: Set[str] = {
    "gateway-intencoes",
    "consensus-engine",
    "orchestrator-dynamic",
    "service-registry",
}

# Limites padrão para blast radius por ambiente
BLAST_RADIUS_LIMITS: Dict[str, int] = {
    "development": 10,
    "staging": 5,
    "production": 2,
}

# Horários de negócio (UTC) onde chaos experiments são bloqueados em produção
BUSINESS_HOURS = {
    "start_hour": 9,   # 9:00 UTC
    "end_hour": 18,    # 18:00 UTC
}

# Timeouts padrão por tipo de experimento (em segundos)
DEFAULT_TIMEOUTS: Dict[str, int] = {
    "network_latency": 120,
    "network_packet_loss": 120,
    "network_partition": 300,
    "pod_kill": 180,
    "container_kill": 180,
    "cpu_stress": 300,
    "memory_stress": 300,
    "disk_fill": 600,
    "http_error": 120,
    "http_delay": 120,
}

# Limites de parâmetros de injeção de falhas
INJECTION_LIMITS = {
    "max_latency_ms": 10000,           # 10 segundos máximo de latência
    "max_packet_loss_percent": 100,     # 100% de perda de pacotes
    "max_cpu_stress_cores": 8,          # 8 cores máximo para stress
    "max_cpu_load_percent": 100,        # 100% de carga de CPU
    "max_memory_stress_mb": 4096,       # 4GB máximo de memory stress
    "max_disk_fill_gb": 10,             # 10GB máximo de disk fill
    "max_experiment_duration_seconds": 3600,  # 1 hora máximo por experimento
    "min_experiment_duration_seconds": 10,    # 10 segundos mínimo
}

# Políticas OPA para validação de experimentos
OPA_POLICIES = {
    "experiment_validation": "neuralhive/chaos/experiment_validation",
    "blast_radius_limits": "neuralhive/chaos/blast_radius_limits",
    "environment_restrictions": "neuralhive/chaos/environment_restrictions",
}

# Tópicos Kafka para eventos de chaos
KAFKA_TOPICS = {
    "experiments": "chaos.experiments",
    "injections": "chaos.injections",
    "validations": "chaos.validations",
    "alerts": "chaos.alerts",
}

# Labels padrão para recursos criados pelo chaos engine
CHAOS_LABELS = {
    "app.kubernetes.io/managed-by": "chaos-engine",
    "app.kubernetes.io/part-of": "neural-hive-mind",
    "chaos.neuralhive.io/component": "fault-injection",
}

# Annotations para recursos de chaos
CHAOS_ANNOTATIONS = {
    "chaos.neuralhive.io/experiment-id": "",
    "chaos.neuralhive.io/injection-id": "",
    "chaos.neuralhive.io/created-at": "",
    "chaos.neuralhive.io/auto-cleanup": "true",
}

# Cenários pré-definidos disponíveis
AVAILABLE_SCENARIOS: List[str] = [
    "pod_failure_scenario",
    "network_partition_scenario",
    "resource_exhaustion_scenario",
    "cascading_failure_scenario",
    "slow_dependency_scenario",
]

# Playbooks mapeados por tipo de falha para validação
PLAYBOOK_FAULT_MAPPING: Dict[str, str] = {
    "pod_kill": "restart-pod",
    "container_kill": "restart-pod",
    "cpu_stress": "scale-up-deployment",
    "memory_stress": "scale-up-deployment",
    "network_partition": "check-network-connectivity",
}

# Métricas Prometheus para monitoramento
PROMETHEUS_METRICS = {
    "experiments_total": "chaos_experiments_total",
    "injection_duration_seconds": "chaos_injection_duration_seconds",
    "playbook_recovery_duration_seconds": "chaos_playbook_recovery_duration_seconds",
    "experiment_blast_radius": "chaos_experiment_blast_radius",
    "playbook_validation_failures_total": "chaos_playbook_validation_failures_total",
    "active_experiments": "chaos_active_experiments",
}

# Roles que podem executar experimentos de chaos
CHAOS_ALLOWED_ROLES: Set[str] = {
    "chaos-engineer",
    "sre-lead",
    "platform-admin",
}

# Configurações de retry para operações de chaos
RETRY_CONFIG = {
    "max_attempts": 3,
    "initial_delay_seconds": 1,
    "max_delay_seconds": 10,
    "exponential_base": 2,
}

# Configurações de circuit breaker para o chaos engine
CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 5,
    "reset_timeout_seconds": 60,
    "half_open_max_calls": 3,
}


def get_blast_radius_limit(environment: str) -> int:
    """Retorna o limite de blast radius para o ambiente especificado."""
    return BLAST_RADIUS_LIMITS.get(environment, BLAST_RADIUS_LIMITS["staging"])


def is_protected_namespace(namespace: str) -> bool:
    """Verifica se o namespace é protegido contra chaos experiments."""
    return namespace in PROTECTED_NAMESPACES


def is_critical_service(service_name: str) -> bool:
    """Verifica se o serviço é considerado crítico."""
    return service_name in CRITICAL_SERVICES


def is_business_hours() -> bool:
    """Verifica se o momento atual está dentro do horário de negócio (UTC)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return BUSINESS_HOURS["start_hour"] <= now.hour < BUSINESS_HOURS["end_hour"]


def get_default_timeout(fault_type: str) -> int:
    """Retorna o timeout padrão para o tipo de falha especificado."""
    return DEFAULT_TIMEOUTS.get(fault_type, 300)
