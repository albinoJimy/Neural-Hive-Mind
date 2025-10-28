# Setup Local - Neural Hive-Mind no Kubernetes

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Pré-requisitos](#pré-requisitos)
3. [Componentes Implantados](#componentes-implantados)
4. [Instalação Passo a Passo](#instalação-passo-a-passo)
5. [Testando o Gateway de Intenções](#testando-o-gateway-de-intenções)
6. [Troubleshooting](#troubleshooting)
7. [Próximos Passos](#próximos-passos)

## 🎯 Visão Geral

Este documento descreve como configurar e executar o Neural Hive-Mind localmente usando **Kubernetes (Docker Desktop)**, **Istio Service Mesh** e todos os componentes de infraestrutura necessários.

### Arquitetura Local

```
┌─────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Keycloak   │  │    Kafka     │  │    Redis     │      │
│  │  (OAuth2)    │  │  (Strimzi)   │  │ (Standalone) │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Gateway de Intenções (FastAPI)              │   │
│  │  - ASR (Whisper tiny)                                │   │
│  │  - NLU (spaCy pt_core_news_sm)                       │   │
│  │  - Redis Client (auto-detection)                     │   │
│  │  - Kafka Producer (JSON fallback)                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                 Istio Service Mesh                    │   │
│  │  - mTLS entre serviços                                │   │
│  │  - Sidecar injection automática                       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Pré-requisitos

### Software Necessário

- **Docker Desktop** 4.x+ com Kubernetes habilitado
- **kubectl** 1.28+
- **Helm** 3.x+
- **Python** 3.11+ (para desenvolvimento local)
- **curl**, **jq** (ferramentas CLI)

### Recursos Mínimos

- **CPU**: 4 cores
- **Memória**: 8 GB RAM
- **Disco**: 20 GB livres

### Verificar Instalação

```bash
# Verificar Kubernetes
kubectl version --client

# Verificar Helm
helm version

# Verificar Docker Desktop Kubernetes
kubectl cluster-info
```

## 📦 Componentes Implantados

### 1. Istio Service Mesh (v1.23.0)

**Finalidade**: Service mesh com mTLS, observabilidade e gerenciamento de tráfego.

**Recursos**:
- Namespace: `istio-system`
- Componentes: Istiod, Ingress Gateway, Egress Gateway
- Configurações: mTLS STRICT entre serviços

**Health Check**:
```bash
kubectl get pods -n istio-system
```

### 2. Keycloak (OAuth2/OIDC)

**Finalidade**: Provedor de autenticação e autorização.

**Recursos**:
- Namespace: `keycloak`
- Database: PostgreSQL embutido
- Admin: `admin` / `admin`
- URL: http://localhost:8888 (via port-forward)

**Realm Criado**:
- Nome: `neural-hive`
- Client ID: `gateway-intencoes`
- Client Secret: *Gerado automaticamente*

**Port-Forward**:
```bash
kubectl port-forward -n keycloak svc/keycloak 8888:8080
```

### 3. Kafka (Strimzi Operator)

**Finalidade**: Message broker para eventos de intenções.

**Recursos**:
- Namespace: `kafka`
- Operator: Strimzi Cluster Operator
- Cluster: `neural-hive-kafka`
- Modo: KRaft (sem ZooKeeper)
- Versão: Kafka 4.1.0

**Tópicos Criados**:
```
intentions-business
intentions-infrastructure
intentions-security
intentions-technical
intentions-validation
intentions.validation
```

**Verificar Tópicos**:
```bash
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### 4. Redis (Standalone)

**Finalidade**: Cache e deduplicação de intenções.

**Recursos**:
- Namespace: `default`
- Modo: Standalone (não cluster)
- Sem autenticação (ambiente dev)

**Configuração do Gateway**:
```yaml
REDIS_CLUSTER_NODES: redis.default.svc.cluster.local:6379
REDIS_MODE: standalone
```

### 5. Gateway de Intenções

**Finalidade**: Captura, processamento e roteamento de intenções.

**Recursos**:
- Namespace: `default`
- Imagem: `neural-hive-mind/gateway-intencoes:local`
- Replicas: 1
- Porta: 8000

**Pipelines Configurados**:
- **ASR**: OpenAI Whisper (modelo `tiny`)
- **NLU**: spaCy (`pt_core_news_sm`)

**Variáveis de Ambiente Importantes**:
```yaml
TOKEN_VALIDATION_ENABLED: "false"  # Desabilitado para testes locais
REDIS_MODE: "standalone"
KAFKA_BOOTSTRAP_SERVERS: "neural-hive-kafka-bootstrap.kafka.svc.cluster.local:9092"
```

## 🚀 Instalação Passo a Passo

### Passo 1: Preparar Ambiente Kubernetes

```bash
# Verificar cluster
kubectl get nodes

# Criar namespaces
kubectl create namespace istio-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace keycloak --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Habilitar Istio injection no namespace default
kubectl label namespace default istio-injection=enabled --overwrite
```

### Passo 2: Instalar Istio

```bash
# Baixar Istio (se ainda não tiver)
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.23.0 sh -

# Instalar Istio
istioctl install --set profile=demo -y

# Verificar instalação
kubectl get pods -n istio-system
```

### Passo 3: Instalar Keycloak

```bash
# Adicionar Helm repo
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Instalar Keycloak
helm install keycloak bitnami/keycloak \
  --namespace keycloak \
  --set auth.adminUser=admin \
  --set auth.adminPassword=admin \
  --set production=false \
  --set proxy=edge

# Aguardar inicialização
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=keycloak -n keycloak --timeout=300s
```

**Configurar Realm e Client**:
```bash
# Port-forward Keycloak
kubectl port-forward -n keycloak svc/keycloak 8888:8080 &

# Aguardar disponibilidade
sleep 10

# Obter token admin
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8888/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=admin" \
  -d "grant_type=password" | jq -r '.access_token')

# Criar realm neural-hive
curl -X POST http://localhost:8888/admin/realms \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "realm": "neural-hive",
    "enabled": true,
    "sslRequired": "none"
  }'

# Criar client gateway-intencoes
curl -X POST http://localhost:8888/admin/realms/neural-hive/clients \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "gateway-intencoes",
    "enabled": true,
    "publicClient": false,
    "serviceAccountsEnabled": true,
    "directAccessGrantsEnabled": true
  }'
```

**Nota**: O client secret é gerado automaticamente. Para recuperá-lo, use a UI do Keycloak em http://localhost:8888.

### Passo 4: Instalar Kafka (Strimzi)

```bash
# Instalar Strimzi Operator
kubectl create -f 'https://strimzi.io/install/latest?namespace=kafka' -n kafka

# Aguardar operator
kubectl wait --for=condition=ready pod -l name=strimzi-cluster-operator -n kafka --timeout=300s

# Criar cluster Kafka
cat <<EOF | kubectl apply -n kafka -f -
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: neural-hive-kafka
spec:
  kafka:
    version: 4.1.0
    replicas: 1
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      offsets.topic.replication.factor: 1
      transaction.state.log.replication.factor: 1
      transaction.state.log.min.isr: 1
    storage:
      type: ephemeral
  zookeeper:
    replicas: 0
  entityOperator:
    topicOperator: {}
    userOperator: {}
EOF

# Aguardar cluster
kubectl wait kafka/neural-hive-kafka --for=condition=Ready --timeout=600s -n kafka
```

**Criar Tópicos**:
```bash
# Tópico de validação
cat <<EOF | kubectl apply -n kafka -f -
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: intentions.validation
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: 604800000
    segment.bytes: 1073741824
EOF

# Tópicos por domínio
for domain in business technical infrastructure security; do
  cat <<EOF | kubectl apply -n kafka -f -
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: intentions-${domain}
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 5
  replicas: 1
  config:
    retention.ms: 2592000000
EOF
done
```

### Passo 5: Instalar Redis

```bash
# Criar ConfigMap
kubectl create configmap redis-config \
  --from-literal=maxmemory=256mb \
  --from-literal=maxmemory-policy=allkeys-lru \
  --dry-run=client -o yaml | kubectl apply -f -

# Deploy Redis
kubectl create deployment redis \
  --image=redis:7-alpine \
  --dry-run=client -o yaml | kubectl apply -f -

# Expor serviço
kubectl expose deployment redis --port=6379 --target-port=6379

# Verificar
kubectl get pods -l app=redis
```

### Passo 6: Build e Deploy Gateway

```bash
# Build imagem Docker
docker build -t neural-hive-mind/gateway-intencoes:local \
  -f services/gateway-intencoes/Dockerfile \
  --build-arg VERSION=1.0.0-local \
  .

# Criar Deployment
kubectl create deployment gateway-intencoes \
  --image=neural-hive-mind/gateway-intencoes:local \
  --dry-run=client -o yaml > /tmp/gateway-deployment.yaml

# Adicionar variáveis de ambiente
cat <<EOF >> /tmp/gateway-deployment.yaml
        env:
        - name: ENVIRONMENT
          value: "dev"
        - name: TOKEN_VALIDATION_ENABLED
          value: "false"
        - name: REDIS_CLUSTER_NODES
          value: "redis.default.svc.cluster.local:6379"
        - name: REDIS_MODE
          value: "standalone"
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "neural-hive-kafka-bootstrap.kafka.svc.cluster.local:9092"
        - name: KEYCLOAK_URL
          value: "http://keycloak.keycloak.svc.cluster.local:8080"
        - name: KEYCLOAK_REALM
          value: "neural-hive"
        - name: SCHEMA_REGISTRY_URL
          value: ""
EOF

# Aplicar deployment
kubectl apply -f /tmp/gateway-deployment.yaml

# Expor serviço
kubectl expose deployment gateway-intencoes --port=8000 --target-port=8000

# Aguardar pod
kubectl wait --for=condition=ready pod -l app=gateway-intencoes --timeout=180s

# Verificar health
kubectl exec deployment/gateway-intencoes -- curl -s http://localhost:8000/health | jq
```

## 🧪 Testando o Gateway de Intenções

### 1. Port-Forward do Gateway

```bash
kubectl port-forward svc/gateway-intencoes 8000:8000
```

### 2. Testar Endpoint de Saúde

```bash
curl http://localhost:8000/health | jq
```

**Resposta Esperada**:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-02T09:36:18.038844",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "components": {
    "redis": {"status": "healthy"},
    "asr_pipeline": {"status": "healthy"},
    "nlu_pipeline": {"status": "healthy"},
    "kafka_producer": {"status": "healthy"},
    "oauth2_validator": {"status": "healthy"}
  }
}
```

### 3. Enviar Intenção de Texto

```bash
curl -X POST http://localhost:8000/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Quero solicitar um empréstimo de 5000 reais para reformar minha casa",
    "language": "pt-BR",
    "metadata": {
      "source": "test",
      "user_id": "test-user-123"
    }
  }' | jq
```

**Resposta Esperada**:
```json
{
  "intent_id": "6bc5e037-542d-4dd9-a745-8141cd9d8c59",
  "correlation_id": "dd0b04f8-d2ab-400e-a818-b4e75750bf04",
  "status": "routed_to_validation",
  "confidence": 0.2,
  "domain": "technical",
  "classification": "general",
  "processing_time_ms": 3570.915,
  "requires_manual_validation": true,
  "validation_reason": "confidence_below_threshold",
  "confidence_threshold": 0.75
}
```

### 4. Verificar Mensagens no Kafka

```bash
# Listar tópicos
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Consumir mensagens do tópico técnico (alta confiança)
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.technical \
  --from-beginning \
  --max-messages 5 \
  --timeout-ms 10000

# Consumir mensagens do tópico de validação (baixa confiança)
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.validation \
  --from-beginning \
  --max-messages 5 \
  --timeout-ms 10000

# Consumir mensagens do tópico de segurança
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.security \
  --from-beginning \
  --max-messages 5 \
  --timeout-ms 10000 | jq
```

**Exemplo de Mensagem Kafka (JSON)**:
```json
{
  "id": "aacb05db-6ec4-406b-a4e4-577cfd556cd2",
  "version": "1.0.0",
  "correlationId": "fb877fca-75d1-4236-9b6a-45da829e4cc9",
  "actor": {
    "id": "test-user-123",
    "actorType": "HUMAN",
    "name": "test-user"
  },
  "intent": {
    "text": "Implementar monitoramento de performance da API",
    "domain": "TECHNICAL",
    "classification": "performance",
    "originalLanguage": "pt-BR",
    "keywords": ["monitoramento", "performance"]
  },
  "confidence": 0.95,
  "timestamp": 1759399033294,
  "schemaVersion": 1
}
```

## 🔍 Troubleshooting

### Pod do Gateway Não Inicia

**Sintoma**: Pod fica em `CrashLoopBackOff` ou `ImagePullBackOff`

**Solução**:
```bash
# Verificar logs
kubectl logs -l app=gateway-intencoes --tail=100

# Verificar eventos
kubectl describe pod -l app=gateway-intencoes

# Rebuild imagem se necessário
docker build -t neural-hive-mind/gateway-intencoes:local \
  -f services/gateway-intencoes/Dockerfile .

# Recriar pod
kubectl delete pod -l app=gateway-intencoes
```

### Redis Connection Refused

**Sintoma**: Gateway reporta erro "connection refused" para Redis

**Solução**:
```bash
# Verificar Redis
kubectl get pods -l app=redis

# Testar conexão
kubectl run redis-test --rm -it --image=redis:7-alpine -- \
  redis-cli -h redis.default.svc.cluster.local ping

# Verificar serviço
kubectl get svc redis
```

### Kafka Producer Timeout

**Sintoma**: Timeout ao enviar mensagens para Kafka

**Solução**:
```bash
# Verificar Kafka
kubectl get pods -n kafka

# Testar conectividade
kubectl run kafka-test --rm -it --image=confluentinc/cp-kafka:latest -- \
  kafka-broker-api-versions --bootstrap-server neural-hive-kafka-bootstrap.kafka.svc.cluster.local:9092

# Verificar configuração do gateway
kubectl get deployment gateway-intencoes -o yaml | grep KAFKA_BOOTSTRAP_SERVERS
```

### Keycloak Token Invalid

**Sintoma**: Erro 401 Unauthorized ao enviar intenção

**Solução 1 - Desabilitar validação (dev)**:
```bash
kubectl set env deployment/gateway-intencoes TOKEN_VALIDATION_ENABLED=false
```

**Solução 2 - Configurar OAuth2 corretamente**:
1. Acessar Keycloak UI: http://localhost:8888 (após port-forward)
2. Login: `admin` / `admin`
3. Selecionar realm `neural-hive`
4. Ir em Clients → `gateway-intencoes`
5. Copiar Client Secret
6. Testar token:
```bash
TOKEN=$(curl -s -X POST http://localhost:8888/realms/neural-hive/protocol/openid-connect/token \
  -d "client_id=gateway-intencoes" \
  -d "client_secret=SEU_CLIENT_SECRET" \
  -d "grant_type=client_credentials" | jq -r '.access_token')

curl -X POST http://localhost:8000/intentions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "teste", "language": "pt-BR"}' | jq
```

### Modelos ML Não Encontrados

**Sintoma**: Logs mostram "Modelo pt_core_news_sm não encontrado"

**Solução**:
```bash
# Rebuild imagem incluindo download de modelos
# (Já está incluído no Dockerfile, mas pode falhar em networks restritas)

# Verificar se modelos foram baixados
kubectl exec deployment/gateway-intencoes -- ls -la /app/models
kubectl exec deployment/gateway-intencoes -- python3 -c "import spacy; print(spacy.util.get_installed_models())"
```

## 📝 Próximos Passos

### 1. Habilitar Autenticação OAuth2

- [ ] Obter client secret do Keycloak
- [ ] Configurar `TOKEN_VALIDATION_ENABLED=true`
- [ ] Atualizar deployment do gateway
- [ ] Testar fluxo OAuth2 completo

### 2. Configurar Schema Registry

- [ ] Instalar Confluent Schema Registry
- [ ] Registrar schema Avro `intent-envelope.avsc`
- [ ] Atualizar variável `SCHEMA_REGISTRY_URL` no gateway
- [ ] Testar serialização Avro

### 3. Implementar Observabilidade

- [ ] Instalar Jaeger (tracing)
- [ ] Instalar Prometheus + Grafana (métricas)
- [ ] Configurar exportadores OpenTelemetry
- [ ] Criar dashboards

### 4. Deploy de Mais Serviços

- [ ] Motor de Validação de Intenções
- [ ] Motor de Orquestração
- [ ] Serviços de Domínio (Business, Technical, etc.)

### 5. Migrar para Produção

- [ ] Configurar TLS/mTLS
- [ ] Habilitar Redis Cluster
- [ ] Configurar Kafka multi-broker
- [ ] Implementar backup/restore
- [ ] Configurar autoscaling (HPA)

## 📚 Referências

- [Documentação Istio](https://istio.io/latest/docs/)
- [Strimzi Kafka Operator](https://strimzi.io/docs/operators/latest/overview.html)
- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenTelemetry](https://opentelemetry.io/docs/)

---

**Última Atualização**: 2025-10-02
**Versão**: 1.0.0
**Ambiente**: Kubernetes Local (Docker Desktop)
