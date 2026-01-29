#!/usr/bin/env bash
# Script de inicialização do Vault PKI Engine
# Configura PKI para emissão de certificados mTLS

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Verificar se vault CLI está instalado
if ! command -v vault &> /dev/null; then
    log_error "Vault CLI não encontrado. Instale: https://www.vaultproject.io/downloads"
    exit 1
fi

# Verificar se está autenticado no Vault
if ! vault token lookup &> /dev/null; then
    log_error "Não autenticado no Vault. Execute: vault login"
    exit 1
fi

log_info "Inicializando Vault PKI Engine..."

# 1. Habilitar PKI secrets engine
log_info "Habilitando PKI secrets engine em path 'pki'..."
if vault secrets list | grep -q "^pki/"; then
    log_warn "PKI engine já habilitado em 'pki/', pulando criação"
else
    vault secrets enable -path=pki pki
    log_info "PKI engine habilitado"
fi

# 2. Configurar TTL máximo (10 anos)
log_info "Configurando TTL máximo para 87600h (10 anos)..."
vault secrets tune -max-lease-ttl=87600h pki

# 3. Gerar Root CA
log_info "Gerando Root CA interna..."
if vault read pki/cert/ca &> /dev/null; then
    log_warn "Root CA já existe, pulando geração"
else
    vault write pki/root/generate/internal \
        common_name="Neural Hive-Mind Root CA" \
        issuer_name="root-ca" \
        ttl=87600h \
        key_type="rsa" \
        key_bits=4096
    log_info "Root CA gerado com sucesso"
fi

# 4. Configurar URLs de CA e CRL
log_info "Configurando URLs de CA e CRL..."
vault write pki/config/urls \
    issuing_certificates="https://vault.vault.svc.cluster.local:8200/v1/pki/ca" \
    crl_distribution_points="https://vault.vault.svc.cluster.local:8200/v1/pki/crl"

# 5. Criar role para emissão de certificados de serviços
log_info "Criando role 'neural-hive-services' para certificados de serviços..."
vault write pki/roles/neural-hive-services \
    allowed_domains="neural-hive.local,svc.cluster.local,*.neural-hive.local,*.svc.cluster.local" \
    allow_subdomains=true \
    max_ttl="720h" \
    ttl="168h" \
    key_type="rsa" \
    key_bits=2048 \
    allow_ip_sans=true \
    server_flag=true \
    client_flag=true

log_info "Role 'neural-hive-services' criada com sucesso"

# 6. Criar policy para emissão de certificados
log_info "Criando policy 'pki-issue' para emissão de certificados..."
vault policy write pki-issue - <<EOF
# Permitir emissão de certificados usando role neural-hive-services
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}

# Permitir leitura do CA
path "pki/cert/ca" {
  capabilities = ["read"]
}

# Permitir leitura de certificados emitidos
path "pki/cert/*" {
  capabilities = ["read"]
}
EOF

log_info "Policy 'pki-issue' criada com sucesso"

# 7. Verificar configuração
log_info "Verificando configuração PKI..."
vault read pki/config/urls

log_info "Listando roles disponíveis..."
vault list pki/roles || log_warn "Nenhuma role encontrada (possível erro de permissão)"

# 8. Testar emissão de certificado
log_info "Testando emissão de certificado de teste..."
if vault write -format=json pki/issue/neural-hive-services \
    common_name="test.neural-hive.local" \
    ttl="24h" > /tmp/vault-pki-test.json 2>&1; then

    log_info "Certificado de teste emitido com sucesso!"

    # Extrair informações do certificado
    CERT_SERIAL=$(jq -r '.data.serial_number' /tmp/vault-pki-test.json)
    CERT_EXPIRY=$(jq -r '.data.expiration' /tmp/vault-pki-test.json)

    log_info "Serial Number: $CERT_SERIAL"
    log_info "Expiry: $(date -d @$CERT_EXPIRY 2>/dev/null || date -r $CERT_EXPIRY)"

    # Revogar certificado de teste
    log_info "Revogando certificado de teste..."
    vault write pki/revoke serial_number="$CERT_SERIAL"

    # Limpar arquivo temporário
    rm -f /tmp/vault-pki-test.json
else
    log_error "Falha ao emitir certificado de teste. Verifique logs acima."
    exit 1
fi

log_info "PKI Engine configurado com sucesso!"
log_info ""
log_info "Próximos passos:"
log_info "  1. Configure Kubernetes auth: ./scripts/vault-configure-policies.sh"
log_info "  2. Adicione policy 'pki-issue' aos roles do Kubernetes auth"
log_info "  3. Configure aplicações para usar Vault PKI engine"
log_info ""
log_info "Para emitir certificado manualmente:"
log_info "  vault write pki/issue/neural-hive-services common_name=\"service.neural-hive.local\" ttl=\"168h\""
