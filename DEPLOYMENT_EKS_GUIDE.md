# Guia de Deployment Neural Hive-Mind no Amazon EKS

Este guia fornece instruções completas para fazer o deploy do Neural Hive-Mind no Amazon EKS (Elastic Kubernetes Service).

## 📋 Índice

- [Pré-requisitos](#pré-requisitos)
- [Arquitetura EKS](#arquitetura-eks)
- [Fase 1: Preparação do Ambiente](#fase-1-preparação-do-ambiente)
- [Fase 2: Deploy da Infraestrutura](#fase-2-deploy-da-infraestrutura)
- [Fase 3: Build e Push de Imagens](#fase-3-build-e-push-de-imagens)
- [Fase 4: Deploy dos Componentes](#fase-4-deploy-dos-componentes)
- [Fase 5: Validação e Testes](#fase-5-validação-e-testes)
- [Troubleshooting](#troubleshooting)
- [Custos Estimados](#custos-estimados)

## 🎯 Pré-requisitos

### Ferramentas Necessárias

```bash
# 1. AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Verificar instalação
aws --version  # Deve ser >= 2.0

# 2. Terraform
wget https://releases.hashicorp.com/terraform/1.6.6/terraform_1.6.6_linux_amd64.zip
unzip terraform_1.6.6_linux_amd64.zip
sudo mv terraform /usr/local/bin/
terraform version  # Deve ser >= 1.5

# 3. kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
kubectl version --client

# 4. Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

### Credenciais AWS

```bash
# Configurar credenciais AWS
aws configure

# Inserir:
# AWS Access Key ID: <sua-access-key>
# AWS Secret Access Key: <sua-secret-key>
# Default region: us-east-1
# Default output format: json

# Verificar credenciais
aws sts get-caller-identity
```

### Permissões IAM Necessárias

O usuário/role AWS precisa das seguintes permissões:

- **EC2**: Criar VPCs, subnets, security groups, NAT gateways
- **EKS**: Criar e gerenciar clusters
- **ECR**: Criar repositórios e fazer push de imagens
- **IAM**: Criar roles e policies para EKS
- **S3**: Criar bucket para Terraform state (opcional mas recomendado)
- **CloudWatch**: Criar log groups

## 🏗️ Arquitetura EKS

```
┌─────────────────────────────────────────────────────────────────┐
│                    AWS REGIÃO (us-east-1)                       │
├─────────────────────────────────────────────────────────────────┤
│  VPC (10.0.0.0/16)                                              │
│  ├─ Availability Zone A (us-east-1a)                            │
│  │  ├─ Public Subnet (10.0.1.0/24)   → NAT Gateway             │
│  │  └─ Private Subnet (10.0.11.0/24) → EKS Worker Nodes        │
│  ├─ Availability Zone B (us-east-1b)                            │
│  │  ├─ Public Subnet (10.0.2.0/24)   → NAT Gateway             │
│  │  └─ Private Subnet (10.0.12.0/24) → EKS Worker Nodes        │
│  └─ Availability Zone C (us-east-1c)                            │
│     ├─ Public Subnet (10.0.3.0/24)   → NAT Gateway             │
│     └─ Private Subnet (10.0.13.0/24) → EKS Worker Nodes        │
├─────────────────────────────────────────────────────────────────┤
│  EKS Cluster (neural-hive-dev)                                  │
│  ├─ Control Plane (Managed by AWS)                              │
│  ├─ Worker Nodes (t3.medium/t3.large)                           │
│  │  ├─ Auto Scaling (1-9 nodes)                                 │
│  │  └─ EBS gp3 SSD (50GB per node)                              │
│  └─ Add-ons                                                      │
│     ├─ AWS Load Balancer Controller                             │
│     └─ Cluster Autoscaler                                       │
├─────────────────────────────────────────────────────────────────┤
│  ECR (Elastic Container Registry)                               │
│  ├─ neural-hive-dev/gateway-intencoes                           │
│  ├─ neural-hive-dev/semantic-translation-engine                 │
│  ├─ neural-hive-dev/specialist-*                                │
│  ├─ neural-hive-dev/consensus-engine                            │
│  └─ neural-hive-dev/memory-layer-api                            │
├─────────────────────────────────────────────────────────────────┤
│  S3 Bucket (terraform-state-neural-hive-dev)                    │
│  └─ Terraform state files                                       │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 Fase 1: Preparação do Ambiente

### 1.1. Configurar Variáveis de Ambiente

```bash
# Exportar variáveis do ambiente
export ENV=dev  # ou staging, prod
export AWS_REGION=us-east-1
export CLUSTER_NAME=neural-hive-${ENV}
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Senhas para componentes de memória (IMPORTANTE: Use senhas fortes!)
export TF_VAR_mongodb_root_password="<senha-forte-mongodb>"
export TF_VAR_neo4j_password="<senha-forte-neo4j>"
export TF_VAR_clickhouse_admin_password="<senha-forte-clickhouse-admin>"
export TF_VAR_clickhouse_readonly_password="<senha-forte-clickhouse-readonly>"
export TF_VAR_clickhouse_writer_password="<senha-forte-clickhouse-writer>"

# Salvar variáveis em arquivo para reutilização
cat > ~/.neural-hive-env <<EOF
export ENV=${ENV}
export AWS_REGION=${AWS_REGION}
export CLUSTER_NAME=${CLUSTER_NAME}
export AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
export TF_VAR_mongodb_root_password="${TF_VAR_mongodb_root_password}"
export TF_VAR_neo4j_password="${TF_VAR_neo4j_password}"
export TF_VAR_clickhouse_admin_password="${TF_VAR_clickhouse_admin_password}"
export TF_VAR_clickhouse_readonly_password="${TF_VAR_clickhouse_readonly_password}"
export TF_VAR_clickhouse_writer_password="${TF_VAR_clickhouse_writer_password}"
EOF

chmod 600 ~/.neural-hive-env
echo "source ~/.neural-hive-env" >> ~/.bashrc
```

### 1.2. Configurar Backend S3 para Terraform State (Recomendado)

```bash
# Criar bucket S3 para Terraform state
aws s3api create-bucket \
  --bucket terraform-state-neural-hive-${ENV} \
  --region ${AWS_REGION}

# Habilitar versionamento
aws s3api put-bucket-versioning \
  --bucket terraform-state-neural-hive-${ENV} \
  --versioning-configuration Status=Enabled

# Habilitar criptografia
aws s3api put-bucket-encryption \
  --bucket terraform-state-neural-hive-${ENV} \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Criar DynamoDB table para state locking
aws dynamodb create-table \
  --table-name terraform-locks-neural-hive-${ENV} \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region ${AWS_REGION}

# Criar arquivo backend.hcl
cat > environments/${ENV}/backend.hcl <<EOF
bucket         = "terraform-state-neural-hive-${ENV}"
key            = "neural-hive-mind/${ENV}/terraform.tfstate"
region         = "${AWS_REGION}"
encrypt        = true
dynamodb_table = "terraform-locks-neural-hive-${ENV}"
EOF
```

### 1.3. Validar Configuração do Terraform

```bash
cd infrastructure/terraform

# Validar arquivo tfvars
cat ../environments/${ENV}/terraform.tfvars

# Verificar se senhas estão configuradas
echo "MongoDB: ${TF_VAR_mongodb_root_password:0:5}***"
echo "Neo4j: ${TF_VAR_neo4j_password:0:5}***"
echo "ClickHouse Admin: ${TF_VAR_clickhouse_admin_password:0:5}***"
```

## 🏗️ Fase 2: Deploy da Infraestrutura

### 2.1. Inicializar Terraform

```bash
cd infrastructure/terraform

# Inicializar com backend S3
terraform init -backend-config=../../environments/${ENV}/backend.hcl -reconfigure

# Ou inicializar com backend local (não recomendado para produção)
# terraform init
```

### 2.2. Validar e Planejar

```bash
# Validar configuração
terraform validate

# Planejar mudanças
terraform plan \
  -var-file=../../environments/${ENV}/terraform.tfvars \
  -out=tfplan

# Revisar o plano cuidadosamente antes de aplicar
```

### 2.3. Aplicar Infraestrutura

```bash
# Aplicar mudanças (isso criará VPC, EKS, ECR, etc)
# ATENÇÃO: Isso irá criar recursos na AWS que geram custos!
terraform apply -auto-approve -var-file=../../environments/${ENV}/terraform.tfvars

# Tempo estimado: 15-20 minutos para criar o cluster EKS
```

### 2.4. Configurar kubectl

```bash
# Atualizar kubeconfig para acessar o cluster EKS
aws eks update-kubeconfig \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION}

# Verificar conectividade
kubectl cluster-info
kubectl get nodes

# Você deve ver 3 nodes (um por AZ)
```

### 2.5. Extrair Outputs do Terraform

```bash
# Salvar outputs importantes
cd infrastructure/terraform

export ECR_REGISTRY=$(terraform output -raw ecr_registry_url 2>/dev/null || echo "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com")
export CLUSTER_ENDPOINT=$(terraform output -raw cluster_endpoint 2>/dev/null)
export CLUSTER_CA=$(terraform output -raw cluster_certificate_authority_data 2>/dev/null)
export SIGSTORE_IRSA_ROLE_ARN=$(terraform output -raw sigstore_irsa_role_arn 2>/dev/null)

echo "ECR Registry: ${ECR_REGISTRY}"
echo "Cluster Endpoint: ${CLUSTER_ENDPOINT}"

# Adicionar ao arquivo de env
cat >> ~/.neural-hive-env <<EOF
export ECR_REGISTRY=${ECR_REGISTRY}
export CLUSTER_ENDPOINT=${CLUSTER_ENDPOINT}
EOF
```

## 📦 Fase 3: Build e Push de Imagens

### 3.1. Criar Repositórios ECR para Componentes

```bash
# Lista de componentes que precisam de repositórios ECR
COMPONENTS=(
  "gateway-intencoes"
  "semantic-translation-engine"
  "specialist-business"
  "specialist-technical"
  "specialist-behavior"
  "specialist-evolution"
  "specialist-architecture"
  "consensus-engine"
  "memory-layer-api"
)

# Criar repositórios ECR
for component in "${COMPONENTS[@]}"; do
  echo "Criando repositório: ${component}"
  aws ecr create-repository \
    --repository-name neural-hive-${ENV}/${component} \
    --region ${AWS_REGION} \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    2>/dev/null || echo "Repositório ${component} já existe"
done
```

### 3.2. Login no ECR

```bash
# Login no ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}
```

### 3.3. Build das Imagens Docker

```bash
cd /jimy/Neural-Hive-Mind

# Build do Gateway de Intenções
docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/gateway-intencoes:latest \
  -f services/gateway-intencoes/Dockerfile .

# Build do Semantic Translation Engine
docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/semantic-translation-engine:latest \
  -f services/semantic-translation-engine/Dockerfile .

# Build dos Specialists (todos usam o mesmo Dockerfile base)
for spec in business technical behavior evolution architecture; do
  docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/specialist-${spec}:latest \
    --build-arg SPECIALIST_TYPE=${spec} \
    -f libraries/python/neural_hive_specialists/Dockerfile .
done

# Build do Consensus Engine
docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/consensus-engine:latest \
  -f services/consensus-engine/Dockerfile .

# Build do Memory Layer API
docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/memory-layer-api:latest \
  -f services/memory-layer-api/Dockerfile .
```

### 3.4. Push das Imagens para ECR

```bash
# Push de todas as imagens
for component in "${COMPONENTS[@]}"; do
  echo "Pushing ${component}..."
  docker push ${ECR_REGISTRY}/neural-hive-${ENV}/${component}:latest
done

# Verificar imagens no ECR
aws ecr list-images --repository-name neural-hive-${ENV}/gateway-intencoes --region ${AWS_REGION}
```

### 3.5. Script Orquestrador Completo (Recomendado)

Para executar build, push e atualização de manifestos em um único comando:

```bash
cd /jimy/Neural-Hive-Mind

# Executar fluxo completo
./scripts/build-and-deploy-eks.sh

# Com opções customizadas
./scripts/build-and-deploy-eks.sh \
  --version 1.0.8 \
  --parallel 8 \
  --env staging \
  --region us-west-2
```

Este script automatiza:
- ✅ Validação de pré-requisitos (Docker, AWS CLI, kubectl)
- ✅ Build paralelo de todas as imagens (4-8 min)
- ✅ Push paralelo para ECR com retry logic (5-8 min)
- ✅ Atualização automática de manifestos Helm e K8s (<1 min)
- ✅ Resumo final com estatísticas consolidadas

**Controle de fluxo**:
```bash
# Apenas build e push (sem atualizar manifestos)
./scripts/build-and-deploy-eks.sh --skip-update

# Apenas push (imagens já buildadas localmente)
./scripts/build-and-deploy-eks.sh --skip-build

# Preview de mudanças nos manifestos
./scripts/build-and-deploy-eks.sh --skip-build --skip-push --dry-run
```

Veja todas as opções: `./scripts/build-and-deploy-eks.sh --help`

---

### 3.6. Scripts Individuais (Uso Avançado)

Ou use os scripts individuais:

```bash
# Criar script de build e push
cat > scripts/deploy/build-and-push-eks.sh <<'EOF'
#!/bin/bash
set -euo pipefail

source ~/.neural-hive-env

# Login no ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}

COMPONENTS=(
  "gateway-intencoes:services/gateway-intencoes/Dockerfile"
  "semantic-translation-engine:services/semantic-translation-engine/Dockerfile"
  "consensus-engine:services/consensus-engine/Dockerfile"
  "memory-layer-api:services/memory-layer-api/Dockerfile"
)

SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

# Build e push dos componentes principais
for comp in "${COMPONENTS[@]}"; do
  name=$(echo $comp | cut -d: -f1)
  dockerfile=$(echo $comp | cut -d: -f2)

  echo "Building ${name}..."
  docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/${name}:latest -f ${dockerfile} .

  echo "Pushing ${name}..."
  docker push ${ECR_REGISTRY}/neural-hive-${ENV}/${name}:latest
done

# Build e push dos specialists
for spec in "${SPECIALISTS[@]}"; do
  echo "Building specialist-${spec}..."
  docker build -t ${ECR_REGISTRY}/neural-hive-${ENV}/specialist-${spec}:latest \
    --build-arg SPECIALIST_TYPE=${spec} \
    -f libraries/python/neural_hive_specialists/Dockerfile .

  echo "Pushing specialist-${spec}..."
  docker push ${ECR_REGISTRY}/neural-hive-${ENV}/specialist-${spec}:latest
done

echo "All images built and pushed successfully!"
EOF

chmod +x scripts/deploy/build-and-push-eks.sh

# Executar
./scripts/deploy/build-and-push-eks.sh
```

## 🚀 Fase 4: Deploy dos Componentes

### 4.1. Deploy dos Helm Charts de Segurança

```bash
cd /jimy/Neural-Hive-Mind

# 1. Deploy Istio Service Mesh
helm upgrade --install istio-base helm-charts/istio-base \
  --namespace istio-system \
  --create-namespace \
  --values environments/${ENV}/helm-values/istio-values.yaml \
  --wait

# 2. Deploy OPA Gatekeeper
helm upgrade --install opa-gatekeeper helm-charts/opa-gatekeeper \
  --namespace gatekeeper-system \
  --create-namespace \
  --values environments/${ENV}/helm-values/opa-gatekeeper-values.yaml \
  --wait

# Aguardar Gatekeeper estar pronto
kubectl -n gatekeeper-system wait --for=condition=ready pod \
  -l gatekeeper.sh/operation=webhook --timeout=180s
```

### 4.2. Aplicar Bootstrap Manifests

```bash
# Aplicar namespaces, RBAC, network policies
kubectl apply -f k8s/bootstrap/namespaces.yaml
kubectl apply -f k8s/bootstrap/rbac.yaml
kubectl apply -f k8s/bootstrap/network-policies.yaml
kubectl apply -f k8s/bootstrap/limit-ranges-templates.yaml
kubectl apply -f k8s/bootstrap/resource-quotas-templates.yaml

# Verificar namespaces criados
kubectl get namespaces | grep neural-hive
```

### 4.3. Aplicar Políticas OPA

```bash
# Aplicar constraint templates
kubectl apply -f policies/constraint-templates/

# Aguardar templates serem estabelecidos
sleep 10

# Aplicar constraints
kubectl apply -f policies/constraints/

# Verificar políticas
kubectl get constrainttemplates
kubectl get constraints --all-namespaces
```

### 4.4. Deploy da Infraestrutura de Dados

```bash
# Deploy Kafka (Strimzi)
kubectl apply -f k8s/kafka-local.yaml
kubectl wait kafka/neural-hive-kafka -n kafka --for=condition=Ready --timeout=10m

# Deploy MongoDB
kubectl apply -f infrastructure/terraform/modules/mongodb-cluster/manifests/
kubectl wait statefulset/mongodb -n mongodb-cluster --for=jsonpath='{.status.readyReplicas}'=3 --timeout=10m

# Deploy Neo4j
kubectl apply -f infrastructure/terraform/modules/neo4j-cluster/manifests/
kubectl wait statefulset/neo4j -n neo4j-cluster --for=jsonpath='{.status.readyReplicas}'=3 --timeout=10m

# Deploy Redis
kubectl apply -f k8s/redis-local.yaml
kubectl wait statefulset/redis -n redis-cluster --for=jsonpath='{.status.readyReplicas}'=3 --timeout=5m

# Deploy ClickHouse (opcional para dev)
kubectl apply -f infrastructure/terraform/modules/clickhouse-cluster/manifests/
```

### 4.5. Deploy dos Serviços Cognitivos

**IMPORTANTE**: Antes de aplicar os deployments, você precisa atualizar as imagens nos manifestos para usar o ECR.

```bash
# Atualizar imagens nos deployments
cd k8s

# Exemplo para gateway-intencoes
sed -i "s|image: .*gateway-intencoes.*|image: ${ECR_REGISTRY}/neural-hive-${ENV}/gateway-intencoes:latest|g" \
  gateway-intencoes-deployment.yaml

# Aplicar para todos os componentes
for component in gateway-intencoes semantic-translation-engine consensus-engine memory-layer-api; do
  sed -i "s|image: .*${component}.*|image: ${ECR_REGISTRY}/neural-hive-${ENV}/${component}:latest|g" \
    ${component}-deployment.yaml 2>/dev/null || true
done

# Deploy Gateway de Intenções
kubectl apply -f gateway-intencoes-deployment.yaml
kubectl wait deployment/gateway-intencoes -n gateway-intencoes --for=condition=Available --timeout=5m

# Deploy Semantic Translation Engine
kubectl apply -f semantic-translation-engine-deployment.yaml
kubectl wait deployment/semantic-translation-engine -n semantic-translation-engine --for=condition=Available --timeout=5m

# Deploy Specialists
for spec in business technical behavior evolution architecture; do
  kubectl apply -f specialist-${spec}-deployment.yaml
  kubectl wait deployment/specialist-${spec} -n specialist-${spec} --for=condition=Available --timeout=5m
done

# Deploy Consensus Engine
kubectl apply -f consensus-engine-deployment.yaml
kubectl wait deployment/consensus-engine -n consensus-engine --for=condition=Available --timeout=5m

# Deploy Memory Layer API
kubectl apply -f memory-layer-api-deployment.yaml
kubectl wait deployment/memory-layer-api -n memory-layer-api --for=condition=Available --timeout=5m
```

### 4.6. Script Automatizado de Deployment Completo

Ou use o script fornecido (após ajustes):

```bash
# Executar deploy completo da foundation
./scripts/deploy/deploy-foundation.sh
```

## ✅ Fase 5: Validação e Testes

### 5.1. Verificar Status dos Pods

```bash
# Verificar todos os pods
kubectl get pods --all-namespaces | grep neural-hive

# Verificar pods com problemas
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Ver logs de um pod específico
kubectl logs -n gateway-intencoes deployment/gateway-intencoes --tail=100
```

### 5.2. Verificar Serviços e Endpoints

```bash
# Listar serviços
kubectl get svc --all-namespaces | grep neural-hive

# Verificar endpoints
kubectl get endpoints --all-namespaces | grep neural-hive
```

### 5.3. Executar Testes E2E

```bash
# Teste básico de conectividade
./tests/phase1-pre-test-validation.sh

# Teste end-to-end completo
./tests/phase1-end-to-end-test.sh

# Ver resultados
cat /tmp/phase1-e2e-test-*.json | jq .
```

### 5.4. Acessar Serviços Externamente

```bash
# Port-forward para Gateway de Intenções
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8080:8080

# Em outro terminal, testar
curl -X POST http://localhost:8080/api/v1/intents \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "intent_text": "Analyze the system performance",
    "priority": "high"
  }'

# Port-forward para Grafana (se deployado)
kubectl port-forward -n neural-hive-observability svc/grafana 3000:80

# Acessar: http://localhost:3000
```

### 5.5. Configurar Ingress/Load Balancer (Opcional)

Para exposição externa via Load Balancer:

```bash
# Criar ALB para Gateway
cat > k8s/gateway-ingress.yaml <<EOF
apiVersion: v1
kind: Service
metadata:
  name: gateway-intencoes-lb
  namespace: gateway-intencoes
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: gateway-intencoes
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
EOF

kubectl apply -f k8s/gateway-ingress.yaml

# Obter endereço do Load Balancer
kubectl get svc -n gateway-intencoes gateway-intencoes-lb
```

## 🔧 Troubleshooting

### Pods não iniciam

```bash
# Descrever pod
kubectl describe pod <pod-name> -n <namespace>

# Ver logs
kubectl logs <pod-name> -n <namespace>

# Ver eventos
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

### Imagens não são baixadas do ECR

```bash
# Verificar se nodes têm permissão para pull do ECR
# A role IAM dos nodes deve ter AmazonEC2ContainerRegistryReadOnly

# Verificar se imagem existe no ECR
aws ecr describe-images \
  --repository-name neural-hive-${ENV}/gateway-intencoes \
  --region ${AWS_REGION}
```

### Erros de OPA Gatekeeper

```bash
# Ver logs do Gatekeeper
kubectl logs -n gatekeeper-system -l gatekeeper.sh/operation=webhook

# Desabilitar temporariamente constraints
kubectl delete constraints --all
```

### Cluster EKS não acessível

```bash
# Reconfigurar kubeconfig
aws eks update-kubeconfig --name ${CLUSTER_NAME} --region ${AWS_REGION}

# Verificar security groups
aws ec2 describe-security-groups \
  --filters Name=tag:Name,Values=*${CLUSTER_NAME}* \
  --region ${AWS_REGION}
```

### Custos muito altos

```bash
# Reduzir número de nodes
kubectl scale deployment --all --replicas=1 --all-namespaces

# Parar cluster (dev only)
# Deletar node groups via console ou:
aws eks delete-nodegroup --cluster-name ${CLUSTER_NAME} --nodegroup-name <nodegroup-name>
```

## 💰 Custos Estimados

### Ambiente Dev (Mínimo)

| Recurso | Tipo | Quantidade | Custo/mês (USD) |
|---------|------|------------|-----------------|
| EKS Control Plane | - | 1 | $72 |
| EC2 Nodes | t3.medium | 3 | ~$75 |
| EBS Volumes | gp3 50GB | 3 | ~$15 |
| NAT Gateways | - | 3 | ~$100 |
| ALB/NLB | (opcional) | 0-1 | $0-25 |
| Data Transfer | - | ~50GB | ~$5 |
| **Total Mínimo** | | | **~$267/mês** |

### Ambiente Prod (Recomendado)

| Recurso | Tipo | Quantidade | Custo/mês (USD) |
|---------|------|------------|-----------------|
| EKS Control Plane | - | 1 | $72 |
| EC2 Nodes | m5.large | 6 | ~$450 |
| EBS Volumes | gp3 100GB | 6 | ~$60 |
| NAT Gateways | - | 3 | ~$100 |
| ALB/NLB | - | 2 | ~$50 |
| RDS (PostgreSQL) | db.t3.medium | 1 | ~$100 |
| ElastiCache Redis | cache.r5.large | 2 | ~$250 |
| Data Transfer | - | ~500GB | ~$45 |
| **Total Produção** | | | **~$1,127/mês** |

**Notas:**
- Custos são aproximados e podem variar por região
- Reserved Instances podem reduzir custos em até 30-50%
- Savings Plans também oferecem descontos
- Shutdown de ambientes dev/staging fora do horário comercial pode reduzir custos significativamente

### Dicas para Reduzir Custos

1. **Use Spot Instances** para workloads dev/staging:
```bash
# Adicionar ao terraform.tfvars
capacity_type = "SPOT"
```

2. **Auto-shutdown para ambientes não-prod**:
```bash
# Criar Lambda para parar/iniciar cluster em horários específicos
# Ou usar AWS Instance Scheduler
```

3. **Cluster Autoscaler** agressivo:
```bash
# Reduzir min_nodes_per_zone para 0 em dev
min_nodes_per_zone = 0
```

4. **Use Fargate** para workloads específicos (opcional):
```bash
# Configurar Fargate profiles para jobs batch
```

## 🎯 Próximos Passos

Após o deployment bem-sucedido:

1. **Configurar Monitoramento**:
   - Deploy Prometheus/Grafana
   - Configurar alertas
   - Ver [DEPLOYMENT_LOCAL.md](DEPLOYMENT_LOCAL.md) seção de observabilidade

2. **Configurar CI/CD**:
   - GitHub Actions ou GitLab CI
   - Automação de build e deploy
   - Ver `.github/workflows/`

3. **Implementar Disaster Recovery**:
   - Configurar backups automáticos
   - Testar procedimentos de restore
   - Ver seção Disaster Recovery no README

4. **Otimização de Performance**:
   - Configurar HPA (Horizontal Pod Autoscaler)
   - Ajustar resources/limits
   - Implementar caching agressivo

5. **Hardening de Segurança**:
   - Restringir public_access_cidrs
   - Implementar AWS WAF
   - Configurar GuardDuty e Security Hub

## 📚 Referências

- [AWS EKS Best Practices](https://aws.github.io/aws-eks-best-practices/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Istio Documentation](https://istio.io/latest/docs/)
- [OPA Gatekeeper](https://open-policy-agent.github.io/gatekeeper/)

## 🆘 Suporte

Para problemas ou dúvidas:

1. Verificar [Troubleshooting](#troubleshooting) acima
2. Consultar [OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md)
3. Abrir issue no GitHub

---

🤖 **Neural Hive-Mind - EKS Deployment Guide**
*Deploy completo da IA distribuída na AWS*
