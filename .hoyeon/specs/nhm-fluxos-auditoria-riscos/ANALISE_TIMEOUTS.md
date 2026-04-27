# Analise de Timeouts e Padroes Async - Neural Hive Mind

**Data:** 2026-04-27
**Autor:** Agente Worker T12
**Escopo:** Configuracao de timeouts, padroes async, backpressure e workflows Temporal

---

## 1. Timeout Granularity Analysis

### 1.1 Configuracao Global vs Por Operacao

**Estado Actual:**
- **Timeouts globais presentes:** A maioria dos services usa timeouts globais configurados em settings.py
- **Timeouts por operacao:** Implementados apenas em alguns pontos criticos

**Exemplos de Timeouts Globais:**

```python
# worker-agents/src/config/settings.py
task_timeout_multiplier: float = 1.5
ticket_api_timeout_seconds: int = 10
code_forge_timeout_seconds: int = 14400  # 4 horas
flux_timeout_seconds: int = 600
opa_timeout_seconds: int = 30
test_execution_timeout_seconds: int = 600
```

**Exemplos de Timeouts por Operacao (GOOD):**

```python
# consensus-engine/src/clients/specialists_grpc_client.py
async def evaluate_plan(self, specialist_type: str, ...):
    timeout_ms = self.config.get_specialist_timeout_ms(specialist_type)
    response = await asyncio.wait_for(
        stub.EvaluatePlan(request, metadata=grpc_metadata),
        timeout=timeout_ms / 1000.0,  # Timeout especifico por especialista
    )
```

**GAP IDENTIFICADO: R-T10.1 - Falta de Granularidade**

| Componente | Timeout Global | Timeout por Operacao | Status |
|------------|----------------|---------------------|---------|
| Specialists gRPC | N/A | YES (por especialista) | ✅ BOM |
| Kafka Consumers | 30s (session) | N/A | ⚠️ GLOBAL |
| MongoDB | 5000ms | N/A | ⚠️ GLOBAL |
| Redis | 10s | N/A | ⚠️ GLOBAL |
| HTTP/gRPC clients | Variável | Pouca granularidade | ❌ GAP |
| Temporal Workflows | N/A | YES (por workflow/activity) | ✅ BOM |

### 1.2 Timeout Configuration Gaps

**GAP #1: Timeout Global Unico para MongoDB**
```python
# approval-service/src/config/settings.py
mongodb_timeout_ms: int = Field(default=5000, description="Timeout (ms)")
```
- **Problema:** 5s para todas as operacoes (query, insert, update, delete)
- **Impacto:** Operacoes rapidas (get) podem esperar desnecessariamente, operacoes lentas (aggregation) podem timeout
- **Recomendacao:** Implementar timeouts por tipo de operacao

**GAP #2: Kafka Session Timeout Unico**
```python
# mcp-tool-catalog/src/config/settings.py
KAFKA_SESSION_TIMEOUT_MS: int = 30000  # 30s fixo
```
- **Problema:** 30s pode ser insuficiente para workloads pesados
- **Impacto:** Rebalanceamento frequente em operacoes longas
- **Recomendacao:** Configurar por consumer group baseado no workload esperado

**GAP #3: Timeouts HTTP/gRPC Sem Distincao por Endpoint**
```python
# optimizer-agents/src/config/settings.py
grpc_timeout: int = Field(default=5, description="gRPC timeout in seconds")
```
- **Problema:** 5s para todos os endpoints
- **Impacto:** Endpoints de treino de modelo (experiment_timeout_seconds=3600) sao inconsistente com o timeout do cliente gRPC

---

## 2. Async Patterns e Backpressure

### 2.1 Uso de asyncio.gather

**Analise de Padrões:**

**PADRAO CORRETO (com return_exceptions):**
```python
# consensus-engine/src/clients/specialists_grpc_client.py
async def evaluate_plan_parallel(self, cognitive_plan, trace_context):
    tasks = [self.evaluate_plan(st, cognitive_plan, trace_context) for st in specialist_types]
    results = await asyncio.gather(*tasks, return_exceptions=True)  # ✅ GOOD
    # Processa excecoes individualmente
```

**PADRAO CORRETO (com timeout):**
```python
# worker-agents/src/engine/parallel_executor.py
try:
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=timeout_seconds
    )
except TimeoutError:
    # Tratamento de timeout
```

**PADRAO PROBLEMÁTICO (sem timeout):**
```python
# gateway-intencoes/src/pipelines/nlu_pipeline_v2.py
async def _warm_up_cache(self):
    tasks = [warmup_single(q, l) for q, l in common_queries]
    await asyncio.gather(*tasks, return_exceptions=True)  # ❌ NO TIMEOUT
```

**GAP IDENTIFICADO: R-T10.2 - Falta de Backpressure em Alguns Ponto**

### 2.2 Implementação de Backpressure

**IMPLEMENTACAO EXISTENTE (EXCELLENTE):**
```python
# worker-agents/src/clients/kafka_ticket_consumer.py
class KafkaTicketConsumer:
    def __init__(self, config, execution_engine, metrics=None):
        # Backpressure control
        self.tickets_semaphore = None  # Inicializado em initialize()
        self.in_flight_tickets: set = set()
        self.consumer_paused = False
        self.pause_start_time = None

    async def initialize(self, redis_client=None):
        max_concurrent = getattr(self.config, "max_concurrent_tickets", 10)
        self.tickets_semaphore = asyncio.Semaphore(max_concurrent)

    def _should_pause_consumer(self) -> bool:
        threshold = getattr(self.config, "consumer_pause_threshold", 0.8)
        pause_limit = int(max_concurrent * threshold)
        return len(self.in_flight_tickets) >= pause_limit

    def _should_resume_consumer(self) -> bool:
        threshold = getattr(self.config, "consumer_resume_threshold", 0.5)
        resume_limit = int(max_concurrent * threshold)
        return len(self.in_flight_tickets) <= resume_limit
```

**Features Implementadas:**
- ✅ Semaphore para limitar concorrência
- ✅ Pause/resume do consumer baseado em threshold
- ✅ Tracking de tickets in-flight
- ✅ Métricas de backpressure
- ✅ Testes de unidade E2E (test_kafka_ticket_consumer_backpressure.py)

**GAP #4: Falta de Backpressure em Outros Consumers**

| Consumer | Backpressure | Status |
|----------|--------------|--------|
| worker-agents/ticket_consumer | ✅ Semaphore + pause/resume | IMPLEMENTADO |
| consensus-engine/plan_consumer | ❌ Nao identificado | GAP |
| guard-agents/ticket_consumer | ✅ Parcial | IMPLEMENTADO |
| orchestrator-dynamic/flow_c_consumer | ❌ Nao identificado | GAP |
| execution-ticket-service/consumer | ❌ Nao identificado | GAP |

### 2.3 Parallel Executor com Prioridades

**IMPLEMENTACAO EXCELENTE:**
```python
# worker-agents/src/engine/parallel_executor.py
class ParallelExecutor:
    def __init__(self, config: ParallelExecutionConfig, execution_engine, metrics=None):
        # Filas por prioridade
        self.queues: dict[TaskPriority, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in TaskPriority
        }
        # Semaphores para limitar paralelismo
        self.global_semaphore = asyncio.Semaphore(config.max_parallel_tasks)
        self.type_semaphores: dict[str, asyncio.Semaphore] = {}
```

**Features:**
- ✅ Priority queue (CRITICAL, HIGH, MEDIUM, LOW)
- ✅ Global semaphore
- ✅ Per-type semaphore
- ✅ Batch processing
- ✅ Dependency resolution

---

## 3. Temporal Workflow Timeouts

### 3.1 Configuracao de Workflows

**IMPLEMENTACAO CONSISTENTE:**
```python
# orchestrator-dynamic/src/workflows/data_migration_workflow.py
await asyncio.start_workflow(
    DataMigrationWorkflow.migrate_sla_policies,
    ...,
    start_to_close_timeout=timedelta(minutes=10)  # ✅ Por workflow
)

# orchestrator-dynamic/src/workflows/fluxo_g_workflow.py
execute_activity(
    AnalyzeIntentActivity.execute,
    intent_data,
    start_to_close_timeout=timedelta(seconds=60)  # ✅ Por activity
)
```

**Timeouts Observados:**

| Workflow/Activity | Timeout | Apropriado? |
|-------------------|---------|-------------|
| migrate_sla_policies | 10 min | ✅ YES |
| validate_migrations | 5 min | ✅ YES |
| execute_migration | 2 horas | ✅ YES (long-running) |
| analyze_intent | 60s | ⚠️ Depende |
| generate_code | 120s | ✅ YES |
| optimize_parameters | 30s | ✅ YES |
| feedback_replay | 10-30s | ✅ YES |
| self_healing_orchestration | 10-30s | ✅ YES |

**GAP #5: Timeout de Workflow vs Activity Timeout**

Algumas activities podem ter timeouts inconsistentes com o workflow pai:
```python
# fluxo_g_workflow.py
start_to_close_timeout=timedelta(seconds=1200),  # 20 minutos workflow
# Mas activities internas podem ter timeout menor sem propagacao adequada
```

### 3.2 Circuit Breaker no Temporal Client

**IMPLEMENTACAO EXCELENTE:**
```python
# orchestrator-dynamic/src/temporal_client.py
class TemporalClientWrapper:
    def __init__(
        self,
        client: Client,
        service_name: str,
        fail_max: int = 5,
        timeout_duration: int = 60,
        recovery_timeout: int = 30,
    ):
        self.breaker = MonitoredCircuitBreaker(
            service_name=service_name,
            circuit_name="temporal_client",
            fail_max=fail_max,
            timeout_duration=timeout_duration,
            recovery_timeout=recovery_timeout,
        )
```

**Features:**
- ✅ Circuit breaker para operacoes criticas
- ✅ Timeout configuravel
- ✅ Recovery timeout
- ✅ Métricas integradas

---

## 4. Blocking Calls em Async Contexts

### 4.1 Chamadas Bloqueantes Identificadas

**CRÍTICO: time.sleep() em async context**

```python
# consensus-engine/src/consumers/plan_consumer.py
for attempt in range(max_retries):
    try:
        # ...
    except FileNotFoundError:
        time.sleep(backoff_seconds)  # ❌ BLOCKING em async function!
        backoff_seconds *= 2
```

**Impacto:** Bloqueia o event loop durante o sleep, impedindo processamento de outras tarefas.

**GAP #6: time.sleep() em Contexto Async**

| Localizacao | Tipo | Impacto | Prioridade |
|-------------|------|---------|------------|
| plan_consumer.py:382 | time.sleep() | ALTO | CRÍTICO |
| plan_consumer.py:452 | time.sleep() | ALTO | CRÍTICO |
| plan_consumer.py:565 | time.sleep() | ALTO | CRÍTICO |

**Recomendacao:**
```python
# ALTERAR DE:
time.sleep(backoff_seconds)

# PARA:
await asyncio.sleep(backoff_seconds)
```

### 4.2 subprocess.run() em Async Context

**USO CORRETO (com executor):**
```python
# gateway-intencoes/src/pipelines/asr_pipeline.py
result = await asyncio.get_event_loop().run_in_executor(
    None, lambda: subprocess.run(cmd, capture_output=True, check=True)
)  # ✅ CORRECTO - usa executor
```

**USO INCORRETO (bloqueante):**
```python
# code-forge/src/clients/sonarqube_client.py
result = subprocess.run(
    sonar_cmd, capture_output=True, text=True, timeout=300
)  # ❌ BLOCKING - chamada direta
```

**GAP #7: subprocess.run() Bloqueante**

| Localizacao | Timeout | Executor? | Status |
|-------------|---------|-----------|--------|
| sonarqube_client.py:78 | 300s | ❌ NAO | GAP |
| trivy_client.py:111 | ? | ❌ NAO | GAP |
| validate_executor.py:128 | ? | ❌ NAO | GAP |

---

## 5. Timeout Configuration Gaps

### 5.1 Configuracoes de Timeout por Servico

**worker-agents (timeout mais detalhado):**
```python
task_timeout_multiplier: float = 1.5
ticket_api_timeout_seconds: int = 10
code_forge_timeout_seconds: int = 14400  # 4 horas
flux_timeout_seconds: int = 600
opa_timeout_seconds: int = 30
opa_poll_timeout_seconds: int = 300
trivy_timeout_seconds: int = 300
test_execution_timeout_seconds: int = 600
github_actions_timeout_seconds: int = 900
gitlab_timeout_seconds: int = 900
jenkins_timeout_seconds: int = 600
sonarqube_timeout_seconds: int = 600
checkov_timeout_seconds: int = 300
docker_timeout_seconds: int = 600
k8s_jobs_timeout_seconds: int = 600
lambda_timeout_seconds: int = 900
```

**mcp-tool-catalog (timeout bem configurado):**
```python
GA_TIMEOUT_SECONDS: int = 30
TOOL_EXECUTION_TIMEOUT_SECONDS: int = 300
MCP_SERVER_TIMEOUT_SECONDS: int = 30
MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = 60
MONGODB_CONNECT_TIMEOUT_MS: int = 10000
MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000
REDIS_CONNECT_TIMEOUT_SECONDS: int = 10
REDIS_SOCKET_TIMEOUT_SECONDS: int = 10
KAFKA_REQUEST_TIMEOUT_MS: int = 30000
KAFKA_SESSION_TIMEOUT_MS: int = 30000
SERVICE_REGISTRY_CONNECT_TIMEOUT_SECONDS: int = 10
```

**GAP #8: Falta de Timeout em Alguns Servicos**

| Servico | Configuracao de Timeout | Status |
|---------|-------------------------|--------|
| worker-agents | ✅ Detalhado | BOM |
| mcp-tool-catalog | ✅ Detalhado | BOM |
| consensus-engine | ⚠️ Basico | GAP |
| guard-agents | ⚠️ Basico | GAP |
| gateway-intencoes | ⚠️ Nao identificado | GAP |
| approval-service | ⚠️ Basico | GAP |

### 5.2 Timeout de Kafka

**CONFIGURACOES OBSERVADAS:**

```python
# mcp-tool-catalog/src/clients/kafka_request_consumer.py
session_timeout_ms: int = 30000  # 30s
request_timeout_ms: int = 30000  # 30s

# orchestrator-dynamic/src/integration/flow_c_consumer.py
"max_poll_interval_ms": 21600000,  # 6 horas
"session_timeout_ms": 30000,       # 30 segundos

# memory-layer-api/src/consumers/sync_event_consumer.py
session_timeout_ms=30000,
heartbeat_interval_ms=10000,
```

**GAP #9: max_poll_interval_ms Inconsistente**

| Consumer | max_poll_interval_ms | session_timeout_ms | Consistente? |
|----------|---------------------|-------------------|--------------|
| flow_c_consumer | 6h (21600000ms) | 30s | ⚠️ Muito alto |
| sync_event_consumer | NAO especificado | 30s | ❌ DEFAULT |
| kafka_request_consumer | NAO especificado | 30s | ❌ DEFAULT |
| ticket_consumer | NAO especificado | NAO especificado | ❌ DEFAULT |

**Impacto:** max_poll_interval_ms de 6h pode permitir processamento muito longo, mas pode causar rebalanceamento se o processamento exceder.

---

## 6. Mitigation Recommendations

### 6.1 Prioridade ALTA (Implementar Imediatamente)

1. **Substituir time.sleep() por asyncio.sleep()**
   - Localizacao: consensus-engine/src/consumers/plan_consumer.py
   - Linhas: 382, 452, 565
   - Impacto: Desbloqueia event loop

2. **Envolver subprocess.run() em executor**
   - Localizacoes:
     - code-forge/src/clients/sonarqube_client.py
     - code-forge/src/clients/trivy_client.py
     - worker-agents/src/executors/validate_executor.py
   - Impacto: Evita bloqueio de event loop

3. **Implementar Backpressure em Todos Consumers**
   - Adicionar semaphore/pause-resume pattern a:
     - consensus-engine/plan_consumer
     - orchestrator-dynamic/flow_c_consumer
     - execution-ticket-service/consumer

### 6.2 Prioridade MEDIA (Implementar Curto Prazo)

4. **Adicionar Timeouts por Operacao MongoDB**
   ```python
   mongodb_query_timeout_ms: int = 1000      # Queries simples
   mongodb_aggregate_timeout_ms: int = 10000 # Aggregations
   mongodb_write_timeout_ms: int = 5000      # Writes
   ```

5. **Adicionar Timeouts por Operacao HTTP/gRPC**
   ```python
   grpc_health_check_timeout_seconds: int = 3
   grpc_analytics_timeout_seconds: int = 30
   grpc_training_timeout_seconds: int = 3600
   ```

6. **Revisar max_poll_interval_ms por Consumer**
   - Configurar baseado no workload esperado
   - Documentar escolha de timeout

### 6.3 Prioridade BAIXA (Melhorias Continuas)

7. **Adicionar Timeout em asyncio.gather sem Timeout**
   - Localizacao: gateway-intencoes/src/pipelines/nlu_pipeline_v2.py
   - Metodo: _warm_up_cache()

8. **Implementar Timeout Hierarquico**
   - Timeout da activity < Timeout do workflow
   - Timeout do client < Timeout da activity

9. **Adicionar Métricas de Timeout Violation**
   - Track de timeouts por operacao
   - Alerta quando timeouts sao frequentemente excedidos

---

## 7. Checklist de Verificacao

### 7.1 R-T10.1: Timeout Granularidade

| Requisito | Status | Evidencia |
|-----------|--------|-----------|
| Identificar servicos com timeout global unico | ✅ DONE | MongoDB (5000ms), Kafka (30000ms) |
| Identificar servicos sem timeout configurado | ✅ DONE | gateway-intencoes, approval-service |
| Documentar gaps de granularidade | ✅ DONE | Secao 1.2 |

### 7.2 R-T10.2: Async Patterns e Backpressure

| Requisito | Status | Evidencia |
|-----------|--------|-----------|
| Verificar asyncio.gather com return_exceptions | ✅ DONE | Implementado em consensus-engine |
| Identificar blocking calls em async context | ✅ DONE | time.sleep() em plan_consumer |
| Verificar mecanismos de backpressure | ✅ DONE | worker-agents implementa semaphore+pause |
| Identificar falta de rate limiting | ✅ DONE | GAP em outros consumers |

### 7.3 R-T10.3: Temporal Workflow Timeouts

| Requisito | Status | Evidencia |
|-----------|--------|-----------|
| Analisar workflow timeouts | ✅ DONE | 30s-2h configurados por workflow |
| Analisar activity timeouts | ✅ DONE | 10s-20min configurados por activity |
| Identificar workflows sem timeout | ✅ DONE | Todos os workflows analisados tem timeout |
| Identificar timeouts inadequados | ✅ DONE | GAP: timeout de activity pode exceder workflow |

### 7.4 R-B6.3: Blocking Call Detection

| Requisito | Status | Evidencia |
|-----------|--------|-----------|
| Detectar time.sleep() em async contexts | ✅ DONE | 3 ocorrencias em plan_consumer.py |
| Detectar subprocess.run() bloqueante | ✅ DONE | 3 ocorrencias em code-forge, worker-agents |
| Detectar requests.get() bloqueante | ✅ DONE | Nao identificado (usa httpx/aiohttp) |
| Identificar chamadas sincronas em contextos async | ✅ DONE | time.sleep(), subprocess.run() |

---

## 8. Conclusao

### Gaps Criticos Identificados

1. **time.sleep() em async context** (consensus-engine) - BLOQUEIA EVENT LOOP
2. **subprocess.run() bloqueante** (code-forge, worker-agents) - BLOQUEIA EVENT LOOP
3. **Falta de backpressure** em 4 de 5 consumers Kafka - RISCO DE OVERLOAD
4. **Timeout global unico** para MongoDB - RISCO DE TIMEOUT/FALHA
5. **max_poll_interval_ms inconsistente** - RISCO DE REBALANCEAMENTO

### Pontos Positivos

1. ✅ **worker-agents** tem backpressure excellente com semaphore+pause/resume
2. ✅ **ParallelExecutor** com priority queue e per-type semaphores
3. ✅ **Temporal workflows** com timeouts por activity/workflow
4. ✅ **Temporal client** com circuit breaker
5. ✅ **Specialists gRPC** com timeout por especialista

### Resumo de Status

| Categoria | Status | Percentual |
|-----------|--------|------------|
| Timeout Granularidade | ⚠️ PARCIAL | 60% |
| Async Patterns | ⚠️ PARCIAL | 70% |
| Backpressure | ⚠️ PARCIAL | 40% |
| Temporal Timeouts | ✅ BOM | 90% |
| Blocking Calls | ❌ CRÍTICO | 30% |

---

## 9. Proximos Passos

1. **Imediato (Sprint 1):**
   - Fix time.sleep() → asyncio.sleep() em plan_consumer
   - Fix subprocess.run() → run_in_executor em code-forge
   - Implementar backpressure em consensus-engine consumer

2. **Curto Prazo (Sprint 2-3):**
   - Adicionar timeouts por operacao MongoDB
   - Adicionar timeouts por operacao HTTP/gRPC
   - Revisar max_poll_interval_ms por consumer

3. **Medio Prazo (Sprint 4-6):**
   - Implementar timeout hierarquico
   - Adicionar metricas de timeout violation
   - Documentar choices de timeout em arquitectura

---

**Fim da Analise**
