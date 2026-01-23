# Runbook: ML Drift Critico

## Alerta

- **Nomes**: MLDriftCritical, MLDriftWarning, MLFeatureDriftHigh, MLPredictionDriftCritical, MLTargetDriftDetected
- **Severidade**: Critical / Warning
- **Thresholds**:
  - Drift status = 2 (critico) ou 1 (warning)
  - PSI > 0.25 (feature drift)
  - MAE ratio > 1.5 (prediction drift)
  - K-S p-value < 0.05 (target drift)

## Sintomas

- Status de drift em nivel critico ou warning por mais de 10-30 minutos
- PSI (Population Stability Index) acima de 0.25 para features de entrada
- MAE ratio (atual/treino) excedendo 1.5 (degradacao de 50%+)
- Kolmogorov-Smirnov test indicando mudanca na distribuicao do target
- Degradacao de performance do modelo sem explicacao aparente
- Aumento na taxa de decisoes incorretas ou feedback negativo

## Diagnostico

### 1. Verificar drift score atual

```bash
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep drift
```

### 2. Analisar features com drift

Acessar MongoDB e buscar ultimo relatorio de drift:

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
import json
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
report = db.drift_reports.find_one(sort=[('created_at', -1)])
print(json.dumps(report, indent=2, default=str))
"
```

### 3. Verificar distribuicao de dados recentes (ClickHouse)

```sql
SELECT
    specialist_type,
    count(*) as executions,
    avg(confidence_score) as avg_confidence,
    min(confidence_score) as min_confidence,
    max(confidence_score) as max_confidence
FROM specialist_opinions
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY specialist_type
```

### 4. Consultar metricas Prometheus

```bash
# Verificar status geral de drift
curl -s http://prometheus.monitoring:9090/api/v1/query?query=orchestration_ml_drift_overall_status

# Verificar PSI maximo
curl -s http://prometheus.monitoring:9090/api/v1/query?query=orchestration_ml_drift_feature_max_psi

# Verificar MAE ratio
curl -s http://prometheus.monitoring:9090/api/v1/query?query=orchestration_ml_drift_prediction_ratio
```

### 5. Verificar dashboard Grafana

Acessar dashboard "Orchestrator ML Predictions":
- URL: https://grafana.neural-hive.local/d/orchestrator-ml-predictions

### 6. Analisar tendencia de drift

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from libraries.python.neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector
detector = DriftDetector()
report = detector.generate_drift_report(window_hours=168)  # ultima semana
print(report.to_json(indent=2))
"
```

## Resolucao

### Opcao 1 - Retreinamento Urgente (Recomendado para drift critico)

Execute quando: drift critico persistente, MAE ratio > 1.5, dados de entrada mudaram

```bash
# Executar via kubectl exec no pod orchestrator-dynamic
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type all \
    --force \
    --notification-channels slack,email
```

Para retreinar apenas um tipo de specialist:

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type technical \
    --force
```

### Opcao 2 - Rollback de Modelo

Execute quando: degradacao subita (< 24h), modelo anterior tinha performance boa, dados de entrada nao mudaram

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -m services.orchestrator_dynamic.src.ml.model_promotion rollback \
    --model-name technical_specialist \
    --reason "drift_critical"
```

Verificar logica de rollback em:
- `services/orchestrator-dynamic/src/ml/model_promotion.py` - metodo `_execute_rollback()`

### Opcao 3 - Ajustar Threshold (Se drift for esperado)

Se a mudanca no padrao de dados for esperada (ex: lancamento de nova feature, mudanca de carga):

```bash
# Editar ConfigMap para ajustar threshold de PSI
kubectl edit configmap mlflow-config -n mlflow

# Localizar e ajustar:
# drift_threshold_psi: "0.30"  # aumentar de 0.25 para 0.30
```

Apos ajustar, reiniciar deployment:

```bash
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

### Acao Imediata - Ativar Fallback (Se F1 < 0.70)

Se o modelo estiver severamente degradado, ativar fallback para heuristicas:

```bash
# Modificar ConfigMap
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"ML_FALLBACK_ENABLED":"true"}}'

# Reiniciar pods
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

## Verificacao de Recuperacao

### 1. Verificar que drift status voltou ao normal

```bash
# Status deve ser 0 (normal)
curl -s http://prometheus.monitoring:9090/api/v1/query?query=orchestration_ml_drift_overall_status | jq '.data.result[0].value[1]'
```

### 2. Confirmar MAE ratio dentro do esperado

```bash
# MAE ratio deve ser < 1.2
curl -s http://prometheus.monitoring:9090/api/v1/query?query=orchestration_ml_drift_prediction_ratio | jq '.data.result[0].value[1]'
```

### 3. Validar novo modelo no MLflow

```bash
curl -s http://mlflow.mlflow:5000/api/2.0/mlflow/registered-models/get-latest-versions?name=technical_specialist | jq '.'
```

### 4. Verificar alertas no Alertmanager

```bash
# Alertas de drift devem estar resolvidos
curl -s http://alertmanager.monitoring:9093/api/v2/alerts?filter=alertname=~"ML.*Drift.*" | jq '.[] | select(.status.state == "active")'
```

### 5. Monitorar metricas por 30 minutos

```bash
# Watch das metricas de drift
watch -n 60 'curl -s http://prometheus.monitoring:9090/api/v1/query?query=orchestration_ml_drift_overall_status | jq ".data.result[0].value[1]"'
```

## Prevencao

### 1. Aumentar frequencia de drift detection

Editar CronJob `k8s/cronjobs/specialist-retraining-job.yaml`:
- Mudar schedule de semanal para diario: `0 3 * * *`

```bash
kubectl patch cronjob specialist-models-retraining -n mlflow \
  --type merge \
  -p '{"spec":{"schedule":"0 3 * * *"}}'
```

### 2. Configurar retraining automatico mais agressivo

Reduzir threshold de feedbacks necessarios em `ml_pipelines/training/real_data_collector.py`:
- Mudar `min_samples` de 100 para 50

### 3. Revisar thresholds de drift

Se houver muitos falsos positivos, considerar:
- Aumentar PSI threshold de 0.25 para 0.30
- Aumentar MAE ratio threshold de 1.5 para 1.8
- Aumentar tempo de `for` nos alertas Prometheus

### 4. Implementar alertas preditivos

Adicionar alertas de burn rate para detectar tendencias antes de atingir thresholds criticos.

### 5. Documentar mudancas esperadas

Manter registro de mudancas de produto/infra que podem impactar distribuicao de dados.

## Referencias

- **Dashboard**: https://grafana.neural-hive.local/d/orchestrator-ml-predictions
- **Codigo Drift Detector**: `libraries/python/neural_hive_specialists/drift_monitoring/drift_detector.py`
- **Auto Retrain Pipeline**: `ml_pipelines/monitoring/auto_retrain.py`
- **Model Promotion**: `services/orchestrator-dynamic/src/ml/model_promotion.py`
- **Alertas Prometheus**: `prometheus-rules/ml-drift-alerts.yaml`
- **SLOs**: `docs/slos/ml-models.md`
