#!/usr/bin/env bash
# Script de configuração de políticas Vault para serviços Neural Hive-Mind
# Cria policies e configura Kubernetes auth para orchestrator, workers e service-registry

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Funções de logging
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificações preliminares
if ! command -v vault &> /dev/null; then
    log_error "Vault CLI não encontrado"
    exit 1
fi

if ! vault token lookup &> /dev/null; then
    log_error "Não autenticado no Vault. Execute: vault login"
    exit 1
fi

# Diretório temporário para policies
POLICY_DIR=$(mktemp -d)
trap "rm -rf $POLICY_DIR" EXIT

log_info "Configurando políticas Vault para Neural Hive-Mind..."

# ==================== ORCHESTRATOR DYNAMIC POLICY ====================
log_info "Criando policy para orchestrator-dynamic..."

cat > "$POLICY_DIR/orchestrator-dynamic-policy.hcl" <<'EOF'
# Policy para Orchestrator Dynamic Service

# Acesso a secrets estáticos do orchestrator
path "secret/data/orchestrator/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/orchestrator/*" {
  capabilities = ["list"]
}

# Acesso a credenciais MongoDB
path "secret/data/mongodb/*" {
  capabilities = ["read"]
}

# Acesso a credenciais Kafka
path "secret/data/kafka/*" {
  capabilities = ["read"]
}

# Acesso a credenciais Redis
path "secret/data/redis/*" {
  capabilities = ["read"]
}

# Acesso a credenciais PostgreSQL dinâmicas (Temporal)
path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}

# Renovação de lease de credenciais dinâmicas
path "sys/leases/renew" {
  capabilities = ["update"]
}

path "sys/leases/revoke" {
  capabilities = ["update"]
}

# Acesso ao PKI para emissão de certificados (se habilitado)
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}
EOF

vault policy write orchestrator-dynamic-policy "$POLICY_DIR/orchestrator-dynamic-policy.hcl"
log_info "Policy 'orchestrator-dynamic-policy' criada"

# ==================== WORKER AGENTS POLICY ====================
log_info "Criando policy para worker-agents..."

cat > "$POLICY_DIR/worker-agents-policy.hcl" <<'EOF'
# Policy para Worker Agents

# Acesso a secrets de workers
path "secret/data/worker/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/worker/*" {
  capabilities = ["list"]
}

# Acesso a credenciais Kafka (consumir tickets)
path "secret/data/kafka/*" {
  capabilities = ["read"]
}

# Acesso a credenciais de execução
path "secret/data/execution/*" {
  capabilities = ["read"]
}

# PKI para mTLS entre workers
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}
EOF

vault policy write worker-agents-policy "$POLICY_DIR/worker-agents-policy.hcl"
log_info "Policy 'worker-agents-policy' criada"

# ==================== SERVICE REGISTRY POLICY ====================
log_info "Criando policy para service-registry..."

cat > "$POLICY_DIR/service-registry-policy.hcl" <<'EOF'
# Policy para Service Registry

# Acesso a secrets do registry
path "secret/data/registry/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/registry/*" {
  capabilities = ["list"]
}

# Acesso a credenciais Redis (cache de registros)
path "secret/data/redis/*" {
  capabilities = ["read"]
}

# PKI para validação de certificados
path "pki/cert/ca" {
  capabilities = ["read"]
}

path "pki/cert/*" {
  capabilities = ["read"]
}
EOF

vault policy write service-registry-policy "$POLICY_DIR/service-registry-policy.hcl"
log_info "Policy 'service-registry-policy' criada"

# ==================== KUBERNETES AUTH CONFIGURATION ====================
log_info "Configurando Kubernetes auth method..."

# Habilitar Kubernetes auth se não estiver habilitado
if vault auth list | grep -q "^kubernetes/"; then
    log_warn "Kubernetes auth já habilitado, atualizando configuração..."
else
    vault auth enable kubernetes
    log_info "Kubernetes auth habilitado"
fi

# Configurar Kubernetes auth
# Nota: Assumindo que o script roda dentro de um pod com service account apropriado
log_info "Configurando Kubernetes auth..."

KUBERNETES_HOST="${KUBERNETES_SERVICE_HOST:-https://kubernetes.default.svc}"
KUBERNETES_PORT="${KUBERNETES_SERVICE_PORT:-443}"

vault write auth/kubernetes/config \
    kubernetes_host="https://${KUBERNETES_HOST}:${KUBERNETES_PORT}" \
    kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
    disable_local_ca_jwt=false || {
        log_warn "Falha ao configurar Kubernetes auth (pode precisar de configuração manual)"
    }

# ==================== KUBERNETES ROLES ====================
log_info "Criando Kubernetes auth roles..."

# Role para orchestrator-dynamic
vault write auth/kubernetes/role/orchestrator-dynamic \
    bound_service_account_names=orchestrator-dynamic \
    bound_service_account_namespaces=neural-hive-orchestration \
    policies=default,orchestrator-dynamic-policy,pki-issue \
    ttl=1h \
    max_ttl=24h

log_info "Role 'orchestrator-dynamic' criado"

# Role para worker-agents
vault write auth/kubernetes/role/worker-agents \
    bound_service_account_names=worker-agents \
    bound_service_account_namespaces=neural-hive-execution \
    policies=default,worker-agents-policy,pki-issue \
    ttl=1h \
    max_ttl=24h

log_info "Role 'worker-agents' criado"

# Role para service-registry
vault write auth/kubernetes/role/service-registry \
    bound_service_account_names=service-registry \
    bound_service_account_namespaces=neural-hive-core \
    policies=default,service-registry-policy \
    ttl=1h \
    max_ttl=24h

log_info "Role 'service-registry' criado"

# ==================== DATABASE SECRETS ENGINE ====================
log_info "Configurando Database secrets engine para PostgreSQL..."

# Habilitar database secrets engine se não estiver habilitado
if vault secrets list | grep -q "^database/"; then
    log_warn "Database secrets engine já habilitado"
else
    vault secrets enable database
    log_info "Database secrets engine habilitado"
fi

PG_HOST=${POSTGRES_HOST:-temporal-postgresql.temporal.svc.cluster.local}
PG_PORT=${POSTGRES_PORT:-5432}
PG_DB=${POSTGRES_DB:-temporal}
PG_USER=${POSTGRES_USER:-vault}
PG_PASSWORD=${POSTGRES_PASSWORD:-vault-password}

log_info "Configurando conexão PostgreSQL para geração de credenciais dinâmicas..."
vault write database/config/temporal-db \
    plugin_name=postgresql-database-plugin \
    allowed_roles="temporal-orchestrator" \
    connection_url="postgresql://{{username}}:{{password}}@${PG_HOST}:${PG_PORT}/${PG_DB}?sslmode=require" \
    username="${PG_USER}" \
    password="${PG_PASSWORD}"

log_info "Criando role dinâmica 'temporal-orchestrator'..."
vault write database/roles/temporal-orchestrator \
    db_name=temporal-db \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT CONNECT ON DATABASE ${PG_DB} TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"

# ==================== VERIFICATION ====================
log_info "Verificando configuração..."

log_info "Policies criadas:"
vault policy list | grep -E "(orchestrator-dynamic|worker-agents|service-registry|pki-issue)"

log_info "Kubernetes roles criados:"
vault list auth/kubernetes/role || log_warn "Erro ao listar roles"

log_info "Testando geração de credenciais PostgreSQL (temporal-orchestrator)..."
if ! vault read database/creds/temporal-orchestrator; then
    log_warn "Falha ao gerar credenciais dinâmicas - verifique conexão PostgreSQL e permissões"
fi

log_info "Configuração concluída com sucesso!"
log_info ""
log_info "Próximos passos:"
log_info "  1. Crie secrets estáticos em secret/orchestrator/*, secret/worker/*, etc."
log_info "  2. Teste autenticação de um pod:"
log_info "     kubectl exec -it <pod> -- vault login -method=kubernetes role=orchestrator-dynamic"
