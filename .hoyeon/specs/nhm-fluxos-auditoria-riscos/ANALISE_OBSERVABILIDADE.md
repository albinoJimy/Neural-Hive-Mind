# Análise de Cobertura de Observabilidade — Neural Hive Mind

> **Sub-requirements:** R-T9.1, R-T9.2, R-T9.3, R-B6.2
> **Biblioteca:** neural_hive_observability

---

## 1. Correlation ID Propagation

### Problema Conhecido: Inconsistência na Propagação

**Status atual:** ⚠️ **INCONSISTENTE**

#### Análise por Serviço

| Serviço | Gera Correlation ID | Propaga para Kafka | Propaga para gRPC | Propaga para HTTP |
|---------|---------------------|-------------------|-------------------|-------------------|
| gateway-intencoes | ✓ | ✓ | ✗ | ✓ |
| semantic-translation-engine | ✓ | ✓ | ✗ | N/A |
| consensus-engine | ⚠️ | ⚠️ | ✗ | N/A |
| orchestrator-dynamic | ✓ | ✗ | ✓ | N/A |
| approval-service | ✓ | N/A | ✗ | ✓ |
| worker-agents | ⚠️ | ⚠️ | N/A | N/A |
| queen-agent | ✓ | ✓ | ✗ | N/A |
| service-registry | ✗ | N/A | ✗ | ⚠️ |

**Problemas principais:**
1. gRPC calls não propagam correlation_id consistentemente
2. worker-agents não geram correlation ID para novas tarefas
3. service-registry não participa da tracing chain

#### Código Problemático

```python
# gateway-intencoes/src/main.py
async def process_intent(intent: dict):
    correlation_id = intent.get("correlation_id", str(uuid4()))
    # Propaga para Kafka ✓
    await producer.send("nhm.intentions", value={**intent, "correlation_id": correlation_id})
    # Mas não para gRPC downstream ✗
    await consensus_client.Consolidate(request)  # Missing correlation_id header
```

---

## 2. OpenTelemetry Tracing Coverage

### Biblioteca neural_hive_observability

**Status:** ✓ Implementada, ⚠️ Cobertura Incompleta

#### Serviços com Tracing

| Serviço | Tracing Ativo | Span Coverage | Exportador |
|---------|--------------|---------------|------------|
| gateway-intencoes | ✓ | ~70% | OTLP |
| semantic-translation-engine | ✓ | ~60% | OTLP |
| consensus-engine | ✓ | ~50% | OTLP |
| orchestrator-dynamic | ✓ | ~80% | OTLP (Temporal) |
| approval-service | ✓ | ~65% | OTLP |
| worker-agents | ⚠️ | ~30% | OTLP |
| queen-agent | ✓ | ~75% | OTLP |
| service-registry | ✗ | 0% | N/A |

#### Gaps Identificados

1. **Worker Agents**: Tracing incompleto em executors
2. **Service Registry**: Sem tracing nenhum
3. **Consensus Engine**: Spans não ligam ao parent span corretamente

#### Código Ausente

```python
# worker-agents/src/executors/query_executor.py
async def execute(self, task: dict):
    # Falta: async with tracer.start_as_current_span("worker.query.execute"):
    result = await self._run_query(task)
    return result
```

---

## 3. Metrics e Alerting (Prometheus/Grafana)

### RED Method Coverage

**RED:** Rate, Errors, Duration

| Serviço | Rate (ops/sec) | Errors (%) | Duration (p95) | Alerts |
|---------|---------------|------------|----------------|--------|
| gateway-intencoes | ✓ | ✓ | ✓ | ✓ |
| semantic-translation-engine | ✓ | ✓ | ✓ | ⚠️ |
| consensus-engine | ✓ | ✓ | ⚠️ | ⚠️ |
| orchestrator-dynamic | ✓ | ✓ | ✓ | ✓ |
| approval-service | ✓ | ✓ | ✓ | ✓ |
| worker-agents | ⚠️ | ⚠️ | ✗ | ✗ |
| queen-agent | ✓ | ✓ | ⚠️ | ✓ |
| service-registry | ✗ | ✗ | ✗ | ✗ |

**Problemas:**
1. worker-agents não expõe metrics granulares por executor type
2. service-registry sem metrics
3. consensus-engine sem alerting de high consensus time

#### SLAs Monitorados

| SLA | Target | Alert Configured |
|-----|--------|------------------|
| p50 latency | < 100ms | ✓ |
| p95 latency | < 500ms | ✓ |
| p99 latency | < 2s | ⚠️ (alguns serviços) |
| Availability | > 99.5% | ✓ |
| Throughput | > 100 ops/sec | ✓ |

---

## 4. Distributed Trace Gaps

### Missing Links

1. **Gateway → STE → Consensus**: Tracing quebra na transição STE→Consensus
2. **Consensus → Orchestrator**: Span context não propagado via Kafka
3. **Orchestrator → Workers**: Worker tasks não herdam span parent

#### Exemplo de Gap

```python
# consensus-engine/src/services/consensus_orchestrator.py
async def publish_decision(decision: ConsolidatedDecision):
    await kafka_producer.send("nhm.decisions", value=decision.json())
    # Falta: Inject span context into Kafka headers
```

**Correção necessária:**
```python
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

async def publish_decision(decision: ConsolidatedDecision):
    carrier = {}
    TraceContextTextMapPropagator().inject(carrier)
    await kafka_producer.send("nhm.decisions", value=decision.json(), headers=carrier)
```

---

## 5. Recomendações de Melhoria

### Risco #1: Correlation ID Inconsistente

**Probabilidade:** ALTA
**Impacto:** ALTO
**Urgência:** Importante

**Mitigação:**
1. Middleware gRPC que injeta correlation_id automaticamente
2. Worker agents geram correlation_id para tarefas internas
3. Service registry participa da tracing chain

### Risco #2: Tracing Gaps

**Probabilidade:** MÉDIA
**Impacto:** MÉDIO
**Urgência:** Moderado

**Mitigação:**
1. Adicionar span context injection em Kafka producers
2. Completar tracing em worker agents
3. Ativar tracing em service-registry

### Risco #3: Missing Metrics

**Probabilidade:** BAIXA
**Impacto:** MÉDIO
**Urgência:** Moderado

**Mitigação:**
1. Worker agents expõe metrics por executor type
2. Service registry adiciona Prometheus endpoint
3. Alertas para todos os SLAs

---

## Matriz de Priorização

| # | Risco | Prob. | Imp. | Risco | Esforço | Prioridade |
|---|-------|-------|------|-------|---------|------------|
| 1 | Correlation ID inconsistente | ALTA | ALTO | 9 | Alto (5-7 dias) | **P0** |
| 2 | Tracing gaps Kafka→Workers | MÉDIA | MÉDIO | 4 | Médio (3-4 dias) | **P1** |
| 3 | Worker metrics missing | BAIXA | MÉDIO | 3 | Baixo (2 dias) | P2 |
| 4 | Service registry sem tracing | BAIXA | BAIXO | 1 | Baixo (1 dia) | P3 |

---

## Status da Observabilidade

**Cobertura geral:** ~60%

**Componentes fortes:**
- gateway-intencoes (70% coverage)
- orchestrator-dynamic (80% coverage)

**Componentes fracos:**
- service-registry (0% tracing, 0% metrics)
- worker-agents (30% tracing, metrics incompletas)

**Ação prioritária:** Correlation ID middleware para gRPC + Kafka
