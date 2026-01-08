# Qualidade de Dados - Memory Layer

## Visão Geral

O sistema de qualidade de dados do Memory Layer monitora e valida a integridade, completude e frescor dos dados armazenados nas diferentes camadas de memória (Redis, MongoDB, ClickHouse).

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    Data Quality Monitor                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Validação   │  │ Cálculo de  │  │ Detecção de Anomalias   │  │
│  │ de Schema   │  │ Scores      │  │ (Z-score)               │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    Fontes de Dados                               │
│  ┌─────────────────────┐     ┌─────────────────────────────┐    │
│  │ ClickHouse          │     │ MongoDB                     │    │
│  │ (Estatísticas       │────▶│ (Fallback para baseline)    │    │
│  │  agregadas)         │     │                             │    │
│  └─────────────────────┘     └─────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes

### DataQualityMonitor

Classe principal que implementa:

- **Validação de dados**: Verifica campos obrigatórios, tipos e ranges
- **Cálculo de scores**: Completude, precisão, frescor, unicidade, consistência
- **Detecção de anomalias**: Identificação estatística via Z-score

### DataQualityChecker (Job)

Job executado como CronJob que:

- Roda a cada 6 horas
- Carrega regras de qualidade do ConfigMap YAML
- Verifica todas as coleções do MongoDB
- Publica métricas para Prometheus

## Dimensões de Qualidade

| Dimensão       | Descrição                                      | Peso    |
|----------------|------------------------------------------------|---------|
| Completude     | % de campos não-nulos                          | 25%     |
| Precisão       | % de registros válidos                         | 25%     |
| Frescor        | % de registros dentro do threshold de idade    | 20%     |
| Unicidade      | % de entity_ids únicos                         | 15%     |
| Consistência   | % de campos comuns entre registros             | 15%     |

## Detecção de Anomalias

### Algoritmo

Utiliza Z-score para detectar valores atípicos:

```
Z-score = (valor_atual - média_baseline) / desvio_padrão_baseline
```

Anomalia detectada quando `|Z-score| > 3`

### Classificação de Severidade

| Z-score    | Severidade |
|------------|------------|
| > 5        | high       |
| 4 - 5      | medium     |
| 3 - 4      | low        |

### Fontes de Baseline

1. **ClickHouse (primária)**: Estatísticas agregadas (avg, stddevPop)
2. **MongoDB (fallback)**: Cálculo manual quando ClickHouse indisponível

## Configuração

### Variáveis de Ambiente

```bash
# Habilitar detecção de anomalias
ENABLE_ANOMALY_DETECTION=true

# Janela de análise (horas)
ANOMALY_WINDOW_HOURS=24

# Período de baseline (dias)
ANOMALY_BASELINE_DAYS=7

# Caminho do arquivo de regras
QUALITY_RULES_FILE=/etc/memory-layer/policies/quality-rules.yaml
```

### Arquivo de Regras (quality-rules.yaml)

```yaml
version: '1.0'
rules:
  completeness:
    enabled: true
    threshold: 0.95
    required_fields:
      - intent_id
      - timestamp
      - source
  accuracy:
    enabled: true
    threshold: 0.95
  freshness:
    enabled: true
    max_age_hours: 24
```

## Métricas Prometheus

| Métrica                                      | Tipo    | Descrição                          |
|----------------------------------------------|---------|-------------------------------------|
| `neural_hive_data_quality_score`             | Gauge   | Score geral (0-1) por tipo de dado  |
| `memory_data_quality_anomalies_detected_total` | Counter | Total de anomalias por severidade   |
| `memory_lineage_integrity_checks_total`      | Counter | Verificações de integridade         |

## Testes

### Testes Unitários

```bash
cd services/memory-layer-api
pytest tests/test_data_quality_monitor.py -v
```

### Testes de Integração com ClickHouse

```bash
# Requer ClickHouse disponível
CLICKHOUSE_HOST=localhost \
CLICKHOUSE_PASSWORD=secret \
pytest tests/test_data_quality_monitor.py::TestClickHouseIntegration -v
```

## Dashboard Grafana

Painel disponível em `monitoring/dashboards/memory-layer-data-quality.json`:

- Health status de Redis, MongoDB, Neo4j, ClickHouse
- Data Quality Score (gauge)
- Redis Cache Hit Rate
- Latências de operações MongoDB e Neo4j
- Anomalias detectadas por severidade
- Lineage Integrity Success Rate
- Distribuição de falhas de integridade

## Troubleshooting

### Anomalias não detectadas

1. Verificar se `ENABLE_ANOMALY_DETECTION=true`
2. Verificar se há dados históricos suficientes (mínimo 10 documentos)
3. Verificar conexão com ClickHouse

### Score de qualidade baixo

1. Verificar campos obrigatórios em `quality-rules.yaml`
2. Analisar métricas por dimensão no dashboard
3. Verificar frescor dos dados (documentos antigos)

### ClickHouse fallback para MongoDB

1. Verificar conectividade com ClickHouse
2. Verificar se tabela `data_quality_metrics` existe
3. Consultar logs por warnings de fallback
