# Semantic Translation Engine - Troubleshooting Guide

## Overview

Este guia fornece soluções para problemas comuns que podem ocorrer durante o deployment e operação do Semantic Translation Engine no ambiente Kubernetes local.

## Problema 1: Pod não inicia (ImagePullBackOff)

**Causa**: Imagem Docker não encontrada no registry do Minikube/Kind

**Sintomas**:
```bash
kubectl get pods -n semantic-translation-engine
# NAME                                          READY   STATUS             RESTARTS   AGE
# semantic-translation-engine-xxxxx-xxxxx      0/1     ImagePullBackOff   0          1m
```

**Solução**:
```bash
# 1. Reconstruir a imagem no registry do cluster
eval $(minikube docker-env)  # ou use o contexto apropriado para Kind

# 2. Build da imagem
cd /jimy/Neural-Hive-Mind
docker build -f services/semantic-translation-engine/Dockerfile \
  -t neural-hive-mind/semantic-translation-engine:1.0.0 .

# 3. Verificar que a imagem foi criada
docker images | grep semantic-translation-engine

# 4. Forçar recriação do pod
kubectl delete pod -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine

# 5. Aguardar nova criação
kubectl get pods -n semantic-translation-engine -w
```

**Verificação**:
```bash
kubectl describe pod -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine | grep -A 5 "Events:"
```

---

## Problema 2: Pod em CrashLoopBackOff

**Causa**: Erro na inicialização do serviço (geralmente falha ao conectar com dependências)

**Sintomas**:
```bash
kubectl get pods -n semantic-translation-engine
# NAME                                          READY   STATUS              RESTARTS   AGE
# semantic-translation-engine-xxxxx-xxxxx      0/1     CrashLoopBackOff    5          3m
```

**Diagnóstico**:
```bash
# 1. Verificar logs completos
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine --tail=200

# 2. Verificar eventos do pod
kubectl describe pod -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine
```

**Possíveis causas e soluções**:

### 2.1. Falha ao conectar com Neo4j
```bash
# Verificar se Neo4j está rodando
kubectl get pods -n neo4j-cluster

# Testar conectividade
kubectl run neo4j-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  nc -zv neo4j.neo4j-cluster.svc.cluster.local 7687

# Se falhar, verificar configuração no ConfigMap
kubectl get configmap -n semantic-translation-engine \
  semantic-translation-engine -o yaml | grep NEO4J_URI
```

### 2.2. Falha ao conectar com MongoDB
```bash
# Verificar se MongoDB está rodando
kubectl get pods -n mongodb-cluster

# Testar conectividade
kubectl run mongo-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017

# Verificar credenciais no Secret
kubectl get secret -n semantic-translation-engine \
  semantic-translation-engine -o yaml
```

### 2.3. Falha ao conectar com Redis
```bash
# Verificar se Redis está rodando
kubectl get pods -n redis-cluster

# Testar conectividade
kubectl run redis-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  nc -zv neural-hive-cache.redis-cluster.svc.cluster.local 6379
```

### 2.4. Falha ao conectar com Kafka
```bash
# Verificar se Kafka está rodando
kubectl get pods -n kafka

# Testar conectividade
kubectl run kafka-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  nc -zv neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local 9092

# Verificar tópicos Kafka
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list
```

---

## Problema 3: /ready retorna false

**Causa**: Uma ou mais dependências não estão acessíveis

**Sintomas**:
```bash
kubectl exec -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine -- \
  wget -q -O- http://localhost:8000/ready
# {"ready":false,"checks":{"kafka_consumer":true,"kafka_producer":false,"neo4j":true,"mongodb":true,"redis":true}}
```

**Solução**:

### 3.1. Identificar qual check está falhando
```bash
# Obter resposta completa do /ready
READY_JSON=$(kubectl exec -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine -- \
  wget -q -O- http://localhost:8000/ready)

echo $READY_JSON | jq .
```

### 3.2. Para cada check = false, investigar:

**Kafka Producer**:
```bash
# Verificar logs do producer
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine | grep -i "kafka\|producer"

# Verificar configuração
kubectl get configmap -n semantic-translation-engine \
  semantic-translation-engine -o yaml | grep KAFKA_BOOTSTRAP_SERVERS
```

**Neo4j**:
```bash
# Verificar conectividade
kubectl run neo4j-diag --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  nc -zv neo4j.neo4j-cluster.svc.cluster.local 7687

# Verificar credenciais
kubectl get secret -n semantic-translation-engine \
  semantic-translation-engine -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d
```

**MongoDB**:
```bash
# Verificar conectividade
kubectl run mongo-diag --image=mongo:7.0 --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  mongosh mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive --eval "db.runCommand({ ping: 1 })"
```

**Redis**:
```bash
# Verificar conectividade
kubectl run redis-diag --image=redis:7.2 --rm -it --restart=Never \
  -n semantic-translation-engine -- \
  redis-cli -h neural-hive-cache.redis-cluster.svc.cluster.local -p 6379 ping
```

---

## Problema 4: Não consome mensagens do Kafka

**Causa**: Consumer não conectado ou tópicos não existem

**Sintomas**:
- Logs não mostram consumo de mensagens
- Endpoint /ready indica kafka_consumer = false
- Métricas de mensagens consumidas permanecem em 0

**Solução**:

### 4.1. Verificar tópicos Kafka
```bash
# Listar todos os tópicos
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Verificar se os tópicos intentions.* existem
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list | grep intentions
```

### 4.2. Criar tópicos se não existirem
```bash
for TOPIC in intentions.business intentions.technical intentions.infrastructure intentions.security plans.ready; do
  kubectl exec -n kafka neural-hive-kafka-0 -- \
    /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create --if-not-exists \
    --topic $TOPIC \
    --partitions 3 \
    --replication-factor 1
done
```

### 4.3. Verificar consumer group
```bash
# Listar consumer groups
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --list

# Descrever o consumer group do STE
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group semantic-translation-engine
```

### 4.4. Verificar logs do consumer
```bash
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=200 | grep -i "consumer\|subscribed\|partition"
```

---

## Problema 5: Não publica em plans.ready

**Causa**: Erro no processamento ou producer não conectado

**Sintomas**:
- Mensagens são consumidas mas não aparecem no tópico plans.ready
- Logs mostram erros durante o processamento

**Solução**:

### 5.1. Verificar logs para erros no orchestrator
```bash
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=300 | grep -i "error\|exception\|orchestrator\|process_intent"
```

### 5.2. Verificar métricas de erros
```bash
# Port-forward para acessar métricas
kubectl port-forward -n semantic-translation-engine \
  svc/semantic-translation-engine 8000:8000 &

# Consultar métricas de erro
curl http://localhost:8000/metrics | grep neural_hive_errors_total

# Matar port-forward
kill %1
```

### 5.3. Testar producer manualmente
```bash
# Publicar mensagem de teste no plans.ready
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready <<EOF
{"test": "message", "timestamp": $(date +%s)}
EOF

# Consumir para verificar
kubectl exec -n kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --from-beginning \
  --max-messages 1
```

---

## Problema 6: Timeout no Neo4j

**Causa**: Queries demoradas ou Neo4j sobrecarregado

**Sintomas**:
```
Neo4j query timeout exceeded: Query took longer than 50ms
```

**Solução**:

### 6.1. Aumentar timeout no ConfigMap
```bash
# Editar ConfigMap
kubectl edit configmap -n semantic-translation-engine semantic-translation-engine

# Localizar e modificar:
# NEO4J_QUERY_TIMEOUT_MS: "50"
# Para:
# NEO4J_QUERY_TIMEOUT_MS: "30000"  # 30 segundos
```

### 6.2. Restart do deployment
```bash
kubectl rollout restart deployment/semantic-translation-engine \
  -n semantic-translation-engine

kubectl rollout status deployment/semantic-translation-engine \
  -n semantic-translation-engine
```

### 6.3. Verificar performance do Neo4j
```bash
# Verificar uso de recursos
kubectl top pods -n neo4j-cluster

# Verificar logs do Neo4j
kubectl logs -n neo4j-cluster -l app=neo4j --tail=100
```

### 6.4. Considerar escalar Neo4j
```bash
# Se necessário, aumentar recursos
kubectl edit deployment -n neo4j-cluster neo4j
# Aumentar resources.limits.memory e resources.limits.cpu
```

---

## Problema 7: Alta latência no processamento

**Causa**: Múltiplos fatores (dependências lentas, falta de recursos, etc.)

**Diagnóstico**:

### 7.1. Verificar métricas de duração
```bash
kubectl port-forward -n semantic-translation-engine \
  svc/semantic-translation-engine 8000:8000 &

curl http://localhost:8000/metrics | grep neural_hive_plan_generation_duration_seconds

kill %1
```

### 7.2. Verificar uso de recursos do pod
```bash
kubectl top pod -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine
```

### 7.3. Aumentar recursos se necessário
```bash
# Editar values-local.yaml
# Aumentar resources.limits e resources.requests

# Aplicar via Helm
helm upgrade --install semantic-translation-engine \
  ./helm-charts/semantic-translation-engine \
  --namespace semantic-translation-engine \
  --values ./helm-charts/semantic-translation-engine/values-local.yaml
```

---

## Comandos Úteis de Manutenção

### Restart completo do deployment
```bash
kubectl rollout restart deployment/semantic-translation-engine \
  -n semantic-translation-engine
```

### Hard restart (escalar para 0 e depois 1)
```bash
kubectl scale deployment/semantic-translation-engine \
  -n semantic-translation-engine --replicas=0

# Aguardar 10 segundos
sleep 10

kubectl scale deployment/semantic-translation-engine \
  -n semantic-translation-engine --replicas=1
```

### Ver eventos do namespace
```bash
kubectl get events -n semantic-translation-engine \
  --sort-by='.lastTimestamp' | tail -20
```

### Exec no pod para debug
```bash
POD_NAME=$(kubectl get pods -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  -o jsonpath='{.items[0].metadata.name}')

kubectl exec -it -n semantic-translation-engine $POD_NAME -- /bin/bash
```

### Verificar configuração completa
```bash
# ConfigMap
kubectl get configmap -n semantic-translation-engine \
  semantic-translation-engine -o yaml

# Secret
kubectl get secret -n semantic-translation-engine \
  semantic-translation-engine -o yaml

# Deployment
kubectl get deployment -n semantic-translation-engine \
  semantic-translation-engine -o yaml
```

### Limpar recursos e redeploy
```bash
# Deletar tudo
helm uninstall semantic-translation-engine -n semantic-translation-engine
kubectl delete namespace semantic-translation-engine

# Aguardar término
sleep 10

# Redeploy
./deploy-fase1-componentes-faltantes.sh
```

---

## Monitoramento Contínuo

### Verificar logs em tempo real
```bash
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  -f --tail=100
```

### Monitorar pods
```bash
watch kubectl get pods -n semantic-translation-engine
```

### Monitorar recursos
```bash
watch kubectl top pod -n semantic-translation-engine
```

### Dashboard do Kubernetes (se disponível)
```bash
minikube dashboard
# ou
kubectl proxy
# Acessar: http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/
```

---

## Checklist de Health Check Completo

Use este checklist para validar o estado do Semantic Translation Engine:

- [ ] Pod está Running (1/1 Ready)
- [ ] Endpoint /health retorna {"status":"healthy"}
- [ ] Endpoint /ready retorna {"ready":true} com todos checks=true
- [ ] Logs não contêm erros críticos
- [ ] Consumer está subscrito aos tópicos intentions.*
- [ ] Producer está conectado ao Kafka
- [ ] Neo4j, MongoDB, Redis são acessíveis
- [ ] Mensagens de teste são consumidas e processadas
- [ ] Planos cognitivos são publicados em plans.ready
- [ ] Métricas Prometheus estão disponíveis em /metrics
- [ ] Não há restarts frequentes do pod

---

## Contato e Suporte

Para problemas não cobertos neste guia:

1. Coletar logs completos: `kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine > ste-logs.txt`
2. Coletar describe do pod: `kubectl describe pod -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine > ste-describe.txt`
3. Coletar eventos: `kubectl get events -n semantic-translation-engine --sort-by='.lastTimestamp' > ste-events.txt`
4. Compartilhar com a equipe de desenvolvimento

---

**Última atualização**: 2025-11-12
**Versão do documento**: 1.0.0
