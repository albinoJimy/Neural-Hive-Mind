#!/bin/bash

validate_observability() {
    log_info "=== Validando Observabilidade ==="
    
    local namespace="${NAMESPACE:-observability}"
    
    # 1. Validar componentes principais
    validate_prometheus "$namespace"
    validate_grafana "$namespace"
    validate_jaeger "$namespace"
    validate_alertmanager "$namespace"
    validate_opentelemetry "$namespace"
    
    # 2. Validar coleta de métricas
    validate_metrics_collection "$namespace"
    
    # 3. Validar ServiceMonitors
    validate_service_monitors
    
    # 4. Validar dashboards
    validate_dashboards "$namespace"
    
    # 5. Validar alertas
    validate_alerting "$namespace"
    
    # 6. Testes avançados (skip se --quick)
    if [[ "$QUICK_MODE" == false ]]; then
        validate_correlation "$namespace"
        validate_slos "$namespace"
        validate_tracing "$namespace"
    fi
}

validate_prometheus() {
    local namespace="$1"
    
    log_info "Validando Prometheus..."
    
    # Pod status
    if check_pod_running "prometheus-stack-prometheus" "$namespace"; then
        add_test_result "prometheus_pod_status" "PASS" "critical" "Prometheus pod Running" "" "2"
    else
        add_test_result "prometheus_pod_status" "FAIL" "critical" "Prometheus pod não está Running" "" "2"
        return
    fi
    
    # Health endpoint
    if check_prometheus_health "$namespace"; then
        add_test_result "prometheus_health" "PASS" "critical" "Prometheus health OK" "" "3"
    else
        add_test_result "prometheus_health" "FAIL" "critical" "Prometheus health falhou" "" "3"
    fi
    
    # Targets
    local down_targets=$(check_prometheus_targets "$namespace")
    if [[ -z "$down_targets" ]]; then
        add_test_result "prometheus_targets" "PASS" "high" "Todos os targets UP" "" "3"
    else
        add_test_result "prometheus_targets" "WARNING" "high" "Alguns targets DOWN: $down_targets" "" "3"
    fi
    
    # Storage
    if check_prometheus_storage "$namespace"; then
        add_test_result "prometheus_storage" "PASS" "medium" "Storage configurado" "" "2"
    else
        add_test_result "prometheus_storage" "WARNING" "medium" "Storage não configurado" "" "2"
    fi
}

validate_grafana() {
    local namespace="$1"
    
    log_info "Validando Grafana..."
    
    # Pod status
    if check_pod_running "grafana" "$namespace"; then
        add_test_result "grafana_pod_status" "PASS" "high" "Grafana pod Running" "" "2"
    else
        add_test_result "grafana_pod_status" "FAIL" "high" "Grafana pod não está Running" "" "2"
        return
    fi
    
    # Health endpoint
    if check_grafana_health "$namespace"; then
        add_test_result "grafana_health" "PASS" "high" "Grafana health OK" "" "2"
    else
        add_test_result "grafana_health" "FAIL" "high" "Grafana health falhou" "" "2"
    fi
    
    # Datasources
    local datasources=$(check_grafana_datasources "$namespace")
    if [[ "$datasources" == *"prometheus"* ]] && [[ "$datasources" == *"jaeger"* ]]; then
        add_test_result "grafana_datasources" "PASS" "high" "Datasources configurados (Prometheus, Jaeger)" "" "3"
    else
        add_test_result "grafana_datasources" "FAIL" "high" "Datasources faltando: $datasources" "" "3"
    fi
    
    # Dashboards
    local dashboard_count=$(kubectl get configmap -n "$namespace" -l grafana_dashboard=1 --no-headers 2>/dev/null | wc -l)
    if [[ "$dashboard_count" -ge 10 ]]; then
        add_test_result "grafana_dashboards" "PASS" "medium" "$dashboard_count dashboards encontrados" "" "2"
    else
        add_test_result "grafana_dashboards" "WARNING" "medium" "Apenas $dashboard_count dashboards encontrados" "" "2"
    fi
}

validate_jaeger() {
    local namespace="$1"
    
    log_info "Validando Jaeger..."
    
    # Pod status
    if check_pod_running "jaeger-query" "$namespace"; then
        add_test_result "jaeger_pod_status" "PASS" "high" "Jaeger pod Running" "" "2"
    else
        add_test_result "jaeger_pod_status" "FAIL" "high" "Jaeger pod não está Running" "" "2"
        return
    fi
    
    # Health endpoint
    if check_jaeger_health "$namespace"; then
        add_test_result "jaeger_health" "PASS" "high" "Jaeger health OK" "" "2"
    else
        add_test_result "jaeger_health" "FAIL" "high" "Jaeger health falhou" "" "2"
    fi
    
    # Ingestion
    local services_count=$(check_jaeger_services "$namespace")
    if [[ "$services_count" -gt 0 ]]; then
        add_test_result "jaeger_ingestion" "PASS" "high" "$services_count serviços com traces" "" "3"
    else
        add_test_result "jaeger_ingestion" "WARNING" "high" "Nenhum serviço com traces" "" "3"
    fi
}

validate_correlation() {
    local namespace="$1"
    
    log_info "Validando correlação distribuída..."
    
    # Executar script de correlação
    local correlation_script="${SCRIPT_DIR}/observability/test-correlation.sh"
    
    if [[ -f "$correlation_script" ]]; then
        if bash "$correlation_script" --namespace "$namespace" > /dev/null 2>&1; then
            add_test_result "correlation_test" "PASS" "medium" "Correlação distribuída funcionando" "" "5"
        else
            add_test_result "correlation_test" "FAIL" "medium" "Correlação distribuída falhou" "" "5"
        fi
    else
        add_test_result "correlation_test" "SKIP" "medium" "Script de correlação não encontrado" "" "0"
    fi
}

validate_slos() {
    local namespace="$1"
    
    log_info "Validando SLOs..."
    
    # Executar script de SLO
    local slo_script="${SCRIPT_DIR}/observability/test-slos.sh"
    
    if [[ -f "$slo_script" ]]; then
        if bash "$slo_script" --namespace "$namespace" > /dev/null 2>&1; then
            add_test_result "slo_test" "PASS" "high" "SLOs configurados e funcionando" "" "5"
        else
            add_test_result "slo_test" "FAIL" "high" "SLOs falharam" "" "5"
        fi
    else
        add_test_result "slo_test" "SKIP" "high" "Script de SLO não encontrado" "" "0"
    fi
}

validate_alertmanager() {
    local namespace="$1"

    log_info "Validando Alertmanager..."

    if check_pod_running "prometheus-stack-kube-prom-alertmanager" "$namespace"; then
        add_test_result "alertmanager_status" "PASS" "high" "Alertmanager Running" "" "2"
    else
        add_test_result "alertmanager_status" "WARNING" "high" "Alertmanager não encontrado" "" "2"
    fi
}

validate_opentelemetry() {
    local namespace="$1"

    log_info "Validando OpenTelemetry Collector..."

    if check_pod_running "otel-collector" "$namespace"; then
        add_test_result "otel_collector_status" "PASS" "medium" "OpenTelemetry Collector Running" "" "2"
    else
        add_test_result "otel_collector_status" "WARNING" "medium" "OpenTelemetry Collector não encontrado" "" "2"
    fi
}

validate_metrics_collection() {
    local namespace="$1"

    log_info "Validando coleta de métricas..."
    add_test_result "metrics_collection" "SKIP" "medium" "Validação detalhada de métricas consolidada (não automatizada aqui)" "" "0"
}

validate_service_monitors() {
    log_info "Validando ServiceMonitors..."

    local count
    count=$(kubectl get servicemonitors --all-namespaces --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "${count:-0}" -gt 0 ]]; then
        add_test_result "service_monitors" "PASS" "medium" "$count ServiceMonitors encontrados" "" "2"
    else
        add_test_result "service_monitors" "WARNING" "medium" "Nenhum ServiceMonitor encontrado" "" "2"
    fi
}

validate_dashboards() {
    local namespace="$1"

    log_info "Validando dashboards Grafana..."

    local dashboard_count
    dashboard_count=$(kubectl get configmap -n "$namespace" -l grafana_dashboard=1 --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "${dashboard_count:-0}" -ge 1 ]]; then
        add_test_result "dashboards" "PASS" "medium" "$dashboard_count dashboards configurados" "" "2"
    else
        add_test_result "dashboards" "WARNING" "medium" "Nenhum dashboard encontrado" "" "2"
    fi
}

validate_alerting() {
    local namespace="$1"

    log_info "Validando alertas Prometheus/Grafana..."
    add_test_result "alerting_rules" "SKIP" "medium" "Validação de alertas consolidada (executar manualmente se necessário)" "" "0"
}

validate_tracing() {
    local namespace="$1"

    log_info "Validando traces no Jaeger..."
    local services_count
    services_count=$(check_jaeger_services "$namespace")
    if [[ "${services_count:-0}" -gt 0 ]]; then
        add_test_result "tracing_services" "PASS" "medium" "$services_count serviços com traces" "" "3"
    else
        add_test_result "tracing_services" "WARNING" "medium" "Nenhum trace encontrado" "" "3"
    fi
}

# Funções auxiliares
check_prometheus_health() {
    local namespace="$1"
    
    kubectl port-forward -n "$namespace" svc/prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
    local pf_pid=$!
    sleep 2
    
    local health=$(curl -s http://localhost:9090/-/healthy 2>/dev/null)
    
    kill $pf_pid 2>/dev/null || true
    wait $pf_pid 2>/dev/null || true
    
    [[ "$health" == "Prometheus is Healthy." ]]
}

check_prometheus_targets() {
    local namespace="$1"
    
    kubectl port-forward -n "$namespace" svc/prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
    local pf_pid=$!
    sleep 2
    
    local down_targets=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null | jq -r '.data.activeTargets[] | select(.health != "up") | .labels.instance' | tr '\n' ',' || echo "")
    
    kill $pf_pid 2>/dev/null || true
    wait $pf_pid 2>/dev/null || true
    
    echo "$down_targets"
}

check_prometheus_storage() {
    local namespace="$1"

    local pvc_count
    pvc_count=$(kubectl get pvc -n "$namespace" -l app=prometheus-stack-prometheus --no-headers 2>/dev/null | wc -l | tr -d ' ')
    [[ "${pvc_count:-0}" -gt 0 ]]
}

check_grafana_datasources() {
    local namespace="$1"
    
    kubectl port-forward -n "$namespace" svc/grafana 3000:80 > /dev/null 2>&1 &
    local pf_pid=$!
    sleep 2
    
    local datasources=$(curl -s -u "admin:admin" http://localhost:3000/api/datasources 2>/dev/null | jq -r '.[].type' | tr '\n' ',' || echo "")
    
    kill $pf_pid 2>/dev/null || true
    wait $pf_pid 2>/dev/null || true
    
    echo "$datasources"
}

check_jaeger_services() {
    local namespace="$1"
    
    kubectl port-forward -n "$namespace" svc/jaeger-query 16686:16686 > /dev/null 2>&1 &
    local pf_pid=$!
    sleep 2
    
    local services_count=$(curl -s http://localhost:16686/api/services 2>/dev/null | jq -r '.data | length' || echo "0")
    
    kill $pf_pid 2>/dev/null || true
    wait $pf_pid 2>/dev/null || true
    
    echo "$services_count"
}
