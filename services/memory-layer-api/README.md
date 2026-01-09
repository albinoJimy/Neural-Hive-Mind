# Memory Layer API

API de camada de memória unificada para o Neural Hive Mind, gerenciando dados em múltiplas camadas de armazenamento com roteamento inteligente.

## Camadas de Armazenamento

| Camada     | Tecnologia  | Retenção    | Uso                           |
|------------|-------------|-------------|-------------------------------|
| Hot        | Redis       | 15 min      | Cache de contexto ativo       |
| Warm       | MongoDB     | 30 dias     | Dados operacionais            |
| Cold       | ClickHouse  | 18 meses    | Analytics e histórico         |
| Semântico  | Neo4j       | Permanente  | Grafo de relacionamentos      |

## Funcionalidades

### Roteamento Inteligente

Direciona queries automaticamente para a camada apropriada baseado em:
- Idade dos dados
- Padrão de acesso
- Tipo de operação

### Qualidade de Dados

- **Validação**: Verificação de schema, tipos e ranges
- **Scores**: Completude, precisão, frescor, unicidade, consistência
- **Anomalias**: Detecção estatística via Z-score usando ClickHouse

Documentação completa: [docs/MEMORY_LAYER_DATA_QUALITY.md](../../docs/MEMORY_LAYER_DATA_QUALITY.md)

### Lineage Tracking

Rastreamento de linhagem de dados para auditoria e compliance.

### Sincronização MongoDB → ClickHouse

Sincronização automática de dados operacionais para camada analítica:

- **Real-time**: Via Kafka com schema Avro
- **Batch**: CronJob diário às 2h UTC

Documentação completa: [docs/MEMORY_LAYER_SYNC_ARCHITECTURE.md](../../docs/MEMORY_LAYER_SYNC_ARCHITECTURE.md)

## Configuração

### Variáveis de Ambiente

```bash
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=neural_hive

# Redis
REDIS_CLUSTER_NODES=localhost:6379

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_PASSWORD=secret

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=secret

# Qualidade de Dados
ENABLE_ANOMALY_DETECTION=true
QUALITY_RULES_FILE=/etc/memory-layer/policies/quality-rules.yaml

# Sincronização Kafka
ENABLE_REALTIME_SYNC=true
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_SYNC_TOPIC=memory.sync.events
KAFKA_DLQ_TOPIC=memory.sync.events.dlq
KAFKA_CONSUMER_GROUP=memory-sync-consumer
BATCH_SIZE=1000
```

## Execução

### Desenvolvimento

```bash
cd services/memory-layer-api
pip install -r requirements.txt
python -m src.main
```

### Testes

```bash
pytest tests/ -v

# Com integração ClickHouse
CLICKHOUSE_HOST=localhost pytest tests/test_data_quality_monitor.py -v
```

### Job de Qualidade

```bash
python -m src.jobs.check_data_quality
```

## Métricas

| Métrica                                        | Tipo    | Descrição                    |
|------------------------------------------------|---------|------------------------------|
| `neural_hive_data_quality_score`               | Gauge   | Score de qualidade (0-1)     |
| `memory_data_quality_anomalies_detected_total` | Counter | Anomalias detectadas         |
| `memory_lineage_integrity_checks_total`        | Counter | Verificações de integridade  |
| `memory_sync_events_published_total`           | Counter | Eventos sync publicados      |
| `memory_sync_events_consumed_total`            | Counter | Eventos sync consumidos      |
| `memory_sync_consumer_lag`                     | Gauge   | Lag do consumer Kafka        |
| `memory_sync_dlq_events_total`                 | Counter | Eventos enviados para DLQ    |

## Estrutura

```
src/
├── clients/                    # Clientes para datastores
│   ├── mongodb_client.py
│   ├── redis_client.py
│   ├── clickhouse_client.py
│   ├── neo4j_client.py
│   ├── kafka_sync_producer.py  # Producer Kafka para sync
│   └── unified_memory_client.py
├── consumers/                  # Consumers Kafka
│   └── sync_event_consumer.py
├── services/                   # Lógica de negócio
│   ├── data_quality_monitor.py
│   ├── lineage_tracker.py
│   └── retention_policy_manager.py
├── jobs/                       # Jobs schedulados
│   ├── check_data_quality.py
│   ├── sync_mongodb_to_clickhouse.py
│   └── enforce_retention.py
└── config/
    └── settings.py
```

## Troubleshooting

### Consumer Lag Alto

```bash
# Verificar lag
kubectl exec -it memory-layer-api-pod -- \
  python -c "from src.consumers.sync_event_consumer import SyncEventConsumer; print(SyncEventConsumer.get_lag())"

# Escalar consumer
kubectl scale deployment memory-sync-consumer --replicas=3
```

### DLQ Crescendo

```bash
# Verificar eventos na DLQ
kubectl exec -it kafka-pod -- \
  kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic memory.sync.events.dlq --from-beginning --max-messages 10
```

### Executar Jobs Manualmente

```bash
# Sync batch
kubectl create job --from=cronjob/memory-sync-mongodb-to-clickhouse manual-sync-$(date +%s)

# Retention enforcement
kubectl create job --from=cronjob/memory-cleanup-retention manual-cleanup-$(date +%s)
```
