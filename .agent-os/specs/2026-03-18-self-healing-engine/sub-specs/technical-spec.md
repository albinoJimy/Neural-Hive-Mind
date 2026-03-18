# Technical Specification

Especificação técnica para o Self-Healing Engine do Neural Hive-Mind.

## Requisitos Técnicos

### 1. Testes Automatizados

**Unitários (pytest):**
- Corrigir imports: adicionar `conftest.py` com `sys.path.insert(0, os.path.abspath('.'))`
- Mock de clientes externos (ETS, Orchestrator, OPA)
- Testes de PlaybookExecutor, RemediationManager, ChaosEngine
- Cobertura >80%

**Integração (Docker Compose):**
- Testar com Kafka, MongoDB, Redis reais
- Validar consumidores de incidentes
- Testar execução de playbooks

**E2E (Kubernetes kind/miniKube):**
- Deploy completo em cluster local
- Injecção de falhas → verificação de recuperação
- Testar todos os playbooks

### 2. Kubernetes Deployment

**Manifestos (kubernetes/):**

| Arquivo | Descrição |
|---------|-----------|
| `deployment.yaml` | Deployment com 3 réplicas, probes |
| `service.yaml` | Service (ClusterIP) porta 8080 |
| `configmap.yaml` | Configurações não-sensíveis |
| `secret.yaml` | Segredos (OPA tokens, mTLS certs) |
| `hpa.yaml` | HorizontalPodAutoscaler (2-10 pods) |
| `pdb.yaml` | PodDisruptionBudget (min 2) |
| `serviceaccount.yaml` | RBAC para Kubernetes API access |
| `networkpolicy.yaml` | Restrições de rede |

**Requisitos:**
- `livenessProbe`: `/health/live` threshold=3
- `readinessProbe`: `/health/ready` verifica Kafka, ETS, Orchestrator
- Resources: requests 200m/512Mi, limits 1CPU/2Gi

### 3. Helm Chart

**Estrutura:**

```
helm-chart/
├── Chart.yaml (version: 1.0.0)
├── values.yaml (configurável por ambiente)
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── hpa.yaml
│   ├── pdb.yaml
│   ├── serviceaccount.yaml
│   └── networkpolicy.yaml
└── tests/
    └── test.yaml (helm test)
```

**Values.yaml:**
- `replicaCount: 3`
- `image.repository`, `image.tag`
- `resources` (configurável)
- `autoscaling.enabled` (default: true)
- `chaos.enabled` (default: false)
- `opa.enabled`, `opa.failOpen`
- `playbooks.configMap` (enable custom playbooks)

### 4. Detecção Automática

**Health Monitor Service:**

```python
class HealthMonitor:
    async def check_service_health(service_name: str) -> HealthStatus
    async def check_kafka_consumer_lag(consumer_group: str) -> LagStatus
    async def check_database_connection(connection_string: str) -> ConnectionStatus
    async def detect_deadlocks(workflow_id: str) -> DeadlockStatus
    async def detect_memory_leak(pod_name: str) -> MemoryStatus
```

**Circuit Breaker Pattern:**
- 3 falhas consecutivas → OPEN
- 60 segundos → HALF_OPEN
- 1 sucesso → CLOSED

**Triggers:**
- Pod CrashLoopBackOff → restart_pod playbook
- Kafka lag > threshold → kafka_lag_recovery playbook
- DB connection timeout → db_connection_recovery playbook
- Workflow timeout > 30min → deadlock_recovery playbook
- Memory usage > 90% → memory_leak_recovery playbook

### 5. Playbooks Adicionais

**database_connection_recovery.yaml:**
- Detect: MongoDB/PostgreSQL connection errors
- Actions: restart_pods → scale_up → restart_connection_pool

**memory_leak_detection.yaml:**
- Detect: Pod memory > 90% limit por 5min
- Actions: graceful_restart → increase_memory_limit → alert

**deadlock_recovery.yaml:**
- Detect: Workflow sem progresso por 30min
- Actions: pause_workflow → analyze_tickets → trigger_replanning

### 6. Métricas e Dashboard

**Prometheus Metrics (novas):**

| Métrica | Tipo | Labels |
|---------|------|--------|
| `self_healing_detection_total` | Counter | service, issue_type |
| `self_healing_remediation_success` | Gauge | playbook |
| `self_healing_mttr_seconds` | Histogram | severity |
| `self_healing_circuit_breaker_state` | Gauge | service |

**Grafana Dashboard:**
- Panel: Detecções por hora (gráfico)
- Panel: Taxa de sucesso de remediação (gauge)
- Panel: MTTR por severidade (heatmap)
- Panel: Circuit breaker states (stat)
- Panel: Playbooks mais executados (bar)

## External Dependencies

| Biblioteca | Versão | Propósito |
|------------|--------|-----------|
| pytest | 8.x | Testes |
| pytest-asyncio | 0.23.x | Testes async |
| pytest-mock | 3.x | Mocks |
| kind | 0.20.x | K8s local E2E |
| helm | 3.x | Chart deployment |

## Performance Criteria

| Métrica | Target |
|---------|--------|
| Detecção de incidente | < 30 segundos |
| Execução de playbook | < 2 minutos |
| MTTR para falhas simples | < 5 minutos |
| Overhead de monitorização | < 5% CPU |
| Test pipeline duration | < 10 minutos |
