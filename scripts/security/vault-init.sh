#!/bin/bash
# Vault Initialization Script for Neural Hive-Mind
#
# This script initializes HashiCorp Vault with:
# - Kubernetes authentication
# - KV secrets engine
# - PKI certificate issuance
# - Database credentials engine
#
# Usage: ./scripts/security/vault-init.sh [namespace]
#   namespace: Kubernetes namespace where Vault is deployed (default: vault)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
VAULT_NAMESPACE="${1:-vault}"
VAULT_POD_NAME="vault-0"
VAULT_PORT="8200"
VAULT_ADDR="http://localhost:${VAULT_PORT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Vault is ready
check_vault_ready() {
    log_info "Verificando se Vault está pronto..."

    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault status > /dev/null 2>&1; then
            log_info "Vault está rodando"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    log_error "Vault não está pronto após ${max_attempts} tentativas"
    return 1
}

# Check if Vault is initialized
check_vault_initialized() {
    log_info "Verificando se Vault está inicializado..."

    if kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault status -format=json 2>/dev/null | jq -e '.initialized' | grep -q true; then
        log_info "Vault já está inicializado"
        return 0
    else
        log_info "Vault não está inicializado"
        return 1
    fi
}

# Initialize Vault
initialize_vault() {
    log_info "Inicializando Vault..."

    local init_output
    init_output=$(kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault operator init -format=json -key-shares=1 -key-threshold=1)

    # Save unseal key and root token
    echo "$init_output" | jq -r '.unseal_keys_b64[0]' > "$PROJECT_ROOT/.vault-unseal-key"
    echo "$init_output" | jq -r '.root_token' > "$PROJECT_ROOT/.vault-root-token"

    chmod 600 "$PROJECT_ROOT/.vault-unseal-key" "$PROJECT_ROOT/.vault-root-token"

    log_info "Vault inicializado. Chaves salvas em:"
    log_info "  - $PROJECT_ROOT/.vault-unseal-key"
    log_info "  - $PROJECT_ROOT/.vault-root-token"
}

# Unseal Vault
unseal_vault() {
    log_info "Desbloqueando (unseal) Vault..."

    local unseal_key
    unseal_key=$(cat "$PROJECT_ROOT/.vault-unseal-key")

    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault operator unseal "$unseal_key" > /dev/null

    log_info "Vault desbloqueado"
}

# Login to Vault
vault_login() {
    log_info "Fazendo login no Vault..."

    local root_token
    root_token=$(cat "$PROJECT_ROOT/.vault-root-token")

    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault login "$root_token" > /dev/null

    log_info "Login realizado"
}

# Enable Kubernetes auth
enable_kubernetes_auth() {
    log_info "Configurando autenticação Kubernetes..."

    # Enable Kubernetes auth method
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault auth enable kubernetes 2>/dev/null || log_warn "Auth method kubernetes já existe"

    # Configure Kubernetes auth
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault write auth/kubernetes/config \
        kubernetes_host="https://kubernetes.default.svc:443" \
        kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
        token_reviewer_jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token \
        issuer="https://kubernetes.default.svc.cluster.local" \
        disable_iss_validation=true

    log_info "Autenticação Kubernetes configurada"
}

# Create service account roles
create_service_roles() {
    log_info "Criando roles para serviços..."

    local services=(
        "gateway-intencoes"
        "semantic-translation-engine"
        "consensus-engine"
        "orchestrator-dynamic"
        "approval-service"
        "queen-agent"
        "worker-agents"
    )

    for service in "${services[@]}"; do
        kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault write auth/kubernetes/role/"$service" \
            bound_service_account_names="$service" \
            bound_service_account_namespaces="neural-hive-system" \
            policies="$service-policy" \
            ttl="24h" 2>/dev/null || log_warn "Role $service já existe"
    done

    log_info "Roles de serviços criados"
}

# Enable secrets engines
enable_secrets_engines() {
    log_info "Habilitando engines de segredos..."

    # Enable KV v2
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault secrets enable -path=secret kv-v2 2>/dev/null || log_warn "KV v2 já habilitado"

    # Enable PKI
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault secrets enable -path=pki pki 2>/dev/null || log_warn "PKI já habilitado"

    # Configure PKI
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault secrets tune -max-lease-ttl=720h pki 2>/dev/null

    # Generate root CA
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault write -field=certificate pki/root/generate/internal \
        common_name="Neural Hive-Mind Root CA" \
        ttl="87600h" \
        exclude_cn_from_sans=true 2>/dev/null || log_warn "CA PKI já gerada"

    # Configure PKI roles
    kubectl exec -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault write pki/roles/neural-hive \
        allowed_domains="neural-hive.local,*.neural-hive.local" \
        allow_subdomains=true \
        max_ttl="720h" 2>/dev/null || log_warn "Role PKI já existe"

    log_info "Engines de segredos habilitados"
}

# Create policies
create_policies() {
    log_info "Criando políticas de acesso..."

    # Gateway policy
    local gateway_policy='
path "secret/data/gateway-intencoes/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "pki/issue/gateway-intencoes" {
  capabilities = ["create", "update"]
}
path "database/creds/gateway-intencoes-*" {
  capabilities = ["create", "read"]
}
'

    kubectl exec -i -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault policy write gateway-intencoes-policy - <<< "$gateway_policy" 2>/dev/null || log_warn "Policy gateway-intencoes já existe"

    # Default policy for all services
    local default_policy='
path "secret/data/*" {
  capabilities = ["read", "list"]
}
path "pki/issue/*" {
  capabilities = ["create"]
}
'

    kubectl exec -i -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" -- vault policy write default-policy - <<< "$default_policy" 2>/dev/null || log_warn "Policy default já existe"

    log_info "Políticas criadas"
}

# Main execution
main() {
    log_info "=== Inicialização do Vault para Neural Hive-Mind ==="
    log_info "Namespace: $VAULT_NAMESPACE"

    # Check prerequisites
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_error "jq não encontrado. Instale com: sudo apt-get install jq"
        exit 1
    fi

    # Check if Vault pod exists
    if ! kubectl get pod -n "$VAULT_NAMESPACE" "$VAULT_POD_NAME" &> /dev/null; then
        log_error "Pod $VAULT_POD_NAME não encontrado no namespace $VAULT_NAMESPACE"
        log_error "Certifique-se de que o Vault está instalado: helm install vault helm-charts/vault"
        exit 1
    fi

    # Initialize Vault
    check_vault_ready || exit 1

    if ! check_vault_initialized; then
        initialize_vault
    fi

    unseal_vault
    vault_login
    enable_kubernetes_auth
    create_service_roles
    enable_secrets_engines
    create_policies

    log_info "=== Vault inicializado com sucesso ==="
    log_info "Para acessar o Vault:"
    log_info "  export VAULT_ADDR=http://vault.vault.svc.cluster.local:8200"
    log_info "  export VAULT_TOKEN=$(cat $PROJECT_ROOT/.vault-root-token)"
    log_info ""
    log_info "Para configurar SPIFFE, execute: ./scripts/security/spire-init.sh"
}

# Run main
main "$@"
