#!/bin/bash
# Script Completo para Deploy do Neural Hive-Mind no Amazon EKS
# Este script automatiza todo o processo de deployment na AWS
# Version: 1.0.0

set -euo pipefail

# ============================================================================
# CONFIGURAÇÃO E VARIÁVEIS
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de log
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ============================================================================
# VERIFICAÇÃO DE PRÉ-REQUISITOS
# ============================================================================

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    local missing_tools=()

    # Verificar ferramentas
    for tool in aws terraform kubectl helm docker jq; do
        if ! command -v $tool &> /dev/null; then
            missing_tools+=($tool)
        fi
    done

    if [ ${#missing_tools[@]} -gt 0 ]; then
        log_error "Ferramentas ausentes: ${missing_tools[*]}"
        log_error "Instale as ferramentas necessárias antes de continuar."
        log_error "Consulte: DEPLOYMENT_EKS_GUIDE.md"
        exit 1
    fi

    # Verificar versões
    log_info "Versões instaladas:"
    log_info "  - AWS CLI: $(aws --version 2>&1 | head -n1)"
    log_info "  - Terraform: $(terraform version | head -n1)"
    log_info "  - kubectl: $(kubectl version --client --short 2>&1)"
    log_info "  - Helm: $(helm version --short)"
    log_info "  - Docker: $(docker --version)"

    # Verificar credenciais AWS
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "Credenciais AWS não configuradas ou inválidas"
        log_error "Execute: aws configure"
        exit 1
    fi

    log_success "Pré-requisitos atendidos"
}

# ============================================================================
# CONFIGURAÇÃO DO AMBIENTE
# ============================================================================

setup_environment() {
    log_info "Configurando ambiente..."

    # Verificar variáveis obrigatórias
    if [ -z "${ENV:-}" ]; then
        log_error "Variável ENV não definida"
        log_error "Exporte: export ENV=dev|staging|prod"
        exit 1
    fi

    export AWS_REGION="${AWS_REGION:-us-east-1}"
    export CLUSTER_NAME="${CLUSTER_NAME:-neural-hive-${ENV}}"
    export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

    log_info "Configuração do ambiente:"
    log_info "  - Ambiente: ${ENV}"
    log_info "  - Região: ${AWS_REGION}"
    log_info "  - Cluster: ${CLUSTER_NAME}"
    log_info "  - AWS Account: ${AWS_ACCOUNT_ID}"
    log_info "  - ECR Registry: ${ECR_REGISTRY}"

    # Verificar senhas
    check_passwords

    log_success "Ambiente configurado"
}

check_passwords() {
    local missing_passwords=()

    [ -z "${TF_VAR_mongodb_root_password:-}" ] && missing_passwords+=("TF_VAR_mongodb_root_password")
    [ -z "${TF_VAR_neo4j_password:-}" ] && missing_passwords+=("TF_VAR_neo4j_password")
    [ -z "${TF_VAR_clickhouse_admin_password:-}" ] && missing_passwords+=("TF_VAR_clickhouse_admin_password")
    [ -z "${TF_VAR_clickhouse_readonly_password:-}" ] && missing_passwords+=("TF_VAR_clickhouse_readonly_password")
    [ -z "${TF_VAR_clickhouse_writer_password:-}" ] && missing_passwords+=("TF_VAR_clickhouse_writer_password")

    if [ ${#missing_passwords[@]} -gt 0 ]; then
        log_error "Senhas não configuradas: ${missing_passwords[*]}"
        log_error "Defina as senhas como variáveis de ambiente:"
        for pwd in "${missing_passwords[@]}"; do
            log_error "  export ${pwd}=\"<senha-forte>\""
        done
        exit 1
    fi
}

# ============================================================================
# SETUP DO BACKEND S3
# ============================================================================

setup_s3_backend() {
    log_info "Configurando backend S3 para Terraform state..."

    local bucket_name="terraform-state-neural-hive-${ENV}"
    local table_name="terraform-locks-neural-hive-${ENV}"

    # Criar bucket se não existir
    if ! aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        log_info "Criando bucket S3: ${bucket_name}"
        # us-east-1 não precisa de LocationConstraint
        if [ "${AWS_REGION}" == "us-east-1" ]; then
            aws s3api create-bucket \
                --bucket "$bucket_name" \
                --region "${AWS_REGION}"
        else
            aws s3api create-bucket \
                --bucket "$bucket_name" \
                --region "${AWS_REGION}" \
                --create-bucket-configuration LocationConstraint=${AWS_REGION}
        fi

        # Habilitar versionamento
        aws s3api put-bucket-versioning \
            --bucket "$bucket_name" \
            --versioning-configuration Status=Enabled

        # Habilitar criptografia
        aws s3api put-bucket-encryption \
            --bucket "$bucket_name" \
            --server-side-encryption-configuration '{
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }]
            }'

        log_success "Bucket S3 criado: ${bucket_name}"
    else
        log_info "Bucket S3 já existe: ${bucket_name}"
    fi

    # Criar DynamoDB table se não existir
    if ! aws dynamodb describe-table --table-name "$table_name" --region "${AWS_REGION}" 2>/dev/null; then
        log_info "Criando DynamoDB table: ${table_name}"
        aws dynamodb create-table \
            --table-name "$table_name" \
            --attribute-definitions AttributeName=LockID,AttributeType=S \
            --key-schema AttributeName=LockID,KeyType=HASH \
            --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
            --region "${AWS_REGION}"

        log_success "DynamoDB table criada: ${table_name}"
    else
        log_info "DynamoDB table já existe: ${table_name}"
    fi

    # Criar arquivo backend.hcl
    local backend_file="${PROJECT_ROOT}/environments/${ENV}/backend.hcl"
    mkdir -p "$(dirname "$backend_file")"

    cat > "$backend_file" <<EOF
bucket         = "${bucket_name}"
key            = "neural-hive-mind/${ENV}/terraform.tfstate"
region         = "${AWS_REGION}"
encrypt        = true
dynamodb_table = "${table_name}"
EOF

    log_success "Backend S3 configurado"
}

# ============================================================================
# DEPLOY DA INFRAESTRUTURA TERRAFORM
# ============================================================================

deploy_terraform() {
    log_info "Deployando infraestrutura com Terraform..."

    cd "${PROJECT_ROOT}/infrastructure/terraform"

    # Inicializar Terraform
    log_info "Inicializando Terraform..."
    if [ -f "${PROJECT_ROOT}/environments/${ENV}/backend.hcl" ]; then
        terraform init -backend-config="${PROJECT_ROOT}/environments/${ENV}/backend.hcl" -reconfigure
    else
        log_warning "Backend S3 não configurado, usando backend local"
        terraform init
    fi

    # Validar
    log_info "Validando configuração..."
    terraform validate

    # Planejar
    log_info "Planejando mudanças..."
    terraform plan \
        -var-file="${PROJECT_ROOT}/environments/${ENV}/terraform.tfvars" \
        -out=tfplan

    # Confirmar com usuário
    if [ "${SKIP_CONFIRM:-false}" != "true" ]; then
        echo ""
        log_warning "ATENÇÃO: Isso criará recursos na AWS que geram custos!"
        log_warning "Revise o plano acima cuidadosamente."
        read -p "Deseja continuar? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            log_info "Deploy cancelado pelo usuário"
            exit 0
        fi
    fi

    # Aplicar
    log_info "Aplicando mudanças (isso pode levar 15-20 minutos)..."
    terraform apply -auto-approve tfplan

    # Configurar kubectl
    log_info "Configurando kubectl..."
    aws eks update-kubeconfig \
        --name "${CLUSTER_NAME}" \
        --region "${AWS_REGION}"

    # Verificar conectividade
    log_info "Verificando conectividade com cluster..."
    kubectl cluster-info
    kubectl get nodes

    log_success "Infraestrutura Terraform deployada com sucesso"
}

# ============================================================================
# CRIAR REPOSITÓRIOS ECR
# ============================================================================

create_ecr_repositories() {
    log_info "Criando repositórios ECR..."

    local components=(
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

    for component in "${components[@]}"; do
        local repo_name="neural-hive-${ENV}/${component}"

        if aws ecr describe-repositories --repository-names "$repo_name" --region "${AWS_REGION}" &>/dev/null; then
            log_info "Repositório já existe: ${component}"
        else
            log_info "Criando repositório: ${component}"
            aws ecr create-repository \
                --repository-name "$repo_name" \
                --region "${AWS_REGION}" \
                --image-scanning-configuration scanOnPush=true \
                --encryption-configuration encryptionType=AES256
        fi
    done

    log_success "Repositórios ECR criados"
}

# ============================================================================
# BUILD E PUSH DE IMAGENS DOCKER
# ============================================================================

build_and_push_images() {
    log_info "Build e push de imagens Docker..."

    cd "${PROJECT_ROOT}"

    # Login no ECR
    log_info "Fazendo login no ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "${ECR_REGISTRY}"

    # Build Gateway de Intenções
    log_info "Building gateway-intencoes..."
    docker build -t "${ECR_REGISTRY}/neural-hive-${ENV}/gateway-intencoes:latest" \
        -f services/gateway-intencoes/Dockerfile .
    docker push "${ECR_REGISTRY}/neural-hive-${ENV}/gateway-intencoes:latest"

    # Build Semantic Translation Engine
    log_info "Building semantic-translation-engine..."
    docker build -t "${ECR_REGISTRY}/neural-hive-${ENV}/semantic-translation-engine:latest" \
        -f services/semantic-translation-engine/Dockerfile .
    docker push "${ECR_REGISTRY}/neural-hive-${ENV}/semantic-translation-engine:latest"

    # Build Specialists
    for spec in business technical behavior evolution architecture; do
        log_info "Building specialist-${spec}..."
        docker build -t "${ECR_REGISTRY}/neural-hive-${ENV}/specialist-${spec}:latest" \
            --build-arg SPECIALIST_TYPE=${spec} \
            -f libraries/python/neural_hive_specialists/Dockerfile .
        docker push "${ECR_REGISTRY}/neural-hive-${ENV}/specialist-${spec}:latest"
    done

    # Build Consensus Engine
    log_info "Building consensus-engine..."
    docker build -t "${ECR_REGISTRY}/neural-hive-${ENV}/consensus-engine:latest" \
        -f services/consensus-engine/Dockerfile .
    docker push "${ECR_REGISTRY}/neural-hive-${ENV}/consensus-engine:latest"

    # Build Memory Layer API
    log_info "Building memory-layer-api..."
    docker build -t "${ECR_REGISTRY}/neural-hive-${ENV}/memory-layer-api:latest" \
        -f services/memory-layer-api/Dockerfile .
    docker push "${ECR_REGISTRY}/neural-hive-${ENV}/memory-layer-api:latest"

    log_success "Imagens Docker buildadas e enviadas para ECR"
}

# ============================================================================
# DEPLOY DOS COMPONENTES KUBERNETES
# ============================================================================

deploy_kubernetes_components() {
    log_info "Deployando componentes Kubernetes..."

    cd "${PROJECT_ROOT}"

    # Deploy Bootstrap Manifests
    log_info "Aplicando bootstrap manifests..."
    kubectl apply -f k8s/bootstrap/namespaces.yaml
    kubectl apply -f k8s/bootstrap/rbac.yaml
    kubectl apply -f k8s/bootstrap/network-policies.yaml

    # Deploy Helm Charts de Segurança
    if [ -d "helm-charts/istio-base" ]; then
        log_info "Deployando Istio..."
        helm upgrade --install istio-base helm-charts/istio-base \
            --namespace istio-system \
            --create-namespace \
            --wait || log_warning "Istio deployment falhou, continuando..."
    fi

    if [ -d "helm-charts/opa-gatekeeper" ]; then
        log_info "Deployando OPA Gatekeeper..."
        helm upgrade --install opa-gatekeeper helm-charts/opa-gatekeeper \
            --namespace gatekeeper-system \
            --create-namespace \
            --wait || log_warning "OPA Gatekeeper deployment falhou, continuando..."
    fi

    # Aguardar Gatekeeper estar pronto
    log_info "Aguardando OPA Gatekeeper ficar pronto..."
    kubectl -n gatekeeper-system wait --for=condition=ready pod \
        -l gatekeeper.sh/operation=webhook --timeout=180s || true

    # Aplicar Políticas OPA
    if [ -d "policies/constraint-templates" ]; then
        log_info "Aplicando constraint templates..."
        kubectl apply -f policies/constraint-templates/ || log_warning "Constraint templates aplicação falhou"
        sleep 10
    fi

    if [ -d "policies/constraints" ]; then
        log_info "Aplicando constraints..."
        kubectl apply -f policies/constraints/ || log_warning "Constraints aplicação falhou"
    fi

    # Deploy Infraestrutura de Dados
    log_info "Deployando infraestrutura de dados..."

    # Kafka
    if [ -f "k8s/kafka-local.yaml" ]; then
        kubectl apply -f k8s/kafka-local.yaml || log_warning "Kafka deployment falhou"
    fi

    # Redis
    if [ -f "k8s/redis-local.yaml" ]; then
        kubectl apply -f k8s/redis-local.yaml || log_warning "Redis deployment falhou"
    fi

    # Deploy Serviços Cognitivos (se deployments existirem)
    log_info "Deployando serviços cognitivos..."

    for service in gateway-intencoes semantic-translation-engine consensus-engine memory-layer-api; do
        if [ -f "k8s/${service}-deployment.yaml" ]; then
            log_info "Deployando ${service}..."
            kubectl apply -f "k8s/${service}-deployment.yaml" || log_warning "${service} deployment falhou"
        fi
    done

    log_success "Componentes Kubernetes deployados"
}

# ============================================================================
# VALIDAÇÃO DO DEPLOYMENT
# ============================================================================

validate_deployment() {
    log_info "Validando deployment..."

    # Verificar nodes
    local node_count=$(kubectl get nodes --no-headers | wc -l)
    log_info "Nodes disponíveis: ${node_count}"

    # Verificar pods
    log_info "Status dos pods:"
    kubectl get pods --all-namespaces | grep -E "neural-hive|gateway|specialist|consensus|memory" || true

    # Verificar pods com problemas
    local problem_pods=$(kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null | wc -l)
    if [ "$problem_pods" -gt 0 ]; then
        log_warning "${problem_pods} pods com problemas detectados"
        kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
    else
        log_success "Todos os pods estão rodando corretamente"
    fi

    # Verificar serviços
    log_info "Serviços deployados:"
    kubectl get svc --all-namespaces | grep -E "neural-hive|gateway|specialist|consensus|memory" || true

    log_success "Validação concluída"
}

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

main() {
    log_info "============================================"
    log_info "Neural Hive-Mind - Deploy Completo no EKS"
    log_info "============================================"

    # Etapa 1: Verificações
    check_prerequisites
    setup_environment

    # Etapa 2: Backend S3
    if [ "${SKIP_S3_BACKEND:-false}" != "true" ]; then
        setup_s3_backend
    else
        log_warning "Pulando configuração do backend S3"
    fi

    # Etapa 3: Deploy Terraform
    if [ "${SKIP_TERRAFORM:-false}" != "true" ]; then
        deploy_terraform
    else
        log_warning "Pulando deploy Terraform"
    fi

    # Etapa 4: ECR Repositories
    if [ "${SKIP_ECR:-false}" != "true" ]; then
        create_ecr_repositories
    else
        log_warning "Pulando criação de repositórios ECR"
    fi

    # Etapa 5: Build e Push de Imagens
    if [ "${SKIP_BUILD:-false}" != "true" ]; then
        build_and_push_images
    else
        log_warning "Pulando build e push de imagens"
    fi

    # Etapa 6: Deploy Kubernetes
    if [ "${SKIP_K8S_DEPLOY:-false}" != "true" ]; then
        deploy_kubernetes_components
    else
        log_warning "Pulando deploy Kubernetes"
    fi

    # Etapa 7: Validação
    validate_deployment

    # Resumo Final
    log_success "============================================"
    log_success "Deploy Concluído com Sucesso!"
    log_success "============================================"
    log_info ""
    log_info "Próximos passos:"
    log_info "1. Verificar status: kubectl get pods --all-namespaces"
    log_info "2. Ver logs: kubectl logs -n <namespace> <pod-name>"
    log_info "3. Port-forward: kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8080:8080"
    log_info "4. Executar testes: ./tests/phase1-end-to-end-test.sh"
    log_info "5. Consultar documentação: DEPLOYMENT_EKS_GUIDE.md"
    log_info ""
    log_info "Para acessar o cluster posteriormente:"
    log_info "  aws eks update-kubeconfig --name ${CLUSTER_NAME} --region ${AWS_REGION}"
    log_info ""
}

# Executar
main "$@"
