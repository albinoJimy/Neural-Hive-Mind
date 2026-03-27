# Quick Start - Deploy no Amazon EKS

Guia rápido para fazer o deploy do Neural Hive-Mind no Amazon EKS em menos de 30 minutos.

## 🚀 Instalação Rápida

### 1. Instalar AWS CLI (se não estiver instalado)

```bash
# Linux/MacOS
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Verificar
aws --version
```

### 2. Configurar Credenciais AWS

```bash
# Configurar AWS CLI
aws configure

# Verificar
aws sts get-caller-identity
```

### 3. Configurar Variáveis de Ambiente

```bash
# Definir ambiente (dev, staging ou prod)
export ENV=dev
export AWS_REGION=us-east-1

# Definir senhas seguras (use senhas fortes!)
export TF_VAR_mongodb_root_password="MongoSecure2024!"
export TF_VAR_neo4j_password="Neo4jSecure2024!"
export TF_VAR_clickhouse_admin_password="ClickHouseAdmin2024!"
export TF_VAR_clickhouse_readonly_password="ClickHouseRead2024!"
export TF_VAR_clickhouse_writer_password="ClickHouseWrite2024!"

# Salvar configuração
cat > ~/.neural-hive-env <<EOF
export ENV=${ENV}
export AWS_REGION=${AWS_REGION}
export TF_VAR_mongodb_root_password="${TF_VAR_mongodb_root_password}"
export TF_VAR_neo4j_password="${TF_VAR_neo4j_password}"
export TF_VAR_clickhouse_admin_password="${TF_VAR_clickhouse_admin_password}"
export TF_VAR_clickhouse_readonly_password="${TF_VAR_clickhouse_readonly_password}"
export TF_VAR_clickhouse_writer_password="${TF_VAR_clickhouse_writer_password}"
EOF

chmod 600 ~/.neural-hive-env
source ~/.neural-hive-env
```

## 🎯 Deploy Automatizado (Recomendado)

### Opção A: Deploy Completo (Uma Linha)

```bash
cd /jimy/Neural-Hive-Mind

# Executar deploy completo (equivalente ao deploy-eks-complete.sh via CLIs)
./scripts/build.sh --target ecr --push --version ${ENV_VERSION:-latest}
./scripts/deploy.sh --env ${ENV:-dev} --phase all --version ${ENV_VERSION:-latest}
```

Este script irá:
- ✅ Verificar pré-requisitos
- ✅ Criar backend S3 para Terraform state
- ✅ Deploy da infraestrutura (VPC, EKS, ECR)
- ✅ Criar repositórios ECR
- ✅ Build e push de todas as imagens Docker
- ✅ Deploy dos componentes Kubernetes
- ✅ Validar o deployment

**Tempo estimado**: 20-30 minutos

### Opção B: Deploy Passo-a-Passo

Se preferir ter mais controle:

```bash
cd /jimy/Neural-Hive-Mind

# 1. Backend S3 + Terraform (manual)
cd infrastructure/terraform
terraform init -backend-config=../../environments/${ENV}/backend.hcl
terraform plan -var-file=../../environments/${ENV}/terraform.tfvars
terraform apply -var-file=../../environments/${ENV}/terraform.tfvars

# 2. Configurar kubectl
aws eks update-kubeconfig --name neural-hive-${ENV} --region ${AWS_REGION}
kubectl get nodes

# 3. Build e Push Imagens (equiv. push-to-ecr.sh)
cd /jimy/Neural-Hive-Mind
./scripts/build.sh --target ecr --push --version ${ENV_VERSION:-latest}

# 4. Deploy Kubernetes (equiv. update-manifests-ecr.sh + deploy)
./scripts/deploy.sh --env ${ENV:-dev} --phase all --version ${ENV_VERSION:-latest}
```

### Opção C: Build Local + Push ECR + Deploy

Esta opção permite fazer build localmente e subir apenas as imagens para ECR, ideal para desenvolvimento iterativo.

#### Workflow Simplificado (Recomendado)

Use o script orquestrador para executar todas as etapas automaticamente:

```bash
cd /jimy/Neural-Hive-Mind

# Fluxo completo: build + push + deploy (equiv. build-and-deploy-eks.sh)
./scripts/build.sh --target ecr --push --version 1.0.8
./scripts/deploy.sh --env eks --phase all --version 1.0.8
```

**Tempo estimado**: 10-15 minutos total.

---

#### Workflow Manual (Controle Total)

Se preferir executar cada etapa manualmente:

> **Nota**: Os passos abaixo podem ser executados automaticamente com `./scripts/build-and-deploy-eks.sh`. Use o workflow manual apenas se precisar de controle granular ou debugging.
> Equivalente via CLIs: `./scripts/build.sh --target ecr --push` + `./scripts/deploy.sh --env eks --phase all`.

#### Pré-requisitos

```bash
# Ferramentas necessárias
docker >= 24.0
aws-cli >= 2.0
yq >= 4.0  # Opcional, mas recomendado

# Credenciais AWS configuradas
aws configure
aws sts get-caller-identity

# Cluster EKS já conectado
aws eks update-kubeconfig --name neural-hive-${ENV} --region ${AWS_REGION}
kubectl get nodes
```

#### Configuração de Ambiente

Crie arquivo `~/.neural-hive-env` com suas configurações:

```bash
cat > ~/.neural-hive-env <<EOF
export ENV="dev"
export AWS_REGION="us-east-1"
# AWS_ACCOUNT_ID será derivado automaticamente
EOF

chmod 600 ~/.neural-hive-env
source ~/.neural-hive-env
```

#### Passo 1: Build Local das Imagens

```bash
cd /jimy/Neural-Hive-Mind

# Build de todos os serviços (9 serviços Phase 1) - equiv. build-local-parallel.sh
./scripts/build.sh --target local --parallel 4 --version 1.0.8

# Build com mais paralelização (8 jobs)
./scripts/build.sh --target local --parallel 8 --version 1.0.8

# Build de serviços específicos
./scripts/build.sh --target local --services "gateway-intencoes,consensus-engine" --version 1.0.8

# Build sem cache (rebuild completo)
./scripts/build.sh --target local --no-cache --version 1.0.8
```

**Tempo estimado**: 5-8 minutos com 4 jobs paralelos.

**Verificar imagens buildadas**:
```bash
docker images | grep neural-hive-mind
```

#### Passo 2: Push para ECR

```bash
# Push de todas as imagens (equiv. push-to-ecr.sh)
./scripts/build.sh --target ecr --push --version 1.0.8

# Push para ambiente staging
./scripts/build.sh --target ecr --push --env staging --region us-west-2 --version 1.0.8

# Push de serviços específicos
./scripts/build.sh --target ecr --push --services "gateway-intencoes,consensus-engine" --version 1.0.8
```

**Tempo estimado**: 5-8 minutos com 4 jobs paralelos.

**O script automaticamente**:
- Faz login no ECR
- Cria repositórios ECR se não existirem (com encryption AES256 e scan on push)
- Valida imagens locais antes do push
- Faz push de ambas as tags (`latest` e versão específica)
- Implementa retry logic para falhas de rede (3 tentativas com backoff exponencial)

**Verificar imagens no ECR**:
```bash
aws ecr list-images --repository-name neural-hive-dev/gateway-intencoes --region us-east-1
```

#### Passo 3: Atualizar Manifestos Kubernetes

```bash
# Preview das mudanças (recomendado)
./scripts/deploy.sh --env eks --phase all --version 1.0.8 --dry-run

# Atualizar e aplicar todos os manifestos
./scripts/deploy.sh --env eks --phase all --version 1.0.8

# Atualizar para ambiente staging
./scripts/deploy.sh --env eks --phase all --version 1.0.8 --env staging --region us-west-2
```

**O script automaticamente**:
- Cria backup timestamped dos manifestos originais em `backups/manifests-YYYYMMDD-HHMMSS/`
- Atualiza `image.repository` e `image.tag` em todos os Helm charts (`/helm-charts/*/values.yaml`)
  - Usa contexto para afetar apenas o bloco `image:` evitando alterar outros campos `repository:` ou `tag:`
- Atualiza imagens hardcoded em manifests standalone (`/k8s/*-deployment.yaml`)
  - Processa todos os arquivos `*-deployment.yaml` no diretório `/k8s`
  - Deriva automaticamente o nome do serviço a partir do nome do arquivo
  - Atualiza apenas serviços na lista de serviços Phase 1
- Exibe resumo de mudanças aplicadas
- **Modo dry-run não requer credenciais AWS** - pode usar valores placeholder para preview

**Verificar mudanças**:
```bash
# Ver diff no Git
git diff helm-charts/gateway-intencoes/values.yaml

# Verificar template Helm
helm template gateway-intencoes helm-charts/gateway-intencoes/ | grep image:
```

#### Passo 4: Deploy no EKS

```bash
# Deploy via CLI unificado (equiv. apply dos charts)
./scripts/deploy.sh --env eks --phase all --version 1.0.8

# Ou deploy de serviço específico
./scripts/deploy.sh --env eks --services gateway-intencoes --version 1.0.8
```

#### Workflow Completo (One-liner)

```bash
# Build + Push + Deploy (equiv. build-and-deploy-eks.sh)
./scripts/build.sh --target ecr --push --version 1.0.8 && \
./scripts/deploy.sh --env eks --phase all --version 1.0.8
```

#### Rollback de Manifestos

Se precisar reverter as mudanças nos manifestos:

```bash
# Listar backups disponíveis
ls -la backups/

# Restaurar backup específico
cp -r backups/manifests-20251114-153000/* .

# Ou usar Git
git checkout helm-charts/*/values.yaml k8s/*.yaml
```

#### Troubleshooting

**Erro: "AWS CLI não encontrado"**
```bash
# Instalar AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

**Erro: "yq não encontrado"**
```bash
# Instalar yq (Linux)
sudo wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/bin/yq
sudo chmod +x /usr/bin/yq

# Instalar yq (macOS)
brew install yq

# Ou o script usará sed como fallback automaticamente
```

**Erro: "Credenciais AWS inválidas"**
```bash
# Configurar AWS CLI
aws configure

# Ou exportar credenciais
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

**Erro: "Imagem local não encontrada"**
```bash
# Verificar se build foi executado
docker images | grep neural-hive-mind

# Re-executar build
./scripts/build.sh --target local --parallel 4
```

#### Comparação de Opções

| Aspecto | Opção A (Deploy Completo) | Opção B (Passo-a-Passo) | **Opção C (Build Local + ECR)** | **Opção D (Orquestrador)** |
|---------|---------------------------|-------------------------|----------------------------------|----------------------------|
| Velocidade | Lenta (build remoto) | Média | **Rápida (paralelo local)** | **Muito Rápida (automatizada)** |
| Controle | Baixo (automatizado) | Alto | **Muito Alto** | **Médio** |
| Recursos | Usa EKS nodes | Usa EKS nodes | **Usa máquina local** | **Usa máquina local** |
| Iteração | Lenta (full rebuild) | Média | **Rápida (sem commit)** | **Muito Rápida** |
| Custo | Alto (EKS compute) | Alto (EKS compute) | **Baixo (apenas ECR storage)** | **Baixo** |
| Ideal para | Produção inicial | Troubleshooting | **Desenvolvimento iterativo** | **Desenvolvimento + Produção** |

**Opção D** combina as vantagens da Opção C com automação completa, ideal para workflows repetitivos.

#### Vantagens desta Abordagem

- ⚡ **Build paralelo local** é mais rápido (usa cache local do Docker)
- 🔄 **Re-build granular** - pode rebuildar apenas serviços específicos
- 🛠️ **Melhor para desenvolvimento** - iteração rápida sem commits
- 📊 **Logs detalhados** - build e push separados para debugging
- 💰 **Mais econômico** - não usa compute do EKS para builds
- 🎯 **Preview seguro** - dry-run dos manifestos antes de aplicar
- 💾 **Backups automáticos** - rollback fácil de manifestos

#### Quando Usar

- ✅ Desenvolvimento ativo com mudanças frequentes
- ✅ Debugging de builds específicos
- ✅ Ambientes com boa conexão de internet para push
- ✅ Quando já tem imagens buildadas localmente
- ✅ Testes de diferentes versões de imagens
- ✅ Deployment incremental de serviços

## ✅ Validação Rápida

```bash
# Verificar nodes
kubectl get nodes

# Verificar pods
kubectl get pods --all-namespaces | grep neural-hive

# Verificar serviços
kubectl get svc --all-namespaces | grep neural-hive

# Port-forward para testar Gateway
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8080:8080

# Em outro terminal:
curl -X POST http://localhost:8080/api/v1/intents \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "intent_text": "Hello", "priority": "high"}'
```

## 🔧 Troubleshooting Rápido

### AWS CLI não instalado

```bash
# Instalar AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### Credenciais AWS inválidas

```bash
# Reconfigurar
aws configure

# Testar
aws sts get-caller-identity
```

### Pods não iniciam

```bash
# Ver detalhes do pod
kubectl describe pod <pod-name> -n <namespace>

# Ver logs
kubectl logs <pod-name> -n <namespace>

# Ver eventos
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

### Erro "image pull"

```bash
# Verificar se imagem existe no ECR
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr describe-images \
  --repository-name neural-hive-${ENV}/gateway-intencoes \
  --region ${AWS_REGION}

# Refazer push
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/neural-hive-${ENV}/gateway-intencoes:latest
```

### Terraform erro de permissão

Verifique se seu usuário IAM tem as seguintes permissões:
- EC2 full access
- EKS full access
- ECR full access
- IAM create roles
- S3 create buckets
- CloudWatch logs

## 💰 Custos Esperados

### Ambiente Dev

- **EKS Control Plane**: ~$72/mês
- **EC2 Nodes (3x t3.medium)**: ~$75/mês
- **NAT Gateway**: ~$100/mês
- **Outros**: ~$20/mês
- **Total**: ~$267/mês

### Como Reduzir Custos

```bash
# 1. Reduzir nodes para mínimo
kubectl scale deployment --all --replicas=1 --all-namespaces

# 2. Usar Spot Instances (70% desconto)
# Editar terraform.tfvars:
# capacity_type = "SPOT"

# 3. Parar cluster quando não estiver usando (dev only)
# Deletar node groups temporariamente
```

## 🧹 Limpeza (Destruir Recursos)

```bash
# ATENÇÃO: Isso irá deletar TODOS os recursos!

# 1. Deletar recursos Kubernetes
kubectl delete all --all --all-namespaces

# 2. Deletar infraestrutura Terraform
cd infrastructure/terraform
terraform destroy -var-file=../../environments/${ENV}/terraform.tfvars

# 3. Deletar backend S3 (opcional)
aws s3 rb s3://terraform-state-neural-hive-${ENV} --force
aws dynamodb delete-table --table-name terraform-locks-neural-hive-${ENV}
```

## 📚 Documentação Completa

Para informações detalhadas, consulte:

- [DEPLOYMENT_EKS_GUIDE.md](DEPLOYMENT_EKS_GUIDE.md) - Guia completo de deployment
- [README.md](README.md) - Documentação do projeto
- [OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) - Operações e troubleshooting

## 🆘 Suporte

Problemas? Consulte:

1. [Troubleshooting](#troubleshooting-rápido) acima
2. [DEPLOYMENT_EKS_GUIDE.md](DEPLOYMENT_EKS_GUIDE.md#troubleshooting) - Seção completa
3. Abrir issue no GitHub

---

🤖 **Neural Hive-Mind - Quick Start EKS**
*Deploy em 30 minutos na AWS*
