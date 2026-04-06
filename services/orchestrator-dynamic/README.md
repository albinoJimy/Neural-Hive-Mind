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

## Execution Tickets Persistence (Fail-Open vs Fail-Closed)

O Orchestrator Dynamic suporta políticas configuráveis de fail-open/fail-closed para persistência de execution tickets no MongoDB.

### Políticas de Persistência

| Coleção | Política Padrão | Rationale |
|---------|-----------------|-----------|
| `execution_tickets` | **Fail-closed** | Audit trail crítico para compliance |
| `validation_audit` | Fail-open | Não crítico para execução |
| `workflow_results` | Fail-open | Pode ser reconstruído a partir de tickets |
| `incidents` | Fail-open | Logging de incidentes não bloqueia workflow |

### Comportamento Fail-Closed (Produção)

Quando `MONGODB_FAIL_OPEN_EXECUTION_TICKETS=false` (padrão):
- Erros de persistência bloqueiam o workflow
- Temporal faz retry automático da activity
- CircuitBreakerError sempre propaga (indica problema sistêmico)
- Garante que tickets são sempre auditados antes de execução

### Comportamento Fail-Open (Desenvolvimento)

Quando `MONGODB_FAIL_OPEN_EXECUTION_TICKETS=true`:
- Erros de persistência são logados mas não bloqueiam workflow
- Métrica `mongodb_persistence_fail_open_total` é incrementada
- Ticket já publicado no Kafka continua sendo processado
- CircuitBreakerError ainda propaga (problema sistêmico não deve ser ignorado)

### Configuração via Helm

```yaml
config:
  mongodb:
    persistence:
      failOpenExecutionTickets: false  # prod/staging
      failOpenValidationAudit: true
      failOpenWorkflowResults: true
```

### Validação de Configuração

O MongoDBClient valida configuração crítica no startup:
- `mongodb_collection_tickets` deve estar definido
- Erro se a configuração estiver vazia ou None

Logs de inicialização indicam configuração carregada:
```
mongodb_client_initialized collection_tickets=execution_tickets fail_open_tickets=false
```

### Métricas de Persistência

```promql
# Taxa de erros de persistência
rate(mongodb_persistence_errors_total{collection="execution_tickets"}[5m])

# Ativações de fail-open (erros ignorados)
rate(mongodb_persistence_fail_open_total{collection="execution_tickets"}[5m])

# Validação de índices no startup
mongodb_index_validation_total{collection="execution_tickets", status="validated"}
```

### Troubleshooting de Persistência

**Tickets não persistidos (fail-closed)**
```bash
# Verificar logs de erro
kubectl logs -n neural-hive-orchestration orchestrator-dynamic-xxx | grep "execution_ticket_persist_failed"

# Verificar circuit breaker
kubectl logs -n neural-hive-orchestration orchestrator-dynamic-xxx | grep "circuit_open"
```

**Verificar tickets no MongoDB**
```bash
# Conectar ao MongoDB
kubectl exec -it mongodb-0 -n mongodb-cluster -- mongosh

# Contar tickets
use neural_hive_orchestration
db.execution_tickets.countDocuments({})

# Buscar tickets de um plan
db.execution_tickets.find({plan_id: "plan-123"})

# Verificar índices
db.execution_tickets.getIndexes()
```

**Verificar métricas Prometheus**
```bash
curl http://orchestrator-dynamic:9090/metrics | grep mongodb_persistence
```

### Índices de Execution Tickets

Índices criados automaticamente no startup:
- `ticket_id_1` (único)
- `plan_id_1`
- `intent_id_1`
- `decision_id_1`
- `status_1`
- `plan_id_1_created_at_-1` (composto)

Validação de índices logada no startup:
```
indexes_validated collection=execution_tickets count=6
```

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

### OPA Authorization Middleware (INFRA-005)

Além da validação OPA nas activities Temporal, o serviço também possui um **middleware de autorização HTTP** que protege todos os endpoints da API REST:

- **Middleware:** `OPAAuthorizationMiddleware` da biblioteca `neural_hive_opa`
- **Política:** `neuralhive/orchestrator/authz` (arquivo: `policies/rego/orchestrator/http_authz.rego`)
- **Ordem:** CORS → OPA Authorization → RateLimit → Metrics
- **Comportamento:** Fail-closed por padrão (retorna HTTP 503 se OPA indisponível)

#### Headers de Autenticação

O middleware extrai contexto de autenticação dos seguintes headers:

| Header | Descrição | Exemplo |
|--------|-----------|---------|
| `X-User-ID` | ID do usuário | `user-123` |
| `X-Tenant-ID` | ID do tenant | `tenant-abc` |
| `X-User-Role` | Role do usuário | `admin`, `developer`, `worker`, `service-registry` |

#### Paths Públicos

Os seguintes paths **não requerem autenticação**:
- `/health`, `/healthz`, `/ready` - Health checks
- `/metrics` - Métricas Prometheus
- `/docs`, `/redoc`, `/openapi.json` - Documentação API
- `/static/*`, `/favicon.ico` - Assets estáticos

#### Regras de Autorização

- **`admin`** - Acesso total a todos os endpoints
- **`developer`** - Acesso leitura (`GET`) em APIs
- **`worker`** - Acesso a `/api/v1/workers/*` para registro/status
- **`service-registry`** - Pode registrar/desregistrar workers
- **Usuários autenticados** - Podem acessar recursos do próprio tenant (tenant isolation)

#### Configuração

```bash
# Habilitar middleware (default: true)
ENABLE_OPA_AUTHORIZATION=true

# Política HTTP
OPA_AUTHORIZATION_POLICY_PATH=neuralhive/orchestrator/authz

# Comportamento fail-closed (default: false)
OPA_FAIL_OPEN=false

# Headers (configurável)
OPA_USER_ID_HEADER=X-User-ID
OPA_TENANT_ID_HEADER=X-Tenant-ID
OPA_ROLE_HEADER=X-User-Role
```

#### Métricas

- `opa_middleware_decisions_total{decision="allow|deny"}` - Decisões por resultado
- `opa_middleware_latency_seconds` - Latência de consulta OPA
- `opa_middleware_cache_hits_total` - Cache hits
- `opa_middleware_circuit_breaker_open` - Estado do circuit breaker
- `opa_middleware_opa_unavailable_total` - Falhas de conexão OPA

#### Testes

```bash
# Testes de integração do middleware
pytest services/orchestrator-dynamic/tests/integration/test_opa_middleware_integration.py -v

# Testes OPA da política HTTP
opa test policies/rego/orchestrator/http_authz.rego \
  policies/rego/orchestrator/tests/http_authz_test.rego
```

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

## Task Preemption

O Orchestrator Dynamic suporta preempção de tarefas de baixa prioridade para liberar recursos para tickets de alta prioridade. Esta funcionalidade é desabilitada por padrão e pode ser habilitada via configuração.

### Visão Geral

Quando um ticket de alta prioridade (HIGH/CRITICAL) não encontra workers disponíveis, o scheduler pode preemptar tarefas de baixa prioridade (LOW/MEDIUM) em execução, liberando recursos para o ticket mais crítico.

```
HIGH Priority Ticket → No Workers Available → Find Preemptable Tasks → Send Cancel Signal → Free Worker → Allocate
                                                        ↓
                                              Worker Agent receives cancel
                                              • Save checkpoint to Redis
                                              • Graceful shutdown
                                              • Mark as PREEMPTED
```

### Configuração

```yaml
# Helm values (helm-charts/orchestrator-dynamic/values.yaml)
scheduler:
  enablePreemption: false  # Feature flag (disabled by default)
  preemption:
    minPreemptorPriority: HIGH       # Minimum priority to preempt
    maxPreemptablePriority: LOW      # Maximum priority that can be preempted
    gracePeriodSeconds: 30           # Grace period for checkpointing
    maxConcurrentPreemptions: 5      # Limit concurrent preemptions
    workerCooldownSeconds: 60        # Cooldown after preemption
    retryPreemptedTasks: true        # Retry preempted tasks
    retryDelaySeconds: 300           # Delay before retrying
```

```bash
# Environment variables
SCHEDULER_ENABLE_PREEMPTION="false"
SCHEDULER_PREEMPTION_MIN_PREEMPTOR_PRIORITY="HIGH"
SCHEDULER_PREEMPTION_MAX_PREEMPTABLE_PRIORITY="LOW"
SCHEDULER_PREEMPTION_GRACE_PERIOD_SECONDS="30"
SCHEDULER_PREEMPTION_MAX_CONCURRENT="5"
SCHEDULER_PREEMPTION_WORKER_COOLDOWN_SECONDS="60"
```

### Priority Mapping

| Preemptor Priority | Can Preempt |
|--------------------|-------------|
| CRITICAL           | LOW, MEDIUM |
| HIGH               | LOW         |
| MEDIUM             | (none)      |
| LOW                | (none)      |

> **Note:** The default configuration only allows HIGH+ to preempt LOW. Adjust `maxPreemptablePriority` to extend preemption scope.

### How It Works

1. **Detection**: When `schedule_ticket()` finds no available workers for a HIGH/CRITICAL ticket
2. **Discovery**: `_find_preemptable_tasks()` queries workers with running LOW priority tasks
3. **Selection**: Tasks sorted by priority (lowest first), then progress (lowest first - less work lost)
4. **Preemption**: HTTP POST to `worker:8080/api/v1/tasks/{ticket_id}/cancel`
5. **Checkpoint**: Worker saves state to Redis before terminating
6. **Cooldown**: Worker enters cooldown period to prevent thrashing
7. **Retry**: Preempted task can be automatically retried after delay

### Worker Agent Endpoint

```http
POST /api/v1/tasks/{ticket_id}/cancel
Content-Type: application/json
Authorization: Bearer <SPIFFE JWT>

{
  "reason": "preemption",
  "preempted_by": "high-priority-ticket-id",
  "grace_period_seconds": 30
}
```

**Response:**
```json
{
  "success": true,
  "ticket_id": "preempted-ticket-id",
  "reason": "preemption",
  "checkpoint_saved": true,
  "checkpoint_key": "checkpoint:preempted-ticket-id"
}
```

### Métricas

**Orchestrator Dynamic:**
- `orchestration_tasks_preempted_total{preempted_priority, preemptor_priority}`: Tasks preempted
- `orchestration_preemption_attempts_total{success, reason}`: Preemption attempts
- `orchestration_preemption_failures_total{reason}`: Failures (timeout, rejected, error)
- `orchestration_preemption_duration_seconds`: Preemption latency histogram
- `orchestration_active_preemptions`: Current active preemptions gauge
- `orchestration_preempted_tasks_retried_total`: Preempted tasks retried

**Worker Agents:**
- `worker_agent_tasks_cancelled_total{reason}`: Tasks cancelled by reason
- `worker_agent_tasks_preempted_total`: Tasks preempted
- `worker_agent_checkpoint_saves_total{success}`: Checkpoint operations
- `worker_agent_graceful_cancellation_duration_seconds`: Cancellation duration

### Alertas

Alertas definidos em `monitoring/alerts/flow-c-preemption-alerts.yaml`:

| Alert | Severity | Condition |
|-------|----------|-----------|
| `HighPreemptionFailureRate` | warning | >30% failure rate over 5m |
| `HighConcurrentPreemptions` | warning | >10 concurrent preemptions |
| `PreemptionTimeoutRate` | warning | >10% timeout rate |
| `SlowPreemptionDuration` | warning | P95 > 30s |
| `HighCheckpointFailureRate` | warning | >20% checkpoint failures |
| `HighPriorityResourceStarvation` | critical | Rejections despite preemption |

### Best Practices

1. **Start Disabled**: Enable preemption only when resource contention is a real problem
2. **Conservative Thresholds**: Start with HIGH→LOW only, expand gradually
3. **Monitor Carefully**: Watch preemption metrics before production rollout
4. **Checkpoint Design**: Ensure tasks can resume from checkpoints
5. **Cooldown Tuning**: Adjust cooldown to prevent worker thrashing
6. **Test Thoroughly**: Test preemption in staging before production

### Troubleshooting

**Preemption Not Working:**
- Verify `enablePreemption: true` in config
- Check priority levels match configuration
- Confirm workers are reachable via HTTP

**High Failure Rate:**
- Check worker agent logs for connectivity issues
- Verify SPIFFE authentication is working
- Increase grace period if checkpoints timeout

**Workers Being Preempted Too Often:**
- Increase `workerCooldownSeconds`
- Reduce `maxConcurrentPreemptions`
- Consider scaling worker agents instead

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

## Configuração de SLA Timeouts

O Orchestrator Dynamic calcula timeouts de SLA para cada execution ticket usando a seguinte fórmula:

```
timeout_ms = max(min_timeout_ms, estimated_duration_ms * buffer_multiplier)
```

### Parâmetros Configuráveis

| Parâmetro | Variável de Ambiente | Valor Padrão | Descrição |
|-----------|---------------------|--------------|-----------|
| **Timeout Mínimo** | `SLA_TICKET_MIN_TIMEOUT_MS` | `60000` (60s) | Timeout mínimo absoluto para qualquer ticket |
| **Multiplicador de Buffer** | `SLA_TICKET_TIMEOUT_BUFFER_MULTIPLIER` | `3.0` | Multiplicador aplicado à duração estimada |

### Rationale dos Valores Padrão

**Histórico de Mudanças:**
- **v1.0.0**: `min=30s`, `buffer=1.5x` → Resultou em 100% de falsos positivos
- **v1.0.9**: `min=60s`, `buffer=3.0x` → Baseado em análise de logs de produção

**Por que 60s mínimo?**
- Acomoda overhead de inicialização de workers (~10-15s)
- Acomoda latência de rede e scheduling (~5-10s)
- Margem para variabilidade de recursos (~10-20s)

**Por que 3.0x buffer?**
- Acomoda variabilidade de carga (workers podem estar ocupados)
- Acomoda variabilidade de recursos (CPU/memória disponível)
- Reduz falsos positivos de SLA violation

### Exemplos de Cálculo

| Duração Estimada | Cálculo | Timeout Final | Observação |
|------------------|---------|---------------|------------|
| 1ms | `max(60000, 1 * 3.0)` | **60000ms** (60s) | Usa mínimo |
| 10s (10000ms) | `max(60000, 10000 * 3.0)` | **60000ms** (60s) | Usa mínimo |
| 20s (20000ms) | `max(60000, 20000 * 3.0)` | **60000ms** (60s) | Threshold |
| 30s (30000ms) | `max(60000, 30000 * 3.0)` | **90000ms** (90s) | Usa multiplicador |
| 60s (60000ms) | `max(60000, 60000 * 3.0)` | **180000ms** (3min) | Usa multiplicador |
| 10min (600000ms) | `max(60000, 600000 * 3.0)` | **1800000ms** (30min) | Usa multiplicador |

### Validação

Para validar a configuração antes do deploy:

```bash
# Executar script de validação
python services/orchestrator-dynamic/scripts/validate_sla_config.py

# Verificar logs durante execução
kubectl logs -n neural-hive-orchestration deployment/orchestrator-dynamic | grep sla_timeout_calculated
```

### Troubleshooting de SLA Timeout

**Problema: Muitos falsos positivos de SLA violation**

Sintomas:
- Logs mostram `remaining_seconds` negativo antes de workflow completar
- Métricas `sla_violations_total` aumentando sem falhas reais

Solução:
1. Aumentar `SLA_TICKET_MIN_TIMEOUT_MS` para 90000 (90s)
2. Aumentar `SLA_TICKET_TIMEOUT_BUFFER_MULTIPLIER` para 4.0
3. Revalidar com script de validação

**Problema: Timeouts muito longos**

Sintomas:
- Tickets com duração curta têm timeouts excessivos
- SLA violations reais não são detectadas a tempo

Solução:
1. Reduzir `SLA_TICKET_TIMEOUT_BUFFER_MULTIPLIER` para 2.5
2. Manter `SLA_TICKET_MIN_TIMEOUT_MS` em 60000
3. Monitorar métricas de SLA por 24h

### Métricas de Timeout

```promql
# Distribuição de timeouts calculados
histogram_quantile(0.95, rate(neural_hive_orchestrator_ticket_timeout_ms_bucket[5m]))

# Taxa de SLA violations
rate(neural_hive_orchestrator_sla_violations_total[5m])

# Tickets com timeout mínimo vs multiplicador
sum(rate(neural_hive_orchestrator_tickets_generated_total{timeout_source="minimum"}[5m]))
sum(rate(neural_hive_orchestrator_tickets_generated_total{timeout_source="multiplier"}[5m]))
```

## API Endpoints

### Workflow Start (`POST /api/v1/workflows/start`)

Inicia um workflow Temporal para execução de plano cognitivo (Fluxo C).

Este endpoint é chamado pelo `FlowCOrchestrator` via `OrchestratorClient` para iniciar a orquestração de execução adaptativa.

**Request:**
```json
{
    "cognitive_plan": {
        "plan_id": "plan-456",
        "intent_id": "intent-789",
        "decision_id": "decision-123",
        "tasks": [...]
    },
    "correlation_id": "corr-abc-123",
    "priority": 7,
    "sla_deadline_seconds": 14400
}
```

**Campos:**

| Campo | Tipo | Obrigatório | Default | Descrição |
|-------|------|-------------|---------|-----------|
| `cognitive_plan` | object | Sim | - | Plano cognitivo a ser executado (contém plan_id, intent_id, tasks) |
| `correlation_id` | string | Sim | - | ID de correlação para rastreabilidade end-to-end |
| `priority` | integer | Não | 5 | Prioridade do workflow (1-10, onde 10 é mais alta) |
| `sla_deadline_seconds` | integer | Não | 14400 | Deadline SLA em segundos (default: 4 horas) |

**Response (200 OK):**
```json
{
    "workflow_id": "nhm-flow-c-corr-abc-123",
    "status": "started",
    "correlation_id": "corr-abc-123"
}
```

**Códigos de Status:**
- `200`: Workflow iniciado com sucesso
- `422`: Erro de validação (campos obrigatórios ausentes ou inválidos)
- `503`: Temporal client não disponível (serviço em modo degradado)
- `500`: Erro ao iniciar workflow (erro interno do Temporal)

**Comportamento:**

1. **Geração de workflow_id**: Formato `{prefix}flow-c-{correlation_id}` onde `prefix` é configurável via `TEMPORAL_WORKFLOW_ID_PREFIX`
2. **Fallback de decision_id**: Se `cognitive_plan.decision_id` não existir, usa `correlation_id` como fallback
3. **Validação de Temporal**: Retorna 503 se Temporal client não estiver disponível (fail-fast)
4. **Logging estruturado**: Todos os eventos são logados com contexto completo (workflow_id, plan_id, correlation_id)

**Exemplo curl:**
```bash
curl -X POST http://orchestrator-dynamic:8000/api/v1/workflows/start \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: corr-abc-123" \
  -d '{
    "cognitive_plan": {
      "plan_id": "plan-456",
      "intent_id": "intent-789",
      "tasks": []
    },
    "correlation_id": "corr-abc-123",
    "priority": 7
  }'
```

**Integração com FlowCOrchestrator:**

Este endpoint é chamado automaticamente pelo `FlowCOrchestrator` (biblioteca `neural_hive_integration`) via `OrchestratorClient.start_workflow()`:

```python
from neural_hive_integration.clients import OrchestratorClient

client = OrchestratorClient(base_url="http://orchestrator-dynamic:8000")
response = await client.start_workflow(
    cognitive_plan={...},
    correlation_id="corr-123",
    priority=7
)
```

**Observabilidade:**

- **Logs**: `workflow_start_attempt`, `workflow_started`, `workflow_start_failed`, `workflow_start_rejected`

### Workflow Query (`POST /api/v1/workflows/{workflow_id}/query`)

Executa queries no workflow Temporal para consultar estado em tempo real.

**Request:**
```json
{
    "query_name": "get_tickets",
    "args": []
}
```

**Response (200 OK):**
```json
{
    "workflow_id": "nhm-flow-c-corr-123",
    "query_name": "get_tickets",
    "result": {
        "tickets": [
            {
                "ticket_id": "ticket-001",
                "plan_id": "plan-456",
                "task_id": "task-1",
                "task_type": "BUILD",
                "status": "PENDING"
            }
        ]
    }
}
```

**Queries disponíveis:**

| Query | Descrição |
|-------|-----------|
| `get_tickets` | Lista tickets gerados pelo workflow |
| `get_status` | Status atual do workflow (status, tickets_generated, sla_warnings) |

**Códigos de Status:**
- `200`: Query executada com sucesso
- `404`: Workflow não encontrado
- `503`: Temporal client não disponível
- `500`: Erro ao executar query

**Caching:** Queries de `get_tickets` são cacheadas no Redis (TTL: 5min) para reduzir carga no Temporal.

**Exemplo curl:**
```bash
curl -X POST http://orchestrator-dynamic:8000/api/v1/workflows/nhm-flow-c-corr-123/query \
  -H "Content-Type: application/json" \
  -d '{"query_name": "get_tickets"}'
```

### GET /api/v1/tickets/{ticket_id}

Consulta um ticket de execução por ID.

**Resposta de Sucesso (200):**
```json
{
  "ticket_id": "ticket-uuid-123",
  "plan_id": "plan-uuid-456",
  "intent_id": "intent-uuid-789",
  "task_id": "task-001",
  "task_type": "BUILD",
  "description": "Compilar aplicação",
  "status": "COMPLETED",
  "priority": 7,
  "risk_band": "LOW",
  "created_at": 1704067200000,
  "started_at": 1704067205000,
  "completed_at": 1704067250000,
  "cached": false
}
```

**Códigos de Status:**
- `200`: Ticket encontrado
- `404`: Ticket não encontrado
- `503`: MongoDB não disponível
- `500`: Erro interno

**Caching:** Respostas são cacheadas no Redis (TTL: 5min).

**Exemplo curl:**
```bash
curl http://orchestrator-dynamic:8000/api/v1/tickets/ticket-uuid-123
```

### GET /api/v1/tickets/by-plan/{plan_id}

Lista todos os tickets de um plano cognitivo com suporte a filtros e paginação.

**Parâmetros de Query:**
| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `status` | string | - | Filtra por status (PENDING, RUNNING, COMPLETED, FAILED, REJECTED, COMPENSATING, COMPENSATED) |
| `limit` | int | 100 | Máximo de resultados (max: 500) |
| `offset` | int | 0 | Offset para paginação |

**Resposta de Sucesso (200):**
```json
{
  "tickets": [
    {
      "ticket_id": "ticket-1",
      "plan_id": "plan-123",
      "status": "COMPLETED",
      "task_type": "BUILD",
      "created_at": 1704067200000
    },
    {
      "ticket_id": "ticket-2",
      "plan_id": "plan-123",
      "status": "RUNNING",
      "task_type": "TEST",
      "created_at": 1704067210000
    }
  ],
  "total": 15,
  "limit": 100,
  "offset": 0,
  "has_more": false,
  "cached": false
}
```

**Códigos de Status:**
- `200`: Lista retornada (pode ser vazia)
- `400`: Parâmetros inválidos (limit > 500, offset negativo, status inválido)
- `503`: MongoDB não disponível
- `500`: Erro interno

**Caching:** Respostas são cacheadas no Redis (TTL: 2min) com chave baseada em filtros.

**Exemplo curl:**
```bash
# Listar todos os tickets de um plano
curl "http://orchestrator-dynamic:8000/api/v1/tickets/by-plan/plan-uuid-123"

# Filtrar por status com paginação
curl "http://orchestrator-dynamic:8000/api/v1/tickets/by-plan/plan-uuid-123?status=RUNNING&limit=50&offset=0"
```

### GET /api/v1/workflows/{workflow_id}

Consulta o status de um workflow Temporal via describe.

**Resposta de Sucesso (200):**
```json
{
  "workflow_id": "nhm-flow-c-corr-123",
  "status": "RUNNING",
  "workflow_type": "OrchestrationWorkflow",
  "task_queue": "orchestration-tasks",
  "start_time": "2025-01-20T10:30:00Z",
  "close_time": null,
  "execution_time": null,
  "cached": false
}
```

**Status Possíveis:**
- `RUNNING`: Workflow em execução
- `COMPLETED`: Workflow finalizado com sucesso
- `FAILED`: Workflow falhou
- `CANCELED`: Workflow cancelado
- `TERMINATED`: Workflow terminado externamente
- `CONTINUED_AS_NEW`: Workflow continuado como nova execução
- `TIMED_OUT`: Workflow expirou por timeout

**Códigos de Status:**
- `200`: Workflow encontrado
- `404`: Workflow não encontrado
- `503`: Temporal client não disponível (serviço em modo degradado)
- `500`: Erro ao consultar workflow

**Caching:** Respostas são cacheadas no Redis (TTL: 5min) para workflows em estados terminais.

**Exemplo curl:**
```bash
curl http://orchestrator-dynamic:8000/api/v1/workflows/nhm-flow-c-corr-123
```

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

### SLA Alerts Integration (INFRA-006)

O Orchestrator Dynamic possui integração com sistemas de notificação externa para alertas SLA críticos, permitindo resposta rápida a violações e situações de emergência.

#### Componentes

##### SLAAlertConsumer (`src/consumers/sla_alert_consumer.py`)

Consumer Kafka que processa alertas SLA vindos do `sla-management-system` e despacha notificações:

- **Tópicos Kafka:** `sla.alerts`, `sla.violations`
- **Canais de Notificação:**
  - **Slack**: Mensagens formatadas com blocos estruturados
  - **PagerDuty**: Alertas via Events API v2 para CRITICAL/EMERGENCY
- **Roteamento por Severidade:**
  - `CRITICAL` → PagerDuty + Slack (`#sla-alerts-critical`)
  - `EMERGENCY` → PagerDuty + Slack (`#sla-alerts`)
  - `WARNING/INFO/DEBUG` → Slack apenas (`#sla-alerts`)

##### SlackClient (`src/clients/slack_client.py`)

Cliente para envio de mensagens via Incoming Webhooks:

- **Retry automático:** 3 tentativas com exponential backoff
- **Formatação:** Suporte a texto e blocos estruturados
- **Configuração:** `SLACK_WEBHOOK_URL`

##### PagerDutyClient (`src/clients/pagerduty_client.py`)

Cliente para Events API v2 do PagerDuty:

- **Operações:** trigger, acknowledge, resolve
- **Deduplication:** via `dedup_key` (usa `alert_id`)
- **Retry automático:** 3 tentativas com exponential backoff
- **Configuração:** `PAGERDUTY_ROUTING_KEY`

#### Configuração

```yaml
# Habilitar consumer de alertas SLA
sla_alerts_enabled: true

# Tópicos Kafka
sla_alerts_topics:
  - sla.alerts
  - sla.violations
sla_alerts_consumer_group: orchestrator-sla-alerts

# Slack
slack_webhook_url: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
slack_alerts_channel: "#sla-alerts"
slack_critical_channel: "#sla-alerts-critical"

# PagerDuty
pagerduty_routing_key: "YOUR_INTEGRATION_KEY"
pagerduty_api_url: "https://events.pagerduty.com/v2/enqueue"
```

#### Formato dos Alertas

##### Estrutura da Mensagem Kafka

```json
{
  "alert_id": "alert-123",
  "title": "Workflow Timeout Exceeded",
  "severity": "CRITICAL",
  "alert_type": "workflow_timeout",
  "workflow_id": "wf-456",
  "service_name": "orchestrator-dynamic",
  "timestamp": "2026-04-06T10:00:00Z",
  "details": {
    "timeout_ms": 3600000,
    "elapsed_ms": 3800000
  }
}
```

##### Formatação Slack

Alertas críticos incluem:
- Header com ícone de alerta
- Seções com título, severidade, workflow ID, serviço
- Botão de ação para Grafana

Alertas de warning incluem:
- Header amarelo
- Título e tipo do alerta

#### Métricas Prometheus

```promql
# Taxa de notificações enviadas por canal
rate(orchestration_sla_notification_sent_total{channel="slack"}[5m])
rate(orchestration_sla_notification_sent_total{channel="pagerduty"}[5m])

# Taxa de falhas por canal
rate(orchestration_sla_notification_failed_total{channel="slack"}[5m])

# Duração do envio (P95)
histogram_quantile(0.95, rate(orchestration_sla_notification_duration_seconds_bucket[5m]))
```

#### Troubleshooting

##### Alertas não chegam no Slack
```bash
# Verificar se consumer está rodando
kubectl logs -n neural-hive-orchestration -l app.kubernetes.io/name=orchestrator-dynamic | grep "sla_alert_consumer"

# Verificar configuração do webhook
kubectl get secret orchestrator-dynamic-config -o jsonpath='{.data.SLACK_WEBHOOK_URL}' | base64 -d

# Testar webhook manualmente
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text": "Test message from orchestrator-dynamic"}'
```

##### Alertas não chegam no PagerDuty
```bash
# Verificar routing key
kubectl get secret orchestrator-dynamic-config -o jsonpath='{.data.PAGERDUTY_ROUTING_KEY}' | base64 -d

# Verificar métricas de envio
curl http://<pod-ip>:9090/metrics | grep sla_notification
```

#### Testes

- **Unitários:** `pytest tests/unit/test_sla_alert_consumer.py`
- **Integração:** `pytest tests/integration/test_sla_alerts_integration.py`

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
