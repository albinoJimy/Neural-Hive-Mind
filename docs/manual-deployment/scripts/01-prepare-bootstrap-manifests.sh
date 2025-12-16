#!/bin/bash
# Script auxiliar para preparar manifests de bootstrap manualmente
# Uso: ./01-prepare-bootstrap-manifests.sh

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
BOOTSTRAP_DIR="${PROJECT_ROOT}/k8s/bootstrap"
ENV_DIR="${PROJECT_ROOT}/environments/local"
TEMP_DIR="${PROJECT_ROOT}/.tmp/bootstrap-manual"

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

replace_placeholders() {
  local file="$1"
  shift
  while [[ $# -gt 0 ]]; do
    local placeholder="$1"
    local value="$2"
    shift 2
    # Escapar barras para o sed
    local safe_value="${value//\//\\/}"
    sed -i "s/${placeholder}/${safe_value}/g" "$file"
  done
}

# Verificar dependências
log "Verificando dependências..."
for cmd in kubectl yq envsubst; do
  if ! command -v $cmd &> /dev/null; then
    log_error "Comando não encontrado: $cmd"
    exit 1
  fi
done
log_success "Dependências OK"

# Verificar cluster
VERIFY_CLUSTER_CONNECTIVITY="${VERIFY_CLUSTER_CONNECTIVITY:-false}"
if [[ "${VERIFY_CLUSTER_CONNECTIVITY}" == "true" ]]; then
  log "Verificando conectividade com cluster..."
  if ! kubectl cluster-info &> /dev/null; then
    log_error "Não foi possível conectar ao cluster Kubernetes"
    exit 1
  fi
  CONTEXT=$(kubectl config current-context)
  log_success "Conectado ao cluster: $CONTEXT"
else
  log_warning "Pulando verificação de conectividade com cluster (defina VERIFY_CLUSTER_CONNECTIVITY=true para habilitar)."
fi

# Criar diretório temporário
log "Criando diretório temporário: $TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Carregar variáveis de ambiente
log "Carregando variáveis de ambiente de: $ENV_DIR/bootstrap-config.yaml"
eval $(yq eval 'to_entries | .[] | select(.value | type == "!!str") | "export " + .key + "=\"" + .value + "\""' "$ENV_DIR/bootstrap-config.yaml")

# Validar que variáveis foram carregadas
if [[ -z "${local_cognition_cpu_requests:-}" ]]; then
  log_error "Falha ao carregar variáveis de ambiente"
  exit 1
fi
log_success "Variáveis de ambiente carregadas"

# Processar namespaces.yaml
log "Processando namespaces.yaml..."
cp "$BOOTSTRAP_DIR/namespaces.yaml" "$TEMP_DIR/namespaces.yaml.tmp"

replace_placeholders "$TEMP_DIR/namespaces.yaml.tmp" \
  COGNITION_CPU_REQUESTS_QUOTA "$local_cognition_cpu_requests" \
  COGNITION_MEMORY_REQUESTS_QUOTA "$local_cognition_memory_requests" \
  COGNITION_CPU_LIMITS_QUOTA "$local_cognition_cpu_limits" \
  COGNITION_MEMORY_LIMITS_QUOTA "$local_cognition_memory_limits" \
  COGNITION_PVC_QUOTA "$local_cognition_persistentvolumeclaims" \
  ORCHESTRATION_CPU_REQUESTS_QUOTA "$local_orchestration_cpu_requests" \
  ORCHESTRATION_MEMORY_REQUESTS_QUOTA "$local_orchestration_memory_requests" \
  ORCHESTRATION_CPU_LIMITS_QUOTA "$local_orchestration_cpu_limits" \
  ORCHESTRATION_MEMORY_LIMITS_QUOTA "$local_orchestration_memory_limits" \
  ORCHESTRATION_PVC_QUOTA "$local_orchestration_persistentvolumeclaims" \
  EXECUTION_CPU_REQUESTS_QUOTA "$local_execution_cpu_requests" \
  EXECUTION_MEMORY_REQUESTS_QUOTA "$local_execution_memory_requests" \
  EXECUTION_CPU_LIMITS_QUOTA "$local_execution_cpu_limits" \
  EXECUTION_MEMORY_LIMITS_QUOTA "$local_execution_memory_limits" \
  EXECUTION_PVC_QUOTA "$local_execution_persistentvolumeclaims" \
  OBSERVABILITY_CPU_REQUESTS_QUOTA "$local_observability_cpu_requests" \
  OBSERVABILITY_MEMORY_REQUESTS_QUOTA "$local_observability_memory_requests" \
  OBSERVABILITY_CPU_LIMITS_QUOTA "$local_observability_cpu_limits" \
  OBSERVABILITY_MEMORY_LIMITS_QUOTA "$local_observability_memory_limits" \
  OBSERVABILITY_PVC_QUOTA "$local_observability_persistentvolumeclaims" \
  APIASSET_QUOTA_PLACEHOLDER "$local_crd_apiassets_quota" \
  DATAASSET_QUOTA_PLACEHOLDER "$local_crd_dataassets_quota" \
  SERVICECONTRACT_QUOTA_PLACEHOLDER "$local_crd_servicecontracts_quota" \
  DATALINEAGE_QUOTA_PLACEHOLDER "$local_crd_datalineages_quota" \
  SECURITY_CPU_REQUESTS_QUOTA "$local_security_cpu_requests" \
  SECURITY_MEMORY_REQUESTS_QUOTA "$local_security_memory_requests" \
  SECURITY_CPU_LIMITS_QUOTA "$local_security_cpu_limits" \
  SECURITY_MEMORY_LIMITS_QUOTA "$local_security_memory_limits" \
  INFRASTRUCTURE_CPU_REQUESTS_QUOTA "$local_certmanager_cpu_requests" \
  INFRASTRUCTURE_MEMORY_REQUESTS_QUOTA "$local_certmanager_memory_requests" \
  INFRASTRUCTURE_CPU_LIMITS_QUOTA "$local_certmanager_cpu_limits" \
  INFRASTRUCTURE_MEMORY_LIMITS_QUOTA "$local_certmanager_memory_limits" \
  AUTH_CPU_REQUESTS_QUOTA "$local_auth_cpu_requests" \
  AUTH_MEMORY_REQUESTS_QUOTA "$local_auth_memory_requests" \
  AUTH_CPU_LIMITS_QUOTA "$local_auth_cpu_limits" \
  AUTH_MEMORY_LIMITS_QUOTA "$local_auth_memory_limits" \
  AUTH_PVC_QUOTA "$local_auth_persistentvolumeclaims" \
  COGNITION_CPU_DEFAULT_LIMIT "$local_cognition_default_limit_cpu" \
  COGNITION_MEMORY_DEFAULT_LIMIT "$local_cognition_default_limit_memory" \
  COGNITION_CPU_DEFAULT_REQUEST "$local_cognition_default_request_cpu" \
  COGNITION_MEMORY_DEFAULT_REQUEST "$local_cognition_default_request_memory" \
  COGNITION_CPU_MAX_LIMIT "$local_cognition_max_limit_cpu" \
  COGNITION_MEMORY_MAX_LIMIT "$local_cognition_max_limit_memory" \
  ORCHESTRATION_CPU_DEFAULT_LIMIT "$local_orchestration_default_limit_cpu" \
  ORCHESTRATION_MEMORY_DEFAULT_LIMIT "$local_orchestration_default_limit_memory" \
  ORCHESTRATION_CPU_DEFAULT_REQUEST "$local_orchestration_default_request_cpu" \
  ORCHESTRATION_MEMORY_DEFAULT_REQUEST "$local_orchestration_default_request_memory" \
  ORCHESTRATION_CPU_MAX_LIMIT "$local_orchestration_max_limit_cpu" \
  ORCHESTRATION_MEMORY_MAX_LIMIT "$local_orchestration_max_limit_memory" \
  EXECUTION_CPU_DEFAULT_LIMIT "$local_execution_default_limit_cpu" \
  EXECUTION_MEMORY_DEFAULT_LIMIT "$local_execution_default_limit_memory" \
  EXECUTION_CPU_DEFAULT_REQUEST "$local_execution_default_request_cpu" \
  EXECUTION_MEMORY_DEFAULT_REQUEST "$local_execution_default_request_memory" \
  EXECUTION_CPU_MAX_LIMIT "$local_execution_max_limit_cpu" \
  EXECUTION_MEMORY_MAX_LIMIT "$local_execution_max_limit_memory" \
  OBSERVABILITY_CPU_DEFAULT_LIMIT "$local_observability_default_limit_cpu" \
  OBSERVABILITY_MEMORY_DEFAULT_LIMIT "$local_observability_default_limit_memory" \
  OBSERVABILITY_CPU_DEFAULT_REQUEST "$local_observability_default_request_cpu" \
  OBSERVABILITY_MEMORY_DEFAULT_REQUEST "$local_observability_default_request_memory" \
  OBSERVABILITY_CPU_MAX_LIMIT "$local_observability_max_limit_cpu" \
  OBSERVABILITY_MEMORY_MAX_LIMIT "$local_observability_max_limit_memory" \
  AUTH_CPU_DEFAULT_LIMIT "$local_auth_default_limit_cpu" \
  AUTH_MEMORY_DEFAULT_LIMIT "$local_auth_default_limit_memory" \
  AUTH_CPU_DEFAULT_REQUEST "$local_auth_default_request_cpu" \
  AUTH_MEMORY_DEFAULT_REQUEST "$local_auth_default_request_memory" \
  AUTH_CPU_MAX_LIMIT "$local_auth_max_limit_cpu" \
  AUTH_MEMORY_MAX_LIMIT "$local_auth_max_limit_memory"

# Expandir variáveis com envsubst
envsubst < "$TEMP_DIR/namespaces.yaml.tmp" > "$TEMP_DIR/namespaces.yaml"
rm "$TEMP_DIR/namespaces.yaml.tmp"

# Validar que não há placeholders restantes
if grep -qE '_QUOTA|_LIMIT|_REQUEST|PLACEHOLDER' "$TEMP_DIR/namespaces.yaml"; then
  log_warning "Placeholders não substituídos encontrados em namespaces.yaml"
  grep -E '_QUOTA|_LIMIT|_REQUEST|PLACEHOLDER' "$TEMP_DIR/namespaces.yaml"
else
  log_success "namespaces.yaml processado com sucesso"
fi

# Copiar arquivos sem placeholders
log "Copiando arquivos sem placeholders..."
cp "$BOOTSTRAP_DIR/rbac.yaml" "$TEMP_DIR/rbac.yaml"
cp "$BOOTSTRAP_DIR/network-policies.yaml" "$TEMP_DIR/network-policies.yaml"
cp "$BOOTSTRAP_DIR/pod-security-standards.yaml" "$TEMP_DIR/pod-security-standards.yaml"
cp "$BOOTSTRAP_DIR/data-governance-crds.yaml" "$TEMP_DIR/data-governance-crds.yaml"
log_success "Arquivos copiados"

# Resumo
log_success "Manifests preparados em: $TEMP_DIR"
echo ""
echo "Próximos passos:"
echo "1. Revisar os manifests gerados em: $TEMP_DIR"
echo "2. Aplicar na ordem:"
echo "   kubectl apply -f $TEMP_DIR/namespaces.yaml"
echo "   kubectl apply -f $TEMP_DIR/data-governance-crds.yaml"
echo "   kubectl apply -f $TEMP_DIR/rbac.yaml"
echo "   kubectl apply -f $TEMP_DIR/network-policies.yaml"
echo "   kubectl apply -f $TEMP_DIR/pod-security-standards.yaml"
echo "3. Validar com: kubectl get namespaces,crds,serviceaccounts,networkpolicies --all-namespaces"
