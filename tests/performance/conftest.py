"""
Fixtures pytest para testes de performance do Fluxo C.

Fornece clientes, configuracoes e helpers para testes de carga.
"""

import os
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

from tests.performance.prometheus_client import PrometheusClient
from tests.performance.kubernetes_client import KubernetesClient
from tests.performance.bottleneck_analyzer import BottleneckAnalyzer, BottleneckThresholds
from tests.performance.slo_validator import SLOValidator, LoadTestMetrics


# Configuracao do ambiente
DEFAULT_CONFIG = {
    'orchestrator_url': os.getenv('ORCHESTRATOR_URL', 'http://orchestrator-dynamic:8000'),
    'prometheus_url': os.getenv('PROMETHEUS_URL', 'http://prometheus:9090'),
    'temporal_host': os.getenv('TEMPORAL_HOST', 'temporal-frontend:7233'),
    'kafka_bootstrap': os.getenv('KAFKA_BOOTSTRAP', 'neural-hive-kafka-bootstrap:9092'),
    'mongodb_uri': os.getenv('MONGODB_URI', 'mongodb://mongodb:27017'),
    'namespace': os.getenv('K8S_NAMESPACE', 'neural-hive-orchestration'),
}


@pytest.fixture(scope='session')
def event_loop():
    """Cria event loop para testes async."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='session')
def load_test_config() -> Dict[str, Any]:
    """
    Configuracao do teste de carga.

    Pode ser sobrescrita via variaveis de ambiente.
    """
    return {
        # Carga
        'workflows_count': int(os.getenv('WORKFLOWS_COUNT', 100)),
        'concurrent_workflows': int(os.getenv('CONCURRENT_WORKFLOWS', 50)),
        'ramp_up_seconds': int(os.getenv('RAMP_UP_SECONDS', 300)),
        'test_duration_seconds': int(os.getenv('TEST_DURATION_SECONDS', 3600)),

        # SLOs
        'slo_latency_p95_seconds': 14400,  # 4h
        'slo_latency_p99_seconds': 21600,  # 6h
        'slo_success_rate': 0.99,
        'slo_throughput_tickets_per_second': 10.0,

        # Thresholds para bottlenecks
        'cpu_warning_percent': 70.0,
        'cpu_critical_percent': 85.0,
        'memory_warning_percent': 75.0,
        'memory_critical_percent': 85.0,
        'kafka_lag_warning': 500,
        'kafka_lag_critical': 1000,

        # URLs e endpoints
        **DEFAULT_CONFIG,
    }


@pytest.fixture
async def prometheus_client(load_test_config) -> PrometheusClient:
    """Cliente Prometheus configurado."""
    client = PrometheusClient(
        url=load_test_config['prometheus_url'],
        timeout_seconds=10.0,
    )
    yield client
    await client.close()


@pytest.fixture
async def kubernetes_client(load_test_config) -> KubernetesClient:
    """Cliente Kubernetes configurado."""
    in_cluster = os.getenv('KUBERNETES_SERVICE_HOST') is not None
    client = KubernetesClient(
        namespace=load_test_config['namespace'],
        in_cluster=in_cluster,
    )
    yield client
    await client.close()


@pytest.fixture
def bottleneck_thresholds(load_test_config) -> BottleneckThresholds:
    """Thresholds configurados para analise de bottlenecks."""
    return BottleneckThresholds(
        cpu_warning_percent=load_test_config['cpu_warning_percent'],
        cpu_critical_percent=load_test_config['cpu_critical_percent'],
        memory_warning_percent=load_test_config['memory_warning_percent'],
        memory_critical_percent=load_test_config['memory_critical_percent'],
        kafka_lag_warning=load_test_config['kafka_lag_warning'],
        kafka_lag_critical=load_test_config['kafka_lag_critical'],
    )


@pytest.fixture
def bottleneck_analyzer(bottleneck_thresholds) -> BottleneckAnalyzer:
    """Analisador de bottlenecks configurado."""
    return BottleneckAnalyzer(thresholds=bottleneck_thresholds)


@pytest.fixture
def slo_validator() -> SLOValidator:
    """Validador de SLOs padrao."""
    return SLOValidator()


@pytest.fixture
def empty_metrics() -> LoadTestMetrics:
    """Metricas vazias para testes."""
    return LoadTestMetrics()


# Fixtures para dados de teste

@pytest.fixture
def sample_cognitive_plan() -> Dict[str, Any]:
    """Plano cognitivo de exemplo para testes."""
    return {
        'plan_id': f'plan-load-test-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
        'intent_id': 'intent-load-test',
        'correlation_id': f'corr-{datetime.utcnow().timestamp()}',
        'risk_band': 'medium',
        'tasks': [
            {
                'task_id': 'task-1',
                'task_type': 'BUILD',
                'description': 'Build application',
                'dependencies': [],
                'estimated_duration_ms': 60000,
                'required_capabilities': ['python', 'build'],
            },
            {
                'task_id': 'task-2',
                'task_type': 'TEST',
                'description': 'Run tests',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 120000,
                'required_capabilities': ['python', 'testing'],
            },
            {
                'task_id': 'task-3',
                'task_type': 'DEPLOY',
                'description': 'Deploy application',
                'dependencies': ['task-2'],
                'estimated_duration_ms': 180000,
                'required_capabilities': ['kubernetes', 'deployment'],
            },
        ],
        'qos': {
            'delivery_mode': 'AT_LEAST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'PERSISTENT',
        },
        'sla': {
            'deadline': int((datetime.utcnow().timestamp() + 14400) * 1000),  # +4h
            'timeout_ms': 14400000,  # 4h
            'max_retries': 3,
        },
        'namespace': 'default',
        'security_level': 'standard',
    }


@pytest.fixture
def sample_consolidated_decision(sample_cognitive_plan) -> Dict[str, Any]:
    """Decisao consolidada de exemplo."""
    return {
        'plan_id': sample_cognitive_plan['plan_id'],
        'intent_id': sample_cognitive_plan['intent_id'],
        'correlation_id': sample_cognitive_plan['correlation_id'],
        'final_decision': 'approve',
        'consensus_type': 'UNANIMOUS',
        'cognitive_plan': sample_cognitive_plan,
        'created_at': int(datetime.utcnow().timestamp() * 1000),
    }


# Funcoes utilitarias


def generate_cognitive_plans(count: int, base_plan: Dict[str, Any]) -> list:
    """
    Gera multiplos planos cognitivos para testes de carga.

    Args:
        count: Numero de planos a gerar
        base_plan: Plano base para usar como template

    Returns:
        Lista de planos cognitivos
    """
    import copy
    import uuid

    plans = []
    risk_bands = ['low', 'medium', 'high', 'critical']
    risk_distribution = [0.2, 0.3, 0.3, 0.2]  # 20% low, 30% medium, 30% high, 20% critical

    for i in range(count):
        plan = copy.deepcopy(base_plan)
        plan['plan_id'] = f'plan-{uuid.uuid4().hex[:8]}'
        plan['intent_id'] = f'intent-{uuid.uuid4().hex[:8]}'
        plan['correlation_id'] = f'corr-{uuid.uuid4().hex[:8]}'

        # Distribuir risk_band
        cumulative = 0
        threshold = (i % 100) / 100
        for j, (risk, prob) in enumerate(zip(risk_bands, risk_distribution)):
            cumulative += prob
            if threshold < cumulative:
                plan['risk_band'] = risk
                break

        # Variar numero de tasks (3-5)
        num_tasks = 3 + (i % 3)
        if num_tasks != len(plan['tasks']):
            if num_tasks > len(plan['tasks']):
                # Adicionar tasks
                for t in range(len(plan['tasks']), num_tasks):
                    plan['tasks'].append({
                        'task_id': f'task-{t+1}',
                        'task_type': ['BUILD', 'TEST', 'DEPLOY', 'VALIDATE'][t % 4],
                        'description': f'Task {t+1}',
                        'dependencies': [f'task-{t}'] if t > 0 else [],
                        'estimated_duration_ms': 60000 * (t + 1),
                        'required_capabilities': ['python', 'automation'],
                    })
            else:
                # Remover tasks
                plan['tasks'] = plan['tasks'][:num_tasks]

        plans.append(plan)

    return plans


def generate_consolidated_decisions(plans: list) -> list:
    """
    Gera decisoes consolidadas para uma lista de planos.

    Args:
        plans: Lista de planos cognitivos

    Returns:
        Lista de decisoes consolidadas
    """
    decisions = []

    for plan in plans:
        decisions.append({
            'plan_id': plan['plan_id'],
            'intent_id': plan['intent_id'],
            'correlation_id': plan['correlation_id'],
            'final_decision': 'approve',
            'consensus_type': 'UNANIMOUS',
            'cognitive_plan': plan,
            'created_at': int(datetime.utcnow().timestamp() * 1000),
        })

    return decisions
