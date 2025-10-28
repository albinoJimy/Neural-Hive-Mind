# 🚀 Neural Hive-Mind - Guia de Deployment

Guia completo para deployment da Fase 1 - Fundação do Neural Hive-Mind.

## 📋 Índice

1. [Pré-requisitos](#-pré-requisitos)
2. [Configuração Inicial](#%EF%B8%8F-configuração-inicial)
3. [Deployment Passo-a-Passo](#-deployment-passo-a-passo)
4. [Validação](#-validação)
5. [Troubleshooting](#-troubleshooting)
6. [Rollback](#-rollback)

## 🎯 Pré-requisitos

### Ferramentas Necessárias

```bash
# Verificar versões das ferramentas
terraform --version    # >= 1.5.0
helm version          # >= 3.13.0
kubectl version       # >= 1.28.0
aws --version         # >= 2.0.0
```

### Instalação das Ferramentas

#### Terraform
```bash
# macOS
brew install terraform

# Linux
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
sudo apt-get update && sudo apt-get install terraform
```

#### Helm
```bash
# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

#### kubectl
```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

#### AWS CLI
```bash
# macOS
brew install awscli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### Permissões AWS Requeridas

#### Criar IAM User/Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "eks:*",
        "iam:*",
        "ecr:*",
        "kms:*",
        "logs:*",
        "s3:*",
        "sns:*",
        "lambda:*",
        "events:*"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Configurar Credenciais
```bash
# Opção 1: AWS Configure
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region name: us-east-1
# Default output format: json

# Opção 2: Environment Variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Verificar credenciais
aws sts get-caller-identity
```

## ⚙️ Configuração Inicial

### 1. Clone e Configure

```bash
# Clone do repositório
git clone <repository-url>
cd Neural-Hive-Mind

# Configurar variáveis de ambiente
export ENV=dev                    # ou staging, prod
export AWS_REGION=us-east-1      # ou sua região preferida
export CLUSTER_NAME=neural-hive-${ENV}
```

### 2. Configurar Backend Terraform

```bash
# Criar bucket S3 para estado Terraform
aws s3 mb s3://neural-hive-terraform-state-${ENV} --region ${AWS_REGION}

# Habilitar versionamento
aws s3api put-bucket-versioning \
  --bucket neural-hive-terraform-state-${ENV} \
  --versioning-configuration Status=Enabled

# Configurar encriptação
aws s3api put-bucket-encryption \
  --bucket neural-hive-terraform-state-${ENV} \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

### 3. Customizar Configurações

#### Editar Terraform Variables
```bash
# Editar configurações por ambiente
vim environments/${ENV}/terraform.tfvars

# Verificar configurações principais:
# - environment = "dev"
# - vpc_cidr = "10.0.0.0/16"
# - cluster_name = "neural-hive-dev"
# - node_instance_types = ["t3.medium", "t3.large"]
```

#### Customizar Helm Values
```bash
# Editar valores Istio por ambiente
vim environments/${ENV}/helm-values/istio-values.yaml

# Configurações importantes:
# - Resource limits
# - Logging levels
# - Telemetry sampling rates
```

## 🚀 Deployment Passo-a-Passo

### Opção 1: Deploy Automatizado (Recomendado)

```bash
# Executar script de deploy completo
chmod +x scripts/deploy/deploy-foundation.sh
./scripts/deploy/deploy-foundation.sh

# Acompanhar progresso
# O script executará automaticamente:
# 1. ✅ Validação de pré-requisitos
# 2. 🏗️ Deploy da infraestrutura de rede
# 3. ⚙️ Deploy do cluster Kubernetes
# 4. 🐳 Deploy do container registry
# 5. 📦 Apply dos bootstrap manifests
# 6. 🕸️ Deploy do service mesh (Istio)
# 7. 🚦 Deploy do policy engine (OPA)
# 8. ✅ Validação pós-deployment
```

### Opção 2: Deploy Manual (Passo-a-Passo)

#### Passo 1: Deploy da Rede
```bash
cd infrastructure/terraform/modules/network

# Inicializar Terraform
terraform init \
  -backend-config="bucket=neural-hive-terraform-state-${ENV}" \
  -backend-config="key=neural-hive/${ENV}/network.tfstate" \
  -backend-config="region=${AWS_REGION}"

# Planejar
terraform plan -var-file="../../../../environments/${ENV}/terraform.tfvars"

# Aplicar
terraform apply -var-file="../../../../environments/${ENV}/terraform.tfvars"

# Salvar outputs
terraform output -json > /tmp/network-outputs.json
```

#### Passo 2: Deploy do Cluster
```bash
cd ../k8s-cluster

# Obter outputs da rede
VPC_ID=$(jq -r '.vpc_id.value' /tmp/network-outputs.json)
PRIVATE_SUBNET_IDS=$(jq -r '.private_subnet_ids.value' /tmp/network-outputs.json)
PUBLIC_SUBNET_IDS=$(jq -r '.public_subnet_ids.value' /tmp/network-outputs.json)

# Inicializar
terraform init \
  -backend-config="bucket=neural-hive-terraform-state-${ENV}" \
  -backend-config="key=neural-hive/${ENV}/k8s-cluster.tfstate" \
  -backend-config="region=${AWS_REGION}"

# Aplicar
terraform apply \
  -var="vpc_id=${VPC_ID}" \
  -var='private_subnet_ids='"${PRIVATE_SUBNET_IDS}" \
  -var='public_subnet_ids='"${PUBLIC_SUBNET_IDS}" \
  -var-file="../../../../environments/${ENV}/terraform.tfvars"

# Configurar kubectl
aws eks update-kubeconfig --name ${CLUSTER_NAME} --region ${AWS_REGION}

# Verificar cluster
kubectl get nodes
```

#### Passo 3: Deploy do Registry
```bash
cd ../container-registry

# Obter OIDC provider do cluster
OIDC_PROVIDER_ARN=$(cd ../k8s-cluster && terraform output -raw oidc_provider_arn)
OIDC_ISSUER_URL=$(cd ../k8s-cluster && terraform output -raw oidc_issuer_url)

# Inicializar
terraform init \
  -backend-config="bucket=neural-hive-terraform-state-${ENV}" \
  -backend-config="key=neural-hive/${ENV}/container-registry.tfstate" \
  -backend-config="region=${AWS_REGION}"

# Aplicar
terraform apply \
  -var="oidc_provider_arn=${OIDC_PROVIDER_ARN}" \
  -var="oidc_issuer_url=${OIDC_ISSUER_URL}" \
  -var-file="../../../../environments/${ENV}/terraform.tfvars"
```

#### Passo 4: Bootstrap Kubernetes
```bash
cd ../../../../k8s/bootstrap

# Aplicar namespaces
kubectl apply -f namespaces.yaml

# Aplicar RBAC
kubectl apply -f rbac.yaml

# Aplicar network policies
kubectl apply -f network-policies.yaml

# Verificar
kubectl get namespaces | grep neural-hive
kubectl get networkpolicies -A
```

#### Passo 5: Deploy Istio
```bash
# Adicionar repos Helm
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
  --values helm-charts/istio-base/values.yaml \
  --values environments/${ENV}/helm-values/istio-values.yaml \
  --wait

# Aplicar configurações customizadas
kubectl apply -f helm-charts/istio-base/templates/

# Verificar
kubectl get pods -n istio-system
kubectl get peerauthentication -A
```

#### Passo 6: Deploy OPA Gatekeeper
```bash
# Adicionar repo Helm
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update

# Instalar Gatekeeper
helm upgrade --install gatekeeper gatekeeper/gatekeeper \
  --namespace gatekeeper-system \
  --create-namespace \
  --values helm-charts/opa-gatekeeper/values.yaml \
  --wait

# Aguardar Gatekeeper estar pronto
kubectl -n gatekeeper-system wait --for=condition=ready pod -l gatekeeper.sh/operation=webhook --timeout=180s

# Aplicar constraint templates
kubectl apply -f policies/constraint-templates/

# Aguardar processamento
sleep 15

# Aplicar constraints
kubectl apply -f policies/constraints/

# Verificar
kubectl get pods -n gatekeeper-system
kubectl get constrainttemplates
kubectl get constraints -A
```

## ✅ Validação

### Checklist de Validação

```bash
# 1. ✅ Cluster Health
./scripts/validation/validate-cluster-health.sh

# 2. ✅ mTLS Connectivity
./scripts/validation/test-mtls-connectivity.sh

# 3. ✅ Autoscaler
./scripts/validation/test-autoscaler.sh

# 4. ✅ Manual Verification
kubectl get nodes
kubectl get namespaces | grep neural-hive
kubectl get pods -A | grep -E "(istio|gatekeeper)"
kubectl get peerauthentication -A
kubectl get constraints -A
```

### Métricas de Sucesso
- ✅ Todos os nodes em estado Ready
- ✅ Todos os pods de sistema Running
- ✅ Namespaces Neural Hive criados
- ✅ mTLS STRICT ativo
- ✅ Políticas OPA aplicadas
- ✅ Zero violações críticas

## 🚨 Troubleshooting

### Problemas Comuns

#### 1. Terraform Errors

**Error**: `NoCredentialsError`
```bash
# Verificar credenciais AWS
aws sts get-caller-identity

# Reconfigurar se necessário
aws configure
```

**Error**: `AccessDenied` para S3/KMS
```bash
# Verificar permissões IAM
aws iam simulate-principal-policy \
  --policy-source-arn $(aws sts get-caller-identity --query Arn --output text) \
  --action-names s3:GetObject,s3:PutObject,kms:Decrypt,kms:Encrypt
```

**Error**: `QuotaExceeded`
```bash
# Verificar quotas de serviço
aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A
aws service-quotas get-service-quota --service-code eks --quota-code L-1194D53C
```

#### 2. Kubernetes Issues

**Pods Stuck in Pending**
```bash
# Verificar resources
kubectl describe pod <pod-name> -n <namespace>

# Verificar node capacity
kubectl describe nodes

# Verificar políticas OPA
kubectl get constraints -A
kubectl describe constraint <constraint-name>
```

**Network Issues**
```bash
# Verificar network policies
kubectl get networkpolicies -A

# Debug DNS
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup kubernetes.default

# Verificar service mesh
kubectl get peerauthentication -A
istioctl proxy-status
```

#### 3. Istio Issues

**mTLS Not Working**
```bash
# Verificar peer authentication
kubectl get peerauthentication -A

# Debug mTLS
istioctl authn tls-check <pod>.<namespace> <service>.<namespace>

# Verificar certificados
istioctl proxy-config secret <pod>.<namespace>
```

**Proxy Not Injected**
```bash
# Verificar namespace labels
kubectl get namespace <namespace> --show-labels

# Verificar injection
kubectl get pods -n <namespace> -o jsonpath='{.items[*].spec.containers[*].name}'

# Manual injection
kubectl label namespace <namespace> istio-injection=enabled
```

#### 4. OPA Gatekeeper Issues

**Policies Not Enforcing**
```bash
# Verificar constraint templates
kubectl get constrainttemplates

# Verificar constraints
kubectl get constraints -A

# Debug violations
kubectl get constraints -A -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.status.totalViolations}{"\n"}{end}'

# Logs do Gatekeeper
kubectl logs -n gatekeeper-system deployment/gatekeeper-controller-manager
```

### Logs Úteis

```bash
# Cluster autoscaler
kubectl logs -n kube-system deployment/cluster-autoscaler

# AWS Load Balancer Controller
kubectl logs -n kube-system deployment/aws-load-balancer-controller

# Istio control plane
kubectl logs -n istio-system deployment/istiod

# OPA Gatekeeper
kubectl logs -n gatekeeper-system deployment/gatekeeper-controller-manager
```

## 🔄 Rollback

### Rollback Completo

```bash
# 1. Rollback Helm releases
helm rollback gatekeeper -n gatekeeper-system
helm rollback istiod -n istio-system
helm rollback istio-base -n istio-system

# 2. Remove bootstrap manifests
kubectl delete -f k8s/bootstrap/

# 3. Destroy Terraform (CUIDADO!)
cd infrastructure/terraform/modules/container-registry
terraform destroy

cd ../k8s-cluster
terraform destroy

cd ../network
terraform destroy
```

### Rollback Parcial

```bash
# Apenas service mesh
helm rollback istiod -n istio-system

# Apenas policies
kubectl delete -f policies/constraints/
kubectl delete -f policies/constraint-templates/
helm rollback gatekeeper -n gatekeeper-system

# Apenas network policies
kubectl delete -f k8s/bootstrap/network-policies.yaml
```

### Backup e Restore

```bash
# Backup cluster state
kubectl get all --all-namespaces -o yaml > cluster-backup.yaml

# Backup Terraform state
aws s3 cp s3://neural-hive-terraform-state-${ENV}/ ./terraform-backup/ --recursive

# Restore (se necessário)
kubectl apply -f cluster-backup.yaml
aws s3 cp ./terraform-backup/ s3://neural-hive-terraform-state-${ENV}/ --recursive
```

## 📊 Monitoramento Pós-Deploy

### Comandos de Monitoramento

```bash
# Health geral
watch "kubectl get nodes; echo; kubectl get pods -A | grep -v Running"

# Recursos por namespace
kubectl top nodes
kubectl top pods -A

# Eventos recentes
kubectl get events --sort-by='.lastTimestamp' -A

# Status do service mesh
istioctl proxy-status
istioctl analyze

# Violações de políticas
kubectl get constraints -A -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.status.totalViolations}{"\n"}{end}'
```

### Dashboards Recomendados

- **Kubernetes Dashboard**: `kubectl proxy` → http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/
- **Kiali**: `istioctl dashboard kiali`
- **Grafana**: Via Istio add-ons
- **AWS Console**: EKS cluster overview

---

## 10. Validação Completa da Fase 1

### 10.1 Pré-requisitos
- Todos os componentes da Fase 1 deployados:
  - ✅ Camadas de Memória (Redis, MongoDB, Neo4j, ClickHouse)
  - ✅ Gateway de Intenções
  - ✅ Semantic Translation Engine
  - ✅ 5 Especialistas Neurais
  - ✅ Consensus Engine
  - ✅ Memory Layer API
  - ✅ Explainability API (opcional)
- Kafka operacional com todos os tópicos
- Observabilidade stack completo (Prometheus, Grafana, Jaeger)

### 10.2 Executar Teste End-to-End
```bash
cd /home/jimy/Base/Neural-Hive-Mind

# Executar teste completo
./tests/phase1-end-to-end-test.sh
```

### 10.3 Validações Executadas pelo Teste

**Infraestrutura:**
- 4 camadas de memória operacionais
- 8+ serviços da Fase 1 deployados
- Kafka, Redis, MongoDB, Neo4j, ClickHouse saudáveis

**Fluxo Completo:**
1. Intent Envelope publicado no Kafka (`intentions.business`)
2. Cognitive Plan gerado pelo Semantic Translation Engine
3. 5 Specialist Opinions gerados (Business, Technical, Behavior, Evolution, Architecture)
4. Consolidated Decision gerada pelo Consensus Engine
5. Publicação no Kafka (`plans.consensus`)

**Persistência:**
- Plano registrado no ledger cognitivo (MongoDB)
- Pareceres registrados no ledger de opiniões (MongoDB)
- Decisão registrada no ledger de consenso (MongoDB)
- Feromônios publicados no Redis
- Explicações registradas no ledger de explicabilidade (MongoDB)

**Telemetria:**
- Métricas Prometheus disponíveis (geracao, evaluations, consensus, pheromones)
- Traces Jaeger correlacionados (intent_id → plan_id → decision_id)
- Logs estruturados em JSON

**Governança:**
- Explicabilidade 100% (tokens gerados)
- Integridade do ledger (hash SHA-256)
- Compliance verificado (OPA Gatekeeper)
- Dashboards Grafana acessíveis
- Alertas Prometheus configurados

### 10.4 Critérios de Aceitação da Fase 1

**Funcionais:**
- ✅ Intent Envelope → Cognitive Plan (< 400ms)
- ✅ Cognitive Plan → 5 Specialist Opinions (< 5s)
- ✅ 5 Opinions → Consolidated Decision (< 120ms)
- ✅ Divergência entre especialistas < 5%
- ✅ Confiança agregada ≥ 0.8
- ✅ Explicabilidade 100%
- ✅ Auditabilidade 100%

**Não-Funcionais:**
- ✅ Disponibilidade > 99.9%
- ✅ Latência P95 < 500ms (fluxo completo)
- ✅ Taxa de erro < 1%
- ✅ Cobertura de telemetria > 99.7%
- ✅ Compliance 100% em controles críticos

**Governança:**
- ✅ Trilhas de auditoria completas
- ✅ Políticas OPA enforçadas
- ✅ Feromônios operacionais
- ✅ Risk scoring multi-domínio
- ✅ Dashboards executivos

### 10.5 Troubleshooting

Se o teste falhar, verificar:

1. **Infraestrutura:**
   ```bash
   ./scripts/validation/validate-cluster-health.sh
   ./scripts/validation/validate-memory-layer.sh
   ```

2. **Serviços:**
   ```bash
   ./scripts/validation/validate-gateway-integration.sh
   ./scripts/validation/validate-semantic-translation-engine.sh
   ./scripts/validation/validate-specialists.sh
   ./scripts/validation/validate-consensus-engine.sh
   ```

3. **Logs:**
   ```bash
   # Verificar logs de cada componente
   kubectl logs -n <namespace> <pod-name> --tail=100
   ```

4. **Métricas:**
   ```bash
   # Verificar métricas Prometheus
   kubectl port-forward -n neural-hive-observability svc/prometheus 9090:9090
   curl http://localhost:9090/api/v1/query?query=up
   ```

### 10.6 Próximos Passos Após Validação

Com a Fase 1 validada e concluída:

1. **Documentar Lições Aprendidas**
2. **Preparar Ambiente de Produção**
3. **Iniciar Fase 2: Orquestração e Coordenação de Swarm**
   - Implementar Orquestrador Dinâmico (Temporal/Cadence)
   - Implementar Queen Agent Coordinator
   - Integrar 87 ferramentas MCP
   - Implementar SLA Management System

### 10.7 Referências
- [Teste End-to-End](tests/phase1-end-to-end-test.sh)
- [Operações de Governança](docs/operations/governance-operations.md)
- [Pheromone Communication Protocol](docs/protocols/pheromone-communication-protocol.md)
- [Documento 06 - Fluxos Operacionais](documento-06-fluxos-processos-neural-hive-mind.md)

---

🤖 **Neural Hive-Mind Deployment Guide**
*Guia completo para implementação da base infraestrutural*