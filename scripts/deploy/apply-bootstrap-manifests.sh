#!/bin/bash
#
# apply-bootstrap-manifests.sh
# Script para aplicar manifests de bootstrap do Kubernetes com substituição de placeholders
# Neural Hive-Mind Cluster Bootstrap
#

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
BOOTSTRAP_DIR="${PROJECT_ROOT}/k8s/bootstrap"
ENVIRONMENTS_DIR="${PROJECT_ROOT}/environments"
# Use different temp dir for dry-run to preserve artifacts
if [[ "${DRY_RUN:-}" == "true" ]]; then
    TEMP_DIR="${PROJECT_ROOT}/.tmp/bootstrap-dry-run"
else
    TEMP_DIR="${PROJECT_ROOT}/.tmp/bootstrap"
fi

# Função para logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Função para verificar dependências
check_dependencies() {
    log "Verificando dependências..."

    local deps=("kubectl" "yq" "envsubst")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "Dependência necessária não encontrada: $dep"
            exit 1
        fi
    done

    log_success "Todas as dependências verificadas"
}

# Função para verificar contexto do Kubernetes
check_k8s_context() {
    log "Verificando contexto do Kubernetes..."

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi

    local context
    context=$(kubectl config current-context)
    log_success "Conectado ao cluster: $context"

    # Verificar se não é um cluster de produção sem confirmação
    if [[ "$context" == *"prod"* ]] && [[ "${FORCE_PROD:-}" != "true" ]]; then
        echo -e "${YELLOW}ATENÇÃO: Você está conectado a um cluster de PRODUÇÃO: $context${NC}"
        read -p "Tem certeza que deseja continuar? (digite 'yes' para confirmar): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_error "Operação cancelada pelo usuário"
            exit 1
        fi
    fi
}

# Função para determinar o ambiente
determine_environment() {
    if [[ -n "${ENVIRONMENT:-}" ]]; then
        echo "$ENVIRONMENT"
        return
    fi

    local context
    context=$(kubectl config current-context)

    if [[ "$context" == *"minikube"* ]]; then
        echo "local"
    elif [[ "$context" == *"dev"* ]]; then
        echo "dev"
    elif [[ "$context" == *"staging"* ]]; then
        echo "staging"
    elif [[ "$context" == *"prod"* ]]; then
        echo "prod"
    else
        log_warning "Não foi possível determinar o ambiente do contexto: $context"
        echo "dev"  # Default para dev
    fi
}

# Função para carregar configuração de ambiente
load_environment_config() {
    local env="$1"
    local config_file="${ENVIRONMENTS_DIR}/${env}/bootstrap-config.yaml"

    log "Carregando configuração para ambiente: $env"

    if [[ ! -f "$config_file" ]]; then
        if [[ "$env" == "local" ]]; then
            log_warning "Arquivo de configuração não encontrado: $config_file"
            log_warning "Usando configuração dev como fallback"
            config_file="${ENVIRONMENTS_DIR}/dev/bootstrap-config.yaml"
            if [[ ! -f "$config_file" ]]; then
                log_error "Arquivo de configuração dev também não encontrado: $config_file"
                exit 1
            fi
        else
            log_error "Arquivo de configuração não encontrado: $config_file"
            exit 1
        fi
    fi

    log "Usando arquivo de configuração: $config_file"

    # Exportar variáveis do arquivo de configuração
    # Parse top-level keys for local environment (no .bootstrap_config wrapper)
    while IFS='=' read -r key value; do
        if [[ ! -z "$key" && ! "$key" =~ ^[[:space:]]*# ]]; then
            export "$key=$value"
        fi
    done < <(yq eval 'to_entries | .[] | select(.value | type == "!!str") | .key + "=" + .value' "$config_file")

    # Sanity check: ensure at least some variables were loaded
    if [[ -z "${environment:-}" ]]; then
        log_error "Failed to load configuration from $config_file"
        log_error "Please verify the file format and structure"
        exit 1
    fi

    log_success "Configuração carregada para ambiente: $env"
}

# Função para carregar templates de quota
load_quota_templates() {
    local env="$1"
    local quota_file="${BOOTSTRAP_DIR}/resource-quotas-templates.yaml"
    local limits_file="${BOOTSTRAP_DIR}/limit-ranges-templates.yaml"

    log "Carregando templates de quota para ambiente: $env"

    # Carregar quotas específicas do ambiente
    while IFS='=' read -r key value; do
        if [[ ! -z "$key" && "$key" =~ ^${env}_ ]]; then
            export "$key=$value"
        fi
    done < <(grep "^${env}_" "$quota_file" | sed 's/: /=/')

    # Carregar limits específicos do ambiente
    while IFS='=' read -r key value; do
        if [[ ! -z "$key" && "$key" =~ ^${env}_ ]]; then
            export "$key=$value"
        fi
    done < <(grep "^${env}_" "$limits_file" | sed 's/: /=/')

    log_success "Templates de quota carregados"
}

# Função para substituir placeholders
substitute_placeholders() {
    local input_file="$1"
    local output_file="$2"
    local env="$3"

    log "Substituindo placeholders em: $(basename "$input_file")"

    # Criar diretório temporário se não existir
    mkdir -p "$(dirname "$output_file")"

    # Mapeamento de placeholders para variáveis
    # Use portable approach: write to temp file without -i flag
    local temp_file="${output_file}.tmp"
    local temp_file2="${output_file}.tmp2"
    cp "$input_file" "$temp_file"

    # Portable sed function - writes to new file instead of in-place
    portable_sed() {
        local pattern="$1"
        local input="$2"
        local output="$3"
        sed "$pattern" "$input" > "$output"
        mv "$output" "$input"
    }

    # Substituições específicas por ambiente - prefixar com $ para envsubst
    # Suporta todos os ambientes: dev, staging, prod, local
    portable_sed "s/COGNITION_CPU_REQUESTS_QUOTA/\$${env}_cognition_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_MEMORY_REQUESTS_QUOTA/\$${env}_cognition_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_CPU_LIMITS_QUOTA/\$${env}_cognition_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_MEMORY_LIMITS_QUOTA/\$${env}_cognition_memory_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_PVC_QUOTA/\$${env}_cognition_persistentvolumeclaims/g" "$temp_file" "$temp_file2"

    # Substituições para orchestration
    portable_sed "s/ORCHESTRATION_CPU_REQUESTS_QUOTA/\$${env}_orchestration_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_MEMORY_REQUESTS_QUOTA/\$${env}_orchestration_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_CPU_LIMITS_QUOTA/\$${env}_orchestration_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_MEMORY_LIMITS_QUOTA/\$${env}_orchestration_memory_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_PVC_QUOTA/\$${env}_orchestration_persistentvolumeclaims/g" "$temp_file" "$temp_file2"

    # Substituições para execution
    portable_sed "s/EXECUTION_CPU_REQUESTS_QUOTA/\$${env}_execution_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_MEMORY_REQUESTS_QUOTA/\$${env}_execution_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_CPU_LIMITS_QUOTA/\$${env}_execution_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_MEMORY_LIMITS_QUOTA/\$${env}_execution_memory_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_PVC_QUOTA/\$${env}_execution_persistentvolumeclaims/g" "$temp_file" "$temp_file2"

    # Substituições para observability
    portable_sed "s/OBSERVABILITY_CPU_REQUESTS_QUOTA/\$${env}_observability_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_MEMORY_REQUESTS_QUOTA/\$${env}_observability_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_CPU_LIMITS_QUOTA/\$${env}_observability_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_MEMORY_LIMITS_QUOTA/\$${env}_observability_memory_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_PVC_QUOTA/\$${env}_observability_persistentvolumeclaims/g" "$temp_file" "$temp_file2"

    # Substituições para security
    portable_sed "s/SECURITY_CPU_REQUESTS_QUOTA/\$${env}_security_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/SECURITY_MEMORY_REQUESTS_QUOTA/\$${env}_security_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/SECURITY_CPU_LIMITS_QUOTA/\$${env}_security_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/SECURITY_MEMORY_LIMITS_QUOTA/\$${env}_security_memory_limits/g" "$temp_file" "$temp_file2"

    # Substituições para system/infrastructure
    portable_sed "s/INFRASTRUCTURE_CPU_REQUESTS_QUOTA/\$${env}_system_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/INFRASTRUCTURE_MEMORY_REQUESTS_QUOTA/\$${env}_system_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/INFRASTRUCTURE_CPU_LIMITS_QUOTA/\$${env}_system_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/INFRASTRUCTURE_MEMORY_LIMITS_QUOTA/\$${env}_system_memory_limits/g" "$temp_file" "$temp_file2"

    # Substituições para auth
    portable_sed "s/AUTH_CPU_REQUESTS_QUOTA/\$${env}_auth_cpu_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_MEMORY_REQUESTS_QUOTA/\$${env}_auth_memory_requests/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_CPU_LIMITS_QUOTA/\$${env}_auth_cpu_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_MEMORY_LIMITS_QUOTA/\$${env}_auth_memory_limits/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_PVC_QUOTA/\$${env}_auth_persistentvolumeclaims/g" "$temp_file" "$temp_file2"

    # Substituições para custom resource quotas (CRDs)
    portable_sed "s/APIASSET_QUOTA_PLACEHOLDER/\$${env}_crd_apiassets_quota/g" "$temp_file" "$temp_file2"
    portable_sed "s/DATAASSET_QUOTA_PLACEHOLDER/\$${env}_crd_dataassets_quota/g" "$temp_file" "$temp_file2"
    portable_sed "s/SERVICECONTRACT_QUOTA_PLACEHOLDER/\$${env}_crd_servicecontracts_quota/g" "$temp_file" "$temp_file2"
    portable_sed "s/DATALINEAGE_QUOTA_PLACEHOLDER/\$${env}_crd_datalineages_quota/g" "$temp_file" "$temp_file2"

    # Substituições para LimitRanges
    portable_sed "s/COGNITION_CPU_DEFAULT_LIMIT/\$${env}_cognition_default_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_MEMORY_DEFAULT_LIMIT/\$${env}_cognition_default_limit_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_CPU_DEFAULT_REQUEST/\$${env}_cognition_default_request_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_MEMORY_DEFAULT_REQUEST/\$${env}_cognition_default_request_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_CPU_MAX_LIMIT/\$${env}_cognition_max_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/COGNITION_MEMORY_MAX_LIMIT/\$${env}_cognition_max_limit_memory/g" "$temp_file" "$temp_file2"

    # Repetir para outros workloads...
    portable_sed "s/ORCHESTRATION_CPU_DEFAULT_LIMIT/\$${env}_orchestration_default_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_MEMORY_DEFAULT_LIMIT/\$${env}_orchestration_default_limit_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_CPU_DEFAULT_REQUEST/\$${env}_orchestration_default_request_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_MEMORY_DEFAULT_REQUEST/\$${env}_orchestration_default_request_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_CPU_MAX_LIMIT/\$${env}_orchestration_max_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/ORCHESTRATION_MEMORY_MAX_LIMIT/\$${env}_orchestration_max_limit_memory/g" "$temp_file" "$temp_file2"

    portable_sed "s/EXECUTION_CPU_DEFAULT_LIMIT/\$${env}_execution_default_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_MEMORY_DEFAULT_LIMIT/\$${env}_execution_default_limit_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_CPU_DEFAULT_REQUEST/\$${env}_execution_default_request_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_MEMORY_DEFAULT_REQUEST/\$${env}_execution_default_request_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_CPU_MAX_LIMIT/\$${env}_execution_max_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/EXECUTION_MEMORY_MAX_LIMIT/\$${env}_execution_max_limit_memory/g" "$temp_file" "$temp_file2"

    portable_sed "s/OBSERVABILITY_CPU_DEFAULT_LIMIT/\$${env}_observability_default_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_MEMORY_DEFAULT_LIMIT/\$${env}_observability_default_limit_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_CPU_DEFAULT_REQUEST/\$${env}_observability_default_request_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_MEMORY_DEFAULT_REQUEST/\$${env}_observability_default_request_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_CPU_MAX_LIMIT/\$${env}_observability_max_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/OBSERVABILITY_MEMORY_MAX_LIMIT/\$${env}_observability_max_limit_memory/g" "$temp_file" "$temp_file2"

    portable_sed "s/AUTH_CPU_DEFAULT_LIMIT/\$${env}_auth_default_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_MEMORY_DEFAULT_LIMIT/\$${env}_auth_default_limit_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_CPU_DEFAULT_REQUEST/\$${env}_auth_default_request_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_MEMORY_DEFAULT_REQUEST/\$${env}_auth_default_request_memory/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_CPU_MAX_LIMIT/\$${env}_auth_max_limit_cpu/g" "$temp_file" "$temp_file2"
    portable_sed "s/AUTH_MEMORY_MAX_LIMIT/\$${env}_auth_max_limit_memory/g" "$temp_file" "$temp_file2"

    # Usar envsubst para substituir as variáveis
    envsubst < "$temp_file" > "$output_file"
    rm "$temp_file"

    # Verificar se ainda há placeholders não substituídos
    if grep -q "_PLACEHOLDER\|PLACEHOLDER_" "$output_file"; then
        log_warning "Placeholders não substituídos encontrados em: $(basename "$output_file")"
        grep "_PLACEHOLDER\|PLACEHOLDER_" "$output_file" || true
    fi

    log_success "Placeholders substituídos em: $(basename "$output_file")"
}

# Função para validar variáveis de ambiente necessárias
validate_environment_variables() {
    local env="$1"

    log "Validando variáveis de ambiente para substituição de placeholders..."

    # Lista de variáveis necessárias com prefixo do ambiente
    local required_vars=(
        "${env}_cognition_cpu_requests"
        "${env}_cognition_memory_requests"
        "${env}_cognition_cpu_limits"
        "${env}_cognition_memory_limits"
        "${env}_cognition_persistentvolumeclaims"
        "${env}_orchestration_cpu_requests"
        "${env}_orchestration_memory_requests"
        "${env}_orchestration_cpu_limits"
        "${env}_orchestration_memory_limits"
        "${env}_orchestration_persistentvolumeclaims"
        "${env}_execution_cpu_requests"
        "${env}_execution_memory_requests"
        "${env}_execution_cpu_limits"
        "${env}_execution_memory_limits"
        "${env}_execution_persistentvolumeclaims"
        "${env}_observability_cpu_requests"
        "${env}_observability_memory_requests"
        "${env}_observability_cpu_limits"
        "${env}_observability_memory_limits"
        "${env}_observability_persistentvolumeclaims"
        "${env}_security_cpu_requests"
        "${env}_security_memory_requests"
        "${env}_security_cpu_limits"
        "${env}_security_memory_limits"
        "${env}_system_cpu_requests"
        "${env}_system_memory_requests"
        "${env}_system_cpu_limits"
        "${env}_system_memory_limits"
        "${env}_auth_cpu_requests"
        "${env}_auth_memory_requests"
        "${env}_auth_cpu_limits"
        "${env}_auth_memory_limits"
        "${env}_auth_persistentvolumeclaims"
        "${env}_crd_apiassets_quota"
        "${env}_crd_dataassets_quota"
        "${env}_crd_servicecontracts_quota"
        "${env}_crd_datalineages_quota"
        "${env}_cognition_default_limit_cpu"
        "${env}_cognition_default_limit_memory"
        "${env}_cognition_default_request_cpu"
        "${env}_cognition_default_request_memory"
        "${env}_cognition_max_limit_cpu"
        "${env}_cognition_max_limit_memory"
        "${env}_orchestration_default_limit_cpu"
        "${env}_orchestration_default_limit_memory"
        "${env}_orchestration_default_request_cpu"
        "${env}_orchestration_default_request_memory"
        "${env}_orchestration_max_limit_cpu"
        "${env}_orchestration_max_limit_memory"
        "${env}_execution_default_limit_cpu"
        "${env}_execution_default_limit_memory"
        "${env}_execution_default_request_cpu"
        "${env}_execution_default_request_memory"
        "${env}_execution_max_limit_cpu"
        "${env}_execution_max_limit_memory"
        "${env}_observability_default_limit_cpu"
        "${env}_observability_default_limit_memory"
        "${env}_observability_default_request_cpu"
        "${env}_observability_default_request_memory"
        "${env}_observability_max_limit_cpu"
        "${env}_observability_max_limit_memory"
        "${env}_auth_default_limit_cpu"
        "${env}_auth_default_limit_memory"
        "${env}_auth_default_request_cpu"
        "${env}_auth_default_request_memory"
        "${env}_auth_max_limit_cpu"
        "${env}_auth_max_limit_memory"
    )

    local missing_vars=()
    local var_name

    for var_name in "${required_vars[@]}"; do
        if [[ -z "${!var_name:-}" ]]; then
            missing_vars+=("$var_name")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Variáveis de ambiente ausentes para substituição de placeholders:"
        for var_name in "${missing_vars[@]}"; do
            log_error "  - $var_name"
        done
        log_error ""
        log_error "Verifique se:"
        log_error "  1. O arquivo environments/${env}/bootstrap-config.yaml está correto"
        log_error "  2. Os templates em k8s/bootstrap/*-templates.yaml contêm todas as variáveis ${env}_*"
        log_error "  3. A função load_environment_config() está carregando as variáveis corretamente"
        return 1
    fi

    log_success "Todas as variáveis de ambiente necessárias estão definidas"
    return 0
}

# Função para aplicar manifests em ordem
apply_manifests() {
    local env="$1"

    log "Iniciando aplicação de manifests para ambiente: $env"

    # Ordem de aplicação
    local manifest_order=(
        "namespaces.yaml"
        "data-governance-crds.yaml"
        "rbac.yaml"
        "network-policies.yaml"
        "pod-security-standards.yaml"
    )

    for manifest in "${manifest_order[@]}"; do
        local input_file="${BOOTSTRAP_DIR}/${manifest}"
        local output_file="${TEMP_DIR}/${manifest}"

        if [[ ! -f "$input_file" ]]; then
            log_warning "Manifest não encontrado: $input_file"
            continue
        fi

        # Substituir placeholders
        substitute_placeholders "$input_file" "$output_file" "$env"

        # Aplicar manifest
        if [[ "${DRY_RUN:-}" == "true" ]]; then
            log "DRY RUN: Manifest gerado em: $output_file"
        else
            log "Aplicando: $manifest"
            if kubectl apply -f "$output_file"; then
                log_success "Aplicado com sucesso: $manifest"
            else
                log_error "Falha ao aplicar: $manifest"
                if [[ "${CONTINUE_ON_ERROR:-}" != "true" ]]; then
                    exit 1
                fi
            fi
        fi

        # Aguardar um momento entre aplicações
        sleep 2
    done
}

# Função para verificar health dos recursos
check_resource_health() {
    local env="$1"

    log "Verificando saúde dos recursos aplicados..."

    # Verificar namespaces
    local namespaces=("neural-hive-system" "neural-hive-cognition" "neural-hive-orchestration" "neural-hive-execution" "neural-hive-observability" "cosign-system" "gatekeeper-system" "cert-manager" "auth")

    for ns in "${namespaces[@]}"; do
        if kubectl get namespace "$ns" &> /dev/null; then
            log_success "Namespace existente: $ns"
        else
            log_error "Namespace não encontrado: $ns"
        fi
    done

    # Verificar CRDs
    local crds=("apiassets.catalog.neural-hive.io" "dataassets.catalog.neural-hive.io" "servicecontracts.catalog.neural-hive.io" "datalineages.catalog.neural-hive.io")

    for crd in "${crds[@]}"; do
        if kubectl get crd "$crd" &> /dev/null; then
            log_success "CRD existente: $crd"
        else
            # Downgrade to warning for local environment - CRDs are not part of bootstrap
            if [[ "$env" == "local" ]]; then
                log_warning "CRD não encontrado: $crd (esperado em fases posteriores de deployment)"
            else
                log_error "CRD não encontrado: $crd"
            fi
        fi
    done

    # Verificar ResourceQuotas
    for ns in "${namespaces[@]}"; do
        if kubectl get resourcequota -n "$ns" &> /dev/null; then
            local quota_count
            quota_count=$(kubectl get resourcequota -n "$ns" --no-headers | wc -l)
            log_success "ResourceQuotas em $ns: $quota_count"
        fi
    done

    log_success "Verificação de saúde concluída"
}

# Função para executar validações
run_validations() {
    local validation_dir="${PROJECT_ROOT}/scripts/validation"

    if [[ ! -d "$validation_dir" ]]; then
        log_warning "Diretório de validação não encontrado: $validation_dir"
        return
    fi

    log "Executando validações..."

    # Executar scripts de validação se existirem
    local validation_scripts=(
        "validate-namespace-isolation.sh"
        "validate-data-governance-crds.sh"
        "test-resource-quotas.sh"
    )

    for script in "${validation_scripts[@]}"; do
        local script_path="${validation_dir}/${script}"
        if [[ -f "$script_path" && -x "$script_path" ]]; then
            log "Executando validação: $script"
            if "$script_path"; then
                log_success "Validação passou: $script"
            else
                log_error "Validação falhou: $script"
                if [[ "${CONTINUE_ON_ERROR:-}" != "true" ]]; then
                    exit 1
                fi
            fi
        else
            log_warning "Script de validação não encontrado ou não executável: $script"
        fi
    done
}

# Função para cleanup em caso de falha
cleanup() {
    # Skip cleanup for dry-run mode to preserve artifacts
    if [[ "${DRY_RUN:-}" == "true" ]]; then
        return 0
    fi

    if [[ -d "$TEMP_DIR" ]]; then
        log "Limpando arquivos temporários..."
        rm -rf "$TEMP_DIR"
    fi
}

# Função principal
main() {
    log "Iniciando aplicação de bootstrap manifests do Neural Hive-Mind"

    # Configurar trap para cleanup
    trap cleanup EXIT

    # Verificações iniciais
    check_dependencies
    check_k8s_context

    # Determinar ambiente
    local env
    env=$(determine_environment)
    log "Ambiente determinado: $env"

    # Carregar configurações
    load_environment_config "$env"
    load_quota_templates "$env"

    # Validar variáveis de ambiente para substituição
    if ! validate_environment_variables "$env"; then
        log_error "Validação de variáveis de ambiente falhou"
        exit 1
    fi

    # Validar recursos do Minikube
    validate_minikube_resources "$env"

    # Aplicar manifests
    apply_manifests "$env"

    # Verificar saúde
    check_resource_health "$env"

    # Executar validações
    if [[ "${SKIP_VALIDATIONS:-}" != "true" ]]; then
        run_validations
    fi

    if [[ "${DRY_RUN:-}" == "true" ]]; then
        log_success "Dry run concluído com sucesso!"
        log "Manifests gerados em: $TEMP_DIR"
        log "Revise os arquivos antes de aplicar sem --dry-run"
    else
        log_success "Bootstrap manifests aplicados com sucesso!"
        log "Ambiente: $env"
        log "Próximos passos:"
        log "  1. Verificar se todos os pods estão em execução"
        log "  2. Configurar monitoramento e alertas"
        log "  3. Executar testes de integração"
    fi
}

# Função para validar recursos do Minikube
validate_minikube_resources() {
    local env="$1"

    if [[ "$env" != "local" ]]; then
        return 0
    fi

    local context
    context=$(kubectl config current-context)

    if [[ "$context" != *"minikube"* ]]; then
        return 0
    fi

    log "Validando recursos do Minikube..."

    # Verificar capacidade do node
    local node_name
    node_name=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
    local cpu_capacity
    cpu_capacity=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.capacity.cpu}')
    local memory_capacity
    memory_capacity=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.capacity.memory}')
    local memory_gb
    memory_gb=$(echo "${memory_capacity}" | sed 's/Ki$//' | awk '{print int($1/1024/1024)}')

    log "Recursos do node:"
    log "  CPUs: ${cpu_capacity}"
    log "  Memory: ${memory_gb}GB"

    if [[ ${cpu_capacity} -lt 4 ]]; then
        log_warning "Node tem apenas ${cpu_capacity} CPUs (recomendado: 4+)"
        log_warning "Considere aumentar com: minikube delete && minikube start --cpus=4 --memory=8192"
    fi

    if [[ ${memory_gb} -lt 8 ]]; then
        log_warning "Node tem apenas ${memory_gb}GB de memória (recomendado: 8GB+)"
        log_warning "Considere aumentar com: minikube delete && minikube start --cpus=4 --memory=8192"
    fi

    log_success "Validação de recursos do Minikube concluída"
}

# Função para processar argumentos de linha de comando
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                export DRY_RUN="true"
                shift
                ;;
            --continue-on-error)
                export CONTINUE_ON_ERROR="true"
                shift
                ;;
            --skip-validations)
                export SKIP_VALIDATIONS="true"
                shift
                ;;
            --help)
                cat << EOF
Usage: $0 [OPTIONS]

Aplicar manifests de bootstrap do Kubernetes com substituição de placeholders.

Options:
  --dry-run              Gerar manifests processados sem aplicar
  --continue-on-error    Continuar mesmo se houver erros
  --skip-validations     Pular etapas de validação
  --help                 Exibir esta mensagem

Environment Variables:
  ENVIRONMENT            Ambiente alvo (local, dev, staging, prod)
  FORCE_PROD             Permitir execução em produção sem confirmação

Examples:
  $0                           # Aplicação normal
  $0 --dry-run                 # Apenas gerar manifests
  ENVIRONMENT=local $0         # Forçar ambiente local

EOF
                exit 0
                ;;
            *)
                log_error "Opção desconhecida: $1"
                log_info "Use --help para informações de uso"
                exit 1
                ;;
        esac
    done
}

# Verificar se o script está sendo executado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    parse_args "$@"
    main
fi