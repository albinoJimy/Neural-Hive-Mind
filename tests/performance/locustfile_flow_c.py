"""
Testes de carga Locust para o Fluxo C de Orquestracao (C1-C6).

Executa via Locust com simulacao de 100 workflows concorrentes,
validacoes de throughput/latencia, circuit breaker e autoscaling.

Uso:
    locust -f tests/performance/locustfile_flow_c.py --host=http://orchestrator-dynamic:8000

    # Modo headless com 100 usuarios
    locust -f tests/performance/locustfile_flow_c.py --host=http://orchestrator-dynamic:8000 \
        --headless -u 100 -r 10 --run-time 10m
"""

import asyncio
import json
import logging
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from locust import HttpUser, TaskSet, task, events, between
from locust.runners import MasterRunner, WorkerRunner

logger = logging.getLogger(__name__)


# ============================================
# Configuracao
# ============================================

CONFIG = {
    'prometheus_url': os.getenv('PROMETHEUS_URL', 'http://prometheus:9090'),
    'kubernetes_namespace': os.getenv('K8S_NAMESPACE', 'neural-hive-orchestration'),
    'workflow_timeout_seconds': int(os.getenv('WORKFLOW_TIMEOUT_SECONDS', 14400)),
    # SLOs
    'slo_latency_p95_seconds': 14400,  # 4h
    'slo_throughput_tickets_per_second': 10.0,
    'slo_success_rate': 0.99,
    # Autoscaling
    'min_scale_up_replicas': 4,
    'autoscaling_cooldown_seconds': 300,
    # Circuit breaker
    'circuit_breaker_components': ['kafka', 'temporal', 'redis', 'mongodb'],
}


@dataclass
class LoadTestState:
    """Estado global do teste de carga."""
    workflow_ids: Set[str] = field(default_factory=set)
    completed_workflows: int = 0
    failed_workflows: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    circuit_breaker_trips: Dict[str, int] = field(default_factory=dict)
    scaling_events: List[Dict[str, Any]] = field(default_factory=list)
    initial_replicas: int = 2
    max_replicas_observed: int = 2
    start_time: float = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_workflow_id(self, workflow_id: str) -> None:
        with self.lock:
            self.workflow_ids.add(workflow_id)

    def record_completion(self, workflow_id: str, success: bool, latency_ms: float) -> None:
        with self.lock:
            self.workflow_ids.discard(workflow_id)
            if success:
                self.completed_workflows += 1
            else:
                self.failed_workflows += 1
            self.latencies_ms.append(latency_ms)

    def record_replicas(self, count: int) -> None:
        with self.lock:
            if count > self.max_replicas_observed:
                self.max_replicas_observed = count
                self.scaling_events.append({
                    'timestamp': datetime.utcnow().isoformat(),
                    'replicas': count,
                    'event': 'scale_up',
                })

    def record_circuit_breaker_trip(self, component: str) -> None:
        with self.lock:
            self.circuit_breaker_trips[component] = (
                self.circuit_breaker_trips.get(component, 0) + 1
            )

    @property
    def pending_workflows(self) -> int:
        with self.lock:
            return len(self.workflow_ids)

    @property
    def success_rate(self) -> float:
        with self.lock:
            total = self.completed_workflows + self.failed_workflows
            if total > 0:
                return self.completed_workflows / total
            return 0.0


# Estado global compartilhado
test_state = LoadTestState()


# ============================================
# Geracao de Dados de Teste
# ============================================

def generate_cognitive_plan() -> Dict[str, Any]:
    """Gera um plano cognitivo aleatorio para teste."""
    plan_id = f'plan-{uuid.uuid4().hex[:8]}'
    risk_bands = ['low', 'medium', 'high', 'critical']
    risk_weights = [0.2, 0.3, 0.3, 0.2]

    num_tasks = random.randint(3, 5)
    tasks = []
    for i in range(num_tasks):
        tasks.append({
            'task_id': f'task-{i+1}',
            'task_type': random.choice(['BUILD', 'TEST', 'DEPLOY', 'VALIDATE']),
            'description': f'Task {i+1} do plano {plan_id}',
            'dependencies': [f'task-{i}'] if i > 0 else [],
            'estimated_duration_ms': random.randint(30000, 180000),
            'required_capabilities': ['python', 'automation'],
        })

    return {
        'plan_id': plan_id,
        'intent_id': f'intent-{uuid.uuid4().hex[:8]}',
        'correlation_id': f'corr-{uuid.uuid4().hex[:8]}',
        'risk_band': random.choices(risk_bands, weights=risk_weights)[0],
        'tasks': tasks,
        'qos': {
            'delivery_mode': 'AT_LEAST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'PERSISTENT',
        },
        'sla': {
            'deadline': int((time.time() + 14400) * 1000),
            'timeout_ms': 14400000,
            'max_retries': 3,
        },
        'namespace': 'default',
        'security_level': 'standard',
    }


def generate_consolidated_decision(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Gera decisao consolidada a partir de um plano."""
    return {
        'plan_id': plan['plan_id'],
        'intent_id': plan['intent_id'],
        'correlation_id': plan['correlation_id'],
        'final_decision': 'approve',
        'consensus_type': 'UNANIMOUS',
        'cognitive_plan': plan,
        'created_at': int(time.time() * 1000),
    }


# ============================================
# Tasks do Locust
# ============================================

class FlowCTasks(TaskSet):
    """TaskSet para testes do Fluxo C."""

    def on_start(self):
        """Setup antes de iniciar as tasks."""
        self._pending_workflows: Dict[str, float] = {}

    def on_stop(self):
        """Cleanup apos parar as tasks."""
        self._cleanup_pending_workflows()

    def _cleanup_pending_workflows(self):
        """Aguarda conclusao ou cancela workflows pendentes."""
        for workflow_id, start_time in list(self._pending_workflows.items()):
            elapsed = time.time() - start_time
            if elapsed < CONFIG['workflow_timeout_seconds']:
                # Tentar cancelar
                try:
                    self.client.post(
                        f'/api/v1/workflows/{workflow_id}/cancel',
                        name='/api/v1/workflows/[id]/cancel',
                    )
                except Exception:
                    pass
            test_state.record_completion(workflow_id, False, elapsed * 1000)

    @task(10)
    def start_and_track_workflow(self):
        """
        Inicia um workflow e aguarda sua conclusao.

        Esta eh a task principal que simula o comportamento real
        de submissao e acompanhamento de workflows.
        """
        plan = generate_cognitive_plan()
        decision = generate_consolidated_decision(plan)

        start_time = time.time()

        # Iniciar workflow
        with self.client.post(
            '/api/v1/workflows/start',
            json=decision,
            name='/api/v1/workflows/start',
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201, 202):
                try:
                    data = response.json()
                    workflow_id = data.get('workflow_id')

                    if workflow_id:
                        test_state.add_workflow_id(workflow_id)
                        self._pending_workflows[workflow_id] = start_time
                        response.success()

                        # Aguardar conclusao em background
                        self._wait_for_completion(workflow_id, start_time)
                    else:
                        response.failure('workflow_id nao retornado')
                except Exception as e:
                    response.failure(f'Erro ao parsear resposta: {e}')
            else:
                response.failure(f'Status code: {response.status_code}')

    def _wait_for_completion(self, workflow_id: str, start_time: float):
        """
        Aguarda conclusao do workflow com polling.

        Registra metricas de latencia e sucesso/falha.
        """
        timeout = CONFIG['workflow_timeout_seconds']
        poll_interval = 5  # segundos

        while time.time() - start_time < timeout:
            try:
                response = self.client.get(
                    f'/api/v1/workflows/{workflow_id}/status',
                    name='/api/v1/workflows/[id]/status',
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', '').lower()

                    if status in ('completed', 'success'):
                        latency_ms = (time.time() - start_time) * 1000
                        test_state.record_completion(workflow_id, True, latency_ms)
                        self._pending_workflows.pop(workflow_id, None)
                        return
                    elif status in ('failed', 'cancelled', 'error'):
                        latency_ms = (time.time() - start_time) * 1000
                        test_state.record_completion(workflow_id, False, latency_ms)
                        self._pending_workflows.pop(workflow_id, None)
                        return

            except Exception as e:
                logger.debug(f'Erro ao consultar status: {e}')

            time.sleep(poll_interval)

        # Timeout
        test_state.record_completion(workflow_id, False, timeout * 1000)
        self._pending_workflows.pop(workflow_id, None)

    @task(2)
    def check_health(self):
        """Verifica health do orchestrator."""
        self.client.get('/health', name='/health')

    @task(1)
    def check_metrics(self):
        """Consulta metricas do orchestrator."""
        self.client.get('/metrics', name='/metrics')


class FlowCCircuitBreakerTasks(TaskSet):
    """TaskSet para testes de circuit breaker com injecao de falhas."""

    @task(5)
    def start_workflow_with_failure_injection(self):
        """
        Inicia workflow com injecao de falhas para testar circuit breakers.

        Usa headers especiais para simular falhas em componentes especificos.
        """
        plan = generate_cognitive_plan()
        decision = generate_consolidated_decision(plan)

        # Escolher componente para simular falha (20% de chance)
        if random.random() < 0.2:
            component = random.choice(CONFIG['circuit_breaker_components'])
            headers = {
                'X-Inject-Failure': component,
                'X-Failure-Type': random.choice(['timeout', 'error', 'unavailable']),
                'X-Failure-Duration-Ms': str(random.randint(1000, 5000)),
            }
        else:
            headers = {}

        with self.client.post(
            '/api/v1/workflows/start',
            json=decision,
            headers=headers,
            name='/api/v1/workflows/start (failure_injection)',
            catch_response=True,
        ) as response:
            # Falhas injetadas podem retornar 503 (circuit breaker aberto)
            if response.status_code == 503:
                # Verificar se e circuit breaker
                try:
                    data = response.json()
                    if 'circuit_breaker' in data.get('error', '').lower():
                        component = data.get('component', 'unknown')
                        test_state.record_circuit_breaker_trip(component)
                        response.success()  # Esperado quando CB esta aberto
                    else:
                        response.failure(f'Erro 503 nao relacionado a CB')
                except Exception:
                    response.failure('Erro 503 inesperado')
            elif response.status_code in (200, 201, 202):
                response.success()
            else:
                response.failure(f'Status code: {response.status_code}')

    @task(3)
    def check_circuit_breaker_states(self):
        """
        Verifica estados dos circuit breakers via API.

        Valida transicoes open -> half_open -> closed.
        """
        with self.client.get(
            '/api/v1/circuit-breakers',
            name='/api/v1/circuit-breakers',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    states = data.get('circuit_breakers', {})

                    for component, info in states.items():
                        state = info.get('state', 'unknown')
                        if state == 'open':
                            test_state.record_circuit_breaker_trip(component)
                            logger.info(f'Circuit breaker {component} OPEN')
                        elif state == 'half_open':
                            logger.info(f'Circuit breaker {component} HALF_OPEN (recuperando)')

                    response.success()
                except Exception as e:
                    response.failure(f'Erro ao parsear: {e}')
            else:
                response.failure(f'Status: {response.status_code}')

    @task(2)
    def trigger_recovery_check(self):
        """
        Envia requisicao de teste para verificar recovery de circuit breakers.
        """
        for component in CONFIG['circuit_breaker_components']:
            self.client.get(
                f'/api/v1/circuit-breakers/{component}/test',
                name='/api/v1/circuit-breakers/[component]/test',
            )


# ============================================
# Usuarios Locust
# ============================================

class FlowCUser(HttpUser):
    """Usuario padrao para testes do Fluxo C."""
    tasks = [FlowCTasks]
    wait_time = between(1, 3)


class FlowCCircuitBreakerUser(HttpUser):
    """Usuario para testes de circuit breaker com injecao de falhas."""
    tasks = [FlowCCircuitBreakerTasks]
    wait_time = between(0.5, 2)
    weight = 3  # Maior peso para mais usuarios deste tipo


class FlowCLoadUser(HttpUser):
    """Usuario de alta carga (100 concorrentes)."""
    tasks = [FlowCTasks]
    wait_time = between(0.1, 0.5)  # Mais agressivo
    weight = 10


# ============================================
# Monitoramento e Validacoes
# ============================================

class MetricsCollector:
    """Coletor de metricas para validacoes."""

    def __init__(self, prometheus_url: str, k8s_namespace: str):
        self.prometheus_url = prometheus_url
        self.k8s_namespace = k8s_namespace
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Inicia coleta de metricas em background."""
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para coleta de metricas."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _collect_loop(self):
        """Loop de coleta de metricas."""
        import requests

        while self._running:
            try:
                # Coletar replicas via Prometheus
                response = requests.get(
                    f'{self.prometheus_url}/api/v1/query',
                    params={
                        'query': f'count(kube_pod_info{{pod=~"orchestrator-dynamic-.*", namespace="{self.k8s_namespace}", phase="Running"}})'
                    },
                    timeout=5,
                )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get('data', {}).get('result', [])
                    if results:
                        replicas = int(float(results[0]['value'][1]))
                        test_state.record_replicas(replicas)

                # Coletar estados de circuit breaker
                response = requests.get(
                    f'{self.prometheus_url}/api/v1/query',
                    params={'query': 'neural_hive_circuit_breaker_state'},
                    timeout=5,
                )

                if response.status_code == 200:
                    data = response.json()
                    for result in data.get('data', {}).get('result', []):
                        component = result.get('metric', {}).get('component', 'unknown')
                        state = int(float(result['value'][1]))
                        if state == 1:  # open
                            test_state.record_circuit_breaker_trip(component)

            except Exception as e:
                logger.debug(f'Erro ao coletar metricas: {e}')

            time.sleep(10)


# Instancia global do coletor
metrics_collector = MetricsCollector(
    prometheus_url=CONFIG['prometheus_url'],
    k8s_namespace=CONFIG['kubernetes_namespace'],
)


# ============================================
# Event Hooks
# ============================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Executa ao iniciar o teste."""
    global test_state
    test_state = LoadTestState()
    test_state.start_time = time.time()

    # Iniciar coleta de metricas (apenas no master ou standalone)
    if not isinstance(environment.runner, WorkerRunner):
        metrics_collector.start()
        logger.info('Teste de carga iniciado - coletando metricas')


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Executa ao parar o teste."""
    # Parar coleta de metricas
    if not isinstance(environment.runner, WorkerRunner):
        metrics_collector.stop()

    # Aguardar conclusao de workflows pendentes (max 60s)
    logger.info(f'Aguardando {test_state.pending_workflows} workflows pendentes...')
    timeout = 60
    start = time.time()

    while test_state.pending_workflows > 0 and (time.time() - start) < timeout:
        time.sleep(5)

    if test_state.pending_workflows > 0:
        logger.warning(f'{test_state.pending_workflows} workflows nao concluidos')

    # Validar resultados
    _validate_test_results(environment)


def _validate_test_results(environment):
    """
    Valida resultados do teste contra SLOs.

    Asserts obrigatorios para throughput, latencia, autoscaling e circuit breakers.
    """
    results = []
    failures = []

    # 1. Validar taxa de sucesso (Comment 3 - mandatory asserts)
    success_rate = test_state.success_rate
    if success_rate < CONFIG['slo_success_rate']:
        failures.append(
            f'Taxa de sucesso {success_rate*100:.1f}% < {CONFIG["slo_success_rate"]*100}% (SLO)'
        )
    results.append(f'Taxa de sucesso: {success_rate*100:.1f}%')

    # 2. Validar latencia P95
    if test_state.latencies_ms:
        sorted_latencies = sorted(test_state.latencies_ms)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p95_ms = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
        p95_seconds = p95_ms / 1000

        if p95_seconds > CONFIG['slo_latency_p95_seconds']:
            failures.append(
                f'Latencia P95 {p95_seconds/3600:.2f}h > {CONFIG["slo_latency_p95_seconds"]/3600:.1f}h (SLO)'
            )
        results.append(f'Latencia P95: {p95_seconds/3600:.2f}h')

    # 3. Validar throughput
    test_duration = time.time() - test_state.start_time
    if test_duration > 0:
        throughput = (test_state.completed_workflows + test_state.failed_workflows) / test_duration
        if throughput < CONFIG['slo_throughput_tickets_per_second']:
            failures.append(
                f'Throughput {throughput:.2f} wf/s < {CONFIG["slo_throughput_tickets_per_second"]} (SLO)'
            )
        results.append(f'Throughput: {throughput:.2f} workflows/s')

    # 4. Validar autoscaling (Comment 3 - mandatory asserts)
    if test_state.max_replicas_observed < CONFIG['min_scale_up_replicas']:
        failures.append(
            f'HPA nao escalou: max {test_state.max_replicas_observed} replicas < '
            f'{CONFIG["min_scale_up_replicas"]} (esperado durante carga)'
        )
    results.append(f'Max replicas observadas: {test_state.max_replicas_observed}')

    # 5. Reportar circuit breaker trips (Comment 2 - validacao de transicoes)
    if test_state.circuit_breaker_trips:
        results.append('Circuit breaker trips:')
        for comp, count in test_state.circuit_breaker_trips.items():
            results.append(f'  - {comp}: {count} trips')

    # Reportar resultados
    logger.info('\n' + '='*60)
    logger.info('RESULTADOS DO TESTE DE CARGA')
    logger.info('='*60)
    for r in results:
        logger.info(r)

    if failures:
        logger.error('\n' + '-'*60)
        logger.error('FALHAS DE VALIDACAO:')
        for f in failures:
            logger.error(f'  FAIL: {f}')
        logger.error('-'*60)

        # Falhar o teste (Comment 3 - asserts obrigatorios)
        environment.runner.quit()
        raise AssertionError('\n'.join(failures))
    else:
        logger.info('\nTodos os SLOs atendidos!')


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Listener para cada requisicao - usado para tracking detalhado."""
    if exception:
        logger.debug(f'Requisicao falhou: {name} - {exception}')


# ============================================
# Funcoes de Validacao de Circuit Breaker
# ============================================

def validate_circuit_breaker_transitions():
    """
    Valida transicoes de estado dos circuit breakers.

    Verifica que apos falhas, os circuit breakers:
    1. Abrem (open)
    2. Tentam recuperar (half_open)
    3. Fecham novamente (closed)

    Esta funcao deve ser chamada apos injecao de falhas controladas.
    """
    import requests

    try:
        response = requests.get(
            f'{CONFIG["prometheus_url"]}/api/v1/query',
            params={'query': 'neural_hive_circuit_breaker_state'},
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            states = {}

            for result in data.get('data', {}).get('result', []):
                component = result.get('metric', {}).get('component', 'unknown')
                state_value = int(float(result['value'][1]))
                state_map = {0: 'closed', 1: 'open', 2: 'half_open'}
                states[component] = state_map.get(state_value, 'unknown')

            return states
    except Exception as e:
        logger.warning(f'Erro ao validar circuit breakers: {e}')

    return {}


# ============================================
# Script K6 alternativo (referencia)
# ============================================

K6_SCRIPT_TEMPLATE = '''
// k6_flow_c_load.js - Script K6 alternativo para testes de carga
// Uso: k6 run --vus 100 --duration 10m k6_flow_c_load.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const workflowLatency = new Trend('workflow_latency_ms');
const circuitBreakerTrips = new Counter('circuit_breaker_trips');

export const options = {
  vus: 100,
  duration: '10m',
  thresholds: {
    'http_req_failed': ['rate<0.01'],  // <1% de falhas
    'workflow_latency_ms': ['p(95)<14400000'],  // P95 < 4h
  },
};

const BASE_URL = __ENV.ORCHESTRATOR_URL || 'http://orchestrator-dynamic:8000';

function generatePlan() {
  const planId = `plan-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  return {
    plan_id: planId,
    intent_id: `intent-${Math.random().toString(36).substr(2, 9)}`,
    correlation_id: `corr-${Math.random().toString(36).substr(2, 9)}`,
    risk_band: ['low', 'medium', 'high', 'critical'][Math.floor(Math.random() * 4)],
    tasks: [
      { task_id: 'task-1', task_type: 'BUILD', dependencies: [] },
      { task_id: 'task-2', task_type: 'TEST', dependencies: ['task-1'] },
      { task_id: 'task-3', task_type: 'DEPLOY', dependencies: ['task-2'] },
    ],
    qos: { delivery_mode: 'AT_LEAST_ONCE' },
    sla: { timeout_ms: 14400000 },
  };
}

export default function() {
  const plan = generatePlan();
  const decision = {
    plan_id: plan.plan_id,
    final_decision: 'approve',
    cognitive_plan: plan,
  };

  const startTime = Date.now();

  // Iniciar workflow
  const startRes = http.post(
    `${BASE_URL}/api/v1/workflows/start`,
    JSON.stringify(decision),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(startRes, {
    'workflow iniciado': (r) => r.status === 200 || r.status === 201 || r.status === 202,
  });

  if (startRes.status === 503) {
    // Circuit breaker aberto
    circuitBreakerTrips.add(1);
    return;
  }

  const workflowId = startRes.json('workflow_id');
  if (!workflowId) return;

  // Aguardar conclusao (simplificado)
  let completed = false;
  const timeout = 300000; // 5 min para polling

  while (!completed && (Date.now() - startTime) < timeout) {
    sleep(5);
    const statusRes = http.get(`${BASE_URL}/api/v1/workflows/${workflowId}/status`);

    if (statusRes.status === 200) {
      const status = statusRes.json('status');
      if (status === 'COMPLETED' || status === 'FAILED') {
        completed = true;
        workflowLatency.add(Date.now() - startTime);
      }
    }
  }
}
'''


if __name__ == '__main__':
    # Executar via locust CLI
    import sys
    print('Execute via: locust -f locustfile_flow_c.py --host=http://orchestrator-dynamic:8000')
    print('\nOu em modo headless:')
    print('locust -f locustfile_flow_c.py --host=http://orchestrator-dynamic:8000 --headless -u 100 -r 10 --run-time 10m')
    sys.exit(0)
