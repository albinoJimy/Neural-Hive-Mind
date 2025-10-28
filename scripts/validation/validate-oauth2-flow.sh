#!/bin/bash

# validate-oauth2-flow.sh
# Script de validação do fluxo OAuth2 com Keycloak
# Testa autenticação, autorização e integração com serviços

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurações
KEYCLOAK_NAMESPACE="auth-system"
APP_NAMESPACE="neural-hive"
REALM="neural-hive"
TEST_CLIENT_ID="neural-hive-test"
KEYCLOAK_SERVICE="keycloak"

# Funções utilitárias
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_keycloak_status() {
    log_info "Verificando status do Keycloak..."

    # Verificar se deployment existe
    if ! kubectl get deployment keycloak -n $KEYCLOAK_NAMESPACE &> /dev/null; then
        log_error "Deployment do Keycloak não encontrado"
        return 1
    fi

    # Verificar se está rodando
    local ready_replicas=$(kubectl get deployment keycloak -n $KEYCLOAK_NAMESPACE -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    local desired_replicas=$(kubectl get deployment keycloak -n $KEYCLOAK_NAMESPACE -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")

    if [ "$ready_replicas" != "$desired_replicas" ]; then
        log_error "Keycloak não está completamente pronto. Réplicas: $ready_replicas/$desired_replicas"
        return 1
    fi

    log_success "Keycloak está rodando com $ready_replicas réplicas"
    return 0
}

check_keycloak_connectivity() {
    log_info "Verificando conectividade com Keycloak..."

    # Obter pod do Keycloak
    local keycloak_pod=$(kubectl get pods -n $KEYCLOAK_NAMESPACE -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$keycloak_pod" ]; then
        log_error "Pod do Keycloak não encontrado"
        return 1
    fi

    # Testar conectividade HTTP dentro do pod
    if ! kubectl exec -n $KEYCLOAK_NAMESPACE "$keycloak_pod" -- curl -s -f http://localhost:8080/health/ready &> /dev/null; then
        log_error "Keycloak não está respondendo no endpoint de saúde"
        return 1
    fi

    log_success "Keycloak está respondendo corretamente"
    return 0
}

get_keycloak_url() {
    # Tentar obter URL através do service
    local keycloak_url=""

    # Verificar se há ingress configurado
    if kubectl get ingress -n $KEYCLOAK_NAMESPACE | grep -q keycloak; then
        keycloak_url="https://$(kubectl get ingress -n $KEYCLOAK_NAMESPACE -o jsonpath='{.items[0].spec.rules[0].host}')"
    else
        # Port-forward como fallback para testes
        log_info "Configurando port-forward para Keycloak..."
        kubectl port-forward -n $KEYCLOAK_NAMESPACE svc/keycloak 8080:80 &
        local portfwd_pid=$!
        sleep 5
        keycloak_url="http://localhost:8080"

        # Salvar PID para limpeza posterior
        echo $portfwd_pid > /tmp/keycloak-portfwd.pid
    fi

    echo "$keycloak_url"
}

test_well_known_endpoint() {
    log_info "Testando endpoint .well-known do OpenID Connect..."

    local keycloak_url=$(get_keycloak_url)
    local wellknown_url="${keycloak_url}/realms/${REALM}/.well-known/openid_configuration"

    # Testar endpoint .well-known
    if ! curl -s -f "$wellknown_url" &> /dev/null; then
        log_error "Endpoint .well-known não está acessível: $wellknown_url"
        return 1
    fi

    # Verificar conteúdo
    local response=$(curl -s "$wellknown_url")
    if ! echo "$response" | jq -e '.issuer' &> /dev/null; then
        log_error "Resposta do .well-known não contém campo 'issuer'"
        return 1
    fi

    local issuer=$(echo "$response" | jq -r '.issuer')
    log_success "Endpoint .well-known está funcionando. Issuer: $issuer"
    return 0
}

test_jwks_endpoint() {
    log_info "Testando endpoint JWKS..."

    local keycloak_url=$(get_keycloak_url)
    local jwks_url="${keycloak_url}/realms/${REALM}/protocol/openid-connect/certs"

    # Testar endpoint JWKS
    if ! curl -s -f "$jwks_url" &> /dev/null; then
        log_error "Endpoint JWKS não está acessível: $jwks_url"
        return 1
    fi

    # Verificar se contém chaves
    local response=$(curl -s "$jwks_url")
    if ! echo "$response" | jq -e '.keys[]' &> /dev/null; then
        log_error "Endpoint JWKS não retorna chaves válidas"
        return 1
    fi

    local key_count=$(echo "$response" | jq '.keys | length')
    log_success "Endpoint JWKS está funcionando com $key_count chaves"
    return 0
}

test_admin_api() {
    log_info "Testando API admin do Keycloak..."

    local keycloak_url=$(get_keycloak_url)

    # Obter credenciais de admin (assumindo que estão em secret)
    local admin_user=$(kubectl get secret keycloak-admin -n $KEYCLOAK_NAMESPACE -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "admin")
    local admin_pass=$(kubectl get secret keycloak-admin -n $KEYCLOAK_NAMESPACE -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

    if [ -z "$admin_pass" ]; then
        log_warning "Senha de admin não encontrada, pulando teste da API admin"
        return 0
    fi

    # Obter token de acesso admin
    local token_response=$(curl -s -X POST "${keycloak_url}/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" \
        -d "username=$admin_user" \
        -d "password=$admin_pass" 2>/dev/null || echo "")

    if [ -z "$token_response" ] || ! echo "$token_response" | jq -e '.access_token' &> /dev/null; then
        log_error "Falha ao obter token de admin"
        return 1
    fi

    local access_token=$(echo "$token_response" | jq -r '.access_token')

    # Testar listagem de realms
    if ! curl -s -H "Authorization: Bearer $access_token" "${keycloak_url}/admin/realms" | jq -e '.[]' &> /dev/null; then
        log_error "Falha ao acessar API admin dos realms"
        return 1
    fi

    log_success "API admin do Keycloak está funcionando"
    return 0
}

check_realm_configuration() {
    log_info "Verificando configuração do realm '$REALM'..."

    local keycloak_url=$(get_keycloak_url)
    local realm_url="${keycloak_url}/realms/${REALM}"

    # Testar se realm existe
    if ! curl -s -f "$realm_url" &> /dev/null; then
        log_warning "Realm '$REALM' não está acessível ou não existe"
        log_info "Você precisa criar o realm '$REALM' no Keycloak"
        return 1
    fi

    log_success "Realm '$REALM' está configurado e acessível"
    return 0
}

test_token_introspection() {
    log_info "Testando endpoint de introspecção de token..."

    local keycloak_url=$(get_keycloak_url)
    local introspect_url="${keycloak_url}/realms/${REALM}/protocol/openid-connect/token/introspect"

    # Testar endpoint (sem token válido, mas deve responder)
    local response=$(curl -s -X POST "$introspect_url" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "token=invalid_token" \
        -d "client_id=test" 2>/dev/null || echo "")

    if [ -z "$response" ]; then
        log_error "Endpoint de introspecção não está respondendo"
        return 1
    fi

    # Para token inválido, deve retornar active: false
    if echo "$response" | jq -e '.active == false' &> /dev/null; then
        log_success "Endpoint de introspecção está funcionando"
        return 0
    else
        log_error "Endpoint de introspecção retornou resposta inesperada"
        return 1
    fi
}

check_istio_integration() {
    log_info "Verificando integração com Istio..."

    # Verificar se RequestAuthentication existe
    if ! kubectl get requestauthentication -n $APP_NAMESPACE | grep -q keycloak; then
        log_warning "RequestAuthentication do Istio não encontrada"
        return 1
    fi

    # Verificar se AuthorizationPolicy existe
    if ! kubectl get authorizationpolicy -n $APP_NAMESPACE | grep -q jwt-auth; then
        log_warning "AuthorizationPolicy do Istio não encontrada"
        return 1
    fi

    log_success "Políticas de autenticação Istio estão configuradas"
    return 0
}

test_service_integration() {
    log_info "Testando integração com serviços..."

    # Verificar se Gateway de Intenções está rodando
    if ! kubectl get deployment gateway-intencoes -n $APP_NAMESPACE &> /dev/null; then
        log_warning "Gateway de Intenções não encontrado"
        return 1
    fi

    # Verificar se está pronto
    local ready_replicas=$(kubectl get deployment gateway-intencoes -n $APP_NAMESPACE -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$ready_replicas" -eq 0 ]; then
        log_warning "Gateway de Intenções não está pronto"
        return 1
    fi

    log_success "Serviços integrados estão rodando"
    return 0
}

cleanup_resources() {
    log_info "Limpando recursos de teste..."

    # Matar port-forward se estiver rodando
    if [ -f /tmp/keycloak-portfwd.pid ]; then
        local pid=$(cat /tmp/keycloak-portfwd.pid)
        kill $pid &> /dev/null || true
        rm -f /tmp/keycloak-portfwd.pid
    fi

    log_success "Recursos de teste limpos"
}

generate_report() {
    log_info "=== RELATÓRIO DE VALIDAÇÃO DO OAUTH2 FLOW ==="
    log_info "Timestamp: $(date)"
    log_info "Namespace Keycloak: $KEYCLOAK_NAMESPACE"
    log_info "Namespace App: $APP_NAMESPACE"
    log_info "Realm: $REALM"

    # Status do Keycloak
    if check_keycloak_status; then
        log_success "✅ Status do Keycloak: SAUDÁVEL"
    else
        log_error "❌ Status do Keycloak: PROBLEMAS DETECTADOS"
        return 1
    fi

    # Endpoints críticos
    local endpoints_ok=true
    if ! test_well_known_endpoint; then
        endpoints_ok=false
    fi
    if ! test_jwks_endpoint; then
        endpoints_ok=false
    fi

    if [ "$endpoints_ok" = true ]; then
        log_success "✅ Endpoints OpenID Connect: FUNCIONAIS"
    else
        log_error "❌ Endpoints OpenID Connect: PROBLEMAS"
    fi

    return 0
}

main() {
    log_info "=== Iniciando validação do fluxo OAuth2 ==="

    local validation_failed=false

    # Verificações básicas
    if ! check_keycloak_status; then
        validation_failed=true
    fi

    if ! check_keycloak_connectivity; then
        validation_failed=true
    fi

    # Testes de endpoints (apenas se básicos passaram)
    if [ "$validation_failed" = false ]; then
        if ! test_well_known_endpoint; then
            validation_failed=true
        fi

        if ! test_jwks_endpoint; then
            validation_failed=true
        fi

        # Testes opcionais (não falham a validação)
        test_admin_api || true
        check_realm_configuration || true
        test_token_introspection || true
        check_istio_integration || true
        test_service_integration || true
    fi

    # Limpeza
    cleanup_resources

    # Relatório final
    generate_report

    if [ "$validation_failed" = true ]; then
        log_error "=== Validação FALHOU - verifique os erros acima ==="
        log_info "Próximos passos:"
        log_info "1. Verifique se o Keycloak está rodando corretamente"
        log_info "2. Configure o realm '$REALM' no Keycloak admin"
        log_info "3. Crie clientes OAuth2 necessários"
        exit 1
    else
        log_success "=== Validação do OAuth2 Flow CONCLUÍDA COM SUCESSO ==="
        log_info "Próximos passos recomendados:"
        log_info "1. Configure clientes OAuth2 específicos para cada serviço"
        log_info "2. Configure políticas de autorização detalhadas"
        log_info "3. Teste integração end-to-end com aplicações"
        exit 0
    fi
}

# Trap para limpeza em caso de erro
trap cleanup_resources ERR

# Executar validação principal
main "$@"