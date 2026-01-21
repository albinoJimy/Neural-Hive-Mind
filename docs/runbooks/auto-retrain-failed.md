# Runbook: Auto-Retrain Failed

## Alerta

- **Nomes**: AutoRetrainFailed, AutoRetrainLongDuration, NoRetrainWithDrift
- **Severidade**: Warning
- **Thresholds**:
  - Retreinamento falhou na ultima hora
  - Duracao do retreinamento > 2 horas (7200 segundos)
  - Drift detectado sem retreinamento nos ultimos 30 dias

## Sintomas

- Pipeline de retreinamento automatico falhou
- Retreinamento esta demorando mais que o esperado (> 2 horas)
- Drift detectado mas sem retreinamento recente
- Logs do auto_retrain.py mostrando erros
- Status "failed" na collection `retraining_triggers` do MongoDB
- Recursos de GPU/CPU podem estar sobrecarregados
- Falha na coleta de dados de treinamento

## Diagnostico

### 1. Verificar logs do auto_retrain.py

```bash
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=500 | grep retrain
```

### 2. Verificar status no MongoDB

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
import json
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
# Buscar ultimas tentativas de retraining
triggers = list(db.retraining_triggers.find({}).sort('triggered_at', -1).limit(10))
for t in triggers:
    print(f\"Status: {t.get('status')}, Specialist: {t.get('specialist_type')}, Time: {t.get('triggered_at')}\")
    if t.get('error'):
        print(f\"  Error: {t.get('error')}\")
"
```

### 3. Verificar recursos disponiveis

```bash
# Verificar uso de CPU/memoria dos pods
kubectl top pods -n neural-hive-orchestration

# Verificar se ha GPU disponivel (se aplicavel)
kubectl describe nodes | grep -A5 "Allocated resources"
```

### 4. Verificar MLflow

```bash
# Verificar status do MLflow server
kubectl get pods -n mlflow -l app=mlflow

# Verificar experimentos recentes
curl -s http://mlflow.mlflow:5000/api/2.0/mlflow/experiments/search | jq '.experiments[] | {name, lifecycle_stage}'
```

### 5. Verificar dados de treinamento

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
# Contar dados disponiveis para treinamento
count = db.ml_feedback.count_documents({'used_for_training': False})
print(f'Feedback disponivel para treinamento: {count}')
"
```

### 6. Verificar metricas Prometheus

```bash
# Verificar contagem de retrains falhados
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=increase(neural_hive_auto_retrain_triggered_total{status='failed'}[24h])"

# Verificar duracao do ultimo retrain
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_auto_retrain_duration_seconds"
```

## Resolucao

### Opcao 1 - Retry Manual do Retreinamento

Execute quando: falha foi transiente (timeout, recurso temporariamente indisponivel)

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type all \
    --force \
    --notification-channels slack
```

Para retreinar apenas um tipo especifico:

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type technical \
    --force
```

### Opcao 2 - Verificar e Corrigir Dados de Treinamento

Execute quando: falha indica dados insuficientes ou corrompidos

```bash
# Verificar integridade dos dados
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/training/real_data_collector.py \
    --validate-only \
    --specialist-type all
```

Se houver problemas nos dados:

```bash
# Limpar dados corrompidos
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
# Remover feedback com dados invalidos
result = db.ml_feedback.delete_many({
    '\$or': [
        {'confidence_score': {'\$exists': False}},
        {'specialist_type': {'\$exists': False}},
        {'actual_duration_ms': {'\$lte': 0}}
    ]
})
print(f'Removed {result.deleted_count} invalid feedback records')
"
```

### Opcao 3 - Aumentar Recursos

Execute quando: falha por OOM ou timeout

```bash
# Escalar verticalmente o pod (editar deployment)
kubectl edit deployment orchestrator-dynamic -n neural-hive-orchestration

# Ou aumentar limites de recursos temporariamente
kubectl patch deployment orchestrator-dynamic -n neural-hive-orchestration \
  --type json \
  -p '[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "8Gi"}]'
```

### Opcao 4 - Reiniciar Pipeline de MLflow

Execute quando: MLflow server esta com problemas

```bash
# Reiniciar MLflow
kubectl rollout restart deployment/mlflow -n mlflow

# Aguardar estabilizacao
kubectl rollout status deployment/mlflow -n mlflow

# Retry do retreinamento
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python ml_pipelines/monitoring/auto_retrain.py --force
```

### Opcao 5 - Marcar Trigger como Resolvido Manualmente

Execute quando: problema foi resolvido fora do pipeline automatico

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
db.retraining_triggers.update_many(
    {'status': 'failed'},
    {'\$set': {'status': 'resolved_manually', 'resolved_at': datetime.utcnow()}}
)
print('Triggers marcados como resolvidos manualmente')
"
```

## Verificacao de Recuperacao

### 1. Verificar que retreinamento completou com sucesso

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
latest = db.retraining_triggers.find_one(sort=[('triggered_at', -1)])
print(f\"Status: {latest.get('status')}, Completed: {latest.get('completed_at')}\")
"
```

### 2. Validar novo modelo no MLflow

```bash
curl -s http://mlflow.mlflow:5000/api/2.0/mlflow/registered-models/get-latest-versions?name=technical_specialist | jq '.'
```

### 3. Verificar metricas do novo modelo

```bash
# F1 score do modelo
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_mlflow_model_f1"

# Confirmar modelo em producao
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_mlflow_model_stage"
```

### 4. Verificar alertas resolvidos

```bash
curl -s http://alertmanager.monitoring:9093/api/v2/alerts?filter=alertname=~"AutoRetrain.*" | jq '.[] | select(.status.state == "active")'
```

## Prevencao

### 1. Configurar alertas de recursos

Adicionar alertas para detectar problemas de recursos antes da falha:

```yaml
- alert: MLTrainingResourcesLow
  expr: |
    (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) < 0.2
  for: 10m
  labels:
    severity: warning
```

### 2. Implementar retry automatico com backoff

Modificar `ml_pipelines/monitoring/auto_retrain.py` para incluir retry com exponential backoff:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=60, max=3600))
def run_retraining():
    ...
```

### 3. Monitorar tamanho do dataset

```bash
# Adicionar ao CronJob de monitoramento
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
# Alertar se dataset muito grande
count = db.ml_feedback.count_documents({})
if count > 1000000:
    print(f'WARNING: Dataset muito grande ({count} records), considerar sampling')
"
```

### 4. Configurar limites de duracao

Adicionar timeout no pipeline de retreinamento para evitar jobs infinitos.

### 5. Backup de modelos anteriores

Garantir que sempre haja um modelo de fallback disponivel antes de iniciar retreinamento.

## Referencias

- **Dashboard**: https://grafana.neural-hive.local/d/orchestrator-ml-predictions
- **Auto Retrain Pipeline**: `ml_pipelines/monitoring/auto_retrain.py`
- **Real Data Collector**: `ml_pipelines/training/real_data_collector.py`
- **MLflow API**: http://mlflow.mlflow:5000
- **Alertas Prometheus**: `prometheus-rules/ml-drift-alerts.yaml`
- **MongoDB Collections**: `retraining_triggers`, `ml_feedback`
