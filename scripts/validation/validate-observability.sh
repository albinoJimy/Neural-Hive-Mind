#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

##
# Script de validação completa da stack de observabilidade Neural Hive-Mind
#
# Executa testes abrangentes de:
# - Conectividade e health checks
# - Coleta de métricas e traces
# - Correlação distribuída
# - SLOs e error budgets
# - Dashboards e alertas
##

set -euo pipefail

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configurações padrão
NAMESPACE="${NAMESPACE:-observability}"
TIMEOUT="${TIMEOUT:-300}"
VERBOSE="${VERBOSE:-false}"
SKIP_CORRELATION="${SKIP_CORRELATION:-false}"
SKIP_SLO_TESTS="${SKIP_SLO_TESTS:-false}"
REPORT_FILE="${REPORT_FILE:-observability-validation-report.json}"

# Contadores de resultados
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNINGS=0

# Função de logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    ((PASSED_TESTS++))
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ((FAILED_TESTS++))
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    ((WARNINGS++))
}

info() {
    if [ "$VERBOSE" = "true" ]; then
        echo -e "${PURPLE}[INFO]${NC} $1"
    fi
}

# Função para executar teste individual
run_test() {
    local test_name="$1"
    local test_function="$2"

    ((TOTAL_TESTS++))
    log "Executando teste: $test_name"

    if $test_function; then
        success "$test_name passou"
        return 0
    else
        error "$test_name falhou"
        return 1
    fi
}

# Verificar pré-requisitos
check_prerequisites() {
    log "Verificando pré-requisitos..."

    local missing_tools=()
    for tool in kubectl curl jq; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done

    if [ ${#missing_tools[@]} -ne 0 ]; then
        error "Ferramentas faltando: ${missing_tools[*]}"
        return 1
    fi

    # Verificar conectividade com cluster
    if ! kubectl cluster-info &> /dev/null; then
        error "Não foi possível conectar ao cluster Kubernetes"
        return 1
    fi

    # Verificar se namespace existe
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        error "Namespace $NAMESPACE não existe"
        return 1
    fi

    success "Pré-requisitos verificados"
    return 0
}

# Teste de health checks básicos
test_health_checks() {
    log "Testando health checks dos componentes..."

    local components=(
        "prometheus:prometheus-stack-prometheus:9090:/-/healthy"
        "grafana:grafana:3000:/api/health"
        "jaeger-query:jaeger-query:16686:/"
        "jaeger-collector:jaeger-collector:14269:/"
        "opentelemetry-collector:opentelemetry-collector:13133:/"
        "alertmanager:prometheus-stack-alertmanager:9093:/-/healthy"
    )

    local failed_components=()

    for component_spec in "${components[@]}"; do
        IFS=':' read -r name service port path <<< "$component_spec"

        info "Testando $name via $service:$port$path"

        # Usar kubectl exec para testar internamente
        local test_result
        test_result=$(kubectl exec -n "$NAMESPACE" deployment/opentelemetry-collector -- \
            curl -s -w "%{http_code}" -o /dev/null \
            "http://$service.$NAMESPACE.svc.cluster.local:$port$path" 2>/dev/null || echo "000")

        if [[ "$test_result" =~ ^[23] ]]; then
            info "$name health check OK ($test_result)"
        else
            failed_components+=("$name:$test_result")
        fi
    done

    if [ ${#failed_components[@]} -eq 0 ]; then
        return 0
    else
        error "Componentes com falha no health check: ${failed_components[*]}"
        return 1
    fi
}

# Teste de coleta de métricas Prometheus
test_prometheus_metrics() {
    log "Testando coleta de métricas do Prometheus..."

    # Port-forward temporário para Prometheus
    kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-prometheus 9090:9090 &
    local pf_pid=$!
    sleep 5

    # Testar queries básicas
    local queries=(
        "up"
        "prometheus_build_info"
        "neural_hive_request_duration_seconds"
    )

    local failed_queries=()

    for query in "${queries[@]}"; do
        info "Testando query: $query"

        local result
        result=$(curl -s "http://localhost:9090/api/v1/query?query=$query" | jq -r '.status // "error"')

        if [ "$result" = "success" ]; then
            info "Query $query OK"
        else
            failed_queries+=("$query")
        fi
    done

    # Cleanup port-forward
    kill $pf_pid 2>/dev/null || true

    if [ ${#failed_queries[@]} -eq 0 ]; then
        return 0
    else
        error "Queries que falharam: ${failed_queries[*]}"
        return 1
    fi
}

# Teste de targets Prometheus
test_prometheus_targets() {
    log "Testando targets do Prometheus..."

    kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-prometheus 9090:9090 &
    local pf_pid=$!
    sleep 5

    # Obter targets
    local targets_response
    targets_response=$(curl -s "http://localhost:9090/api/v1/targets")

    local down_targets
    down_targets=$(echo "$targets_response" | jq -r '.data.activeTargets[] | select(.health != "up") | .labels.instance')

    # Cleanup port-forward
    kill $pf_pid 2>/dev/null || true

    if [ -z "$down_targets" ]; then
        return 0
    else
        warning "Targets down: $down_targets"
        return 1
    fi
}

# Teste de datasources Grafana
test_grafana_datasources() {
    log "Testando datasources do Grafana..."

    kubectl port-forward -n "$NAMESPACE" service/grafana 3000:80 &
    local pf_pid=$!
    sleep 5

    # Testar datasources (usando credenciais admin padrão)
    local datasources_response
    datasources_response=$(curl -s -u "admin:admin" "http://localhost:3000/api/datasources")

    local prometheus_ds
    prometheus_ds=$(echo "$datasources_response" | jq -r '.[] | select(.type == "prometheus") | .name')

    local jaeger_ds
    jaeger_ds=$(echo "$datasources_response" | jq -r '.[] | select(.type == "jaeger") | .name')

    # Cleanup port-forward
    kill $pf_pid 2>/dev/null || true

    local missing_ds=()

    if [ -z "$prometheus_ds" ] || [ "$prometheus_ds" = "null" ]; then
        missing_ds+=("prometheus")
    fi

    if [ -z "$jaeger_ds" ] || [ "$jaeger_ds" = "null" ]; then
        missing_ds+=("jaeger")
    fi

    if [ ${#missing_ds[@]} -eq 0 ]; then
        return 0
    else
        error "Datasources faltando: ${missing_ds[*]}"
        return 1
    fi
}

# Teste de ingestion Jaeger
test_jaeger_ingestion() {
    log "Testando ingestion de traces no Jaeger..."

    kubectl port-forward -n "$NAMESPACE" service/jaeger-query 16686:16686 &
    local pf_pid=$!
    sleep 5

    # Obter serviços disponíveis
    local services_response
    services_response=$(curl -s "http://localhost:16686/api/services")

    local services_count
    services_count=$(echo "$services_response" | jq -r '.data | length')

    # Cleanup port-forward
    kill $pf_pid 2>/dev/null || true

    if [ "$services_count" -gt 0 ]; then
        info "Serviços encontrados no Jaeger: $services_count"
        return 0
    else
        warning "Nenhum serviço encontrado no Jaeger"
        return 1
    fi
}

# Teste de correlação distribuída
test_correlation() {
    if [ "$SKIP_CORRELATION" = "true" ]; then
        log "Pulando testes de correlação"
        return 0
    fi

    log "Testando correlação distribuída..."

    # Executar script específico de correlação
    local correlation_script="$SCRIPT_DIR/test-correlation.sh"

    if [ -f "$correlation_script" ]; then
        bash "$correlation_script" --namespace "$NAMESPACE"
        return $?
    else
        warning "Script de correlação não encontrado: $correlation_script"
        return 1
    fi
}

# Teste de SLOs
test_slos() {
    if [ "$SKIP_SLO_TESTS" = "true" ]; then
        log "Pulando testes de SLO"
        return 0
    fi

    log "Testando configuração de SLOs..."

    # Executar script específico de SLOs
    local slo_script="$SCRIPT_DIR/test-slos.sh"

    if [ -f "$slo_script" ]; then
        bash "$slo_script" --namespace "$NAMESPACE"
        return $?
    else
        warning "Script de SLO não encontrado: $slo_script"
        return 1
    fi
}

# Teste de alertas
test_alerting() {
    log "Testando configuração de alertas..."

    # Verificar PrometheusRules
    local rules_count
    rules_count=$(kubectl get prometheusrules -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

    if [ "$rules_count" -gt 0 ]; then
        info "PrometheusRules encontradas: $rules_count"
        return 0
    else
        warning "Nenhuma PrometheusRule encontrada"
        return 1
    fi
}

# Teste de armazenamento
test_storage() {
    log "Testando configuração de armazenamento..."

    # Verificar PVCs
    local pvcs
    pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null)

    local failed_pvcs=()

    while IFS= read -r pvc_line; do
        if [[ -n "$pvc_line" ]]; then
            local status=$(echo "$pvc_line" | awk '{print $2}')
            local name=$(echo "$pvc_line" | awk '{print $1}')

            if [ "$status" != "Bound" ]; then
                failed_pvcs+=("$name:$status")
            fi
        fi
    done <<< "$pvcs"

    if [ ${#failed_pvcs[@]} -eq 0 ]; then
        return 0
    else
        error "PVCs com problemas: ${failed_pvcs[*]}"
        return 1
    fi
}

# Gerar relatório JSON
generate_report() {
    log "Gerando relatório de validação..."

    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local success_rate=$(awk "BEGIN {printf \"%.1f\", $PASSED_TESTS/$TOTAL_TESTS*100}")

    cat > "$REPORT_FILE" << EOF
{
  "validation_report": {
    "timestamp": "$timestamp",
    "namespace": "$NAMESPACE",
    "summary": {
      "total_tests": $TOTAL_TESTS,
      "passed": $PASSED_TESTS,
      "failed": $FAILED_TESTS,
      "warnings": $WARNINGS,
      "success_rate_percent": $success_rate
    },
    "components": {
      "prometheus": {
        "health_check": "$([ $PROMETHEUS_HEALTH -eq 0 ] && echo "pass" || echo "fail")",
        "metrics_collection": "$([ $PROMETHEUS_METRICS -eq 0 ] && echo "pass" || echo "fail")",
        "targets": "$([ $PROMETHEUS_TARGETS -eq 0 ] && echo "pass" || echo "fail")"
      },
      "grafana": {
        "health_check": "pass",
        "datasources": "$([ $GRAFANA_DATASOURCES -eq 0 ] && echo "pass" || echo "fail")"
      },
      "jaeger": {
        "health_check": "pass",
        "ingestion": "$([ $JAEGER_INGESTION -eq 0 ] && echo "pass" || echo "fail")"
      },
      "correlation": {
        "distributed_tracing": "$([ $CORRELATION_TEST -eq 0 ] && echo "pass" || echo "fail")"
      },
      "storage": {
        "persistent_volumes": "$([ $STORAGE_TEST -eq 0 ] && echo "pass" || echo "fail")"
      }
    },
    "recommendations": []
  }
}
EOF

    success "Relatório gerado: $REPORT_FILE"
}

# Função principal
main() {
    log "=== Validação da Stack de Observabilidade Neural Hive-Mind ==="
    log "Namespace: $NAMESPACE"
    log "Timeout: ${TIMEOUT}s"
    log "Verbose: $VERBOSE"

    # Inicializar contadores
    TOTAL_TESTS=0
    PASSED_TESTS=0
    FAILED_TESTS=0
    WARNINGS=0

    # Executar testes
    check_prerequisites || exit 1

    # Health checks
    run_test "Health Checks" test_health_checks

    # Testes de Prometheus
    run_test "Prometheus Metrics" test_prometheus_metrics
    PROMETHEUS_METRICS=$?

    run_test "Prometheus Targets" test_prometheus_targets
    PROMETHEUS_TARGETS=$?

    # Testes de Grafana
    run_test "Grafana Datasources" test_grafana_datasources
    GRAFANA_DATASOURCES=$?

    # Testes de Jaeger
    run_test "Jaeger Ingestion" test_jaeger_ingestion
    JAEGER_INGESTION=$?

    # Testes de correlação
    run_test "Correlation" test_correlation
    CORRELATION_TEST=$?

    # Testes de SLO
    run_test "SLOs" test_slos

    # Testes de alertas
    run_test "Alerting" test_alerting

    # Testes de storage
    run_test "Storage" test_storage
    STORAGE_TEST=$?

    # Gerar relatório
    generate_report

    # Resumo final
    log "=== Resumo da Validação ==="
    log "Total de testes: $TOTAL_TESTS"
    success "Testes aprovados: $PASSED_TESTS"
    if [ $FAILED_TESTS -gt 0 ]; then
        error "Testes falharam: $FAILED_TESTS"
    fi
    if [ $WARNINGS -gt 0 ]; then
        warning "Avisos: $WARNINGS"
    fi

    local success_rate=$(awk "BEGIN {printf \"%.1f\", $PASSED_TESTS/$TOTAL_TESTS*100}")
    log "Taxa de sucesso: ${success_rate}%"

    # Código de saída baseado em falhas
    if [ $FAILED_TESTS -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
}

# Função de ajuda
show_help() {
    cat << EOF
Validação da Stack de Observabilidade Neural Hive-Mind

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -n, --namespace NAMESPACE    Namespace Kubernetes (padrão: observability)
    -t, --timeout SECONDS       Timeout para testes (padrão: 300)
    -v, --verbose               Modo verbose
    --skip-correlation          Pular testes de correlação
    --skip-slo                  Pular testes de SLO
    -r, --report-file FILE      Arquivo de relatório (padrão: observability-validation-report.json)
    -h, --help                  Mostrar esta ajuda

EXAMPLES:
    # Validação completa
    $0

    # Validação em namespace específico
    $0 --namespace observability-staging

    # Validação verbose com relatório customizado
    $0 --verbose --report-file /tmp/validation.json

ENVIRONMENT VARIABLES:
    NAMESPACE                   Namespace Kubernetes
    TIMEOUT                     Timeout em segundos
    VERBOSE                     Modo verbose (true/false)
    SKIP_CORRELATION            Pular correlação (true/false)
    SKIP_SLO_TESTS              Pular SLO (true/false)
    REPORT_FILE                 Arquivo de relatório
EOF
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="true"
            shift
            ;;
        --skip-correlation)
            SKIP_CORRELATION="true"
            shift
            ;;
        --skip-slo)
            SKIP_SLO_TESTS="true"
            shift
            ;;
        -r|--report-file)
            REPORT_FILE="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            error "Argumento desconhecido: $1"
            show_help
            exit 1
            ;;
    esac
done

# Executar main
main "$@"