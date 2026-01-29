#!/bin/bash
#
# Smoke Test para Distributed Tracing - Neural Hive
#
# Este script realiza uma validação rápida (<2 minutos) para verificar
# se a infraestrutura de tracing está funcionando corretamente.
#
# Uso:
#   ./scripts/observability/smoke-test-tracing.sh
#   NAMESPACE=my-observability ./scripts/observability/smoke-test-tracing.sh
#
# Variáveis de ambiente:
#   NAMESPACE: namespace do Kubernetes (default: observability)
#   JAEGER_URL: URL do Jaeger Query (default: auto-detectado via port-forward)
#

set -euo pipefail

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Configurações
NAMESPACE="${NAMESPACE:-observability}"
NEURAL_HIVE_NAMESPACE="${NEURAL_HIVE_NAMESPACE:-neural-hive}"
JAEGER_URL="${JAEGER_URL:-}"
TIMEOUT=30
PF_PID=""

# Cleanup function
cleanup() {
    if [ -n "$PF_PID" ]; then
        kill $PF_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Funções de logging
log_info() {
    echo -e "${NC}[INFO] $1${NC}"
}

log_success() {
    echo -e "${GREEN}[✓] $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}[!] $1${NC}"
}

log_error() {
    echo -e "${RED}[✗] $1${NC}"
}

# Função para verificar pod está rodando
check_pod_running() {
    local namespace=$1
    local selector=$2
    local name=$3

    echo -n "Verificando $name... "

    local phase=$(kubectl get pods -n "$namespace" -l "$selector" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")

    if [ "$phase" = "Running" ]; then
        log_success "$name está rodando"
        return 0
    else
        log_error "$name não está rodando (status: $phase)"
        return 1
    fi
}

# Função para setup do port-forward
setup_port_forward() {
    if [ -z "$JAEGER_URL" ]; then
        log_info "Configurando port-forward para Jaeger..."

        # Tentar encontrar o serviço Jaeger
        JAEGER_SVC=$(kubectl get svc -n "$NAMESPACE" -l app.kubernetes.io/component=query -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [ -z "$JAEGER_SVC" ]; then
            JAEGER_SVC=$(kubectl get svc -n "$NAMESPACE" -l app=jaeger-query -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "jaeger-query")
        fi

        kubectl port-forward -n "$NAMESPACE" "svc/$JAEGER_SVC" 16686:16686 > /dev/null 2>&1 &
        PF_PID=$!
        sleep 3

        JAEGER_URL="http://localhost:16686"
        log_info "Port-forward configurado: $JAEGER_URL"
    fi
}

# Função principal
main() {
    echo ""
    echo "=============================================="
    echo " Smoke Test - Distributed Tracing Neural Hive"
    echo "=============================================="
    echo ""

    local failed=0
    local warnings=0

    # 1. Verificar OTEL Collector
    echo "1. Verificando OTEL Collector..."
    if ! check_pod_running "$NAMESPACE" "app.kubernetes.io/name=neural-hive-otel-collector" "OTEL Collector"; then
        # Tentar label alternativo
        if ! check_pod_running "$NAMESPACE" "app=otel-collector" "OTEL Collector"; then
            ((failed++))
        fi
    fi

    # 2. Verificar Jaeger Collector
    echo ""
    echo "2. Verificando Jaeger Collector..."
    if ! check_pod_running "$NAMESPACE" "app.kubernetes.io/component=collector" "Jaeger Collector"; then
        if ! check_pod_running "$NAMESPACE" "app=jaeger-collector" "Jaeger Collector"; then
            ((failed++))
        fi
    fi

    # 3. Verificar Jaeger Query
    echo ""
    echo "3. Verificando Jaeger Query..."
    if ! check_pod_running "$NAMESPACE" "app.kubernetes.io/component=query" "Jaeger Query"; then
        if ! check_pod_running "$NAMESPACE" "app=jaeger-query" "Jaeger Query"; then
            ((failed++))
        fi
    fi

    # 4. Setup port-forward se necessário
    echo ""
    echo "4. Configurando acesso ao Jaeger..."
    setup_port_forward

    # 5. Verificar Jaeger API está respondendo
    echo ""
    echo "5. Verificando Jaeger API..."
    echo -n "Verificando conectividade... "

    if curl -s --connect-timeout 5 "$JAEGER_URL/api/services" > /dev/null 2>&1; then
        log_success "Jaeger API está acessível"
    else
        log_error "Jaeger API não está acessível"
        ((failed++))
    fi

    # 6. Verificar métricas do OTEL Collector
    echo ""
    echo "6. Verificando métricas do OTEL Collector..."

    OTEL_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=neural-hive-otel-collector -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$OTEL_POD" ]; then
        OTEL_POD=$(kubectl get pods -n "$NAMESPACE" -l app=otel-collector -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi

    if [ -n "$OTEL_POD" ]; then
        echo -n "Verificando spans recebidos... "

        SPANS_RECEIVED=$(kubectl exec -n "$NAMESPACE" "$OTEL_POD" -- curl -s http://localhost:8888/metrics 2>/dev/null | grep 'otelcol_receiver_accepted_spans{' | head -1 | awk '{print $2}' || echo "0")

        if [ "${SPANS_RECEIVED:-0}" != "0" ] && [ "${SPANS_RECEIVED:-0}" != "" ]; then
            # Converter para inteiro (remover decimais se houver)
            SPANS_INT=$(echo "$SPANS_RECEIVED" | cut -d. -f1)
            if [ "${SPANS_INT:-0}" -gt 0 ]; then
                log_success "OTEL Collector recebeu $SPANS_INT spans"
            else
                log_warn "OTEL Collector recebeu 0 spans"
                ((warnings++))
            fi
        else
            log_warn "Não foi possível verificar spans recebidos"
            ((warnings++))
        fi

        echo -n "Verificando spans exportados... "

        SPANS_SENT=$(kubectl exec -n "$NAMESPACE" "$OTEL_POD" -- curl -s http://localhost:8888/metrics 2>/dev/null | grep 'otelcol_exporter_sent_spans{' | head -1 | awk '{print $2}' || echo "0")

        if [ "${SPANS_SENT:-0}" != "0" ] && [ "${SPANS_SENT:-0}" != "" ]; then
            SPANS_INT=$(echo "$SPANS_SENT" | cut -d. -f1)
            if [ "${SPANS_INT:-0}" -gt 0 ]; then
                log_success "OTEL Collector exportou $SPANS_INT spans"
            else
                log_warn "OTEL Collector exportou 0 spans"
                ((warnings++))
            fi
        else
            log_warn "Não foi possível verificar spans exportados"
            ((warnings++))
        fi
    else
        log_warn "Não foi possível encontrar pod do OTEL Collector"
        ((warnings++))
    fi

    # 7. Verificar Jaeger tem serviços com traces
    echo ""
    echo "7. Verificando serviços no Jaeger..."
    echo -n "Verificando serviços com traces... "

    SERVICES_JSON=$(curl -s --connect-timeout 5 "$JAEGER_URL/api/services" 2>/dev/null || echo '{"data":[]}')
    SERVICES_COUNT=$(echo "$SERVICES_JSON" | jq -r '.data | length' 2>/dev/null || echo "0")

    if [ "${SERVICES_COUNT:-0}" -gt 0 ]; then
        log_success "Jaeger tem $SERVICES_COUNT serviços com traces"

        # Listar serviços Neural Hive
        NEURAL_HIVE_SERVICES=$(echo "$SERVICES_JSON" | jq -r '.data[] | select(. | test("gateway|orchestrator|specialist|consensus|queen|worker|guard|execution|service-registry"))' 2>/dev/null || echo "")

        if [ -n "$NEURAL_HIVE_SERVICES" ]; then
            echo "    Serviços Neural Hive encontrados:"
            echo "$NEURAL_HIVE_SERVICES" | while read svc; do
                echo "      - $svc"
            done
        fi
    else
        log_warn "Jaeger não tem serviços com traces"
        ((warnings++))
    fi

    # 8. Verificar traces recentes
    echo ""
    echo "8. Verificando traces recentes..."
    echo -n "Verificando traces dos últimos 5 minutos... "

    RECENT_TRACES=$(curl -s --connect-timeout 5 "$JAEGER_URL/api/traces?service=gateway-intencoes&lookback=5m&limit=5" 2>/dev/null || echo '{"data":[]}')
    TRACES_COUNT=$(echo "$RECENT_TRACES" | jq -r '.data | length' 2>/dev/null || echo "0")

    if [ "${TRACES_COUNT:-0}" -gt 0 ]; then
        log_success "Encontrados $TRACES_COUNT traces recentes no gateway"
    else
        # Tentar outro serviço
        RECENT_TRACES=$(curl -s --connect-timeout 5 "$JAEGER_URL/api/traces?service=orchestrator-dynamic&lookback=5m&limit=5" 2>/dev/null || echo '{"data":[]}')
        TRACES_COUNT=$(echo "$RECENT_TRACES" | jq -r '.data | length' 2>/dev/null || echo "0")

        if [ "${TRACES_COUNT:-0}" -gt 0 ]; then
            log_success "Encontrados $TRACES_COUNT traces recentes no orchestrator"
        else
            log_warn "Nenhum trace recente encontrado (últimos 5 minutos)"
            ((warnings++))
        fi
    fi

    # 9. Verificar atributos Neural Hive
    echo ""
    echo "9. Verificando atributos Neural Hive..."
    echo -n "Verificando presença de neural.hive.* attributes... "

    NH_TRACES=$(curl -s --connect-timeout 5 "$JAEGER_URL/api/traces?tag=neural.hive.component:gateway&lookback=1h&limit=1" 2>/dev/null || echo '{"data":[]}')
    NH_TRACES_COUNT=$(echo "$NH_TRACES" | jq -r '.data | length' 2>/dev/null || echo "0")

    if [ "${NH_TRACES_COUNT:-0}" -gt 0 ]; then
        log_success "Atributos neural.hive.* estão sendo propagados"
    else
        log_warn "Atributos neural.hive.* não encontrados"
        ((warnings++))
    fi

    # Resumo
    echo ""
    echo "=============================================="
    echo " Resumo do Smoke Test"
    echo "=============================================="

    if [ $failed -eq 0 ] && [ $warnings -eq 0 ]; then
        echo -e "${GREEN}"
        echo "  ✓ Todos os testes passaram!"
        echo -e "${NC}"
        exit 0
    elif [ $failed -eq 0 ]; then
        echo -e "${YELLOW}"
        echo "  ! Testes passaram com $warnings aviso(s)"
        echo ""
        echo "  Recomendações:"
        echo "  - Execute tráfego de teste para gerar traces"
        echo "  - Verifique configuração de sampling"
        echo "  - Execute validação completa com test-e2e-tracing-complete.py"
        echo -e "${NC}"
        exit 0
    else
        echo -e "${RED}"
        echo "  ✗ $failed teste(s) falharam, $warnings aviso(s)"
        echo ""
        echo "  Próximos passos:"
        echo "  - Verifique logs: kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=neural-hive-otel-collector"
        echo "  - Verifique conectividade entre componentes"
        echo "  - Consulte docs/observability/jaeger-troubleshooting.md"
        echo -e "${NC}"
        exit 1
    fi
}

# Verificar dependências
if ! command -v kubectl &> /dev/null; then
    log_error "kubectl não encontrado. Instale kubectl primeiro."
    exit 1
fi

if ! command -v curl &> /dev/null; then
    log_error "curl não encontrado. Instale curl primeiro."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    log_warn "jq não encontrado. Algumas funcionalidades podem não funcionar."
fi

# Executar
main "$@"
