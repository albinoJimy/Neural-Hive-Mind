# Runbook: Approval Service Down

## Alerta

- **Nome**: ApprovalServiceDown / ApprovalProcessingErrors / ApprovalKafkaLag
- **Severidade**: Critical / Warning
- **Threshold**: Service down por 2min / >5% erros / >100 msgs lag

## Sintomas

- Approval Service nao respondendo
- Fila de aprovacoes crescendo sem processamento
- Erros de processamento de aprovacoes
- Lag alto no consumer Kafka

## Diagnostico

### 1. Verificar status dos pods

```bash
kubectl get pods -n neural-hive -l app=approval-service
kubectl describe pods -n neural-hive -l app=approval-service
```

### 2. Verificar logs de erro

```bash
kubectl logs -n neural-hive -l app=approval-service --tail=100
kubectl logs -n neural-hive -l app=approval-service --previous --tail=100
```

### 3. Verificar recursos (CPU/Memory)

```bash
kubectl top pods -n neural-hive -l app=approval-service
```

### 4. Verificar conectividade Kafka

```bash
kubectl exec -n neural-hive deployment/approval-service -- \
  python -c "from kafka import KafkaConsumer; print('Kafka OK')"
```

### 5. Verificar consumer lag

```bash
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --describe
```

### 6. Verificar conectividade com dependencias

```bash
# MongoDB
kubectl exec -n neural-hive deployment/approval-service -- \
  python -c "from pymongo import MongoClient; print('MongoDB OK')"

# Redis (se usado)
kubectl exec -n neural-hive deployment/approval-service -- \
  python -c "import redis; print('Redis OK')"
```

## Resolucao

### Acao Imediata

1. Verificar se e problema de pod ou de infraestrutura
2. Se pod crashed, verificar logs do crash
3. Reiniciar deployment se necessario

```bash
kubectl rollout restart deployment/approval-service -n neural-hive
```

### Se Problema de Recursos

```bash
# Escalar horizontalmente
kubectl scale deployment/approval-service -n neural-hive --replicas=3

# Ou ajustar recursos
kubectl set resources deployment/approval-service -n neural-hive \
  --limits=cpu=1000m,memory=1Gi \
  --requests=cpu=500m,memory=512Mi
```

### Se Problema de Kafka

1. Verificar se Kafka esta saudavel
2. Verificar se topics existem
3. Reset consumer group se necessario

```bash
# Verificar topics
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list | grep approval

# Reset consumer (CUIDADO: pode reprocessar mensagens)
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --reset-offsets --to-latest \
  --topic cognitive-plans-approval-requests \
  --execute
```

### Se Problema de MongoDB

1. Verificar conectividade com MongoDB
2. Verificar se collections existem
3. Verificar indices

```bash
kubectl exec -n neural-hive deployment/approval-service -- \
  python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb:27017')
db = client['neural_hive']
print('Collections:', db.list_collection_names())
"
```

## Verificacao de Recuperacao

1. Pods em estado Running
2. Metricas sendo coletadas
3. Consumer lag reduzindo
4. Taxa de erro < 1%

```bash
# Verificar pods
kubectl get pods -n neural-hive -l app=approval-service

# Verificar metricas
curl -s http://approval-service.neural-hive:8000/metrics | head -20

# Verificar lag
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --describe
```

## Prevencao

- Configurar HPA para auto-scaling
- Implementar circuit breaker para dependencias
- Monitorar tendencias de recursos
- Manter replicas minimas >= 2

## Referencias

- Dashboard: https://grafana.neural-hive.io/d/approval-monitoring
- Codigo: `services/approval-service/`
- Deployment: `k8s/approval-service-deployment.yaml`
