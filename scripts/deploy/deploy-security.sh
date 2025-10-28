#!/bin/bash
# Script dedicado para deployment da camada de segurança e governança Zero Trust
# Implementa Istio mTLS, OPA Gatekeeper e Sigstore Policy Controller

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform"
HELM_DIR="${PROJECT_ROOT}/helm-charts"
K8S_DIR="${PROJECT_ROOT}/k8s"
POLICIES_DIR="${PROJECT_ROOT}/policies"
VALIDATION_DIR="${PROJECT_ROOT}/scripts/validation"

# Variáveis de ambiente
ENV="${ENV:-dev}"
REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-neural-hive-${ENV}}"

# Funções auxiliares
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar pré-requisitos
check_prerequisites() {
    log_info "Verificando pré-requisitos para deployment de segurança..."

    # Verificar se infraestrutura Terraform existe
    if [[ ! -d "$TERRAFORM_DIR" ]]; then
        log_error "Diretório Terraform não encontrado: $TERRAFORM_DIR"
        exit 1
    fi

    cd "$TERRAFORM_DIR"

    # Verificar se Terraform foi inicializado
    if [[ ! -d ".terraform" ]]; then
        log_error "Terraform não foi inicializado. Execute: terraform init"
        exit 1
    fi

    # Verificar se infraestrutura foi deployada
    if ! terraform show -json &>/dev/null; then
        log_error "Infraestrutura Terraform não foi deployada. Execute: scripts/deploy/deploy-foundation.sh primeiro"
        exit 1
    fi

    # Verificar kubectl conectividade
    if ! kubectl cluster-info &>/dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        log_error "Execute: aws eks update-kubeconfig --name ${CLUSTER_NAME} --region ${REGION}"
        exit 1
    fi

    # Verificar Helm
    if ! command -v helm &> /dev/null; then
        log_error "Helm não encontrado. Instale em: https://helm.sh/docs/intro/install/"
        exit 1
    fi

    log_success "Pré-requisitos verificados"
}

# Extrair outputs do Terraform
extract_terraform_outputs() {
    log_info "Extraindo outputs necessários do Terraform..."

    cd "${TERRAFORM_DIR}"

    # Obter outputs necessários
    export SIGSTORE_IRSA_ROLE_ARN=$(terraform output -raw sigstore_irsa_role_arn 2>/dev/null || echo "")
    export CLUSTER_NAME_OUTPUT=$(terraform output -raw cluster_name 2>/dev/null || echo "${CLUSTER_NAME}")
    export ECR_REGISTRY_URL=$(terraform output -json registry_urls 2>/dev/null | jq -r 'values[0] // ""' | cut -d'/' -f1)
    export CLUSTER_ENDPOINT=$(terraform output -raw cluster_endpoint 2>/dev/null || echo "")
    export OIDC_ISSUER_URL=$(terraform output -raw oidc_issuer_url 2>/dev/null || echo "")

    # Validar outputs críticos
    if [[ -z "$SIGSTORE_IRSA_ROLE_ARN" ]]; then
        log_warning "SIGSTORE_IRSA_ROLE_ARN não encontrado"
        log_warning "Sigstore Policy Controller será instalado sem IRSA"
    else
        log_info "✓ IRSA Role ARN: ${SIGSTORE_IRSA_ROLE_ARN}"
    fi

    if [[ -z "$ECR_REGISTRY_URL" ]]; then
        log_warning "ECR Registry URL não encontrado"
    else
        log_info "✓ ECR Registry: ${ECR_REGISTRY_URL}"
    fi

    if [[ -z "$CLUSTER_ENDPOINT" ]]; then
        log_warning "Cluster endpoint não encontrado"
    else
        log_info "✓ Cluster endpoint: ${CLUSTER_ENDPOINT}"
    fi

    log_success "Outputs do Terraform extraídos"
}

# Deploy Istio service mesh com configuração de segurança
deploy_istio_security() {
    log_info "Deployando Istio service mesh com configuração de segurança..."

    # Verificar se Istio já está instalado
    if helm list -n istio-system | grep -q istio-base; then
        log_info "Istio já está instalado, atualizando configuração..."
    else
        log_info "Instalando Istio base..."
    fi

    # Verificar se arquivo de valores específico do ambiente existe
    ISTIO_VALUES_FILE="${PROJECT_ROOT}/environments/${ENV}/helm-values/istio-values.yaml"
    if [[ ! -f "$ISTIO_VALUES_FILE" ]]; then
        log_warning "Arquivo de valores Istio não encontrado: $ISTIO_VALUES_FILE"
        log_info "Usando valores padrão do chart"
        VALUES_ARGS=""
    else
        log_info "Usando valores específicos do ambiente: $ISTIO_VALUES_FILE"
        VALUES_ARGS="--values $ISTIO_VALUES_FILE"
    fi

    # Deploy Istio
    helm upgrade --install istio-base "${HELM_DIR}/istio-base" \
        --namespace istio-system \
        --create-namespace \
        $VALUES_ARGS \
        --wait \
        --timeout=10m

    if [[ $? -ne 0 ]]; then
        log_error "Falha ao instalar Istio"
        exit 1
    fi

    # Aguardar Istio ficar pronto
    log_info "Aguardando Istio control plane ficar pronto..."
    kubectl -n istio-system wait --for=condition=ready pod -l app=istiod --timeout=300s
    if [[ $? -ne 0 ]]; then
        log_error "Timeout aguardando Istio ficar pronto"
        exit 1
    fi

    log_success "Istio service mesh deployado com sucesso"
}

# Deploy OPA Gatekeeper com configuração de transição warn→enforce
deploy_opa_gatekeeper_security() {
    log_info "Deployando OPA Gatekeeper com configuração de segurança..."

    # Verificar se OPA já está instalado
    if helm list -n gatekeeper-system | grep -q opa-gatekeeper; then
        log_info "OPA Gatekeeper já está instalado, atualizando configuração..."
    else
        log_info "Instalando OPA Gatekeeper..."
    fi

    # Verificar se arquivo de valores específico do ambiente existe
    OPA_VALUES_FILE="${PROJECT_ROOT}/environments/${ENV}/helm-values/opa-gatekeeper-values.yaml"
    if [[ ! -f "$OPA_VALUES_FILE" ]]; then
        log_warning "Arquivo de valores OPA não encontrado: $OPA_VALUES_FILE"
        log_info "Usando valores padrão do chart"
        VALUES_ARGS=""
    else
        log_info "Usando valores específicos do ambiente: $OPA_VALUES_FILE"
        VALUES_ARGS="--values $OPA_VALUES_FILE"
    fi

    # Deploy OPA Gatekeeper
    helm upgrade --install opa-gatekeeper "${HELM_DIR}/opa-gatekeeper" \
        --namespace gatekeeper-system \
        --create-namespace \
        $VALUES_ARGS \
        --wait \
        --timeout=10m

    if [[ $? -ne 0 ]]; then
        log_error "Falha ao instalar OPA Gatekeeper"
        exit 1
    fi

    # Aguardar Gatekeeper ficar pronto
    log_info "Aguardando OPA Gatekeeper ficar pronto..."
    kubectl -n gatekeeper-system wait --for=condition=ready pod -l gatekeeper.sh/operation=webhook --timeout=300s
    if [[ $? -ne 0 ]]; then
        log_error "Timeout aguardando OPA Gatekeeper ficar pronto"
        exit 1
    fi

    log_success "OPA Gatekeeper deployado com sucesso"
}

# Deploy Sigstore Policy Controller com IRSA configurado
deploy_sigstore_policy_controller_security() {
    log_info "Deployando Sigstore Policy Controller com configuração IRSA..."

    # Verificar se Sigstore já está instalado
    if helm list -n cosign-system | grep -q sigstore-policy-controller; then
        log_info "Sigstore Policy Controller já está instalado, atualizando configuração..."
    else
        log_info "Instalando Sigstore Policy Controller..."
    fi

    # Verificar se arquivo de valores específico do ambiente existe
    SIGSTORE_VALUES_FILE="${PROJECT_ROOT}/environments/${ENV}/helm-values/sigstore-values.yaml"
    if [[ ! -f "$SIGSTORE_VALUES_FILE" ]]; then
        log_warning "Arquivo de valores Sigstore não encontrado: $SIGSTORE_VALUES_FILE"
        log_info "Usando valores padrão do chart"
        VALUES_ARGS=""
    else
        log_info "Usando valores específicos do ambiente: $SIGSTORE_VALUES_FILE"

        # Criar arquivo temporário com substituições de placeholders
        TEMP_VALUES_FILE="/tmp/sigstore-values-${ENV}-$(date +%s).yaml"
        cp "$SIGSTORE_VALUES_FILE" "$TEMP_VALUES_FILE"

        # Substituir placeholders com valores reais
        if [[ -n "$SIGSTORE_IRSA_ROLE_ARN" ]]; then
            sed -i "s|SIGSTORE_IRSA_ROLE_ARN_PLACEHOLDER|${SIGSTORE_IRSA_ROLE_ARN}|g" "$TEMP_VALUES_FILE"
            log_info "✓ IRSA Role ARN configurado: ${SIGSTORE_IRSA_ROLE_ARN}"
        else
            # Remover annotation IRSA se não estiver disponível
            sed -i '/eks.amazonaws.com\/role-arn/d' "$TEMP_VALUES_FILE"
            log_warning "IRSA não configurado - Sigstore funcionará sem permissões AWS"
        fi

        if [[ -n "$CLUSTER_NAME_OUTPUT" ]]; then
            sed -i "s|CLUSTER_NAME_PLACEHOLDER|${CLUSTER_NAME_OUTPUT}|g" "$TEMP_VALUES_FILE"
        fi

        if [[ -n "$ECR_REGISTRY_URL" ]]; then
            sed -i "s|ECR_REGISTRY_URL_PLACEHOLDER|${ECR_REGISTRY_URL}|g" "$TEMP_VALUES_FILE"
        fi

        VALUES_ARGS="--values $TEMP_VALUES_FILE"
    fi

    # Instalar cert-manager se necessário (para TLS dos webhooks)
    if ! kubectl get namespace cert-manager &>/dev/null; then
        log_info "Instalando cert-manager para gerenciar certificados TLS..."
        "${SCRIPT_DIR}/../security/setup-cert-manager.sh"
    fi

    # Deploy Sigstore Policy Controller
    helm upgrade --install sigstore-policy-controller "${HELM_DIR}/sigstore-policy-controller" \
        --namespace cosign-system \
        --create-namespace \
        $VALUES_ARGS \
        --wait \
        --timeout=10m

    if [[ $? -ne 0 ]]; then
        log_error "Falha ao instalar Sigstore Policy Controller"
        [[ -f "$TEMP_VALUES_FILE" ]] && rm -f "$TEMP_VALUES_FILE"
        exit 1
    fi

    # Limpar arquivo temporário
    [[ -f "$TEMP_VALUES_FILE" ]] && rm -f "$TEMP_VALUES_FILE"

    # Aguardar Policy Controller ficar pronto
    log_info "Aguardando Sigstore Policy Controller ficar pronto..."
    kubectl -n cosign-system wait --for=condition=available deployment/sigstore-policy-controller --timeout=300s
    if [[ $? -ne 0 ]]; then
        log_error "Timeout aguardando Sigstore Policy Controller ficar pronto"
        exit 1
    fi

    log_success "Sigstore Policy Controller deployado com sucesso"
}

# Aplicar bootstrap manifests de segurança
apply_security_bootstrap_manifests() {
    log_info "Aplicando bootstrap manifests de segurança..."

    # Aplicar network policies
    log_info "Aplicando network policies deny-by-default..."
    kubectl apply -f "${K8S_DIR}/bootstrap/network-policies.yaml"
    if [[ $? -ne 0 ]]; then
        log_error "Falha ao aplicar network policies"
        exit 1
    fi

    # Aplicar Istio auth policies
    log_info "Aplicando Istio authorization policies..."
    kubectl apply -f "${K8S_DIR}/bootstrap/istio-auth-policies.yaml"
    if [[ $? -ne 0 ]]; then
        log_error "Falha ao aplicar Istio auth policies"
        exit 1
    fi

    # Aplicar outros manifests se existirem
    if [[ -f "${K8S_DIR}/bootstrap/security-policies.yaml" ]]; then
        log_info "Aplicando políticas de segurança adicionais..."
        kubectl apply -f "${K8S_DIR}/bootstrap/security-policies.yaml"
    fi

    log_success "Bootstrap manifests de segurança aplicados"
}

# Aplicar políticas OPA com transição warn→enforce
apply_opa_security_policies() {
    log_info "Aplicando políticas OPA de segurança..."

    # Aplicar constraint templates primeiro
    log_info "Aplicando constraint templates..."
    kubectl apply -f "${POLICIES_DIR}/constraint-templates/"
    if [[ $? -ne 0 ]]; then
        log_error "Falha ao aplicar constraint templates"
        exit 1
    fi

    # Aguardar templates serem processados
    log_info "Aguardando constraint templates serem processados..."
    sleep 30

    # Verificar se templates foram aceitos
    log_info "Verificando status dos constraint templates..."
    kubectl get constrainttemplates -o custom-columns=NAME:.metadata.name,STATUS:.status.created

    # Aplicar constraints com substituição de placeholders
    log_info "Aplicando constraints com configurações específicas do ambiente..."
    for constraint_file in "${POLICIES_DIR}/constraints"/*.yaml; do
        if [[ -f "$constraint_file" ]]; then
            log_info "Processando: $(basename "$constraint_file")"

            # Criar arquivo temporário com substituições
            TEMP_CONSTRAINT_FILE="/tmp/$(basename "$constraint_file")-${ENV}-$(date +%s).yaml"
            cp "$constraint_file" "$TEMP_CONSTRAINT_FILE"

            # Substituir placeholders se necessário
            if [[ -n "$ECR_REGISTRY_URL" ]]; then
                sed -i "s|ECR_REGISTRY_URL_PLACEHOLDER|${ECR_REGISTRY_URL}|g" "$TEMP_CONSTRAINT_FILE"
            fi

            # Aplicar constraint
            kubectl apply -f "$TEMP_CONSTRAINT_FILE"
            if [[ $? -ne 0 ]]; then
                log_error "Falha ao aplicar constraint: $(basename "$constraint_file")"
                rm -f "$TEMP_CONSTRAINT_FILE"
                exit 1
            fi

            rm -f "$TEMP_CONSTRAINT_FILE"
        fi
    done

    log_success "Políticas OPA de segurança aplicadas"
}

# Executar validação completa de segurança
execute_security_validation() {
    log_info "Executando validação completa da camada de segurança..."

    # Validar saúde básica do cluster
    if [[ -f "${VALIDATION_DIR}/validate-cluster-health.sh" ]]; then
        log_info "Validando saúde do cluster..."
        "${VALIDATION_DIR}/validate-cluster-health.sh"
    fi

    # Validar conectividade mTLS
    if [[ -f "${VALIDATION_DIR}/test-mtls-connectivity.sh" ]]; then
        log_info "Testando conectividade mTLS..."
        "${VALIDATION_DIR}/test-mtls-connectivity.sh"
    fi

    # Validar enforcement de políticas
    if [[ -f "${VALIDATION_DIR}/validate-policy-enforcement.sh" ]]; then
        log_info "Validando enforcement de políticas..."
        "${VALIDATION_DIR}/validate-policy-enforcement.sh"
    fi

    # Validar verificação de assinatura de imagens
    if [[ -f "${VALIDATION_DIR}/test-sigstore-verification.sh" ]]; then
        log_info "Testando verificação de assinatura de imagens..."
        "${VALIDATION_DIR}/test-sigstore-verification.sh"
    fi

    log_success "Validação de segurança concluída"
}

# Função de rollback
rollback_security_deployment() {
    log_error "Erro detectado. Iniciando rollback da camada de segurança..."

    # Reverter Helm releases
    log_info "Revertendo Helm releases..."
    helm rollback sigstore-policy-controller -n cosign-system || true
    helm rollback opa-gatekeeper -n gatekeeper-system || true
    helm rollback istio-base -n istio-system || true

    # Remover políticas OPA
    log_info "Removendo policies OPA..."
    kubectl delete -f "${POLICIES_DIR}/constraints/" --ignore-not-found=true || true
    kubectl delete -f "${POLICIES_DIR}/constraint-templates/" --ignore-not-found=true || true

    # Remover bootstrap manifests
    log_info "Removendo bootstrap manifests..."
    kubectl delete -f "${K8S_DIR}/bootstrap/" --ignore-not-found=true || true

    log_warning "Rollback concluído. Verifique o estado do cluster manualmente."
}

# Trap para rollback em caso de erro
trap rollback_security_deployment ERR

# Main
main() {
    log_info "==================================="
    log_info "Neural Hive-Mind - Security Layer Deployment"
    log_info "==================================="
    log_info "Ambiente: ${ENV}"
    log_info "Região: ${REGION}"
    log_info "Cluster: ${CLUSTER_NAME}"
    log_info ""

    # Confirmar com usuário se não estiver em modo forçado
    if [[ "${FORCE:-false}" != "true" ]]; then
        read -p "Deseja continuar com o deployment da camada de segurança? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warning "Deployment cancelado"
            exit 0
        fi
    fi

    # Executar deployment sequencial
    log_info "Iniciando deployment sequencial da camada de segurança Zero Trust..."

    # 1. Verificar pré-requisitos
    check_prerequisites

    # 2. Extrair outputs do Terraform
    extract_terraform_outputs

    # 3. Deploy Istio com configuração mTLS rigorosa
    deploy_istio_security

    # 4. Deploy OPA Gatekeeper com transição warn→enforce
    deploy_opa_gatekeeper_security

    # 5. Deploy Sigstore Policy Controller com IRSA
    deploy_sigstore_policy_controller_security

    # 6. Aplicar bootstrap manifests de segurança
    apply_security_bootstrap_manifests

    # 7. Aplicar políticas OPA
    apply_opa_security_policies

    # 8. Executar validação completa
    execute_security_validation

    # Remover trap para evitar rollback em sucesso
    trap - ERR

    log_success "==================================="
    log_success "Camada de segurança Zero Trust deployada com sucesso!"
    log_info ""
    log_info "Componentes instalados:"
    log_info "  ✓ Istio Service Mesh com mTLS STRICT"
    log_info "  ✓ OPA Gatekeeper (modo warn → enforce)"
    log_info "  ✓ Sigstore Policy Controller com IRSA"
    log_info "  ✓ Network Policies deny-by-default"
    log_info "  ✓ Istio Authorization Policies"
    log_info ""
    log_info "Próximos passos:"
    log_info "1. Monitore violações: kubectl get constraints -A"
    log_info "2. Verifique mTLS: kubectl get peerauthentication -A"
    log_info "3. Para transição automática warn→enforce: scripts/security/transition-policies-to-enforce.sh"
    log_info "4. Dashboard Istio: istioctl dashboard kiali"
    log_success "==================================="
}

# Executar
main "$@"