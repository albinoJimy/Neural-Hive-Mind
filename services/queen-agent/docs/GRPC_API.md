# API gRPC do Queen Agent

Documentação completa da API gRPC do Queen Agent - Coordenador Estratégico do Neural Hive-Mind.

## Visão Geral

O Queen Agent é o coordenador estratégico do sistema, responsável por:
- Tomada de decisões estratégicas (replanning, escalation, resource allocation)
- Gerenciamento de conflitos entre decisões
- Aprovação de exceções
- Agregação de status do sistema
- Recebimento de insights do Analyst Agent

**Endpoint gRPC:** `queen-agent:50051`
**Arquivo Proto:** `services/queen-agent/src/proto/queen_agent.proto`

---

## Endpoints gRPC

| Método | Descrição |
|--------|-----------|
| `GetStrategicDecision` | Buscar decisão estratégica por ID |
| `ListStrategicDecisions` | Listar decisões com filtros e paginação |
| `GetSystemStatus` | Obter status agregado do sistema |
| `RequestExceptionApproval` | Solicitar aprovação de exceção |
| `ApproveException` | Aprovar exceção pendente |
| `RejectException` | Rejeitar exceção pendente |
| `GetActiveConflicts` | Listar conflitos ativos entre decisões |
| `SubmitInsight` | Receber insight do Analyst Agent |

---

## GetStrategicDecision

Busca uma decisão estratégica por ID no ledger MongoDB.

### Request

```protobuf
message GetStrategicDecisionRequest {
  string decision_id = 1;  // ID único da decisão (formato: dec-{uuid})
}
```

### Response

```protobuf
message StrategicDecisionResponse {
  string decision_id = 1;           // ID da decisão
  string decision_type = 2;         // Tipo: REPLANNING, ESCALATION, RESOURCE_ALLOCATION
  double confidence_score = 3;      // Confiança (0.0-1.0)
  double risk_score = 4;            // Risco (0.0-1.0)
  string reasoning_summary = 5;     // Resumo da decisão
  int64 created_at = 6;             // Timestamp em ms
  repeated string target_entities = 7;  // Entidades afetadas
  string action = 8;                // Ação a ser tomada
}
```

### Exemplo Python

```python
import grpc
from queen_agent_pb2 import GetStrategicDecisionRequest
from queen_agent_pb2_grpc import QueenAgentStub

async def get_decision(decision_id: str):
    async with grpc.aio.insecure_channel('queen-agent:50051') as channel:
        stub = QueenAgentStub(channel)
        request = GetStrategicDecisionRequest(decision_id=decision_id)
        response = await stub.GetStrategicDecision(request)
        print(f"Decisão: {response.decision_type}, Confiança: {response.confidence_score}")
        return response
```

### Códigos de Erro

| Código | Descrição |
|--------|-----------|
| `NOT_FOUND` | Decisão não encontrada no MongoDB |
| `INTERNAL` | Erro ao consultar MongoDB ou processar resposta |

---

## ListStrategicDecisions

Lista decisões estratégicas com filtros e paginação.

### Request

```protobuf
message ListStrategicDecisionsRequest {
  optional string decision_type = 1;  // Filtro por tipo
  optional int64 start_date = 2;      // Data início (timestamp ms)
  optional int64 end_date = 3;        // Data fim (timestamp ms)
  int32 limit = 4;                    // Limite (padrão: 50)
  int32 offset = 5;                   // Offset para paginação
}
```

### Response

```protobuf
message ListStrategicDecisionsResponse {
  repeated StrategicDecisionResponse decisions = 1;
  int32 total = 2;  // Total de decisões retornadas
}
```

### Exemplo Python

```python
import grpc
from datetime import datetime, timedelta
from queen_agent_pb2 import ListStrategicDecisionsRequest
from queen_agent_pb2_grpc import QueenAgentStub

async def list_recent_decisions():
    now = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(hours=24)).timestamp() * 1000)

    async with grpc.aio.insecure_channel('queen-agent:50051') as channel:
        stub = QueenAgentStub(channel)
        request = ListStrategicDecisionsRequest(
            decision_type='REPLANNING',
            start_date=start,
            end_date=now,
            limit=20,
            offset=0
        )
        response = await stub.ListStrategicDecisions(request)
        print(f"Total: {response.total} decisões")
        for dec in response.decisions:
            print(f"  - {dec.decision_id}: {dec.decision_type}")
        return response
```

### Códigos de Erro

| Código | Descrição |
|--------|-----------|
| `INTERNAL` | Erro ao consultar MongoDB |

---

## GetSystemStatus

Obtém status agregado do sistema via TelemetryAggregator.

### Request

```protobuf
message GetSystemStatusRequest {}
```

### Response

```protobuf
message SystemStatusResponse {
  double system_score = 1;        // Score geral (0.0-1.0)
  double sla_compliance = 2;      // Compliance de SLA (0.0-1.0)
  double error_rate = 3;          // Taxa de erro (0.0-1.0)
  double resource_saturation = 4; // Saturação de recursos (0.0-1.0)
  int32 active_incidents = 5;     // Incidentes ativos
  int64 timestamp = 6;            // Timestamp da coleta (ms)
}
```

### Fórmula do System Score

```
system_score = sla_compliance * 0.3
             + (1 - error_rate) * 0.3
             + (1 - resource_saturation) * 0.2
             + workflow_success_rate * 0.2
```

### Exemplo Python

```python
import grpc
from queen_agent_pb2 import GetSystemStatusRequest
from queen_agent_pb2_grpc import QueenAgentStub

async def check_system_health():
    async with grpc.aio.insecure_channel('queen-agent:50051') as channel:
        stub = QueenAgentStub(channel)
        request = GetSystemStatusRequest()
        response = await stub.GetSystemStatus(request)

        health_status = "SAUDÁVEL" if response.system_score >= 0.8 else \
                       "DEGRADADO" if response.system_score >= 0.5 else "CRÍTICO"

        print(f"Status: {health_status}")
        print(f"  System Score: {response.system_score:.2f}")
        print(f"  SLA Compliance: {response.sla_compliance:.2f}")
        print(f"  Error Rate: {response.error_rate:.2f}")
        print(f"  Incidentes Ativos: {response.active_incidents}")
        return response
```

### Códigos de Erro

| Código | Descrição |
|--------|-----------|
| `INTERNAL` | Erro ao agregar métricas do Prometheus |

---

## GetActiveConflicts

Lista conflitos ativos entre decisões no Neo4j.

### Request

```protobuf
message GetActiveConflictsRequest {}
```

### Response

```protobuf
message GetActiveConflictsResponse {
  repeated ConflictInfo conflicts = 1;
}

message ConflictInfo {
  string decision_id = 1;      // ID da decisão
  string conflicts_with = 2;   // ID da decisão conflitante
  int64 created_at = 3;        // Timestamp de criação
}
```

### Exemplo Python

```python
import grpc
from queen_agent_pb2 import GetActiveConflictsRequest
from queen_agent_pb2_grpc import QueenAgentStub

async def list_conflicts():
    async with grpc.aio.insecure_channel('queen-agent:50051') as channel:
        stub = QueenAgentStub(channel)
        request = GetActiveConflictsRequest()
        response = await stub.GetActiveConflicts(request)

        if response.conflicts:
            print(f"Conflitos ativos: {len(response.conflicts)}")
            for c in response.conflicts:
                print(f"  {c.decision_id} <-> {c.conflicts_with}")
        else:
            print("Nenhum conflito ativo")
        return response
```

---

## SubmitInsight

Recebe insight do Analyst Agent para processamento.

### Request

```protobuf
message SubmitInsightRequest {
  string insight_id = 1;
  string version = 2;
  string correlation_id = 3;
  string trace_id = 4;
  string span_id = 5;
  string insight_type = 6;           // ANOMALY_DETECTION, TREND_ANALYSIS, etc
  string priority = 7;               // LOW, MEDIUM, HIGH, CRITICAL
  string title = 8;
  string summary = 9;
  string detailed_analysis = 10;
  repeated string data_sources = 11;
  map<string, double> metrics = 12;
  double confidence_score = 13;
  double impact_score = 14;
  repeated Recommendation recommendations = 15;
  repeated RelatedEntity related_entities = 16;
  TimeWindow time_window = 17;
  int64 created_at = 18;
  optional int64 valid_until = 19;
  repeated string tags = 20;
  map<string, string> metadata = 21;
  string hash = 22;
  int32 schema_version = 23;
}
```

### Response

```protobuf
message SubmitInsightResponse {
  bool accepted = 1;
  string insight_id = 2;
  string message = 3;
}
```

---

## Métricas Prometheus

O Queen Agent expõe métricas específicas para monitoramento dos métodos gRPC:

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `queen_agent_grpc_requests_total` | Counter | method, status | Total de requisições gRPC |
| `queen_agent_grpc_request_duration_seconds` | Histogram | method | Latência das requisições |
| `queen_agent_active_decisions` | Gauge | - | Decisões ativas no sistema |
| `queen_agent_system_status_queries_total` | Counter | - | Queries de status do sistema |
| `queen_agent_insights_received_total` | Counter | insight_type, priority, accepted | Insights recebidos |

### Exemplos de Queries Prometheus

```promql
# Throughput por método (req/s)
rate(queen_agent_grpc_requests_total[5m])

# P95 de latência por método
histogram_quantile(0.95, rate(queen_agent_grpc_request_duration_seconds_bucket[5m]))

# Taxa de erro
sum(rate(queen_agent_grpc_requests_total{status="error"}[5m])) /
sum(rate(queen_agent_grpc_requests_total[5m]))

# Decisões ativas
queen_agent_active_decisions
```

---

## Troubleshooting

### Decisão não encontrada

```
grpc.StatusCode.NOT_FOUND: Decision dec-xxx not found
```

**Causa:** O `decision_id` não existe no MongoDB.
**Solução:** Verificar se o ID está correto ou listar decisões disponíveis.

### Erro de conexão com MongoDB

```
grpc.StatusCode.INTERNAL: MongoDB connection timeout
```

**Causa:** MongoDB não está acessível.
**Solução:**
- Verificar status do MongoDB: `kubectl get pods -l app=mongodb`
- Checar health check: `GET /ready`

### Erro de conexão com Neo4j

```
grpc.StatusCode.INTERNAL: Neo4j connection refused
```

**Causa:** Neo4j não está acessível.
**Solução:**
- Verificar status do Neo4j: `kubectl get pods -l app=neo4j`
- Checar conectividade: `nc -zv neo4j 7687`

### Métricas do Prometheus indisponíveis

```
grpc.StatusCode.INTERNAL: Prometheus query failed
```

**Causa:** Prometheus não está acessível ou query inválida.
**Solução:**
- Verificar endpoint do Prometheus
- Checar se métricas existem: `curl prometheus:9090/api/v1/query?query=up`

---

## Integração com Orchestrator Dynamic (gRPC Client)

O Queen Agent comunica-se com o Orchestrator Dynamic via gRPC para enviar comandos estratégicos.

**Endpoint gRPC:** `orchestrator-dynamic:50053`
**Arquivo Proto:** `services/orchestrator-dynamic/proto/orchestrator_strategic.proto`

### Métodos Disponíveis

| Método | Descrição |
|--------|-----------|
| `AdjustPriorities` | Ajustar prioridade de um workflow |
| `RebalanceResources` | Rebalancear alocação de recursos |
| `PauseWorkflow` | Pausar workflow em execução |
| `ResumeWorkflow` | Retomar workflow pausado |
| `TriggerReplanning` | Acionar replanejamento de um plano |
| `GetWorkflowStatus` | Obter status detalhado de um workflow |

### Exemplo: Ajustar Prioridade

```python
from src.clients.orchestrator_client import OrchestratorClient

async def increase_workflow_priority(workflow_id: str, plan_id: str):
    client = OrchestratorClient(settings)
    await client.connect()

    success = await client.adjust_priorities(
        workflow_id=workflow_id,
        plan_id=plan_id,
        new_priority=9,
        reason="SLA violation detected"
    )

    if success:
        print(f"Prioridade ajustada para workflow {workflow_id}")
    else:
        print("Falha ao ajustar prioridade")

    await client.close()
```

### Exemplo: Acionar Replanejamento

```python
async def trigger_strategic_replanning(plan_id: str):
    client = OrchestratorClient(settings)
    await client.connect()

    replanning_id = await client.trigger_replanning(
        plan_id=plan_id,
        reason="Strategic decision from Queen Agent",
        trigger_type="STRATEGIC",
        context={"decision_id": "dec-123"},
        preserve_progress=True,
        priority=8
    )

    if replanning_id:
        print(f"Replanejamento acionado: {replanning_id}")

    await client.close()
```

### Segurança (mTLS via SPIFFE/SPIRE)

Em produção, a comunicação é protegida por mTLS usando SPIFFE/SPIRE:

```yaml
# helm-charts/queen-agent/values.yaml
config:
  spiffe:
    enabled: true
    socketPath: unix:///run/spire/sockets/agent.sock
    trustDomain: neural-hive.local
    enableX509: true
```

### Circuit Breaker

O cliente possui circuit breaker integrado para resiliência:

```yaml
config:
  circuitBreaker:
    enabled: true
    failMax: 5           # Abre após 5 falhas
    timeoutSeconds: 60   # Permanece aberto por 60s
    recoveryTimeoutSeconds: 30  # Half-open após 30s
```

### Métricas Prometheus (Client)

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `queen_agent_orchestrator_grpc_requests_total` | Counter | method, success | Total de requisições ao Orchestrator |
| `queen_agent_orchestrator_grpc_latency_seconds` | Histogram | method | Latência das requisições |
| `queen_agent_orchestrator_circuit_breaker_state` | Gauge | - | Estado do circuit breaker (0=closed, 1=open, 2=half-open) |
