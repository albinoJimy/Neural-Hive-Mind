# Arquitetura de Sincronização Memory Layer

## Visão Geral

Arquitetura de sincronização MongoDB→ClickHouse com dois caminhos:
- **Real-time** via Kafka
- **Batch** via CronJob

## Componentes

### 1. Sincronização Real-time (Kafka)

| Componente | Arquivo | Descrição |
|------------|---------|-----------|
| Producer | `src/clients/kafka_sync_producer.py` | Publica eventos de sync |
| Consumer | `src/consumers/sync_event_consumer.py` | Consome e processa eventos |
| Topic | `memory.sync.events` | Tópico principal de eventos |
| Schema | `schemas/memory-sync-event.avsc` | Schema Avro |

### 2. Sincronização Batch (CronJob)

| Componente | Arquivo | Descrição |
|------------|---------|-----------|
| Job | `src/jobs/sync_mongodb_to_clickhouse.py` | Job de sync batch |
| Schedule | `0 2 * * *` | Diariamente às 2h UTC |
| Batch Size | 1000 documentos | Por iteração |

### 3. Políticas de Retenção

| Componente | Arquivo | Descrição |
|------------|---------|-----------|
| Manager | `src/services/retention_policy_manager.py` | Gerencia políticas |
| Job | `src/jobs/enforce_retention.py` | Aplica políticas |
| Schedule | `0 3 * * *` | Diariamente às 3h UTC |

## Fluxos

### Fluxo de Sincronização Real-time

```
┌─────────────────┐     ┌───────────────────┐     ┌─────────────┐
│ UnifiedMemory   │────▶│ KafkaSyncProducer │────▶│   Kafka     │
│    Client       │     │  (Avro/JSON)      │     │  Topic      │
└─────────────────┘     └───────────────────┘     └──────┬──────┘
       │                                                  │
       │ save()                                          │
       ▼                                                  ▼
┌─────────────────┐                              ┌─────────────────┐
│    MongoDB      │                              │ SyncEventConsumer│
│  (operacional)  │                              │  (idempotente)   │
└─────────────────┘                              └────────┬─────────┘
                                                          │
                                                          ▼
                                            ┌─────────────────────┐
                                            │     ClickHouse      │
                                            │    (histórico)      │
                                            └─────────────────────┘
```

### Fluxo de Sincronização Batch

```
┌─────────────────┐     ┌───────────────────┐     ┌─────────────────┐
│   CronJob K8s   │────▶│ MongoToClickhouse │────▶│   ClickHouse    │
│  (diário 2h)    │     │     Sync Job      │     │  (batch insert) │
└─────────────────┘     └───────────────────┘     └─────────────────┘
                               │
                               │ find() últimas 24h
                               ▼
                        ┌─────────────────┐
                        │    MongoDB      │
                        │  (operacional)  │
                        └─────────────────┘
```

## Idempotência

### Cache In-Memory

```python
# LRU Cache com 10.000 IDs
idempotency_cache = LRUCache(maxsize=10000)

def is_processed(event_id: str) -> bool:
    if event_id in idempotency_cache:
        return True
    return False
```

### Verificação ClickHouse

```sql
SELECT count(*) FROM operational_context_history
WHERE entity_id = {entity_id}
AND created_at = {timestamp}
```

## Dead Letter Queue

### Fluxo de Falhas

```
Evento ─▶ Retry 1 ─▶ Retry 2 ─▶ Retry 3 ─▶ DLQ
           │          │          │
           ▼          ▼          ▼
         1s         2s         4s (exponential backoff)
```

### Tópico DLQ
- **Tópico:** `memory.sync.events.dlq`
- **Formato:** Evento original + metadados de erro
- **Retenção:** 7 dias

## Métricas Prometheus

### Producer
| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `memory_sync_events_published_total` | Counter | Eventos publicados |
| `memory_sync_publish_latency_seconds` | Histogram | Latência de publicação |

### Consumer
| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `memory_sync_events_consumed_total` | Counter | Eventos consumidos |
| `memory_sync_consume_latency_seconds` | Histogram | Latência de consumo |
| `memory_sync_consumer_lag` | Gauge | Lag por partição |
| `memory_sync_dlq_events_total` | Counter | Eventos enviados para DLQ |
| `memory_sync_duplicate_events_skipped_total` | Counter | Duplicatas ignoradas |

## Configuração

### Variáveis de Ambiente

```bash
# Habilitação
ENABLE_REALTIME_SYNC=true

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_SYNC_TOPIC=memory.sync.events
KAFKA_DLQ_TOPIC=memory.sync.events.dlq
KAFKA_CONSUMER_GROUP=memory-sync-consumer
KAFKA_SECURITY_PROTOCOL=SASL_SSL

# Batch
BATCH_SIZE=1000
SYNC_LOOKBACK_HOURS=24
```

## Troubleshooting

### Consumer Lag Alto

**Sintoma:** `memory_sync_consumer_lag > 1000`

**Causas:**
1. ClickHouse lento
2. Consumer com poucos recursos
3. Pico de eventos

**Soluções:**
1. Escalar consumer horizontalmente
2. Aumentar batch size
3. Verificar performance do ClickHouse

### DLQ Crescendo

**Sintoma:** `memory_sync_dlq_events_total` aumentando

**Causas:**
1. ClickHouse indisponível
2. Schema incompatível
3. Dados inválidos

**Soluções:**
1. Verificar conexão ClickHouse
2. Validar schema Avro
3. Analisar eventos na DLQ

### Sync Latency Alta

**Sintoma:** `memory_sync_publish_latency_seconds_p95 > 5s`

**Causas:**
1. Kafka sobrecarregado
2. Network issues
3. Serialização lenta

**Soluções:**
1. Verificar métricas do Kafka
2. Diagnosticar rede
3. Otimizar serialização Avro

## Schema Avro

```json
{
  "type": "record",
  "name": "MemorySyncEvent",
  "namespace": "com.neuralhive.memory",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "entity_id", "type": "string"},
    {"name": "data_type", "type": "string"},
    {"name": "operation", "type": {"type": "enum", "name": "Operation", "symbols": ["INSERT", "UPDATE", "DELETE"]}},
    {"name": "collection", "type": "string"},
    {"name": "timestamp", "type": "long"},
    {"name": "data", "type": "string"},
    {"name": "metadata", "type": ["null", "string"]}
  ]
}
```

## Alertas

### Configuração Prometheus

```yaml
groups:
  - name: memory-sync-alerts
    rules:
      - alert: HighConsumerLag
        expr: memory_sync_consumer_lag > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Consumer lag alto no memory sync"

      - alert: HighDLQRate
        expr: rate(memory_sync_dlq_events_total[5m]) / rate(memory_sync_events_consumed_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Taxa de DLQ acima de 5%"

      - alert: SyncLatencyHigh
        expr: histogram_quantile(0.95, rate(memory_sync_publish_latency_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Latência P95 de sync acima de 5s"
```
