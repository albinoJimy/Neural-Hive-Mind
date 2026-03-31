#!/bin/bash
# Script para inicializar secrets do Neural-Hive-Mind no HashiCorp Vault
# Uso: ./vault-seed.sh [VAULT_ADDR] [VAULT_TOKEN]

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-dev-only-token}"

export VAULT_ADDR
export VAULT_TOKEN

echo "Configurando Vault para Neural-Hive-Mind..."
echo "Vault Addr: $VAULT_ADDR"

# Habilitar KV v2 (falha silenciosamente se já habilitado)
vault secrets enable -path=neural-hive kv-v2 2>/dev/null || echo "KV v2 ja habilitado em neural-hive"

# Gerar e armazenar JWT secret para Gateway de Intencoes
echo "Configurando JWT secret para Gateway..."
vault kv put neural-hive/gateway/jwt \
  secret="$(openssl rand -hex 32)" \
  ttl="87600h" \
  description="JWT secret for Gateway de Intencoes"

# Armazenar Keycloak client secret
echo "Configurando Keycloak client secret..."
vault kv put neural-hive/gateway/api \
  keycloak_client_secret="${KEYCLOAK_CLIENT_SECRET:-change-me-in-prod}" \
  description="API secrets for external integrations"

# Criar policy para o Gateway de Intencoes
echo "Criando policy neural-hive-gateway..."
vault policy write neural-hive-gateway - <<EOF
path "neural-hive/data/gateway/*" {
  capabilities = ["read"]
}
EOF

# Criar policy para outros servicos (exemplo)
echo "Criando policy neural-hive-services..."
vault policy write neural-hive-services - <<EOF
path "neural-hive/data/*" {
  capabilities = ["read", "list"]
}
EOF

# Habilitar Kubernetes auth (opcional, para cluster Kubernetes)
echo "Habilitando Kubernetes auth method..."
vault auth enable kubernetes 2>/dev/null || echo "Kubernetes auth ja habilitado"

# Configurar Kubernetes auth (requer executar dentro do cluster ou fornecer config)
# Nota: Em producao, configure o host e token do Kubernetes
# vault write auth/kubernetes/config \
#   kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
#   token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
#   kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

# Criar role para Kubernetes auth do Gateway
echo "Criando role Kubernetes para gateway-intencoes..."
vault write auth/kubernetes/role/neural-hive-gateway \
  bound_service_account_names=gateway-intencoes \
  bound_service_account_namespaces=neural-hive \
  policies=neural-hive-gateway \
  ttl=24h

echo ""
echo "Vault setup completado!"
echo ""
echo "Secrets configurados:"
echo "  - neural-hive/gateway/jwt (JWT secret)"
echo "  - neural-hive/gateway/api (Keycloak client secret)"
echo ""
echo "Policies criadas:"
echo "  - neural-hive-gateway"
echo "  - neural-hive-services"
echo ""
echo "Kubernetes auth role criada:"
echo "  - neural-hive-gateway (para gateway-intencoes service account)"
echo ""
echo "Para verificar os secrets:"
echo "  vault kv get neural-hive/gateway/jwt"
echo "  vault kv get neural-hive/gateway/api"
