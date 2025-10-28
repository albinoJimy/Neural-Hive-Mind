# Semantic Translation Engine - Guia Completo de Deploy e Testes

## 1. Visão Geral

O **Semantic Translation Engine** é o componente central da **Fase 1** do Neural Hive-Mind, responsável por implementar o **Fluxo B (Geração de Planos Cognitivos)**. Ele consome Intent Envelopes do Kafka, enriquece com contexto operacional, consulta o grafo de conhecimento, e gera Cognitive Plans estruturados e executáveis.

### Papel na Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                     NEURAL HIVE-MIND - FASE 1                    │
└─────────────────────────────────────────────────────────────────┘

Intent Envelope (Kafka: intentions.*)
            ↓
  ┌─────────────────────────┐
  │ Semantic Translation    │
  │ Engine                  │
  │                         │
  │  - Semantic Parser      │
  │  - DAG Generator        │
  │  - Risk Scorer          │
  │  - Explainability Gen   │
  └─────────────────────────┘
            ↓
   Cognitive Plan (estruturado)
            ↓
MongoDB (Ledger Cognitivo) + Redis (Cache)
            ↓
Kafka (topic: plans.ready)
            ↓
   [Consensus Engine]
```

### Funcionalidades Principais

1. **Análise Semântica**: Enriquecimento de intenções com contexto operacional
2. **Consulta ao Grafo**: Busca de padrões e workflows no Neo4j
3. **Geração de DAG**: Decomposição da intenção em passos executáveis (Directed Acyclic Graph)
4. **Avaliação de Riscos**: Cálculo de scores de segurança, prioridade e complexidade
5. **Explicabilidade**: Geração de raciocínio e fontes de conhecimento utilizadas
6. **Persistência**: Registro no ledger cognitivo com hash SHA-256 (blockchain-like)
7. **Publicação**: Envio do plano para o Kafka (topic: plans.ready)

---

## 2. Pré-requisitos

### 2.1 Infraestrutura Base

#### Minikube Configurado

```bash
# Verificar status
minikube status

# Se não estiver rodando, iniciar com recursos adequados
minikube start --cpus=4 --memory=8192 --disk-size=40g

# Habilitar addons necessários
minikube addons enable ingress
minikube addons enable metrics-server
minikube addons enable storage-provisioner
```

#### Namespaces Criados

```bash
# Aplicar namespaces do projeto
kubectl apply -f k8s/bootstrap/namespaces.yaml

# Verificar namespaces
kubectl get namespaces | grep -E "neural-hive|redis|mongodb|neo4j|observability"
```

### 2.2 Dependências Deployadas

O Semantic Translation Engine depende de múltiplos serviços de infraestrutura que devem estar rodando **antes** do deploy:

#### ✅ Kafka (Strimzi)

```bash
# Verificar Kafka
kubectl get pods -n neural-hive-kafka

# Deve mostrar:
# neural-hive-kafka-0                Ready   1/1
# neural-hive-kafka-1                Ready   1/1
# neural-hive-kafka-2                Ready   1/1
# neural-hive-entity-operator-...    Ready   2/2
# neural-hive-zookeeper-0            Ready   1/1
# neural-hive-zookeeper-1            Ready   1/1
# neural-hive-zookeeper-2            Ready   1/1
```

**Se não estiver deployado:**
```bash
./scripts/deploy/deploy-kafka-local.sh
```

#### ✅ Neo4j (Grafo de Conhecimento)

```bash
# Verificar Neo4j
kubectl get pods -n neo4j

# Deve mostrar pods Neo4j rodando
```

**Se não estiver deployado:**
```bash
# Deploy do Neo4j via script ou Helm
./scripts/deploy/deploy-neo4j-local.sh
```

#### ✅ MongoDB (Ledger Cognitivo)

```bash
# Verificar MongoDB
kubectl get pods -n mongodb-cluster

# Deve mostrar pods MongoDB rodando
```

**Se não estiver deployado:**
```bash
./scripts/deploy/deploy-mongodb-local.sh
```

#### ✅ Redis (Cache)

```bash
# Verificar Redis
kubectl get pods -n redis-cluster

# Deve mostrar pods Redis rodando
```

**Se não estiver deployado:**
```bash
./scripts/deploy/deploy-redis-local.sh
```

#### ✅ OpenTelemetry Collector (Observabilidade)

```bash
# Verificar OpenTelemetry
kubectl get pods -n observability

# Deve mostrar OpenTelemetry Collector rodando
```

**Se não estiver deployado:**
```bash
./scripts/deploy/deploy-observability-local.sh
```

### 2.3 Verificar Topics Kafka

Os topics Kafka devem existir antes do deploy:

```bash
# Listar topics
kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list

# Deve incluir:
# intentions.business
# intentions.technical
# intentions.infrastructure
# intentions.security
# plans.ready
```

**Se os topics não existirem**, criar manualmente:

```bash
# Criar topics de intenções
for TOPIC in intentions.business intentions.technical intentions.infrastructure intentions.security; do
  kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
    /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create \
    --topic ${TOPIC} \
    --partitions 3 \
    --replication-factor 2
done

# Criar topic de planos
kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic plans.ready \
  --partitions 3 \
  --replication-factor 2
```

---

## 3. Deploy Passo a Passo

### 3.1 Preparar Ambiente Docker

O Minikube possui seu próprio daemon Docker. Para construir a imagem localmente sem precisar de um registry externo, configure o Docker para usar o daemon do Minikube:

```bash
# Configurar Docker para usar daemon do Minikube
eval $(minikube docker-env)

# Verificar configuração
docker ps

# Deve mostrar containers do Minikube
```

⚠️ **Importante**: Este comando afeta apenas a sessão do shell atual. Se abrir um novo terminal, execute novamente.

### 3.2 Build da Imagem Docker

```bash
# Navegar para o diretório do serviço
cd /home/jimy/Base/Neural-Hive-Mind/services/semantic-translation-engine

# Build da imagem
docker build -t neural-hive-mind/semantic-translation-engine:local .

# Saída esperada:
# [+] Building 45.2s (15/15) FINISHED
# => [internal] load build definition...
# => [builder 1/4] FROM python:3.11-slim...
# => [stage-1 3/6] COPY --from=builder...
# => => writing image sha256:...
# => => naming to docker.io/neural-hive-mind/semantic-translation-engine:local

# Verificar imagem
docker images | grep semantic-translation-engine

# Deve mostrar:
# neural-hive-mind/semantic-translation-engine   local   <IMAGE_ID>   <SIZE>
```

**Troubleshooting Build:**

Se o build falhar, verificar:
- Arquivo `requirements.txt` está presente
- Diretório `src/` existe e contém `main.py`
- Conexão de internet para baixar dependências Python

### 3.3 Criar Namespace

```bash
# Criar namespace
kubectl create namespace semantic-translation-engine

# Aplicar labels
kubectl label namespace semantic-translation-engine \
  neural-hive.io/component=semantic-translator \
  neural-hive.io/layer=cognitiva \
  --overwrite

# Verificar namespace
kubectl get namespace semantic-translation-engine --show-labels
```

### 3.4 Criar Secrets

O serviço precisa de credenciais para acessar as dependências. Em ambiente local, usamos valores padrão:

```bash
# Criar secret
kubectl create secret generic semantic-translation-engine-secrets \
  --from-literal=kafka_sasl_password="" \
  --from-literal=neo4j_password="neo4j" \
  --from-literal=mongodb_password="" \
  --from-literal=redis_password="" \
  -n semantic-translation-engine

# Verificar secret
kubectl get secret semantic-translation-engine-secrets -n semantic-translation-engine
```

### 3.5 Deploy via Helm

```bash
# Voltar para raiz do projeto
cd /home/jimy/Base/Neural-Hive-Mind

# Verificar valores locais
cat ./helm-charts/semantic-translation-engine/values-local.yaml

# Deploy via Helm
helm upgrade --install semantic-translation-engine \
  ./helm-charts/semantic-translation-engine \
  --namespace semantic-translation-engine \
  --values ./helm-charts/semantic-translation-engine/values-local.yaml \
  --set image.tag=local \
  --set image.pullPolicy=IfNotPresent \
  --wait --timeout 10m

# Saída esperada:
# Release "semantic-translation-engine" has been upgraded. Happy Helming!
# NAME: semantic-translation-engine
# LAST DEPLOYED: ...
# NAMESPACE: semantic-translation-engine
# STATUS: deployed
```

**Parâmetros Importantes:**
- `--set image.tag=local`: Usa a imagem local construída
- `--set image.pullPolicy=IfNotPresent`: Não tenta pull de registry externo
- `--wait`: Aguarda pods ficarem prontos
- `--timeout 10m`: Timeout de 10 minutos para deployment

### 3.6 Verificar Deployment

```bash
# Verificar rollout
kubectl rollout status deployment/semantic-translation-engine -n semantic-translation-engine

# Saída esperada:
# deployment "semantic-translation-engine" successfully rolled out

# Verificar pods
kubectl get pods -n semantic-translation-engine

# Deve mostrar:
# NAME                                        READY   STATUS    RESTARTS   AGE
# semantic-translation-engine-xxxxx-yyyyy     1/1     Running   0          2m

# Ver logs iniciais
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine --tail=20

# Logs esperados devem incluir:
# Starting Semantic Translation Engine
# Initializing infrastructure clients...
# Neo4j client initialized
# MongoDB client initialized
# Redis client initialized
# Kafka consumer connected
# Semantic Translation Engine started successfully
```

---

## 4. Validação de Conectividade

### 4.1 Health Checks

#### Liveness Probe (GET /health)

```bash
# Port-forward para pod
kubectl port-forward -n semantic-translation-engine \
  svc/semantic-translation-engine 8000:8000 &

# Testar health
curl http://localhost:8000/health

# Resposta esperada:
# {
#   "status": "healthy",
#   "service": "semantic-translation-engine",
#   "version": "1.0.0"
# }

# Parar port-forward
kill %1
```

#### Readiness Probe (GET /ready)

```bash
# Port-forward
kubectl port-forward -n semantic-translation-engine \
  svc/semantic-translation-engine 8000:8000 &

# Testar readiness
curl http://localhost:8000/ready

# Resposta esperada:
# {
#   "ready": true,
#   "checks": {
#     "kafka_consumer": true,
#     "kafka_producer": true,
#     "neo4j": true,
#     "mongodb": true,
#     "redis": true
#   }
# }

# Parar port-forward
kill %1
```

Se alguma dependência estiver `false`, investigar:
- Logs do pod: `kubectl logs -n semantic-translation-engine <pod-name>`
- Status da dependência: `kubectl get pods -n <namespace-da-dependencia>`

### 4.2 Verificar Conexões nos Logs

```bash
# Filtrar logs de conexão
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  | grep -E "Connected|Established|Initialized"

# Deve mostrar mensagens como:
# Neo4j connection established
# MongoDB client initialized
# Redis connection established
# Kafka consumer connected to bootstrap servers
```

---

## 5. Testes End-to-End

### 5.1 Executar Script de Teste Automatizado

O script `test-semantic-translation-engine-local.sh` realiza validação completa do serviço:

```bash
# Executar testes
./tests/test-semantic-translation-engine-local.sh

# O script executa:
# 1. Validação de infraestrutura
# 2. Validação do deployment
# 3. Teste de conectividade
# 4. Teste end-to-end (fluxo completo)
# 5. Validação de métricas
# 6. Resumo final
```

**Saída Esperada:**

```
========================================
TESTES DO SEMANTIC TRANSLATION ENGINE
========================================

========================================
1. VALIDAÇÃO DE INFRAESTRUTURA
========================================
[✓] Kafka está rodando
[✓] Neo4j está rodando
[✓] MongoDB está rodando
[✓] Redis está rodando
[✓] Topic intentions.business existe
[✓] Topic plans.ready existe

========================================
2. VALIDAÇÃO DO DEPLOYMENT
========================================
[✓] Pod semantic-translation-engine-xxx está Running
[✓] Nenhum erro crítico encontrado nos logs
[✓] Endpoint /health retornou 200 OK
[✓] Endpoint /ready retornou resposta
[✓] Status do Kafka consumer disponível
[✓] Status do Neo4j disponível
[✓] Endpoint /metrics está disponível

========================================
4. TESTE END-TO-END (FLUXO COMPLETO)
========================================
[✓] Intent Envelope publicado
[✓] Intent Envelope foi consumido
[✓] Logs indicam geração de plano cognitivo
[✓] Plano cognitivo publicado no topic plans.ready
[✓] Plano contém campo plan_id
[✓] Plano contém campo intent_id
[✓] Plano contém campo steps

========================================
✅ TODOS OS TESTES PASSARAM!
========================================
```

### 5.2 Teste Manual Detalhado

Se preferir executar os passos manualmente para entender o fluxo:

#### Passo 1: Criar Intent Envelope

```bash
# Definir variáveis
INTENT_ID="test-intent-$(date +%s)"
TIMESTAMP_MS=$(date +%s)000

# Criar Intent Envelope JSON
INTENT_ENVELOPE=$(cat <<EOF
{
  "id": "${INTENT_ID}",
  "actor": {
    "type": "human",
    "id": "user-123",
    "name": "João Silva"
  },
  "intent": {
    "text": "Criar API REST para gerenciar produtos com operações CRUD completas",
    "domain": "business",
    "classification": "api-creation",
    "entities": [
      {"type": "resource", "value": "produtos"},
      {"type": "operation", "value": "CRUD"}
    ],
    "keywords": ["API", "REST", "produtos", "CRUD", "gerenciar"]
  },
  "confidence": 0.95,
  "context": {
    "session_id": "session-${TIMESTAMP_MS}",
    "user_id": "user-123",
    "tenant_id": "tenant-acme",
    "channel": "web"
  },
  "constraints": {
    "priority": "high",
    "security_level": "internal"
  },
  "timestamp": ${TIMESTAMP_MS}
}
EOF
)

echo "Intent ID: ${INTENT_ID}"
```

#### Passo 2: Publicar no Kafka

```bash
# Publicar Intent Envelope
kubectl run kafka-producer-manual --restart='Never' \
  --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace neural-hive-kafka \
  --command -- sh -c "echo '${INTENT_ENVELOPE}' | \
    /opt/bitnami/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server neural-hive-kafka-bootstrap:9092 \
    --topic intentions.business"

# Aguardar publicação
sleep 3

# Limpar pod temporário
kubectl delete pod kafka-producer-manual -n neural-hive-kafka --force --grace-period=0
```

#### Passo 3: Verificar Consumo

```bash
# Ver logs do semantic-translation-engine
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=50 | grep "${INTENT_ID}"

# Deve mostrar:
# Intent Envelope received: test-intent-xxxxx
# Processing intent: test-intent-xxxxx
```

#### Passo 4: Aguardar Geração do Plano

```bash
# Aguardar 10-15 segundos para processamento
sleep 15

# Verificar geração do plano
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=100 | grep -A 5 "Cognitive Plan generated"

# Extrair plan_id (exemplo)
PLAN_ID=$(kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=100 | grep -oP '"plan_id":\s*"[^"]+"' | head -1)

echo "Plan ID: ${PLAN_ID}"
```

#### Passo 5: Consumir Plano do Kafka

```bash
# Consumir mensagem do topic plans.ready
kubectl run kafka-consumer-manual --restart='Never' \
  --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace neural-hive-kafka \
  --command -- sh -c "/opt/bitnami/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server neural-hive-kafka-bootstrap:9092 \
    --topic plans.ready \
    --from-beginning \
    --max-messages 1 \
    --timeout-ms 10000"

# Aguardar consumo
sleep 5

# Ver logs (contém o Cognitive Plan JSON)
kubectl logs kafka-consumer-manual -n neural-hive-kafka

# Limpar
kubectl delete pod kafka-consumer-manual -n neural-hive-kafka --force --grace-period=0
```

**Estrutura Esperada do Cognitive Plan:**

```json
{
  "plan_id": "plan-xxxxx",
  "intent_id": "test-intent-xxxxx",
  "domain": "business",
  "steps": [
    {
      "step_id": "step-1",
      "action": "create_database_schema",
      "description": "Criar schema de banco de dados para produtos",
      "dependencies": [],
      "estimated_duration": 300,
      "resources_required": {}
    },
    {
      "step_id": "step-2",
      "action": "implement_crud_endpoints",
      "description": "Implementar endpoints REST CRUD",
      "dependencies": ["step-1"],
      "estimated_duration": 1800,
      "resources_required": {}
    }
  ],
  "risk_assessment": {
    "overall_score": 0.65,
    "priority_score": 0.8,
    "security_score": 0.5,
    "complexity_score": 0.6,
    "risk_level": "medium",
    "mitigation_strategies": [...]
  },
  "explainability": {
    "reasoning": "...",
    "knowledge_sources": [...],
    "confidence_factors": {...},
    "alternative_approaches": [...]
  },
  "metadata": {...},
  "created_at": 1234567890000,
  "version": "1.0.0"
}
```

#### Passo 6: Validar Persistência no MongoDB

```bash
# Conectar ao MongoDB
MONGO_POD=$(kubectl get pods -n mongodb-cluster -o jsonpath='{.items[0].metadata.name}')

# Consultar ledger cognitivo
kubectl exec -n mongodb-cluster ${MONGO_POD} -- mongosh --quiet --eval "
  db = db.getSiblingDB('neural_hive');
  db.cognitive_ledger.find({intent_id: '${INTENT_ID}'}).pretty();
"

# Deve retornar documento com:
# - entry_id
# - plan_id
# - intent_id
# - event_type: "plan_generated"
# - payload: {...}
# - hash: "sha256:..."
# - previous_hash: "sha256:..." (se não for o primeiro)
# - timestamp
```

#### Passo 7: Validar Cache no Redis

```bash
# Conectar ao Redis
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=neural-hive-cache -o jsonpath='{.items[0].metadata.name}')

# Verificar chaves de contexto
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS 'context:*'

# Verificar chaves de planos
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS 'plan:*'

# Ver conteúdo de uma chave (exemplo)
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli GET "plan:${PLAN_ID}"
```

---

## 6. Validação de Métricas

### 6.1 Endpoint Prometheus

```bash
# Port-forward para métricas
kubectl port-forward -n semantic-translation-engine \
  svc/semantic-translation-engine 8080:8080 &

# Consultar métricas
curl http://localhost:8080/metrics | grep neural_hive

# Parar port-forward
kill %1
```

### 6.2 Métricas Disponíveis

#### Contadores

```prometheus
# Total de planos gerados (por domínio e status)
neural_hive_plans_generated_total{domain="business", status="success"} 5

# Total de mensagens consumidas do Kafka
neural_hive_kafka_messages_consumed_total{topic="intentions.business"} 10

# Total de mensagens produzidas no Kafka
neural_hive_kafka_messages_produced_total{topic="plans.ready"} 5

# Total de erros
neural_hive_errors_total{error_type="neo4j_timeout", component="neo4j_client"} 0
```

#### Histogramas

```prometheus
# Latência de geração de planos (em segundos)
neural_hive_plan_generation_duration_seconds_bucket{domain="business", le="0.5"} 2
neural_hive_plan_generation_duration_seconds_bucket{domain="business", le="1.0"} 4
neural_hive_plan_generation_duration_seconds_sum{domain="business"} 3.8
neural_hive_plan_generation_duration_seconds_count{domain="business"} 5

# Latência de queries Neo4j
neural_hive_neo4j_query_duration_seconds_bucket{query_type="find_similar_intents", le="0.1"} 15

# Latência de operações MongoDB
neural_hive_mongodb_operation_duration_seconds_bucket{operation="insert_plan", le="0.05"} 20
```

#### Gauges

```prometheus
# Taxa de acerto do cache Redis
neural_hive_redis_cache_hit_rate 0.75
```

### 6.3 Visualização no Grafana (Opcional)

Se tiver Grafana deployado:

```bash
# Port-forward para Grafana
kubectl port-forward -n observability svc/grafana 3000:3000 &

# Acessar: http://localhost:3000
# Usuário: admin
# Senha: (verificar secret do Grafana)

# Importar dashboard Prometheus e consultar métricas neural_hive_*
```

---

## 7. Troubleshooting

### 7.1 Pod não inicia

**Problema**: Pod fica em estado `Pending`, `CrashLoopBackOff` ou `ImagePullBackOff`

#### Verificar eventos:

```bash
kubectl describe pod -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine
```

#### Causas comuns:

**ImagePullBackOff:**
- Imagem não foi construída localmente
- Solução: Rebuild da imagem
  ```bash
  eval $(minikube docker-env)
  cd services/semantic-translation-engine
  docker build -t neural-hive-mind/semantic-translation-engine:local .
  kubectl rollout restart deployment/semantic-translation-engine -n semantic-translation-engine
  ```

**CrashLoopBackOff:**
- Erro no código ou dependências não disponíveis
- Solução: Verificar logs
  ```bash
  kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine
  ```

**Pending:**
- Recursos insuficientes
- Solução: Verificar recursos do Minikube
  ```bash
  kubectl describe node minikube | grep -A 5 "Allocated resources"
  ```

### 7.2 Consumer não conecta ao Kafka

**Sintomas**: Logs mostram erros de conexão com Kafka ou timeout

#### Verificar conectividade:

```bash
# Testar conectividade de rede
kubectl run kafka-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local 9092
```

#### Verificar configuração:

```bash
# Ver configuração Kafka no ConfigMap
kubectl get configmap -n semantic-translation-engine semantic-translation-engine -o yaml | grep KAFKA
```

#### Causas comuns:

- Kafka não está rodando
  ```bash
  kubectl get pods -n neural-hive-kafka
  ```
- Endereço incorreto no ConfigMap
- Problemas de DNS no Kubernetes

### 7.3 Neo4j timeout

**Sintomas**: Logs mostram `Neo4jTimeout` ou queries lentas

#### Verificar conectividade:

```bash
kubectl run neo4j-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv neo4j.neo4j.svc.cluster.local 7687
```

#### Aumentar timeout:

Editar ConfigMap:
```bash
kubectl edit configmap semantic-translation-engine -n semantic-translation-engine

# Alterar:
NEO4J_QUERY_TIMEOUT_MS: "30000"  # 30 segundos
```

Reiniciar deployment:
```bash
kubectl rollout restart deployment/semantic-translation-engine -n semantic-translation-engine
```

#### Verificar logs Neo4j:

```bash
kubectl logs -n neo4j -l app=neo4j
```

### 7.4 MongoDB não conecta

**Sintomas**: Erros de conexão MongoDB nos logs

#### Verificar conectividade:

```bash
kubectl run mongo-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017
```

#### Verificar logs MongoDB:

```bash
kubectl logs -n mongodb-cluster -l app=mongodb
```

#### Verificar URI de conexão:

```bash
kubectl get configmap -n semantic-translation-engine semantic-translation-engine -o yaml | grep MONGODB_URI
```

### 7.5 Redis não conecta

**Sintomas**: Cache não funciona, erros Redis nos logs

#### Verificar conectividade:

```bash
kubectl run redis-test --image=busybox --rm -it --restart=Never \
  -n semantic-translation-engine \
  -- nc -zv redis.redis-cluster.svc.cluster.local 6379
```

#### Testar Redis:

```bash
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=neural-hive-cache -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli PING

# Deve retornar: PONG
```

---

## 8. Comandos Úteis

### Logs e Debugging

```bash
# Ver logs em tempo real
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine -f

# Ver logs das últimas N linhas
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine --tail=100

# Ver logs com timestamps
kubectl logs -n semantic-translation-engine \
  -l app.kubernetes.io/name=semantic-translation-engine --timestamps

# Ver logs de container específico (se houver múltiplos)
kubectl logs -n semantic-translation-engine <pod-name> -c semantic-translation-engine
```

### Port-Forwarding

```bash
# Port-forward para health checks
kubectl port-forward -n semantic-translation-engine svc/semantic-translation-engine 8000:8000

# Port-forward para métricas
kubectl port-forward -n semantic-translation-engine svc/semantic-translation-engine 8080:8080

# Port-forward para pod específico
kubectl port-forward -n semantic-translation-engine <pod-name> 8000:8000
```

### Gerenciamento do Deployment

```bash
# Reiniciar deployment
kubectl rollout restart deployment/semantic-translation-engine -n semantic-translation-engine

# Verificar status do rollout
kubectl rollout status deployment/semantic-translation-engine -n semantic-translation-engine

# Ver histórico de rollouts
kubectl rollout history deployment/semantic-translation-engine -n semantic-translation-engine

# Rollback para revisão anterior
kubectl rollout undo deployment/semantic-translation-engine -n semantic-translation-engine

# Escalar replicas
kubectl scale deployment/semantic-translation-engine \
  -n semantic-translation-engine --replicas=2

# Editar deployment
kubectl edit deployment/semantic-translation-engine -n semantic-translation-engine
```

### Rebuild e Redeploy

```bash
# Rebuild completo
eval $(minikube docker-env)
cd services/semantic-translation-engine
docker build -t neural-hive-mind/semantic-translation-engine:local .
cd -
kubectl rollout restart deployment/semantic-translation-engine -n semantic-translation-engine

# Deletar e redeployar via Helm
helm uninstall semantic-translation-engine -n semantic-translation-engine
./scripts/deploy/deploy-semantic-translation-engine-local.sh
```

### Inspecionar Recursos

```bash
# Ver todos os recursos do namespace
kubectl get all -n semantic-translation-engine

# Descrever deployment
kubectl describe deployment/semantic-translation-engine -n semantic-translation-engine

# Ver ConfigMap
kubectl get configmap semantic-translation-engine -n semantic-translation-engine -o yaml

# Ver Secret
kubectl get secret semantic-translation-engine-secrets -n semantic-translation-engine -o yaml

# Ver PVC (se houver)
kubectl get pvc -n semantic-translation-engine
```

---

## 9. Scripts de Automação

### Deploy Automatizado

```bash
# Script de deploy local
./scripts/deploy/deploy-semantic-translation-engine-local.sh

# O script executa:
# 1. Validação de pré-requisitos
# 2. Build da imagem Docker
# 3. Criação de namespace e secrets
# 4. Deploy via Helm
# 5. Validação pós-deploy
# 6. Output de comandos úteis
```

### Testes Automatizados

```bash
# Script de testes end-to-end
./tests/test-semantic-translation-engine-local.sh

# O script valida:
# - Infraestrutura
# - Deployment
# - Conectividade
# - Fluxo completo Intent → Cognitive Plan
# - Métricas
```

---

## 10. Próximos Passos

Após validar o Semantic Translation Engine, prosseguir com:

### 10.1 Deploy dos Especialistas Neurais (5 pods)

```bash
./scripts/deploy/deploy-specialist-business-local.sh
./scripts/deploy/deploy-specialist-technical-local.sh
./scripts/deploy/deploy-specialist-infrastructure-local.sh
./scripts/deploy/deploy-specialist-security-local.sh
./scripts/deploy/deploy-specialist-evolution-local.sh
```

### 10.2 Deploy do Consensus Engine

```bash
./scripts/deploy/deploy-consensus-engine-local.sh
```

### 10.3 Deploy do Memory Layer API

```bash
./scripts/deploy/deploy-memory-layer-api-local.sh
```

### 10.4 Teste End-to-End da Fase 1

```bash
./tests/phase1-end-to-end-test.sh
```

---

## 11. Referências

- **Arquitetura Geral**: `ARCHITECTURE.md`
- **Deployment Local**: `DEPLOYMENT_LOCAL.md`
- **Helm Chart**: `helm-charts/semantic-translation-engine/`
- **Código Fonte**: `services/semantic-translation-engine/src/`
- **README do Serviço**: `services/semantic-translation-engine/README.md`

---

**Documentação mantida por**: Neural Hive-Mind Team
**Última atualização**: 2025-10-06
**Versão**: 1.0.0
