# Guia de Monitoramento de SLA do Orchestrator

## Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Configuração](#configuração)
4. [Monitoramento](#monitoramento)
5. [Troubleshooting](#troubleshooting)
6. [Runbooks](#runbooks)
7. [Testes](#testes)
8. [Melhores Práticas](#melhores-práticas)
9. [Referências](#referências)

---

## Visão Geral

### Propósito

O monitoramento de SLA no orchestrator garante que workflows atendam aos deadlines estabelecidos e que o error budget seja mantido dentro de limites aceitáveis. O sistema fornece:

- **Rastreamento de deadline em tempo real** para workflows e tickets
- **Monitoramento de error budget** via integração com SLA Management System
- **Alertas proativos** para condições de deadline se aproximando e budget crítico
- **Detecção automática de violações** com publicação de eventos
- **Deduplicação de alertas** baseada em Redis para prevenir alert storms
- **Streaming de eventos via Kafka** para consumidores downstream

### Arquitetura Simplificada

```
Workflow (C1-C6) → SLAMonitor → SLA Management System API
                       ↓                    ↓
                   Redis Cache         Budget Data
                       ↓
               AlertManager → Kafka (sla.alerts, sla.violations)
                       ↓
               Prometheus Metrics
                       ↓
               Alertmanager → Slack / PagerDuty
```

### Componentes Principais

1. **SLAMonitor** (`src/sla/sla_monitor.py`): 377 linhas
   - Verificação de deadline
   - Fetching de budget via API
   - Caching em Redis (TTL 10s)
   - Fail-open em caso de erros

2. **AlertManager** (`src/sla/alert_manager.py`): 297 linhas
   - Envio de alertas proativos
   - Deduplicação via Redis (TTL 5min)
   - Publicação ao Kafka

3. **Integração em Activities** (`src/activities/result_consolidation.py`): linhas 156-378
   - Monitoramento completo no passo C5
   - Verificação de deadline
   - Validação de budget threshold
   - Alertas proativos
   - Publicação de violações

4. **Monitoramento Proativo Opcional** (`src/activities/sla_monitoring.py`):
   - Verificações leves em C2 e C4
   - Controlado por feature flag
   - Fail-open, não bloqueia workflow

### Pontos de Integração

| Etapa | Tipo | Descrição |
|-------|------|-----------|
| **C2 (pós-geração de tickets)** | Proativo (opcional) | Early warning de deadline |
| **C4 (pós-publicação)** | Proativo (opcional) | Verificação final pré-consolidação |
| **C5 (consolidação)** | Reativo (sempre) | Monitoramento completo com alertas e violações |

---

## Arquitetura

### Diagrama de Fluxo Detalhado

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WORKFLOW EXECUTION                            │
│                                                                      │
│  C1: Validate  →  C2: Tickets  →  C3: Allocate  →  C4: Publish     │
│                       ↓ (opcional)                      ↓ (opcional) │
│                   Proactive SLA                     Proactive SLA    │
│                   Check #1                          Check #2         │
│                                                                      │
│  → C5: Consolidate  →  C6: Telemetry                                │
│        ↓ (sempre)                                                   │
│    SLA Monitor                                                      │
└─────────────────────────────────────────────────────────────────────┘
         │
         ├─────→ SLA Management System API
         │       GET /api/v1/budgets?service=orchestrator
         │       ↓
         │       Budget Data (remaining, status, burn_rates)
         │       ↓
         ├─────→ Redis Cache (TTL: 10s)
         │       KEY: sla:budget:orchestrator-dynamic
         │
         ├─────→ AlertManager
         │       ├─→ Kafka Topic: sla.alerts
         │       │   (BUDGET_CRITICAL, DEADLINE_APPROACHING)
         │       │
         │       └─→ Kafka Topic: sla.violations
         │           (DEADLINE_EXCEEDED, TIMEOUT)
         │
         └─────→ Prometheus Metrics
                 ├─→ orchestration_sla_remaining_seconds
                 ├─→ orchestration_sla_budget_remaining_percent
                 ├─→ orchestration_sla_violations_total
                 ├─→ orchestration_sla_alerts_sent_total
                 └─→ orchestration_sla_check_duration_seconds
                     ↓
                 Alertmanager
                 ├─→ Slack (#sla-alerts)
                 ├─→ PagerDuty (critical)
                 └─→ SLA Management System Webhook
```

### Componentes Detalhados

#### 1. SLAMonitor (`src/sla/sla_monitor.py`)

**Responsabilidades:**
- Buscar dados de budget do SLA Management System
- Cachear budgets em Redis para reduzir latência
- Verificar deadlines de tickets individuais
- Verificar SLA de workflow agregado
- Calcular tempo restante e percentual consumido

**Métodos Principais:**

```python
# Buscar budget do serviço (com cache)
async def get_service_budget(service_name: str) -> Optional[Dict[str, Any]]

# Verificar threshold de budget
async def check_budget_threshold(service_name: str, threshold: float) -> Tuple[bool, Optional[Dict]]

# Verificar deadline de ticket individual
def check_ticket_deadline(ticket: Dict[str, Any]) -> Dict[str, Any]

# Verificar SLA de workflow agregado
async def check_workflow_sla(workflow_id: str, tickets: List[Dict]) -> Dict[str, Any]
```

**Configurações:**
- `sla_management_enabled`: Habilitar/desabilitar (default: true)
- `sla_management_host`: Endpoint do SLA Management System
- `sla_management_timeout_seconds`: Timeout para API calls (default: 5s)
- `sla_management_cache_ttl_seconds`: TTL do cache Redis (default: 10s)

#### 2. AlertManager (`src/sla/alert_manager.py`)

**Responsabilidades:**
- Enviar alertas proativos ao Kafka
- Publicar violações formais ao Kafka
- Deduplicar alertas usando Redis
- Registrar métricas Prometheus

**Métodos Principais:**

```python
# Enviar alerta de deadline approaching
async def send_deadline_alert(workflow_id: str, ticket_id: str, deadline_data: Dict)

# Enviar alerta de budget crítico
async def send_budget_alert(workflow_id: str, service_name: str, budget_data: Dict)

# Publicar violação formal
async def publish_sla_violation(violation: Dict[str, Any])
```

**Tópicos Kafka:**
- `sla.alerts`: Alertas proativos (BUDGET_CRITICAL, DEADLINE_APPROACHING, BURN_RATE_HIGH)
- `sla.violations`: Violações formais (DEADLINE_EXCEEDED, TIMEOUT)

**Schema de Eventos:**

```python
# sla.alerts
{
    "alert_id": "uuid",
    "event_type": "BUDGET_CRITICAL | DEADLINE_APPROACHING | BURN_RATE_HIGH",
    "severity": "WARNING | CRITICAL",
    "timestamp": "2025-11-16T14:30:00Z",
    "context": {
        "workflow_id": "orch-abc123",
        "service_name": "orchestrator-dynamic",
        "budget_remaining": 0.15,
        "burn_rate": 8.5,
        "remaining_seconds": 120.0
    }
}

# sla.violations
{
    "violation_id": "uuid",
    "violation_type": "DEADLINE_EXCEEDED | TIMEOUT",
    "severity": "CRITICAL",
    "timestamp": "2025-11-16T14:35:00Z",
    "ticket_id": "ticket-xyz789",
    "workflow_id": "orch-abc123",
    "delay_ms": 5000
}
```

#### 3. Métricas Prometheus

| Métrica | Tipo | Descrição | Labels |
|---------|------|-----------|--------|
| `orchestration_sla_remaining_seconds` | Gauge | Tempo restante de SLA | workflow_id, risk_band |
| `orchestration_sla_budget_remaining_percent` | Gauge | Budget restante (%) | service_name |
| `orchestration_sla_budget_status` | Gauge | Status do budget (0-3) | service_name, status |
| `orchestration_sla_burn_rate` | Gauge | Taxa de consumo | service_name, window_hours |
| `orchestration_sla_violations_total` | Counter | Total de violações | violation_type |
| `orchestration_deadline_approaching_total` | Counter | Deadlines se aproximando | - |
| `orchestration_sla_alerts_sent_total` | Counter | Alertas enviados | alert_type |
| `orchestration_sla_alert_deduplication_hits_total` | Counter | Alertas deduplicados | - |
| `orchestration_sla_check_duration_seconds` | Histogram | Latência das verificações | check_type |
| `orchestration_sla_monitor_errors_total` | Counter | Erros no monitor | error_type |

---

## Configuração

### Variáveis de Ambiente

```bash
# === Monitoramento SLA Básico ===
SLA_MANAGEMENT_ENABLED=true
SLA_MANAGEMENT_HOST=sla-management-system.neural-hive-orchestration.svc.cluster.local
SLA_MANAGEMENT_PORT=8000
SLA_MANAGEMENT_TIMEOUT_SECONDS=5

# === Thresholds de Alerta ===
SLA_DEADLINE_WARNING_THRESHOLD=0.8      # Alertar quando 80% do deadline consumido
SLA_BUDGET_CRITICAL_THRESHOLD=0.2       # Alertar quando budget < 20%

# === Tópicos Kafka ===
SLA_ALERTS_TOPIC=sla.alerts
SLA_VIOLATIONS_TOPIC=sla.violations

# === Cache e Deduplicação ===
SLA_MANAGEMENT_CACHE_TTL_SECONDS=10     # TTL do cache Redis para budgets
SLA_ALERT_DEDUPLICATION_TTL_SECONDS=300 # TTL deduplicação (5 minutos)

# === Monitoramento Proativo (OPCIONAL) ===
SLA_PROACTIVE_MONITORING_ENABLED=false  # Default: desabilitado
```

### Arquivo de Configuração (`settings.py`)

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class OrchestratorSettings(BaseSettings):
    # SLA Management System Integration
    sla_management_enabled: bool = Field(default=True)
    sla_management_host: str = Field(default='sla-management-system...')
    sla_management_port: int = Field(default=8000)
    sla_management_timeout_seconds: int = Field(default=5)
    sla_management_cache_ttl_seconds: int = Field(default=10)

    # Thresholds
    sla_deadline_warning_threshold: float = Field(default=0.8)
    sla_budget_critical_threshold: float = Field(default=0.2)

    # Kafka Topics
    sla_alerts_topic: str = Field(default='sla.alerts')
    sla_violations_topic: str = Field(default='sla.violations')

    # Deduplicação
    sla_alert_deduplication_ttl_seconds: int = Field(default=300)

    # Monitoramento Proativo (Feature Flag)
    sla_proactive_monitoring_enabled: bool = Field(default=False)
    sla_proactive_checkpoints: list = Field(
        default=['post_ticket_generation', 'post_ticket_publishing']
    )
```

### Habilitar Monitoramento Proativo

**Quando usar:**
- Workflows com SLA muito restritivo (<5 minutos)
- Necessidade de early warning para acionar burst capacity
- Workflows complexos com múltiplos estágios

**Trade-offs:**
- **Prós**: Detecção precoce, capacidade de ação preventiva
- **Cons**: Adiciona 50-100ms de latência por check, requer SLA Management System disponível

**IMPORTANTE - Impacto de Performance em Alto Volume:**

A verificação proativa de SLA cria e fecha uma nova instância de `SLAMonitor`
(incluindo httpx.AsyncClient e conexões Redis) em **cada execução** da activity.

**Overhead esperado por verificação:**
- ~10-50ms: Criação de httpx.AsyncClient e conexões
- ~50-200ms: Chamada HTTP ao SLA Management System (se cache miss)
- ~5-10ms: Query Redis (se disponível)
- **Total: 65-260ms por verificação proativa**

**Com 2 checkpoints ativos (C2 + C4), cada workflow adiciona:**
- ~130-520ms de latência total
- 2-4 conexões HTTP ao SLA Management System
- 2-4 queries Redis

**Recomendações por Volume:**

| Volume de Workflows | Recomendação | Justificativa |
|---------------------|--------------|---------------|
| <50/min | ✅ Habilitar proativo | Overhead aceitável, benefícios superam custos |
| 50-100/min | ⚠️ Avaliar | Monitorar latência P95, considerar apenas checkpoint C4 |
| >100/min | ❌ Desabilitar | Overhead significativo, usar apenas monitoramento reativo em C5 |

**Alternativas para Alto Volume:**
1. Desabilitar completamente (`SLA_PROACTIVE_MONITORING_ENABLED=false`)
2. Usar apenas checkpoint final (`sla_proactive_checkpoints: ['post_ticket_publishing']`)
3. Aumentar cache TTL para reduzir calls ao SLA Management System
4. Escalar SLA Management System horizontalmente

**Configuração:**

```bash
# Habilitar via env var
export SLA_PROACTIVE_MONITORING_ENABLED=true

# OU via settings.yaml
sla_proactive_monitoring_enabled: true
sla_proactive_checkpoints:
  - post_ticket_generation  # Após C2
  - post_ticket_publishing  # Após C4
```

**Monitoramento do Overhead:**

```promql
# Latência P95 de verificações proativas
histogram_quantile(0.95,
  rate(orchestration_sla_check_duration_seconds_bucket{check_type=~"proactive_.*"}[5m])
)

# Taxa de verificações proativas
sum(rate(orchestration_sla_check_duration_seconds_count{check_type=~"proactive_.*"}[5m]))
```

### Configurar Alertmanager

**1. Merge com Configuração Existente:**

```bash
# Backup da config atual
kubectl get configmap alertmanager-config -n monitoring -o yaml > backup.yaml

# Editar e merge manualmente as seções 'routes' e 'receivers' de:
# monitoring/alertmanager/alertmanager-slack-pagerduty-config.yaml

# Aplicar configuração merged
kubectl apply -f alertmanager-merged-config.yaml
```

**2. Configurar Slack Webhook:**

```yaml
receivers:
  - name: 'slack-sla-warnings'
    slack_configs:
      - channel: '#sla-alerts'
        api_url: 'https://hooks.slack.com/services/YOUR_WEBHOOK_URL'
        text: '{{ template "slack.sla.text" . }}'
```

Obter webhook URL em: https://api.slack.com/messaging/webhooks

**3. Configurar PagerDuty:**

```yaml
receivers:
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'YOUR_INTEGRATION_KEY'
        severity: 'critical'
```

Obter integration key em: PagerDuty → Services → Integrations → Events API V2

---

## Monitoramento

### Dashboards Grafana

#### 1. Dashboard do Orchestrator (`fluxo-c-orquestracao`)

**Localização:** http://grafana/d/fluxo-c-orchestration

**Row: SLA Compliance & Alerting**

| Painel | Métrica | Threshold |
|--------|---------|-----------|
| **SLA Remaining Time** | `min(orchestration_sla_remaining_seconds)` | Verde >300s, Amarelo 60-300s, Vermelho <60s |
| **Error Budget Status** | `orchestration_sla_budget_remaining_percent` | Verde >50%, Amarelo 20-50%, Vermelho <20% |
| **SLA Violations (Last Hour)** | `increase(orchestration_sla_violations_total[1h])` | Verde =0, Vermelho >0 |
| **Deadline Approaching** | `increase(orchestration_deadline_approaching_total[15m])` | Verde <5, Amarelo 5-10, Vermelho >10 |
| **SLA Alerts Sent** | `rate(orchestration_sla_alerts_sent_total[5m])` by alert_type | - |
| **Budget Burn Rate** | `orchestration_sla_burn_rate{window_hours="1"}` | Warning @6, Critical @10 |
| **SLA Check Performance** | `histogram_quantile(0.95, ...)` by check_type | Alert se P95 >5s |
| **Alert Deduplication Rate** | `rate(...deduplication_hits) / rate(...alerts_sent)` | Monitor trends |

#### 2. Dashboard do SLA Management System (`sla-management-system`)

**Localização:** http://grafana/d/sla-management-system

Fornece análise detalhada de budgets, burn rates e SLOs.

### Alertas Prometheus

**Arquivo:** `monitoring/alerts/orchestrator-sla-alerts.yaml`

**14 regras de alerta em 4 grupos:**

#### Grupo 1: Violações Críticas

```yaml
# Budget Esgotado (CRITICAL)
- alert: OrchestratorBudgetExhausted
  expr: orchestration_sla_budget_remaining_percent <= 0
  for: 1m
  annotations:
    summary: "Error budget completamente esgotado"

# SLA Violado (CRITICAL)
- alert: OrchestratorDeadlineExceeded
  expr: increase(orchestration_sla_violations_total{violation_type="DEADLINE_EXCEEDED"}[5m]) > 0
  annotations:
    summary: "Deadline de SLA excedido"
```

#### Grupo 2: Budget Warnings

```yaml
# Budget Crítico (WARNING → CRITICAL)
- alert: OrchestratorBudgetCritical
  expr: orchestration_sla_budget_remaining_percent < 20
  for: 5m
  labels:
    severity: critical

# Burn Rate Alto (WARNING)
- alert: OrchestratorHighBurnRate
  expr: orchestration_sla_burn_rate{window_hours="1"} > 6
  for: 10m
```

#### Grupo 3: Deadline Warnings

```yaml
# Deadline Approaching (WARNING)
- alert: OrchestratorDeadlineApproaching
  expr: increase(orchestration_deadline_approaching_total[15m]) > 5
  labels:
    severity: warning
```

#### Grupo 4: Monitoramento do Monitor

```yaml
# SLA Monitor Down (CRITICAL)
- alert: OrchestratorSLAMonitorDown
  expr: rate(orchestration_sla_check_duration_seconds_count[5m]) == 0
  for: 2m
```

### Consumindo Eventos Kafka

#### Alertas Proativos (`sla.alerts`)

```bash
# Console consumer
kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic sla.alerts \
  --from-beginning

# Python consumer
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    'sla.alerts',
    bootstrap_servers=['kafka:9092'],
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

for message in consumer:
    alert = message.value
    print(f"Alert: {alert['event_type']} - {alert['context']}")
```

#### Violações Formais (`sla.violations`)

```bash
kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic sla.violations \
  --from-beginning
```

---

## Troubleshooting

### Issue 1: Verificações de SLA Não Executam

**Sintomas:**
- `orchestration_sla_check_duration_seconds_count` = 0
- Sem alertas sendo gerados
- Logs não mostram chamadas ao SLA Management System

**Causas Possíveis:**

1. **SLA monitoring desabilitado**
   ```bash
   # Verificar configuração
   kubectl get configmap orchestrator-config -n neural-hive-orchestration -o yaml | grep SLA_MANAGEMENT_ENABLED
   ```
   **Solução:** `SLA_MANAGEMENT_ENABLED=true`

2. **SLA Management System indisponível**
   ```bash
   # Testar conectividade
   kubectl exec -it orchestrator-pod -- curl http://sla-management-system:8000/health
   ```
   **Solução:** Verificar health do SLA Management System

3. **Workflow não alcança C5**
   ```bash
   # Verificar logs do workflow
   kubectl logs -n neural-hive-orchestration orchestrator-pod | grep "C5: Consolidando"
   ```
   **Solução:** Investigar falhas em C1-C4

### Issue 2: Alertas Não São Enviados

**Sintomas:**
- `orchestration_sla_alerts_sent_total` = 0
- Violações detectadas mas sem alertas no Slack/PagerDuty
- Métricas mostram deadline approaching

**Causas Possíveis:**

1. **Kafka producer não inicializado**
   ```bash
   # Verificar logs
   kubectl logs orchestrator-pod | grep "KafkaProducer"
   ```
   **Solução:** Verificar conectividade Kafka

2. **Deduplicação bloqueando todos os alertas**
   ```bash
   # Verificar métrica
   kubectl exec prometheus-pod -- promtool query instant \
     'orchestration_sla_alert_deduplication_hits_total'
   ```
   **Solução:** Reduzir TTL de deduplicação ou investigar alert storm

3. **Alertmanager não configurado**
   ```bash
   # Verificar rotas do Alertmanager
   kubectl exec alertmanager-0 -n monitoring -- amtool config routes show
   ```
   **Solução:** Aplicar configuração do Alertmanager

### Issue 3: Alta Latência nas Verificações

**Sintomas:**
- `orchestration_sla_check_duration_seconds` P95 > 5s
- Workflows mais lentos após habilitar SLA monitoring
- Timeouts em verificações de SLA

**Causas Possíveis:**

1. **SLA Management System lento**
   ```bash
   # Medir latência diretamente
   time curl http://sla-management-system:8000/api/v1/budgets?service=orchestrator-dynamic
   ```
   **Solução:** Otimizar SLA Management System ou aumentar recursos

2. **Redis indisponível (sem cache)**
   ```bash
   # Verificar Redis
   kubectl exec redis-pod -- redis-cli ping
   ```
   **Solução:** Restaurar Redis, cache reduz latência de ~500ms para ~10ms

3. **Problemas de rede**
   ```bash
   # Testar latência de rede
   kubectl exec orchestrator-pod -- ping -c 5 sla-management-system
   ```
   **Solução:** Investigar network policies, DNS, service mesh

### Issue 4: Alert Storm

**Sintomas:**
- `orchestration_sla_alert_deduplication_hits_total` muito alto
- Centenas de alertas em poucos minutos
- Slack/PagerDuty sendo spammed

**Causas Possíveis:**

1. **Muitos workflows violando SLA simultaneamente**
   ```bash
   # Investigar causa raiz
   kubectl logs orchestrator-pod | grep "deadline_approaching" | wc -l
   ```
   **Solução:** Resolver incidente subjacente (capacidade, falha de serviço)

2. **TTL de deduplicação muito baixo**
   ```bash
   # Verificar configuração
   echo $SLA_ALERT_DEDUPLICATION_TTL_SECONDS
   ```
   **Solução:** Aumentar para 600s (10min) durante incidentes

3. **Budget esgotado**
   ```bash
   # Verificar budget
   curl http://sla-management-system:8000/api/v1/budgets?service=orchestrator-dynamic
   ```
   **Solução:** Freezar deployments, resolver erros

### Issue 5: Falsos Positivos de Violação

**Sintomas:**
- Violações reportadas mas tickets completaram com sucesso
- Diferenças entre tempo reportado e real
- SLA violations não correlacionam com falhas reais

**Causas Possíveis:**

1. **Clock skew entre serviços**
   ```bash
   # Verificar NTP sync
   kubectl exec orchestrator-pod -- date
   kubectl exec sla-management-system-pod -- date
   ```
   **Solução:** Garantir sincronização NTP em todos os nodes

2. **Configuração incorreta de timeout_ms**
   ```bash
   # Verificar tickets gerados
   kubectl logs orchestrator-pod | grep "timeout_ms"
   ```
   **Solução:** Revisar cálculo de timeout em `generate_execution_tickets`

3. **Estimativas de duração imprecisas**
   ```bash
   # Comparar estimado vs real
   # Query Prometheus
   histogram_quantile(0.95, rate(ticket_execution_duration_seconds_bucket[1h]))
   ```
   **Solução:** Retreinar modelo ML de previsão de duração

---

## Runbooks

### Runbook 1: Budget Crítico (<20%)

**Severidade:** WARNING → CRITICAL
**Impact:** Risco de esgotamento de budget e violações de SLA
**SLO Afetado:** Error Budget

#### Investigação

1. **Verificar budget atual**
   ```bash
   curl http://sla-management-system:8000/api/v1/budgets?service=orchestrator-dynamic | jq
   ```

2. **Identificar fonte de erros**
   ```bash
   # Taxa de erro por tipo
   kubectl logs orchestrator-pod | grep ERROR | awk '{print $5}' | sort | uniq -c | sort -rn
   ```

3. **Revisar mudanças recentes**
   ```bash
   # Últimos deployments
   kubectl rollout history deployment/orchestrator-dynamic -n neural-hive-orchestration
   ```

4. **Verificar utilização de recursos**
   ```bash
   kubectl top pods -n neural-hive-orchestration
   ```

#### Mitigação

1. **Freezar deployments não-críticos**
   - Pausar rollouts automáticos
   - Apenas hotfixes críticos

2. **Habilitar burst capacity** (se disponível)
   ```bash
   kubectl scale deployment/worker-agents --replicas=10
   ```

3. **Aumentar worker pool**
   ```bash
   # Temporary scale-up
   kubectl patch deployment orchestrator-dynamic -p '{"spec":{"template":{"spec":{"containers":[{"name":"orchestrator","env":[{"name":"WORKER_POOL_SIZE","value":"20"}]}]}}}}'
   ```

4. **Implementar circuit breakers** para dependências falhando
   - Verificar se specialists estão falhando
   - Ativar fallbacks

#### Escalação

- **Budget <10%**: Notificar líder de plantão
- **Budget <5%**: Page incident commander
- **Budget esgotado**: Incidente P1, convocar war room

### Runbook 2: Deadline Approaching (>80% consumido)

**Severidade:** WARNING
**Impact:** Workflow pode violar SLA se não completar logo
**SLO Afetado:** Latency

#### Investigação

1. **Identificar workflow e tickets**
   ```bash
   # Via logs
   kubectl logs orchestrator-pod | grep -A 5 "deadline_approaching"

   # Via Grafana
   # Dashboard → SLA Compliance → Deadline Approaching panel
   ```

2. **Verificar status dos tickets**
   ```python
   # Query Temporal
   from temporalio.client import Client
   client = await Client.connect("temporal:7233")
   workflow = client.get_workflow_handle(workflow_id)
   status = await workflow.query("get_status")
   print(status)
   ```

3. **Revisar disponibilidade de workers**
   ```bash
   # Workers saudáveis
   kubectl get pods -l agent_type=worker,status=healthy
   ```

4. **Verificar fila de trabalho**
   ```bash
   # Depth da fila Kafka
   kafka-consumer-groups --bootstrap-server kafka:9092 \
     --describe --group worker-agents-group
   ```

#### Mitigação

1. **Boost de prioridade** para tickets críticos
   ```python
   # Republicar com prioridade alta
   await publish_ticket_to_kafka(ticket, priority="HIGH")
   ```

2. **Alocar workers adicionais**
   ```bash
   kubectl scale deployment/worker-agents --replicas=15
   ```

3. **Cancelar tickets não-críticos** (se aplicável)
   ```python
   # Via Temporal signal
   await workflow.signal("cancel_ticket", ticket_id="non-critical-123")
   ```

4. **Intervenção manual** se necessário
   - Executar ticket manualmente
   - Marcar como completado via compensação

#### Escalação

- **Tempo restante <60s**: Page on-call engineer
- **Workflow bloqueado**: Escalar para time de specialists

### Runbook 3: SLA Violation Detectada

**Severidade:** CRITICAL
**Impact:** SLA breach, potencial impacto ao cliente
**SLO Afetado:** Latency e/ou Availability

#### Investigação

1. **Identificar violação**
   ```bash
   # Consumer Kafka
   kafka-console-consumer --bootstrap-server kafka:9092 \
     --topic sla.violations --max-messages 1
   ```

2. **Revisar timeline do ticket**
   ```bash
   # Logs do ticket
   kubectl logs orchestrator-pod | grep "ticket_id: ticket-xyz789"
   ```

3. **Analisar causa raiz**
   - Timeout: Verificar se specialist travou
   - Failure: Revisar logs de erro
   - Resource contention: Verificar métricas de CPU/memória

4. **Verificar se é padrão ou incidente isolado**
   ```bash
   # Contagem de violações na última hora
   kubectl exec prometheus-pod -- promtool query instant \
     'increase(orchestration_sla_violations_total[1h])'
   ```

#### Mitigação

1. **Documentar incidente** em post-mortem
   - Timeline detalhada
   - Causa raiz
   - Ações corretivas

2. **Ajustar SLA thresholds** se irrealista
   ```yaml
   # Revisar configuração
   sla_deadline_warning_threshold: 0.75  # Era 0.8
   ```

3. **Melhorar previsões de duração**
   ```bash
   # Retreinar modelo ML
   python scripts/retrain_duration_predictor.py --data last_30_days
   ```

4. **Implementar medidas preventivas**
   - Circuit breakers
   - Rate limiting
   - Timeouts ajustados

#### Escalação

- **Violação detectada**: Page on-call imediatamente
- **Múltiplas violações**: Notificar stakeholders (product, customer success)
- **Incidente em andamento**: Convocar incident response team

### Runbook 4: SLA Monitor Down

**Severidade:** CRITICAL
**Impact:** Sem visibilidade de SLA, potenciais violações não detectadas
**SLO Afetado:** Monitoring Availability

#### Investigação

1. **Verificar health do SLA Management System**
   ```bash
   kubectl get pods -l app=sla-management-system
   kubectl logs sla-management-system-pod --tail=50
   curl http://sla-management-system:8000/health
   ```

2. **Verificar conectividade do orchestrator**
   ```bash
   kubectl exec orchestrator-pod -- curl -v http://sla-management-system:8000/health
   ```

3. **Revisar logs do orchestrator**
   ```bash
   kubectl logs orchestrator-pod | grep "SLA\|sla_monitor"
   ```

4. **Verificar Redis e Kafka**
   ```bash
   kubectl get pods -l app=redis
   kubectl get pods -l app=kafka
   ```

#### Mitigação

1. **Restart do SLA Management System** se unhealthy
   ```bash
   kubectl rollout restart deployment/sla-management-system
   ```

2. **Verificar network policies**
   ```bash
   kubectl get networkpolicies -n neural-hive-orchestration
   kubectl describe networkpolicy sla-management-system
   ```

3. **Verificar service discovery**
   ```bash
   kubectl get svc sla-management-system
   kubectl get endpoints sla-management-system
   ```

4. **Habilitar fail-open temporariamente** (último recurso)
   ```bash
   # Desabilitar SLA monitoring
   kubectl set env deployment/orchestrator-dynamic SLA_MANAGEMENT_ENABLED=false
   ```

5. **Monitorar workflows manualmente** via Grafana
   - Dashboard do orchestrator
   - Métricas de latência
   - Taxa de sucesso

#### Escalação

- **Monitor down >5min**: Page on-call engineer
- **SLA Management System crash**: Escalar para infra team
- **Incidente prolongado**: Notificar management

---

## Testes

### Testes Unitários

**Localização:**
- `tests/unit/test_sla_monitor.py` (12 test cases)
- `tests/unit/test_alert_manager.py` (16 test cases)

**Executar:**
```bash
pytest tests/unit/test_sla_monitor.py -v
pytest tests/unit/test_alert_manager.py -v
```

**Cobertura:** 100% dos métodos principais

### Testes de Integração (Mocked)

**Localização:** `tests/integration/test_sla_integration.py` (8 scenarios)

**Cenários:**
1. Deadline approaching detectado
2. Budget critical alertado
3. Violações publicadas ao Kafka
4. Fail-open quando SLA Management System indisponível
5. Deduplicação de alertas
6. Cache Redis funcionando
7. Workflow completo C5 com SLA
8. Proactive monitoring em C2/C4

**Executar:**
```bash
pytest tests/integration/test_sla_integration.py -v
```

### Testes de Integração Real

**Localização:** `tests/integration/test_sla_real_integration.py`

**Requisitos:**
- SLA Management System rodando
- Redis disponível
- Kafka disponível

**Executar:**
```bash
# Apenas quando serviços reais disponíveis
pytest -m real_integration tests/integration/test_sla_real_integration.py -v

# Pular real integration (padrão)
pytest -m "not real_integration"
```

**Cenários:**
1. Fetch real de budget da API
2. Threshold checking com dados reais
3. Deadline check com tickets realistas
4. Publicação real de alertas ao Kafka
5. Publicação de violações
6. Caching Redis end-to-end
7. Deduplicação com Redis real
8. Fluxo completo integrado

### Testes Manuais

#### Teste 1: Trigger Deadline Approaching Alert

```python
# Criar ticket com deadline curto
ticket = {
    "ticket_id": "test-deadline-123",
    "sla": {
        "deadline": datetime.utcnow() + timedelta(seconds=30),  # 30s deadline
        "timeout_ms": 30000,
        "estimated_duration_ms": 25000  # 83% consumido
    }
}

# Publicar via orchestrator
await publish_ticket_to_kafka(ticket)

# Verificar alert no Kafka
kafka-console-consumer --topic sla.alerts --max-messages 1
```

#### Teste 2: Trigger Budget Critical Alert

```bash
# Simular alta taxa de erro
for i in {1..100}; do
  curl -X POST http://orchestrator:8000/api/v1/test-error
done

# Verificar budget
curl http://sla-management-system:8000/api/v1/budgets?service=orchestrator-dynamic

# Esperar alert (se budget < 20%)
```

#### Teste 3: Verificar Routing de Alertas

```bash
# Enviar alert de teste ao Alertmanager
curl -H "Content-Type: application/json" -d '[{
  "labels": {
    "alertname": "OrchestratorBudgetCritical",
    "severity": "critical",
    "component": "orchestrator-dynamic",
    "service_name": "orchestrator-dynamic"
  },
  "annotations": {
    "summary": "Budget crítico de teste",
    "budget_remaining": "15"
  }
}]' http://alertmanager:9093/api/v1/alerts

# Verificar no Slack #sla-alerts
# Verificar no PagerDuty
```

#### Teste 4: Validar Deduplicação

```bash
# Enviar mesmo alert 3x em 1 minuto
for i in {1..3}; do
  curl -X POST http://orchestrator:8000/api/v1/test-alert
  sleep 10
done

# Verificar métrica de deduplicação
kubectl exec prometheus-pod -- promtool query instant \
  'orchestration_sla_alert_deduplication_hits_total'

# Deve mostrar 2 hits (segundo e terceiro bloqueados)
```

---

## Melhores Práticas

### Configuração de SLA

1. **Definir deadlines realistas**
   - Basear em dados históricos (P95 duration + 20% buffer)
   - Usar risk_band para diferenciar requisitos (critical vs non-critical)
   - Revisar periodicamente com base em violações

2. **Configurar timeout_ms conservadoramente**
   ```python
   timeout_ms = estimated_duration_ms * 2  # 2x o esperado
   ```

3. **Usar risk bands adequadamente**
   - `CRITICAL`: SLA restritivo (P95 + 10%)
   - `HIGH`: SLA normal (P95 + 20%)
   - `MEDIUM`: SLA relaxado (P95 + 50%)
   - `LOW`: Best-effort (sem SLA)

### Alerting

1. **Deduplicação para prevenir alert storms**
   - TTL default: 5 minutos
   - Aumentar para 10-15min durante incidentes
   - Monitorar `orchestration_sla_alert_deduplication_hits_total`

2. **Routing inteligente**
   - **Critical alerts** → PagerDuty (page on-call)
   - **Warning alerts** → Slack (notify team)
   - **Info alerts** → Logs apenas

3. **Inhibit rules**
   ```yaml
   # Suprimir warnings quando critical ativo
   inhibit_rules:
     - source_match:
         severity: critical
       target_match:
         severity: warning
       equal: ['alertname', 'service_name']
   ```

4. **Contexto acionável em alertas**
   - Sempre incluir: workflow_id, ticket_id, remaining_seconds
   - Links para: Dashboard Grafana, Runbook, Logs
   - Evitar alertas genéricos sem contexto

### Monitoramento

1. **Revisar dashboard diariamente**
   - SLA Compliance row no dashboard do orchestrator
   - Identificar tendências antes de virar incidente
   - Verificar burn rate

2. **Configurar relatórios semanais**
   - Total de violações
   - Top workflows com deadlines approaching
   - Utilização de budget
   - Taxa de deduplicação

3. **Monitorar burn rate para prever esgotamento**
   ```promql
   # Tempo até esgotar budget (em horas)
   orchestration_sla_budget_remaining_percent / orchestration_sla_burn_rate{window_hours="1"}
   ```

4. **Track alert deduplication rate**
   - Taxa alta (>50%): Indicativo de alert storm ou threshold muito sensível
   - Taxa baixa (<5%): Deduplicação não está funcionando

### Capacity Planning

1. **Usar violações como sinal de capacidade**
   - Violações aumentando: Escalar workers, reduzir carga
   - Correlacionar com métricas de CPU/memória

2. **Monitorar correlação entre utilização e SLA**
   ```promql
   # SLA remaining vs CPU usage
   orchestration_sla_remaining_seconds / on() group_left() avg(container_cpu_usage_seconds_total)
   ```

3. **Implementar auto-scaling baseado em SLA**
   ```yaml
   # HPA customizado
   metrics:
     - type: Pods
       pods:
         metric:
           name: orchestration_sla_remaining_seconds
         target:
           type: AverageValue
           averageValue: "300"  # Escalar se <5min restante
   ```

4. **Manter error budget reserve para incidentes**
   - Target: >30% budget restante sempre
   - Freezar deploys se <20%
   - Emergency freeze se <10%

### Troubleshooting

1. **Fail-open é crítico**
   - SLA monitoring nunca deve bloquear workflows
   - Log errors mas continue execução
   - Alertar se monitor está down

2. **Usar logs estruturados**
   ```python
   logger.warning(
       "SLA deadline approaching",
       workflow_id=workflow_id,
       remaining_seconds=120.5,
       ticket_count=5
   )
   ```

3. **Correlacionar eventos entre sistemas**
   - Timestamp preciso (NTP sync)
   - Trace IDs para correlação
   - Centralizar logs (ELK, Loki)

4. **Documentar false positives**
   - Criar runbook para cada tipo
   - Ajustar thresholds se necessário
   - Treinar time para reconhecer

---

## Referências

### Documentação Relacionada

- **SLA Management System API:** `/docs/sla-management-system-api.md`
- **Temporal Workflow Guide:** `services/orchestrator-dynamic/README.md`
- **Prometheus Alerting:** `monitoring/alerts/README.md`
- **Kafka Topics:** `k8s/kafka-topics/README.md`

### Código Fonte

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `src/sla/sla_monitor.py` | 377 | Lógica de monitoramento SLA |
| `src/sla/alert_manager.py` | 297 | Publicação de alertas e violações |
| `src/activities/result_consolidation.py` | 156-378 | Integração em C5 |
| `src/activities/sla_monitoring.py` | 205 | Monitoramento proativo |
| `src/config/settings.py` | 84-190 | Configurações SLA |
| `src/observability/metrics.py` | 96-143 | Métricas Prometheus |
| `monitoring/alerts/orchestrator-sla-alerts.yaml` | - | Regras de alerta |
| `monitoring/alertmanager/alertmanager-slack-pagerduty-config.yaml` | - | Configuração Alertmanager |
| `monitoring/dashboards/fluxo-c-orquestracao.json` | 749-1190 | Dashboard Grafana |

### Links Externos

- **Google SRE Book - SLOs:** https://sre.google/sre-book/service-level-objectives/
- **Error Budget Policy:** https://sre.google/workbook/error-budget-policy/
- **Alertmanager Config:** https://prometheus.io/docs/alerting/latest/configuration/
- **Slack Webhooks:** https://api.slack.com/messaging/webhooks
- **PagerDuty Events API:** https://developer.pagerduty.com/docs/events-api-v2/overview/
- **Temporal Best Practices:** https://docs.temporal.io/dev-guide/

### Comandos Úteis

```bash
# === Verificação de SLA ===
# Status do SLA Management System
curl http://sla-management-system:8000/health

# Budget atual
curl http://sla-management-system:8000/api/v1/budgets?service=orchestrator-dynamic | jq

# === Métricas Prometheus ===
# Tempo restante de SLA
curl 'http://prometheus:9090/api/v1/query?query=min(orchestration_sla_remaining_seconds)'

# Budget restante
curl 'http://prometheus:9090/api/v1/query?query=orchestration_sla_budget_remaining_percent'

# Total de violações
curl 'http://prometheus:9090/api/v1/query?query=sum(orchestration_sla_violations_total)'

# === Kafka ===
# Consumer de alertas
kafka-console-consumer --bootstrap-server kafka:9092 --topic sla.alerts

# Consumer de violações
kafka-console-consumer --bootstrap-server kafka:9092 --topic sla.violations

# === Redis ===
# Verificar cache de budget
redis-cli GET "sla:budget:orchestrator-dynamic"

# Verificar deduplicação
redis-cli KEYS "sla:alert:*"

# === Alertmanager ===
# Validar configuração
amtool config routes test --config.file=/etc/alertmanager/alertmanager.yml

# Listar alertas ativos
amtool alert

# Criar silence
amtool silence add alertname=OrchestratorBudgetWarning --duration=1h

# === Kubernetes ===
# Logs do orchestrator
kubectl logs -f -l app=orchestrator-dynamic | grep SLA

# Métricas dos pods
kubectl top pods -l app=orchestrator-dynamic

# Restart deployment
kubectl rollout restart deployment/orchestrator-dynamic
```

---

**Última Atualização:** 2025-11-16
**Versão:** 1.0
**Mantenedores:** Time de Orchestration
