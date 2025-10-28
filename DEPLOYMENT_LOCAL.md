# 🏠 Neural Hive-Mind - Guia de Deployment Local

Guia completo para configurar e executar o Neural Hive-Mind em ambiente local usando Docker, Kubernetes e Minikube.

## 📋 Índice

1. [Pré-requisitos](#-pré-requisitos)
2. [Configuração do Ambiente Local](#-configuração-do-ambiente-local)
3. [Deployment com Minikube](#-deployment-com-minikube)
4. [Fase 2: Deploy da Base de Infraestrutura](#️-fase-2-deploy-da-base-de-infraestrutura)
5. [Deployment com Docker Compose](#-deployment-com-docker-compose)
6. [Validação e Testes](#-validação-e-testes)
7. [Troubleshooting](#-troubleshooting)
8. [Comandos Úteis](#-comandos-úteis)

## 🎯 Pré-requisitos

### Ferramentas Necessárias

```bash
# Verificar versões das ferramentas
docker --version          # >= 24.0.0
kubectl version --client  # >= 1.28.0
minikube version          # >= 1.32.0
helm version              # >= 3.13.0
```

### Instalação das Ferramentas

#### Docker
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Verificar instalação
docker run hello-world
```

#### Minikube
```bash
# Linux
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# macOS
brew install minikube

# Windows (PowerShell como Admin)
New-Item -Path 'c:\' -Name 'minikube' -ItemType Directory -Force
Invoke-WebRequest -OutFile 'c:\minikube\minikube.exe' -Uri 'https://github.com/kubernetes/minikube/releases/latest/download/minikube-windows-amd64.exe' -UseBasicParsing
```

#### kubectl
```bash
# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# macOS
brew install kubectl

# Windows
curl.exe -LO "https://dl.k8s.io/release/v1.29.0/bin/windows/amd64/kubectl.exe"
```

#### Helm
```bash
# Linux/macOS
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Windows
choco install kubernetes-helm
```

### Requisitos de Sistema

- **CPU**: Mínimo 4 cores (recomendado 8 cores)
- **RAM**: Mínimo 8GB (recomendado 16GB)
- **Disco**: Mínimo 20GB livres
- **SO**: Linux, macOS ou Windows 10+

## ⚙️ Configuração do Ambiente Local

### 1. Clone e Prepare o Projeto

```bash
# Clone do repositório
git clone <repository-url>
cd Neural-Hive-Mind

# Definir variáveis de ambiente
export ENV=local
export NAMESPACE=neural-hive-local
```

### 2. Configurar Minikube

```bash
# Iniciar Minikube com configurações adequadas
minikube start \
  --driver=docker \
  --cpus=4 \
  --memory=8192 \
  --disk-size=20g \
  --kubernetes-version=v1.29.0

# Habilitar add-ons necessários
minikube addons enable ingress
minikube addons enable ingress-dns
minikube addons enable metrics-server
minikube addons enable storage-provisioner

# Verificar status
minikube status
kubectl get nodes
```

### 3. Configurar Registry Local

```bash
# Habilitar registry local do Minikube
minikube addons enable registry

# Configurar porta do registry
kubectl port-forward --namespace kube-system service/registry 5000:80 &

# Verificar registry
curl http://localhost:5000/v2/_catalog
```

## 🚀 Deployment com Minikube

### Opção 1: Deploy Automatizado Local

```bash
# Criar script de deploy local
cat > deploy-local.sh << 'EOF'
#!/bin/bash
set -e

echo "🚀 Iniciando deployment local do Neural Hive-Mind"

# 1. Configurar contexto kubectl
kubectl config use-context minikube

# 2. Criar namespaces
kubectl apply -f k8s/bootstrap/namespaces.yaml

# 3. Aplicar RBAC
kubectl apply -f k8s/bootstrap/rbac.yaml

# 4. Aplicar network policies (adaptadas para local)
kubectl apply -f k8s/bootstrap/network-policies.yaml

# 5. Adicionar repositórios Helm
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# 6. Instalar Istio (versão simplificada para local)
helm upgrade --install istio-base istio/base \
  --namespace istio-system \
  --create-namespace \
  --wait

helm upgrade --install istiod istio/istiod \
  --namespace istio-system \
  --values helm-charts/istio-base/values-local.yaml \
  --wait

# 7. Instalar OPA Gatekeeper (simplificado)
helm upgrade --install gatekeeper gatekeeper/gatekeeper \
  --namespace gatekeeper-system \
  --create-namespace \
  --values helm-charts/opa-gatekeeper/values-local.yaml \
  --wait

# 8. Aguardar todos os pods estarem prontos
echo "⏳ Aguardando pods estarem prontos..."
kubectl wait --for=condition=ready pod -l app=istiod -n istio-system --timeout=300s
kubectl wait --for=condition=ready pod -l gatekeeper.sh/operation=webhook -n gatekeeper-system --timeout=180s

echo "✅ Deployment local concluído!"
echo "🔧 Para acessar os serviços, execute: minikube tunnel"
EOF

chmod +x deploy-local.sh
./deploy-local.sh
```

### Opção 2: Deploy Passo-a-Passo Manual

#### Passo 1: Preparar Namespaces e RBAC

```bash
# Aplicar namespaces
kubectl apply -f k8s/bootstrap/namespaces.yaml

# Verificar namespaces criados
kubectl get namespaces | grep neural-hive

# Aplicar RBAC
kubectl apply -f k8s/bootstrap/rbac.yaml

# Aplicar network policies
kubectl apply -f k8s/bootstrap/network-policies.yaml
```

#### Passo 2: Deploy do Istio (Service Mesh)

```bash
# Criar values-local.yaml para Istio
cat > helm-charts/istio-base/values-local.yaml << 'EOF'
global:
  meshID: mesh1
  multiCluster:
    clusterName: local-cluster
  network: network1

pilot:
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi

telemetry:
  v2:
    prometheus:
      configOverride:
        metric_relabeling_configs:
        - source_labels: [__name__]
          regex: istio_.*
          target_label: __tmp_keep_me
          replacement: true
        - source_labels: [__tmp_keep_me]
          regex: true
          action: keep

sidecarInjectorWebhook:
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 128Mi
EOF

# Adicionar repo Helm do Istio
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

# Instalar Istio base
helm upgrade --install istio-base istio/base \
  --namespace istio-system \
  --create-namespace \
  --wait

# Instalar Istiod
helm upgrade --install istiod istio/istiod \
  --namespace istio-system \
  --values helm-charts/istio-base/values-local.yaml \
  --wait

# Verificar instalação
kubectl get pods -n istio-system
kubectl get services -n istio-system
```

#### Passo 3: Deploy do OPA Gatekeeper

```bash
# Criar values-local.yaml para Gatekeeper
cat > helm-charts/opa-gatekeeper/values-local.yaml << 'EOF'
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

audit:
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi

webhook:
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi

replicas: 1
auditReplicas: 1
EOF

# Instalar Gatekeeper
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update

helm upgrade --install gatekeeper gatekeeper/gatekeeper \
  --namespace gatekeeper-system \
  --create-namespace \
  --values helm-charts/opa-gatekeeper/values-local.yaml \
  --wait

# Aguardar webhook estar pronto
kubectl -n gatekeeper-system wait --for=condition=ready pod -l gatekeeper.sh/operation=webhook --timeout=180s

# Aplicar constraint templates e constraints (simplificado para local)
kubectl apply -f policies/constraint-templates/
sleep 10
kubectl apply -f policies/constraints/

# Verificar
kubectl get constrainttemplates
kubectl get constraints -A
```

## 🗄️ Fase 2: Deploy da Base de Infraestrutura

Após completar a Fase 1 (bootstrap com namespaces, RBAC, Istio e OPA Gatekeeper), esta fase instala os componentes de infraestrutura base necessários para os serviços da aplicação.

### Componentes Instalados

Esta fase deploy os seguintes componentes:

1. **Kafka** (Strimzi Operator + Cluster) - Sistema de mensageria
2. **Redis** - Cache em memória
3. **MongoDB** - Banco de dados de documentos
4. **Neo4j** - Banco de dados de grafos
5. **ClickHouse** - Banco de dados analítico
6. **Keycloak** - Autenticação e autorização

### Pré-requisitos da Fase 2

Verifique que a Fase 1 (bootstrap) foi completada com sucesso:

```bash
# Verificar se namespaces foram criados
kubectl get namespaces | grep -E "kafka|redis-cluster|mongodb-cluster|neo4j-cluster|clickhouse-cluster|keycloak"

# Verificar se Istio está rodando
kubectl get pods -n istio-system

# Verificar se OPA Gatekeeper está rodando
kubectl get pods -n gatekeeper-system

# Verificar recursos do cluster
kubectl top nodes
```

### Opção 1: Deploy Automatizado

Execute o script automatizado que deploy todos os componentes em sequência:

```bash
# Executar script de deploy automatizado
./scripts/deploy/deploy-infrastructure-local.sh
```

Este script irá:
- Verificar pré-requisitos
- Deploy Strimzi Kafka Operator e Kafka Cluster
- Deploy Redis
- Deploy MongoDB com operator
- Deploy Neo4j
- Deploy ClickHouse com operator e ZooKeeper
- Deploy Keycloak
- Validar cada componente após deployment
- Gerar relatório de status

**Tempo estimado**: 15-20 minutos

**Logs**: Salvos em `logs/infrastructure-deployment-YYYYMMDD-HHMMSS.log`

### Opção 2: Deploy Manual Passo-a-Passo

Para maior controle, você pode fazer o deploy manual de cada componente:

#### Passo 1: Deploy Strimzi Kafka Operator e Kafka Cluster

```bash
# Criar namespace para Kafka
kubectl create namespace kafka

# Adicionar repositório Helm do Strimzi
helm repo add strimzi https://strimzi.io/charts/
helm repo update

# Instalar Strimzi Kafka Operator
helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
  --namespace kafka \
  --set watchNamespaces=kafka \
  --create-namespace \
  --wait \
  --timeout 10m

# Aguardar operator estar pronto
kubectl wait --for=condition=ready pod \
  -l name=strimzi-cluster-operator \
  -n kafka \
  --timeout=300s

# Deploy do Kafka Cluster
kubectl apply -f k8s/kafka-local.yaml

# Aguardar cluster estar pronto (pode levar 5-10 minutos)
kubectl wait --for=condition=ready kafka neural-hive-kafka \
  -n kafka \
  --timeout=600s

# Verificar pods do Kafka
kubectl get pods -n kafka

# Verificar tópicos criados
KAFKA_POD=$(kubectl get pods -n kafka -l strimzi.io/name=neural-hive-kafka-kafka -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n kafka $KAFKA_POD -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

#### Passo 2: Deploy Redis

```bash
# Criar namespace para Redis
kubectl create namespace redis-cluster

# Deploy Redis
kubectl apply -f k8s/redis-local.yaml

# Aguardar Redis estar pronto
kubectl wait --for=condition=ready pod \
  -l app=neural-hive-cache \
  -n redis-cluster \
  --timeout=180s

# Testar conectividade Redis
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=neural-hive-cache -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli ping
# Deve retornar: PONG
```

#### Passo 3: Deploy MongoDB

```bash
# Criar namespaces
kubectl create namespace mongodb-operator
kubectl create namespace mongodb-cluster

# Instalar MongoDB Community Operator
kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/crd/bases/mongodbcommunity.mongodbcommunity.mongodb.com_mongodbcommunity.yaml
kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/rbac/role.yaml -n mongodb-operator
kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/rbac/role_binding.yaml -n mongodb-operator
kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/rbac/service_account.yaml -n mongodb-operator
kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/manager/manager.yaml -n mongodb-operator

# Aguardar operator
kubectl wait --for=condition=ready pod \
  --all \
  -n mongodb-operator \
  --timeout=300s

# Deploy MongoDB com Helm usando values locais
helm install neural-hive-mongodb ./helm-charts/mongodb \
  --namespace mongodb-cluster \
  --values ./helm-charts/mongodb/values-local.yaml \
  --wait \
  --timeout 10m

# Verificar MongoDB
kubectl get pods -n mongodb-cluster
```

#### Passo 4: Deploy Neo4j

```bash
# Criar namespace
kubectl create namespace neo4j-cluster

# Adicionar repositório Helm do Neo4j
helm repo add neo4j https://helm.neo4j.com/neo4j
helm repo update

# Deploy Neo4j com values locais
helm install neural-hive-neo4j ./helm-charts/neo4j \
  --namespace neo4j-cluster \
  --values ./helm-charts/neo4j/values-local.yaml \
  --wait \
  --timeout 10m

# Verificar Neo4j
kubectl get pods -n neo4j-cluster

# Verificar serviços (Bolt: 7687, HTTP: 7474)
kubectl get svc -n neo4j-cluster
```

#### Passo 5: Deploy ClickHouse

```bash
# Criar namespaces
kubectl create namespace clickhouse-operator
kubectl create namespace clickhouse-cluster

# Instalar ClickHouse Operator
kubectl apply -f https://raw.githubusercontent.com/Altinity/clickhouse-operator/master/deploy/operator/clickhouse-operator-install-bundle.yaml

# Aguardar operator
sleep 30
kubectl wait --for=condition=available deployment/clickhouse-operator \
  -n kube-system \
  --timeout=300s

# Deploy ClickHouse com Helm usando values locais
helm install neural-hive-clickhouse ./helm-charts/clickhouse \
  --namespace clickhouse-cluster \
  --values ./helm-charts/clickhouse/values-local.yaml \
  --wait \
  --timeout 10m

# Verificar ClickHouse e ZooKeeper
kubectl get pods -n clickhouse-cluster

# Verificar serviços (HTTP: 8123, Native: 9000)
kubectl get svc -n clickhouse-cluster
```

#### Passo 6: Deploy Keycloak

```bash
# Criar namespace
kubectl create namespace keycloak

# Deploy Keycloak
kubectl apply -f k8s/keycloak-local.yaml

# Aguardar Keycloak estar pronto
kubectl wait --for=condition=ready pod \
  --all \
  -n keycloak \
  --timeout=300s

# Verificar Keycloak
kubectl get pods -n keycloak
kubectl get svc -n keycloak
```

### Validação da Infraestrutura

Após o deployment, execute o script de validação:

```bash
# Executar validação automatizada
./scripts/validation/validate-infrastructure-local.sh
```

Este script irá:
- Verificar status de cada componente
- Testar conectividade de cada serviço
- Validar operações básicas (queries, leitura/escrita)
- Gerar relatório de saúde

#### Validação Manual de Componentes

**Kafka:**
```bash
# Listar pods
kubectl get pods -n kafka

# Verificar tópicos
KAFKA_POD=$(kubectl get pods -n kafka -l strimzi.io/name=neural-hive-kafka-kafka -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n kafka $KAFKA_POD -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Verificar cluster status
kubectl get kafka neural-hive-kafka -n kafka -o yaml
```

**Redis:**
```bash
# Testar PING
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=neural-hive-cache -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli ping

# Testar SET/GET
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli SET test_key "test_value"
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli GET test_key
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli DEL test_key
```

**MongoDB:**
```bash
# Listar pods
kubectl get pods -n mongodb-cluster

# Testar conexão
MONGODB_POD=$(kubectl get pods -n mongodb-cluster -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh --eval "db.version()"
```

**Neo4j:**
```bash
# Listar pods e serviços
kubectl get pods,svc -n neo4j-cluster

# Testar query Cypher
NEO4J_POD=$(kubectl get pods -n neo4j-cluster -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n neo4j-cluster $NEO4J_POD -- \
  cypher-shell -u neo4j -p local_dev_password "RETURN 1"
```

**ClickHouse:**
```bash
# Listar pods
kubectl get pods -n clickhouse-cluster

# Testar query
CLICKHOUSE_POD=$(kubectl get pods -n clickhouse-cluster -l app=clickhouse -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n clickhouse-cluster $CLICKHOUSE_POD -- \
  clickhouse-client --query "SELECT 1"

# Listar databases
kubectl exec -n clickhouse-cluster $CLICKHOUSE_POD -- \
  clickhouse-client --query "SHOW DATABASES"
```

**Keycloak:**
```bash
# Listar pods
kubectl get pods -n keycloak

# Testar health endpoint
KEYCLOAK_POD=$(kubectl get pods -n keycloak -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n keycloak $KEYCLOAK_POD -- \
  curl -s http://localhost:8080/health
```

### Acessando os Serviços

Use `kubectl port-forward` para acessar os serviços localmente:

```bash
# Kafka
kubectl port-forward -n kafka svc/neural-hive-kafka-kafka-bootstrap 9092:9092

# Redis
kubectl port-forward -n redis-cluster svc/neural-hive-cache 6379:6379

# MongoDB (ajuste o nome do serviço conforme deployment)
kubectl port-forward -n mongodb-cluster svc/<mongodb-service> 27017:27017

# Neo4j Bolt (ajuste o nome do serviço)
kubectl port-forward -n neo4j-cluster svc/<neo4j-service> 7687:7687

# Neo4j Browser
kubectl port-forward -n neo4j-cluster svc/<neo4j-service> 7474:7474

# ClickHouse HTTP
kubectl port-forward -n clickhouse-cluster svc/<clickhouse-service> 8123:8123

# Keycloak
kubectl port-forward -n keycloak svc/<keycloak-service> 8080:8080
```

### Credenciais Padrão (Ambiente Local)

**MongoDB:**
- Usuário: (configurado via operator)
- Senha: `local_dev_password`

**Neo4j:**
- Usuário: `neo4j`
- Senha: `local_dev_password`
- Bolt: `bolt://localhost:7687`
- Browser: `http://localhost:7474`

**ClickHouse:**
- Usuário Admin: `admin`
- Senha Admin: `local_admin_password`
- Usuário ReadOnly: `readonly`
- Senha ReadOnly: `local_readonly_password`
- Usuário Writer: `writer`
- Senha Writer: `local_writer_password`
- HTTP Interface: `http://localhost:8123`

**Keycloak:**
- Console Admin: `http://localhost:8080/admin`
- Credenciais: (configuradas no manifest keycloak-local.yaml)

**Redis:**
- Host: `localhost:6379`
- Sem senha (ambiente local)

**Kafka:**
- Bootstrap Server: `localhost:9092`
- Sem autenticação (ambiente local)

### Troubleshooting Fase 2

#### Kafka não inicia

```bash
# Verificar logs do operator
kubectl logs -n kafka deployment/strimzi-cluster-operator

# Verificar logs do Kafka
kubectl logs -n kafka -l strimzi.io/cluster=neural-hive-kafka

# Verificar descrição do recurso Kafka
kubectl describe kafka neural-hive-kafka -n kafka

# Verificar eventos
kubectl get events -n kafka --sort-by='.lastTimestamp'
```

#### MongoDB não conecta

```bash
# Verificar operator
kubectl logs -n mongodb-operator --all-containers

# Verificar pods MongoDB
kubectl describe pods -n mongodb-cluster

# Verificar secrets
kubectl get secrets -n mongodb-cluster
```

#### Neo4j não inicia

```bash
# Verificar logs
kubectl logs -n neo4j-cluster --all-containers

# Verificar recursos
kubectl describe pods -n neo4j-cluster

# Verificar PVCs
kubectl get pvc -n neo4j-cluster
```

#### ClickHouse falha no deploy

```bash
# Verificar operator
kubectl logs -n kube-system deployment/clickhouse-operator

# Verificar ZooKeeper
kubectl get pods -n clickhouse-cluster -l app=zookeeper
kubectl logs -n clickhouse-cluster -l app=zookeeper

# Verificar ClickHouse
kubectl logs -n clickhouse-cluster -l app=clickhouse
```

#### Problemas de recursos

Se os pods ficarem pendentes por falta de recursos:

```bash
# Verificar recursos disponíveis
kubectl top nodes
kubectl describe nodes

# Reduzir recursos nos values-local.yaml
# Editar arquivos em helm-charts/*/values-local.yaml
# Reduzir requests/limits de CPU e memória

# Redeployar com novos valores
helm upgrade <release-name> <chart-path> \
  --namespace <namespace> \
  --values <values-local.yaml>
```

#### Logs detalhados de componentes

```bash
# Ver todos os logs de um namespace
kubectl logs -n <namespace> --all-containers --tail=100

# Seguir logs em tempo real
kubectl logs -n <namespace> <pod-name> -f

# Logs de múltiplos pods
kubectl logs -n <namespace> -l app=<label> --all-containers
```

### Próximos Passos (Fase 3)

Após validar que todos os componentes da infraestrutura estão rodando:

1. **Deploy do Gateway**: Configurar e deployer o API Gateway
2. **Deploy dos Especialistas**: Deployer os serviços de especialistas (Business, Technical, etc.)
3. **Deploy da Semantic Translation Engine**: Deployer o motor de tradução semântica
4. **Deploy do Consensus Engine**: Deployer o motor de consenso
5. **Testes End-to-End**: Executar testes de integração completos

## 🐳 Deployment com Docker Compose

Para um ambiente ainda mais simples, você pode usar Docker Compose:

```bash
# Criar docker-compose.local.yml
cat > docker-compose.local.yml << 'EOF'
version: '3.8'

services:
  # Redis para cache
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - neural-hive

  # PostgreSQL para dados
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: neural_hive_local
      POSTGRES_USER: neural_hive
      POSTGRES_PASSWORD: local_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - neural-hive

  # Apache Kafka
  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    networks:
      - neural-hive

  kafka:
    image: confluentinc/cp-kafka:latest
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    networks:
      - neural-hive

  # Elasticsearch
  elasticsearch:
    image: elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    networks:
      - neural-hive

  # Kibana
  kibana:
    image: kibana:8.11.0
    depends_on:
      - elasticsearch
    ports:
      - "5601:5601"
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
    networks:
      - neural-hive

  # Jaeger for tracing
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "14268:14268"
    environment:
      COLLECTOR_OTLP_ENABLED: true
    networks:
      - neural-hive

volumes:
  redis_data:
  postgres_data:
  elasticsearch_data:

networks:
  neural-hive:
    driver: bridge
EOF

# Iniciar serviços de infraestrutura
docker compose -f docker-compose.local.yml up -d

# Verificar status dos serviços
docker compose -f docker-compose.local.yml ps
```

## ✅ Validação e Testes

### Verificação da Infraestrutura

```bash
# 1. Verificar status do cluster
kubectl get nodes
kubectl get pods -A

# 2. Verificar namespaces Neural Hive
kubectl get namespaces | grep neural-hive

# 3. Verificar Istio
kubectl get pods -n istio-system
kubectl get services -n istio-system

# 4. Verificar OPA Gatekeeper
kubectl get pods -n gatekeeper-system
kubectl get constrainttemplates
kubectl get constraints -A

# 5. Testar conectividade interna
kubectl run test-pod --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default
```

### Scripts de Validação

```bash
# Executar validações automáticas
./scripts/validation/validate-cluster-health.sh

# Testar conectividade mTLS (se aplicável)
./scripts/validation/test-mtls-connectivity.sh

# Testar políticas OPA
kubectl auth can-i create pods --namespace neural-hive-core
kubectl auth can-i create secrets --namespace neural-hive-memory
```

### Testes de Carga Básicos

```bash
# Teste básico de DNS
kubectl run dns-test --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default.svc.cluster.local

# Teste de conectividade entre namespaces
kubectl run network-test --image=busybox --rm -it --restart=Never --namespace neural-hive-core -- ping neural-hive-memory.svc.cluster.local
```

## 🚨 Troubleshooting

### Problemas Comuns

#### 1. Minikube não inicia
```bash
# Limpar e reiniciar Minikube
minikube delete
minikube start --driver=docker --cpus=4 --memory=8192

# Se driver docker não funciona, tentar com VirtualBox
minikube start --driver=virtualbox
```

#### 2. Pods ficam em Pending
```bash
# Verificar recursos disponíveis
kubectl describe nodes
kubectl top nodes

# Verificar eventos de erro
kubectl get events --sort-by='.lastTimestamp' -A

# Verificar descrição do pod problemático
kubectl describe pod <pod-name> -n <namespace>
```

#### 3. Registry local não acessível
```bash
# Verificar se port-forward está ativo
ps aux | grep "port-forward"

# Recriar port-forward para registry
kubectl port-forward --namespace kube-system service/registry 5000:80 &

# Testar acesso ao registry
curl http://localhost:5000/v2/_catalog
```

#### 4. Helm releases falham
```bash
# Listar releases com problemas
helm list -A --failed

# Ver logs detalhados do release
helm get notes <release-name> -n <namespace>
helm get values <release-name> -n <namespace>

# Fazer rollback se necessário
helm rollback <release-name> -n <namespace>
```

#### 5. Docker Compose não funciona
```bash
# Verificar logs dos serviços
docker compose -f docker-compose.local.yml logs

# Parar e reiniciar serviços específicos
docker compose -f docker-compose.local.yml restart postgres

# Limpar volumes se necessário
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

### Logs Úteis

```bash
# Logs do Minikube
minikube logs

# Logs do Istio
kubectl logs -n istio-system deployment/istiod

# Logs do Gatekeeper
kubectl logs -n gatekeeper-system deployment/gatekeeper-controller-manager

# Logs de um pod específico
kubectl logs <pod-name> -n <namespace> -f
```

## 🔧 Comandos Úteis

### Gerenciamento do Minikube
```bash
# Status do cluster
minikube status

# Acessar dashboard do Kubernetes
minikube dashboard

# Obter IP do Minikube
minikube ip

# Criar túnel para LoadBalancers
minikube tunnel

# SSH no nó do Minikube
minikube ssh

# Parar cluster
minikube stop

# Deletar cluster
minikube delete
```

### Monitoramento
```bash
# Monitoramento em tempo real
watch kubectl get pods -A

# Recursos por namespace
kubectl top pods -A
kubectl top nodes

# Eventos recentes
kubectl get events --sort-by='.lastTimestamp' -A --watch

# Status do service mesh
istioctl proxy-status
istioctl analyze

# Verificar políticas
kubectl get constraints -A -o wide
```

### Desenvolvimento Local
```bash
# Port-forward para serviços
kubectl port-forward svc/<service-name> 8080:80 -n <namespace>

# Executar shell em pod
kubectl exec -it <pod-name> -n <namespace> -- /bin/bash

# Copiar arquivos para/do pod
kubectl cp <local-file> <namespace>/<pod-name>:/path/to/file
kubectl cp <namespace>/<pod-name>:/path/to/file <local-file>

# Aplicar manifests com dry-run
kubectl apply -f <manifest> --dry-run=client -o yaml
```

### Limpeza
```bash
# Limpar recursos não utilizados
kubectl delete pods --field-selector=status.phase=Succeeded -A
kubectl delete pods --field-selector=status.phase=Failed -A

# Limpar Docker Compose
docker compose -f docker-compose.local.yml down -v --remove-orphans

# Limpar imagens Docker não utilizadas
docker system prune -a
```

---

## 📝 Próximos Passos

Após ter o ambiente local funcionando:

1. **Deploy dos Serviços**: Configure e implante os microserviços específicos
2. **Testes de Integração**: Execute os testes de integração completos
3. **Observabilidade**: Configure monitoramento e logging locais
4. **Desenvolvimento**: Use o ambiente para desenvolvimento iterativo

## 🤖 Support

Para problemas específicos do ambiente local, consulte:
- Logs do Minikube: `minikube logs`
- Status dos pods: `kubectl get pods -A`
- Eventos do cluster: `kubectl get events --sort-by='.lastTimestamp' -A`

---

🤖 **Neural Hive-Mind Local Deployment Guide**
*Guia completo para ambiente de desenvolvimento local*