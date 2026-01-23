# Guia de Operacoes ML - Neural Hive-Mind

## Arquitetura do Pipeline ML

```
┌─────────────────┐    ┌──────────────────────────┐    ┌─────────────────┐
│  MongoDB/       │───▶│  train_predictive_       │───▶│  MLflow         │
│  ClickHouse     │    │  models.py               │    │  Registry       │
│  (Dados Hist.)  │    │                          │    │  (Production)   │
└─────────────────┘    └──────────────────────────┘    └────────┬────────┘
                                                                 │
                                                                 ▼
┌─────────────────┐    ┌──────────────────────────┐    ┌─────────────────┐
│  DriftDetector  │◀───│  guard-agents            │◀───│  Modelo         │
│  (Evidently)    │    │  ThreatDetector          │    │  Carregado      │
└────────┬────────┘    └──────────────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────────────┐
│  drift_         │───▶│  Retreinamento           │
│  triggered_     │    │  Automatico              │
│  retraining.py  │    │                          │
└─────────────────┘    └──────────────────────────┘
```

## Modelos Disponiveis

| Modelo | Algoritmo | Finalidade | Metricas Chave |
|--------|-----------|------------|----------------|
| `anomaly-detector-isolation_forest` | IsolationForest | Detecta tickets anomalos | F1 > 0.65, Precision > 0.75 |
| `load-predictor-60m` | Prophet | Previsao de carga (1h) | MAPE < 20% |
| `load-predictor-360m` | Prophet | Previsao de carga (6h) | MAPE < 25% |
| `load-predictor-1440m` | Prophet | Previsao de carga (24h) | MAPE < 30% |
| `scheduling-predictor-xgboost` | XGBoost | Previsao de duracao | MAE < 5000ms |

## Treinamento Inicial

### Pre-requisitos

1. MongoDB executando com dados historicos em `execution_tickets`
2. MLflow Tracking Server acessivel
3. (Opcional) ClickHouse para dados de alta performance

### Execucao

```bash
cd ml_pipelines/training

# Configurar variaveis de ambiente
export MONGODB_URI="mongodb://user:pass@mongodb:27017"
export MLFLOW_TRACKING_URI="http://mlflow:5000"
export CLICKHOUSE_HOST="clickhouse"  # Opcional

# Executar treinamento inicial
./train_initial_models.sh

# Modo dry-run (apenas validacao)
./train_initial_models.sh --dry-run
```

### Verificacao

Apos treinamento, verifique os modelos no MLflow:

```bash
# Via CLI
mlflow models list

# Ou via Python
from mlflow.tracking import MlflowClient
client = MlflowClient()
for model in ['anomaly-detector-isolation_forest', 'scheduling-predictor-xgboost']:
    versions = client.get_latest_versions(model, stages=['Production'])
    print(f"{model}: v{versions[0].version if versions else 'N/A'}")
```

## Monitoramento

### Metricas Prometheus

As seguintes metricas sao exportadas pelo `guard-agents`:

```promql
# Taxa de deteccao de anomalias
anomaly_detection_total{model_type, is_anomaly}

# Latencia de inferencia
anomaly_detection_latency_seconds{model_type, quantile}

# Drift score
model_drift_score{model_name}

# Eventos de retreinamento
ml_retraining_events_total{model_type, success}
```

### Dashboards Grafana

- **Predictive Models Dashboard**: Visao geral de todos os modelos
  - Latencia P50/P95/P99
  - Taxa de anomalias detectadas
  - MAPE de predicoes de carga
  - Versoes de modelos ativos

- **Drift Monitoring**: Monitoramento de drift
  - Drift score ao longo do tempo
  - Features com maior drift
  - Historico de retreinamentos

- **ML SLOs Dashboard**: SLOs e Error Budgets de ML
  - Compliance de F1 Score, Latencia, Feedback, Uptime
  - Error budget consumption
  - Burn rate alerting
  - Acesso: `/d/ml-slos-dashboard/ml-slos`

## Service Level Objectives (SLOs)

Os modelos ML possuem 4 SLOs criticos:

| SLO | Target | Janela | Metrica |
|-----|--------|--------|---------|
| F1 Score | >= 0.75 | 7d | `neural_hive:slo:ml_f1_score:7d` |
| Latencia P95 | < 100ms | 24h | `neural_hive:slo:ml_latency_p95_total:5m` |
| Feedback Rate | >= 10% | 7d | `neural_hive:slo:ml_feedback_rate:7d` |
| Uptime | >= 99.5% | 30d | `neural_hive:slo:ml_availability:30d` |

### Alertas de SLO

Alertas configurados em `prometheus-rules/ml-slo-alerts.yaml`:

- **Critical**: F1 Score SLO Breach, Error Budget Fast Burn, Uptime Critical
- **Warning**: Latency SLO Breach, Feedback Rate Low, Error Budget Slow Burn

### Acoes em Violacao

#### F1 Score < 0.75
```bash
# Verificar drift
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic | grep drift

# Analisar distribuicao de predicoes
curl -s "http://prometheus:9090/api/v1/query?query=neural_hive_mlflow_model_f1" | jq

# Considerar retreinamento
python train_predictive_models.py --model-type all --promote-if-better
```

#### Latencia P95 > 100ms
```bash
# Verificar recursos dos pods
kubectl top pods -n neural-hive-orchestration

# Verificar cache MLflow
kubectl logs -n mlflow -l app=mlflow-server | grep cache

# Escalar se necessario
kubectl scale deployment orchestrator-dynamic -n neural-hive-orchestration --replicas=3
```

#### Feedback Rate < 10%
```bash
# Verificar API de feedback
curl -s "http://approval-service:8000/api/v1/feedback/health"

# Verificar taxa atual
curl -s "http://prometheus:9090/api/v1/query?query=neural_hive:slo:ml_feedback_rate:7d" | jq
```

Para documentacao completa de SLOs: `docs/slos/ml-models.md`

## Retreinamento

### Automatico (Drift-Triggered)

O CronJob `drift-retraining` verifica drift a cada 6 horas:

```yaml
# k8s/jobs/drift-retraining-cronjob.yaml
schedule: "0 */6 * * *"  # A cada 6 horas
```

Condicoes para retreinamento:
- `drift_detected = True`
- `drift_score > 0.2` (threshold configuravel)

### Manual

```bash
# Retreinar modelo especifico
python train_predictive_models.py \
    --model-type anomaly \
    --promote-if-better \
    --training-window-days 90

# Retreinar todos os modelos
python train_predictive_models.py \
    --model-type all \
    --hyperparameter-tuning \
    --promote-if-better
```

### Periodico

O CronJob `ml-model-training` executa semanalmente:

```yaml
# k8s/jobs/ml-training-cronjob.yaml
schedule: "0 2 * * 0"  # Domingo 2AM
```

## Troubleshooting

### Modelo nao carrega

**Sintoma**: `guard-agents` loga "Failed to load model from MLflow"

**Causas possiveis**:
1. Modelo nao registrado no MLflow
2. Nenhuma versao em Production
3. Conexao com MLflow falhou

**Solucao**:
```bash
# Verificar modelos registrados
mlflow models list --filter "name LIKE 'anomaly%'"

# Verificar stage Production
python -c "
from mlflow.tracking import MlflowClient
client = MlflowClient()
versions = client.get_latest_versions('anomaly-detector-isolation_forest', stages=['Production'])
print('Production versions:', [v.version for v in versions])
"

# Se nao houver versao em Production, promover manualmente
python train_predictive_models.py --model-type anomaly --promote-if-better
```

### Drift falso positivo

**Sintoma**: Alertas frequentes de drift sem mudanca real nos dados

**Causas possiveis**:
1. Threshold muito baixo
2. Janela de referencia desatualizada
3. Sazonalidade nao considerada

**Solucao**:
```bash
# Aumentar threshold
export DRIFT_THRESHOLD=0.25  # Padrao: 0.2

# Atualizar dados de referencia
python -c "
from neural_hive_specialists.drift_monitoring.evidently_monitor import EvidentlyMonitor
monitor = EvidentlyMonitor(config)
monitor.update_reference_data()
"
```

### Metricas abaixo do threshold

**Sintoma**: Modelo treinado tem F1 < 0.65 ou Precision < 0.75

**Causas possiveis**:
1. Dados de treinamento insuficientes
2. Desbalanceamento de classes
3. Features nao informativas

**Solucao**:
```bash
# Aumentar janela de treinamento
python train_predictive_models.py \
    --model-type anomaly \
    --training-window-days 365 \
    --min-samples 5000

# Ativar tuning de hiperparametros
python train_predictive_models.py \
    --model-type anomaly \
    --hyperparameter-tuning \
    --promote-if-better
```

### Latencia de inferencia alta

**Sintoma**: P95 > 100ms

**Causas possiveis**:
1. Modelo muito complexo
2. Feature engineering lento
3. Cache nao configurado

**Solucao**:
- Verificar tamanho do modelo
- Habilitar cache de features no Redis
- Considerar modelo mais simples (IsolationForest vs Autoencoder)

## Configuracao de Ambiente

### Variaveis de Ambiente

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `MONGODB_URI` | URI do MongoDB | `mongodb://localhost:27017` |
| `MLFLOW_TRACKING_URI` | URI do MLflow | `http://localhost:5000` |
| `CLICKHOUSE_HOST` | Host do ClickHouse | `localhost` |
| `DRIFT_THRESHOLD` | Threshold para retreinamento | `0.2` |
| `DRIFT_CHECK_INTERVAL_MINUTES` | Intervalo de verificacao | `60` |

### Secrets Kubernetes

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ml-training-secrets
  namespace: neural-hive-ml
type: Opaque
stringData:
  mongodb_uri: "mongodb://user:pass@mongodb:27017"
  mlflow_tracking_uri: "http://mlflow:5000"
  clickhouse_user: "default"
  clickhouse_password: ""
```

## Validacao E2E

Para validar o pipeline completo:

```bash
# Executar teste E2E
pytest tests/e2e/test_ml_pipeline_e2e.py -v

# Checklist manual:
# 1. Treinar modelo
# 2. Verificar registro no MLflow
# 3. Reiniciar guard-agents
# 4. Enviar evento de teste
# 5. Verificar deteccao
# 6. Checar metricas Prometheus
```

## Contatos

- **Time ML**: ml-platform@neural-hive.io
- **Alertas**: #alerts-ml-pipeline (Slack)
- **Documentacao**: https://docs.neural-hive.io/ml-operations
