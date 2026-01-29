#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

# validate-memory-layer.sh
# Script de validação completa da camada de memória
# Executa validações do Redis, OAuth2 e integração end-to-end

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDIS_VALIDATION_SCRIPT="$SCRIPT_DIR/validate-redis-cluster.sh"
OAUTH2_VALIDATION_SCRIPT="$SCRIPT_DIR/validate-oauth2-flow.sh"

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

log_section() {
    echo -e "${PURPLE}[SECTION]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando pré-requisitos para validação..."

    # Verificar se scripts de validação existem
    if [ ! -f "$REDIS_VALIDATION_SCRIPT" ]; then
        log_error "Script de validação do Redis não encontrado: $REDIS_VALIDATION_SCRIPT"
        exit 1
    fi

    if [ ! -f "$OAUTH2_VALIDATION_SCRIPT" ]; then
        log_error "Script de validação do OAuth2 não encontrado: $OAUTH2_VALIDATION_SCRIPT"
        exit 1
    fi

    # Verificar se são executáveis
    if [ ! -x "$REDIS_VALIDATION_SCRIPT" ]; then
        chmod +x "$REDIS_VALIDATION_SCRIPT"
    fi

    if [ ! -x "$OAUTH2_VALIDATION_SCRIPT" ]; then
        chmod +x "$OAUTH2_VALIDATION_SCRIPT"
    fi

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale o kubectl primeiro."
        exit 1
    fi

    # Verificar curl
    if ! command -v curl &> /dev/null; then
        log_error "curl não encontrado. Instale o curl primeiro."
        exit 1
    fi

    # Verificar jq
    if ! command -v jq &> /dev/null; then
        log_error "jq não encontrado. Instale o jq primeiro."
        exit 1
    fi

    # Verificar conexão com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi

    log_success "Pré-requisitos verificados com sucesso"
}

validate_redis_cluster() {
    log_section "=== VALIDAÇÃO DO REDIS CLUSTER ==="

    if bash "$REDIS_VALIDATION_SCRIPT"; then
        log_success "Validação do Redis Cluster: PASSOU"
        return 0
    else
        log_error "Validação do Redis Cluster: FALHOU"
        return 1
    fi
}

validate_oauth2_flow() {
    log_section "=== VALIDAÇÃO DO OAUTH2 FLOW ==="

    if bash "$OAUTH2_VALIDATION_SCRIPT"; then
        log_success "Validação do OAuth2 Flow: PASSOU"
        return 0
    else
        log_error "Validação do OAuth2 Flow: FALHOU"
        return 1
    fi
}

test_integration() {
    log_section "=== TESTE DE INTEGRAÇÃO END-TO-END ==="

    log_info "Testando integração entre componentes..."

    local integration_passed=true

    # Teste 1: Redis está acessível para o Gateway
    log_info "Teste 1: Conectividade Redis <-> Gateway"
    if kubectl get deployment gateway-intencoes -n neural-hive &> /dev/null; then
        local gateway_pod=$(kubectl get pods -n neural-hive -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [ -n "$gateway_pod" ]; then
            # Testar se o gateway consegue resolver o serviço Redis
            if kubectl exec -n neural-hive "$gateway_pod" -- nslookup neural-hive-cluster-redis.redis-system.svc.cluster.local &> /dev/null; then
                log_success "Gateway consegue resolver serviço Redis"
            else
                log_error "Gateway não consegue resolver serviço Redis"
                integration_passed=false
            fi
        else
            log_warning "Pod do Gateway não encontrado - pulando teste de conectividade"
        fi
    else
        log_warning "Gateway de Intenções não está implantado - pulando testes de integração"
    fi

    # Teste 2: Keycloak está acessível para validação JWT
    log_info "Teste 2: Conectividade Keycloak <-> Gateway"
    if [ -n "$gateway_pod" ]; then
        # Testar se o gateway consegue resolver o serviço Keycloak
        if kubectl exec -n neural-hive "$gateway_pod" -- nslookup keycloak.auth-system.svc.cluster.local &> /dev/null; then
            log_success "Gateway consegue resolver serviço Keycloak"
        else
            log_error "Gateway não consegue resolver serviço Keycloak"
            integration_passed=false
        fi
    fi

    # Teste 3: Políticas Istio estão aplicadas
    log_info "Teste 3: Políticas Istio"
    if kubectl get requestauthentication -n neural-hive | grep -q keycloak; then
        log_success "RequestAuthentication está configurada"
    else
        log_warning "RequestAuthentication não encontrada"
        integration_passed=false
    fi

    if kubectl get authorizationpolicy -n neural-hive | grep -q jwt-auth; then
        log_success "AuthorizationPolicy está configurada"
    else
        log_warning "AuthorizationPolicy não encontrada"
        integration_passed=false
    fi

    # Teste 4: OPA Gatekeeper está funcionando
    log_info "Teste 4: OPA Gatekeeper"
    if kubectl get deployment gatekeeper-controller-manager -n opa-system &> /dev/null; then
        local gatekeeper_ready=$(kubectl get deployment gatekeeper-controller-manager -n opa-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [ "$gatekeeper_ready" -gt 0 ]; then
            log_success "OPA Gatekeeper está rodando"
        else
            log_error "OPA Gatekeeper não está pronto"
            integration_passed=false
        fi
    else
        log_warning "OPA Gatekeeper não encontrado"
        integration_passed=false
    fi

    # Teste 5: Monitoramento está coletando métricas
    log_info "Teste 5: Monitoramento"
    if kubectl get servicemonitor -n redis-system | grep -q redis-cluster; then
        log_success "ServiceMonitor do Redis está configurado"
    else
        log_warning "ServiceMonitor do Redis não encontrado"
    fi

    if kubectl get servicemonitor -n auth-system | grep -q keycloak; then
        log_success "ServiceMonitor do Keycloak está configurado"
    else
        log_warning "ServiceMonitor do Keycloak não encontrado"
    fi

    if [ "$integration_passed" = true ]; then
        log_success "Teste de integração: PASSOU"
        return 0
    else
        log_error "Teste de integração: FALHOU"
        return 1
    fi
}

test_performance() {
    log_section "=== TESTE DE PERFORMANCE BÁSICA ==="

    log_info "Executando testes de performance básica..."

    local performance_passed=true

    # Teste de latência Redis
    log_info "Testando latência do Redis..."
    local redis_pod=$(kubectl get pods -n redis-system -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -n "$redis_pod" ]; then
        local latency_start=$(date +%s%N)
        kubectl exec -n redis-system "$redis_pod" -- redis-cli set "perf-test-$(date +%s)" "test-value" EX 60 &> /dev/null
        local latency_end=$(date +%s%N)
        local latency_ms=$(((latency_end - latency_start) / 1000000))

        if [ "$latency_ms" -lt 100 ]; then  # < 100ms
            log_success "Latência Redis: ${latency_ms}ms (EXCELENTE)"
        elif [ "$latency_ms" -lt 500 ]; then  # < 500ms
            log_success "Latência Redis: ${latency_ms}ms (BOM)"
        else
            log_warning "Latência Redis: ${latency_ms}ms (LENTA)"
            performance_passed=false
        fi
    else
        log_warning "Pod Redis não encontrado - pulando teste de latência"
    fi

    # Teste de latência Keycloak
    log_info "Testando latência do Keycloak..."
    local keycloak_pod=$(kubectl get pods -n auth-system -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -n "$keycloak_pod" ]; then
        local kc_start=$(date +%s%N)
        kubectl exec -n auth-system "$keycloak_pod" -- curl -s -f http://localhost:8080/health/ready &> /dev/null
        local kc_end=$(date +%s%N)
        local kc_latency_ms=$(((kc_end - kc_start) / 1000000))

        if [ "$kc_latency_ms" -lt 200 ]; then  # < 200ms
            log_success "Latência Keycloak: ${kc_latency_ms}ms (EXCELENTE)"
        elif [ "$kc_latency_ms" -lt 1000 ]; then  # < 1s
            log_success "Latência Keycloak: ${kc_latency_ms}ms (BOM)"
        else
            log_warning "Latência Keycloak: ${kc_latency_ms}ms (LENTA)"
            performance_passed=false
        fi
    else
        log_warning "Pod Keycloak não encontrado - pulando teste de latência"
    fi

    if [ "$performance_passed" = true ]; then
        log_success "Teste de performance: PASSOU"
        return 0
    else
        log_error "Teste de performance: FALHOU"
        return 1
    fi
}

generate_final_report() {
    log_section "=== RELATÓRIO FINAL DA VALIDAÇÃO DA CAMADA DE MEMÓRIA ==="

    local timestamp=$(date)
    local cluster_info=$(kubectl cluster-info | head -1 | grep -o 'https://[^[:space:]]*' || echo "unknown")

    echo -e "${BLUE}Timestamp:${NC} $timestamp"
    echo -e "${BLUE}Cluster:${NC} $cluster_info"
    echo -e "${BLUE}Namespaces:${NC} redis-system, auth-system, opa-system, neural-hive"

    echo ""
    echo "=== COMPONENTES VALIDADOS ==="

    # Status dos componentes principais
    echo "🔴 Redis Cluster:"
    if kubectl get rediscluster neural-hive-cluster -n redis-system &> /dev/null; then
        local redis_status=$(kubectl get rediscluster neural-hive-cluster -n redis-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        echo "  ✅ Status: $redis_status/6 réplicas prontas"
    else
        echo "  ❌ Status: Não encontrado"
    fi

    echo "🔐 Keycloak OAuth2:"
    if kubectl get deployment keycloak -n auth-system &> /dev/null; then
        local kc_status=$(kubectl get deployment keycloak -n auth-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        echo "  ✅ Status: $kc_status réplicas prontas"
    else
        echo "  ❌ Status: Não encontrado"
    fi

    echo "🛡️  OPA Gatekeeper:"
    if kubectl get deployment gatekeeper-controller-manager -n opa-system &> /dev/null; then
        local opa_status=$(kubectl get deployment gatekeeper-controller-manager -n opa-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        echo "  ✅ Status: $opa_status réplicas prontas"
    else
        echo "  ❌ Status: Não encontrado"
    fi

    echo "🌐 Istio Integration:"
    local istio_policies=$(kubectl get requestauthentication,authorizationpolicy -n neural-hive 2>/dev/null | wc -l)
    echo "  ✅ Políticas configuradas: $istio_policies"

    echo "📊 Monitoring:"
    local monitors=$(kubectl get servicemonitor --all-namespaces 2>/dev/null | grep -E "(redis|keycloak)" | wc -l)
    echo "  ✅ ServiceMonitors: $monitors configurados"

    echo ""
    echo "=== PRÓXIMOS PASSOS RECOMENDADOS ==="
    echo "1. 🔧 Configure clientes OAuth2 específicos no Keycloak"
    echo "2. 🧪 Execute testes de carga para validar escalabilidade"
    echo "3. 🚀 Implante aplicações que utilizem a camada de memória"
    echo "4. 📈 Configure alertas adicionais no Prometheus/Grafana"
    echo "5. 🔒 Revise e ajuste políticas de segurança conforme necessário"

    return 0
}

main() {
    log_section "=== INICIANDO VALIDAÇÃO COMPLETA DA CAMADA DE MEMÓRIA ==="

    local overall_success=true

    # Verificar pré-requisitos
    check_prerequisites

    # Executar validações individuais
    if ! validate_redis_cluster; then
        overall_success=false
    fi

    if ! validate_oauth2_flow; then
        overall_success=false
    fi

    # Executar testes de integração
    if ! test_integration; then
        overall_success=false
    fi

    # Executar testes de performance
    if ! test_performance; then
        overall_success=false
    fi

    # Gerar relatório final
    generate_final_report

    if [ "$overall_success" = true ]; then
        log_success "=== VALIDAÇÃO COMPLETA: SUCESSO TOTAL ==="
        echo ""
        echo "🎉 A camada de memória está funcionando corretamente!"
        echo "🚀 Sistema pronto para uso em produção."
        exit 0
    else
        log_error "=== VALIDAÇÃO COMPLETA: PROBLEMAS ENCONTRADOS ==="
        echo ""
        echo "⚠️  Alguns componentes apresentaram problemas."
        echo "🔍 Revise os logs acima para detalhes específicos."
        echo "🛠️  Execute correções necessárias antes de usar em produção."
        exit 1
    fi
}

# Executar script principal
main "$@"