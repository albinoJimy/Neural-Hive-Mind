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

## Estrutura

```
src/
├── clients/           # Clientes para datastores
│   ├── mongodb_client.py
│   ├── redis_client.py
│   ├── clickhouse_client.py
│   └── neo4j_client.py
├── services/          # Lógica de negócio
│   ├── data_quality_monitor.py
│   └── lineage_tracker.py
├── jobs/              # Jobs schedulados
│   └── check_data_quality.py
└── config/
    └── settings.py
```
