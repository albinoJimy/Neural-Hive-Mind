# Padrao Tópicos Kafka - Neural-Hive-Mind

## Visao Geral

Este documento define a convencao de nomes e configuracao para topicos Kafka utilizados no Neural-Hive-Mind. Seguir este padrao garante:

- Consistencia entre servicos
- Facilidade de descoberta e debug
- Organizacao logica de eventos
- Otimizacao de particionamento

## Convencao de Nomes

### Formato Padrao

```
{service}.{domain}.{entity}.{event}
```

### Componentes

| Componente | Descricao | Exemplos |
|------------|-----------|----------|
| `service` | Nome do servico produtor | `analyst`, `queen`, `consensus` |
| `domain` | Area de negocio | `execution`, `telemetry`, `plans` |
| `entity` | Tipo de entidade (opcional) | `results`, `agent`, `decision` |
| `event` | Tipo de evento | `created`, `updated`, `completed`, `failed` |

### Nomes Reservados

| Prefixo | Uso | Exemplo |
|---------|-----|---------|
| `dlq.` | Dead Letter Queue | `dlq.analyst.execution` |
| `retry.` | Retry topics | `retry.consensus.plans` |
| `internal.` | Eventos internos | `internal.orchestrator.heartbeat` |

## Exemplos de Topicos

### Produtor: Analyst Agents

```python
from neural_hive_api.kafka import KafkaTopicsConfig

class AnalystTopics(KafkaTopicsConfig):
    PREFIX = "analyst"

    # Eventos de execucao
    EXECUTION_STARTED = get_topic("execution", "started")
    EXECUTION_RESULTS = get_topic("execution", "results")
    EXECUTION_FAILED = get_topic("execution", "failed")

    # Eventos de insights
    INSIGHT_CREATED = get_topic("insights", "created")
    INSIGHT_VALIDATED = get_topic("insights", "validated")
```

**Topicos gerados:**
- `analyst.execution.started`
- `analyst.execution.results`
- `analyst.execution.failed`
- `analyst.insights.created`
- `analyst.insights.validated`

### Produtor: Consensus Engine

```python
class ConsensusTopics(KafkaTopicsConfig):
    PREFIX = "consensus"

    # Eventos de planos
    PLAN_CREATED = get_topic("plans", "created")
    PLAN_DECISION = get_topic("plans", "decision")

    # Eventos de feroomono
    PHEROMONE_PUBLISHED = get_topic("pheromone", "published")
```

**Topicos gerados:**
- `consensus.plans.created`
- `consensus.plans.decision`
- `consensus.pheromone.published`

### Produtor: Queen Agent

```python
class QueenTopics(KafkaTopicsConfig):
    PREFIX = "queen"

    # Telemetry
    TELEMETRY_HEARTBEAT = get_topic("telemetry", "heartbeat")
    TELEMETRY_METRICS = get_topic("telemetry", "metrics")
    TELEMETRY_AGGREGATED = get_topic("telemetry", "aggregated")

    # Coordinacao
    COORDINATION_DIRECTIVE = get_topic("coordination", "directive")
```

**Topicos gerados:**
- `queen.telemetry.heartbeat`
- `queen.telemetry.metrics`
- `queen.telemetry.aggregated`
- `queen.coordination.directive`

## Configuracao de Tópicos

### Retention Policy

| Tipo de Topico | Retencao | Justificativa |
|----------------|----------|---------------|
| Eventos de dominio | 7 dias | Audit e reprocessamento |
| Telemetry/Metrics | 1 dia | Dados efemeros |
| DLQ | 30 dias | Investigacao de problemas |
| Retry | 4 horas | Curta duracao |

### Particionamento

**Regra:** Usar a entidade ID como chave de particao

```python
# Correto - particao por agent_id
producer.produce(
    topic="analyst.execution.results",
    key=str(execution.agent_id).encode(),
    value=execution.json()
)

# Incorreto - sem chave (distribuicao aleatoria)
producer.produce(
    topic="analyst.execution.results",
    value=execution.json()
)
```

### Configuracoes Recomendadas

```python
DEFAULT_TOPIC_CONFIG = {
    "partitions": 12,  # Ajustar baseado em throughput
    "replication.factor": 3,  # Para producao
    "cleanup.policy": "delete",
    "retention.ms": 7 * 24 * 60 * 60 * 1000,  # 7 dias
    "compression.type": "lz4",
    "max.message.bytes": 10485760,  # 10MB
}

HIGH_THROUGHPUT_CONFIG = {
    "partitions": 24,
    "replication.factor": 3,
    "cleanup.policy": "delete",
    "retention.ms": 1 * 24 * 60 * 60 * 1000,  # 1 dia
    "compression.type": "lz4",
    "max.message.bytes": 10485760,
}
```

## Schema de Mensagens

### Padrao de Envelope

```json
{
  "event_id": "uuid-v4",
  "event_type": "execution.results",
  "event_version": "1.0",
  "producer": "analyst-agents",
  "timestamp": "2026-04-02T12:00:00Z",
  "correlation_id": "trace-123",
  "causation_id": "previous-event-456",
  "data": {
    "agent_id": "agent-1",
    "execution_id": "exec-123",
    "status": "completed",
    "result": {}
  }
}
```

### Campos Obrigatorios

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `event_id` | string (UUID) | Identificador unico do evento |
| `event_type` | string | Tipo do evento (deve bater com topico) |
| `event_version` | string | Versao do schema |
| `producer` | string | Nome do servico produtor |
| `timestamp` | string (ISO8601) | Timestamp de producao |
| `correlation_id` | string | ID para tracing distribuido |
| `data` | object | Payload do evento |

## Dead Letter Queue (DLQ)

### Configuracao

```python
DLQ_TOPIC_CONFIG = {
    "retention.ms": 30 * 24 * 60 * 60 * 1000,  # 30 dias
    "cleanup.policy": "delete",
}
```

### Estrutura de Mensagem DLQ

```json
{
  "original_topic": "analyst.execution.results",
  "original_partition": 2,
  "original_offset": 12345,
  "failure_timestamp": "2026-04-02T12:00:00Z",
  "error_type": "deserialization",
  "error_message": "Invalid schema",
  "retry_count": 3,
  "original_payload": {}
}
```

## Criacao Automatica de Tópicos

### Via KafkaTopicsConfig

```python
from neural_hive_api.kafka import KafkaTopicsConfig

class MyTopics(KafkaTopicsConfig):
    PREFIX = "myservice"

    EXECUTION_RESULTS = get_topic(
        "execution",
        "results",
        partitions=12,
        replication_factor=3,
        retention_ms=7 * 24 * 60 * 60 * 1000
    )

# Criar topicos no startup
await MyTopics.create_topics()
```

### Via Terraform/Helm

```hcl
resource "kafka_topic" "analyst_execution_results" {
  name               = "analyst.execution.results"
  partitions         = 12
  replication_factor = 3
  retention_ms       = 604800000  # 7 days

  config = {
    "compression.type" = "lz4"
    "cleanup.policy"   = "delete"
  }
}
```

## Consumo

### Consumer Group Naming

```
{service}-consumer-group
```

Exemplos:
- `orchestrator-consumer-group`
- `approval-service-consumer-group`

### Configuracao de Consumo

```python
CONSUMER_CONFIG = {
    "bootstrap.servers": "kafka:9092",
    "group.id": "my-service-consumer-group",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,  # Commit manual
    "max.poll.records": 100,
    "session.timeout.ms": 30000,
}
```

## Boas Praticas

1. **Nomes:** Seguir a convencao rigorosamente
2. **Schemas:** Usar schemas versionados (Avro/JSON Schema)
3. **Chaves:** Sempre fornecer chave para particionamento correto
4. **Compactacao:** NAO usar compactacao (apenas delete)
5. **Monitoring:** Monitorar lag e throughput de cada topico
6. **DLQ:** Sempre configurar DLQ para consumidores criticos

## Referencias

- `libraries/python/neural_hive_api/neural_hive_api/kafka.py`
- Kafka documentation: https://kafka.apache.org/documentation/
