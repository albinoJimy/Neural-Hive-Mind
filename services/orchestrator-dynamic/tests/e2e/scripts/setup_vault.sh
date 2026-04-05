#!/bin/sh
set -e

echo "=== Setup Vault para Testes E2E ==="

# Aguardar Vault estar pronto
echo "Aguardando Vault..."
until curl -s http://localhost:8200/v1/sys/health > /dev/null 2>&1; do
    echo "Vault não está pronto ainda..."
    sleep 2
done
echo "Vault está pronto!"

# Exportar token
export VAULT_TOKEN='dev-root-token'
export VAULT_ADDR='http://127.0.0.1:8200'

echo ""
echo "=== 1. Habilitar Kubernetes Auth (simulado) ==="
vault auth enable kubernetes 2>/dev/null || echo "Kubernetes auth já habilitado"

# Configurar Kubernetes auth (mock para testes locais)
vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443" \
    kubernetes_ca_cert="@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt" \
    token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token 2>/dev/null || echo 'mock_jwt')" || true

vault write auth/kubernetes/role/orchestrator \
    bound_service_account_names=orchestrator \
    bound_service_account_namespaces=default \
    policies=orchestrator-policy \
    ttl=1h

echo ""
echo "=== 2. Habilitar JWT Auth para SPIFFE ==="
vault auth enable jwt 2>/dev/null || echo "JWT auth já habilitado"

vault write auth/jwt/config \
    default_lease_ttl=3600 \
    max_lease_ttl=7200

# Configurar role para SPIFFE JWT-SVID
vault write auth/jwt/role/orchestrator \
    role_type=jwt \
    bound_audiences=vault.neural-hive.local \
    user_claim=sub \
    policies=orchestrator-policy \
    ttl=1h

echo ""
echo "=== 3. Habilitar Secrets Engines ==="

# KV v2 secrets
vault secrets enable -path=secret kv-v2 2>/dev/null || echo "KV v2 já habilitado"

# Database secrets engine para PostgreSQL dynamic credentials
vault secrets enable database 2>/dev/null || echo "Database já habilitado"

# PKI para certificados
vault secrets enable pki 2>/dev/null || echo "PKI já habilitado"

echo ""
echo "=== 4. Configurar Database Secrets Engine (PostgreSQL) ==="
vault write database/config/postgresql-test \
    plugin_name=postgresql-database-plugin \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/test_db?sslmode=disable" \
    allowed_roles="temporal-orchestrator" \
    username="postgres" \
    password="postgres"

vault write database/roles/temporal-orchestrator \
    db_name=postgresql-test \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"

echo ""
echo "=== 5. Configurar PKI Engine ==="
# Configurar CA
vault write -field=certificate pki/root/generate/internal \
    common_name="neural-hive.local" \
    ttl=87600h > /tmp/ca_cert.pem

# Publicar URLs de CRL e cert
vault write pki/config/urls \
    issuing_certificates="http://vault:8200/v1/pki/ca" \
    crl_distribution_points="http://vault:8200/v1/pki/crl"

# Criar role para emissão de certificados
vault write pki/roles/orchestrator \
    allowed_domains=orchestrator.neural-hive.local,neural-hive.local \
    allow_subdomains=true \
    max_ttl=720h

echo ""
echo "=== 6. Criar Policy de RBAC ==="
vault policy write orchestrator-policy - <<EOF
# Permitir KV secrets
path "secret/data/orchestrator/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Permitir database credentials
path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}

# Permitir PKI certificados
path "pki/issue/orchestrator" {
  capabilities = ["create", "update"]
}

# Permitir token renewal
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Permitir lookup do próprio token
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

echo ""
echo "=== 7. Escrever Segredos de Teste ==="
vault kv put secret/orchestrator/mongodb \
    uri="mongodb://testuser:testpass@mongodb:27017/test_db"

vault kv put secret/orchestrator/redis \
    password="test_redis_password"

vault kv put secret/orchestrator/kafka \
    username="test_kafka_user" \
    password="test_kafka_pass" \
    ttl=3600

echo ""
echo "=== 8. Verificar Configuração ==="
echo "Status dos Auth Methods:"
vault auth list

echo ""
echo "Status dos Secrets Engines:"
vault secrets list

echo ""
echo "=== Vault Setup Concluído ==="
echo "Token de desenvolvimento: $VAULT_TOKEN"
echo "Endpoint: http://localhost:8200"
