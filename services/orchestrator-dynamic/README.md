# Orchestrator Dynamic - Orquestrador Dinâmico

**Versão**: 1.0.0
**Fase**: 2.1 - Fundação do Orquestrador
**Status**: Implementação Base Completa (85%)

## Visão Geral

O **Orchestrator Dynamic** é o componente central da Fase 2 do Neural Hive-Mind, responsável por implementar o **Fluxo C - Orquestração de Execução Adaptativa** conforme descrito no `documento-06-fluxos-processos-neural-hive-mind.md`.

Este serviço consome **Consolidated Decisions** do Consensus Engine, converte **Cognitive Plans** em **Execution Tickets**, e orquestra a execução distribuída seguindo políticas de SLA, QoS e priorização baseada em risk bands.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator Dynamic                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────────────────────────┐  │
│  │ FastAPI      │    │ Temporal Worker                  │  │
│  │              │    │                                  │  │
│  │ /health      │    │  ┌────────────────────────────┐ │  │
│  │ /ready       │    │  │ OrchestrationWorkflow      │ │  │
│  │ /metrics     │    │  │  • C1: Validate Plan       │ │  │
│  │ /api/v1/...  │    │  │  • C2: Generate Tickets    │ │  │
│  └──────────────┘    │  │  • C3: Allocate Resources  │ │  │
│                       │  │  • C4: Publish Tickets     │ │  │
│  ┌──────────────┐    │  │  • C5: Consolidate Results │ │  │
│  │ Kafka        │    │  │  • C6: Publish Telemetry   │ │  │
│  │ Consumer     │───→│  └────────────────────────────┘ │  │
│  │              │    │                                  │  │
│  │ plans.       │    │  Activities:                     │  │
│  │ consensus    │    │  • plan_validation               │  │
│  └──────────────┘    │  • ticket_generation             │  │
│                       │  • result_consolidation          │  │
│                       └──────────────────────────────────┘  │
│                                                               │
│  Observability:                                              │
│  • Prometheus Metrics (20+ métricas)                        │
│  • OpenTelemetry Tracing                                    │
│  • Structured Logging (structlog)                           │
│  • PolicyValidator + OPA Enforcement                         │
└─────────────────────────────────────────────────────────────┘
         │                        │                   │
         ↓                        ↓                   ↓
    Kafka Topics            PostgreSQL          MongoDB
    • execution.tickets     (Temporal State)   (Auditoria)
    • orchestration.incidents
    • telemetry.orchestration
```

## Observability & Tracing

O serviço está instrumentado com OpenTelemetry via `neural_hive_observability`, habilitando tracing para Kafka (consumers/producers), gRPC (clientes) e workflows Temporal. Os spans incluem atributos customizados do Neural Hive para facilitar correlação:
- `neural.hive.intent.id`: ID da intenção original
- `neural.hive.plan.id`: ID do plano cognitivo
- `neural.hive.decision.id`: ID da decisão consolidada
- `neural.hive.workflow.id`: ID do workflow Temporal
- `neural.hive.ticket.id`: ID do execution ticket
- `neural.hive.worker.id`: ID do worker alocado
- `neural.hive.ml.*`: Atributos de operações ML (source, predicted_queue_ms, predicted_load_pct, anomaly_score, optimization_source)
- `messaging.kafka.*`: Tópico/partição/offset Kafka consumido
- `rpc.*`: Serviço/método gRPC invocado

Consultas úteis no Jaeger:
- Por plano: `neural.hive.plan.id=<plan_id>`
- Por intenção: `neural.hive.intent.id=<intent_id>`
- Spans ML: `operation=load.predict_worker_load` ou `operation=scheduling.optimize_allocation`

Visualização: os traces são exportados para o OTLP Collector configurado em `OTEL_EXPORTER_ENDPOINT` e podem ser inspecionados no Jaeger UI do cluster.

## Tecnologias

- **Framework**: FastAPI 0.104+
- **Workflow Engine**: Temporal 1.5+ (Python SDK)
- **Messaging**: Kafka (aiokafka)
- **State Store**: PostgreSQL 15 (Temporal)
- **Auditoria**: MongoDB 6+
- **Cache**: Redis Cluster
- **Observabilidade**: Prometheus + OpenTelemetry + Jaeger
- **Logging**: structlog

## Estrutura do Projeto

```
services/orchestrator-dynamic/
├── Dockerfile                 # Multi-stage Docker build
├── requirements.txt           # Dependências Python
├── src/
│   ├── main.py               # Entry point FastAPI + lifecycle
│   ├── config/
│   │   └── settings.py       # Pydantic Settings (Temporal, Kafka, DB)
│   ├── scheduler/
│   │   ├── intelligent_scheduler.py  # Scheduler principal
│   │   ├── priority_calculator.py    # Cálculo de prioridades
│   │   └── resource_allocator.py     # Alocação de recursos
│   ├── sla/
│   │   ├── sla_monitor.py           # Monitor proativo de SLA
│   │   └── alert_manager.py         # Gerenciador de alertas SLA
│   ├── workflows/
│   │   └── orchestration_workflow.py  # Workflow principal Fluxo C
│   ├── activities/
│   │   ├── plan_validation.py         # C1: Validação
│   │   ├── ticket_generation.py       # C2: Geração de tickets
│   │   └── result_consolidation.py    # C5-C6: Consolidação e telemetria
│   ├── clients/
│   │   ├── service_registry_client.py # Cliente gRPC Service Registry
│   │   ├── kafka_producer.py          # Cliente Kafka Producer
│   │   ├── redis_client.py            # Cliente Redis (singleton)
│   │   └── mongodb_client.py          # Cliente MongoDB
│   ├── consumers/
│   │   └── decision_consumer.py       # Consumer plans.consensus
│   ├── workers/
│   │   └── temporal_worker.py         # Temporal Worker Manager
│   ├── models/
│   │   └── execution_ticket.py        # Pydantic model ExecutionTicket
│   └── observability/
│       └── metrics.py                 # Métricas Prometheus
└── README.md (este arquivo)
```

## Fluxo de Execução (Fluxo C)

### Etapa C1: Validar Plano Cognitivo
- Verifica schema Avro do Cognitive Plan
- Valida campos obrigatórios, versão, expiração
- Detecta ciclos no DAG de dependências
- Audita resultado no MongoDB

### Etapa C2: Quebrar Plano em Tickets
- Gera um `ExecutionTicket` para cada task do plano
- Calcula SLA baseado em `risk_band` e `estimated_duration_ms`
- Define QoS (delivery_mode, consistency, durability)
- Mapeia dependencies (task_ids → ticket_ids)
- Ordena tickets topologicamente

### Etapa C3: Alocar Recursos
- Usa `IntelligentScheduler` para alocação otimizada
- Calcula `priority_score` baseado em risk_band, QoS e SLA urgency
- Descobre workers via Service Registry gRPC
- Seleciona melhor worker baseado em score composto
- Fallback para alocação stub se Service Registry indisponível
- Tempo de reação <30s conforme SLO

### Etapa C4: Executar Tarefas
- Publica cada ticket no Kafka `execution.tickets`
- Aguarda confirmação de publicação
- Atualiza status do ticket para `RUNNING`
- Persiste ticket no MongoDB para auditoria

### Etapa C5: Consolidar Resultado
- Agrega resultados de todos os tickets
- Calcula métricas (duração, sucesso/falha, retries, SLA violations)
- Valida integridade (verifica inconsistências)
- Aciona autocura (Fluxo E) se necessário

### Etapa C6: Publicar Telemetria
- Cria Telemetry Frame com correlação completa
- Publica no Kafka `telemetry.orchestration`
- Exporta métricas para Prometheus
- Cria span OpenTelemetry para o workflow
- Buffer local em caso de falha

## MongoDB Persistence

- Coleções: `validation_audit` (auditoria C1), `workflow_results` (resultados C5), `incidents` (autocura Fluxo E), `telemetry_buffer` (retry de telemetria)
- Estruturas: cada coleção inclui `workflow_id`; `validation_audit` armazena `validation_result`, `timestamp`, `hash`; `workflow_results` guarda métricas/SLA e resumo de tickets; `incidents` registra `type`, `details`, `severity`; `telemetry_buffer` persiste frame com `buffered_at` e `retry_count`
- Índices: `validation_audit` em `plan_id`, `workflow_id`, `(plan_id, timestamp)`; `workflow_results` em `workflow_id` (único), `status`, `(status, consolidated_at)`; `incidents` em `workflow_id`, `type`, `(severity, timestamp)`; `telemetry_buffer` em `workflow_id`, `buffered_at`, `(retry_count, buffered_at)`
- Uso: auditoria completa de validações, consolidação para analytics/SLA, trilha de incidentes para autocura e buffer resiliente de telemetria
- Diagrama (simplificado): `plan_validation.audit_validation → validation_audit` | `consolidate_results → workflow_results` | `trigger_self_healing → incidents` | `buffer_telemetry → telemetry_buffer`

## Retry e Resiliência

- Todas as operações de persistência usam `tenacity` com `stop_after_attempt(config.retry_max_attempts)` e `wait_exponential` (`multiplier=config.retry_backoff_coefficient`, `min=config.retry_initial_interval_ms/1000`, `max=config.retry_max_interval_ms/1000`)
- Fail-open por padrão: erros de MongoDB são logados e não bloqueiam workflow (orquestração continua em modo degradado)
- Logs estruturados para sucesso/erro: `validation_audit_saved`, `workflow_result_saved`, `incident_saved`, `telemetry_buffered`
- Configurações padrão em `src/config/settings.py`: tentativas=3, intervalo inicial=1000ms, backoff=2.0, intervalo máximo=60000ms

## Configuração MongoDB

- `MONGODB_URI`: string de conexão (pode vir do Vault)
- `MONGODB_DATABASE`: nome do database (default: `neural_hive_orchestration`)
- `RETRY_MAX_ATTEMPTS`: tentativas de retry (default: 3)
- `RETRY_INITIAL_INTERVAL_MS`: intervalo inicial em ms (default: 1000)
- `RETRY_BACKOFF_COEFFICIENT`: multiplicador do backoff (default: 2.0)
- `RETRY_MAX_INTERVAL_MS`: intervalo máximo em ms (default: 60000)

## Troubleshooting MongoDB

- MongoDB indisponível: serviço segue em modo degradado; logs `mongodb_client_not_initialized` indicam que a activity foi pulada
- Falhas recorrentes de persistência: revisar logs `*_persist_failed`, ajustar parâmetros de retry ou conexão
- Índices: executar `db.<collection>.getIndexes()` para validar criação; `workflow_results` usa `_id=workflow_id` com índice único
- Consultas rápidas: contar validações por plano (`db.validation_audit.countDocuments({plan_id: "<id>"})`), listar SLA violados (`db.workflow_results.find({"sla_status.violations_count": {$gt: 0}})`), incidentes críticos (`db.incidents.find({severity: "CRITICAL"})`)

## Testes de Persistência

- Rodar unitários: `pytest services/orchestrator-dynamic/tests/test_mongodb_persistence.py`
- Rodar integração das activities: `pytest services/orchestrator-dynamic/tests/test_activities_mongodb_integration.py`
- Tests usam MongoDB mockado e validam retry + fail-open; seguros para execução local sem MongoDB real

## Policy Validation

- Integração com OPA Policy Engine cobrindo C1 (plano cognitivo), C2 (tickets) e C3 (alocação de recursos).
- C1: `plan_validation.validate_cognitive_plan` valida planos completos com `resource_limits.rego` e `sla_enforcement.rego`.
- C2: `ticket_generation.allocate_resources` valida tickets e aplica `feature_flags.rego` para habilitar Intelligent Scheduler e capacidades relacionadas.
- C3: `ticket_generation.allocate_resources` valida a alocação retornada pelo `IntelligentScheduler.schedule_ticket` via `validate_resource_allocation`.
- Métricas OPA registradas em todas as etapas (validações, rejeições, warnings e erros).
- Detalhamento completo em `docs/POLICY_VALIDATION_INTEGRATION.md`.

## OPA Policy Enforcement

- Enforcement centralizado com OPA no C1 (plano completo) e C3 (tickets e alocações), usando `PolicyValidator` + `OPAClient`.
- Políticas ativas: `resource_limits`, `sla_enforcement`, `feature_flags`, `security_constraints`.
- Configuração rápida (env):
  - `OPA_ENABLED=true`, `OPA_HOST`, `OPA_PORT`, `OPA_TIMEOUT_SECONDS`, `OPA_FAIL_OPEN`
  - `OPA_POLICY_RESOURCE_LIMITS`, `OPA_POLICY_SLA_ENFORCEMENT`, `OPA_POLICY_FEATURE_FLAGS`, `OPA_POLICY_SECURITY_CONSTRAINTS`
  - `OPA_CIRCUIT_BREAKER_ENABLED=true`, `OPA_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5`, `OPA_CACHE_TTL_SECONDS=30`
- Documentação: `docs/OPA_INTEGRATION_GUIDE.md` e `docs/FEATURE_FLAGS_GUIDE.md`.
- Validação rápida: `scripts/validate_opa_integration.sh` (faz healthcheck, valida políticas e roda testes E2E).
- Observabilidade: métricas OPA já expostas em `/metrics` e alertas pré-configurados em `monitoring/prometheus-rules/orchestrator-opa-alerts.yaml`.
- Troubleshooting resumido:
  - OPA indisponível → verificar `/health`, métrica `orchestration_opa_evaluation_errors_total`, circuit breaker (`orchestration_opa_circuit_breaker_state`).
  - Rejeições inesperadas → revisar `orchestration_opa_policy_rejections_total{policy_name,rule}` e testar entrada no OPA Playground.
  - Cache/latência → `orchestration_opa_cache_hits_total` e `orchestration_opa_validation_duration_seconds`.

## Scheduler Inteligente

O Orchestrator Dynamic inclui um scheduler inteligente que otimiza a alocação de recursos para execution tickets baseado em múltiplos fatores:

### Principais Funcionalidades

- **Priorização Multi-Fator:** Combina risk band (40%), requisitos QoS (30%) e urgência SLA (30%) para priorização inteligente
- **Integração com Service Registry:** Descobre workers disponíveis via gRPC com matching de health e capabilities
- **Seleção Inteligente de Workers:** Scoring composto baseado em saúde do agente, telemetria (taxa de sucesso, latência, experiência)
- **Cache de Performance:** Cache baseado em TTL para descoberta de workers reduz latência em 70-80%
- **Fallback Gracioso:** Fallback automático para alocação stub quando Service Registry está indisponível
- **Integração ML:** Boost de prioridade baseado em duração de execução prevista por modelos ML
- **Enforcement de Política OPA:** Valida tickets contra políticas antes da alocação
- **Métricas Abrangentes:** 10+ métricas Prometheus para monitoramento e alertas

### Arquitetura

```
Ticket → Validação OPA → Predições ML → Cálculo de Prioridade → Descoberta de Workers → Seleção → Alocação
                                                                           ↓
                                                                    Service Registry
```

### Configuração

```yaml
# Habilitar/desabilitar scheduler
ENABLE_INTELLIGENT_SCHEDULER: "true"

# Conexão Service Registry
SERVICE_REGISTRY_ENDPOINT: "service-registry:50051"
SERVICE_REGISTRY_CACHE_TTL_SECONDS: "60"
SERVICE_REGISTRY_MAX_RESULTS: "10"

# Pesos de prioridade (customizar scoring)
SCHEDULER_PRIORITY_WEIGHTS: '{"risk": 0.4, "qos": 0.3, "sla": 0.3}'
```

### Priorização

Score composto: `(risk_weight * 0.4) + (qos_weight * 0.3) + (sla_urgency * 0.3)`

**Risk Weights:**
- critical: 1.0
- high: 0.7
- normal: 0.5
- low: 0.3

**QoS Weights:**
- EXACTLY_ONCE + STRONG + PERSISTENT: 1.0
- AT_LEAST_ONCE + STRONG: 0.85
- AT_LEAST_ONCE + EVENTUAL + PERSISTENT: 0.595
- AT_MOST_ONCE: 0.5

**SLA Urgency:**
- 0-50% deadline consumido: 0.3
- 50-80%: 0.7
- 80-100%: 1.0

### Discovery de Workers

- Integração gRPC com Service Registry
- Matching baseado em capabilities, namespace e security level
- Ranking por health + telemetria (success_rate, latência, experiência)
- Cache de descobertas (TTL configurável, padrão 60s)
- Timeout 5s com fallback gracioso

### Seleção de Workers

Score composto do worker: `(agent_score * 0.6) + (priority_score * 0.4)`

**Agent Score** combina:
- Health (50%): status HEALTHY=1.0, DEGRADED=0.6, UNHEALTHY=0.0
- Telemetry (50%): (success_rate × 0.6) + (duration_score × 0.2) + (experience × 0.2)

**Disponibilidade:**
- Status: deve ser HEALTHY ou DEGRADED
- Capacidade: active_tasks < max_concurrent_tasks

### Monitoramento

**Dashboards:**
- Métricas detalhadas: `monitoring/dashboards/orchestrator-intelligent-scheduler.json`
- Visão geral: `monitoring/dashboards/fluxo-c-orquestracao.json` (seção Scheduler)

**Métricas Principais:**
- `orchestration_scheduler_allocations_total`: Total de alocações (sucesso/falha)
- `orchestration_scheduler_allocation_duration_seconds`: Latência de alocação (p50, p95, p99)
- `orchestration_scheduler_priority_score`: Distribuição de scores de prioridade por risk band
- `orchestration_scheduler_workers_discovered`: Workers encontrados por alocação
- `orchestration_scheduler_cache_hits_total`: Eficiência de cache
- `orchestration_scheduler_rejections_total`: Razões de rejeição

**Endpoint Prometheus:** `http://localhost:8000/metrics`

### Performance

- **Latência:** p95 < 200ms (típico: p50 ~50ms, p95 ~150ms)
- **Taxa de Cache Hit:** 70-80% típico
- **Taxa de Fallback:** <5% em ambientes saudáveis
- **Throughput:** Até 50 alocações concorrentes

### Testes

```bash
# Executar todos os testes do scheduler
./scripts/test_scheduler.sh

# Testes unitários apenas
pytest tests/unit/test_intelligent_scheduler.py -v

# Testes de integração
pytest tests/integration/test_scheduler_integration.py -v
```

**Cobertura de Testes:** 40+ testes cobrindo todos os componentes do scheduler e cenários de integração

## SLA Monitoring

O Orchestrator Dynamic implementa monitoramento proativo de SLA em tempo de execução, integrado com o SLA Management System.

### Componentes

#### SLAMonitor (`src/sla/sla_monitor.py`)

Responsável por verificar deadlines de tickets e consultar error budgets via API:

- **Verificação de Deadlines**: Calcula tempo restante e percentual consumido para cada ticket
- **Agregação de Workflow**: Identifica tickets críticos (>80% deadline consumido)
- **Consulta de Budgets**: Integração HTTP com SLA Management System API
- **Cache Redis**: Cache de budgets com TTL configurável (default: 10s)
- **Fail-open**: Continua operação mesmo com falhas no sistema de SLA

#### AlertManager (`src/sla/alert_manager.py`)

Gerencia publicação de alertas proativos e violações no Kafka:

- **Alertas Proativos**: Budget crítico, deadline próximo, burn rate alto
- **Violações SLA**: Eventos de deadline excedido ou timeout
- **Deduplicação**: Cache Redis de alertas enviados (TTL: 5min)
- **Fail-safe**: Validação de Kafka producer antes de publicação

### Tópicos Kafka

- **`sla.alerts`**: Alertas proativos (BUDGET_CRITICAL, DEADLINE_APPROACHING, BURN_RATE_HIGH)
- **`sla.violations`**: Violações formais de SLA (DEADLINE_EXCEEDED, TIMEOUT)

Cada mensagem inclui campo `event_type` ('ALERT' ou 'VIOLATION') para distinção clara.

### Integração no Fluxo C5

Durante consolidação de resultados (`result_consolidation.py`):

1. **Inicialização**: Cria clientes Redis e Kafka compartilhados
2. **Verificação de Deadlines**: Monitora todos os tickets do workflow
3. **Alertas de Deadline**: Envia alertas para tickets críticos (>80% consumido)
4. **Verificação de Budget**: Consulta error budget do serviço
5. **Alertas de Budget**: Envia alertas se budget < 20%
6. **Detecção de Violações**: Calcula duração real vs timeout_ms usando:
   - `actual_duration_ms` (se disponível)
   - `completed_at - started_at` (calculado de timestamps)
   - `estimated_duration_ms` (fallback)
7. **Publicação de Violações**: Publica eventos de violação no Kafka
8. **Cleanup**: Fecha conexões Redis e Kafka

### Configuração

Variáveis de ambiente:

```bash
# SLA Management System Integration
SLA_MANAGEMENT_ENABLED=true
SLA_MANAGEMENT_HOST=sla-management-system.neural-hive-orchestration.svc.cluster.local
SLA_MANAGEMENT_PORT=8000
SLA_MANAGEMENT_TIMEOUT_SECONDS=5
SLA_MANAGEMENT_CACHE_TTL_SECONDS=10

# Thresholds
SLA_BUDGET_CRITICAL_THRESHOLD=0.2        # 20%
SLA_DEADLINE_WARNING_THRESHOLD=0.8       # 80%

# Kafka Topics
SLA_VIOLATIONS_TOPIC=sla.violations
SLA_ALERTS_TOPIC=sla.alerts

# Deduplicação
SLA_ALERT_DEDUPLICATION_TTL_SECONDS=300  # 5 minutos
```

### Métricas Prometheus

**Budgets**:
- `orchestration_sla_budget_remaining_percent` - Percentual de error budget restante (labels: service_name, slo_id)
- `orchestration_sla_budget_status` - Status do budget: 0=HEALTHY, 1=WARNING, 2=CRITICAL, 3=EXHAUSTED (labels: service_name, slo_id)
- `orchestration_sla_burn_rate` - Taxa de consumo do budget (labels: service_name, window_hours)

**Alertas**:
- `orchestration_sla_alerts_sent_total` - Total de alertas enviados (labels: alert_type, severity)
- `orchestration_sla_alert_deduplication_hits_total` - Alertas bloqueados por deduplicação

**Violações**:
- `orchestration_sla_violations_published_total` - Violações publicadas no Kafka (labels: violation_type)

**Performance**:
- `orchestration_sla_check_duration_seconds` - Duração de verificações (labels: check_type) - buckets: [0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]

**Erros**:
- `orchestration_sla_monitor_errors_total` - Erros no SLA monitoring (labels: error_type: api_error, cache_error, deadline_check, workflow_check, producer_not_initialized, alert_publish, violation_publish)

### Exemplo de Queries PromQL

```promql
# Budget restante por serviço
orchestration_sla_budget_remaining_percent{service_name="orchestrator-dynamic"}

# Taxa de burn do budget (1h)
orchestration_sla_burn_rate{service_name="orchestrator-dynamic", window_hours="1"}

# Alertas críticos enviados
rate(orchestration_sla_alerts_sent_total{severity="CRITICAL"}[5m])

# Taxa de violações por tipo
rate(orchestration_sla_violations_published_total[5m]) by (violation_type)

# Latência P95 de verificações SLA
histogram_quantile(0.95, rate(orchestration_sla_check_duration_seconds_bucket[5m])) by (check_type)
```

### Alertas Prometheus

Ver regras em `monitoring/alerts/orchestrator-sla-alerts.yaml`:

- **SLABudgetCritical**: Budget < 20%
- **SLABudgetExhausted**: Budget = 0%
- **SLAHighBurnRate**: Taxa de consumo > 10x em 1h
- **SLAViolationRate**: Taxa de violações > threshold

### Troubleshooting

**Erro: "kafka_producer_not_configured"**
- Verificar conectividade Kafka: `kubectl exec -it <pod> -- nc -zv kafka-bootstrap 9092`
- Revisar logs de inicialização do produtor

**Erro: "sla_api_request_error"**
- Verificar SLA Management System: `kubectl get pods -l app=sla-management-system`
- Testar endpoint: `curl http://sla-management-system:8000/api/v1/budgets?service_name=orchestrator-dynamic`

**Alertas não sendo enviados**
- Verificar métrica `orchestration_sla_monitor_errors_total{error_type="producer_not_initialized"}`
- Verificar deduplicação: `orchestration_sla_alert_deduplication_hits_total`

**Violações não detectadas**
- Verificar se tickets possuem `started_at` e `completed_at` preenchidos
- Revisar campo `duration_source` em metadata da violação (persisted/calculated/estimated)

### Monitoramento Proativo (Opcional)

O orchestrator suporta verificações proativas de SLA durante execução do workflow, controlado por feature flag:

```bash
# Habilitar monitoramento proativo
SLA_PROACTIVE_MONITORING_ENABLED=true
```

**Checkpoints:**
- **Pós C2 (geração de tickets)**: Early warning de deadline approaching
- **Pós C4 (publicação)**: Verificação final antes da consolidação

**Trade-offs:**
- **Prós**: Detecção precoce, capacidade de ação preventiva
- **Cons**: Adiciona 50-100ms de latência por check

**Quando usar:**
- Workflows com SLA muito restritivo (<5 minutos)
- Necessidade de early warning para acionar burst capacity
- Workflows complexos com múltiplos estágios

### Alertas Slack e PagerDuty

Configuração de alertas externos via Alertmanager:

**Configuração Slack:**

```yaml
# Ver: monitoring/alertmanager/alertmanager-slack-pagerduty-config.yaml
receivers:
  - name: 'slack-sla-warnings'
    slack_configs:
      - channel: '#sla-alerts'
        api_url: 'https://hooks.slack.com/services/YOUR_WEBHOOK_URL'
```

**Configuração PagerDuty:**

```yaml
receivers:
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'YOUR_INTEGRATION_KEY'
        severity: 'critical'
```

**Routing de Alertas:**
- **Crítico (budget <20%, deadline exceeded)** → PagerDuty
- **Warning (deadline approaching, burn rate alto)** → Slack
- **Info** → Logs apenas

**Templates Customizados:**
- Template Slack com contexto rico: `monitoring/alertmanager/slack-message-template.tmpl`
- Suporte para múltiplos tipos de alerta (budget, deadline, burn rate)
- Formatação com emojis e links para dashboards

### Dashboards Grafana

#### Dashboard Principal (`fluxo-c-orquestracao`)

**Row: SLA Compliance & Alerting** (8 painéis):

| Painel | Descrição | Threshold |
|--------|-----------|-----------|
| **SLA Remaining Time** | Tempo mínimo restante de SLA | <60s vermelho, 60-300s amarelo |
| **Error Budget Status** | Percentual de budget restante | <20% vermelho, 20-50% amarelo |
| **SLA Violations (Last Hour)** | Total de violações | >0 vermelho |
| **Deadline Approaching** | Workflows críticos (últimos 15min) | >10 vermelho |
| **SLA Alerts Sent** | Taxa de alertas por tipo | - |
| **Budget Burn Rate** | Taxa de consumo (1h window) | >6 warning, >10 critical |
| **SLA Check Performance** | P95 latência de verificações | >5s alerta |
| **Alert Deduplication Rate** | % de alertas bloqueados | Monitor tendência |

**Acesso:** http://grafana/d/fluxo-c-orchestration

### Guia Completo

Documentação detalhada disponível em:

**📖 [SLA Monitoring Guide](docs/SLA_MONITORING_GUIDE.md)**

Inclui:
- Arquitetura detalhada com diagramas
- Configuração completa (SLA Management System, Redis, Kafka)
- Runbooks para alertas críticos
- Troubleshooting avançado
- Melhores práticas de SLA e capacity planning
- Exemplos de queries PromQL
- Testes de integração real

### Testes de Integração Real

Testes com serviços reais (SLA Management System, Redis, Kafka):

```bash
# Executar testes reais (requer serviços rodando)
SLA_MANAGEMENT_HOST=localhost \
REDIS_HOST=localhost:6379 \
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
pytest -m real_integration tests/integration/test_sla_real_integration.py -v

# Pular testes reais (padrão)
pytest -m "not real_integration"
```

**Cenários testados:**
- Fetch de budget do SLA Management System
- Verificação de threshold
- Detecção de deadline approaching
- Publicação de alertas ao Kafka
- Caching Redis end-to-end
- Deduplicação de alertas
- Fluxo completo de monitoramento

### Métricas Adicionais

Além das métricas listadas acima, o sistema SLA também exporta:

```promql
# Tempo restante por workflow
orchestration_sla_remaining_seconds{workflow_id="...", risk_band="..."}

# Status do budget (0=HEALTHY, 1=WARNING, 2=CRITICAL, 3=EXHAUSTED)
orchestration_sla_budget_status{service_name="orchestrator-dynamic", status="..."}

# Deadline approaching por risk band
orchestration_deadline_approaching_total

# Erros no monitor SLA por tipo
orchestration_sla_monitor_errors_total{error_type="api_error|cache_error|..."}
```

## Policy Enforcement com OPA

O Orchestrator Dynamic integra com Open Policy Agent (OPA) para enforcement de políticas de governança em tempo de execução.

### Políticas Implementadas

#### 1. Resource Limits (`neuralhive/orchestrator/resource_limits`)

Valida limites de recursos em execution tickets:
- Timeout máximo por risk_band (critical: 2h, high: 1h, medium: 30min, low: 15min)
- Número máximo de retries por risk_band (critical: 5, high: 3, medium: 2, low: 1)
- Capabilities permitidas (whitelist configurável)
- Parâmetros de recursos (CPU, memória)
- Limite de tickets concorrentes (default: 100)

#### 2. SLA Enforcement (`neuralhive/orchestrator/sla_enforcement`)

Enforce constraints de SLA:
- Deadline válido (futuro, não muito distante)
- Alinhamento QoS/risk_band (critical/high exigem EXACTLY_ONCE + STRONG)
- Alinhamento priority/risk_band
- Timeout suficiente para estimated_duration (>= 1.5x)
- Budget de SLA disponível

#### 3. Feature Flags (`neuralhive/orchestrator/feature_flags`)

Controle dinâmico de funcionalidades:
- **Intelligent Scheduler**: Habilitado para namespaces permitidos e risk_bands critical/high
- **Burst Capacity**: Habilitado para tenants premium quando carga < threshold
- **Predictive Allocation**: Habilitado para beta testing com model_accuracy > 0.85
- **Auto-scaling**: Habilitado quando queue_depth > threshold e dentro de horário comercial

### Pontos de Integração

#### C1: Validação de Plano Cognitivo

Após validação de schema, o plano completo é validado contra políticas OPA:

```python
policy_result = await policy_validator.validate_cognitive_plan(cognitive_plan)
```

Se violações forem encontradas, o workflow é rejeitado antes de gerar tickets.

#### C3: Alocação de Recursos

Antes de alocar recursos, cada ticket é validado individualmente:

```python
policy_result = await policy_validator.validate_execution_ticket(ticket)
```

Feature flags são obtidos das decisões de políticas e usados para controlar comportamento do scheduler.

### Configuração OPA

Configurar via variáveis de ambiente ou Helm values:

```yaml
config:
  opa:
    enabled: true
    host: opa.neural-hive-orchestration.svc.cluster.local
    port: 8181
    timeoutSeconds: 2
    failOpen: false  # fail-closed por padrão

    policies:
      maxConcurrentTickets: 100
      allowedCapabilities: [code_generation, deployment, testing, validation]
      resourceLimits:
        maxCpu: "4000m"
        maxMemory: "8Gi"

    featureFlags:
      intelligentSchedulerEnabled: true
      burstCapacityEnabled: true
```

### Métricas OPA

Métricas Prometheus disponíveis:
- `opa_validations_total{policy_name, result}` - Total de validações por política
- `opa_validation_duration_seconds{policy_name}` - Latência das avaliações
- `opa_policy_rejections_total{policy_name, rule, severity}` - Rejeições por regra
- `opa_policy_warnings_total{policy_name, rule}` - Avisos por regra
- `opa_evaluation_errors_total{error_type}` - Erros de avaliação ou indisponibilidade do OPA

### Troubleshooting OPA

**Erro: "OPA connection timeout"**
- Verificar se OPA server está rodando: `kubectl get pods -n neural-hive-orchestration -l app=opa`
- Verificar logs do OPA: `kubectl logs -n neural-hive-orchestration -l app=opa`

**Tickets sendo rejeitados inesperadamente**
- Verificar métricas de rejeições: `orchestration_opa_policy_rejections_total`
- Revisar políticas Rego em `policies/rego/orchestrator/`

## ML Predictions e Detecção de Anomalias

O Orchestrator Dynamic incorpora um subsistema de Machine Learning para predição inteligente de duração de tickets, estimativa de recursos e detecção de anomalias.

### Visão Geral

O sistema ML enriquece tickets com predições antes da alocação de recursos, permitindo:
- **Predição de duração**: Estimativa mais precisa do tempo de execução usando RandomForest Regression
- **Estimativa de recursos**: Cálculo dinâmico de CPU e memória necessários baseado em duração prevista
- **Detecção de anomalias**: Identificação de tickets com configurações atípicas usando Isolation Forest
- **Treinamento incremental**: Retreinamento periódico com dados históricos do MongoDB

### Componentes

#### DurationPredictor
RandomForest Regressor para predição de `actual_duration_ms` baseado em 15+ features:
- Features de risco e QoS: `risk_weight`, `qos_delivery_score`, `qos_consistency_score`
- Features de complexidade: `capabilities_count`, `task_type_encoded`, `parameters_size`
- Features históricas: `avg_duration_by_task`, `success_rate_by_task`, `std_duration_by_task`
- Features temporais: `hour_of_day`, `retry_count`

Métricas de performance: MAE, RMSE, R2, MAE% (target < 15%)

#### AnomalyDetector
Isolation Forest para detecção de tickets anômalos:
- **resource_mismatch**: Risk band baixo mas muitas capabilities
- **qos_inconsistency**: QoS incompatível com task_type
- **duration_outlier**: Duração muito diferente do histórico
- **capability_anomaly**: Número anormal de capabilities

Contamination rate: 5% (configurável)

#### ModelRegistry
Integração com MLflow para ciclo de vida de modelos:
- Versionamento automático de modelos treinados
- Promoção para Production se métricas atingirem thresholds
- Cache LRU de modelos carregados
- Experimento MLflow: `orchestrator-predictive-models`

#### TrainingPipeline
Pipeline de treinamento incremental:
- Query automática de dados históricos (MongoDB `execution_tickets`)
- Feature engineering com estatísticas agregadas
- Treinamento paralelo de ambos os modelos
- Agendamento periódico (padrão: 24h)
- Mínimo de amostras: 100 tickets completados

### Integração com Workflow C3

As predições ML são integradas na etapa **allocate_resources** (C3):

1. **Validação OPA** → políticas aplicadas
2. **ML Predictions** → ticket enriquecido com campo `predictions`:
   ```python
   {
       "duration_ms": 75230.5,           # Duração prevista
       "duration_confidence": 0.85,       # Confiança (0-1)
       "resource_estimate": {
           "cpu_m": 650,                  # Millicores
           "memory_mb": 768               # MiB
       },
       "anomaly": {
           "is_anomaly": false,
           "anomaly_score": 0.12,
           "anomaly_type": null,
           "explanation": "Ticket dentro do padrão esperado"
       }
   }
   ```
3. **Intelligent Scheduler** → ajusta prioridade se `predicted_duration > 1.5 * estimated_duration`
4. **Allocation Metadata** → inclui `predicted_duration_ms` e `anomaly_detected`

### Features Extraídas

| Feature | Tipo | Range | Descrição |
|---------|------|-------|-----------|
| `risk_weight` | float | 0.3-1.0 | Peso do risk_band (critical=1.0) |
| `qos_delivery_score` | float | 0.5-1.0 | Score de delivery_guarantee |
| `qos_consistency_score` | float | 0.85-1.0 | Score de consistency_level |
| `capabilities_count` | int | 0-n | Número de capabilities requeridas |
| `task_type_encoded` | int | 0-6 | Task type codificado (BUILD=0, ...) |
| `parameters_size` | int | 0-n | Tamanho serializado de parameters |
| `estimated_duration_ms` | float | >0 | Duração estimada do ticket |
| `sla_timeout_ms` | float | >0 | Timeout de SLA |
| `avg_duration_by_task` | float | >0 | Média histórica por task_type |
| `avg_duration_by_risk` | float | >0 | Média histórica por risk_band |
| `success_rate_by_task` | float | 0-1 | Taxa de sucesso histórica |
| `std_duration_by_task` | float | ≥0 | Desvio padrão histórico |
| `retry_count` | int | ≥0 | Número de retries do ticket |
| `hour_of_day` | int | 0-23 | Hora de criação (padrão temporal) |

### Métricas Prometheus

8 novas métricas para observabilidade do subsistema ML:

```promql
# Total de predições executadas
orchestration_ml_predictions_total{model_type="duration|anomaly", status="success|error"}

# Latência de predições (P50, P95, P99)
histogram_quantile(0.95, rate(orchestration_ml_prediction_duration_seconds_bucket[5m]))

# Erro de predição (actual - predicted)
orchestration_ml_prediction_error{model_type="duration"}

# Anomalias detectadas por tipo
orchestration_ml_anomalies_detected_total{anomaly_type="resource_mismatch|qos_inconsistency|..."}

# Erros de carregamento de modelos
orchestration_ml_model_load_errors_total{model_name="ticket-duration-predictor|ticket-anomaly-detector"}

# Duração de treinamento
orchestration_ml_training_duration_seconds{model_type="duration|anomaly"}

# Métricas de acurácia dos modelos
orchestration_ml_model_accuracy{model_name="...", metric_type="mae_pct|r2|precision|recall|f1"}

# Erros de extração de features
orchestration_ml_feature_extraction_errors_total
```

### Configuração

Variáveis de ambiente para ML Predictions:

```bash
# Habilitar/desabilitar predições ML
ML_PREDICTIONS_ENABLED=true

# MLflow Tracking Server
MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local:5000
MLFLOW_EXPERIMENT_NAME=orchestrator-predictive-models

# Parâmetros de treinamento
ML_TRAINING_WINDOW_DAYS=30               # Janela de dados históricos
ML_TRAINING_INTERVAL_HOURS=24            # Intervalo de retreinamento
ML_MIN_TRAINING_SAMPLES=100              # Mínimo de amostras
ML_DURATION_ERROR_THRESHOLD=0.15         # MAE máximo: 15%
ML_ANOMALY_CONTAMINATION=0.05            # Taxa esperada de anomalias: 5%

# Cache
ML_MODEL_CACHE_TTL_SECONDS=3600          # TTL de modelos (1h)
ML_FEATURE_CACHE_TTL_SECONDS=3600        # TTL de features (1h)
```

### Troubleshooting

**MLflow connection failed**
```bash
# Verificar MLflow disponível
kubectl port-forward -n mlflow svc/mlflow 5000:5000
curl http://localhost:5000/health

# Verificar logs do predictor
kubectl logs -n orchestrator deployment/orchestrator-dynamic | grep "ml_predictor"
```

**Insufficient training data**
- Verificar tickets no MongoDB: `db.execution_tickets.countDocuments({status: 'COMPLETED'})`
- Ajustar `ML_MIN_TRAINING_SAMPLES` se necessário
- Aguardar acúmulo de dados históricos (30 dias padrão)

**High prediction errors (MAE > 15%)**
```bash
# Verificar métricas de acurácia
kubectl port-forward -n orchestrator svc/prometheus 9090:9090
# Query: orchestration_ml_model_accuracy{metric_type="mae_pct"}

# Forçar retreinamento
kubectl exec -n orchestrator deployment/orchestrator-dynamic -- python -c "
from src.ml import TrainingPipeline
import asyncio
asyncio.run(pipeline.run_training_cycle())
"
```

**Models not being promoted**
- Verificar critérios de promoção:
  - Duration predictor: MAE% < 15%
  - Anomaly detector: Precision > 0.75
- Ajustar thresholds via `ML_DURATION_ERROR_THRESHOLD`
- Verificar logs de treinamento para métricas

**Predictions não aparecem nos tickets**
- Verificar `ML_PREDICTIONS_ENABLED=true`
- Verificar logs de inicialização do worker
- Validar MongoDB disponível (required)
- Checar métricas: `orchestration_ml_predictions_total`

### Dashboards e Alertas

**Grafana Dashboard**: `monitoring/dashboards/orchestrator-ml-predictions.json`
- Overview de predições e anomalias
- Performance de modelos (latência, acurácia)
- Distribuição de erros de predição
- Status de treinamento

**Prometheus Alerts**: `monitoring/alerts/orchestrator-ml-alerts.yaml`
- `MLPredictionHighErrorRate`: Taxa de erro > 20%
- `MLPredictionLatencyHigh`: P95 > 2s
- `MLModelLoadFailure`: Falhas ao carregar modelos
- `MLDurationPredictionInaccurate`: MAE > 15%
- `MLTrainingFailed`: Erros em treinamento
- `MLTrainingStale`: Sem treinamento > 48h

## 🤖 ML Feedback Loop

O Orchestrator Dynamic implementa um feedback loop completo para treinamento contínuo de modelos ML:

### Componentes

1. **Predições em Tempo Real:**
   - Predição de duração de tickets (RandomForest)
   - Detecção de anomalias (Isolation Forest)
   - Predição de queue time e carga de workers
2. **Priority Boosting:**
   - Tickets com `duration_ratio > 1.5`: +20% prioridade
   - Tickets com anomalia detectada: +20% prioridade
3. **Error Tracking:**
   - Calcula erro: `actual_duration_ms - predicted_duration_ms`
   - Registra em Prometheus: `ml_prediction_error`
   - Log estruturado com erro percentual
4. **Allocation Outcome Feedback:**
   - Publica outcomes no Kafka `ml.allocation_outcomes`
   - Usado para treinamento de RL policy (Q-learning)
   - Métricas de allocation quality
5. **Treinamento Offline:**
   - CronJob periódico (24h) ou por drift detection
   - Retreina modelos com dados históricos (18 meses)
   - Promove modelos para Production no MLflow

### Configuração

```yaml
ML_PREDICTIONS_ENABLED: true
ML_ALLOCATION_OUTCOMES_ENABLED: true
ML_TRAINING_WINDOW_DAYS: 540
ML_DURATION_ERROR_THRESHOLD: 0.15
```

### Métricas

- `orchestration_ml_prediction_error`: Erro de predição (Histogram)
- `orchestration_ml_model_accuracy`: Acurácia do modelo (Gauge)
- `orchestration_scheduler_allocation_quality_score`: Qualidade de alocação (Histogram)

### Documentação Detalhada

Ver `docs/ML_FEEDBACK_LOOP_ARCHITECTURE.md` para arquitetura completa.

## Schemas

### Execution Ticket (Avro)
Ver: `schemas/execution-ticket/execution-ticket.avsc`

**Campos principais**:
- `ticket_id`, `plan_id`, `intent_id`, `decision_id`
- `task_id`, `task_type`, `description`, `dependencies`
- `status`, `priority`, `risk_band`
- `sla` (deadline, timeout_ms, max_retries)
- `qos` (delivery_mode, consistency, durability)
- `created_at`, `started_at`, `completed_at`
- `retry_count`, `error_message`, `compensation_ticket_id`

## Configuração

Todas as configurações são gerenciadas via variáveis de ambiente ou arquivo `.env`:

```bash
# Temporal
TEMPORAL_HOST=temporal-frontend.temporal.svc.cluster.local
TEMPORAL_PORT=7233
TEMPORAL_NAMESPACE=neural-hive-mind
TEMPORAL_TASK_QUEUE=orchestration-tasks

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka-bootstrap.kafka.svc.cluster.local:9092
KAFKA_CONSENSUS_TOPIC=plans.consensus
KAFKA_TICKETS_TOPIC=execution.tickets
KAFKA_CONSUMER_GROUP_ID=orchestrator-dynamic

# PostgreSQL (Temporal State)
POSTGRES_HOST=postgres-temporal-headless.temporal-postgres.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_DATABASE=temporal
POSTGRES_USER=temporal
POSTGRES_PASSWORD=<secret>

# MongoDB (Auditoria)
MONGODB_URI=mongodb://mongodb-0.mongodb-headless:27017,.../?replicaSet=rs0
MONGODB_DATABASE=neural_hive_orchestration

# Redis (Cache)
REDIS_CLUSTER_NODES=redis-cluster.redis-cluster.svc.cluster.local:6379

# Service Registry
SERVICE_REGISTRY_HOST=service-registry.neural-hive-execution.svc.cluster.local
SERVICE_REGISTRY_PORT=50051
SERVICE_REGISTRY_TIMEOUT_SECONDS=3
SERVICE_REGISTRY_MAX_RESULTS=5
SERVICE_REGISTRY_CACHE_TTL_SECONDS=10

# SLA e Scheduler
ENABLE_INTELLIGENT_SCHEDULER=true
SCHEDULER_MAX_PARALLEL_TICKETS=100
SLA_DEFAULT_TIMEOUT_MS=3600000

# OPA / Policy Validation
OPA_ENABLED=true
OPA_HOST=opa.neural-hive-orchestration.svc.cluster.local
OPA_FAIL_OPEN=false
OPA_INTELLIGENT_SCHEDULER_ENABLED=true
OPA_BURST_CAPACITY_ENABLED=true

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
LOG_LEVEL=INFO
```

## Métricas Prometheus

O serviço exporta 20+ métricas em `/metrics`:

**Workflows**:
- `orchestration_workflows_started_total`
- `orchestration_workflows_completed_total`
- `orchestration_workflow_duration_seconds`
- `orchestration_workflows_active`

**Tickets**:
- `orchestration_tickets_generated_total`
- `orchestration_tickets_published_total`
- `orchestration_tickets_completed_total`
- `orchestration_ticket_generation_duration_seconds`

**SLA**:
- `orchestration_sla_violations_total`
- `orchestration_sla_remaining_seconds`
- `orchestration_deadline_approaching_total`

**Kafka**:
- `orchestration_kafka_messages_consumed_total`
- `orchestration_kafka_messages_produced_total`
- `orchestration_kafka_consumer_lag`
- `orchestration_kafka_errors_total`

**Scheduler**:
- `orchestration_scheduler_allocations_total`
- `orchestration_scheduler_allocation_duration_seconds`
- `orchestration_scheduler_workers_discovered`
- `orchestration_scheduler_discovery_failures_total`
- `orchestration_scheduler_priority_score`
- `orchestration_scheduler_cache_hits_total`

**Outros**: retries, compensations, validations, resources

## Deployment

### Via Script (Recomendado)
```bash
cd /path/to/Neural-Hive-Mind

# Deploy completo (build, push, secrets, helm)
./scripts/deploy/deploy-orchestrator-dynamic.sh

# Validação completa
./scripts/validation/validate-orchestrator-dynamic.sh
```

### Via Helm Manual
```bash
cd helm-charts/orchestrator-dynamic

# Lint
helm lint .

# Install/Upgrade
helm upgrade --install orchestrator-dynamic . \
  --namespace neural-hive-orchestration \
  --create-namespace \
  --values values.yaml \
  --set image.tag=1.0.0 \
  --wait
```

## Desenvolvimento Local

### Prerequisites
- Python 3.11+
- Docker
- Temporal CLI (opcional, para debugging)
- Kafka running
- PostgreSQL running
- MongoDB running

### Setup
```bash
cd services/orchestrator-dynamic

# Criar virtualenv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar .env
cp .env.example .env
# Editar .env com credenciais locais

# Run
python -m src.main
```

### Testes
```bash
# Unit tests
pytest tests/

# ML feedback loop
pytest tests/integration/test_ml_feedback_loop_integration.py tests/unit/test_ml_prediction_integration.py -v

# OPA integration (C1-C3)
pytest tests/test_policy_integration_c3.py tests/test_policy_integration_e2e.py -v

# Linting
black src/
flake8 src/
mypy src/

# Integration test
./tests/phase2-orchestrator-test.sh
```

## Monitoramento

### Grafana Dashboard
Ver: `docs/observability/dashboards/orchestration-flow-c.json`

**Rows**:
1. Overview (workflows started/completed, success rate)
2. Workflow Duration (P50/P95/P99)
3. Tickets (generated, published, completed)
4. SLA Tracking (violations, remaining time, compliance)
5. Retry and Compensation
6. Kafka Integration
7. Validations and Optimizations
8. Resources (CPU, Memory, Pods)
9. Logs and Traces

### Jaeger
Traces disponíveis em: `http://jaeger-query:16686`
- Filtrar por service: `orchestrator-dynamic`
- Buscar por workflow_id ou plan_id
- Visualizar correlação intent_id → plan_id → workflow_id → ticket_ids

## Troubleshooting

### Workflow não inicia
```bash
# Verificar consumer Kafka
kubectl logs -n neural-hive-orchestration -l app.kubernetes.io/name=orchestrator-dynamic | grep "Consumer"

# Verificar mensagens no tópico
kubectl exec -n kafka kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.consensus \
  --from-beginning --max-messages 10
```

### Tickets não são publicados
```bash
# Verificar logs de activities
kubectl logs -n neural-hive-orchestration -l app.kubernetes.io/name=orchestrator-dynamic | grep "publish_ticket"

# Verificar tópico execution.tickets
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic execution.tickets
```

### SLA violations altos
```bash
# Verificar métricas
curl http://<pod-ip>:9090/metrics | grep sla_violations

# Ajustar timeouts em values.yaml
helm upgrade orchestrator-dynamic . \
  --set config.sla.defaultTimeoutMs=7200000  # 2 horas
```

## Roadmap

### Fase 2.2 - QoS e Políticas (Próximo)
- [ ] Scheduler Inteligente com balanceamento de carga
- [ ] Integração OPA para validação de políticas
- [ ] Alertas automáticos para SLA violations
- [ ] Modelos preditivos para estimativa de duração

### Fase 2.3 - Integrações Avançadas
- [ ] Service Registry para discovery de Worker Agents
- [ ] Tokens efêmeros via Vault/SPIFFE
- [ ] Feromônios digitais para ajuste dinâmico
- [ ] Replay de workflows para debugging

## Referências

- [Documento 06 - Fluxos e Processos](../../documento-06-fluxos-processos-neural-hive-mind.md)
- [Orquestração - Visão Detalhada](../../docs/observability/services/orquestracao.md)
- [Execution Ticket Schema](../../schemas/execution-ticket/execution-ticket.avsc)
- [Temporal Documentation](https://docs.temporal.io/)
- [PHASE2_IMPLEMENTATION_STATUS.md](../../PHASE2_IMPLEMENTATION_STATUS.md)

---

**Mantenedores**: Neural Hive-Mind Team
**Última atualização**: 2025-10-03
**Licença**: Proprietária
