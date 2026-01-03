# Guia de Troubleshooting - Consensus Engine

## Problema 1: Pod em CrashLoopBackOff

### Causa Provável
Erro na inicialização do Python antes da configuração do logging (Settings validation failure)

### Diagnóstico
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --previous
kubectl describe pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine
```

### Soluções

#### 1.1. Variável obrigatória faltando
**Sintoma**: Logs vazios ou erro `ValueError: Valor não pode ser vazio`

**Verificar ConfigMap**:
```bash
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep -E 'KAFKA_BOOTSTRAP_SERVERS|MONGODB_URI|REDIS_CLUSTER_NODES'
```

**Solução**: Garantir que todas as 3 variáveis obrigatórias estão presentes e não vazias

#### 1.2. Formato de endpoint inválido
**Sintoma**: Erro `ValueError: Endpoint deve estar no formato host:port`

**Verificar endpoints**:
```bash
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep SPECIALIST_.*_ENDPOINT
```

**Solução**: Todos os endpoints devem conter `:` (ex: `specialist-business.specialist-business.svc.cluster.local:50051`)

#### 1.3. Imagem não encontrada (ImagePullBackOff)
**Sintoma**: Pod em `ImagePullBackOff` ou `ErrImageNeverPull`

**Solução**:
```bash
eval $(minikube docker-env)
cd /jimy/Neural-Hive-Mind
docker build -f services/consensus-engine/Dockerfile -t neural-hive-mind/consensus-engine:1.0.0 .
kubectl delete pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine
```

## Problema 2: Pod Running mas /ready retorna false

### Causa Provável
Dependência (MongoDB, Redis, Specialists) não acessível

### Diagnóstico
```bash
kubectl port-forward -n consensus-engine svc/consensus-engine 8000:8000 &
curl http://localhost:8000/ready | jq .
kill %1
```

### Soluções por Check

#### 2.1. MongoDB check = false
**Testar conectividade**:
```bash
kubectl run mongo-test --image=busybox --rm -it --restart=Never -n consensus-engine -- nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017
```

**Se falhar**: Verificar se MongoDB está Running
```bash
kubectl get pods -n mongodb-cluster
```

**Verificar autenticação**:
```bash
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep MONGODB_URI
# Deve conter: mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin
```

#### 2.2. Redis check = false
**Testar conectividade**:
```bash
kubectl run redis-test --image=busybox --rm -it --restart=Never -n consensus-engine -- nc -zv neural-hive-cache.redis-cluster.svc.cluster.local 6379
```

**Se falhar**: Verificar se Redis está Running
```bash
kubectl get pods -n redis-cluster
```

#### 2.3. Specialists check = false
**Identificar qual specialist falhou**:
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=50 | grep -i "specialist.*not_serving\|specialist.*error"
```

**Testar conectividade individual**:
```bash
for specialist in business technical behavior evolution architecture; do
  kubectl run test-${specialist} --image=busybox --rm -it --restart=Never -n consensus-engine -- nc -zv specialist-${specialist}.specialist-${specialist}.svc.cluster.local 50051 && echo "✓ ${specialist}" || echo "✗ ${specialist}"
done
```

**Verificar health do specialist**:
```bash
kubectl get pods -n specialist-business
kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business --tail=20
```

## Problema 3: Não consome mensagens do Kafka

### Causa Provável
Consumer não conectado, tópico não existe, ou consumer group com offset travado

### Diagnóstico
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=100 | grep -i "plan consumer\|kafka\|subscribe"
```

### Soluções

#### 3.1. Verificar tópico existe
```bash
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list | grep plans.ready
```

**Se não existir**: Criar tópico
```bash
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic plans.ready --partitions 3 --replication-factor 1
```

#### 3.2. Verificar consumer group
```bash
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group consensus-engine
```

**Se offset travado**: Resetar consumer group
```bash
kubectl scale deployment/consensus-engine -n consensus-engine --replicas=0
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group consensus-engine --reset-offsets --to-earliest --topic plans.ready --execute
kubectl scale deployment/consensus-engine -n consensus-engine --replicas=1
```

#### 3.3. Publicar mensagem de teste
```bash
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-producer --bootstrap-server localhost:9092 --topic plans.ready <<EOF
{"plan_id":"test-$(date +%s)","intent_id":"test-intent","version":"1.0.0","tasks":[],"execution_order":[],"risk_score":0.5,"risk_band":"low","risk_factors":{},"explainability_token":"test","reasoning_summary":"test","status":"draft","created_at":$(date +%s)000,"complexity_score":0.5,"original_domain":"test","original_priority":"medium","original_security_level":"standard","metadata":{},"schema_version":1}
EOF
```

**Verificar consumo**:
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=50 | grep "test-"
```

## Problema 4: Não publica em plans.consensus

### Causa Provável
Erro no processamento, producer não conectado, ou serialização falhou

### Diagnóstico
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=100 | grep -i "decision producer\|publish\|serialize"
```

### Soluções

#### 4.1. Verificar erros de processamento
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=200 | grep -i "error\|exception\|failed"
```

#### 4.2. Verificar tópico de saída
```bash
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list | grep plans.consensus
```

#### 4.3. Consumir mensagens do tópico
```bash
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-consumer --bootstrap-server localhost:9092 --topic plans.consensus --from-beginning --timeout-ms 5000
```

## Problema 5: Timeout ao invocar specialists

### Causa Provável
Specialist sobrecarregado, rede lenta, ou timeout muito curto

### Diagnóstico
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=100 | grep -i "timeout\|specialist"
```

### Soluções

#### 5.1. Aumentar timeout gRPC
**Editar ConfigMap**:
```bash
kubectl edit configmap -n consensus-engine consensus-engine-config
# Alterar SPECIALIST_GRPC_TIMEOUT_MS de 5000 para 10000
```

**Restart deployment**:
```bash
kubectl rollout restart deployment/consensus-engine -n consensus-engine
```

#### 5.2. Verificar performance do specialist
```bash
kubectl top pod -n specialist-business
kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business --tail=50 | grep -i "processing_time\|duration"
```

## Problema 6: Recursos insuficientes (Pending)

### Causa Provável
Cluster em 94% CPU, sem recursos para agendar pod

### Diagnóstico
```bash
kubectl describe pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine | grep -A 5 "Events:"
```

### Soluções

#### 6.1. Escalar componentes não essenciais
```bash
kubectl scale deployment/mlflow -n mlflow --replicas=0
kubectl scale statefulset/redis -n redis-cluster --replicas=0
```

#### 6.2. Reduzir recursos do consensus-engine
**Editar values-local.yaml**:
```yaml
resources:
  requests:
    cpu: 100m  # Reduzido de 250m
    memory: 256Mi  # Reduzido de 512Mi
```

**Redeploy**:
```bash
helm upgrade consensus-engine ./helm-charts/consensus-engine --namespace consensus-engine --values ./helm-charts/consensus-engine/values-local.yaml
```

## Problema 7: Restarts Frequentes (8+ restarts)

### Causa Provável
OOM devido ao processamento Bayesiano intensivo ou startup timeout com dependências lentas

### Diagnóstico
```bash
# Verificar OOMKill
kubectl get pods -n consensus-engine -l app.kubernetes.io/name=consensus-engine \
  -o jsonpath='{.items[0].status.containerStatuses[0].lastState.terminated.reason}'

kubectl describe pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine | grep -i "oomkilled"

# Verificar uso de memória
kubectl top pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine
```

### Soluções

#### 7.1. OOM Confirmado
**Sintoma**: `lastState.terminated.reason=OOMKilled` ou uso de memória >850Mi

**Solução**: Aumentar memória limit de 1Gi para 1.25Gi conforme guidance do `helm-charts/consensus-engine/values.yaml` linha 34:
```bash
helm upgrade consensus-engine ./helm-charts/consensus-engine \
  --set resources.limits.memory=1280Mi \
  -n consensus-engine
```

#### 7.2. Startup Timeout
**Sintoma**: Logs mostram "Startup probe failed", dependências lentas

**Solução**: Aumentar `startupProbe.failureThreshold` de 15 para 20:
```bash
helm upgrade consensus-engine ./helm-charts/consensus-engine \
  --set startupProbe.failureThreshold=20 \
  -n consensus-engine
```

#### 7.3. Deadlock/Hang com Specialists
**Sintoma**: Logs param de aparecer, CPU usage cai para 0

**Solução**: Aumentar timeout gRPC:
```bash
kubectl edit configmap -n consensus-engine consensus-engine-config
# Alterar SPECIALIST_GRPC_TIMEOUT_MS de 120000 para 180000
kubectl rollout restart deployment/consensus-engine -n consensus-engine
```

### Monitoramento
- Alerta Prometheus: `ConsensusEngineHighMemoryUsage`, `ConsensusEngineOOMKilled`, `ConsensusEngineHighRestarts`
- Dashboard Grafana: "Consensus & Governance" > painéis "Memory Usage", "Restart Count", "CPU Usage"

---

## Comandos Úteis

### Restart completo
```bash
kubectl rollout restart deployment/consensus-engine -n consensus-engine
```

### Hard restart (scale down/up)
```bash
kubectl scale deployment/consensus-engine -n consensus-engine --replicas=0
sleep 5
kubectl scale deployment/consensus-engine -n consensus-engine --replicas=1
```

### Ver eventos do namespace
```bash
kubectl get events -n consensus-engine --sort-by='.lastTimestamp' | tail -20
```

### Exec no pod para debug
```bash
POD_NAME=$(kubectl get pods -n consensus-engine -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it -n consensus-engine $POD_NAME -- /bin/bash
```

### Verificar variáveis de ambiente no pod
```bash
kubectl exec -n consensus-engine $POD_NAME -- env | grep -E 'KAFKA|MONGODB|REDIS|SPECIALIST'
```

### Deletar e recriar deployment
```bash
helm uninstall consensus-engine -n consensus-engine
kubectl delete namespace consensus-engine
# Aguardar 30s
./deploy-fase1-componentes-faltantes.sh
```
