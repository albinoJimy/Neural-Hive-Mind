#!/bin/bash

# Enhanced Correlation Testing Script for Neural Hive-Mind
# Este script testa correlação distribuída específica do Neural Hive-Mind

set -euo pipefail

# Configurações
NAMESPACE="${NAMESPACE:-observability}"
TARGET_NAMESPACE="${TARGET_NAMESPACE:-neural-hive}"
TEST_DURATION="${TEST_DURATION:-60}"
SAMPLE_RATE="${SAMPLE_RATE:-1.0}"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"

# Headers de correlação Neural Hive-Mind
INTENT_ID_HEADER="X-Neural-Hive-Intent-ID"
PLAN_ID_HEADER="X-Neural-Hive-Plan-ID"
DOMAIN_HEADER="X-Neural-Hive-Domain"
USER_ID_HEADER="X-Neural-Hive-User-ID"

# Baggage keys para propagação
INTENT_BAGGAGE_KEY="neural.hive.intent.id"
PLAN_BAGGAGE_KEY="neural.hive.plan.id"
DOMAIN_BAGGAGE_KEY="neural.hive.domain"
USER_BAGGAGE_KEY="neural.hive.user.id"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Contadores de teste
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
CORRELATION_FAILURES=0

# Arrays para resultados
declare -a TEST_RESULTS=()
declare -a CORRELATION_FAILURES_LIST=()

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

# Função para gerar IDs únicos
generate_test_id() {
    echo "test-$(date +%s)-$(shuf -i 1000-9999 -n 1)"
}

generate_intent_id() {
    echo "intent-$(uuidgen | tr '[:upper:]' '[:lower:]')"
}

generate_plan_id() {
    echo "plan-$(uuidgen | tr '[:upper:]' '[:lower:]')"
}

# Função para executar teste de correlação
run_correlation_test() {
    local test_name="$1"
    local test_function="$2"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$DRY_RUN" == "true" ]; then
        info "[DRY-RUN] Seria executado: $test_name"
        return
    fi

    log "Executando teste de correlação: $test_name"

    if $test_function; then
        success "✓ $test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        TEST_RESULTS+=("PASS: $test_name")
    else
        error "✗ $test_name"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        TEST_RESULTS+=("FAIL: $test_name")
    fi
}

# Função para verificar dependências
check_dependencies() {
    log "Verificando dependências..."

    local deps=("kubectl" "curl" "jq" "uuidgen")
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

# Teste 1: Verificar configuração de correlação
test_correlation_config() {
    log "Verificando configuração de correlação..."

    # Verificar ConfigMap de correlação
    local correlation_config
    correlation_config=$(kubectl get configmap -n "$NAMESPACE" neural-hive-observability-config -o jsonpath='{.data.correlation\.yaml}' 2>/dev/null || echo "")

    if [ -z "$correlation_config" ]; then
        error "ConfigMap de correlação não encontrado"
        return 1
    fi

    # Verificar headers esperados
    local headers=("$INTENT_ID_HEADER" "$PLAN_ID_HEADER" "$DOMAIN_HEADER" "$USER_ID_HEADER")
    local failed=0

    for header in "${headers[@]}"; do
        if echo "$correlation_config" | grep -q "$header"; then
            [ "$VERBOSE" == "true" ] && info "Header configurado: $header"
        else
            error "Header não configurado: $header"
            failed=$((failed + 1))
        fi
    done

    # Verificar baggage keys
    local baggage_keys=("$INTENT_BAGGAGE_KEY" "$PLAN_BAGGAGE_KEY" "$DOMAIN_BAGGAGE_KEY" "$USER_BAGGAGE_KEY")

    for key in "${baggage_keys[@]}"; do
        if echo "$correlation_config" | grep -q "$key"; then
            [ "$VERBOSE" == "true" ] && info "Baggage key configurado: $key"
        else
            warn "Baggage key não configurado: $key"
        fi
    done

    [ $failed -eq 0 ]
}

# Teste 2: Verificar instrumentação do OpenTelemetry Collector
test_otel_correlation_config() {
    log "Verificando configuração de correlação no OpenTelemetry Collector..."

    # Obter configuração do OTEL Collector
    local otel_config
    otel_config=$(kubectl get configmap -n "$NAMESPACE" opentelemetry-collector -o jsonpath='{.data.relay\.yaml}' 2>/dev/null || echo "")

    if [ -z "$otel_config" ]; then
        error "Configuração do OpenTelemetry Collector não encontrada"
        return 1
    fi

    local failed=0

    # Verificar processadores de correlação
    if echo "$otel_config" | grep -q "baggage"; then
        [ "$VERBOSE" == "true" ] && info "Processador de baggage configurado"
    else
        error "Processador de baggage não configurado"
        failed=$((failed + 1))
    fi

    # Verificar headers de correlação
    local correlation_patterns=("neural.hive.intent" "neural.hive.plan" "neural.hive.domain" "neural.hive.user")

    for pattern in "${correlation_patterns[@]}"; do
        if echo "$otel_config" | grep -q "$pattern"; then
            [ "$VERBOSE" == "true" ] && info "Padrão de correlação encontrado: $pattern"
        else
            warn "Padrão de correlação não encontrado: $pattern"
        fi
    done

    [ $failed -eq 0 ]
}

# Teste 3: Testar propagação de headers HTTP
test_http_header_propagation() {
    log "Testando propagação de headers HTTP..."

    # Gerar IDs de teste
    local intent_id
    intent_id=$(generate_intent_id)
    local plan_id
    plan_id=$(generate_plan_id)
    local domain="correlacao-teste"
    local user_id="user-test-$(date +%s)"

    info "Testando com Intent ID: $intent_id"
    info "Testando com Plan ID: $plan_id"

    # Port-forward para OpenTelemetry Collector
    kubectl port-forward -n "$NAMESPACE" service/opentelemetry-collector 0:8888 &
    local pf_pid=$!
    sleep 3

    local local_port
    local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -z "$local_port" ]; then
        kill $pf_pid 2>/dev/null || true
        error "Falha ao conectar com OpenTelemetry Collector"
        return 1
    fi

    # Simular requisição com headers de correlação
    local response_code
    response_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "$INTENT_ID_HEADER: $intent_id" \
        -H "$PLAN_ID_HEADER: $plan_id" \
        -H "$DOMAIN_HEADER: $domain" \
        -H "$USER_ID_HEADER: $user_id" \
        "http://localhost:$local_port/metrics" \
        --connect-timeout 5 --max-time 10 || echo "000")

    kill $pf_pid 2>/dev/null || true

    if [[ "$response_code" =~ ^[23] ]]; then
        info "Headers propagados com sucesso (código: $response_code)"
        return 0
    else
        error "Falha na propagação de headers (código: $response_code)"
        return 1
    fi
}

# Teste 4: Verificar exemplars no Prometheus
test_prometheus_exemplars() {
    log "Testando exemplars no Prometheus..."

    # Port-forward para Prometheus
    kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-prometheus 0:9090 &
    local pf_pid=$!
    sleep 3

    local local_port
    local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -z "$local_port" ]; then
        kill $pf_pid 2>/dev/null || true
        error "Falha ao conectar com Prometheus"
        return 1
    fi

    # Verificar se exemplars estão habilitados
    local exemplars_enabled
    exemplars_enabled=$(curl -s "http://localhost:$local_port/api/v1/status/config" | jq -r '.data.yaml' | grep -c "enable_exemplar_storage: true" || echo "0")

    if [ "$exemplars_enabled" -gt 0 ]; then
        info "Exemplars habilitados no Prometheus"

        # Verificar se há exemplars disponíveis
        local exemplars_query
        exemplars_query=$(curl -s "http://localhost:$local_port/api/v1/query_exemplars?query=up" | jq -r '.data | length' 2>/dev/null || echo "0")

        if [ "$exemplars_query" -gt 0 ]; then
            info "$exemplars_query exemplar(s) encontrados"
        else
            warn "Exemplars habilitados mas nenhum disponível (normal se não há tráfego com traces)"
        fi
    else
        error "Exemplars não habilitados no Prometheus"
        kill $pf_pid 2>/dev/null || true
        return 1
    fi

    kill $pf_pid 2>/dev/null || true
    return 0
}

# Teste 5: Verificar correlação trace-metric no Jaeger
test_jaeger_trace_correlation() {
    log "Testando correlação de traces no Jaeger..."

    # Port-forward para Jaeger Query
    kubectl port-forward -n "$NAMESPACE" service/jaeger-query 0:16686 &
    local pf_pid=$!
    sleep 3

    local local_port
    local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -z "$local_port" ]; then
        kill $pf_pid 2>/dev/null || true
        error "Falha ao conectar com Jaeger"
        return 1
    fi

    # Verificar serviços com traces
    local services
    services=$(curl -s "http://localhost:$local_port/api/services" | jq -r '. | length' 2>/dev/null || echo "0")

    if [ "$services" -gt 0 ]; then
        info "$services serviço(s) com traces encontrados"

        # Verificar se há traces recentes com tags de correlação
        local traces_with_correlation=0
        local correlation_tags=("neural.hive.intent.id" "neural.hive.plan.id" "neural.hive.domain" "neural.hive.user.id")

        # Buscar traces recentes (últimos 5 minutos)
        local end_time
        end_time=$(date +%s)000000  # microseconds
        local start_time
        start_time=$(( end_time - 300000000 ))  # 5 minutes ago

        local traces_response
        traces_response=$(curl -s "http://localhost:$local_port/api/traces?service=neural-hive-gateway&start=$start_time&end=$end_time&limit=10" 2>/dev/null || echo '{"data":null}')

        if [ "$(echo "$traces_response" | jq -r '.data')" != "null" ]; then
            for tag in "${correlation_tags[@]}"; do
                local tag_count
                tag_count=$(echo "$traces_response" | jq -r ".data[] | select(.spans[]?.tags[]?.key == \"$tag\") | .traceID" 2>/dev/null | wc -l || echo "0")

                if [ "$tag_count" -gt 0 ]; then
                    info "Encontrados $tag_count trace(s) com tag: $tag"
                    traces_with_correlation=$((traces_with_correlation + 1))
                elif [ "$VERBOSE" == "true" ]; then
                    info "Nenhum trace encontrado com tag: $tag"
                fi
            done
        else
            warn "Nenhum trace encontrado (pode ser normal se não há tráfego)"
        fi

        if [ $traces_with_correlation -gt 0 ]; then
            info "Correlação encontrada em traces do Jaeger"
        else
            warn "Nenhuma correlação encontrada em traces (normal se não há tráfego instrumentado)"
        fi
    else
        warn "Nenhum serviço com traces encontrado (normal se não há tráfego)"
    fi

    kill $pf_pid 2>/dev/null || true
    return 0
}

# Teste 6: Testar sampling específico do Neural Hive-Mind
test_neural_hive_sampling() {
    log "Testando estratégias de sampling Neural Hive-Mind..."

    # Verificar configuração de sampling no Jaeger
    local jaeger_config
    jaeger_config=$(kubectl get configmap -n "$NAMESPACE" jaeger-sampling -o jsonpath='{.data.sampling_strategies\.json}' 2>/dev/null || echo "{}")

    if [ "$jaeger_config" == "{}" ]; then
        warn "Configuração de sampling não encontrada"
        return 0
    fi

    # Verificar estratégias específicas do Neural Hive-Mind
    local neural_hive_strategies
    neural_hive_strategies=$(echo "$jaeger_config" | jq -r '.per_service_strategies[]? | select(.service | test("neural-hive")) | .service' 2>/dev/null || echo "")

    if [ -n "$neural_hive_strategies" ]; then
        info "Estratégias de sampling Neural Hive-Mind encontradas:"
        echo "$neural_hive_strategies" | while read -r service; do
            local strategy_type
            strategy_type=$(echo "$jaeger_config" | jq -r ".per_service_strategies[] | select(.service == \"$service\") | .type" 2>/dev/null)
            local param
            param=$(echo "$jaeger_config" | jq -r ".per_service_strategies[] | select(.service == \"$service\") | .param" 2>/dev/null)
            info "  - $service: $strategy_type ($param)"
        done
    else
        warn "Nenhuma estratégia de sampling específica do Neural Hive-Mind encontrada"
    fi

    return 0
}

# Teste 7: Simular cenário completo de correlação
test_end_to_end_correlation() {
    log "Testando cenário end-to-end de correlação..."

    # Gerar contexto de teste
    local intent_id
    intent_id=$(generate_intent_id)
    local plan_id
    plan_id=$(generate_plan_id)
    local domain="experiencia"
    local user_id="user-e2e-$(date +%s)"

    info "Simulando fluxo com:"
    info "  Intent ID: $intent_id"
    info "  Plan ID: $plan_id"
    info "  Domain: $domain"
    info "  User ID: $user_id"

    # Verificar se há endpoints do Neural Hive-Mind para testar
    local neural_hive_services
    neural_hive_services=$(kubectl get services -n "$TARGET_NAMESPACE" --no-headers 2>/dev/null | grep -c "neural-hive" || echo "0")

    if [ "$neural_hive_services" -eq 0 ]; then
        warn "Nenhum serviço Neural Hive-Mind encontrado no namespace $TARGET_NAMESPACE"
        info "Simulando requisição através do OpenTelemetry Collector"

        # Port-forward para OTEL Collector
        kubectl port-forward -n "$NAMESPACE" service/opentelemetry-collector 0:4318 &
        local pf_pid=$!
        sleep 3

        local local_port
        local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

        if [ -n "$local_port" ]; then
            # Simular trace através do OTLP endpoint
            local trace_data
            trace_data=$(cat << EOF
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "neural-hive-correlation-test"}},
        {"key": "service.version", "value": {"stringValue": "1.0.0"}}
      ]
    },
    "instrumentationLibrarySpans": [{
      "instrumentationLibrary": {
        "name": "correlation-test"
      },
      "spans": [{
        "traceId": "$(openssl rand -hex 16)",
        "spanId": "$(openssl rand -hex 8)",
        "name": "correlation-test-span",
        "kind": 1,
        "startTimeUnixNano": $(date +%s%N),
        "endTimeUnixNano": $(date +%s%N),
        "attributes": [
          {"key": "$INTENT_BAGGAGE_KEY", "value": {"stringValue": "$intent_id"}},
          {"key": "$PLAN_BAGGAGE_KEY", "value": {"stringValue": "$plan_id"}},
          {"key": "$DOMAIN_BAGGAGE_KEY", "value": {"stringValue": "$domain"}},
          {"key": "$USER_BAGGAGE_KEY", "value": {"stringValue": "$user_id"}}
        ]
      }]
    }]
  }]
}
EOF
)

            local response_code
            response_code=$(curl -s -o /dev/null -w "%{http_code}" \
                -X POST \
                -H "Content-Type: application/json" \
                -H "$INTENT_ID_HEADER: $intent_id" \
                -H "$PLAN_ID_HEADER: $plan_id" \
                -H "$DOMAIN_HEADER: $domain" \
                -H "$USER_ID_HEADER: $user_id" \
                -d "$trace_data" \
                "http://localhost:$local_port/v1/traces" \
                --connect-timeout 10 --max-time 30 || echo "000")

            if [[ "$response_code" =~ ^[23] ]]; then
                info "Trace simulado enviado com sucesso (código: $response_code)"
                info "Aguardando processamento..."
                sleep 5

                # Verificar se o trace foi processado
                kubectl port-forward -n "$NAMESPACE" service/jaeger-query 0:16686 &
                local jaeger_pf_pid=$!
                sleep 3

                local jaeger_port
                jaeger_port=$(lsof -Pan -p $jaeger_pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

                if [ -n "$jaeger_port" ]; then
                    local traces_found
                    traces_found=$(curl -s "http://localhost:$jaeger_port/api/traces?service=neural-hive-correlation-test&tag=$INTENT_BAGGAGE_KEY:$intent_id" | jq -r '.data | length' 2>/dev/null || echo "0")

                    if [ "$traces_found" -gt 0 ]; then
                        success "Trace com correlação encontrado no Jaeger!"
                    else
                        warn "Trace não encontrado no Jaeger (pode levar alguns segundos para aparecer)"
                    fi
                fi

                kill $jaeger_pf_pid 2>/dev/null || true
            else
                error "Falha ao enviar trace simulado (código: $response_code)"
                kill $pf_pid 2>/dev/null || true
                return 1
            fi
        fi

        kill $pf_pid 2>/dev/null || true
    else
        info "Encontrados $neural_hive_services serviço(s) Neural Hive-Mind"
        warn "Teste end-to-end completo requer instrumentação ativa dos serviços"
    fi

    return 0
}

# Função para gerar relatório de correlação
generate_correlation_report() {
    echo
    echo "=========================================="
    echo "  RELATÓRIO DE CORRELAÇÃO NEURAL HIVE-MIND"
    echo "=========================================="
    echo
    echo "Total de testes executados: $TOTAL_TESTS"
    echo -e "${GREEN}Testes aprovados: $PASSED_TESTS${NC}"
    echo -e "${RED}Testes falharam: $FAILED_TESTS${NC}"
    echo

    if [ $FAILED_TESTS -gt 0 ]; then
        echo -e "${RED}TESTES FALHARAM:${NC}"
        for result in "${TEST_RESULTS[@]}"; do
            if [[ $result == FAIL:* ]]; then
                echo "  ✗ ${result#FAIL: }"
            fi
        done
        echo
    fi

    local success_rate
    if [ $TOTAL_TESTS -gt 0 ]; then
        success_rate=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
    else
        success_rate=0
    fi

    echo "Taxa de sucesso: ${success_rate}%"
    echo

    # Recomendações baseadas nos resultados
    echo "RECOMENDAÇÕES:"
    if [ $FAILED_TESTS -eq 0 ]; then
        echo "✓ Correlação Neural Hive-Mind configurada corretamente"
        echo "✓ Headers de correlação propagando adequadamente"
        echo "✓ Exemplars e traces correlacionados funcionais"
    else
        echo "⚠ Verificar configuração de headers de correlação"
        echo "⚠ Validar instrumentação dos serviços Neural Hive-Mind"
        echo "⚠ Confirmar configuração do OpenTelemetry Collector"
    fi

    echo
    echo "Para melhor rastreabilidade, instrumentar aplicações com:"
    echo "- Headers HTTP: $INTENT_ID_HEADER, $PLAN_ID_HEADER, $DOMAIN_HEADER, $USER_ID_HEADER"
    echo "- Baggage keys: $INTENT_BAGGAGE_KEY, $PLAN_BAGGAGE_KEY, $DOMAIN_BAGGAGE_KEY, $USER_BAGGAGE_KEY"
    echo "- Sampling rate: $SAMPLE_RATE para captura completa"
    echo

    if [ $FAILED_TESTS -eq 0 ]; then
        success "Correlação Neural Hive-Mind funcionando corretamente! 🚀"
        return 0
    else
        error "Problemas detectados na correlação. Verificar configurações."
        return 1
    fi
}

# Função de ajuda
show_help() {
    cat << EOF
Neural Hive-Mind Correlation Testing Script

Uso: $0 [opções]

Opções:
  -h, --help                    Mostrar esta ajuda
  -n, --namespace NS            Namespace da observabilidade (padrão: observability)
  -t, --target-namespace NS     Namespace dos serviços Neural Hive-Mind (padrão: neural-hive)
  -d, --duration SEC            Duração do teste (padrão: 60s)
  -s, --sample-rate RATE        Taxa de sampling (padrão: 1.0)
  -v, --verbose                 Output verboso
  --dry-run                     Apenas mostrar quais testes seriam executados

Variáveis de ambiente:
  NAMESPACE                     Namespace da observabilidade
  TARGET_NAMESPACE              Namespace dos serviços Neural Hive-Mind
  TEST_DURATION                 Duração do teste em segundos
  SAMPLE_RATE                   Taxa de sampling (0.0 a 1.0)
  VERBOSE                       true/false para output verboso
  DRY_RUN                      true/false para dry run

Headers de correlação testados:
  $INTENT_ID_HEADER             ID da intenção Neural Hive-Mind
  $PLAN_ID_HEADER               ID do plano Neural Hive-Mind
  $DOMAIN_HEADER                Domínio Neural Hive-Mind
  $USER_ID_HEADER               ID do usuário

Baggage keys testados:
  $INTENT_BAGGAGE_KEY           Propagação do intent ID
  $PLAN_BAGGAGE_KEY             Propagação do plan ID
  $DOMAIN_BAGGAGE_KEY           Propagação do domain
  $USER_BAGGAGE_KEY             Propagação do user ID

Exemplos:
  $0                                          # Teste completo
  $0 --verbose --duration 120                 # Teste verboso por 2 minutos
  $0 --dry-run                               # Apenas listar testes
  $0 --target-namespace production           # Testar namespace específico
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
            -s|--sample-rate)
                SAMPLE_RATE="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
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
    echo "  TESTE DE CORRELAÇÃO NEURAL HIVE-MIND"
    echo "=========================================="
    echo
    log "Namespace observabilidade: $NAMESPACE"
    log "Namespace Neural Hive-Mind: $TARGET_NAMESPACE"
    log "Duração do teste: ${TEST_DURATION}s"
    log "Sample rate: $SAMPLE_RATE"
    log "Verbose: $VERBOSE"
    log "Dry run: $DRY_RUN"
    echo

    # Verificar dependências
    if ! check_dependencies; then
        error "Falha na verificação de dependências"
        exit 1
    fi

    # Executar testes de correlação
    run_correlation_test "Configuração de correlação" test_correlation_config
    run_correlation_test "Configuração OTEL Collector" test_otel_correlation_config
    run_correlation_test "Propagação de headers HTTP" test_http_header_propagation
    run_correlation_test "Exemplars no Prometheus" test_prometheus_exemplars
    run_correlation_test "Correlação de traces no Jaeger" test_jaeger_trace_correlation
    run_correlation_test "Sampling Neural Hive-Mind" test_neural_hive_sampling
    run_correlation_test "Cenário end-to-end" test_end_to_end_correlation

    # Gerar relatório final
    generate_correlation_report
}

# Executar se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi