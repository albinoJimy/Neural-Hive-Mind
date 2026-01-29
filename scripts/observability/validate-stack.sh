#!/bin/bash

# Comprehensive Validation Script for Neural Hive-Mind Observability Stack
# Este script executa validação completa da stack de observabilidade

set -euo pipefail

# Configurações
NAMESPACE="${NAMESPACE:-observability}"
TIMEOUT="${TIMEOUT:-300}"
VERBOSE="${VERBOSE:-false}"
CORRELATION_TEST="${CORRELATION_TEST:-true}"
SLO_TEST="${SLO_TEST:-true}"
DRY_RUN="${DRY_RUN:-false}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Contadores para relatório final
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Arrays para armazenar resultados
declare -a FAILED_TESTS_LIST=()
declare -a SKIPPED_TESTS_LIST=()

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

# Função para executar teste
run_test() {
    local test_name="$1"
    local test_function="$2"
    local required="${3:-true}"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$DRY_RUN" == "true" ]; then
        info "[DRY-RUN] Seria executado: $test_name"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
        SKIPPED_TESTS_LIST+=("$test_name (dry-run)")
        return
    fi

    log "Executando teste: $test_name"

    if $test_function; then
        success "✓ $test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        if [ "$required" == "true" ]; then
            error "✗ $test_name (CRÍTICO)"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            FAILED_TESTS_LIST+=("$test_name (crítico)")
        else
            warn "⚠ $test_name (OPCIONAL)"
            SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
            SKIPPED_TESTS_LIST+=("$test_name (opcional)")
        fi
    fi
}

# Função para verificar dependências
check_dependencies() {
    log "Verificando dependências..."

    local deps=("kubectl" "curl" "jq" "helm")
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

# Teste 1: Verificar namespace e recursos básicos
test_namespace_resources() {
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        error "Namespace $NAMESPACE não encontrado"
        return 1
    fi

    # Verificar se os recursos básicos existem
    local resources=("deployment" "service" "configmap" "secret")

    for resource in "${resources[@]}"; do
        local count
        count=$(kubectl get "$resource" -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
        if [ "$count" -eq 0 ]; then
            warn "Nenhum $resource encontrado no namespace $NAMESPACE"
        else
            [ "$VERBOSE" == "true" ] && info "Encontrados $count $resource(s)"
        fi
    done

    return 0
}

# Teste 2: Verificar pods em execução
test_pods_running() {
    local pods_not_ready=0

    # Listar todos os pods e verificar status
    while IFS= read -r line; do
        if [[ $line == *"0/"* ]] || [[ $line == *"Pending"* ]] || [[ $line == *"Error"* ]] || [[ $line == *"CrashLoopBackOff"* ]]; then
            error "Pod com problema: $line"
            pods_not_ready=$((pods_not_ready + 1))
        elif [ "$VERBOSE" == "true" ]; then
            info "Pod OK: $line"
        fi
    done < <(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ $pods_not_ready -gt 0 ]; then
        error "$pods_not_ready pod(s) não estão ready"
        return 1
    fi

    return 0
}

# Teste 3: Verificar services e endpoints
test_services_endpoints() {
    local failed=0

    # Verificar services principais
    local services=(
        "prometheus-stack-prometheus:9090"
        "grafana:3000"
        "jaeger-query:16686"
        "opentelemetry-collector:4317"
        "prometheus-stack-alertmanager:9093"
    )

    for service_port in "${services[@]}"; do
        local service="${service_port%:*}"
        local port="${service_port#*:}"

        if ! kubectl get service "$service" -n "$NAMESPACE" &> /dev/null; then
            error "Service não encontrado: $service"
            failed=$((failed + 1))
            continue
        fi

        # Verificar endpoints
        local endpoints
        endpoints=$(kubectl get endpoints "$service" -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || echo "")

        if [ -z "$endpoints" ]; then
            error "Service $service não tem endpoints disponíveis"
            failed=$((failed + 1))
        elif [ "$VERBOSE" == "true" ]; then
            info "Service $service tem endpoints: $endpoints"
        fi
    done

    [ $failed -eq 0 ]
}

# Teste 4: Verificar conectividade HTTP dos serviços
test_http_connectivity() {
    local failed=0

    # Port-forward temporário para testar conectividade
    local services=(
        "prometheus-stack-prometheus:9090:/-/healthy"
        "grafana:3000:/api/health"
        "jaeger-query:16686:/"
        "opentelemetry-collector:8888:/metrics"
        "prometheus-stack-alertmanager:9093:/-/healthy"
    )

    for service_config in "${services[@]}"; do
        IFS=':' read -r service port path <<< "$service_config"

        log "Testando conectividade HTTP: $service"

        # Iniciar port-forward em background
        kubectl port-forward -n "$NAMESPACE" "service/$service" "0:$port" &
        local pf_pid=$!
        sleep 2

        # Obter porta local atribuída
        local local_port
        local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

        if [ -z "$local_port" ]; then
            error "Falha ao obter porta local para $service"
            kill $pf_pid 2>/dev/null || true
            failed=$((failed + 1))
            continue
        fi

        # Testar conectividade
        local response_code
        response_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$local_port$path" --connect-timeout 5 --max-time 10 || echo "000")

        # Limpar port-forward
        kill $pf_pid 2>/dev/null || true
        sleep 1

        if [[ "$response_code" =~ ^[23] ]]; then
            [ "$VERBOSE" == "true" ] && info "$service respondeu com código $response_code"
        else
            error "$service falhou com código $response_code"
            failed=$((failed + 1))
        fi
    done

    [ $failed -eq 0 ]
}

# Teste 5: Verificar métricas do Prometheus
test_prometheus_metrics() {
    log "Testando métricas do Prometheus..."

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

    local failed=0

    # Verificar métricas essenciais
    local metrics=(
        "up"
        "prometheus_notifications_total"
        "prometheus_config_last_reload_successful"
        "neural_hive_requests_total"
    )

    for metric in "${metrics[@]}"; do
        local result
        result=$(curl -s "http://localhost:$local_port/api/v1/query?query=$metric" | jq -r '.status' 2>/dev/null || echo "error")

        if [ "$result" == "success" ]; then
            [ "$VERBOSE" == "true" ] && info "Métrica disponível: $metric"
        else
            if [ "$metric" == "neural_hive_requests_total" ]; then
                warn "Métrica personalizada não encontrada: $metric (pode ser normal se não há tráfego)"
            else
                error "Métrica não disponível: $metric"
                failed=$((failed + 1))
            fi
        fi
    done

    # Verificar targets
    local targets_up
    targets_up=$(curl -s "http://localhost:$local_port/api/v1/targets" | jq -r '.data.activeTargets | map(select(.health == "up")) | length' 2>/dev/null || echo "0")

    if [ "$targets_up" -gt 0 ]; then
        info "$targets_up target(s) ativos no Prometheus"
    else
        error "Nenhum target ativo no Prometheus"
        failed=$((failed + 1))
    fi

    kill $pf_pid 2>/dev/null || true

    [ $failed -eq 0 ]
}

# Teste 6: Verificar dashboards do Grafana
test_grafana_dashboards() {
    log "Testando dashboards do Grafana..."

    # Port-forward para Grafana
    kubectl port-forward -n "$NAMESPACE" service/grafana 0:3000 &
    local pf_pid=$!
    sleep 3

    local local_port
    local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -z "$local_port" ]; then
        kill $pf_pid 2>/dev/null || true
        error "Falha ao conectar com Grafana"
        return 1
    fi

    # Obter credenciais do admin
    local admin_password
    admin_password=$(kubectl get secret -n "$NAMESPACE" grafana -o jsonpath='{.data.admin-password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")

    if [ -z "$admin_password" ]; then
        warn "Senha do admin do Grafana não encontrada, usando 'admin'"
        admin_password="admin"
    fi

    # Testar login e listar dashboards
    local auth_header="Authorization: Basic $(echo -n "admin:$admin_password" | base64)"
    local dashboards_count
    dashboards_count=$(curl -s -H "$auth_header" "http://localhost:$local_port/api/search?type=dash-db" | jq '. | length' 2>/dev/null || echo "0")

    kill $pf_pid 2>/dev/null || true

    if [ "$dashboards_count" -gt 0 ]; then
        info "$dashboards_count dashboard(s) encontrados no Grafana"
        return 0
    else
        error "Nenhum dashboard encontrado no Grafana"
        return 1
    fi
}

# Teste 7: Verificar traces no Jaeger
test_jaeger_traces() {
    log "Testando traces no Jaeger..."

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

    # Verificar serviços disponíveis
    local services_count
    services_count=$(curl -s "http://localhost:$local_port/api/services" | jq '. | length' 2>/dev/null || echo "0")

    kill $pf_pid 2>/dev/null || true

    if [ "$services_count" -gt 0 ]; then
        info "$services_count serviço(s) com traces no Jaeger"
        return 0
    else
        warn "Nenhum serviço com traces encontrado no Jaeger (pode ser normal se não há tráfego)"
        return 0  # Não é um erro crítico se não há traces ainda
    fi
}

# Teste 8: Verificar configurações do OpenTelemetry Collector
test_otel_collector_config() {
    log "Testando configuração do OpenTelemetry Collector..."

    # Verificar se o ConfigMap existe
    if ! kubectl get configmap -n "$NAMESPACE" opentelemetry-collector -o yaml &> /dev/null; then
        error "ConfigMap do OpenTelemetry Collector não encontrado"
        return 1
    fi

    # Verificar métricas do collector
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

    # Verificar métricas internas do collector
    local metrics_available
    metrics_available=$(curl -s "http://localhost:$local_port/metrics" | grep -c "otelcol_" || echo "0")

    kill $pf_pid 2>/dev/null || true

    if [ "$metrics_available" -gt 0 ]; then
        info "$metrics_available métricas internas do OpenTelemetry Collector disponíveis"
        return 0
    else
        error "Métricas do OpenTelemetry Collector não disponíveis"
        return 1
    fi
}

# Teste 9: Verificar correlação distribuída (se habilitado)
test_distributed_correlation() {
    if [ "$CORRELATION_TEST" != "true" ]; then
        info "Teste de correlação desabilitado"
        return 0
    fi

    log "Testando correlação distribuída Neural Hive-Mind..."

    # Verificar se headers de correlação estão configurados
    local correlation_config
    correlation_config=$(kubectl get configmap -n "$NAMESPACE" neural-hive-observability-config -o jsonpath='{.data.correlation\.yaml}' 2>/dev/null || echo "")

    if [ -z "$correlation_config" ]; then
        warn "Configuração de correlação não encontrada"
        return 1
    fi

    # Verificar headers esperados
    local headers=("X-Neural-Hive-Intent-ID" "X-Neural-Hive-Plan-ID" "X-Neural-Hive-Domain" "X-Neural-Hive-User-ID")
    local failed=0

    for header in "${headers[@]}"; do
        if echo "$correlation_config" | grep -q "$header"; then
            [ "$VERBOSE" == "true" ] && info "Header de correlação configurado: $header"
        else
            error "Header de correlação não configurado: $header"
            failed=$((failed + 1))
        fi
    done

    [ $failed -eq 0 ]
}

# Teste 10: Verificar SLOs (se habilitado)
test_slo_configuration() {
    if [ "$SLO_TEST" != "true" ]; then
        info "Teste de SLO desabilitado"
        return 0
    fi

    log "Testando configuração de SLOs..."

    # Verificar se regras de SLO estão configuradas
    local slo_rules
    slo_rules=$(kubectl get prometheusrule -n "$NAMESPACE" -l "neural.hive/slo=enabled" --no-headers 2>/dev/null | wc -l)

    if [ "$slo_rules" -gt 0 ]; then
        info "$slo_rules regra(s) de SLO encontradas"

        # Verificar se as métricas de SLO estão sendo geradas
        kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-prometheus 0:9090 &
        local pf_pid=$!
        sleep 3

        local local_port
        local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

        if [ -n "$local_port" ]; then
            local slo_metrics
            slo_metrics=$(curl -s "http://localhost:$local_port/api/v1/query?query=neural_hive_slo" | jq -r '.data.result | length' 2>/dev/null || echo "0")

            if [ "$slo_metrics" -gt 0 ]; then
                info "$slo_metrics métrica(s) de SLO ativas"
            else
                warn "Regras de SLO configuradas mas métricas não disponíveis (pode ser normal sem tráfego)"
            fi
        fi

        kill $pf_pid 2>/dev/null || true
        return 0
    else
        warn "Nenhuma regra de SLO encontrada"
        return 1
    fi
}

# Teste 11: Verificar storage e persistência
test_storage_persistence() {
    log "Testando storage e persistência..."

    local failed=0

    # Verificar PVCs
    local pvcs
    pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

    if [ "$pvcs" -gt 0 ]; then
        info "$pvcs PVC(s) encontrados"

        # Verificar status dos PVCs
        while IFS= read -r pvc_line; do
            if [[ $pvc_line == *"Pending"* ]]; then
                error "PVC pendente: $pvc_line"
                failed=$((failed + 1))
            elif [ "$VERBOSE" == "true" ]; then
                info "PVC OK: $pvc_line"
            fi
        done < <(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null)
    else
        warn "Nenhum PVC encontrado (pode usar storage efêmero)"
    fi

    # Verificar se há dados no Prometheus (como indicador de persistência)
    kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-prometheus 0:9090 &
    local pf_pid=$!
    sleep 3

    local local_port
    local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -n "$local_port" ]; then
        local data_points
        data_points=$(curl -s "http://localhost:$local_port/api/v1/query?query=up" | jq -r '.data.result | length' 2>/dev/null || echo "0")

        if [ "$data_points" -gt 0 ]; then
            info "Dados históricos disponíveis no Prometheus"
        else
            warn "Poucos dados históricos no Prometheus (pode ser instalação recente)"
        fi
    fi

    kill $pf_pid 2>/dev/null || true

    [ $failed -eq 0 ]
}

# Teste 12: Verificar alerting
test_alerting_configuration() {
    log "Testando configuração de alerting..."

    # Verificar AlertManager
    kubectl port-forward -n "$NAMESPACE" service/prometheus-stack-alertmanager 0:9093 &
    local pf_pid=$!
    sleep 3

    local local_port
    local_port=$(lsof -Pan -p $pf_pid -i | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)

    if [ -z "$local_port" ]; then
        kill $pf_pid 2>/dev/null || true
        error "Falha ao conectar com AlertManager"
        return 1
    fi

    # Verificar status do AlertManager
    local status
    status=$(curl -s "http://localhost:$local_port/api/v1/status" | jq -r '.status' 2>/dev/null || echo "error")

    if [ "$status" == "success" ]; then
        info "AlertManager respondendo corretamente"

        # Verificar configuração de receivers
        local receivers
        receivers=$(curl -s "http://localhost:$local_port/api/v1/status" | jq -r '.data.configYAML' 2>/dev/null | grep -c "receivers:" || echo "0")

        if [ "$receivers" -gt 0 ]; then
            info "Receivers configurados no AlertManager"
        else
            warn "Nenhum receiver configurado no AlertManager"
        fi
    else
        error "AlertManager não está respondendo corretamente"
        kill $pf_pid 2>/dev/null || true
        return 1
    fi

    kill $pf_pid 2>/dev/null || true
    return 0
}

# Função para gerar relatório final
generate_final_report() {
    echo
    echo "=========================================="
    echo "  RELATÓRIO FINAL DE VALIDAÇÃO"
    echo "=========================================="
    echo
    echo "Total de testes executados: $TOTAL_TESTS"
    echo -e "${GREEN}Testes aprovados: $PASSED_TESTS${NC}"
    echo -e "${RED}Testes falharam: $FAILED_TESTS${NC}"
    echo -e "${YELLOW}Testes pulados: $SKIPPED_TESTS${NC}"
    echo

    if [ $FAILED_TESTS -gt 0 ]; then
        echo -e "${RED}TESTES FALHARAM:${NC}"
        for failed_test in "${FAILED_TESTS_LIST[@]}"; do
            echo "  ✗ $failed_test"
        done
        echo
    fi

    if [ $SKIPPED_TESTS -gt 0 ]; then
        echo -e "${YELLOW}TESTES PULADOS:${NC}"
        for skipped_test in "${SKIPPED_TESTS_LIST[@]}"; do
            echo "  ⚠ $skipped_test"
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

    if [ $FAILED_TESTS -eq 0 ]; then
        success "Stack de observabilidade Neural Hive-Mind validada com sucesso! 🚀"
        return 0
    else
        error "Validação falhou. Verifique os componentes com problemas."
        return 1
    fi
}

# Função de ajuda
show_help() {
    cat << EOF
Neural Hive-Mind Observability Stack Validation Script

Uso: $0 [opções]

Opções:
  -h, --help              Mostrar esta ajuda
  -n, --namespace NS      Namespace da stack (padrão: observability)
  -t, --timeout SEC       Timeout para testes (padrão: 300s)
  -v, --verbose           Output verboso
  --no-correlation        Desabilitar teste de correlação
  --no-slo               Desabilitar teste de SLO
  --dry-run              Apenas mostrar quais testes seriam executados

Variáveis de ambiente:
  NAMESPACE              Namespace da stack
  TIMEOUT                Timeout para testes
  VERBOSE                true/false para output verboso
  CORRELATION_TEST       true/false para teste de correlação
  SLO_TEST              true/false para teste de SLO
  DRY_RUN               true/false para dry run

Exemplos:
  $0                                    # Validação completa
  $0 --verbose --namespace observability # Validação verbosa
  $0 --dry-run                          # Apenas listar testes
  $0 --no-correlation --no-slo          # Pular testes específicos
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
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            --no-correlation)
                CORRELATION_TEST=false
                shift
                ;;
            --no-slo)
                SLO_TEST=false
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
    echo "  VALIDAÇÃO NEURAL HIVE-MIND OBSERVABILITY"
    echo "=========================================="
    echo
    log "Namespace: $NAMESPACE"
    log "Timeout: ${TIMEOUT}s"
    log "Verbose: $VERBOSE"
    log "Teste de correlação: $CORRELATION_TEST"
    log "Teste de SLO: $SLO_TEST"
    log "Dry run: $DRY_RUN"
    echo

    # Verificar dependências primeiro
    if ! check_dependencies; then
        error "Falha na verificação de dependências"
        exit 1
    fi

    # Executar testes
    run_test "Namespace e recursos básicos" test_namespace_resources true
    run_test "Pods em execução" test_pods_running true
    run_test "Services e endpoints" test_services_endpoints true
    run_test "Conectividade HTTP" test_http_connectivity true
    run_test "Métricas do Prometheus" test_prometheus_metrics true
    run_test "Dashboards do Grafana" test_grafana_dashboards true
    run_test "Traces do Jaeger" test_jaeger_traces false
    run_test "Configuração do OpenTelemetry Collector" test_otel_collector_config true
    run_test "Correlação distribuída" test_distributed_correlation false
    run_test "Configuração de SLOs" test_slo_configuration false
    run_test "Storage e persistência" test_storage_persistence false
    run_test "Configuração de alerting" test_alerting_configuration true

    # Gerar relatório final
    generate_final_report
}

# Executar se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi