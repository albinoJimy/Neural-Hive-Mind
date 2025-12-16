# Drift Monitoring Guide - Neural Hive Mind

Sistema de monitoramento contínuo de drift em modelos ML para detecção precoce de degradação e retreinamento automático.

## Visão Geral

O sistema de drift monitoring detecta mudanças na distribuição de dados e degradação de performance dos modelos ML de scheduling do orchestrator. Quando drift significativo é detectado, o sistema pode disparar retreinamento automático para manter a qualidade das predições.

## Arquitetura

### Componentes

1. **DriftDetector** (`services/orchestrator-dynamic/src/ml/drift_detector.py`)
   - Detecta três tipos de drift:
     - **Feature Drift**: PSI (Population Stability Index) > 0.25
     - **Prediction Drift**: MAE ratio (atual/treino) > 1.5
     - **Target Drift**: K-S test p-value < 0.05
   - Salva baselines em MongoDB (`ml_feature_baselines` collection)

2. **drift_job.py** (`services/orchestrator-dynamic/src/ml/drift_job.py`)
   - Job standalone executado via CronJob Kubernetes
   - Publica métricas no Prometheus Pushgateway
   - Logs estruturados em JSON

3. **auto_retrain.py** (`ml_pipelines/monitoring/auto_retrain.py`)
   - Orquestra retreinamento automático
   - Usa `ModelPerformanceMonitor` para detectar degradação
   - Dispara training via `RetrainingTrigger`
   - Envia notificações (Slack/Email)

4. **ModelPerformanceMonitor** (`ml_pipelines/monitoring/model_performance_monitor.py`)
   - Consulta métricas do MLflow (precision, recall, F1)
   - Consulta estatísticas de feedback do MongoDB
   - Calcula score agregado de performance
   - Detecta degradação baseado em thresholds

### Fluxo de Detecção e Retreinamento

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CronJob       │────>│  drift_job.py   │────>│  DriftDetector  │
│  (3 AM UTC)     │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┤
                        │                                │
                        v                                v
                ┌───────────────┐              ┌─────────────────┐
                │   MongoDB     │              │   Prometheus    │
                │  (baselines)  │              │  (pushgateway)  │
                └───────────────┘              └─────────────────┘
                        │
                        │ Se drift crítico
                        v
                ┌─────────────────┐     ┌─────────────────┐
                │  auto_retrain   │────>│ RetrainingTrigger│
                │  .py            │     │                 │
                └─────────────────┘     └────────┬────────┘
                        │                        │
                        v                        v
                ┌─────────────────┐     ┌─────────────────┐
                │   Slack/Email   │     │     MLflow      │
                │  Notifications  │     │   Training Run  │
                └─────────────────┘     └─────────────────┘
```

## Tipos de Drift

### 1. Feature Drift (PSI)

Population Stability Index mede mudanças na distribuição das features de entrada.

**Fórmula:**
```
PSI = Σ (actual_pct - expected_pct) * ln(actual_pct / expected_pct)
```

**Interpretação:**
| PSI Range | Interpretação |
|-----------|---------------|
| < 0.10    | Sem mudança significativa |
| 0.10-0.25 | Mudança moderada - monitorar |
| > 0.25    | Mudança significativa - investigar/retreinar |

**Features monitoradas:**
- `risk_weight`: Peso de risco do ticket
- `capabilities_count`: Número de capabilities requeridas
- `parameters_count`: Número de parâmetros
- `qos_delivery_mode`: Modo de entrega QoS
- `qos_consistency`: Nível de consistência QoS

### 2. Prediction Drift (MAE Ratio)

Compara Mean Absolute Error atual com o MAE do treino.

**Fórmula:**
```
drift_ratio = MAE_atual / MAE_treino
```

**Interpretação:**
| Drift Ratio | Interpretação |
|-------------|---------------|
| < 1.2       | Performance estável |
| 1.2-1.5     | Degradação moderada - monitorar |
| > 1.5       | Degradação crítica - retreinar urgente |

### 3. Target Drift (K-S Test)

Kolmogorov-Smirnov test compara distribuição do target (actual_duration_ms).

**Interpretação:**
| p-value | Interpretação |
|---------|---------------|
| > 0.05  | Distribuições similares |
| < 0.05  | Distribuições significativamente diferentes |
| < 0.01  | Drift crítico |

## Thresholds e Configuração

### Thresholds de Drift

| Métrica | Threshold | Descrição |
|---------|-----------|-----------|
| PSI (Feature Drift) | 0.25 | PSI > 0.25 indica mudança significativa na distribuição de features |
| MAE Ratio (Prediction Drift) | 1.5 | MAE atual / MAE treino > 1.5 indica degradação de 50%+ |
| K-S p-value (Target Drift) | 0.05 | p-value < 0.05 indica distribuição de target mudou significativamente |

### Configuração do CronJob

```yaml
# helm-charts/orchestrator-dynamic/values.yaml
config:
  ml:
    drift:
      enabled: true
      checkWindowDays: 7
      psiThreshold: 0.25
      maeRatioThreshold: 1.5
      ksPvalueThreshold: 0.05
      cronSchedule: "0 3 * * *"  # Diário às 3 AM UTC
```

### Variáveis de Ambiente

```bash
ML_DRIFT_DETECTION_ENABLED=true
ML_DRIFT_CHECK_WINDOW_DAYS=7
ML_DRIFT_PSI_THRESHOLD=0.25
ML_DRIFT_MAE_RATIO_THRESHOLD=1.5
ML_DRIFT_KS_PVALUE_THRESHOLD=0.05
PROMETHEUS_PUSHGATEWAY_URL=http://prometheus-pushgateway.monitoring.svc.cluster.local:9091
```

### Thresholds de Performance (ModelPerformanceMonitor)

| Métrica | Threshold | Peso |
|---------|-----------|------|
| Precision | 0.75 | - |
| Recall | 0.70 | - |
| F1 Score | 0.72 | - |
| Feedback Avg | 0.60 | - |
| MLflow Weight | - | 0.7 |
| Feedback Weight | - | 0.3 |

**Score Agregado:**
```
aggregate_score = (mlflow_f1 * 0.7) + (feedback_avg * 0.3)
```

## Operação

### Monitoramento via Prometheus

**Queries úteis:**

```promql
# Status geral de drift (0=ok, 1=warning, 2=critical)
orchestration_ml_drift_overall_status

# PSI máximo entre features
orchestration_ml_drift_feature_max_psi

# Ratio MAE (atual/treino)
orchestration_ml_drift_prediction_ratio

# P-value K-S test
orchestration_ml_drift_target_pvalue

# Timestamp do último check
orchestration_ml_drift_check_timestamp

# Auto-retrain triggered
neural_hive_auto_retrain_triggered_total

# Model performance score
neural_hive_model_performance_score
```

**Alertas recomendados:**

```yaml
groups:
  - name: ml_drift
    interval: 5m
    rules:
      - alert: MLDriftCritical
        expr: orchestration_ml_drift_overall_status == 2
        for: 10m
        labels:
          severity: critical
          component: ml-drift-detection
        annotations:
          summary: "Drift crítico detectado em modelos ML"
          description: "Status de drift está em nível crítico. Retreinamento urgente recomendado."

      - alert: MLDriftWarning
        expr: orchestration_ml_drift_overall_status == 1
        for: 30m
        labels:
          severity: warning
          component: ml-drift-detection
        annotations:
          summary: "Drift moderado detectado em modelos ML"
          description: "Status de drift está em nível de warning. Monitorar e considerar retreinamento."

      - alert: MLModelDegraded
        expr: neural_hive_model_degradation_detected == 1
        for: 15m
        labels:
          severity: warning
          component: ml-performance
        annotations:
          summary: "Degradação de modelo detectada"
          description: "Performance do modelo {{ $labels.specialist_type }} está abaixo dos thresholds."
```

### Verificação Manual de Drift

```bash
# Executar job manualmente
kubectl create job --from=cronjob/orchestrator-dynamic-ml-drift \
  manual-drift-check-$(date +%s) \
  -n neural-hive-orchestration

# Ver logs
kubectl logs -n neural-hive-orchestration job/manual-drift-check-<timestamp> -f

# Verificar baselines no MongoDB
kubectl exec -it mongodb-0 -n mongodb-cluster -- mongosh
> use neural_hive_orchestration
> db.ml_feature_baselines.find().sort({timestamp: -1}).limit(1).pretty()

# Verificar métricas no Pushgateway
kubectl port-forward -n monitoring svc/prometheus-pushgateway 9091:9091
curl http://localhost:9091/metrics | grep orchestration_ml_drift
```

### Retreinamento Manual

```bash
# Via auto_retrain.py
cd ml_pipelines/monitoring
python auto_retrain.py \
  --specialist-type technical \
  --force \
  --notification-channels slack,email

# Todos os specialists
python auto_retrain.py \
  --specialist-type all \
  --force

# Dry-run (simular sem executar)
python auto_retrain.py \
  --specialist-type technical \
  --dry-run

# Usando datasets existentes (skip generation)
python auto_retrain.py \
  --specialist-type technical \
  --skip-dataset-generation
```

### Verificar Performance do Modelo

```bash
cd ml_pipelines/monitoring
python model_performance_monitor.py \
  --specialist-type technical \
  --output-format json \
  --export-metrics http://pushgateway:9091
```

## Troubleshooting

### Problema: Drift job falha com "No baseline found"

**Causa:** Baseline não foi salvo após treinamento inicial.

**Solução:**
```bash
# Verificar se baseline existe
kubectl exec -it mongodb-0 -n mongodb-cluster -- mongosh --eval \
  "db.ml_feature_baselines.countDocuments({})"

# Se 0, executar training job para gerar baseline
kubectl create job --from=cronjob/orchestrator-dynamic-ml-training \
  manual-training-$(date +%s) \
  -n neural-hive-orchestration

# Verificar que baseline foi salvo
kubectl logs -n neural-hive-orchestration job/manual-training-<timestamp> | grep "Feature baseline saved"
```

### Problema: PSI sempre alto (> 0.25)

**Causa:** Distribuição de dados mudou permanentemente (ex: novo tipo de workload).

**Solução:**
1. Retreinar modelo com dados recentes
2. Atualizar baseline após retreinamento
3. Considerar ajustar threshold se mudança é esperada

```bash
# Forçar retreinamento
python auto_retrain.py --specialist-type technical --force

# Verificar novo baseline foi criado
kubectl exec -it mongodb-0 -n mongodb-cluster -- mongosh --eval \
  "db.ml_feature_baselines.find().sort({timestamp:-1}).limit(1).pretty()"
```

### Problema: MAE ratio crescendo continuamente

**Causa:** Modelo desatualizado, padrões de carga mudaram.

**Solução:**
1. Verificar logs de predições:
```bash
kubectl logs -n neural-hive-orchestration deployment/orchestrator-dynamic | grep prediction_error
```

2. Analisar features no Grafana dashboard "ML Predictions"

3. Disparar retreinamento urgente:
```bash
python auto_retrain.py --specialist-type all --force
```

### Problema: CronJob não executa

**Causa:** CronJob suspenso ou schedule incorreto.

**Solução:**
```bash
# Verificar status
kubectl get cronjob -n neural-hive-orchestration orchestrator-dynamic-ml-drift

# Verificar se está suspenso
kubectl get cronjob orchestrator-dynamic-ml-drift -n neural-hive-orchestration \
  -o jsonpath='{.spec.suspend}'

# Reativar se necessário
kubectl patch cronjob orchestrator-dynamic-ml-drift -n neural-hive-orchestration \
  -p '{"spec":{"suspend":false}}'

# Verificar schedule
kubectl get cronjob orchestrator-dynamic-ml-drift -n neural-hive-orchestration \
  -o jsonpath='{.spec.schedule}'
```

### Problema: Notificações Slack não chegam

**Causa:** Webhook URL não configurado ou inválido.

**Solução:**
```bash
# Verificar variável de ambiente
kubectl get deployment orchestrator-dynamic -n neural-hive-orchestration \
  -o jsonpath='{.spec.template.spec.containers[0].env}' | jq '.[] | select(.name=="SLACK_WEBHOOK_URL")'

# Testar webhook manualmente
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test notification from Neural Hive"}' \
  $SLACK_WEBHOOK_URL
```

### Problema: MLflow training run falha

**Causa:** Problema de conectividade ou configuração MLflow.

**Solução:**
```bash
# Verificar conectividade MLflow
kubectl exec -it deployment/orchestrator-dynamic -n neural-hive-orchestration -- \
  curl -s http://mlflow.mlflow.svc.cluster.local:5000/api/2.0/mlflow/experiments/list

# Verificar logs do run
kubectl exec -it deployment/orchestrator-dynamic -n neural-hive-orchestration -- \
  python -c "import mlflow; mlflow.set_tracking_uri('http://mlflow:5000'); print(mlflow.search_runs())"
```

## Estrutura de Dados no MongoDB

### Collection: ml_feature_baselines

```json
{
  "model_name": "duration-predictor",
  "version": "v1.0",
  "timestamp": "2024-01-15T03:00:00Z",
  "features": {
    "risk_weight": {
      "values": [0.5, 0.6, ...],
      "mean": 0.55,
      "std": 0.12,
      "min": 0.1,
      "max": 1.0
    },
    "capabilities_count": {
      "values": [2, 3, 4, ...],
      "mean": 3.2,
      "std": 1.1,
      "min": 1,
      "max": 8
    }
  },
  "target_distribution": {
    "values": [60000, 62000, ...],
    "mean": 62000.0,
    "std": 5000.0,
    "percentiles": {
      "p50": 61500.0,
      "p95": 72000.0,
      "p99": 85000.0
    }
  },
  "training_mae": 5000.0,
  "sample_count": 1000
}
```

### Collection: retraining_triggers

```json
{
  "trigger_id": "trigger-abc123",
  "specialist_type": "technical",
  "triggered_at": "2024-01-15T04:30:00Z",
  "feedback_count": 150,
  "feedback_window_days": 30,
  "mlflow_run_id": "run-xyz789",
  "mlflow_experiment_id": "exp-123",
  "status": "completed",
  "completed_at": "2024-01-15T05:30:00Z",
  "metadata": {
    "duration_seconds": 3600,
    "model_precision": 0.85,
    "model_recall": 0.82,
    "model_f1": 0.83
  }
}
```

## Referências

### Arquivos de Código

- **DriftDetector:** `services/orchestrator-dynamic/src/ml/drift_detector.py`
- **Drift Job:** `services/orchestrator-dynamic/src/ml/drift_job.py`
- **Auto-Retrain:** `ml_pipelines/monitoring/auto_retrain.py`
- **Performance Monitor:** `ml_pipelines/monitoring/model_performance_monitor.py`
- **Retraining Trigger:** `libraries/python/neural_hive_specialists/feedback/retraining_trigger.py`

### Testes

- **Drift Detection Tests:** `services/orchestrator-dynamic/tests/integration/test_ml_drift_detection.py`
- **Auto-Retrain Tests:** `ml_pipelines/monitoring/tests/test_auto_retrain_integration.py`

### Configuração Kubernetes

- **CronJob:** `helm-charts/orchestrator-dynamic/templates/ml-drift-cronjob.yaml`
- **Values:** `helm-charts/orchestrator-dynamic/values.yaml` (seção `config.ml.drift`)
- **Alertas:** `prometheus-rules/ml-drift-alerts.yaml`

### Dashboards Grafana

- **Orchestrator ML Predictions:** Métricas de predições e drift
- **Model Performance:** Score agregado e degradação por specialist
