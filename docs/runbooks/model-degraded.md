# Runbook: Model Degraded

## Alerta

- **Nomes**: MLModelDegraded, MLModelLowPerformance, MLModelLowF1Score
- **Severidade**: Warning
- **Thresholds**:
  - `neural_hive_model_degradation_detected == 1`
  - Performance score < 0.65
  - F1 score < 0.72

## Sintomas

- Performance do modelo abaixo dos thresholds configurados
- Score agregado de performance abaixo de 0.65
- F1 Score do modelo abaixo de 0.72
- Aumento na taxa de decisoes incorretas
- Feedback negativo dos usuarios aumentando
- Predicoes com baixa confianca frequentes
- Tempo de resposta do modelo pode estar elevado

## Diagnostico

### 1. Verificar ModelPerformanceMonitor

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/model_performance_monitor.py \
    --specialist-type all \
    --output-format json
```

### 2. Verificar metricas de performance por specialist

```bash
# F1 Score atual
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_mlflow_model_f1" | jq '.data.result[] | {specialist: .metric.specialist_type, f1: .value[1]}'

# Performance score agregado
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_model_performance_score" | jq '.data.result[] | {specialist: .metric.specialist_type, score: .value[1]}'
```

### 3. Analisar feedback recente

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

# Feedback das ultimas 24h
cutoff = datetime.utcnow() - timedelta(hours=24)
pipeline = [
    {'\$match': {'created_at': {'\$gte': cutoff}}},
    {'\$group': {
        '_id': {
            'specialist_type': '\$specialist_type',
            'feedback_type': '\$feedback_type'
        },
        'count': {'\$sum': 1}
    }},
    {'\$sort': {'_id.specialist_type': 1}}
]
results = list(db.ml_feedback.aggregate(pipeline))
for r in results:
    print(f\"{r['_id']['specialist_type']}: {r['_id']['feedback_type']} = {r['count']}\")
"
```

### 4. Comparar com baseline de treinamento

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from libraries.python.neural_hive_specialists.mlflow_client import MLflowClient
client = MLflowClient()
for specialist in ['technical', 'security', 'business']:
    model = client.get_latest_model(f'{specialist}_specialist')
    if model:
        train_f1 = model.run.data.metrics.get('f1_score', 'N/A')
        print(f'{specialist}: Training F1 = {train_f1}')
"
```

### 5. Verificar distribuicao de predicoes

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

# Distribuicao de confidence scores
cutoff = datetime.utcnow() - timedelta(hours=24)
pipeline = [
    {'\$match': {'timestamp': {'\$gte': cutoff}}},
    {'\$bucket': {
        'groupBy': '\$confidence_score',
        'boundaries': [0, 0.5, 0.7, 0.85, 1.0],
        'default': 'unknown',
        'output': {'count': {'\$sum': 1}}
    }}
]
results = list(db.specialist_opinions.aggregate(pipeline))
for r in results:
    print(f'Confidence {r[\"_id\"]}: {r[\"count\"]}')
"
```

### 6. Verificar logs de erro do modelo

```bash
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=200 | grep -E "(error|exception|failed|prediction)" -i
```

### 7. Verificar dashboard Grafana

Acessar dashboard "Orchestrator ML Predictions":
- URL: https://grafana.neural-hive.local/d/orchestrator-ml-predictions
- Verificar paineis de F1 Score, Precision, Recall

## Resolucao

### Opcao 1 - Retreinamento do Modelo

Execute quando: degradacao gradual, dados de treinamento atualizados disponiveis

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type all \
    --force \
    --notification-channels slack,email
```

Para retreinar apenas o modelo degradado:

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type technical \
    --force
```

### Opcao 2 - Rollback para Modelo Anterior

Execute quando: degradacao subita apos deploy de novo modelo

```bash
# Listar versoes disponiveis
curl -s http://mlflow.mlflow:5000/api/2.0/mlflow/registered-models/get-latest-versions?name=technical_specialist | jq '.model_versions[] | {version, current_stage, creation_timestamp}'

# Executar rollback
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -m services.orchestrator_dynamic.src.ml.model_promotion rollback \
    --model-name technical_specialist \
    --reason "performance_degradation"
```

### Opcao 3 - Ajustar Threshold de Confianca

Execute quando: modelo esta correto mas threshold muito alto

```bash
# Editar ConfigMap
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"ML_CONFIDENCE_THRESHOLD":"0.65"}}'

# Reiniciar para aplicar
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

### Opcao 4 - Ativar Fallback para Heuristicas

Execute quando: degradacao severa (F1 < 0.65), necessita acao imediata

```bash
# Ativar fallback
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"ML_FALLBACK_ENABLED":"true","ML_FALLBACK_THRESHOLD":"0.65"}}'

# Reiniciar pods
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

### Opcao 5 - Investigar e Corrigir Dados de Treinamento

Execute quando: suspeita de dados de treinamento com problemas

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

# Verificar balanceamento de classes
pipeline = [
    {'\$group': {
        '_id': '\$feedback_type',
        'count': {'\$sum': 1}
    }}
]
results = list(db.ml_feedback.aggregate(pipeline))
total = sum(r['count'] for r in results)
print('Distribuicao de feedback:')
for r in results:
    pct = (r['count'] / total) * 100
    print(f\"  {r['_id']}: {r['count']} ({pct:.1f}%)\")
"
```

## Verificacao de Recuperacao

### 1. Verificar que performance voltou ao normal

```bash
# F1 Score deve ser >= 0.72
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_mlflow_model_f1" | jq '.data.result[] | {specialist: .metric.specialist_type, f1: .value[1]}'

# Performance score deve ser >= 0.65
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_model_performance_score" | jq '.data.result[] | {specialist: .metric.specialist_type, score: .value[1]}'
```

### 2. Verificar que degradation flag foi limpa

```bash
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_model_degradation_detected" | jq '.data.result[] | {specialist: .metric.specialist_type, degraded: .value[1]}'
```

### 3. Monitorar feedback por 1 hora

```bash
watch -n 300 'kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient(\"mongodb://mongodb.neural-hive:27017\")
db = client[\"neural_hive\"]
cutoff = datetime.utcnow() - timedelta(hours=1)
positive = db.ml_feedback.count_documents({\"created_at\": {\"\$gte\": cutoff}, \"feedback_type\": \"positive\"})
negative = db.ml_feedback.count_documents({\"created_at\": {\"\$gte\": cutoff}, \"feedback_type\": \"negative\"})
total = positive + negative
if total > 0:
    print(f\"Positive: {positive} ({positive/total*100:.1f}%), Negative: {negative} ({negative/total*100:.1f}%)\")
else:
    print(\"Sem feedback na ultima hora\")
"'
```

### 4. Verificar alertas resolvidos

```bash
curl -s http://alertmanager.monitoring:9093/api/v2/alerts?filter=alertname=~"MLModel.*" | jq '.[] | select(.status.state == "active")'
```

## Prevencao

### 1. Configurar monitoramento continuo

Garantir que `ModelPerformanceMonitor` execute regularmente:

```bash
# Verificar CronJob
kubectl get cronjob -n neural-hive-orchestration | grep performance
```

### 2. Implementar shadow mode para novos modelos

Antes de promover novos modelos para producao, executar em shadow mode:

```python
# services/orchestrator-dynamic/src/ml/shadow_mode.py
shadow_evaluator.evaluate(new_model, production_traffic, duration_hours=24)
```

### 3. Configurar alertas de tendencia

Adicionar alertas que detectem degradacao gradual antes de atingir threshold critico:

```yaml
- alert: MLModelPerformanceDeclining
  expr: |
    deriv(neural_hive_model_performance_score[6h]) < -0.01
  for: 30m
  labels:
    severity: warning
```

### 4. Revisar dados de treinamento periodicamente

Agendar revisao mensal da qualidade dos dados de feedback.

### 5. Documentar baseline de performance

Manter registro das metricas esperadas para cada tipo de specialist apos cada retreinamento.

## Referencias

- **Dashboard**: https://grafana.neural-hive.local/d/orchestrator-ml-predictions
- **Model Performance Monitor**: `ml_pipelines/monitoring/model_performance_monitor.py`
- **Model Promotion**: `services/orchestrator-dynamic/src/ml/model_promotion.py`
- **Shadow Mode**: `services/orchestrator-dynamic/src/ml/shadow_mode.py`
- **Alertas Prometheus**: `prometheus-rules/ml-drift-alerts.yaml`
- **MLflow Models**: http://mlflow.mlflow:5000
