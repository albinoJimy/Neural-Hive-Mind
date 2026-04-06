#!/bin/sh
# Setup Vault para testes E2E
# Configura: KV v2 secrets engine, Kubernetes auth, Database secrets engine, policies

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo "${RED}[ERROR]${NC} $1"
}

# Configurações
VAULT_ADDR=${VAULT_ADDR:-"http://vault.neural-hive.local:8200"}
VAULT_TOKEN=${VAULT_TOKEN:-"e2e-test-root-token"}
export VAULT_ADDR VAULT_TOKEN

log_info "Iniciando setup do Vault para testes E2E..."
log_info "Vault address: $VAULT_ADDR"

# Aguardar Vault estar pronto
log_info "Aguardando Vault estar pronto..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if vault status > /dev/null 2>&1; then
        log_info "Vault está pronto!"
        break
    fi
    attempt=$((attempt + 1))
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    log_error "Vault não ficou pronto após $max_attempts tentativas"
    exit 1
fi

# 1. Habilitar KV v2 secrets engine em orchestrator/
log_info "Habilitando KV v2 secrets engine em orchestrator/"
if vault secrets list | grep -q "^orchestrator/"; then
    log_warn "KV v2 em orchestrator/ já existe"
else
    vault secrets enable -path=orchestrator kv-v2
    log_info "KV v2 habilitado em orchestrator/"
fi

# 2. Escrever secrets estáticos de teste
log_info "Escrevendo secrets estáticos de teste..."
vault kv put orchestrator/mongodb \
    uri="mongodb://test_user:test_pass@mongodb.neural-hive.local:27017/temporal" \
    tls_ca="" \
    tls_cert_key=""

vault kv put orchestrator/redis \
    password="test_redis_password" \
    mode="standalone"

vault kv put orchestrator/kafka \
    username="test_kafka_user" \
    password="test_kafka_password" \
    mechanism="SCRAM-SHA-512"

log_info "Secrets estáticos criados"

# 3. Habilitar Kubernetes auth method
log_info "Habilitando Kubernetes auth method..."
if vault auth list | grep -q "^kubernetes/"; then
    log_warn "Kubernetes auth method já existe"
else
    vault auth enable kubernetes
    log_info "Kubernetes auth method habilitado"
fi

# Configurar Kubernetes auth (simulado para testes locais)
log_info "Configurando Kubernetes auth..."
vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443" \
    token_reviewer_jwt="" \
    kubernetes_ca_cert="" \
    disable_iss_validation=true || log_warn "Configuração Kubernetes auth pode falhar fora do cluster"

# Criar role para orchestrator
log_info "Criando role orchestrator..."
vault write auth/kubernetes/role/orchestrator \
    bound_service_account_names="orchestrator-dynamic" \
    bound_service_account_namespaces="neural-hive" \
    policies=orchestrator \
    ttl=1h

# 4. Habilitar Database secrets engine para PostgreSQL
log_info "Habilitando Database secrets engine..."
if vault secrets list | grep -q "^database/"; then
    log_warn "Database secrets engine já existe"
else
    vault secrets enable database
    log_info "Database secrets engine habilitado"
fi

# Configurar conexão PostgreSQL
log_info "Configurando conexão PostgreSQL..."
vault write database/config/postgres-orchestrator \
    plugin_name="postgresql-database-plugin" \
    connection_url="postgresql://{{username}}:{{password}}@postgres.neural-hive.local:5432/temporal?sslmode=disable" \
    allowed_roles="temporal-orchestrator" \
    username="temporal_admin" \
    password="admin_password_change_me"

# Criar role temporal-orchestrator com credenciais dinâmicas
log_info "Criando role temporal-orchestrator..."
vault write database/roles/temporal-orchestrator \
    db_name="postgres-orchestrator" \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON DATABASE temporal TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="4h"

# Criar role mongodb-orchestrator (simulado - usa PostgreSQL backend)
log_info "Criando role mongodb-orchestrator..."
vault write database/roles/mongodb-orchestrator \
    db_name="postgres-orchestrator" \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON DATABASE temporal TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="4h"

# 5. Criar policies
log_info "Criando policies..."

# Policy orchestrator (leitura e escrita)
vault policy write orchestrator - <<EOF
# Permite ler e escrever secrets estáticos
path "orchestrator/data/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "orchestrator/metadata/*" {
  capabilities = ["list"]
}

# Permite gerar credenciais dinâmicas
path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}

path "database/creds/mongodb-orchestrator" {
  capabilities = ["read"]
}

# Permite renovar leases
path "sys/renew/*" {
  capabilities = ["update"]
}

# Permite verificar próprio token
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

# Policy readonly (apenas leitura)
vault policy write readonly - <<EOF
# Apenas leitura de secrets estáticos
path "orchestrator/data/*" {
  capabilities = ["read", "list"]
}

path "orchestrator/metadata/*" {
  capabilities = ["list"]
}

# Apenas leitura de credenciais dinâmicas
path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}

path "database/creds/mongodb-orchestrator" {
  capabilities = ["read"]
}

# Verificar próprio token
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

log_info "Policies criadas: orchestrator, readonly"

# 6. Habilitar PKI secrets engine (opcional, para testes de certificados)
log_info "Habilitando PKI secrets engine..."
if vault secrets list | grep -q "^pki/"; then
    log_warn "PKI secrets engine já existe"
else
    vault secrets enable -path=pki pki
    log_info "PKI secrets engine habilitado"
fi

# Configurar CA interna para testes
log_info "Configurando CA PKI para testes..."
vault write pki/root/generate/internal \
    common_name="Neural Hive Internal CA" \
    ttl=8760h \
    organization="Neural Hive" \
    ou="Engineering"

vault write pki/config/urls \
    issuing_certificates="http://vault.neural-hive.local:8200/v1/pki/ca" \
    crl_distribution_points="http://vault.neural-hive.local:8200/v1/pki/crl"

# Criar role para emissão de certificados
vault write pki/roles/orchestrator \
    allowed_domains="neural-hive.local" \
    allow_subdomains=true \
    max_ttl=720h

log_info "PKI configurado com CA interna e role orchestrator"

# 7. Habilitar JWT auth method para autenticação SPIFFE
log_info "Habilitando JWT auth method..."
if vault auth list | grep -q "^jwt/"; then
    log_warn "JWT auth method já existe"
else
    vault auth enable jwt
    log_info "JWT auth method habilitado"
fi

# Configurar JWT auth para SPIFFE
log_info "Configurando JWT auth para SPIFFE..."
vault write auth/jwt/config \
    bound_issuer="spiffe://neural-hive.local" \
    jwks_url="http://spire-server.neural-hive.local:8081/oidc/discovery/jwks"

# Criar role para autenticação via SPIFFE JWT
vault write auth/jwt/role/spiffe-role \
    role_type="jwt" \
    user_claim="sub" \
    bound_audiences="vault.neural-hive.local" \
    policies="orchestrator" \
    ttl=1h

# 8. Verificação final
log_info "=========================================="
log_info "Setup do Vault concluído com sucesso!"
log_info "=========================================="
log_info "Secrets engines disponíveis:"
vault secrets list
log_info ""
log_info "Auth methods disponíveis:"
vault auth list
log_info ""
log_info "Policies disponíveis:"
vault policy list
log_info ""
log_info "Teste de leitura de secret:"
vault kv get orchestrator/mongodb
log_info ""
log_info "Para executar testes E2E:"
log_info "  RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_vault_spiffe_e2e.py -v"
