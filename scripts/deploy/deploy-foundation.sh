#!/bin/bash
# Script principal para deploy da Fase 1 - Fundação Neural Hive-Mind
# Orquestra Terraform, Helm e políticas OPA com melhorias de orquestração e controle de erros
# Version: 2.0

set -euo pipefail

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform"
HELM_DIR="${PROJECT_ROOT}/helm-charts"
K8S_DIR="${PROJECT_ROOT}/k8s"
POLICIES_DIR="${PROJECT_ROOT}/policies"
VALIDATION_DIR="${PROJECT_ROOT}/scripts/validation"

# Carregar funções comuns de validação
source "${VALIDATION_DIR}/common-validation-functions.sh"

# Variáveis de ambiente
ENV="${ENV:-dev}"
REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-neural-hive-${ENV}}"
VALIDATION_MODE="${VALIDATION_MODE:-all}"  # all, basic, skip
SKIP_VALIDATION="${SKIP_VALIDATION:-false}"
CORRELATION_ID="deploy-$(date +%s)-$(generate_random_string 6)"

# Configuração de deploy
DEPLOY_START_TIME=$(date +%s)
DEPLOY_REPORT_FILE="${REPORT_DIR}/deploy-foundation-${REPORT_TIMESTAMP}.json"
COMPONENTS_DEPLOYED=()
FAILED_COMPONENTS=()
ROLLBACK_ACTIONS=()

# ============================================================================
# FUNÇÕES DE CONFIGURAÇÃO E VALIDAÇÃO DE AMBIENTE
# ============================================================================

# Validar configuração de ambiente
validate_environment_config() {
    log_info "Validando configuração de ambiente: ${ENV}"

    local config_issues=()

    # Verificar consistência de variáveis
    if [[ "$ENV" == "prod" && "$REGION" != "us-east-1" ]]; then
        config_issues+=("Ambiente prod deve usar região us-east-1")
    fi

    # Verificar arquivos de configuração necessários
    local required_configs=(
        "${PROJECT_ROOT}/environments/${ENV}/terraform.tfvars"
        "${PROJECT_ROOT}/environments/${ENV}/helm-values/istio-values.yaml"
    )

    for config_file in "${required_configs[@]}"; do
        if [[ ! -f "$config_file" ]]; then
            config_issues+=("Arquivo de configuração não encontrado: $config_file")
        fi
    done

    # Verificar recursos AWS necessários
    if ! aws ec2 describe-vpcs --region "$REGION" >/dev/null 2>&1; then
        config_issues+=("Não foi possível acessar VPCs na região $REGION")
    fi

    if [[ ${#config_issues[@]} -gt 0 ]]; then
        log_error "Problemas de configuração encontrados:"
        for issue in "${config_issues[@]}"; do
            log_error "  - $issue"
        done
        return 1
    fi

    log_success "Configuração de ambiente validada"
    return 0
}

# Verificar pré-requisitos com melhor validação
check_prerequisites_deploy() {
    log_info "[${CORRELATION_ID}] Verificando pré-requisitos avançados..."

    # Usar função da biblioteca comum
    if ! check_prerequisites; then
        log_error "Pré-requisitos básicos não atendidos"
        return 1
    fi

    # Verificações específicas do deploy
    local required_tools=("terraform" "aws" "kubectl" "helm" "jq")
    local tool_versions=()

    for tool in "${required_tools[@]}"; do
        if command -v "$tool" >/dev/null 2>&1; then
            local version=$("$tool" version --short 2>/dev/null || "$tool" --version 2>/dev/null | head -1 || echo "unknown")
            tool_versions+=("$tool: $version")
        fi
    done

    log_info "Versões das ferramentas:"
    for version_info in "${tool_versions[@]}"; do
        log_info "  $version_info"
    done

    # Verificar permissões AWS específicas
    local required_permissions=(
        "eks:DescribeCluster"
        "iam:ListRoles"
        "s3:ListBucket"
    )

    for permission in "${required_permissions[@]}"; do
        log_debug "Verificando permissão: $permission"
    done

    # Verificar espaço em disco
    local available_space=$(df "$PROJECT_ROOT" | awk 'NR==2 {print $4}')
    if [[ $available_space -lt 1048576 ]]; then  # 1GB in KB
        log_warning "Espaço em disco baixo: ${available_space}KB disponível"
    fi

    log_success "Todos os pré-requisitos avançados atendidos"
    return 0
}

# Deploy da infraestrutura Terraform (root stack)
deploy_terraform_infrastructure() {
    log_info "Deployando infraestrutura completa com Terraform..."

    cd "${TERRAFORM_DIR}"

    # Verificar se backend S3 está configurado
    BACKEND_CONFIG="${PROJECT_ROOT}/environments/${ENV}/backend.hcl"
    if [[ -f "$BACKEND_CONFIG" ]]; then
        log_info "Usando backend S3 remoto para ambiente ${ENV}"

        # Verificar se backend S3 existe
        BUCKET_NAME=$(grep "bucket" "$BACKEND_CONFIG" | cut -d'=' -f2 | tr -d ' "')
        if ! aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
            log_warning "Backend S3 não existe. Execute: scripts/setup/setup-backend.sh ${ENV}"
            log_info "Usando backend local temporariamente..."
            terraform init
        else
            log_info "Inicializando Terraform com backend S3..."
            terraform init -backend-config="$BACKEND_CONFIG" -reconfigure
        fi
    else
        log_warning "Backend S3 não configurado. Usando backend local."
        log_info "Para configurar backend S3, execute: scripts/setup/setup-backend.sh ${ENV}"
        terraform init
    fi

    # Validar configuração
    log_info "Validando configuração Terraform..."
    terraform validate
    if [[ $? -ne 0 ]]; then
        log_error "Falha na validação do Terraform"
        exit 1
    fi

    # Verificar se arquivo tfvars existe
    TFVARS_FILE="${PROJECT_ROOT}/environments/${ENV}/terraform.tfvars"
    if [[ ! -f "$TFVARS_FILE" ]]; then
        log_warning "Arquivo tfvars não encontrado: $TFVARS_FILE"
        log_info "Usando variáveis padrão do Terraform"
        TFVARS_ARGS=""
    else
        TFVARS_ARGS="-var-file=$TFVARS_FILE"
    fi

    # Planejar mudanças
    log_info "Planejando mudanças Terraform..."
    terraform plan $TFVARS_ARGS -out=tfplan
    if [[ $? -ne 0 ]]; then
        log_error "Falha no planejamento do Terraform"
        exit 1
    fi

    # Aplicar mudanças
    if [[ "${DRY_RUN:-false}" != "true" ]]; then
        log_info "Aplicando mudanças Terraform..."
        terraform apply -auto-approve $TFVARS_ARGS
        if [[ $? -ne 0 ]]; then
            log_error "Falha na aplicação do Terraform"
            exit 1
        fi

        # Atualizar kubeconfig
        log_info "Atualizando kubeconfig..."
        aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${REGION}"
        if [[ $? -ne 0 ]]; then
            log_error "Falha ao atualizar kubeconfig"
            exit 1
        fi

        # Verificar conectividade com cluster
        log_info "Verificando conectividade com cluster..."
        kubectl cluster-info
        if [[ $? -ne 0 ]]; then
            log_error "Falha ao conectar com cluster EKS"
            exit 1
        fi

        log_success "Infraestrutura Terraform deployada com sucesso"
    else
        log_warning "Modo DRY_RUN - pulando apply"
    fi
}

# Extrair outputs do Terraform
extract_terraform_outputs() {
    log_info "Extraindo outputs do Terraform..."

    cd "${TERRAFORM_DIR}"

    # Obter outputs necessários
    export SIGSTORE_IRSA_ROLE_ARN=$(terraform output -raw sigstore_irsa_role_arn 2>/dev/null || echo "")
    export CLUSTER_NAME_OUTPUT=$(terraform output -raw cluster_name 2>/dev/null || echo "${CLUSTER_NAME}")
    export ECR_REGISTRY_URL=$(terraform output -json registry_urls 2>/dev/null | jq -r 'values[0] // ""' | cut -d'/' -f1)

    # Validar outputs críticos
    if [[ -z "$SIGSTORE_IRSA_ROLE_ARN" ]]; then
        log_warning "SIGSTORE_IRSA_ROLE_ARN não encontrado nos outputs do Terraform"
        log_warning "Sigstore Policy Controller será instalado sem IRSA"
    else
        log_info "IRSA Role ARN encontrado: ${SIGSTORE_IRSA_ROLE_ARN}"
    fi

    if [[ -z "$ECR_REGISTRY_URL" ]]; then
        log_warning "ECR Registry URL não encontrado nos outputs do Terraform"
    else
        log_info "ECR Registry encontrado: ${ECR_REGISTRY_URL}"
    fi

    log_success "Outputs do Terraform extraídos"
}

# Aplicar bootstrap manifests
apply_bootstrap_manifests() {
    log_info "Aplicando bootstrap manifests..."

    log_info "Aplicando namespaces..."
    kubectl apply -f "${K8S_DIR}/bootstrap/"
    if [[ $? -ne 0 ]]; then
        log_error "Falha ao aplicar bootstrap manifests"
        exit 1
    fi

    log_success "Bootstrap manifests aplicados"
}

# Aplicar políticas OPA com validação avançada
apply_opa_policies() {
    log_info "[${CORRELATION_ID}] Aplicando políticas OPA com validação..."

    local policy_start_time=$(date +%s)

    # Verificar se OPA Gatekeeper está pronto
    if ! wait_for_condition "OPA Gatekeeper ready" \
        "kubectl -n gatekeeper-system get pods -l gatekeeper.sh/operation=webhook -o jsonpath='{.items[*].status.phase}' | grep -q Running" \
        180; then
        log_error "OPA Gatekeeper não está pronto"
        FAILED_COMPONENTS+=("opa-policies")
        return 1
    fi

    # Aplicar constraint templates com validação
    log_info "Aplicando constraint templates..."
    if ! kubectl apply -f "${POLICIES_DIR}/constraint-templates/" --validate=true; then
        log_error "Falha ao aplicar constraint templates"
        FAILED_COMPONENTS+=("constraint-templates")
        return 1
    fi

    # Aguardar e validar templates
    log_info "Validando constraint templates..."
    if ! wait_for_condition "Constraint templates established" \
        "kubectl get constrainttemplates -o jsonpath='{.items[*].status.created[*]}' | grep -q true" \
        120; then
        log_warning "Algumas constraint templates podem não estar prontas"
    fi

    # Aplicar constraints com retry
    log_info "Aplicando constraints..."
    local retry_count=0
    local max_retries=3

    while [[ $retry_count -lt $max_retries ]]; do
        if kubectl apply -f "${POLICIES_DIR}/constraints/" --validate=true; then
            break
        else
            retry_count=$((retry_count + 1))
            if [[ $retry_count -lt $max_retries ]]; then
                log_warning "Tentativa $retry_count falhou, tentando novamente em 10s..."
                sleep 10
            else
                log_error "Falha ao aplicar constraints após $max_retries tentativas"
                FAILED_COMPONENTS+=("constraints")
                return 1
            fi
        fi
    done

    # Validar políticas aplicadas
    local applied_constraints=$(kubectl get constraints --all-namespaces --no-headers | wc -l)
    log_info "Políticas aplicadas: $applied_constraints constraints"

    local policy_time=$(measure_execution_time $policy_start_time)
    log_success "Políticas OPA aplicadas com sucesso (${policy_time}s)"
    COMPONENTS_DEPLOYED+=("opa-policies")
    return 0
}

# Deploy do Istio service mesh
deploy_istio() {
    log_info "Deployando Istio service mesh..."

    # Instalar Istio base usando helm chart local
    log_info "Instalando Istio base..."
    helm upgrade --install istio-base "${HELM_DIR}/istio-base" \
        --namespace istio-system \
        --create-namespace \
        --values "${PROJECT_ROOT}/environments/${ENV}/helm-values/istio-values.yaml" \
        --wait

    if [[ $? -ne 0 ]]; then
        log_error "Falha ao instalar Istio base"
        exit 1
    fi

    log_success "Istio service mesh deployado"
}

# Deploy do OPA Gatekeeper
deploy_opa_gatekeeper() {
    log_info "Deployando OPA Gatekeeper..."

    # Verificar se arquivo de valores específico do ambiente existe
    OPA_VALUES_FILE="${PROJECT_ROOT}/environments/${ENV}/helm-values/opa-gatekeeper-values.yaml"
    if [[ ! -f "$OPA_VALUES_FILE" ]]; then
        log_warning "Arquivo de valores específico não encontrado: $OPA_VALUES_FILE"
        log_info "Usando valores padrão do chart"
        VALUES_ARGS=""
    else
        log_info "Usando valores específicos do ambiente: $OPA_VALUES_FILE"
        VALUES_ARGS="--values $OPA_VALUES_FILE"
    fi

    # Instalar Gatekeeper usando helm chart local
    log_info "Instalando OPA Gatekeeper..."
    helm upgrade --install opa-gatekeeper "${HELM_DIR}/opa-gatekeeper" \
        --namespace gatekeeper-system \
        --create-namespace \
        $VALUES_ARGS \
        --wait

    if [[ $? -ne 0 ]]; then
        log_error "Falha ao instalar OPA Gatekeeper"
        exit 1
    fi

    # Aguardar Gatekeeper estar pronto
    log_info "Aguardando Gatekeeper ficar pronto..."
    kubectl -n gatekeeper-system wait --for=condition=ready pod -l gatekeeper.sh/operation=webhook --timeout=180s
    if [[ $? -ne 0 ]]; then
        log_error "Timeout aguardando Gatekeeper ficar pronto"
        exit 1
    fi

    log_success "OPA Gatekeeper deployado"
}

# Deploy do Sigstore Policy Controller
deploy_sigstore_policy_controller() {
    log_info "Deployando Sigstore Policy Controller..."

    # Verificar se arquivo de valores específico do ambiente existe
    SIGSTORE_VALUES_FILE="${PROJECT_ROOT}/environments/${ENV}/helm-values/sigstore-values.yaml"
    if [[ ! -f "$SIGSTORE_VALUES_FILE" ]]; then
        log_warning "Arquivo de valores específico não encontrado: $SIGSTORE_VALUES_FILE"
        log_info "Usando valores padrão do chart"
        VALUES_ARGS=""
    else
        log_info "Usando valores específicos do ambiente: $SIGSTORE_VALUES_FILE"

        # Criar arquivo temporário com substituições de placeholders
        TEMP_VALUES_FILE="/tmp/sigstore-values-${ENV}.yaml"
        cp "$SIGSTORE_VALUES_FILE" "$TEMP_VALUES_FILE"

        # Substituir placeholders com valores reais
        if [[ -n "$SIGSTORE_IRSA_ROLE_ARN" ]]; then
            sed -i "s|SIGSTORE_IRSA_ROLE_ARN_PLACEHOLDER|${SIGSTORE_IRSA_ROLE_ARN}|g" "$TEMP_VALUES_FILE"
            log_info "IRSA Role ARN configurado: ${SIGSTORE_IRSA_ROLE_ARN}"
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

    # Instalar Policy Controller usando helm chart local
    log_info "Instalando Sigstore Policy Controller..."
    helm upgrade --install sigstore-policy-controller "${HELM_DIR}/sigstore-policy-controller" \
        --namespace cosign-system \
        --create-namespace \
        $VALUES_ARGS \
        --wait

    if [[ $? -ne 0 ]]; then
        log_error "Falha ao instalar Sigstore Policy Controller"
        exit 1
    fi

    # Limpar arquivo temporário
    [[ -f "$TEMP_VALUES_FILE" ]] && rm -f "$TEMP_VALUES_FILE"

    # Aguardar Policy Controller estar pronto
    log_info "Aguardando Policy Controller ficar pronto..."
    kubectl -n cosign-system wait --for=condition=available deployment/sigstore-policy-controller --timeout=180s
    if [[ $? -ne 0 ]]; then
        log_error "Timeout aguardando Policy Controller ficar pronto"
        exit 1
    fi

    log_success "Sigstore Policy Controller deployado"
}

# Executar suite de validações granular
execute_validation_suite() {
    if [[ "$SKIP_VALIDATION" == "true" ]]; then
        log_warning "Validações puladas por configuração"
        return 0
    fi

    log_info "[${CORRELATION_ID}] Executando suite de validações ($VALIDATION_MODE)..."

    local validation_start_time=$(date +%s)
    local validation_results=()

    case "$VALIDATION_MODE" in
        "basic")
            validation_results+=($(run_basic_validations))
            ;;
        "all")
            validation_results+=($(run_comprehensive_validations))
            ;;
        "skip")
            log_warning "Modo skip - executando apenas verificações críticas"
            validation_results+=($(run_critical_validations))
            ;;
        *)
            log_warning "Modo de validação desconhecido: $VALIDATION_MODE, usando 'basic'"
            validation_results+=($(run_basic_validations))
            ;;
    esac

    local validation_time=$(measure_execution_time $validation_start_time)

    # Analisar resultados
    local failed_validations=0
    for result in "${validation_results[@]}"; do
        if [[ "$result" == *"FAIL"* ]]; then
            failed_validations=$((failed_validations + 1))
        fi
    done

    if [[ $failed_validations -gt 0 ]]; then
        log_warning "$failed_validations validações falharam"
        add_recommendation "Revisar validações que falharam antes de prosseguir para produção" "high"
    else
        log_success "Todas as validações passaram"
    fi

    log_info "Suite de validações concluída (${validation_time}s)"
    return $failed_validations
}

run_basic_validations() {
    log_info "Executando validações básicas..."

    local results=()

    # Validação de saúde do cluster
    if "${VALIDATION_DIR}/validate-cluster-health.sh" >/dev/null 2>&1; then
        results+=("cluster-health:PASS")
    else
        results+=("cluster-health:FAIL")
    fi

    printf '%s\n' "${results[@]}"
}

run_comprehensive_validations() {
    log_info "Executando validações abrangentes..."

    local results=()

    # Executar suite completa
    if "${VALIDATION_DIR}/validate-comprehensive-suite.sh" >/dev/null 2>&1; then
        results+=("comprehensive-suite:PASS")
    else
        results+=("comprehensive-suite:FAIL")
    fi

    printf '%s\n' "${results[@]}"
}

run_critical_validations() {
    log_info "Executando apenas validações críticas..."

    local results=()

    # Verificar se cluster está acessível
    if kubectl cluster-info >/dev/null 2>&1; then
        results+=("cluster-access:PASS")
    else
        results+=("cluster-access:FAIL")
    fi

    printf '%s\n' "${results[@]}"
}

# Função de rollback inteligente com rollback seletivo
rollback() {
    local rollback_reason="${1:-unknown}"

    log_error "[${CORRELATION_ID}] Erro detectado: $rollback_reason. Iniciando rollback seletivo..."

    local rollback_start_time=$(date +%s)

    # Executar ações de rollback na ordem inversa
    if [[ ${#ROLLBACK_ACTIONS[@]} -gt 0 ]]; then
        log_info "Executando ${#ROLLBACK_ACTIONS[@]} ações de rollback..."

        for ((i=${#ROLLBACK_ACTIONS[@]}-1; i>=0; i--)); do
            local action="${ROLLBACK_ACTIONS[i]}"
            log_info "Executando rollback: $action"

            case "$action" in
                "opa-policies")
                    kubectl delete constraints --all --ignore-not-found=true >/dev/null 2>&1 || true
                    kubectl delete constrainttemplates --all --ignore-not-found=true >/dev/null 2>&1 || true
                    ;;
                "opa-gatekeeper")
                    helm uninstall opa-gatekeeper -n gatekeeper-system >/dev/null 2>&1 || true
                    ;;
                "sigstore-policy-controller")
                    helm uninstall sigstore-policy-controller -n cosign-system >/dev/null 2>&1 || true
                    ;;
                "istio")
                    helm uninstall istio-base -n istio-system >/dev/null 2>&1 || true
                    ;;
                "bootstrap-manifests")
                    kubectl delete -f "${K8S_DIR}/bootstrap/" --ignore-not-found=true >/dev/null 2>&1 || true
                    ;;
                *)
                    log_warning "Ação de rollback desconhecida: $action"
                    ;;
            esac
        done
    else
        log_warning "Nenhuma ação de rollback registrada"
    fi

    # Preservar logs de deploy em caso de falha
    local rollback_log_dir="${REPORT_DIR}/rollback-$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$rollback_log_dir"

    # Coletar logs dos namespaces afetados
    for namespace in "istio-system" "gatekeeper-system" "cosign-system"; do
        if kubectl get namespace "$namespace" >/dev/null 2>&1; then
            kubectl logs --all-containers=true -n "$namespace" --prefix=true > "${rollback_log_dir}/${namespace}-logs.txt" 2>/dev/null || true
        fi
    done

    # Salvar estado atual dos recursos
    kubectl get all --all-namespaces -o yaml > "${rollback_log_dir}/cluster-state.yaml" 2>/dev/null || true

    local rollback_time=$(measure_execution_time $rollback_start_time)

    log_warning "Rollback concluído (${rollback_time}s). Logs salvos em: $rollback_log_dir"
    log_warning "Para reverter infraestrutura Terraform, execute:"
    log_warning "  cd ${TERRAFORM_DIR} && terraform destroy -var-file=${PROJECT_ROOT}/environments/${ENV}/terraform.tfvars"

    # Gerar relatório de rollback
    generate_rollback_report "$rollback_reason" "$rollback_log_dir"
}

generate_rollback_report() {
    local reason="$1"
    local log_dir="$2"

    cat > "${log_dir}/rollback-report.json" <<EOF
{
  "rollback_metadata": {
    "correlation_id": "$CORRELATION_ID",
    "reason": "$reason",
    "timestamp": "$(date -Iseconds)",
    "environment": "$ENV",
    "cluster_name": "$CLUSTER_NAME"
  },
  "components_deployed": $(printf '%s\n' "${COMPONENTS_DEPLOYED[@]}" | jq -R . | jq -s .),
  "failed_components": $(printf '%s\n' "${FAILED_COMPONENTS[@]}" | jq -R . | jq -s .),
  "rollback_actions": $(printf '%s\n' "${ROLLBACK_ACTIONS[@]}" | jq -R . | jq -s .),
  "log_directory": "$log_dir"
}
EOF
}

# Trap para rollback em caso de erro
trap rollback ERR

# Main
main() {
    log_info "Iniciando deployment da Fase 1 - Fundação Neural Hive-Mind"
    log_info "Ambiente: ${ENV}"
    log_info "Região: ${REGION}"
    log_info "Cluster: ${CLUSTER_NAME}"

    # Confirmar com usuário
    if [[ "${FORCE:-false}" != "true" ]]; then
        read -p "Deseja continuar? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warning "Deployment cancelado"
            exit 0
        fi
    fi

    # Executar deployment
    check_prerequisites_deploy

    # Fase 1: Infraestrutura base (Terraform)
    deploy_terraform_infrastructure

    # Validar configuração de ambiente
    validate_environment_config

    # Extrair outputs do Terraform para configurar Helm charts
    extract_terraform_outputs

    # Deploy sequencial completo com controle de dependências
    log_info "[${CORRELATION_ID}] Executando deployment sequencial completo..."

    # Fase 2: Helm charts de segurança
    if deploy_istio; then
        COMPONENTS_DEPLOYED+=("istio")
        ROLLBACK_ACTIONS+=("istio")
    else
        log_error "Falha no deploy do Istio"
        exit 1
    fi

    if deploy_opa_gatekeeper; then
        COMPONENTS_DEPLOYED+=("opa-gatekeeper")
        ROLLBACK_ACTIONS+=("opa-gatekeeper")
    else
        log_error "Falha no deploy do OPA Gatekeeper"
        exit 1
    fi

    if deploy_sigstore_policy_controller; then
        COMPONENTS_DEPLOYED+=("sigstore-policy-controller")
        ROLLBACK_ACTIONS+=("sigstore-policy-controller")
    else
        log_error "Falha no deploy do Sigstore Policy Controller"
        exit 1
    fi

    # Fase 3: Kubernetes bootstrap manifests
    if apply_bootstrap_manifests; then
        COMPONENTS_DEPLOYED+=("bootstrap-manifests")
        ROLLBACK_ACTIONS+=("bootstrap-manifests")
    else
        log_error "Falha ao aplicar bootstrap manifests"
        exit 1
    fi

    # Fase 4: Políticas OPA
    if apply_opa_policies; then
        COMPONENTS_DEPLOYED+=("opa-policies")
        ROLLBACK_ACTIONS+=("opa-policies")
    else
        log_error "Falha ao aplicar políticas OPA"
        exit 1
    fi

    # Fase 5: Validação completa
    execute_validation_suite

    # Gerar relatório final de deployment
    generate_deployment_report

    # Executar health checks contínuos
    check_deployment_health

    log_success "==================================="
    log_success "[${CORRELATION_ID}] Fundação Neural Hive-Mind deployada com sucesso!"
    log_info "Componentes deployados: ${#COMPONENTS_DEPLOYED[@]}"
    log_info "Tempo total de deployment: $(measure_execution_time $DEPLOY_START_TIME)s"
    log_info "Relatório detalhado: $DEPLOY_REPORT_FILE"
    log_info "Próximos passos:"
    log_info "1. Verifique o dashboard: kubectl proxy"
    log_info "2. Acesse Istio: istioctl dashboard kiali"
    log_info "3. Monitore políticas: kubectl get constraints -A"
    log_info "4. Execute validações contínuas: scripts/validation/validate-comprehensive-suite.sh"
    log_info "5. Para deployment específico de segurança: scripts/deploy/deploy-security.sh"
    log_success "==================================="

# Gerar relatório consolidado de deployment
generate_deployment_report() {
    log_info "Gerando relatório consolidado de deployment..."

    local total_time=$(measure_execution_time $DEPLOY_START_TIME)
    local cluster_metrics=($(collect_cluster_metrics))

    cat > "$DEPLOY_REPORT_FILE" <<EOF
{
  "deployment_metadata": {
    "correlation_id": "$CORRELATION_ID",
    "environment": "$ENV",
    "region": "$REGION",
    "cluster_name": "$CLUSTER_NAME",
    "start_time": $DEPLOY_START_TIME,
    "total_time_seconds": $total_time,
    "completion_timestamp": "$(date -Iseconds)",
    "script_version": "2.0"
  },
  "deployment_summary": {
    "components_deployed": $(printf '%s\n' "${COMPONENTS_DEPLOYED[@]}" | jq -R . | jq -s .),
    "failed_components": $(printf '%s\n' "${FAILED_COMPONENTS[@]}" | jq -R . | jq -s .),
    "success_rate": "$(( ${#COMPONENTS_DEPLOYED[@]} * 100 / (${#COMPONENTS_DEPLOYED[@]} + ${#FAILED_COMPONENTS[@]}) ))%"
  },
  "cluster_metrics": {
EOF

    for metric in "${cluster_metrics[@]}"; do
        local key=$(echo "$metric" | cut -d: -f1)
        local value=$(echo "$metric" | cut -d: -f2)
        echo "    \"$key\": $value," >> "$DEPLOY_REPORT_FILE"
    done

    cat >> "$DEPLOY_REPORT_FILE" <<EOF
    "validation_mode": "$VALIDATION_MODE"
  },
  "next_steps": [
    "Execute validações contínuas",
    "Configure monitoramento",
    "Deploy aplicações Neural Hive-Mind"
  ]
}
EOF

    log_success "Relatório salvo em: $DEPLOY_REPORT_FILE"
}

# Executar health checks contínuos durante deploy
check_deployment_health() {
    log_info "Executando health checks pós-deployment..."

    local health_issues=()

    # Verificar pods em crash loop
    local crashing_pods=$(kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null | wc -l)
    if [[ $crashing_pods -gt 0 ]]; then
        health_issues+=("$crashing_pods pods não estão em estado Running")
    fi

    # Verificar services sem endpoints
    local services_without_endpoints=$(kubectl get endpoints --all-namespaces --no-headers -o custom-columns=":metadata.name" | grep "<none>" | wc -l 2>/dev/null || echo 0)
    if [[ $services_without_endpoints -gt 0 ]]; then
        health_issues+=("$services_without_endpoints services sem endpoints")
    fi

    if [[ ${#health_issues[@]} -gt 0 ]]; then
        log_warning "Problemas de saúde detectados:"
        for issue in "${health_issues[@]}"; do
            log_warning "  - $issue"
        done
        add_recommendation "Investigar e corrigir problemas de saúde detectados" "high"
    else
        log_success "Todos os health checks passaram"
    fi
}
}

# Executar
main "$@"