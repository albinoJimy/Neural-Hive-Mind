#!/bin/bash

#######################################################################################################
# Script: deploy-opa-gatekeeper-local.sh
# Descrição: Deploy simplificado de OPA Gatekeeper para ambiente local (Minikube/Kind)
# Autor: Neural Hive-Mind Team
# Data: 2025-11-12
# Versão: 1.0.0
#
# Referências:
# - scripts/deploy/deploy-security.sh (linhas 168-211, 322-369)
# - environments/dev/helm-values/opa-gatekeeper-values.yaml
# - helm-charts/opa-gatekeeper/Chart.yaml
#######################################################################################################

set -euo pipefail

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configurações (namespace é parametrizável via --namespace flag)
NAMESPACE="opa-gatekeeper"
readonly HELM_RELEASE_NAME="opa-gatekeeper"
readonly ENVIRONMENT="development"
readonly VALUES_FILE="environments/dev/helm-values/opa-gatekeeper-values.yaml"
readonly TIMEOUT="10m"
readonly WEBHOOK_TIMEOUT="300s"
readonly AUDIT_TIMEOUT="300s"
readonly REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Logging functions
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
    log_info "Verificando pré-requisitos..."

    # kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale o kubectl primeiro."
        exit 1
    fi

    # helm
    if ! command -v helm &> /dev/null; then
        log_error "helm não encontrado. Instale o helm v3.10+ primeiro."
        exit 1
    fi

    # Verificar versão do Helm
    local helm_version
    helm_version=$(helm version --short | grep -oP 'v\d+\.\d+' | sed 's/v//')
    if [[ "$(echo "$helm_version < 3.10" | bc -l)" -eq 1 ]]; then
        log_error "Helm v3.10+ é necessário. Versão atual: v$helm_version"
        exit 1
    fi

    # Verificar conectividade com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes. Verifique o contexto kubectl."
        exit 1
    fi

    # Verificar se values file existe
    if [[ ! -f "$REPO_DIR/$VALUES_FILE" ]]; then
        log_error "Arquivo de values não encontrado: $VALUES_FILE"
        exit 1
    fi

    log_success "Pré-requisitos verificados com sucesso"
}

# Adicionar repositório Helm
add_helm_repo() {
    log_info "Adicionando repositório Helm do OPA Gatekeeper..."

    if helm repo list | grep -q "^gatekeeper"; then
        log_info "Repositório 'gatekeeper' já existe. Atualizando..."
    else
        helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
    fi

    helm repo update

    log_success "Repositório Helm configurado"
}

# Criar namespace com labels
create_namespace() {
    log_info "Criando namespace $NAMESPACE..."

    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_warning "Namespace $NAMESPACE já existe. Aplicando labels..."
    else
        kubectl create namespace "$NAMESPACE"
    fi

    # Aplicar labels
    kubectl label namespace "$NAMESPACE" \
        neural.hive/component=gatekeeper \
        neural.hive/layer=governanca \
        neural.hive/environment="$ENVIRONMENT" \
        --overwrite

    log_success "Namespace $NAMESPACE configurado"
}

# Deploy OPA Gatekeeper via Helm
deploy_gatekeeper() {
    log_info "Deployando OPA Gatekeeper via Helm..."

    cd "$REPO_DIR"

    # Atualizar dependências do chart
    log_info "Atualizando dependências do chart..."
    if ! helm dependency update ./helm-charts/opa-gatekeeper; then
        log_error "Falha ao atualizar dependências do chart"
        exit 1
    fi
    log_success "Dependências atualizadas"

    helm upgrade --install "$HELM_RELEASE_NAME" ./helm-charts/opa-gatekeeper \
        --namespace "$NAMESPACE" \
        --values "$VALUES_FILE" \
        --wait \
        --timeout="$TIMEOUT" \
        --debug

    log_success "OPA Gatekeeper deployado com sucesso"
}

# Aguardar pods ficarem prontos
wait_for_pods() {
    log_info "Aguardando pods do Gatekeeper ficarem prontos..."

    # Webhook
    log_info "Aguardando webhook controller..."
    if ! kubectl wait --for=condition=ready pod \
        -l gatekeeper.sh/operation=webhook \
        -n "$NAMESPACE" \
        --timeout="$WEBHOOK_TIMEOUT"; then
        log_error "Timeout aguardando webhook controller"
        kubectl get pods -n "$NAMESPACE"
        kubectl logs -n "$NAMESPACE" -l gatekeeper.sh/operation=webhook --tail=50
        exit 1
    fi

    # Audit
    log_info "Aguardando audit controller..."
    if ! kubectl wait --for=condition=ready pod \
        -l gatekeeper.sh/operation=audit \
        -n "$NAMESPACE" \
        --timeout="$AUDIT_TIMEOUT"; then
        log_error "Timeout aguardando audit controller"
        kubectl get pods -n "$NAMESPACE"
        kubectl logs -n "$NAMESPACE" -l gatekeeper.sh/operation=audit --tail=50
        exit 1
    fi

    log_success "Todos os pods estão prontos"
}

# Verificar CRDs instalados
verify_crds() {
    log_info "Verificando CRDs do Gatekeeper..."

    local expected_crds=(
        "constrainttemplates.templates.gatekeeper.sh"
        "configs.config.gatekeeper.sh"
    )

    for crd in "${expected_crds[@]}"; do
        if kubectl get crd "$crd" &> /dev/null; then
            log_success "CRD encontrado: $crd"
        else
            log_error "CRD não encontrado: $crd"
            exit 1
        fi
    done

    # Listar todos os CRDs do Gatekeeper
    log_info "CRDs do Gatekeeper instalados:"
    kubectl get crd | grep gatekeeper.sh
}

# Aplicar ConstraintTemplates
apply_constraint_templates() {
    log_info "Aplicando ConstraintTemplates..."

    cd "$REPO_DIR"

    if [[ -d "policies/constraint-templates" ]]; then
        kubectl apply -f policies/constraint-templates/

        # Aguardar processamento
        log_info "Aguardando processamento dos templates (30s)..."
        sleep 30

        # Verificar status
        log_info "ConstraintTemplates instalados:"
        kubectl get constrainttemplates -o custom-columns=NAME:.metadata.name,STATUS:.status.created
    else
        log_warning "Diretório policies/constraint-templates não encontrado. Pulando..."
    fi
}

# Aplicar Constraints (apenas aplicáveis para Fase 1)
apply_constraints() {
    log_info "Aplicando Constraints para Fase 1..."

    cd "$REPO_DIR"

    # Data Governance Validation
    if [[ -f "policies/constraints/data-governance-validation.yaml" ]]; then
        kubectl apply -f policies/constraints/data-governance-validation.yaml
        log_success "Constraint aplicado: data-governance-validation"
    else
        log_warning "Constraint não encontrado: data-governance-validation.yaml"
    fi

    # Resource Limits Required
    if [[ -f "policies/constraints/enforce-resource-limits.yaml" ]]; then
        kubectl apply -f policies/constraints/enforce-resource-limits.yaml
        log_success "Constraint aplicado: enforce-resource-limits"
    else
        log_warning "Constraint não encontrado: enforce-resource-limits.yaml"
    fi

    # Redis Security Validation
    if [[ -f "policies/constraints/redis-security-validation.yaml" ]]; then
        kubectl apply -f policies/constraints/redis-security-validation.yaml
        log_success "Constraint aplicado: redis-security-validation"
    else
        log_warning "Constraint não encontrado: redis-security-validation.yaml"
    fi

    # Pular mTLS e Image Signature (requerem Istio/Sigstore)
    log_info "Pulando constraints de mTLS e Image Signature (requerem Istio/Sigstore - Fase 2)"

    # Verificar constraints aplicados
    log_info "Constraints ativos:"
    kubectl get constraints -A
}

# Validar deployment
validate_deployment() {
    log_info "Validando deployment do OPA Gatekeeper..."

    # Status dos pods
    log_info "Status dos pods:"
    kubectl get pods -n "$NAMESPACE"

    # Validating Webhook Configuration
    log_info "ValidatingWebhookConfiguration:"
    kubectl get validatingwebhookconfigurations | grep gatekeeper || true

    # Executar script de validação se existir
    if [[ -f "$REPO_DIR/scripts/validation/validate-policy-enforcement.sh" ]]; then
        log_info "Executando validação de políticas..."
        bash "$REPO_DIR/scripts/validation/validate-policy-enforcement.sh"
    else
        log_warning "Script de validação não encontrado: scripts/validation/validate-policy-enforcement.sh"
    fi

    # Verificar violações
    log_info "Verificando violações..."
    local violations
    violations=$(kubectl get constraints -A -o jsonpath='{.items[*].status.totalViolations}' 2>/dev/null || echo "0")

    if [[ "$violations" == "0" ]] || [[ -z "$violations" ]]; then
        log_success "Nenhuma violação detectada"
    else
        log_warning "Violações detectadas: $violations (modo warn - esperado)"
    fi
}

# Exibir instruções de acesso
show_access_instructions() {
    log_success "========================================="
    log_success "OPA Gatekeeper deployado com sucesso!"
    log_success "========================================="
    echo ""
    log_info "Comandos úteis:"
    echo ""
    echo "  # Verificar pods:"
    echo "  kubectl get pods -n $NAMESPACE"
    echo ""
    echo "  # Verificar logs do webhook:"
    echo "  kubectl logs -n $NAMESPACE -l gatekeeper.sh/operation=webhook --tail=100"
    echo ""
    echo "  # Verificar logs do audit:"
    echo "  kubectl logs -n $NAMESPACE -l gatekeeper.sh/operation=audit --tail=100"
    echo ""
    echo "  # Listar ConstraintTemplates:"
    echo "  kubectl get constrainttemplates"
    echo ""
    echo "  # Listar Constraints ativos:"
    echo "  kubectl get constraints -A"
    echo ""
    echo "  # Verificar violações:"
    echo "  kubectl get constraints -A -o custom-columns=NAME:.metadata.name,VIOLATIONS:.status.totalViolations"
    echo ""
    log_info "Próximos passos:"
    echo "  1. Executar teste de governança: ./tests/governance-compliance-test.sh"
    echo "  2. Gerar relatório de compliance: ./scripts/governance/generate-compliance-report.sh"
    echo "  3. Monitorar violações por 7 dias (modo warn)"
    echo "  4. Transição para enforcement mode 'deny' após validação"
    echo ""
}

# Parse command-line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [--namespace NAMESPACE]"
                echo ""
                echo "Options:"
                echo "  --namespace NAMESPACE   Namespace para deploy do Gatekeeper (default: opa-gatekeeper)"
                echo "  -h, --help             Exibir esta mensagem de ajuda"
                exit 0
                ;;
            *)
                log_error "Argumento desconhecido: $1"
                echo "Use --help para ver opções disponíveis"
                exit 1
                ;;
        esac
    done
}

# Main execution
main() {
    log_info "========================================="
    log_info "Deploy OPA Gatekeeper - Ambiente Local"
    log_info "========================================="
    echo ""

    parse_args "$@"

    log_info "Namespace configurado: $NAMESPACE"
    echo ""

    check_prerequisites
    add_helm_repo
    create_namespace
    deploy_gatekeeper
    wait_for_pods
    verify_crds
    apply_constraint_templates
    apply_constraints
    validate_deployment
    show_access_instructions

    log_success "Deploy concluído com sucesso!"
    exit 0
}

# Executar main
main "$@"
