#!/bin/bash
# Script de inicialização e configuração do Vault
set -euo pipefail

# Configuração
VAULT_NAMESPACE="vault"
VAULT_POD="vault-0"
TRUST_DOMAIN="neural-hive.local"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verificar pré-requisitos
check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    if ! kubectl get pod -n $VAULT_NAMESPACE $VAULT_POD &> /dev/null; then
        log_error "Pod Vault não encontrado"
        exit 1
    fi

    if ! kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault status &> /dev/null; then
        log_error "Vault está sealed ou não pronto"
        exit 1
    fi

    log_info "Pré-requisitos OK"
}

# Habilitar métodos de autenticação
enable_auth_methods() {
    log_info "Habilitando métodos de autenticação..."

    # Kubernetes auth
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault auth enable kubernetes 2>/dev/null || log_warn "Kubernetes auth já habilitado"
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault write auth/kubernetes/config \
        kubernetes_host="https://kubernetes.default.svc" \
        kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

    # JWT auth for SPIFFE
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault auth enable jwt 2>/dev/null || log_warn "JWT auth já habilitado"

    log_info "Métodos de autenticação configurados"
}

# Habilitar secrets engines
enable_secrets_engines() {
    log_info "Habilitando secrets engines..."

    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault secrets enable -path=secret kv-v2 2>/dev/null || log_warn "KV engine já habilitado"
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault secrets enable database 2>/dev/null || log_warn "Database engine já habilitado"
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault secrets enable pki 2>/dev/null || log_warn "PKI engine já habilitado"
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault secrets tune -max-lease-ttl=87600h pki

    log_info "Secrets engines configurados"
}

# Criar policies
create_policies() {
    log_info "Criando policies..."

    # Orchestrator-dynamic policy
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault policy write orchestrator-dynamic - <<EOF
path "secret/data/orchestrator/*" {
  capabilities = ["read", "list"]
}
path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
EOF

    # Worker-agents policy
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault policy write worker-agents - <<EOF
path "secret/data/worker/*" {
  capabilities = ["read", "list"]
}
path "database/creds/worker" {
  capabilities = ["read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
EOF

    # Service-registry policy
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault policy write service-registry - <<EOF
path "secret/data/service-registry/*" {
  capabilities = ["read", "list"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
EOF

    log_info "Policies criadas"
}

# Criar roles
create_roles() {
    log_info "Criando roles..."

    # Kubernetes auth roles
    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault write auth/kubernetes/role/orchestrator-dynamic \
        bound_service_account_names=orchestrator-dynamic \
        bound_service_account_namespaces=neural-hive-orchestration \
        policies=orchestrator-dynamic \
        ttl=24h

    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault write auth/kubernetes/role/worker-agents \
        bound_service_account_names=worker-agents \
        bound_service_account_namespaces=neural-hive-execution \
        policies=worker-agents \
        ttl=24h

    kubectl exec -n $VAULT_NAMESPACE $VAULT_POD -- vault write auth/kubernetes/role/service-registry \
        bound_service_account_names=service-registry \
        bound_service_account_namespaces=neural-hive-orchestration \
        policies=service-registry \
        ttl=24h

    log_info "Roles criadas"
}

# Execução principal
main() {
    log_info "Iniciando inicialização do Vault..."

    check_prerequisites
    enable_auth_methods
    enable_secrets_engines
    create_policies
    create_roles

    log_info "Inicialização do Vault completa!"
    log_info "Próximos passos:"
    log_info "  1. Armazenar secrets: vault kv put secret/orchestrator/mongodb uri=..."
    log_info "  2. Configurar conexões de database: vault write database/config/..."
    log_info "  3. Criar registration entries SPIRE"
}

main "$@"
