# Analise de Confiabilidade de Mensagens e Error Handling

**Data:** 2026-04-27
**Analista:** Agente Worker T6
**Escopo:** Kafka message reliability, DLQ, retries, exponential backoff e circuit breakers

---

## Resumo Executivo

A analise revelou **gaps criticos** na confiabilidade de mensagens Kafka, especialmente:

1. **DLQ NAO IMPLEMENTADA** no servico critico `consensus-engine` (configuracao reservada mas nao funcional)
2. **Circuit breakers** aplicados de forma inconsistente (apenas em alguns servicos)
3. **Retry sem limites** em alguns consumers, criando risco de congestionamento
4. **Exponential backoff** nem sempre configurado adequadamente

---

## 1. Analise de DLQ por Topico Kafka

### 1.1 Topicos Kafka Identificados

| Topico | Servico Produtor | Servico Consumer | DLQ Configurada | Status |
|--------|------------------|------------------|-----------------|--------|
| `plans.ready` | semantic-translation-engine | consensus-engine | NAO | **CRITICO** |
| `plans.consensus` | consensus-engine | orchestrator-dynamic | NAO | GAP |
| `execution.tickets` | orchestrator-dynamic | guard-agents | NAO | GAP |
| `execution.results` | worker-agents | orchestrator-dynamic | NAO | GAP |
| `security.validations` | guard-agents | approval-service | NAO | GAP |
| `consensus.decisions` | consensus-engine | queen-agent | NAO | GAP |
| `execution.tickets.validated` | guard-agents | worker-agents | NAO | GAP |
| `execution.tickets.rejected` | guard-agents | execution-ticket-service | NAO | GAP |
| `requirements.events` | requirements-engine | requirements-engine | SIM | OK |
| `memory.sync.events` | memory-layer-api | memory-layer-api | SIM | OK |
| `documentation.events` | documentation-generation | documentation-generation | SIM | OK |

### 1.2 Detalhamento dos Gaps

#### GAP CRITICO: consensus-engine/PlanConsumer

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`
**Linhas:** 120-121

```python
# NOTA: DLQ ainda nao esta implementado. Configuracoes consumer_enable_dlq e
# kafka_dlq_topic sao reservadas para implementacao futura.
```

**Configuracao existente (nao utilizada):**
- `consumer_enable_dlq`: bool = False (field_validator impede True em producao)
- `kafka_dlq_topic`: "plans.ready.dlq"
- `consumer_max_retries_before_dlq`: int = 2

**Impacto:**
- Mensagens com erros de negocio (dados invalidos) ficam presas no consumer
- Offset nao commitado causa reprocessamento infinito de mensagens invalidas
- Risk de **congestionamento do topico principal**

**Comportamento atual (linha 256):**
```python
# Erro de negocio - NAO commita offset, permite retry/analise
ConsensusMetrics.increment_consumer_error(
    type(process_error).__name__, is_systemic=False
)
logger.warning(
    "Erro de negocio - offset NAO commitado, mensagem permanece no Kafka",
    offset=msg.offset(),
    plan_id=cognitive_plan.get("plan_id", "unknown"),
    error_type=type(process_error).__name__,
)
```

#### GAP: Orchestrator DecisionConsumer

**Arquivo:** `services/orchestrator-dynamic/src/consumers/decision_consumer.py`
**Linha:** 803-804

```python
# Nao commitar offset para permitir retry
raise
```

**Problema:** Mensagens com erros permanentes (schema invalid, plano nao encontrado) sao retentadas infinitamente.

#### GAP: ExecutionResultConsumer

**Arquivo:** `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`
**Linhas:** 103-104

```python
# Commit mesmo assim para nao bloquear topico
await self.consumer.commit()
```

**Problema:** Mensagens com erro sao descartadas (commit mesmo com erro), sem DLQ.

### 1.3 Servicos com DLQ Implementada

#### requirements-engine/CognitivePlanConsumer

**Arquivo:** `services/requirements-engineering/src/consumers/cognitive_plan_consumer.py`

**Implementacao funcional:**
```python
async def _send_to_dlq(self, raw_value: bytes, reason: str) -> None:
    """Envia mensagem para DLQ."""
    if not self._producer:
        return

    try:
        await self._producer.send_to_dlq(
            topic=self._dlq_topic,
            value=raw_value,
            reason=reason,
        )
    except Exception as e:
        self._logger.error("failed_to_send_to_dlq", error=str(e))
```

**Chamada em casos de erro:**
```python
except json.JSONDecodeError as e:
    self._logger.error("invalid_json", error=str(e))
    await self._send_to_dlq(msg.value, reason="invalid_json")

except Exception as e:
    self._logger.error("message_processing_error", error=str(e))
    await self._send_to_dlq(msg.value, reason=str(e))
```

---

## 2. Analise de Retry Logic e Exponential Backoff

### 2.1 Retry Implementations

#### consensus-engine: Exponential Backoff Implementado

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`
**Linhas:** 176-188

```python
# Backoff exponencial
backoff = min(
    base_backoff_seconds * (2**consecutive_errors), max_backoff_seconds
)
ConsensusMetrics.increment_backoff_event("kafka_error")
ConsensusMetrics.observe_backoff_duration(backoff, "kafka_error")
logger.warning(
    "Backoff antes de retry",
    backoff_seconds=backoff,
    consecutive_errors=consecutive_errors,
)
await asyncio.sleep(backoff)
```

**Configuracoes:**
- `consumer_base_backoff_seconds`: 1.0 (padrao)
- `consumer_max_backoff_seconds`: 60.0 (padrao)
- `consumer_max_consecutive_errors`: 10 (padrao)

**Problema:** Circuit breaker interno mas sem DLQ para mensagens invalidas.

#### queen-agent: gRPC Retry com Backoff

**Arquivo:** `services/consensus-engine/src/clients/queen_agent_grpc_client.py`
**Padrao:** Exponential backoff para chamadas gRPC

```python
backoff = BASE_BACKOFF_SECONDS * (2**attempt)
await asyncio.sleep(backoff)
```

**Limite:** MAX_RETRIES = 3

#### Orchestrator Saga Retry

**Arquivo:** `services/orchestrator-dynamic/src/saga/retry_config.py`

**Configuracao:**
```python
max_retries: int = Field(default=3, ge=0, le=10)
initial_delay: float = Field(default=1.0, ge=0.1)
multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
```

**Backoff implementado:** `delay = initial_delay * multiplier^(attempt-1)`

### 2.2 Gaps de Retry

#### GAP: Retry Infinito em Alguns Consumers

**Problema:** Consumers sem `max_retries` podem retentar indefinidamente.

**Exemplo:** `guard-agents/src/consumers/ticket_consumer.py` (linha 168)

```python
# Nao commitar offset em caso de erro
# Mensagem sera reprocessada
```

**Risk:** Loop infinito se erro for permanente (ex: schema invalido).

---

## 3. Analise de Circuit Breaker Coverage

### 3.1 neural_hive_resilience Library

**Localizacao:** `libraries/python/neural_hive_resilience/`

**Componentes disponiveis:**
- `MonitoredCircuitBreaker` (com metricas Prometheus)
- `RetryPolicy` (com exponential backoff)
- `RateLimiter` (token bucket, sliding window)
- `TimeoutHandler`
- `FallbackHandler`
- `Bulkhead`

### 3.2 Servicos com Circuit Breaker

| Servico | Circuit Breaker | Target | Status |
|---------|----------------|--------|--------|
| queen-agent | MonitoredCircuitBreaker | Neo4j, MCP | OK |
| orchestrator-dynamic | MonitoredCircuitBreaker | Temporal client | OK |
| specialist-architecture | pybreaker.CircuitBreaker | MongoDB, Neo4j, Redis | OK |
| self-healing-engine | MonitoredCircuitBreaker | Chaos engine | OK |

#### Exemplo: queen-agent Neo4j Client

**Arquivo:** `services/queen-agent/src/clients/neo4j_client.py`

```python
from neural_hive_resilience.circuit_breaker import (
    CircuitBreakerError,
    MonitoredCircuitBreaker,
)

# Configuracao
self.neo4j_breaker = MonitoredCircuitBreaker(
    service_name="queen-agent",
    circuit_name="neo4j",
    failure_threshold=5,
    recovery_timeout=60,
)

# Uso
try:
    result = await self._call_with_breaker(...)
except CircuitBreakerError:
    logger.warning("Neo4j circuit breaker open")
    # Fallback ou erro
```

### 3.3 Servicos SEM Circuit Breaker

| Servico | Dependencias Externas | Gap |
|---------|----------------------|-----|
| consensus-engine | MongoDB, gRPC specialists | **CRITICO** |
| guard-agents | Nenhum circuit breaker identificado | GAP |
| worker-agents | Nenhum circuit breaker identificado | GAP |
| gateway-intencoes | Nenhum circuit breaker identificado | GAP |
| execution-ticket-service | Nenhum circuit breaker identificado | GAP |

#### GAP CRITICO: consensus-engine sem Circuit Breaker

**Problema:** Chamadas gRPC para especialistas sem circuit breaker.

**Arquivo:** `services/consensus-engine/src/clients/specialists_grpc_client.py`

```python
async def evaluate_plan(self, specialist_type: str, cognitive_plan: dict):
    # Chamada gRPC direta sem circuit breaker
    async with grpc.aio.insecure_channel(target) as channel:
        stub = SpecialistStub(channel)
        response = await stub.EvaluatePlan(...)
```

**Risk:** Se specialist estiver lento/falhando, consensus-engine fica bloqueado.

---

## 4. Error Handling Patterns

### 4.1 Padroes Identificados

#### Pattern 1: Commit Manual com DLQ (requis-engineering)

```python
try:
    await self._handle_cognitive_plan(data)
except json.JSONDecodeError as e:
    await self._send_to_dlq(msg.value, reason="invalid_json")
except Exception as e:
    await self._send_to_dlq(msg.value, reason=str(e))
```

**Avaliacao:** **BOA PRATICA** - Mensagens problematicas sao isoladas em DLQ.

#### Pattern 2: Commit Mesmo com Erro (orchestrator-dynamic)

```python
try:
    await self._process_result(message)
except Exception as e:
    logger.error(...)
    # Commit mesmo assim para nao bloquear topico
    await self.consumer.commit()
```

**Avaliacao:** **PERIGOSO** - Mensagens com erro sao perdidas sem rastreabilidade.

#### Pattern 3: Nao Commitar (consensus-engine)

```python
try:
    await self._process_message(msg, cognitive_plan)
except Exception as process_error:
    # NAO para o consumer - apenas loga e continua
    logger.error(...)
    # NAO commita offset em caso de erro (permitir retry)
```

**Avaliacao:** **RISCO CONGESTIONAMENTO** - Sem DLQ, mensagens invalidas sao retentadas infinitamente.

### 4.2 Diferenciacao de Erros

**consensus-engine implementa:**

```python
def _is_systemic_error(self, error: Exception) -> bool:
    """
    Erros sistemicos vs erros de negocio.

    Sistemicos: connectivity, timeout, unavailability
    Negocio: validacao, logica, dados invalidos
    """
    systemic_error_types = (
        ConnectionError, TimeoutError, OSError, grpc.RpcError,
    )
    # ... logica de discriminacao
```

**Avaliacao:** **BOA PRATICA** - Permite tratamento diferenciado.

---

## 5. Configuracao Kafka Producer/Consumer

### 5.1 Producer Configurations

#### consensus-engine DecisionProducer

```python
producer_config = {
    "bootstrap.servers": self.config.kafka_bootstrap_servers,
    "enable.idempotence": self.config.kafka_enable_idempotence,  # TRUE
    "acks": "all",  # Wait for all replicas
    "retries": 3,
    "max.in.flight.requests.per.connection": 5,
}
```

**Avaliacao:** **BOA PRATICA** - Exactly-once semantica habilitada.

#### execution-ticket-service Producer

```python
producer_config = {
    "acks": "all",  # Wait for all replicas
    "enable.idempotence": True,
}
```

**Avaliacao:** **BOA PRATICA**

### 5.2 Consumer Configurations

#### Padrao observado:

```python
consumer_config = {
    "bootstrap_servers": ...,
    "group_id": ...,
    "auto_offset_reset": "latest" ou "earliest",
    "enable_auto_commit": False,  # Commit manual
    "max_poll_records": 10,
}
```

**Avaliacao:** **BOA PRATICA** - Commit manual permite controle granular.

**GAP:** `max.poll.interval.ms` nao configurado explicitamente (usando padrao Kafka).

---

## 6. Metricas de Resiliencia

### 6.1 Metricas Implementadas (consensus-engine)

```python
consumer_dlq_messages_total = Counter(...)
circuit_breaker_state = Gauge(...)
consumer_consecutive_errors = Gauge(...)
backoff_duration = Histogram(...)
```

**Avaliacao:** **BOA PRATICA** - Visibilidade adequada.

### 6.2 Metricas Faltantes

- Mensagens descartadas (commit com erro sem DLQ)
- Taxa de sucesso por topico
- Latencia end-to-end por mensagem

---

## 7. Recomendacoes de Mitigacao

### 7.1 PRIORIDADE ALTA: Implementar DLQ nos Servicos Criticos

**Servicos:**
1. consensus-engine (plans.ready)
2. orchestrator-dynamic (plans.consensus)
3. guard-agents (execution.tickets)
4. execution-ticket-service (execution.results)

**Acao:**
- Seguir padrao `requirements-engine` (send_to_dlq)
- Criar topicos `{topic}.dlq` para cada topico principal
- Configurar `max_retries_before_dlq`
- Implementar consumer DLQ para analise posterior

**Estimativa:** 3-5 dias por servico

### 7.2 PRIORIDADE ALTA: Adicionar Circuit Breakers

**Servicos:**
1. consensus-engine (gRPC specialists, MongoDB)
2. guard-agents (MongoDB, Kafka)
3. worker-agents (MongoDB, Redis)

**Acao:**
- Usar `neural_hive_resilience.MonitoredCircuitBreaker`
- Configurar `failure_threshold` e `recovery_timeout`
- Implementar fallback adequado (cache, valor padrao)

**Estimativa:** 2-3 dias por servico

### 7.3 PRIORIDADE MEDIA: Padronizar Retry Policies

**Acao:**
- Criar `RetryPolicy` centralizada via `neural_hive_resilience`
- Configurar `max_retries` globalmente
- Implementar exponential backoff com jitter

**Estimativa:** 2 dias

### 7.4 PRIORIDADE MEDIA: Consumer Health Checks

**Acao:**
- Expor metricas de consumer lag
- Implementar alerta para mensagens em DLQ
- Dashboard de mensagens pendentes

**Estimativa:** 2 dias

---

## 8. Matriz de Risco

| Risco | Probabilidade | Impacto | Risco Score | Prioridade |
|-------|--------------|---------|-------------|------------|
| DLQ nao implementada (consensus-engine) | ALTA | ALTO | 9 | CRITICA |
| Circuit breaker ausente (consensus-engine gRPC) | MEDIA | ALTO | 6 | ALTA |
| Retry infinito (guard-agents) | BAIXA | ALTO | 4 | MEDIA |
| Mensagens descartadas (orchestrator) | MEDIA | MEDIO | 4 | MEDIA |
| Falta de metricas DLQ | ALTA | BAIXO | 3 | BAIXA |

---

## 9. evidencias

### 9.1 DLQ nao implementada

**Arquivo:** `services/consensus-engine/src/consumers/plan_consumer.py`
**Linhas:** 120-121

```python
# NOTA: DLQ ainda nao esta implementado. Configuracoes consumer_enable_dlq e
# kafka_dlq_topic sao reservadas para implementacao futura.
```

### 9.2 Circuit breaker ausente em gRPC calls

**Arquivo:** `services/consensus-engine/src/clients/specialists_grpc_client.py`
**Linha:** 77-85 (sem circuit breaker wrapper)

### 9.3 Mensagens descartadas

**Arquivo:** `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`
**Linhas:** 103-104

```python
# Commit mesmo assim para nao bloquear topico
await self.consumer.commit()
```

---

## Conclusao

A analise identificou **gaps significativos** na confiabilidade de mensagens:

1. **DLQ nao funcional** no servico mais critico (consensus-engine)
2. **Circuit breakers** aplicados de forma inconsistente
3. **Retry patterns** variam entre servicos sem padrao centralizado

A biblioteca `neural_hive_resilience` esta disponivel mas **subutilizada**.

**Proximo passo:** Priorizar implementacao de DLQ nos servicos criticos (consensus-engine, orchestrator-dynamic, guard-agents).
