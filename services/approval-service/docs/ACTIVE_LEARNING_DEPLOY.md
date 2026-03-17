# Active Learning - Deployment Guide

## Visão Geral

O sistema de Active Learning coleta feedbacks de forma balanceada para melhorar a qualidade do dataset ML, focando em casos sub-representados (rejeições, baixa confiança, domínios específicos).

## Variáveis de Ambiente

```bash
# === Active Learning Configuration ===
ENABLE_ACTIVE_LEARNING=true
ACTIVE_LEARNING_QUEUE_COLLECTION=active_learning_queue
ACTIVE_LEARNING_MIN_INFORMATION_VALUE=0.5
ACTIVE_LEARNING_ENQUEUE_RATE=0.2

# Valores recomendados por ambiente:
# Dev/Testing: ENABLE_ACTIVE_LEARNING=true, MIN_INFORMATION_VALUE=0.3, ENQUEUE_RATE=0.5
# Staging: ENABLE_ACTIVE_LEARNING=true, MIN_INFORMATION_VALUE=0.5, ENQUEUE_RATE=0.2
# Production: ENABLE_ACTIVE_LEARNING=true, MIN_INFORMATION_VALUE=0.6, ENQUEUE_RATE=0.1
```

## Deploy via Kubernetes

### 1. Atualizar ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: approval-service-config
data:
  ENABLE_ACTIVE_LEARNING: "true"
  ACTIVE_LEARNING_MIN_INFORMATION_VALUE: "0.5"
  ACTIVE_LEARNING_ENQUEUE_RATE: "0.2"
```

### 2. Deploy Command

```bash
# Aplicar configuração
kubectl apply -f k8s/configmap.yaml

# Deploy do serviço
kubectl rollout restart deployment/approval-service

# Verificar logs
kubectl logs -f deployment/approval-service -c approval-service
```

## MongoDB Migration

### Executar migration manualmente

```bash
# Entrar no pod
kubectl exec -it deployment/approval-service -- bash

# Executar migration
python -m src.database.migrations.m001_active_learning_schema
```

### Via Job Kubernetes

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: active-learning-migration
spec:
  template:
    spec:
      containers:
      - name: migration
        image: nhm/approval-service:latest
        command: ["python", "-m", "src.database.migrations.m001_active_learning_schema"]
        env:
        - name: MONGODB_URI
          valueFrom:
            secretKeyRef:
              name: mongodb-secret
              key: uri
      restartPolicy: OnFailure
```

## Verificação Pós-Deploy

### 1. Verificar Health Check

```bash
curl http://approval-service:8080/health | jq .
```

### 2. Verificar Active Learning endpoints

```bash
# Métricas de balanceamento
curl http://approval-service:8080/api/v1/active-learning/metrics | jq .

# Fila de casos
curl http://approval-service:8080/api/v1/active-learning/queue | jq .
```

### 3. Verificar MongoDB

```bash
# Conectar ao MongoDB
kubectl exec -it statefulset/mongodb -- mongo

# Verificar coleções
show collections
# Esperado: active_learning_queue, specialist_feedback, plan_approvals

# Verificar índices
db.active_learning_queue.getIndexes()
db.specialist_feedback.getIndexes()
```

## Monitoração

### Métricas Prometheus

As seguintes métricas são expostas:

- `active_learning_queue_size` - Tamanho da fila
- `active_learning_cases_enqueued_total` - Total de casos enfileirados
- `active_learning_feedbacks_collected_total` - Total de feedbacks coletados
- `dataset_balance_gap` - Gap de balanceamento por classe

### Alertas Recomendados

```yaml
# Alerta: Fila muito grande
- alert: ActiveLearningQueueBacklog
  expr: active_learning_queue_size > 100
  for: 1h
  annotations:
    summary: "Fila de Active Learning está muito grande"

# Alerta: Sem novos feedbacks balanceados
- alert: NoBalancedFeedbacks
  expr: increase(active_learning_feedbacks_collected_total[24h]) == 0
  annotations:
    summary: "Nenhum feedback balanceado coletado nas últimas 24h"
```

## Rollback

Se necessário desabilitar Active Learning:

```bash
# Atualizar ConfigMap
kubectl patch configmap approval-service-config -p '{"data":{"ENABLE_ACTIVE_LEARNING":"false"}}'

# Restart do serviço
kubectl rollout restart deployment/approval-service
```

## Troubleshooting

### Problema: Casos não são enfileirados

**Sintoma:** Fila sempre vazia

**Diagnóstico:**
```bash
# Verificar configuração
kubectl exec -it deployment/approval-service -- env | grep ACTIVE_LEARNING

# Verificar logs
kubectl logs deployment/approval-service | grep "active_learning"
```

**Solução:**
- Verificar se `ENABLE_ACTIVE_LEARNING=true`
- Verificar se `MIN_INFORMATION_VALUE` não está muito alto
- Verificar logs de erro no ApprovalService

### Problema: Migration falhou

**Sintoma:** Erro 404 ao acessar active_learning_queue

**Solução:**
```bash
# Re-executar migration
kubectl apply -f k8s/migration-job.yaml

# Verificar se coleção foi criada
kubectl exec -it statefulset/mongodb -- mongo --eval "db.getCollectionNames()"
```

### Problema: Feedback não marcado como balanced

**Sintoma:** `balanced_dataset=false` em todos os feedbacks

**Diagnóstico:**
```bash
# Verificar se PriorityFeedbackQueue está retornando casos
curl http://approval-service:8080/api/v1/active-learning/queue | jq '.cases | length'
```

**Solução:**
- Verificar se `from_active_learning=True` está sendo passado
- Verificar logs do approval-service
