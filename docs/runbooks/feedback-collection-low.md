# Runbook: Feedback Collection Low

## Alerta

- **Nomes**: MLModelFeedbackRateSLOBreach, MLModelFeedbackRateSLOCritical
- **Severidade**: Warning / Critical
- **Thresholds**:
  - Taxa de feedback < 10% (Warning - SLO breach)
  - Taxa de feedback < 5% (Critical)

## Sintomas

- Taxa de coleta de feedback abaixo do SLO (10%)
- Poucos usuarios fornecendo feedback sobre decisoes
- Ratio feedback/predicoes muito baixo
- Dados insuficientes para retreinamento efetivo
- Qualidade do retreinamento pode estar comprometida
- UI de feedback pode estar com problemas
- Fluxo de usuario pode estar confuso ou inacessivel

## Diagnostico

### 1. Verificar taxa atual de feedback

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

# Ultimos 7 dias
cutoff = datetime.utcnow() - timedelta(days=7)

# Total de predicoes
predictions = db.specialist_opinions.count_documents({'timestamp': {'\$gte': cutoff}})

# Total de feedback
feedback = db.ml_feedback.count_documents({'created_at': {'\$gte': cutoff}})

rate = (feedback / predictions * 100) if predictions > 0 else 0
print(f'Predicoes: {predictions}')
print(f'Feedback: {feedback}')
print(f'Taxa: {rate:.2f}%')
"
```

### 2. Verificar metricas Prometheus

```bash
# Taxa de feedback atual (SLO)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive:slo:ml_feedback_rate:7d" | jq '.data.result[0].value[1]'

# Historico da taxa
curl -s "http://prometheus.monitoring:9090/api/v1/query_range?query=neural_hive:slo:ml_feedback_rate:7d&start=$(date -d '7 days ago' +%s)&end=$(date +%s)&step=3600" | jq '.data.result[0].values'
```

### 3. Analisar distribuicao de feedback por dia

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

# Ultimos 7 dias por dia
for i in range(7):
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i+1)
    end = start + timedelta(days=1)
    count = db.ml_feedback.count_documents({'created_at': {'\$gte': start, '\$lt': end}})
    print(f'{start.date()}: {count} feedbacks')
"
```

### 4. Verificar saude do servico de feedback

```bash
# Verificar pods do approval-service
kubectl get pods -n neural-hive-approval -l app=approval-service

# Verificar logs de erro
kubectl logs -n neural-hive-approval -l app=approval-service --tail=100 | grep -i "feedback\|error"
```

### 5. Verificar endpoints de feedback

```bash
# Testar endpoint de feedback (se disponivel externamente)
curl -X GET http://approval-service.neural-hive-approval:8080/health

# Verificar metricas do endpoint
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=http_requests_total{handler='/feedback'}" | jq '.data.result'
```

### 6. Analisar feedback por tipo de specialist

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

cutoff = datetime.utcnow() - timedelta(days=7)
pipeline = [
    {'\$match': {'created_at': {'\$gte': cutoff}}},
    {'\$group': {
        '_id': '\$specialist_type',
        'positive': {'\$sum': {'\$cond': [{'\$eq': ['\$feedback_type', 'positive']}, 1, 0]}},
        'negative': {'\$sum': {'\$cond': [{'\$eq': ['\$feedback_type', 'negative']}, 1, 0]}}
    }}
]
results = list(db.ml_feedback.aggregate(pipeline))
for r in results:
    total = r['positive'] + r['negative']
    print(f\"{r['_id']}: {total} total (positive: {r['positive']}, negative: {r['negative']})\")
"
```

### 7. Verificar UI de feedback (se aplicavel)

- Acessar aplicacao como usuario
- Verificar se botoes de feedback estao visiveis
- Testar fluxo completo de submissao de feedback
- Verificar console do browser para erros JavaScript

## Resolucao

### Opcao 1 - Verificar e Corrigir Servico de Feedback

Execute quando: endpoint de feedback esta com problemas

```bash
# Verificar deployment
kubectl describe deployment approval-service -n neural-hive-approval

# Reiniciar servico
kubectl rollout restart deployment/approval-service -n neural-hive-approval

# Verificar logs apos restart
kubectl logs -n neural-hive-approval -l app=approval-service -f
```

### Opcao 2 - Verificar Conectividade MongoDB

Execute quando: feedback nao esta sendo persistido

```bash
# Testar conexao MongoDB
kubectl exec -n neural-hive-approval deployment/approval-service -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017', serverSelectionTimeoutMS=5000)
client.server_info()
print('MongoDB connection OK')
"

# Verificar se collection existe e tem indices
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
print('Indices em ml_feedback:')
for idx in db.ml_feedback.list_indexes():
    print(f\"  {idx['name']}: {idx['key']}\")
"
```

### Opcao 3 - Incentivar Coleta de Feedback

Execute quando: servico OK mas usuarios nao fornecem feedback

Acoes recomendadas (coordenar com equipe de produto):

1. **Simplificar UI de feedback**
   - Reduzir numero de cliques necessarios
   - Tornar botoes mais visiveis
   - Adicionar tooltips explicativos

2. **Implementar feedback passivo**
   - Inferir feedback de acoes do usuario
   - Rastrear se usuario seguiu recomendacao

3. **Gamificacao**
   - Adicionar incentivos para fornecer feedback
   - Mostrar impacto do feedback do usuario

4. **Notificacoes**
   - Lembrar usuarios de fornecer feedback
   - Email/push notification apos decisoes

### Opcao 4 - Ajustar Threshold do SLO Temporariamente

Execute quando: problema conhecido e em investigacao

```bash
# Documentar ajuste temporario em decisions.md
# Ajustar recording rule temporariamente (nao recomendado para producao)
```

### Opcao 5 - Coletar Feedback Retroativo

Execute quando: ha dados historicos que podem ser usados

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']

# Inferir feedback de resultados conhecidos
# CUIDADO: Isso deve ser validado pela equipe de ML
cutoff = datetime.utcnow() - timedelta(days=30)

# Exemplo: marcar como positivo decisoes que nao foram revertidas
# Este e apenas um exemplo - a logica real depende do dominio
result = db.specialist_opinions.update_many(
    {
        'timestamp': {'\$gte': cutoff},
        'was_reverted': False,
        'feedback_collected': {'\$ne': True}
    },
    {'\$set': {'inferred_feedback': 'positive', 'feedback_source': 'inferred'}}
)
print(f'Marked {result.modified_count} opinions with inferred feedback')
"
```

## Verificacao de Recuperacao

### 1. Verificar que taxa de feedback melhorou

```bash
# Taxa deve ser >= 10%
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive:slo:ml_feedback_rate:7d" | jq '.data.result[0].value[1]'
```

### 2. Monitorar tendencia de feedback

```bash
watch -n 300 'kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
client = MongoClient(\"mongodb://mongodb.neural-hive:27017\")
db = client[\"neural_hive\"]
cutoff = datetime.utcnow() - timedelta(hours=1)
count = db.ml_feedback.count_documents({\"created_at\": {\"\$gte\": cutoff}})
print(f\"Feedback na ultima hora: {count}\")
"'
```

### 3. Verificar alertas resolvidos

```bash
curl -s http://alertmanager.monitoring:9093/api/v2/alerts?filter=alertname=~".*Feedback.*" | jq '.[] | select(.status.state == "active")'
```

### 4. Confirmar que retreinamento tem dados suficientes

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
count = db.ml_feedback.count_documents({'used_for_training': False})
print(f'Feedback disponivel para proximo retreinamento: {count}')
print('Minimo recomendado: 100')
"
```

## Prevencao

### 1. Monitorar taxa de feedback continuamente

Adicionar ao dashboard principal:

```yaml
- title: Feedback Collection Rate
  type: graph
  targets:
    - expr: neural_hive:slo:ml_feedback_rate:7d * 100
      legendFormat: "Feedback Rate %"
```

### 2. Configurar alertas de tendencia

```yaml
- alert: FeedbackRateDeclining
  expr: |
    deriv(neural_hive:slo:ml_feedback_rate:7d[24h]) < -0.001
  for: 6h
  labels:
    severity: warning
  annotations:
    summary: "Taxa de feedback em declinio"
```

### 3. Implementar feedback automatico

Para casos onde o resultado e conhecido:
- Decisoes nao contestadas apos X dias = positivo
- Decisoes revertidas = negativo

### 4. Revisar UX de feedback trimestralmente

Agendar revisao periodica da usabilidade do sistema de feedback.

### 5. Metricas de engajamento

Adicionar metricas de:
- Tempo para fornecer feedback
- Taxa de abandono do fluxo de feedback
- Correlacao entre tipo de decisao e taxa de feedback

## Referencias

- **Dashboard**: https://grafana.neural-hive.local/d/ml-slos-dashboard/ml-slos
- **Approval Service**: `services/approval-service/`
- **Feedback Integration Tests**: `services/approval-service/tests/integration/test_feedback_integration.py`
- **SLO Recording Rules**: `prometheus-rules/ml-slo-recording-rules.yaml`
- **SLO Alerts**: `prometheus-rules/ml-slo-alerts.yaml`
- **MongoDB Collection**: `ml_feedback`
