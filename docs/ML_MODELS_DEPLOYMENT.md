# Deployment de Modelos ML no Neural Hive-Mind

## Visão Geral

O sistema utiliza modelos de Machine Learning para detecção de anomalias e predição de comportamento. Este documento descreve como treinar, deployar e monitorar os modelos.

## Modelos Implementados

### 1. Anomaly Detector (Guard Agents)

**Propósito:** Detectar tickets e eventos anômalos em tempo real.

**Algoritmos Suportados:**

| Algoritmo | Vantagens | Desvantagens | Uso Recomendado |
|-----------|-----------|--------------|-----------------|
| Isolation Forest | Rápido, menor memória | Menos preciso para anomalias sutis | Produção (default) |
| Autoencoder | Maior acurácia, detecta padrões complexos | Mais lento, requer mais recursos | Alta precisão |

## Treinamento

### Pré-requisitos

```bash
# Dependências
pip install neural-hive-ml mlflow scikit-learn tensorflow

# Variáveis de ambiente
export MLFLOW_TRACKING_URI=http://mlflow:5000
export MONGODB_URI=mongodb://localhost:27017/neural_hive
```

### Treinar Modelo

```bash
# Isolation Forest (recomendado)
python ml_pipelines/training/train_predictive_models.py \
  --model-type anomaly \
  --model-algorithm isolation_forest \
  --training-window-days 90 \
  --min-samples 1000 \
  --promote-if-better

# Autoencoder (maior acurácia)
python ml_pipelines/training/train_predictive_models.py \
  --model-type anomaly \
  --model-algorithm autoencoder \
  --training-window-days 90 \
  --min-samples 1000 \
  --promote-if-better
```

### Validar Acurácia

```bash
python ml_pipelines/training/test_model_accuracy.py \
  --mongo-uri mongodb://localhost:27017 \
  --mlflow-uri http://localhost:5000 \
  --model-type isolation_forest \
  --days-back 7
```

**Métricas Esperadas:**
- Precision: > 0.80
- Recall: > 0.75
- F1-Score: > 0.77

## Integração com Serviços

### Guard Agents

O Guard Agent carrega o modelo automaticamente na inicialização:

1. Conecta ao MLflow (`MLFLOW_TRACKING_URI`)
2. Carrega modelo em "Production"
3. Inicializa `AnomalyDetector`
4. Passa para `ThreatDetector`

**Configuração (`services/guard-agents/.env`):**

```bash
# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Anomaly Detection
ANOMALY_DETECTOR_ENABLED=true
ANOMALY_DETECTOR_MODEL_TYPE=isolation_forest
ANOMALY_DETECTOR_CONTAMINATION=0.05
```

### Queen Agent

Queries reais implementadas para métricas:

| Componente | Fonte | Query |
|------------|-------|-------|
| Workflow success rate | Prometheus | `rate(temporal_workflow_completed_total{status="COMPLETED"}[5m])` |
| Active plans | Neo4j | `MATCH (p:CognitivePlan) WHERE p.status = 'ACTIVE'` |
| Historical success rate | MongoDB/Neo4j | Agregação de decisões dos últimos 7 dias |
| SLA violations | Prometheus | Serviços com taxa de sucesso < 95% |
| Critical incidents | MongoDB | Incidentes não resolvidos com severidade CRITICAL/HIGH |

## Monitoramento

### Métricas Prometheus

```promql
# Taxa de detecção de anomalias
rate(guard_agent_anomalies_detected_total[5m])

# Latência de inferência
histogram_quantile(0.95, rate(ml_inference_duration_seconds_bucket[5m]))

# Taxa de sucesso de workflows
sum(rate(temporal_workflow_completed_total{status="COMPLETED"}[5m])) /
sum(rate(temporal_workflow_completed_total[5m]))
```

### Logs Estruturados

```bash
# Guard Agent - Detecção ML
kubectl logs -f deployment/guard-agents -n neural-hive | grep anomaly_detector

# Queen Agent - Workflow metrics
kubectl logs -f deployment/queen-agent -n neural-hive | grep workflow_success_rate
```

## Retraining

Modelos devem ser retreinados periodicamente:

| Modelo | Frequência | Motivo |
|--------|------------|--------|
| Anomaly Detector | Semanal | Padrões de uso evoluem |
| Load Predictor | Diário | Carga varia frequentemente |
| Scheduling Predictor | Semanal | Comportamento de execução |

### CronJob Kubernetes

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: retrain-anomaly-detector
  namespace: neural-hive
spec:
  schedule: "0 2 * * 0"  # Domingo 2AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: trainer
            image: neural-hive/ml-trainer:latest
            command:
            - python
            - ml_pipelines/training/train_predictive_models.py
            - --model-type=anomaly
            - --promote-if-better
            env:
            - name: MLFLOW_TRACKING_URI
              value: http://mlflow:5000
            - name: MONGODB_URI
              valueFrom:
                secretKeyRef:
                  name: mongodb-credentials
                  key: uri
          restartPolicy: OnFailure
```

## Troubleshooting

### Modelo não carrega

**Sintoma:** `anomaly_detector_no_model_loaded` no log

**Soluções:**
1. Verificar MLflow está acessível: `curl http://mlflow:5000/api/2.0/mlflow/experiments/list`
2. Confirmar modelo em "Production": UI MLflow ou `mlflow.search_model_versions`
3. Verificar permissões de rede entre Guard Agent e MLflow

### Baixa acurácia

**Sintoma:** F1-Score < 0.70

**Soluções:**
1. Retreinar com mais dados (`--training-window-days 180`)
2. Ajustar `contamination` (0.03 para menos anomalias, 0.10 para mais)
3. Considerar trocar para Autoencoder
4. Revisar feature engineering em `feature_engineering.py`

### Alta latência

**Sintoma:** Inferência > 100ms

**Soluções:**
1. Usar Isolation Forest (mais rápido que Autoencoder)
2. Reduzir número de features
3. Adicionar cache Redis para tickets similares
4. Escalar horizontalmente Guard Agents

### Falsos positivos excessivos

**Sintoma:** Muitos alertas para tickets normais

**Soluções:**
1. Aumentar threshold de detecção (`anomaly_score_threshold > 0.8`)
2. Reduzir `contamination` (ex: 0.03)
3. Analisar padrões de falsos positivos para ajustar heurísticas

## Arquitetura

```
┌─────────────────┐      ┌─────────────┐
│   MLflow        │◄─────│  Training   │
│   Registry      │      │  Pipeline   │
└────────┬────────┘      └─────────────┘
         │
         │ Carrega modelo
         ▼
┌─────────────────┐      ┌─────────────┐
│   Guard Agent   │◄─────│   Kafka     │
│   + Anomaly     │      │   Events    │
│   Detector      │      └─────────────┘
└────────┬────────┘
         │
         │ Detecta anomalias
         ▼
┌─────────────────┐      ┌─────────────┐
│   Queen Agent   │◄─────│  Prometheus │
│   + Strategic   │      │  Neo4j      │
│   Decisions     │      │  MongoDB    │
└─────────────────┘      └─────────────┘
```

## Referências

- [MLflow Model Registry](https://mlflow.org/docs/latest/model-registry.html)
- [Isolation Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)
- [neural_hive_ml Library](/libraries/python/neural_hive_ml)
