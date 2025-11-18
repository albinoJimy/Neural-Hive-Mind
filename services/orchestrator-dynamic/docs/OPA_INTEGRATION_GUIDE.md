# Guia de Integração OPA - Orchestrator Dynamic

## Visão Geral

O Orchestrator Dynamic integra-se com o Open Policy Agent (OPA) para aplicar políticas de governança e compliance em tempo de execução. Esta integração permite validações declarativas de planos cognitivos e tickets de execução, garantindo que requisições atendam aos critérios de segurança, recursos e SLA antes da execução.

### Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│ Orchestrator Dynamic                                    │
│                                                          │
│  ┌──────────────┐         ┌──────────────────────┐     │
│  │ C1: Plan     │────────▶│ PolicyValidator      │     │
│  │ Validation   │         │                      │     │
│  └──────────────┘         │  ┌────────────────┐  │     │
│                           │  │ OPAClient      │  │     │
│  ┌──────────────┐         │  │                │  │     │
│  │ C3: Resource │────────▶│  │ Circuit        │◀─┼─────┼──▶ OPA Server
│  │ Allocation   │         │  │ Breaker        │  │     │    :8181
│  └──────────────┘         │  │                │  │     │
│                           │  │ Cache (TTL)    │  │     │
│                           │  └────────────────┘  │     │
│                           └──────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Características Principais

- **Validação Declarativa**: Políticas Rego definem regras de forma declarativa
- **Circuit Breaker**: Proteção contra cascading failures com pybreaker
- **Cache TTL**: Cache de decisões para reduzir latência
- **Batch Evaluation**: Avaliação paralela de múltiplas políticas
- **Fail-Open/Fail-Closed**: Estratégias configuráveis para falhas de OPA
- **Métricas**: Observabilidade completa via Prometheus

---

## Catálogo de Políticas

### 1. Resource Limits (`neuralhive/orchestrator/resource_limits`)

Valida limites de recursos baseados em `risk_band` do ticket.

**Regras:**

| Regra | Severidade | Descrição |
|-------|-----------|-----------|
| `timeout_exceeds_maximum` | high | Timeout excede máximo para o risk_band |
| `retries_exceed_maximum` | medium | Max retries excede máximo para o risk_band |
| `estimated_duration_unrealistic` | low/medium | Duração estimada muito curta (<1s) ou >= timeout |
| `capabilities_not_allowed` | high | Capability requerida não está na whitelist |
| `concurrent_tickets_limit` | high | Total de tickets excede limite concorrente |

**Limites de Timeout por Risk Band:**

```rego
timeout_limits := {
    "critical": 7200000,  # 2h
    "high": 3600000,      # 1h
    "medium": 1800000,    # 30min
    "low": 900000         # 15min
}
```

**Limites de Retries por Risk Band:**

```rego
retry_limits := {
    "critical": 5,
    "high": 3,
    "medium": 2,
    "low": 1
}
```

**Input Esperado:**

```json
{
  "resource": {
    "ticket_id": "ticket-123",
    "risk_band": "high",
    "sla": {
      "timeout_ms": 60000,
      "max_retries": 3
    },
    "estimated_duration_ms": 30000,
    "required_capabilities": ["code_generation"]
  },
  "parameters": {
    "allowed_capabilities": ["code_generation", "deployment", "testing"],
    "max_concurrent_tickets": 100
  },
  "context": {
    "total_tickets": 50
  }
}
```

**Output:**

```json
{
  "result": {
    "allow": true,
    "violations": [],
    "warnings": []
  }
}
```

---

### 2. SLA Enforcement (`neuralhive/orchestrator/sla_enforcement`)

Valida requisitos de SLA, QoS e prioridade alinhados ao risk_band.

**Regras:**

| Regra | Severidade | Descrição |
|-------|-----------|-----------|
| `deadline_in_past` | critical | Deadline está no passado |
| `deadline_too_far` | medium | Deadline muito distante (>7 dias) |
| `qos_mismatch_risk_band` | critical/high | QoS não alinhado com risk_band |
| `priority_mismatch_risk_band` | medium | Priority não permitida para risk_band |
| `timeout_insufficient` | high | Timeout < 1.5x estimated_duration |

**Requisitos de QoS por Risk Band:**

```rego
qos_requirements := {
    "critical": {
        "delivery_mode": "EXACTLY_ONCE",
        "consistency": "STRONG"
    },
    "high": {
        "delivery_mode": "EXACTLY_ONCE",
        "consistency": "STRONG"
    },
    "medium": {
        "delivery_mode": "AT_LEAST_ONCE",
        "consistency": ["STRONG", "EVENTUAL"]
    },
    "low": {
        "delivery_mode": ["AT_LEAST_ONCE", "AT_MOST_ONCE"],
        "consistency": ["STRONG", "EVENTUAL", "WEAK"]
    }
}
```

**Warnings:**

| Warning | Descrição |
|---------|-----------|
| `deadline_approaching_threshold` | Deadline se aproximando (<20% do tempo restante) |

**Input Esperado:**

```json
{
  "resource": {
    "ticket_id": "ticket-456",
    "risk_band": "critical",
    "sla": {
      "timeout_ms": 120000,
      "deadline": 1700000000000
    },
    "qos": {
      "delivery_mode": "EXACTLY_ONCE",
      "consistency": "STRONG"
    },
    "priority": "CRITICAL",
    "estimated_duration_ms": 60000
  },
  "context": {
    "current_time": 1699900000000
  }
}
```

---

### 3. Feature Flags (`neuralhive/orchestrator/feature_flags`)

Controla habilitação de funcionalidades avançadas baseadas em contexto e configuração.

**Features:**

| Feature | Descrição | Habilitação |
|---------|-----------|-------------|
| `enable_intelligent_scheduler` | Scheduler ML-based | Flag global + namespace permitido + risk_band |
| `enable_burst_capacity` | Burst de recursos | Flag global + carga < threshold + (tenant premium OU critical) |
| `enable_predictive_allocation` | Alocação preditiva | Flag global + acurácia modelo > 0.85 + namespace beta |
| `enable_auto_scaling` | Auto-scaling dinâmico | Flag global + queue_depth > threshold + horário comercial |
| `enable_experimental_features` | Features experimentais | Namespace dev/staging OU tenant early access |

**Input Esperado:**

```json
{
  "resource": {
    "ticket_id": "ticket-789",
    "risk_band": "high"
  },
  "flags": {
    "intelligent_scheduler_enabled": true,
    "scheduler_namespaces": ["production", "staging"],
    "burst_capacity_enabled": true,
    "burst_threshold": 0.8,
    "premium_tenants": ["tenant-1", "tenant-2"],
    "predictive_allocation_enabled": false,
    "auto_scaling_enabled": true,
    "scaling_threshold": 100
  },
  "context": {
    "namespace": "production",
    "current_load": 0.6,
    "tenant_id": "tenant-1",
    "queue_depth": 120,
    "current_time": 1699900000000,
    "model_accuracy": 0.9
  }
}
```

**Output:**

```json
{
  "result": {
    "enable_intelligent_scheduler": true,
    "enable_burst_capacity": true,
    "enable_predictive_allocation": false,
    "enable_auto_scaling": true,
    "enable_experimental_features": false
  }
}
```

---

## Configuração do OPA

### Variáveis de Ambiente

```bash
# OPA Server
OPA_HOST=localhost
OPA_PORT=8181
OPA_TIMEOUT_SECONDS=2

# Retry e Circuit Breaker
OPA_RETRY_ATTEMPTS=3
OPA_CIRCUIT_BREAKER_ENABLED=true
OPA_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
OPA_CIRCUIT_BREAKER_RESET_TIMEOUT=60

# Cache
OPA_CACHE_TTL_SECONDS=30

# Fail Strategy
OPA_FAIL_OPEN=false  # false = rejeitar tickets em falha OPA

# Políticas
OPA_POLICY_RESOURCE_LIMITS=neuralhive/orchestrator/resource_limits
OPA_POLICY_SLA_ENFORCEMENT=neuralhive/orchestrator/sla_enforcement
OPA_POLICY_FEATURE_FLAGS=neuralhive/orchestrator/feature_flags

# Parâmetros
OPA_MAX_CONCURRENT_TICKETS=100
OPA_ALLOWED_CAPABILITIES=code_generation,deployment,testing,validation
OPA_RESOURCE_LIMITS={"max_cpu": "4000m", "max_memory": "8Gi"}
```

### Deployment OPA

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opa
  namespace: orchestrator-dynamic
spec:
  replicas: 3
  selector:
    matchLabels:
      app: opa
  template:
    metadata:
      labels:
        app: opa
    spec:
      containers:
      - name: opa
        image: openpolicyagent/opa:0.58.0
        args:
        - "run"
        - "--server"
        - "--addr=0.0.0.0:8181"
        - "--set=decision_logs.console=true"
        - "/policies"
        ports:
        - containerPort: 8181
          name: http
        volumeMounts:
        - name: policies
          mountPath: /policies
          readOnly: true
        livenessProbe:
          httpGet:
            path: /health
            port: 8181
          initialDelaySeconds: 10
          periodSeconds: 5
        readinessProbe:
          httpGet:
            path: /health?bundle=true
            port: 8181
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
      volumes:
      - name: policies
        configMap:
          name: opa-policies
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: opa-policies
  namespace: orchestrator-dynamic
data:
  resource_limits.rego: |
    # Conteúdo de policies/rego/orchestrator/resource_limits.rego
  sla_enforcement.rego: |
    # Conteúdo de policies/rego/orchestrator/sla_enforcement.rego
  feature_flags.rego: |
    # Conteúdo de policies/rego/orchestrator/feature_flags.rego
---
apiVersion: v1
kind: Service
metadata:
  name: opa
  namespace: orchestrator-dynamic
spec:
  selector:
    app: opa
  ports:
  - port: 8181
    targetPort: 8181
    name: http
  type: ClusterIP
```

---

## Circuit Breaker

O circuit breaker protege contra cascading failures quando OPA está indisponível.

### Estados do Circuit Breaker

```
┌─────────┐
│ CLOSED  │ ◀───────┐
│ (normal)│         │
└────┬────┘         │
     │              │
     │ 5 failures   │ reset_timeout (60s)
     │              │
     ▼              │
┌─────────┐         │
│  OPEN   │         │
│(aberto) │         │
└────┬────┘         │
     │              │
     │ reset_timeout│
     │              │
     ▼              │
┌──────────┐        │
│ HALF_OPEN│────────┘
│(testando)│   success
└──────────┘
```

### Comportamento

1. **CLOSED** (Normal):
   - Chamadas passam normalmente
   - Falhas incrementam contador
   - Sucessos resetam contador

2. **OPEN** (Circuito Aberto):
   - Chamadas falham imediatamente com `CircuitBreakerError`
   - Convertido para `OPAConnectionError` com mensagem "Circuit breaker aberto"
   - Aguarda `reset_timeout` (60s) para tentar novamente

3. **HALF_OPEN** (Testando):
   - Próxima chamada testa conexão
   - Sucesso → CLOSED
   - Falha → OPEN

### Exceções Excluídas

O circuit breaker **não contabiliza** como falha:

- `OPAPolicyNotFoundError` (404): Política não encontrada é erro de configuração, não de disponibilidade

### Uso

```python
from src.policies import OPAClient

client = OPAClient(config)
await client.initialize()

try:
    result = await client.evaluate_policy(
        'neuralhive/orchestrator/resource_limits',
        input_data
    )
except OPAConnectionError as e:
    if 'circuit breaker aberto' in str(e).lower():
        # Circuit breaker está aberto
        # Aplicar estratégia fail-open ou fail-closed
        logger.error("Circuit breaker OPA aberto")
    else:
        # Erro de conexão normal
        logger.error(f"Erro de conexão OPA: {e}")
```

### Métricas

```python
state = client.get_circuit_breaker_state()
# {
#   'enabled': True,
#   'state': 'closed',  # closed/open/half_open
#   'failure_count': 0,
#   'last_failure_time': None
# }
```

---

## Monitoramento

### Métricas Prometheus

```python
# OPA evaluation latency
opa_evaluation_duration_seconds{policy="resource_limits"} 0.05

# OPA evaluation total
opa_evaluations_total{policy="resource_limits",status="success"} 1234

# OPA errors
opa_errors_total{error_type="connection_error"} 5
opa_errors_total{error_type="circuit_breaker_open"} 12

# Circuit breaker state
opa_circuit_breaker_state{state="closed"} 1

# Cache hit rate
opa_cache_hits_total 567
opa_cache_requests_total 1234
# Hit rate = 567 / 1234 = 46%
```

### Alertas Recomendados

```yaml
groups:
- name: opa_orchestrator
  rules:
  # Circuit breaker aberto
  - alert: OPACircuitBreakerOpen
    expr: opa_circuit_breaker_state{state="open"} == 1
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "OPA circuit breaker aberto"
      description: "Circuit breaker OPA aberto há mais de 1 minuto"

  # Taxa de erro alta
  - alert: OPAHighErrorRate
    expr: |
      rate(opa_errors_total[5m]) / rate(opa_evaluations_total[5m]) > 0.05
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Taxa de erro OPA alta (>5%)"

  # Latência alta
  - alert: OPAHighLatency
    expr: |
      histogram_quantile(0.95, opa_evaluation_duration_seconds) > 1.0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Latência P95 OPA > 1s"

  # Cache hit rate baixo
  - alert: OPALowCacheHitRate
    expr: |
      rate(opa_cache_hits_total[10m]) / rate(opa_cache_requests_total[10m]) < 0.3
    for: 10m
    labels:
      severity: info
    annotations:
      summary: "Cache hit rate OPA baixo (<30%)"
```

### Logs Estruturados

```json
{
  "event": "opa_evaluation",
  "policy_path": "neuralhive/orchestrator/resource_limits",
  "duration_ms": 45,
  "cache_hit": false,
  "result": {
    "allow": true,
    "violations": []
  }
}

{
  "event": "opa_circuit_breaker_state_change",
  "old_state": "closed",
  "new_state": "open",
  "failure_count": 5,
  "timestamp": "2024-11-16T10:30:00Z"
}
```

---

## Troubleshooting

### Problema: Circuit Breaker Abre Constantemente

**Sintomas:**
- Métricas mostram `opa_circuit_breaker_state{state="open"}` frequente
- Logs indicam "Circuit breaker aberto" repetidamente

**Causas Possíveis:**
1. OPA Server indisponível ou instável
2. Timeout configurado muito baixo
3. Rede instável entre orchestrator e OPA

**Soluções:**

```bash
# 1. Verificar saúde do OPA
kubectl logs -n orchestrator-dynamic -l app=opa --tail=100

# 2. Aumentar timeout
export OPA_TIMEOUT_SECONDS=5

# 3. Aumentar threshold de falhas
export OPA_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10

# 4. Verificar conectividade
kubectl exec -n orchestrator-dynamic orchestrator-dynamic-xxx -- \
  curl -v http://opa:8181/health
```

---

### Problema: Políticas Retornam Violações Inesperadas

**Sintomas:**
- Tickets válidos são rejeitados
- `result.allow = false` com violações não esperadas

**Diagnóstico:**

```bash
# 1. Testar política manualmente
opa eval -d policies/rego/orchestrator/resource_limits.rego \
  -i test_input.json \
  'data.neuralhive.orchestrator.resource_limits.result'

# 2. Verificar input enviado
# Ver logs estruturados do orchestrator com input completo
kubectl logs -n orchestrator-dynamic orchestrator-dynamic-xxx | \
  jq 'select(.event == "opa_evaluation")'

# 3. Validar limites configurados
# Revisar timeout_limits e retry_limits no arquivo .rego
```

**Soluções:**
1. Ajustar limites nas políticas Rego
2. Corrigir input enviado pelo orchestrator
3. Revisar mapeamento de risk_band → limites

---

### Problema: Cache Hit Rate Muito Baixo

**Sintomas:**
- `opa_cache_hits_total / opa_cache_requests_total < 0.3`
- Latência alta devido a chamadas repetidas ao OPA

**Causas:**
1. TTL muito curto (`OPA_CACHE_TTL_SECONDS`)
2. Input muito variável (cada ticket é único)
3. Cache size muito pequeno (maxsize=1000)

**Soluções:**

```python
# 1. Aumentar TTL (se políticas não mudam frequentemente)
config.opa_cache_ttl_seconds = 60

# 2. Aumentar cache size
self._cache = TTLCache(maxsize=5000, ttl=config.opa_cache_ttl_seconds)

# 3. Normalizar input para melhorar cache hit
# Remover campos variáveis como timestamps se não afetam decisão
```

---

### Problema: Latência Alta em Batch Evaluation

**Sintomas:**
- P95 de `opa_evaluation_duration_seconds` > 1s
- Validação de planos com múltiplas políticas demora muito

**Diagnóstico:**

```bash
# Ver latência por política
kubectl logs -n orchestrator-dynamic orchestrator-dynamic-xxx | \
  jq 'select(.event == "opa_evaluation") | {policy_path, duration_ms}' | \
  jq -s 'group_by(.policy_path) | map({policy: .[0].policy_path, avg: (map(.duration_ms) | add / length)})'
```

**Soluções:**

1. **Aumentar connection pool:**
```python
connector = aiohttp.TCPConnector(
    limit=200,  # Era 100
    limit_per_host=50  # Era 30
)
```

2. **Otimizar políticas Rego:**
   - Evitar loops desnecessários
   - Usar `some` em vez de comprehensions complexas
   - Pre-calcular valores constantes

3. **Escalar OPA horizontalmente:**
```bash
kubectl scale deployment opa -n orchestrator-dynamic --replicas=5
```

---

### Problema: OPAPolicyNotFoundError Frequente

**Sintomas:**
- Logs mostram `OPAPolicyNotFoundError` repetidamente
- Políticas não encontradas (404)

**Causas:**
1. ConfigMap `opa-policies` não montado corretamente
2. Path da política incorreto
3. OPA não carregou políticas no startup

**Soluções:**

```bash
# 1. Verificar ConfigMap
kubectl get configmap opa-policies -n orchestrator-dynamic -o yaml

# 2. Verificar se OPA carregou políticas
kubectl exec -n orchestrator-dynamic opa-xxx -- \
  curl http://localhost:8181/v1/policies

# 3. Recarregar políticas
kubectl delete pod -n orchestrator-dynamic -l app=opa

# 4. Verificar path correto
# Deve ser: neuralhive/orchestrator/resource_limits
# NÃO: /neuralhive/orchestrator/resource_limits
```

---

## Exemplos de Uso

### Exemplo 1: Validação de Plano Cognitivo em C1

```python
from src.policies import PolicyValidator

validator = PolicyValidator(opa_client, config)

plan = {
    'plan_id': 'plan-123',
    'tasks': [
        {'task_id': 't1', 'timeout_ms': 30000},
        {'task_id': 't2', 'timeout_ms': 60000}
    ],
    'execution_order': ['t1', 't2'],
    'risk_score': 0.7,
    'risk_band': 'high',
    'namespace': 'production'
}

result = await validator.validate_cognitive_plan(plan)

if not result.valid:
    logger.error("Plano rejeitado", violations=result.violations)
    for violation in result.violations:
        logger.error(
            f"Violação: {violation.policy_name}.{violation.rule_name}",
            severity=violation.severity,
            message=violation.message
        )
    # Rejeitar plano
else:
    logger.info("Plano aprovado")
    # Prosseguir para C2
```

### Exemplo 2: Validação de Ticket com Feature Flags em C3

```python
ticket = {
    'ticket_id': 'ticket-456',
    'risk_band': 'critical',
    'sla': {
        'timeout_ms': 120000,
        'deadline': int((datetime.now() + timedelta(hours=1)).timestamp() * 1000),
        'max_retries': 5
    },
    'qos': {
        'delivery_mode': 'EXACTLY_ONCE',
        'consistency': 'STRONG'
    },
    'priority': 'CRITICAL',
    'required_capabilities': ['code_generation'],
    'estimated_duration_ms': 60000,
    'namespace': 'production'
}

result = await validator.validate_execution_ticket(ticket)

if not result.valid:
    # Fail-closed: rejeitar ticket
    logger.error("Ticket rejeitado", ticket_id=ticket['ticket_id'])
    raise TicketValidationError(result.violations)

# Verificar feature flags
feature_flags = result.policy_decisions.get('feature_flags', {})

if feature_flags.get('enable_intelligent_scheduler'):
    # Usar scheduler ML-based
    logger.info("Usando intelligent scheduler")
    scheduler = IntelligentScheduler()
else:
    # Usar scheduler simples
    logger.info("Usando scheduler padrão")
    scheduler = SimpleScheduler()

# Alocar recursos
await scheduler.allocate(ticket)
```

### Exemplo 3: Tratamento de Circuit Breaker Aberto

```python
from src.policies.opa_client import OPAConnectionError

try:
    result = await validator.validate_execution_ticket(ticket)
except OPAConnectionError as e:
    if 'circuit breaker aberto' in str(e).lower():
        # Circuit breaker está aberto
        if config.opa_fail_open:
            # Fail-open: permitir ticket com warning
            logger.warning(
                "Circuit breaker OPA aberto - permitindo ticket (fail-open)",
                ticket_id=ticket['ticket_id']
            )
            # Criar resultado default com warnings
            result = ValidationResult(
                valid=True,
                violations=[],
                warnings=[{
                    'policy': 'opa',
                    'msg': 'Circuit breaker aberto - validação pulada'
                }],
                policy_decisions={}
            )
        else:
            # Fail-closed: rejeitar ticket
            logger.error(
                "Circuit breaker OPA aberto - rejeitando ticket (fail-closed)",
                ticket_id=ticket['ticket_id']
            )
            raise TicketValidationError([{
                'policy': 'opa',
                'severity': 'critical',
                'msg': 'Circuit breaker aberto - validação indisponível'
            }])
```

---

## Referências

- [OPA Documentation](https://www.openpolicyagent.org/docs/)
- [Rego Language Reference](https://www.openpolicyagent.org/docs/latest/policy-language/)
- [pybreaker Circuit Breaker](https://github.com/danielfm/pybreaker)
- Políticas Rego: `policies/rego/orchestrator/`
- Testes de Integração: `services/orchestrator-dynamic/tests/test_opa_integration.py`
