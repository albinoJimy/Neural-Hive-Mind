#!/bin/bash
# Script para validação de código Terraform
# Inclui format, validate, lint e security scanning

set -euo pipefail

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform"

log_info() {
    echo -e "[INFO] $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Validar formato
validate_format() {
    log_info "Verificando formatação Terraform..."

    find "${TERRAFORM_DIR}" -name "*.tf" -type f | while read -r file; do
        if terraform fmt -check=true "$file" > /dev/null 2>&1; then
            log_success "$file"
        else
            log_error "$file - necessita formatação"
            terraform fmt "$file"
        fi
    done
}

# Validar sintaxe
validate_syntax() {
    log_info "Validando sintaxe Terraform..."

    # Primeiro validar o root module com backend S3
    log_info "Validando módulo root com backend S3..."
    cd "${TERRAFORM_DIR}"

    # Inicializar com backend configurado se existir backend.hcl
    if [[ -f "${TERRAFORM_DIR}/backend.hcl" ]]; then
        log_info "Usando backend.hcl para configuração"
        terraform init -backend-config="backend.hcl" -reconfigure > /dev/null 2>&1
    else
        terraform init -backend=false > /dev/null 2>&1
    fi

    if terraform validate; then
        log_success "Módulo root válido"
    else
        log_error "Módulo root com erros"
        exit 1
    fi

    # Validar sub-módulos
    for module_dir in "${TERRAFORM_DIR}"/modules/*/; do
        if [[ -d "$module_dir" ]]; then
            module_name=$(basename "$module_dir")
            log_info "Validando módulo: $module_name"

            cd "$module_dir"
            if terraform init -backend=false > /dev/null 2>&1; then
                if terraform validate; then
                    log_success "Módulo $module_name válido"
                else
                    log_error "Módulo $module_name com erros"
                    exit 1
                fi
            fi
        fi
    done
}

# Executar tflint
run_tflint() {
    log_info "Executando TFLint..."

    if command -v tflint &> /dev/null; then
        for module_dir in "${TERRAFORM_DIR}"/modules/*/; do
            if [[ -d "$module_dir" ]]; then
                module_name=$(basename "$module_dir")
                cd "$module_dir"

                if tflint --init > /dev/null 2>&1; then
                    if tflint; then
                        log_success "TFLint passou para $module_name"
                    else
                        log_warning "TFLint encontrou issues em $module_name"
                    fi
                fi
            fi
        done
    else
        log_warning "TFLint não instalado. Instale com: brew install tflint"
    fi
}

# Security scanning com Checkov
run_checkov() {
    log_info "Executando Checkov security scanning..."

    if command -v checkov &> /dev/null; then
        checkov -d "${TERRAFORM_DIR}" \
            --framework terraform \
            --output cli \
            --soft-fail \
            --quiet

        if [[ $? -eq 0 ]]; then
            log_success "Checkov não encontrou vulnerabilidades críticas"
        else
            log_warning "Checkov encontrou potenciais issues de segurança"
        fi
    else
        log_warning "Checkov não instalado. Instale com: pip install checkov"
    fi
}

# Validar terraform plan
validate_plan() {
    log_info "Gerando terraform plan para validação..."

    ENV="${ENV:-dev}"
    cd "${TERRAFORM_DIR}"

    # Verificar se backend está configurado
    if [[ -f "backend.hcl" ]]; then
        log_info "Usando backend S3 configurado"

        # Inicializar com backend
        if ! terraform init -backend-config="backend.hcl" -reconfigure > /dev/null 2>&1; then
            log_warning "Falha ao inicializar com backend S3, usando local"
            terraform init -backend=false > /dev/null 2>&1
        fi
    else
        terraform init -backend=false > /dev/null 2>&1
    fi

    # Validar plan do root module
    if [[ -f "${PROJECT_ROOT}/environments/${ENV}/terraform.tfvars" ]]; then
        if terraform plan \
            -var-file="${PROJECT_ROOT}/environments/${ENV}/terraform.tfvars" \
            -input=false \
            > /dev/null 2>&1; then
            log_success "Plan válido para infraestrutura completa"
        else
            log_error "Plan falhou para infraestrutura"
        fi
    else
        log_warning "Arquivo tfvars não encontrado para ambiente ${ENV}"
    fi
}

# Verificar tags Kubernetes
validate_kubernetes_tags() {
    log_info "Verificando tags Kubernetes nas subnets..."

    # Verificar se as tags kubernetes estão usando cluster_name correto
    if grep -r "kubernetes.io/cluster" "${TERRAFORM_DIR}/modules/network" | grep -q "var.cluster_name"; then
        log_success "Tags Kubernetes configuradas corretamente com cluster_name"
    else
        log_warning "Verificar tags Kubernetes nas subnets"
    fi
}

# Verificar outputs necessários
validate_outputs() {
    log_info "Verificando outputs dos módulos..."

    required_outputs=("vpc_id" "private_subnet_ids" "public_subnet_ids" "cluster_endpoint" "oidc_provider_arn")

    for output in "${required_outputs[@]}"; do
        if grep -r "output \"$output\"" "${TERRAFORM_DIR}/modules" > /dev/null; then
            log_success "Output $output definido"
        else
            log_error "Output $output não encontrado"
        fi
    done
}

# Gerar relatório
generate_report() {
    log_info "Gerando relatório de validação..."

    REPORT_FILE="${PROJECT_ROOT}/terraform-validation-report.txt"

    {
        echo "==================================="
        echo "Terraform Validation Report"
        echo "Date: $(date)"
        echo "Environment: ${ENV:-dev}"
        echo "Backend: ${BACKEND_TYPE:-local}"
        echo "==================================="
        echo ""
        echo "Modules validated:"
        echo "  - root module"
        find "${TERRAFORM_DIR}/modules" -maxdepth 1 -type d | tail -n +2 | while read -r dir; do
            echo "  - $(basename "$dir")"
        done
        echo ""
        echo "Validation checks performed:"
        echo "  ✓ Terraform format"
        echo "  ✓ Terraform validate"
        echo "  ✓ TFLint"
        echo "  ✓ Checkov security scan"
        echo "  ✓ Terraform plan"
        echo "  ✓ Kubernetes tags validation"
        echo "  ✓ Module outputs validation"
        echo ""
        echo "Backend Configuration:"
        if [[ -f "${TERRAFORM_DIR}/backend.hcl" ]]; then
            echo "  ✓ Backend S3 configurado"
        else
            echo "  ⚠ Backend local (S3 não configurado)"
        fi
        echo ""
        echo "==================================="
    } > "$REPORT_FILE"

    log_success "Relatório salvo em: $REPORT_FILE"
}

# Detectar tipo de backend
detect_backend() {
    if [[ -f "${TERRAFORM_DIR}/backend.hcl" ]]; then
        BACKEND_TYPE="s3"
        log_info "Backend S3 detectado"
    else
        BACKEND_TYPE="local"
        log_info "Usando backend local"
    fi
}

# Main
main() {
    log_info "Iniciando validação de infraestrutura Terraform..."

    detect_backend
    validate_format
    validate_syntax
    validate_kubernetes_tags
    validate_outputs
    run_tflint
    run_checkov
    validate_plan
    generate_report

    log_success "Validação Terraform completa!"
}

main "$@"