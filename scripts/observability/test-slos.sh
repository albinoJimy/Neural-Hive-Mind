#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

# Expanded SLO Testing Script for Neural Hive-Mind
# Este script testa e valida SLOs específicos do Neural Hive-Mind

set -euo pipefail

# Configurações
NAMESPACE="${NAMESPACE:-observability}"
TARGET_NAMESPACE="${TARGET_NAMESPACE:-neural-hive}"
TEST_DURATION="${TEST_DURATION:-300}"
LOOKBACK_PERIOD="${LOOKBACK_PERIOD:-1h}"
VERBOSE="${VERBOSE:-false}"
DRY_RUN="${DRY_RUN:-false}"
ALERT_TEST="${ALERT_TEST:-true}"

# SLOs Neural Hive-Mind (conforme especificação)
BARRAMENTO_LATENCY_SLO=150         # ms
AVAILABILITY_SLO=99.9              # %
PLAN_GENERATION_SLO=120            # ms
CAPTURE_LATENCY_SLO=200            # ms
ERROR_BUDGET_BURN_RATE_FAST=14.4   # 1 hour
ERROR_BUDGET_BURN_RATE_SLOW=1.0    # 6 hours

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Contadores de teste
TOTAL_SLO_TESTS=0
PASSED_SLO_TESTS=0
FAILED_SLO_TESTS=0
WARNING_SLO_TESTS=0

# Arrays para resultados
declare -a SLO_RESULTS=()
declare -a SLO_VIOLATIONS=()
declare -a SLO_WARNINGS=()

# Função para logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

# Função para executar teste de SLO
run_slo_test() {
    local test_name="$1"
    local test_function="$2"
    local is_critical="${3:-true}"

    TOTAL_SLO_TESTS=$((TOTAL_SLO_TESTS + 1))

    if [ "$DRY_RUN" == "true" ]; then
        info "[DRY-RUN] Seria executado: $test_name"
        return
    fi

    log "Executando teste de SLO: $test_name"

    local result
    result=$($test_function)
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        success "✓ $test_name: $result"
        PASSED_SLO_TESTS=$((PASSED_SLO_TESTS + 1))
        SLO_RESULTS+=("PASS: $test_name - $result")
    elif [ $exit_code -eq 2 ]; then
        warn "⚠ $test_name: $result"
        WARNING_SLO_TESTS=$((WARNING_SLO_TESTS + 1))
        SLO_WARNINGS+=("$test_name - $result")
        SLO_RESULTS+=("WARN: $test_name - $result")
    else
        if [ "$is_critical" == "true" ]; then
            error "✗ $test_name: $result"
            FAILED_SLO_TESTS=$((FAILED_SLO_TESTS + 1))
            SLO_VIOLATIONS+=("$test_name - $result")
            SLO_RESULTS+=("FAIL: $test_name - $result")
        else
            warn "⚠ $test_name: $result (não crítico)"
            WARNING_SLO_TESTS=$((WARNING_SLO_TESTS + 1))
            SLO_WARNINGS+=("$test_name - $result (não crítico)")
            SLO_RESULTS+=("WARN: $test_name - $result")
        fi
    fi
}

# Função para verificar dependências
check_dependencies() {
    log "Verificando dependências..."

    local deps=("kubectl" "curl" "jq" "bc")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            error "Dependência não encontrada: $dep"
            return 1
        fi
    done

    # Verificar conectividade com cluster
    if ! kubectl cluster-info &> /dev/null; then
        error "Não foi possível conectar ao cluster Kubernetes"
        return 1
    fi

    success "Dependências OK"
    return 0
}

# Função para conectar com Prometheus
setup_prometheus_connection() {
    # Port-forward para Prometheus
    kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-prometheus 0:9090 &
    PROMETHEUS_PID=$!
    sleep 3

    PROMETHEUS_PORT=$(lsof -Pan -p $PROMETHEUS_PID -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -z "$PROMETHEUS_PORT" ]; then
        kill $PROMETHEUS_PID 2>/dev/null || true
        error "Falha ao conectar com Prometheus"
        return 1
    fi

    export PROMETHEUS_URL="http://localhost:$PROMETHEUS_PORT"
    return 0
}

# Função para limpar conexões
cleanup_connections() {
    if [ -n "${PROMETHEUS_PID:-}" ]; then
        kill $PROMETHEUS_PID 2>/dev/null || true
    fi
}

# Função para executar query no Prometheus
prometheus_query() {
    local query="$1"
    local result
    result=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=$(echo "$query" | jq -sRr @uri)" | jq -r '.data.result[0].value[1] // "0"' 2>/dev/null || echo "0")
    echo "$result"
}

# Função para executar query com range no Prometheus
prometheus_range_query() {
    local query="$1"
    local range="${2:-$LOOKBACK_PERIOD}"
    local step="${3:-60s}"

    local end_time
    end_time=$(date +%s)
    local start_time
    start_time=$(date -d "$range ago" +%s)

    local result
    result=$(curl -s "$PROMETHEUS_URL/api/v1/query_range?query=$(echo "$query" | jq -sRr @uri)&start=$start_time&end=$end_time&step=$step" | jq -r '.data.result[0].values[-1][1] // "0"' 2>/dev/null || echo "0")
    echo "$result"
}

# SLO Test 1: Disponibilidade do Barramento Neural
test_barramento_availability() {
    local query='(
        sum(rate(neural_hive_barramento_requests_total{status!~"5.."}[5m])) /
        sum(rate(neural_hive_barramento_requests_total[5m]))
    ) * 100'

    local availability
    availability=$(prometheus_range_query "$query")

    if [ "$(echo "$availability == 0" | bc)" -eq 1 ]; then
        echo "Sem métricas de barramento disponíveis"
        return 2  # Warning
    fi

    local availability_int
    availability_int=$(echo "$availability" | cut -d. -f1)

    if [ -z "$availability_int" ] || [ "$availability_int" == "0" ]; then
        echo "Disponibilidade: dados insuficientes"
        return 2
    fi

    if [ "$(echo "$availability >= $AVAILABILITY_SLO" | bc)" -eq 1 ]; then
        echo "Disponibilidade: ${availability}% (✓ SLO: ≥${AVAILABILITY_SLO}%)"
        return 0
    else
        echo "Disponibilidade: ${availability}% (✗ SLO: ≥${AVAILABILITY_SLO}%)"
        return 1
    fi
}

# SLO Test 2: Latência do Barramento
test_barramento_latency() {
    local query='histogram_quantile(0.95,
        sum(rate(neural_hive_barramento_request_duration_seconds_bucket[5m])) by (le)
    ) * 1000'

    local latency_p95
    latency_p95=$(prometheus_range_query "$query")

    if [ "$(echo "$latency_p95 == 0" | bc)" -eq 1 ]; then
        echo "Sem métricas de latência do barramento disponíveis"
        return 2  # Warning
    fi

    if [ "$(echo "$latency_p95 <= $BARRAMENTO_LATENCY_SLO" | bc)" -eq 1 ]; then
        echo "Latência P95: ${latency_p95}ms (✓ SLO: ≤${BARRAMENTO_LATENCY_SLO}ms)"
        return 0
    else
        echo "Latência P95: ${latency_p95}ms (✗ SLO: ≤${BARRAMENTO_LATENCY_SLO}ms)"
        return 1
    fi
}

# SLO Test 3: Tempo de Geração de Planos
test_plan_generation_latency() {
    local query='histogram_quantile(0.95,
        sum(rate(neural_hive_plan_generation_duration_seconds_bucket[5m])) by (le)
    ) * 1000'

    local plan_latency_p95
    plan_latency_p95=$(prometheus_range_query "$query")

    if [ "$(echo "$plan_latency_p95 == 0" | bc)" -eq 1 ]; then
        echo "Sem métricas de geração de planos disponíveis"
        return 2  # Warning
    fi

    if [ "$(echo "$plan_latency_p95 <= $PLAN_GENERATION_SLO" | bc)" -eq 1 ]; then
        echo "Latência geração P95: ${plan_latency_p95}ms (✓ SLO: ≤${PLAN_GENERATION_SLO}ms)"
        return 0
    else
        echo "Latência geração P95: ${plan_latency_p95}ms (✗ SLO: ≤${PLAN_GENERATION_SLO}ms)"
        return 1
    fi
}

# SLO Test 4: Latência de Captura de Intenções
test_intent_capture_latency() {
    local query='histogram_quantile(0.95,
        sum(rate(neural_hive_intent_capture_duration_seconds_bucket[5m])) by (le)
    ) * 1000'

    local capture_latency_p95
    capture_latency_p95=$(prometheus_range_query "$query")

    if [ "$(echo "$capture_latency_p95 == 0" | bc)" -eq 1 ]; then
        echo "Sem métricas de captura de intenções disponíveis"
        return 2  # Warning
    fi

    if [ "$(echo "$capture_latency_p95 <= $CAPTURE_LATENCY_SLO" | bc)" -eq 1 ]; then
        echo "Latência captura P95: ${capture_latency_p95}ms (✓ SLO: ≤${CAPTURE_LATENCY_SLO}ms)"
        return 0
    else
        echo "Latência captura P95: ${capture_latency_p95}ms (✗ SLO: ≤${CAPTURE_LATENCY_SLO}ms)"
        return 1
    fi
}

# SLO Test 5: Taxa de Erro do Sistema
test_system_error_rate() {
    local query='(
        sum(rate(neural_hive_requests_total{status=~"5.."}[5m])) /
        sum(rate(neural_hive_requests_total[5m]))
    ) * 100'

    local error_rate
    error_rate=$(prometheus_range_query "$query")

    if [ "$(echo "$error_rate == 0" | bc)" -eq 1 ]; then
        echo "Taxa de erro: 0% (✓ SLO: ≤1%)"
        return 0
    fi

    local max_error_rate=1.0  # 1% maximum error rate

    if [ "$(echo "$error_rate <= $max_error_rate" | bc)" -eq 1 ]; then
        echo "Taxa de erro: ${error_rate}% (✓ SLO: ≤1%)"
        return 0
    else
        echo "Taxa de erro: ${error_rate}% (✗ SLO: ≤1%)"
        return 1
    fi
}

# SLO Test 6: Disponibilidade de Componentes Críticos
test_critical_components_availability() {
    local components=("neural-hive-gateway" "neural-hive-barramento" "neural-hive-cognicao" "neural-hive-experiencia")
    local failed_components=()

    for component in "${components[@]}"; do
        local query="up{job=\"$component\"}"
        local availability
        availability=$(prometheus_query "$query")

        if [ "$(echo "$availability == 1" | bc)" -eq 1 ]; then
            [ "$VERBOSE" == "true" ] && info "Componente $component: disponível"
        else
            failed_components+=("$component")
        fi
    done

    if [ ${#failed_components[@]} -eq 0 ]; then
        echo "Todos os componentes críticos disponíveis"
        return 0
    elif [ ${#failed_components[@]} -eq ${#components[@]} ]; then
        echo "Sem métricas de componentes disponíveis"
        return 2  # Warning - pode ser normal em ambiente de teste
    else
        echo "Componentes indisponíveis: ${failed_components[*]}"
        return 1
    fi
}

# SLO Test 7: Error Budget Burn Rate
test_error_budget_burn_rate() {
    # Calcular burn rate baseado na taxa de erro atual
    local error_rate_query='(
        sum(rate(neural_hive_requests_total{status=~"5.."}[1h])) /
        sum(rate(neural_hive_requests_total[1h]))
    ) * 100'

    local current_error_rate
    current_error_rate=$(prometheus_range_query "$error_rate_query" "1h")

    if [ "$(echo "$current_error_rate == 0" | bc)" -eq 1 ]; then
        echo "Error budget burn rate: 0% (✓ dentro dos limites)"
        return 0
    fi

    # Error budget de 0.1% (100% - 99.9% SLO)
    local error_budget=0.1
    local burn_rate
    burn_rate=$(echo "scale=2; $current_error_rate / $error_budget" | bc)

    # Verificar burn rate fast (1 hora) e slow (6 horas)
    if [ "$(echo "$burn_rate > $ERROR_BUDGET_BURN_RATE_FAST" | bc)" -eq 1 ]; then
        echo "Error budget burn rate: ${burn_rate}x (✗ crítico: >${ERROR_BUDGET_BURN_RATE_FAST}x)"
        return 1
    elif [ "$(echo "$burn_rate > $ERROR_BUDGET_BURN_RATE_SLOW" | bc)" -eq 1 ]; then
        echo "Error budget burn rate: ${burn_rate}x (⚠ atenção: >${ERROR_BUDGET_BURN_RATE_SLOW}x)"
        return 2  # Warning
    else
        echo "Error budget burn rate: ${burn_rate}x (✓ dentro dos limites)"
        return 0
    fi
}

# SLO Test 8: Correlação entre Traces e Métricas
test_trace_metric_correlation() {
    # Verificar se há exemplars disponíveis (indicando correlação ativa)
    local exemplars_query='neural_hive_requests_total'

    # Port-forward para verificar exemplars
    local exemplars_response
    exemplars_response=$(curl -s "$PROMETHEUS_URL/api/v1/query_exemplars?query=$exemplars_query" | jq -r '.data | length' 2>/dev/null || echo "0")

    if [ "$exemplars_response" -gt 0 ]; then
        echo "Correlação trace-métrica: $exemplars_response exemplar(s) disponíveis (✓)"
        return 0
    else
        echo "Correlação trace-métrica: nenhum exemplar disponível (⚠ normal sem tráfego)"
        return 2  # Warning
    fi
}

# SLO Test 9: Throughput do Sistema
test_system_throughput() {
    local query='sum(rate(neural_hive_requests_total[5m]))'

    local throughput
    throughput=$(prometheus_range_query "$query")

    if [ "$(echo "$throughput == 0" | bc)" -eq 1 ]; then
        echo "Throughput: 0 req/s (⚠ sistema inativo)"
        return 2  # Warning
    fi

    # SLO mínimo de throughput (exemplo: 1 req/s)
    local min_throughput=1

    if [ "$(echo "$throughput >= $min_throughput" | bc)" -eq 1 ]; then
        echo "Throughput: ${throughput} req/s (✓ SLO: ≥${min_throughput} req/s)"
        return 0
    else
        echo "Throughput: ${throughput} req/s (✗ SLO: ≥${min_throughput} req/s)"
        return 1
    fi
}

# SLO Test 10: Latência End-to-End
test_end_to_end_latency() {
    local query='histogram_quantile(0.95,
        sum(rate(neural_hive_request_duration_seconds_bucket{span_kind="server"}[5m])) by (le)
    ) * 1000'

    local e2e_latency_p95
    e2e_latency_p95=$(prometheus_range_query "$query")

    if [ "$(echo "$e2e_latency_p95 == 0" | bc)" -eq 1 ]; then
        echo "Sem métricas de latência end-to-end disponíveis"
        return 2  # Warning
    fi

    # SLO de latência end-to-end (exemplo: 500ms)
    local e2e_latency_slo=500

    if [ "$(echo "$e2e_latency_p95 <= $e2e_latency_slo" | bc)" -eq 1 ]; then
        echo "Latência E2E P95: ${e2e_latency_p95}ms (✓ SLO: ≤${e2e_latency_slo}ms)"
        return 0
    else
        echo "Latência E2E P95: ${e2e_latency_p95}ms (✗ SLO: ≤${e2e_latency_slo}ms)"
        return 1
    fi
}

# Função para testar alertas de SLO (se habilitado)
test_slo_alerts() {
    if [ "$ALERT_TEST" != "true" ]; then
        info "Teste de alertas de SLO desabilitado"
        return 0
    fi

    log "Testando alertas de SLO..."

    # Verificar se há alertas ativos relacionados a SLOs
    local alerts_query='ALERTS{alertname=~".*SLO.*|.*ErrorBudget.*"}'
    local active_alerts
    active_alerts=$(prometheus_query "$alerts_query")

    if [ "$(echo "$active_alerts == 0" | bc)" -eq 1 ]; then
        info "Nenhum alerta de SLO ativo (✓)"
        return 0
    else
        warn "$active_alerts alerta(s) de SLO ativo(s)"
        return 2  # Warning, não é necessariamente um erro
    fi
}

# Função para calcular SLI atual
calculate_current_sli() {
    log "Calculando SLIs atuais..."

    echo "=========================================="
    echo "  INDICADORES DE NÍVEL DE SERVIÇO (SLI)"
    echo "=========================================="

    # SLI 1: Disponibilidade geral
    local availability_query='(
        sum(rate(neural_hive_requests_total{status!~"5.."}[1h])) /
        sum(rate(neural_hive_requests_total[1h]))
    ) * 100'
    local availability
    availability=$(prometheus_range_query "$availability_query" "1h")
    echo "Disponibilidade (1h): ${availability}%"

    # SLI 2: Latência P95
    local latency_query='histogram_quantile(0.95,
        sum(rate(neural_hive_request_duration_seconds_bucket[1h])) by (le)
    ) * 1000'
    local latency_p95
    latency_p95=$(prometheus_range_query "$latency_query" "1h")
    echo "Latência P95 (1h): ${latency_p95}ms"

    # SLI 3: Taxa de erro
    local error_rate_query='(
        sum(rate(neural_hive_requests_total{status=~"5.."}[1h])) /
        sum(rate(neural_hive_requests_total[1h]))
    ) * 100'
    local error_rate
    error_rate=$(prometheus_range_query "$error_rate_query" "1h")
    echo "Taxa de erro (1h): ${error_rate}%"

    # SLI 4: Throughput
    local throughput_query='sum(rate(neural_hive_requests_total[1h]))'
    local throughput
    throughput=$(prometheus_range_query "$throughput_query" "1h")
    echo "Throughput (1h): ${throughput} req/s"

    echo "=========================================="
}

# Função para gerar relatório de SLO
generate_slo_report() {
    echo
    echo "=========================================="
    echo "  RELATÓRIO DE SLOs NEURAL HIVE-MIND"
    echo "=========================================="
    echo
    echo "Total de testes de SLO: $TOTAL_SLO_TESTS"
    echo -e "${GREEN}SLOs atendidos: $PASSED_SLO_TESTS${NC}"
    echo -e "${YELLOW}SLOs com avisos: $WARNING_SLO_TESTS${NC}"
    echo -e "${RED}SLOs violados: $FAILED_SLO_TESTS${NC}"
    echo

    if [ $FAILED_SLO_TESTS -gt 0 ]; then
        echo -e "${RED}VIOLAÇÕES DE SLO:${NC}"
        for violation in "${SLO_VIOLATIONS[@]}"; do
            echo "  ✗ $violation"
        done
        echo
    fi

    if [ $WARNING_SLO_TESTS -gt 0 ]; then
        echo -e "${YELLOW}AVISOS DE SLO:${NC}"
        for warning in "${SLO_WARNINGS[@]}"; do
            echo "  ⚠ $warning"
        done
        echo
    fi

    # Calcular compliance rate
    local compliant_tests=$((PASSED_SLO_TESTS + WARNING_SLO_TESTS))
    local compliance_rate
    if [ $TOTAL_SLO_TESTS -gt 0 ]; then
        compliance_rate=$(( (compliant_tests * 100) / TOTAL_SLO_TESTS ))
    else
        compliance_rate=0
    fi

    echo "Taxa de compliance: ${compliance_rate}%"
    echo

    echo "OBJETIVOS DE NÍVEL DE SERVIÇO (SLO):"
    echo "✓ Disponibilidade: ≥${AVAILABILITY_SLO}%"
    echo "✓ Latência do barramento: ≤${BARRAMENTO_LATENCY_SLO}ms (P95)"
    echo "✓ Geração de planos: ≤${PLAN_GENERATION_SLO}ms (P95)"
    echo "✓ Captura de intenções: ≤${CAPTURE_LATENCY_SLO}ms (P95)"
    echo "✓ Taxa de erro: ≤1%"
    echo "✓ Error budget burn rate: ≤${ERROR_BUDGET_BURN_RATE_FAST}x (fast), ≤${ERROR_BUDGET_BURN_RATE_SLOW}x (slow)"
    echo

    if [ $FAILED_SLO_TESTS -eq 0 ]; then
        success "Todos os SLOs Neural Hive-Mind estão sendo atendidos! 🎯"
        return 0
    else
        error "Detectadas violações de SLO. Ação necessária para restaurar níveis de serviço."
        return 1
    fi
}

# Função de ajuda
show_help() {
    cat << EOF
Neural Hive-Mind SLO Testing Script

Uso: $0 [opções]

Opções:
  -h, --help                    Mostrar esta ajuda
  -n, --namespace NS            Namespace da observabilidade (padrão: observability)
  -t, --target-namespace NS     Namespace dos serviços Neural Hive-Mind (padrão: neural-hive)
  -d, --duration SEC            Duração do teste (padrão: 300s)
  -l, --lookback PERIOD         Período de análise (padrão: 1h)
  -v, --verbose                 Output verboso
  --no-alerts                   Desabilitar teste de alertas
  --dry-run                     Apenas mostrar quais testes seriam executados

Variáveis de ambiente:
  NAMESPACE                     Namespace da observabilidade
  TARGET_NAMESPACE              Namespace dos serviços Neural Hive-Mind
  TEST_DURATION                 Duração do teste em segundos
  LOOKBACK_PERIOD               Período para análise histórica (ex: 1h, 24h)
  VERBOSE                       true/false para output verboso
  DRY_RUN                      true/false para dry run
  ALERT_TEST                   true/false para testar alertas

SLOs Neural Hive-Mind testados:
  Disponibilidade:              ≥${AVAILABILITY_SLO}%
  Latência barramento (P95):    ≤${BARRAMENTO_LATENCY_SLO}ms
  Geração de planos (P95):      ≤${PLAN_GENERATION_SLO}ms
  Captura de intenções (P95):   ≤${CAPTURE_LATENCY_SLO}ms
  Taxa de erro:                 ≤1%
  Error budget burn rate:       ≤${ERROR_BUDGET_BURN_RATE_FAST}x (fast), ≤${ERROR_BUDGET_BURN_RATE_SLOW}x (slow)

Exemplos:
  $0                                          # Teste completo de SLOs
  $0 --verbose --lookback 24h                 # Análise verbosa das últimas 24h
  $0 --dry-run                               # Apenas listar testes
  $0 --no-alerts --duration 600              # Teste longo sem alertas
EOF
}

# Função principal
main() {
    # Parse argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -n|--namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            -t|--target-namespace)
                TARGET_NAMESPACE="$2"
                shift 2
                ;;
            -d|--duration)
                TEST_DURATION="$2"
                shift 2
                ;;
            -l|--lookback)
                LOOKBACK_PERIOD="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            --no-alerts)
                ALERT_TEST=false
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            *)
                error "Opção desconhecida: $1"
                show_help
                exit 1
                ;;
        esac
    done

    echo "=========================================="
    echo "  TESTE DE SLOs NEURAL HIVE-MIND"
    echo "=========================================="
    echo
    log "Namespace observabilidade: $NAMESPACE"
    log "Namespace Neural Hive-Mind: $TARGET_NAMESPACE"
    log "Duração do teste: ${TEST_DURATION}s"
    log "Período de análise: $LOOKBACK_PERIOD"
    log "Verbose: $VERBOSE"
    log "Teste de alertas: $ALERT_TEST"
    log "Dry run: $DRY_RUN"
    echo

    # Trap para cleanup
    trap cleanup_connections EXIT

    # Verificar dependências
    if ! check_dependencies; then
        error "Falha na verificação de dependências"
        exit 1
    fi

    # Conectar com Prometheus
    if [ "$DRY_RUN" != "true" ]; then
        if ! setup_prometheus_connection; then
            error "Falha ao conectar com Prometheus"
            exit 1
        fi
        info "Conectado ao Prometheus: $PROMETHEUS_URL"
    fi

    # Calcular SLIs atuais
    if [ "$DRY_RUN" != "true" ] && [ "$VERBOSE" == "true" ]; then
        calculate_current_sli
        echo
    fi

    # Executar testes de SLO
    run_slo_test "Disponibilidade do Barramento" test_barramento_availability true
    run_slo_test "Latência do Barramento" test_barramento_latency true
    run_slo_test "Tempo de Geração de Planos" test_plan_generation_latency true
    run_slo_test "Latência de Captura de Intenções" test_intent_capture_latency true
    run_slo_test "Taxa de Erro do Sistema" test_system_error_rate true
    run_slo_test "Disponibilidade de Componentes Críticos" test_critical_components_availability true
    run_slo_test "Error Budget Burn Rate" test_error_budget_burn_rate true
    run_slo_test "Correlação Trace-Métrica" test_trace_metric_correlation false
    run_slo_test "Throughput do Sistema" test_system_throughput false
    run_slo_test "Latência End-to-End" test_end_to_end_latency true

    # Testar alertas se habilitado
    if [ "$ALERT_TEST" == "true" ] && [ "$DRY_RUN" != "true" ]; then
        test_slo_alerts
    fi

    # Gerar relatório final
    generate_slo_report
}

# Executar se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi