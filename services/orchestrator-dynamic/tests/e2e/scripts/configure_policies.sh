#!/bin/sh
set -e

echo "=== Configurar Policies RBAC Vault ==="

export VAULT_ADDR='http://vault:8200'
export VAULT_TOKEN='dev-root-token'

# Aguardar Vault estar pronto
until curl -s http://vault:8200/v1/sys/health > /dev/null 2>&1; do
    echo "Aguardando Vault..."
    sleep 2
done

echo ""
echo "=== 1. Policy para Orchestrator (leitura/escrita limitada) ==="
vault policy write orchestrator-policy - <<EOF
path "secret/data/orchestrator/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}

path "database/creds/mongodb-orchestrator" {
  capabilities = ["read"]
}

path "pki/issue/orchestrator" {
  capabilities = ["create", "update"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

echo ""
echo "=== 2. Policy para Read-Only (testar permissões) ==="
vault policy write readonly-policy - <<EOF
path "secret/data/orchestrator/*" {
  capabilities = ["read", "list"]
}

path "database/creds/*" {
  capabilities = ["read"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}
EOF

echo ""
echo "=== 3. Policy para Admin (testar diferentes permissões) ==="
vault policy write admin-policy - <<EOF
path "*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
EOF

echo ""
echo "=== 4. Atualizar Role Kubernetes com ==="
vault write auth/kubernetes/role/orchestrator \
    bound_service_account_names=orchestrator,test-runner \
    bound_service_account_namespaces=default \
    policies=orchestrator-policy \
    ttl=1h \
    max_ttl=24h

vault write auth/kubernetes/role/readonly \
    bound_service_account_names=readonly \
    bound_service_account_namespaces=default \
    policies=readonly-policy \
    ttl=1h

vault write auth/kubernetes/role/admin \
    bound_service_account_names=admin \
    bound_service_account_namespaces=default \
    policies=admin-policy \
    ttl=2h

echo ""
echo "=== 5. Atualizar Role JWT para SPIFFE ==="
vault write auth/jwt/role/orchestrator \
    role_type=jwt \
    bound_audiences=vault.neural-hive.local \
    user_claim=sub \
    policies=orchestrator-policy \
    ttl=1h \
    max_ttl=24h

vault write auth/jwt/role/readonly \
    role_type=jwt \
    bound_audiences=vault.neural-hive.local \
    user_claim=sub \
    policies=readonly-policy \
    ttl=1h

echo ""
echo "=== 6. Criar Token com role específica para testes ==="
vault token create -policy=orchestrator-policy -ttl=2h -format=json > /tmp/vault-token.json
echo "Token de teste criado em /tmp/vault-token.json"

echo ""
echo "=== Policies Configuradas ==="
vault policy list

echo ""
echo "=== Roles Configuradas ==="
vault list auth/kubernetes/role 2>/dev/null || echo "Kubernetes roles:"
vault list auth/jwt/role 2>/dev/null || echo "JWT roles:"
