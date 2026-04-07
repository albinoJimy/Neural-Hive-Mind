# Políticas de Segurança - Self-Healing Engine

> **Versão:** 1.0.0
> **Última Atualização:** 2026-04-07
> **Responsável:** Security Team

## Visão Geral

Este documento descreve as políticas de segurança implementadas no Self-Healing Engine para garantir operações seguras de auto-recuperação, prevenção de danos colaterais e conformidade com requisitos de governança.

## Arquitetura de Segurança

```
┌─────────────────────────────────────────────────────────────┐
│                    Self-Healing Engine                       │
│                                                               │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐ │
│  │  Detection   │────▶│   Remediation│────▶│    OPA     │ │
│  │  Service     │     │   Manager    │     │  Policies   │ │
│  └──────────────┘     └──────────────┘     └────────────┘ │
│         │                    │                   │         │
│         ▼                    ▼                   ▼         │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐ │
│  │  Prometheus  │     │   Playbook   │     │   Audit    │ │
│  │   Metrics    │     │   Executor   │     │    Log     │ │
│  └──────────────┘     └──────────────┘     └────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                   ┌────────────────┐
                   │   Kubernetes   │
                   │     Cluster     │
                   └────────────────┘
```

## 1. Políticas OPA (Open Policy Agent)

### 1.1 Configuração

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `opa_enabled` | `true` | Habilita validação OPA |
| `opa_fail_open` | `true` | Permite ações se OPA indisponível |
| `opa_timeout_seconds` | `5` | Timeout para avaliação de política |
| `opa_cache_ttl_seconds` | `60` | TTL de cache de decisões OPA |

### 1.2 Políticas de Validação de Playbooks

#### 1.2.1 Política de Ações de Remediação

**Caminho:** `neuralhive/self_healing/playbook_validation`

```rego
package neuralhive.self_healing

# Verifica se ação de remediação é permitida
default allow = false

allow {
    not deny
}

deny {
    input.resource.action == "reallocate_ticket"
    count(input.context.last_reallocation_timestamp) > 0
    time.now_ns() - input.context.last_reallocation_timestamp < 300000000000
}

deny {
    input.resource.action == "restart_workflow"
    input.resource.workflow_id == ""
}

deny {
    input.resource.action == "trigger_replanning"
    input.context.plan_id == ""
}
```

#### 1.2.2 Política de Rate Limiting

**Previne:** Múltiplas ações no mesmo recurso em curto período.

```rego
deny {
    count(input.resource.affected_tickets) > 10
}
```

#### 1.2.3 Política de Janela de Manutenção

**Previne:** Ações destrutivas fora da janela permitida.

```rego
deny {
    input.resource.action == "delete_pod"
    not is_maintenance_window()
}

is_maintenance_window[hour] {
    hour := time.clock(time.now_ns())
    hour >= 0
    hour < 6  # Apenas madrugada
}
```

### 1.3 Políticas de Chaos Engineering

**Configuração:** `chaos_require_opa_approval = true`

```rego
package neuralhive.chaos

allow {
    input.executor.role == "admin"
    input.experiment.environment != "production"
}

allow {
    input.executor.approval["approved_by"] != ""
    input.executor.approval["timestamp"] > 0
}
```

## 2. Políticas de Execução de Playbooks

### 2.1 Validação Estrutural

Todo playbook deve passar validação Pydantic antes da execução:

- ✅ `playbook_name`: string, 1-100 caracteres
- ✅ `timeout_seconds`: 1-3600 segundos
- ✅ `actions`: mínimo 1 ação
- ✅ `action.type`: deve ser um ActionType válido

### 2.2 Tipos de Ação Suportados

| Categoria | Ações |
|-----------|-------|
| Tickets | `reallocate_ticket`, `update_ticket_status`, `get_ticket` |
| Workflow | `pause_workflow`, `resume_workflow`, `trigger_replanning` |
| Kubernetes | `restart_pod`, `delete_pod`, `scale_deployment` |
| Kafka | `check_kafka_lag`, `reset_consumer_offset` |
| Database | `check_database_connection`, `execute_query` |
| Geral | `wait`, `log`, `notify` |

### 2.3 Limites de Execução

| Recurso | Limite |
|---------|--------|
| Actions por playbook | 20 (warning), 50 (hard) |
| Timeout total | 600s (warning), 3600s (hard) |
| Pod restarts por hora | 10 |
| Realocações por ticket | 3/hora |

## 3. Políticas de Acesso RBAC

### 3.1 Roles do Kubernetes

| Role | Permissões |
|------|------------|
| `self-healing-admin` | Full access aos recursos |
| `self-healing-operator` | Pods, Deployments, Services |
| `self-healing-viewer` | Read-only |

### 3.2 Network Policies

**Default deny-all:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: self-healing-engine-deny-all
spec:
  podSelector:
    matchLabels:
      app: self-healing-engine
  policyTypes:
  - Ingress
  - Egress
```

**Allowed traffic:**

```yaml
# Ingress: apenas de APIs Gateway
# Egress: Kafka, MongoDB, Redis, OPA
```

## 4. Políticas de Segurança de Dados

### 4.1 Dados Sensíveis

| Tipo | Armazenamento | Criptografia |
|------|---------------|--------------|
| Secrets | Kubernetes Secrets | at-rest (AES-256) |
| Logs | Elasticsearch | TLS em trânsito |
| Métricas | Prometheus | N/A (não sensível) |

### 4.2 Retenção de Logs

| Tipo | Retenção |
|------|----------|
| Audit logs | 1 ano |
| Error logs | 6 meses |
| Debug logs | 30 dias |

## 5. Políticas de Rate Limiting

### 5.1 APIs Externas

| API | Limite |
|-----|--------|
| Orchestrator gRPC | 100 req/min |
| Execution Ticket Service | 200 req/min |
| OPA Policy Engine | 50 req/min |

### 5.2 Circuit Breakers

```python
circuit_breaker_config = {
    "execution_ticket_service": {
        "failure_threshold": 5,
        "timeout_seconds": 60,
        "reset_timeout": 30,
    },
    "orchestrator": {
        "failure_threshold": 5,
        "timeout_seconds": 60,
        "reset_timeout": 30,
    },
    "opa": {
        "failure_threshold": 5,
        "timeout_seconds": 60,
        "reset_timeout": 30,
    },
}
```

## 6. Políticas de Compliance

### 6.1 Auditoria

Todas as ações de remediação são registradas:

```json
{
  "timestamp": "2026-04-07T10:30:00Z",
  "action": "reallocate_ticket",
  "actor": "self-healing-engine",
  "resource": "ticket-123",
  "opa_decision": "allowed",
  "result": "success"
}
```

### 6.2 Labels de Segurança

Todo recurso deve ter:

```yaml
labels:
  app: self-healing-engine
  security-level: "high"
  data-classification: "internal"
  owner: "platform-team"
```

## 7. Políticas de Chaos Engineering

### 7.1 GameDay Permissions

| Role | Permissão |
|------|-----------|
| Admin | Full access |
| Platform Lead | Approve experiments |
| Developer | Propose experiments |

### 7.2 Proteções em Produção

```yaml
chaos_engine:
  production_protections:
    blast_radius_percentage: 10
    max_experiments_parallel: 1
    require_manual_approval: true
    allowed_hours: "02:00-06:00"
```

## 8. Procedimentos de Resposta a Incidentes

### 8.1 Self-Healing Desativado

Se o self-healing causar problemas:

```bash
# 1. Desativar imediatamente
kubectl patch configmap self-healing-config \
  --type=json \
  -p='[{"op": "replace", "path": "/data/enabled", "value": "false"}]'

# 2. Escalar para zero
kubectl scale deployment self-healing-engine --replicas=0

# 3. Investigar logs
kubectl logs -f deployment/self-healing-engine
```

### 8.2 Loop de Remediação

Se detectar loop de remediação:

```bash
# 1. Identificar playbook em loop
kubectl get events --field-selector reason=RemediationTriggered

# 2. Desativar playbook específico
kubectl annotate playbook <name> self-healing.neuralhive/disabled="true"
```

## 9. Métricas de Segurança

### 9.1 Prometheus Metrics

```promql
# Taxa de ações negadas pelo OPA
rate(opa_validation_denied_total[5m])

# Circuit breakers abertos
self_healing_circuit_breaker_state{state="open"}

# Playbooks com falha de validação
rate(playbook_validation_failed_total[5m])
```

### 9.2 Alertas

| Alerta | Condição | Severidade |
|--------|----------|-----------|
| `SelfHealingOPADown` | OPA indisponível | CRITICAL |
| `SelfHealingHighDenyRate` | >10% negadas | WARNING |
| `SelfHealingCircuitOpen` | Circuit breaker open | CRITICAL |

## 10. Referências

- [OPA Documentation](https://www.openpolicyagent.org/docs/latest/)
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Chaos Engineering Principles](https://principlesofchaos.org/)
