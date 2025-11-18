# Integração do Intelligent Scheduler

## Visão Geral

O **IntelligentScheduler** é o componente central de alocação de recursos do Orchestrator Dynamic, responsável por alocar execution tickets nos worker agents mais adequados baseado em múltiplos fatores: prioridade do ticket, saúde dos agentes, telemetria histórica e predições de machine learning.

O scheduler implementa um pipeline de decisão em 4 etapas:
1. **Cálculo de prioridade**: Combina risk band (40%), QoS (30%) e SLA urgency (30%)
2. **Descoberta de workers**: Consulta Service Registry com cache baseado em TTL
3. **Seleção inteligente**: Ranking de workers baseado em health + telemetria + prioridade
4. **Alocação**: Atualiza ticket com metadata de alocação

## Componentes

### 1. IntelligentScheduler

**Arquivo**: `src/scheduler/intelligent_scheduler.py`

**Responsabilidades**:
- Coordenar o pipeline completo de scheduling
- Gerenciar cache de descobertas de workers (TTL configurável)
- Implementar fallback gracioso quando Service Registry está indisponível
- Aplicar boost de prioridade baseado em predições ML
- Registrar métricas detalhadas de alocação

**Principais Métodos**:

#### `schedule_ticket(ticket: Dict) -> Dict`
Método principal de agendamento que executa o pipeline completo.

**Entrada**: Execution ticket com campos obrigatórios:
- `ticket_id`: Identificador único
- `risk_band`: Banda de risco (critical/high/normal/low)
- `qos`: Configuração de QoS (delivery_mode, consistency, durability)
- `sla`: Configuração de SLA (deadline, timeout_ms)
- `required_capabilities`: Lista de capabilities necessárias
- `namespace`: Namespace do ticket
- `security_level`: Nível de segurança
- `estimated_duration_ms`: Duração estimada
- `created_at`: Timestamp de criação (ms ou ISO string)
- `predictions` (opcional): Predições ML

**Saída**: Ticket enriquecido com `allocation_metadata`:
```python
{
    "allocated_at": 1699123456789,
    "agent_id": "worker-001",
    "agent_type": "worker-agent",
    "priority_score": 0.75,
    "agent_score": 0.85,
    "composite_score": 0.81,
    "allocation_method": "intelligent_scheduler",  # ou "fallback_stub"
    "workers_evaluated": 5,
    "predicted_duration_ms": 1250,  # se ML predictions disponíveis
    "anomaly_detected": false  # se ML predictions disponíveis
}
```

**Fluxo**:
1. Calcula `priority_score` via `PriorityCalculator`
2. Ajusta prioridade se `predictions['duration_ms'] > 1.5 * estimated_duration_ms` (boost de 20%)
3. Descobre workers via `_discover_workers_cached()`
4. Se nenhum worker disponível: registra rejeição `no_workers` e retorna fallback
5. Seleciona melhor worker via `ResourceAllocator.select_best_worker()`
6. Se nenhum worker adequado: registra rejeição `no_suitable_worker` e retorna fallback
7. Calcula `composite_score` e popula `allocation_metadata`
8. Registra métricas de sucesso

#### `_discover_workers_cached(ticket: Dict) -> List[Dict]`
Descobre workers com cache baseado em TTL.

**Lógica de Cache**:
- Chave de cache: `"{namespace}:{security_level}:{capabilities_sorted}"`
- TTL: Configurável via `SERVICE_REGISTRY_CACHE_TTL_SECONDS` (padrão: 60s)
- Cache hit: Retorna workers imediatamente, registra métrica `cache_hit`
- Cache miss/expirado: Consulta `ResourceAllocator.discover_workers()` com timeout de 5s

**Tratamento de Erros**:
- `asyncio.TimeoutError`: Registra `discovery_failure('timeout')`, retorna `[]`
- Qualquer exceção: Registra `discovery_failure(error_type)`, retorna `[]`

#### `_create_fallback_allocation(ticket: Dict) -> Dict`
Cria alocação stub quando Service Registry está indisponível.

**Metadata de Fallback**:
```python
{
    "allocated_at": <timestamp>,
    "agent_id": "worker-agent-pool",
    "agent_type": "worker-agent",
    "priority_score": 0.5,
    "agent_score": 0.5,
    "composite_score": 0.5,
    "allocation_method": "fallback_stub",
    "workers_evaluated": 0
}
```

### 2. PriorityCalculator

**Arquivo**: `src/scheduler/priority_calculator.py`

**Responsabilidades**:
- Calcular score de prioridade combinando múltiplos fatores
- Normalizar scores para [0.0, 1.0]
- Aplicar pesos configuráveis

**Principais Métodos**:

#### `calculate_priority_score(ticket: Dict) -> float`
Calcula score composto de prioridade.

**Fórmula**:
```
priority_score = (risk_weight * 0.4) + (qos_weight * 0.3) + (sla_urgency * 0.3)
```

**Pesos Configuráveis** (via `SCHEDULER_PRIORITY_WEIGHTS`):
- `risk`: Padrão 0.4 (40%)
- `qos`: Padrão 0.3 (30%)
- `sla`: Padrão 0.3 (30%)

#### `_calculate_risk_weight(risk_band: str) -> float`
Mapeia risk band para peso:
- `critical`: 1.0
- `high`: 0.7
- `normal`: 0.5
- `low`: 0.3

#### `_calculate_qos_weight(qos: Dict) -> float`
Combina delivery_mode, consistency e durability.

**Pesos de Delivery Mode**:
- `EXACTLY_ONCE`: 1.0
- `AT_LEAST_ONCE`: 0.7
- `AT_MOST_ONCE`: 0.5

**Multiplicadores de Consistency**:
- `STRONG`: 1.0
- `EVENTUAL`: 0.85

**Multiplicadores de Durability**:
- `PERSISTENT`: 1.0
- `TRANSIENT`: 0.9
- `EPHEMERAL`: 0.8

**Fórmula**: `base_weight * consistency_mult * durability_mult`

#### `_calculate_sla_urgency(sla: Dict, created_at: int) -> float`
Calcula urgência baseada em % de deadline consumido.

**Entrada**:
- `sla['deadline']`: Timestamp absoluto (ms) ou `None`
- `sla['timeout_ms']`: Timeout relativo se deadline não especificado
- `created_at`: Timestamp de criação (ms ou ISO string - será convertido)

**Lógica**:
1. Se `deadline` é `None`: `deadline = created_at + timeout_ms`
2. Calcula `elapsed_ms = now - created_at`
3. Calcula `total_allowed_ms = deadline - created_at`
4. Se `total_allowed_ms <= 0`: retorna `1.0` (urgência máxima)
5. Calcula `deadline_consumed_pct = (elapsed_ms / total_allowed_ms) * 100`

**Mapeamento de Urgência**:
- `< 50%`: urgência `0.3`
- `50-80%`: urgência `0.7`
- `> 80%`: urgência `1.0`

### 3. ResourceAllocator

**Arquivo**: `src/scheduler/resource_allocator.py`

**Responsabilidades**:
- Descobrir workers disponíveis via Service Registry gRPC
- Calcular score de saúde do agente
- Selecionar melhor worker baseado em score composto

**Principais Métodos**:

#### `discover_workers(ticket: Dict) -> List[Dict]`
Consulta Service Registry para descobrir workers compatíveis.

**Critérios de Matching**:
- `capabilities`: Workers devem ter todas as capabilities requeridas
- `namespace`: Workers no mesmo namespace
- `security_level`: Nível de segurança compatível

**Timeout**: 3s (configurável via `SERVICE_REGISTRY_TIMEOUT_SECONDS`)

**Retorno**: Lista de workers com telemetria enriquecida

#### `select_best_worker(workers: List[Dict], priority_score: float) -> Dict`
Seleciona worker com maior score composto.

**Score Composto**:
```
composite_score = (agent_score * 0.6) + (priority_score * 0.4)
```

**Agent Score** combina:
- **Health (50%)**: `HEALTHY=1.0`, `DEGRADED=0.6`, `UNHEALTHY=0.0`
- **Telemetry (50%)**:
  - Success Rate (60%): `success_rate`
  - Duration Score (20%): `1.0 - min(avg_duration_ms / 10000, 1.0)`
  - Experience (20%): `min(total_executions / 100, 1.0)`

**Filtros de Disponibilidade**:
- Status: `HEALTHY` ou `DEGRADED` (workers `UNHEALTHY` são excluídos)
- Capacidade: `active_tasks < max_concurrent_tasks`

## Fluxo Detalhado de Dados

### Fluxo End-to-End

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. OrchestrationWorkflow - Step C3: allocate_resources         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. ticket_generation.py - Activity allocate_resources()        │
│                                                                  │
│    a) PolicyValidator.validate_execution_ticket(ticket)         │
│       → Valida políticas OPA                                    │
│       → Retorna feature_flags                                   │
│                                                                  │
│    b) MLPredictor.predict_and_enrich(ticket) [se habilitado]   │
│       → Adiciona campo predictions: {duration_ms, anomaly}      │
│                                                                  │
│    c) IntelligentScheduler.schedule_ticket(ticket)              │
│       [se feature_flags.enable_intelligent_scheduler=true]      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. IntelligentScheduler.schedule_ticket()                      │
│                                                                  │
│    a) PriorityCalculator.calculate_priority_score(ticket)       │
│       → Combina risk (40%) + qos (30%) + sla (30%)              │
│       → Retorna priority_score [0.0-1.0]                        │
│                                                                  │
│    b) Ajusta prioridade com ML predictions                      │
│       → Se predictions.duration_ms > 1.5*estimated: boost 20%   │
│                                                                  │
│    c) _discover_workers_cached(ticket)                          │
│       → Verifica cache por chave                                │
│       → Cache hit: retorna workers do cache                     │
│       → Cache miss: chama ResourceAllocator.discover_workers()  │
│       → Atualiza cache com TTL de 60s                           │
│                                                                  │
│    d) ResourceAllocator.select_best_worker(workers, priority)   │
│       → Calcula agent_score para cada worker                    │
│       → Calcula composite_score                                 │
│       → Filtra por disponibilidade (status + capacidade)        │
│       → Retorna worker com maior composite_score                │
│                                                                  │
│    e) Popula allocation_metadata                                │
│       → allocated_at, agent_id, scores, workers_evaluated       │
│       → predicted_duration_ms, anomaly_detected (se ML)         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. ticket_generation.py retorna ticket enriquecido             │
│    → allocation_metadata incluso                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. OrchestrationWorkflow - Step C4: Publicar tickets           │
│    → Publica no Kafka execution.tickets                         │
│    → Worker Agents consomem e executam                          │
└─────────────────────────────────────────────────────────────────┘
```

## Pontos de Integração com o Workflow

### C3: Allocate Resources (`ticket_generation.py` - activity `allocate_resources`)

**Localização**: `services/orchestrator-dynamic/src/activities/ticket_generation.py`

**Sequência de Execução**:

```python
async def allocate_resources(ticket: Dict, context: TicketContext) -> Dict:
    """
    Aloca recursos para um ticket via IntelligentScheduler.

    Steps:
    1. Valida ticket contra políticas OPA
    2. Enriquece com predições ML (se habilitado)
    3. Executa scheduler inteligente (se feature flag habilitada)
    4. Fallback para alocação stub se scheduler desabilitado
    """

    # Step 1: Validação OPA
    policy_result = await policy_validator.validate_execution_ticket(ticket)

    if not policy_result.is_valid:
        # Política rejeitou o ticket
        raise PolicyViolationError(policy_result.violations)

    feature_flags = policy_result.feature_flags

    # Step 2: ML Predictions (se habilitado)
    if context.ml_predictions_enabled:
        ticket = await ml_predictor.predict_and_enrich(ticket)

    # Step 3: Scheduling
    if feature_flags.get('enable_intelligent_scheduler', True):
        # Usar IntelligentScheduler
        ticket = await intelligent_scheduler.schedule_ticket(ticket)
    else:
        # Fallback para alocação stub
        ticket = create_stub_allocation(ticket)

    return ticket
```

**Dependências Injetadas**:
- `policy_validator`: Instância de `PolicyValidator`
- `ml_predictor`: Instância de `MLPredictor`
- `intelligent_scheduler`: Instância de `IntelligentScheduler`

### OrchestrationWorkflow - Integração Completa

**Localização**: `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py`

**Fluxo Completo**:

```python
@workflow.defn(name='OrchestrationWorkflow')
class OrchestrationWorkflow:
    """Workflow principal do Fluxo C - Orquestração de Execução."""

    @workflow.run
    async def run(self, cognitive_plan: Dict) -> Dict:
        # C1: Validate Plan
        validation_result = await workflow.execute_activity(
            validate_cognitive_plan,
            cognitive_plan,
            ...
        )

        # C2: Generate Tickets
        tickets = await workflow.execute_activity(
            generate_execution_tickets,
            cognitive_plan,
            ...
        )

        # C3: Allocate Resources (PONTO DE INTEGRAÇÃO)
        allocated_tickets = []
        for ticket in tickets:
            allocated_ticket = await workflow.execute_activity(
                allocate_resources,  # ← Integração do IntelligentScheduler
                ticket,
                ...
            )
            allocated_tickets.append(allocated_ticket)

        # C4: Publish Tickets
        publish_results = await workflow.execute_activity(
            publish_tickets_to_kafka,
            allocated_tickets,
            ...
        )

        # C5-C6: Consolidate & Publish Telemetry
        ...
```

## Configurações Relevantes no OrchestratorSettings

**Arquivo**: `src/config/settings.py`

### Service Registry

```python
SERVICE_REGISTRY_ENDPOINT = "service-registry:50051"
SERVICE_REGISTRY_TIMEOUT_SECONDS = 3  # Timeout gRPC
SERVICE_REGISTRY_CACHE_TTL_SECONDS = 60  # TTL de cache de descobertas
SERVICE_REGISTRY_MAX_RESULTS = 10  # Máximo de workers retornados
```

### Scheduler

```python
ENABLE_INTELLIGENT_SCHEDULER = True  # Master switch

SCHEDULER_PRIORITY_WEIGHTS = {
    "risk": 0.4,
    "qos": 0.3,
    "sla": 0.3
}
```

### ML Predictions

```python
ML_PREDICTIONS_ENABLED = True  # Habilitar predições ML
MLFLOW_TRACKING_URI = "http://mlflow.mlflow.svc.cluster.local:5000"
```

### OPA Policies

```python
OPA_ENABLED = True
OPA_HOST = "opa.neural-hive-orchestration.svc.cluster.local"
OPA_PORT = 8181
OPA_TIMEOUT_SECONDS = 2
OPA_FAIL_OPEN = False  # fail-closed por padrão
```

## Estratégia de Cache e Fallback

### Cache de Descobertas

**Implementação**: Dictionary Python in-memory
```python
_discovery_cache: Dict[str, tuple[List[Dict], datetime]] = {}
```

**Chave de Cache**: `"{namespace}:{security_level}:{capabilities_sorted}"`

**Exemplo**:
```
"default:standard:data-processing:python"
```

**TTL**: 60s (configurável via `SERVICE_REGISTRY_CACHE_TTL_SECONDS`)

**Benefícios**:
- Reduz latência em 70-80% para tickets similares
- Diminui carga no Service Registry
- Melhora throughput de scheduling

**Invalidação**:
- Expiração por TTL (remoção lazy ao tentar reutilizar)
- Não há invalidação proativa (by design para simplicidade)

### Estratégia de Fallback

**Cenários de Fallback**:
1. Service Registry indisponível (timeout, conexão recusada)
2. Nenhum worker descoberto
3. Nenhum worker adequado (todos UNHEALTHY ou sem capacidade)
4. Feature flag `enable_intelligent_scheduler=false`
5. Erro inesperado no scheduler

**Comportamento de Fallback**:
- Allocation method: `fallback_stub`
- Agent ID: `worker-agent-pool` (pool genérico)
- Scores: Todos 0.5 (neutro)
- Workers evaluated: 0

**Fail-open vs Fail-closed**:
- Scheduler: **Fail-open** (permite execução mesmo sem discovery)
- OPA: **Fail-closed** (padrão, configurável via `OPA_FAIL_OPEN`)

## Métricas de Scheduling Expostas via OrchestratorMetrics

### Alocações

**`orchestration_scheduler_allocations_total`**
- **Tipo**: Counter
- **Labels**: `status` (success/error), `fallback` (true/false)
- **Descrição**: Total de alocações executadas pelo scheduler

**Queries PromQL**:
```promql
# Taxa de sucesso de alocações
rate(orchestration_scheduler_allocations_total{status="success"}[5m])
  / rate(orchestration_scheduler_allocations_total[5m]) * 100

# Taxa de uso de fallback
rate(orchestration_scheduler_allocations_total{fallback="true"}[5m])
  / rate(orchestration_scheduler_allocations_total[5m]) * 100
```

### Latência

**`orchestration_scheduler_allocation_duration_seconds`**
- **Tipo**: Histogram
- **Buckets**: `[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30]`
- **Descrição**: Tempo de alocação end-to-end (cálculo de prioridade → seleção de worker)

**Queries PromQL**:
```promql
# P50, P95, P99
histogram_quantile(0.50, rate(orchestration_scheduler_allocation_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(orchestration_scheduler_allocation_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(orchestration_scheduler_allocation_duration_seconds_bucket[5m]))
```

### Prioridade

**`orchestration_scheduler_priority_score`**
- **Tipo**: Histogram
- **Labels**: `risk_band`
- **Descrição**: Distribuição de scores de prioridade calculados

**Queries PromQL**:
```promql
# Distribuição de prioridades por risk band
histogram_quantile(0.50, rate(orchestration_scheduler_priority_score_bucket[5m])) by (risk_band)
```

### Discovery

**`orchestration_scheduler_workers_discovered`**
- **Tipo**: Histogram
- **Descrição**: Número de workers descobertos por alocação

**`orchestration_scheduler_discovery_failures_total`**
- **Tipo**: Counter
- **Labels**: `error_type` (timeout, connection_error, etc.)
- **Descrição**: Total de falhas de discovery

**Queries PromQL**:
```promql
# Média de workers descobertos
avg(orchestration_scheduler_workers_discovered)

# Taxa de falhas de discovery por tipo
rate(orchestration_scheduler_discovery_failures_total[5m]) by (error_type)
```

### Cache

**`orchestration_scheduler_cache_hits_total`**
- **Tipo**: Counter
- **Descrição**: Total de cache hits em descobertas

**Queries PromQL**:
```promql
# Taxa de cache hit
rate(orchestration_scheduler_cache_hits_total[5m])
```

### Rejeições

**`orchestration_scheduler_rejections_total`**
- **Tipo**: Counter
- **Labels**: `reason` (no_workers, no_suitable_worker, policy_violation)
- **Descrição**: Total de rejeições de alocação

**Queries PromQL**:
```promql
# Taxa de rejeições por motivo
rate(orchestration_scheduler_rejections_total[5m]) by (reason)
```

## Cenários de Troubleshooting Comuns

### 1. Alta taxa de fallback (>10%)

**Sintomas**:
- Métrica `orchestration_scheduler_allocations_total{fallback="true"}` alta
- Logs: "no_workers_discovered" ou "discovery_timeout"

**Diagnóstico**:
```bash
# Verificar Service Registry disponível
kubectl get pods -l app=service-registry -n neural-hive-execution

# Testar endpoint gRPC
grpcurl -plaintext service-registry:50051 list

# Verificar logs de discovery
kubectl logs -l app=orchestrator-dynamic | grep discovery_error
```

**Solução**:
1. Verificar health do Service Registry
2. Aumentar timeout: `SERVICE_REGISTRY_TIMEOUT_SECONDS=10`
3. Verificar registro de workers no Service Registry
4. Revisar filtros de capabilities/namespace

### 2. Latência de alocação alta (P95 > 200ms)

**Sintomas**:
- Métrica `orchestration_scheduler_allocation_duration_seconds` P95 > 0.2s
- Logs: "discovery_timeout"

**Diagnóstico**:
```promql
# Verificar P95 por fallback
histogram_quantile(0.95,
  rate(orchestration_scheduler_allocation_duration_seconds_bucket[5m])
) by (fallback)

# Cache hit rate
rate(orchestration_scheduler_cache_hits_total[5m])
  / rate(orchestration_scheduler_allocations_total[5m])
```

**Solução**:
1. Aumentar TTL de cache: `SERVICE_REGISTRY_CACHE_TTL_SECONDS=120`
2. Reduzir max results: `SERVICE_REGISTRY_MAX_RESULTS=5`
3. Otimizar filtros de capabilities (mais específicos)
4. Escalar Service Registry horizontalmente

### 3. Tickets não sendo alocados em workers específicos

**Sintomas**:
- Ticket sempre alocado em `worker-agent-pool` (fallback)
- Worker esperado não aparece em logs de discovery

**Diagnóstico**:
```bash
# Verificar capabilities do ticket
kubectl logs -l app=orchestrator-dynamic | grep scheduling_ticket

# Listar workers registrados
grpcurl -plaintext service-registry:50051 \
  ServiceRegistry.ListAgents \
  -d '{"capabilities": ["python"]}'

# Verificar health do worker
kubectl get pods -l agent-type=worker-agent
```

**Solução**:
1. Verificar capabilities exatas (case-sensitive)
2. Verificar namespace do ticket vs worker
3. Verificar security_level compatível
4. Checar status do worker (deve ser HEALTHY ou DEGRADED)
5. Verificar capacidade do worker (active_tasks < max_concurrent_tasks)

### 4. Predições ML não aparecem em allocation_metadata

**Sintomas**:
- Campo `predicted_duration_ms` ausente em allocation_metadata
- Campo `anomaly_detected` ausente

**Diagnóstico**:
```bash
# Verificar ML_PREDICTIONS_ENABLED
kubectl get configmap orchestrator-config -o yaml | grep ML_PREDICTIONS

# Verificar logs de ML predictor
kubectl logs -l app=orchestrator-dynamic | grep ml_prediction

# Verificar MLflow disponível
kubectl port-forward -n mlflow svc/mlflow 5000:5000
curl http://localhost:5000/health
```

**Solução**:
1. Habilitar: `ML_PREDICTIONS_ENABLED=true`
2. Verificar MLflow tracking URI configurado
3. Verificar modelos treinados no MLflow
4. Verificar MongoDB disponível (required para features históricas)

### 5. Política OPA rejeitando tickets

**Sintomas**:
- Métrica `orchestration_opa_policy_rejections_total` aumentando
- Logs: "policy_validation_failed"

**Diagnóstico**:
```bash
# Verificar rejeições por política
promtool query instant \
  'rate(orchestration_opa_policy_rejections_total[5m]) by (policy_name, rule)'

# Verificar logs de validação OPA
kubectl logs -l app=orchestrator-dynamic | grep opa_validation

# Testar política manualmente
curl -X POST http://opa:8181/v1/data/neuralhive/orchestrator/resource_limits \
  -d @ticket.json
```

**Solução**:
1. Revisar políticas Rego em `policies/rego/orchestrator/`
2. Ajustar limites de recursos na política
3. Verificar alinhamento QoS/risk_band
4. Se necessário, habilitar fail-open temporariamente: `OPA_FAIL_OPEN=true`

## Instruções de Teste

### Testes Unitários

**Executar todos os testes unitários do scheduler**:
```bash
cd services/orchestrator-dynamic

# Todos os testes de scheduler
pytest tests/unit/test_intelligent_scheduler.py -v
pytest tests/unit/test_priority_calculator.py -v
pytest tests/unit/test_resource_allocator.py -v

# Com cobertura
pytest tests/unit/test_intelligent_scheduler.py --cov=src/scheduler --cov-report=html
```

**Exemplo de teste individual**:
```bash
# Testar alocação bem-sucedida
pytest tests/unit/test_intelligent_scheduler.py::TestIntelligentScheduler::test_schedule_ticket_success_with_workers -v

# Testar fallback
pytest tests/unit/test_intelligent_scheduler.py::TestIntelligentScheduler::test_schedule_ticket_fallback_no_workers -v

# Testar boost de prioridade ML
pytest tests/unit/test_intelligent_scheduler.py::TestIntelligentScheduler::test_schedule_ticket_ml_priority_boost -v
```

### Testes de Integração

**Executar testes de integração completos**:
```bash
cd services/orchestrator-dynamic

# Testes de integração do scheduler
pytest tests/integration/test_scheduler_integration.py -v

# Testes de integração do workflow
pytest tests/integration/test_orchestration_workflow_scheduler.py -v
```

**Cenários cobertos**:
- Fluxo end-to-end com Service Registry
- Service Registry indisponível (fallback)
- Integração com predições ML
- Validação de políticas OPA
- Feature flags (habilitado/desabilitado)
- Tickets concorrentes
- Cache de descobertas
- Diferentes risk bands

**Exemplo de comando para cenário específico**:
```bash
# Testar integração com ML predictions
pytest tests/integration/test_scheduler_integration.py::TestSchedulerIntegration::test_e2e_with_ml_predictions -v

# Testar rejeição de política OPA
pytest tests/integration/test_scheduler_integration.py::TestSchedulerIntegration::test_e2e_opa_rejection -v
```

### Script de Teste Completo

**Executar suite completa de testes do scheduler**:
```bash
cd services/orchestrator-dynamic

# Script que executa todos os testes + validações
./scripts/test_scheduler.sh
```

**Conteúdo do script**:
```bash
#!/bin/bash
set -e

echo "=== Testes Unitários ==="
pytest tests/unit/test_intelligent_scheduler.py -v
pytest tests/unit/test_priority_calculator.py -v
pytest tests/unit/test_resource_allocator.py -v

echo "=== Testes de Integração ==="
pytest tests/integration/test_scheduler_integration.py -v
pytest tests/integration/test_orchestration_workflow_scheduler.py -v

echo "=== Cobertura ==="
pytest tests/ --cov=src/scheduler --cov-report=term-missing --cov-fail-under=80

echo "✅ Todos os testes passaram!"
```

### Testes Manuais em Ambiente Local

**1. Iniciar dependências locais**:
```bash
# Service Registry mock
docker-compose up -d service-registry

# MongoDB (para ML features)
docker-compose up -d mongodb

# MLflow (para predições)
docker-compose up -d mlflow

# OPA (para políticas)
docker-compose up -d opa
```

**2. Configurar variáveis de ambiente**:
```bash
export SERVICE_REGISTRY_ENDPOINT="localhost:50051"
export MONGODB_URI="mongodb://localhost:27017"
export MLFLOW_TRACKING_URI="http://localhost:5000"
export OPA_HOST="localhost"
export ML_PREDICTIONS_ENABLED="true"
```

**3. Executar scheduler standalone**:
```python
# test_scheduler_manual.py
import asyncio
from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.config.settings import get_settings

async def main():
    config = get_settings()
    # ... inicializar scheduler

    ticket = {
        "ticket_id": "test-001",
        "risk_band": "high",
        "required_capabilities": ["python"],
        # ... outros campos
    }

    result = await scheduler.schedule_ticket(ticket)
    print(f"Resultado: {result['allocation_metadata']}")

asyncio.run(main())
```

### Validação de Métricas

**Verificar métricas expostas**:
```bash
# Port-forward para endpoint de métricas
kubectl port-forward -n neural-hive-orchestration svc/orchestrator-dynamic 9090:9090

# Consultar métricas
curl http://localhost:9090/metrics | grep orchestration_scheduler

# Métricas esperadas:
# - orchestration_scheduler_allocations_total
# - orchestration_scheduler_allocation_duration_seconds
# - orchestration_scheduler_priority_score
# - orchestration_scheduler_workers_discovered
# - orchestration_scheduler_cache_hits_total
# - orchestration_scheduler_rejections_total
```

**Queries PromQL para validação**:
```promql
# Taxa de sucesso deve ser > 95%
rate(orchestration_scheduler_allocations_total{status="success"}[5m])
  / rate(orchestration_scheduler_allocations_total[5m])

# P95 de latência deve ser < 200ms
histogram_quantile(0.95, rate(orchestration_scheduler_allocation_duration_seconds_bucket[5m]))

# Taxa de fallback deve ser < 5%
rate(orchestration_scheduler_allocations_total{fallback="true"}[5m])
  / rate(orchestration_scheduler_allocations_total[5m])
```

## Links para Seções Relevantes

### Documentação Principal
- [README do Orchestrator](../README.md#scheduler-inteligente) - Seção "Scheduler Inteligente"
- [README do Orchestrator](../README.md#monitoramento) - Seção "Monitoramento"

### Dashboards Grafana
- [Dashboard Principal](../../../../monitoring/dashboards/orchestrator-intelligent-scheduler.json) - Métricas detalhadas do scheduler
- [Dashboard Fluxo C](../../../../monitoring/dashboards/fluxo-c-orquestracao.json) - Seção "Intelligent Scheduler"

### Código-fonte
- [IntelligentScheduler](../src/scheduler/intelligent_scheduler.py)
- [PriorityCalculator](../src/scheduler/priority_calculator.py)
- [ResourceAllocator](../src/scheduler/resource_allocator.py)
- [Ticket Generation Activity](../src/activities/ticket_generation.py) - `allocate_resources()`
- [Orchestration Workflow](../src/workflows/orchestration_workflow.py) - Step C3

### Testes
- [Testes Unitários - IntelligentScheduler](../tests/unit/test_intelligent_scheduler.py)
- [Testes Unitários - PriorityCalculator](../tests/unit/test_priority_calculator.py)
- [Testes de Integração](../tests/integration/test_scheduler_integration.py)
- [Testes de Workflow](../tests/integration/test_orchestration_workflow_scheduler.py)

### Configuração
- [OrchestratorSettings](../src/config/settings.py)
- [Helm Values](../../../../helm-charts/orchestrator-dynamic/values.yaml) - Seção `config.scheduler`

### Políticas e ML
- [Políticas OPA](../../../../policies/rego/orchestrator/)
- [ML Predictions](../src/ml/) - Integração com MLflow
- [Alertas Prometheus](../../../../monitoring/alerts/orchestrator-scheduler-alerts.yaml)
