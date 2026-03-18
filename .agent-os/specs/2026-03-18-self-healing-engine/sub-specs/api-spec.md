# API Specification

API REST do Self-Healing Engine para gestão de remediação e playbooks.

## Endpoints

### Health Endpoints

#### GET /health/live

**Purpose:** Liveness probe para Kubernetes
**Parameters:** Nenhum
**Response:** `200 OK` `{"status": "alive"}`
**Errors:** 503 se serviço indisponível

#### GET /health/ready

**Purpose:** Readiness probe para Kubernetes
**Parameters:** Nenhum
**Response:**
```json
{
  "status": "ready",
  "checks": {
    "kafka": "ok",
    "execution_ticket_service": "ok",
    "orchestrator": "ok",
    "opa": "ok"
  }
}
```
**Errors:** 503 se qualquer check falhar

---

### Remediation Endpoints

#### POST /api/v1/remediation/execute

**Purpose:** Executar playbook manualmente
**Parameters:**
```json
{
  "playbook": "ticket_timeout_recovery",
  "incident_id": "inc-123",
  "parameters": {
    "ticket_id": "ticket-456",
    "worker_id": "worker-1"
  },
  "dry_run": false
}
```
**Response:** `202 Accepted`
```json
{
  "execution_id": "exec-789",
  "status": "running",
  "estimated_duration_seconds": 120
}
```
**Errors:**
- 400: Playbook inválido
- 404: Playbook não encontrado
- 403: Ação bloqueada pelo OPA

#### GET /api/v1/remediation/execution/{execution_id}

**Purpose:** Obter status de execução
**Parameters:** execution_id (path)
**Response:**
```json
{
  "execution_id": "exec-789",
  "status": "completed",
  "started_at": "2026-03-18T10:00:00Z",
  "completed_at": "2026-03-18T10:01:30Z",
  "actions_executed": [
    {"type": "restart_pod", "status": "success"},
    {"type": "reallocate_ticket", "status": "success"}
  ],
  "result": "success"
}
```

#### GET /api/v1/remediation/playbooks

**Purpose:** Listar playbooks disponíveis
**Response:**
```json
{
  "playbooks": [
    {
      "name": "ticket_timeout_recovery",
      "description": "Recover from ticket execution timeout",
      "timeout_seconds": 120,
      "actions": ["check_worker_health", "restart_pod", "reallocate_ticket"]
    }
  ]
}
```

---

### Chaos Engineering Endpoints

#### POST /api/v1/chaos/experiment

**Purpose:** Executar experimento de chaos
**Parameters:**
```json
{
  "scenario": "pod_kill",
  "target": {
    "service": "worker-agents",
    "namespace": "neural-hive-orchestration"
  },
  "blast_radius": "single_pod",
  "duration_seconds": 60
}
```
**Response:** `202 Accepted`
**Errors:**
- 400: Blast radius excede limite
- 403: Não autorizado (require_opa_approval=true)

#### GET /api/v1/chaos/experiment/{experiment_id}

**Purpose:** Obter status de experimento
**Response:**
```json
{
  "experiment_id": "exp-123",
  "status": "running",
  "started_at": "2026-03-18T10:00:00Z",
  "scenario": "pod_kill",
  "affected_pods": ["worker-agents-5f7b8d9c-x2k4p"]
}
```

---

### Monitoring Endpoints

#### GET /metrics

**Purpose:** Prometheus metrics endpoint
**Response:** Text/plain com métricas Prometheus

#### GET /api/v1/monitoring/stats

**Purpose:** Estatísticas agregadas de remediação
**Response:**
```json
{
  "total_remediations": 1450,
  "success_rate": 0.92,
  "avg_mttr_seconds": 180,
  "top_playbooks": [
    {"name": "ticket_timeout_recovery", "executions": 520},
    {"name": "kafka_lag_recovery", "executions": 380}
  ]
}
```

---

### Configuração Endpoints

#### POST /api/v1/admin/playbooks/reload

**Purpose:** Recarregar playbooks do disco (hot reload)
**Response:** `200 OK` `{"reloaded": 8, "failed": 0}`

#### GET /api/v1/admin/config

**Purpose:** Obter configuração atual
**Response:**
```json
{
  "chaos_enabled": false,
  "opa_enabled": true,
  "opa_fail_open": true,
  "playbooks_dir": "/app/playbooks",
  "kafka_bootstrap_servers": "kafka:9092"
}
```

## Controllers

### RemediationController

- `execute_playbook()` - Valida parâmetros, submete ao PlaybookExecutor
- `get_execution_status()` - Busca status no repositório de execuções
- `list_playbooks()` - Escaneia diretório de playbooks
- Error handling: retorna 400 para parâmetros inválidos, 404 para não encontrado

### ChaosController

- `create_experiment()` - Valida blast radius, obtém aprovação OPA se necessário
- `get_experiment_status()` - Busca status no ChaosEngine
- Error handling: valida limites de blast_radius contra configuração

### MonitoringController

- `get_stats()` - Agrega métricas de execuções
- `get_prometheus_metrics()` - Formata métricas para Prometheus
- Cache: stats cache 60 segundos

## Rate Limiting

| Endpoint | Limite |
|----------|--------|
| POST /remediation/execute | 10/minuto |
| POST /chaos/experiment | 5/minuto |
| GET /* | 100/minuto |
