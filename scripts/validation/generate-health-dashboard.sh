#!/bin/bash
# Gerador de dashboard HTML interativo com status de saúde do cluster Neural Hive-Mind
# Coleta métricas em tempo real e gera visualizações interativas
# Version: 1.0

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

# Configurações do dashboard
DASHBOARD_REFRESH_INTERVAL=30  # segundos
DASHBOARD_PORT="${DASHBOARD_PORT:-8080}"
DASHBOARD_OUTPUT_DIR="${REPORT_DIR}/dashboard"
STATIC_MODE="${STATIC_MODE:-false}"
PROMETHEUS_NAMESPACE="${PROMETHEUS_NAMESPACE:-observability}"
GRAFANA_NAMESPACE="${GRAFANA_NAMESPACE:-observability}"

# URLs de serviços (serão detectadas automaticamente)
PROMETHEUS_URL=""
GRAFANA_URL=""
JAEGER_URL=""

# Dados coletados
declare -A CLUSTER_METRICS=()
declare -A COMPONENT_STATUS=()
declare -A RESOURCE_UTILIZATION=()
declare -A SECURITY_STATUS=()

# ============================================================================
# DETECÇÃO E CONFIGURAÇÃO DE SERVIÇOS
# ============================================================================

# Detectar URLs dos serviços de monitoramento
detect_monitoring_services() {
    log_info "Detectando serviços de monitoramento..."

    # Detectar Prometheus
    if kubectl get service prometheus-stack-prometheus -n "$PROMETHEUS_NAMESPACE" >/dev/null 2>&1; then
        PROMETHEUS_URL="http://prometheus-stack-prometheus.${PROMETHEUS_NAMESPACE}.svc.cluster.local:9090"
        log_debug "Prometheus detectado: $PROMETHEUS_URL"
    else
        log_warning "Prometheus não detectado no namespace $PROMETHEUS_NAMESPACE"
    fi

    # Detectar Grafana
    if kubectl get service grafana -n "$GRAFANA_NAMESPACE" >/dev/null 2>&1; then
        GRAFANA_URL="http://grafana.${GRAFANA_NAMESPACE}.svc.cluster.local:3000"
        log_debug "Grafana detectado: $GRAFANA_URL"
    else
        log_warning "Grafana não detectado no namespace $GRAFANA_NAMESPACE"
    fi

    # Detectar Jaeger
    if kubectl get service jaeger-query -n "$PROMETHEUS_NAMESPACE" >/dev/null 2>&1; then
        JAEGER_URL="http://jaeger-query.${PROMETHEUS_NAMESPACE}.svc.cluster.local:16686"
        log_debug "Jaeger detectado: $JAEGER_URL"
    else
        log_warning "Jaeger não detectado no namespace $PROMETHEUS_NAMESPACE"
    fi
}

# ============================================================================
# COLETA DE MÉTRICAS
# ============================================================================

# Coletar métricas básicas do cluster
collect_cluster_metrics() {
    log_debug "Coletando métricas básicas do cluster..."

    # Métricas de nodes
    local total_nodes=$(kubectl get nodes --no-headers | wc -l)
    local ready_nodes=$(kubectl get nodes --no-headers | grep -c " Ready " || echo "0")
    CLUSTER_METRICS["nodes_total"]=$total_nodes
    CLUSTER_METRICS["nodes_ready"]=$ready_nodes
    CLUSTER_METRICS["nodes_not_ready"]=$((total_nodes - ready_nodes))

    # Métricas de pods
    local total_pods=$(kubectl get pods --all-namespaces --no-headers | wc -l)
    local running_pods=$(kubectl get pods --all-namespaces --no-headers | grep -c " Running " || echo "0")
    local pending_pods=$(kubectl get pods --all-namespaces --no-headers | grep -c " Pending " || echo "0")
    local failed_pods=$(kubectl get pods --all-namespaces --no-headers | grep -c " Failed " || echo "0")
    CLUSTER_METRICS["pods_total"]=$total_pods
    CLUSTER_METRICS["pods_running"]=$running_pods
    CLUSTER_METRICS["pods_pending"]=$pending_pods
    CLUSTER_METRICS["pods_failed"]=$failed_pods

    # Métricas de namespaces
    local total_namespaces=$(kubectl get namespaces --no-headers | wc -l)
    CLUSTER_METRICS["namespaces_total"]=$total_namespaces

    # Métricas de recursos (se metrics-server disponível)
    if kubectl top nodes >/dev/null 2>&1; then
        local cpu_usage=$(kubectl top nodes --no-headers | awk '{sum += $3} END {print int(sum)}' 2>/dev/null || echo "0")
        local memory_usage=$(kubectl top nodes --no-headers | awk '{sum += $5} END {print int(sum)}' 2>/dev/null || echo "0")
        CLUSTER_METRICS["cpu_usage_percent"]=$cpu_usage
        CLUSTER_METRICS["memory_usage_percent"]=$memory_usage
    else
        CLUSTER_METRICS["cpu_usage_percent"]="N/A"
        CLUSTER_METRICS["memory_usage_percent"]="N/A"
    fi

    # Timestamp da coleta
    CLUSTER_METRICS["last_updated"]=$(date -Iseconds)
}

# Coletar status dos componentes Neural Hive-Mind
collect_component_status() {
    log_debug "Coletando status dos componentes..."

    local namespaces=(
        "neural-gateway"
        "neural-cognitive"
        "neural-orchestration"
        "neural-security"
        "neural-monitoring"
        "istio-system"
        "gatekeeper-system"
        "cosign-system"
        "observability"
    )

    for namespace in "${namespaces[@]}"; do
        if kubectl get namespace "$namespace" >/dev/null 2>&1; then
            local pods_in_ns=$(kubectl get pods -n "$namespace" --no-headers 2>/dev/null | wc -l)
            local ready_pods=$(kubectl get pods -n "$namespace" --no-headers 2>/dev/null | grep -c " Running " || echo "0")
            local health_percentage=0

            if [[ $pods_in_ns -gt 0 ]]; then
                health_percentage=$((ready_pods * 100 / pods_in_ns))
            fi

            COMPONENT_STATUS["${namespace}_pods_total"]=$pods_in_ns
            COMPONENT_STATUS["${namespace}_pods_ready"]=$ready_pods
            COMPONENT_STATUS["${namespace}_health_percentage"]=$health_percentage

            # Status geral do componente
            if [[ $health_percentage -ge 90 ]]; then
                COMPONENT_STATUS["${namespace}_status"]="healthy"
            elif [[ $health_percentage -ge 70 ]]; then
                COMPONENT_STATUS["${namespace}_status"]="warning"
            else
                COMPONENT_STATUS["${namespace}_status"]="critical"
            fi
        else
            COMPONENT_STATUS["${namespace}_status"]="not-found"
            COMPONENT_STATUS["${namespace}_pods_total"]=0
            COMPONENT_STATUS["${namespace}_pods_ready"]=0
            COMPONENT_STATUS["${namespace}_health_percentage"]=0
        fi
    done
}

# Coletar utilização de recursos por namespace
collect_resource_utilization() {
    log_debug "Coletando utilização de recursos..."

    local namespaces=(
        "neural-gateway"
        "neural-cognitive"
        "neural-orchestration"
        "istio-system"
        "observability"
    )

    for namespace in "${namespaces[@]}"; do
        if kubectl get namespace "$namespace" >/dev/null 2>&1; then
            # CPU e memória via kubectl top (se disponível)
            if kubectl top pods -n "$namespace" >/dev/null 2>&1; then
                local cpu_usage=$(kubectl top pods -n "$namespace" --no-headers 2>/dev/null | \
                    awk '{sum += $2} END {print int(sum)}' || echo "0")
                local memory_usage=$(kubectl top pods -n "$namespace" --no-headers 2>/dev/null | \
                    awk '{sum += $3} END {print int(sum)}' || echo "0")

                RESOURCE_UTILIZATION["${namespace}_cpu_millicores"]=$cpu_usage
                RESOURCE_UTILIZATION["${namespace}_memory_mb"]=$memory_usage
            else
                RESOURCE_UTILIZATION["${namespace}_cpu_millicores"]="N/A"
                RESOURCE_UTILIZATION["${namespace}_memory_mb"]="N/A"
            fi

            # Contagem de recursos
            local services=$(kubectl get services -n "$namespace" --no-headers 2>/dev/null | wc -l)
            local configmaps=$(kubectl get configmaps -n "$namespace" --no-headers 2>/dev/null | wc -l)
            local secrets=$(kubectl get secrets -n "$namespace" --no-headers 2>/dev/null | wc -l)

            RESOURCE_UTILIZATION["${namespace}_services"]=$services
            RESOURCE_UTILIZATION["${namespace}_configmaps"]=$configmaps
            RESOURCE_UTILIZATION["${namespace}_secrets"]=$secrets
        fi
    done
}

# Coletar status de segurança
collect_security_status() {
    log_debug "Coletando status de segurança..."

    # OPA Gatekeeper
    if kubectl get namespace gatekeeper-system >/dev/null 2>&1; then
        local active_constraints=$(kubectl get constraints --all-namespaces --no-headers 2>/dev/null | wc -l)
        local violated_constraints=$(kubectl get constraints --all-namespaces -o jsonpath='{range .items[*]}{.status.totalViolations}{"\n"}{end}' 2>/dev/null | \
            awk '$1 > 0 {count++} END {print count+0}')

        SECURITY_STATUS["opa_constraints_total"]=$active_constraints
        SECURITY_STATUS["opa_violations"]=$violated_constraints
        SECURITY_STATUS["opa_status"]="active"
    else
        SECURITY_STATUS["opa_status"]="not-found"
        SECURITY_STATUS["opa_constraints_total"]=0
        SECURITY_STATUS["opa_violations"]=0
    fi

    # Istio mTLS
    if kubectl get namespace istio-system >/dev/null 2>&1; then
        local peer_auth_policies=$(kubectl get peerauthentication --all-namespaces --no-headers 2>/dev/null | wc -l)
        SECURITY_STATUS["istio_mtls_policies"]=$peer_auth_policies
        SECURITY_STATUS["istio_status"]="active"
    else
        SECURITY_STATUS["istio_status"]="not-found"
        SECURITY_STATUS["istio_mtls_policies"]=0
    fi

    # Sigstore Policy Controller
    if kubectl get namespace cosign-system >/dev/null 2>&1; then
        local policy_controller_ready=$(kubectl get deployment policy-controller -n cosign-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ $policy_controller_ready -gt 0 ]]; then
            SECURITY_STATUS["sigstore_status"]="active"
        else
            SECURITY_STATUS["sigstore_status"]="degraded"
        fi
    else
        SECURITY_STATUS["sigstore_status"]="not-found"
    fi

    # Certificados TLS próximos ao vencimento
    local tls_secrets_warning=0
    while IFS= read -r secret_info; do
        local namespace=$(echo "$secret_info" | awk '{print $1}')
        local secret_name=$(echo "$secret_info" | awk '{print $2}')

        local cert_data=$(kubectl get secret "$secret_name" -n "$namespace" -o jsonpath='{.data.tls\.crt}' 2>/dev/null | base64 -d 2>/dev/null)
        if [[ -n "$cert_data" ]]; then
            local days_until_expiry=$(echo "$cert_data" | openssl x509 -enddate -noout 2>/dev/null | cut -d= -f2 | xargs -I {} date -d {} +%s 2>/dev/null)
            if [[ -n "$days_until_expiry" ]]; then
                local current_time=$(date +%s)
                local days_left=$(( (days_until_expiry - current_time) / 86400 ))
                if [[ $days_left -lt 30 ]]; then
                    tls_secrets_warning=$((tls_secrets_warning + 1))
                fi
            fi
        fi
    done < <(kubectl get secrets --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.type" --no-headers 2>/dev/null | grep "kubernetes.io/tls" | head -20)

    SECURITY_STATUS["certificates_expiring_soon"]=$tls_secrets_warning
}

# Coletar métricas do Prometheus (se disponível)
collect_prometheus_metrics() {
    if [[ -z "$PROMETHEUS_URL" ]]; then
        return 0
    fi

    log_debug "Coletando métricas do Prometheus..."

    # Port-forward temporário para acessar Prometheus
    kubectl port-forward -n "$PROMETHEUS_NAMESPACE" service/prometheus-stack-prometheus 0:9090 &
    local prom_pid=$!
    sleep 3

    local prom_port=$(lsof -Pan -p $prom_pid -i 2>/dev/null | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1 || echo "")

    if [[ -n "$prom_port" ]]; then
        # Consultar métricas específicas do Neural Hive-Mind
        local metrics_queries=(
            "up"
            "rate(http_requests_total[5m])"
            "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
            "rate(http_requests_total{status=~\"5..\"}[5m])"
        )

        for query in "${metrics_queries[@]}"; do
            local result=$(curl -s "http://localhost:$prom_port/api/v1/query?query=$(echo "$query" | sed 's/ /%20/g')" | \
                jq -r '.status' 2>/dev/null || echo "error")

            if [[ "$result" == "success" ]]; then
                log_debug "Métrica disponível: $query"
            fi
        done

        # Verificar targets ativos
        local targets_up=$(curl -s "http://localhost:$prom_port/api/v1/targets" | \
            jq -r '.data.activeTargets | map(select(.health == "up")) | length' 2>/dev/null || echo "0")
        CLUSTER_METRICS["prometheus_targets_up"]=$targets_up
    fi

    kill $prom_pid 2>/dev/null || true
}

# ============================================================================
# GERAÇÃO DO DASHBOARD HTML
# ============================================================================

# Gerar dashboard HTML completo
generate_html_dashboard() {
    local dashboard_file="${DASHBOARD_OUTPUT_DIR}/neural-hive-health-dashboard.html"
    mkdir -p "$DASHBOARD_OUTPUT_DIR"

    log_info "Gerando dashboard HTML: $dashboard_file"

    cat > "$dashboard_file" <<'EOF'
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Neural Hive-Mind - Dashboard de Saúde</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 20px 0;
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .logo h1 {
            color: #4f46e5;
            font-size: 1.8em;
            font-weight: 700;
        }
        .status-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .status-healthy { background: #d1fae5; color: #065f46; }
        .status-warning { background: #fef3c7; color: #92400e; }
        .status-critical { background: #fee2e2; color: #991b1b; }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 30px 20px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }
        .metric-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.15);
        }
        .metric-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .metric-title {
            font-size: 1.1em;
            font-weight: 600;
            color: #374151;
        }
        .metric-icon {
            width: 40px;
            height: 40px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
        }
        .icon-nodes { background: #dbeafe; color: #1d4ed8; }
        .icon-pods { background: #d1fae5; color: #059669; }
        .icon-security { background: #fde68a; color: #d97706; }
        .icon-performance { background: #e0e7ff; color: #6366f1; }
        .metric-value {
            font-size: 2.5em;
            font-weight: 700;
            color: #111827;
            margin-bottom: 10px;
        }
        .metric-subtext {
            color: #6b7280;
            font-size: 0.9em;
        }
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
            margin: 15px 0;
        }
        .progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.6s ease;
        }
        .progress-healthy { background: linear-gradient(90deg, #10b981, #059669); }
        .progress-warning { background: linear-gradient(90deg, #f59e0b, #d97706); }
        .progress-critical { background: linear-gradient(90deg, #ef4444, #dc2626); }
        .components-section {
            margin-top: 50px;
        }
        .section-title {
            font-size: 1.5em;
            font-weight: 700;
            color: #fff;
            margin-bottom: 25px;
            text-align: center;
        }
        .components-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
        }
        .component-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .component-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .component-name {
            font-weight: 600;
            color: #374151;
            text-transform: capitalize;
        }
        .health-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        .health-healthy { background: #10b981; }
        .health-warning { background: #f59e0b; }
        .health-critical { background: #ef4444; }
        .health-not-found { background: #6b7280; }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .component-stats {
            display: flex;
            justify-content: space-between;
            margin-top: 15px;
        }
        .stat {
            text-align: center;
        }
        .stat-value {
            font-size: 1.2em;
            font-weight: 600;
            color: #111827;
        }
        .stat-label {
            font-size: 0.8em;
            color: #6b7280;
            margin-top: 2px;
        }
        .last-updated {
            text-align: center;
            color: rgba(255, 255, 255, 0.8);
            margin-top: 30px;
            font-size: 0.9em;
        }
        .refresh-button {
            background: #4f46e5;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.3s ease;
        }
        .refresh-button:hover {
            background: #4338ca;
        }
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #6b7280;
            font-size: 0.9em;
        }
        @media (max-width: 768px) {
            .header-content {
                flex-direction: column;
                gap: 15px;
            }
            .metrics-grid,
            .components-grid {
                grid-template-columns: 1fr;
            }
            .container {
                padding: 20px 10px;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="logo">
                <div class="metric-icon icon-nodes">🧠</div>
                <h1>Neural Hive-Mind</h1>
            </div>
            <div style="display: flex; align-items: center; gap: 20px;">
                <span id="overall-status" class="status-badge status-healthy">Sistema Saudável</span>
                <button class="refresh-button" onclick="refreshData()">Atualizar</button>
            </div>
        </div>
    </div>

    <div class="container">
        <!-- Métricas Principais -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Nodes do Cluster</span>
                    <div class="metric-icon icon-nodes">🖥️</div>
                </div>
                <div class="metric-value" id="nodes-ready">-</div>
                <div class="metric-subtext">de <span id="nodes-total">-</span> nodes prontos</div>
                <div class="progress-bar">
                    <div class="progress-fill progress-healthy" id="nodes-progress"></div>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Pods em Execução</span>
                    <div class="metric-icon icon-pods">📦</div>
                </div>
                <div class="metric-value" id="pods-running">-</div>
                <div class="metric-subtext">de <span id="pods-total">-</span> pods</div>
                <div class="progress-bar">
                    <div class="progress-fill progress-healthy" id="pods-progress"></div>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Segurança</span>
                    <div class="metric-icon icon-security">🔒</div>
                </div>
                <div class="metric-value" id="security-policies">-</div>
                <div class="metric-subtext"><span id="security-violations">-</span> violações detectadas</div>
                <div class="progress-bar">
                    <div class="progress-fill progress-healthy" id="security-progress"></div>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Performance</span>
                    <div class="metric-icon icon-performance">⚡</div>
                </div>
                <div class="metric-value" id="cpu-usage">-%</div>
                <div class="metric-subtext">CPU • <span id="memory-usage">-%</span> Memory</div>
                <div class="progress-bar">
                    <div class="progress-fill progress-healthy" id="performance-progress"></div>
                </div>
            </div>
        </div>

        <!-- Componentes -->
        <div class="components-section">
            <h2 class="section-title">Status dos Componentes</h2>
            <div class="components-grid" id="components-grid">
                <!-- Componentes serão inseridos dinamicamente -->
            </div>
        </div>

        <div class="last-updated">
            Última atualização: <span id="last-updated">-</span>
            <div class="auto-refresh">
                <span>🔄 Atualização automática a cada 30s</span>
            </div>
        </div>
    </div>

    <script>
EOF

    # Inserir dados JavaScript
    cat >> "$dashboard_file" <<EOF
        // Dados do dashboard
        let dashboardData = {
            cluster_metrics: $(echo "${CLUSTER_METRICS[@]}" | jq -R 'split(" ") | map(split("=")) | map({key: .[0], value: .[1]}) | from_entries' 2>/dev/null || echo "{}"),
            component_status: $(echo "${COMPONENT_STATUS[@]}" | jq -R 'split(" ") | map(split("=")) | map({key: .[0], value: .[1]}) | from_entries' 2>/dev/null || echo "{}"),
            security_status: $(echo "${SECURITY_STATUS[@]}" | jq -R 'split(" ") | map(split("=")) | map({key: .[0], value: .[1]}) | from_entries' 2>/dev/null || echo "{}")
        };
EOF

    cat >> "$dashboard_file" <<'EOF'

        // Função para formatar dados
        function formatData() {
            // Dados em formato mais acessível
            const data = {
                nodes_ready: parseInt(dashboardData.cluster_metrics.nodes_ready) || 0,
                nodes_total: parseInt(dashboardData.cluster_metrics.nodes_total) || 0,
                pods_running: parseInt(dashboardData.cluster_metrics.pods_running) || 0,
                pods_total: parseInt(dashboardData.cluster_metrics.pods_total) || 0,
                cpu_usage: dashboardData.cluster_metrics.cpu_usage_percent || 'N/A',
                memory_usage: dashboardData.cluster_metrics.memory_usage_percent || 'N/A',
                opa_constraints: parseInt(dashboardData.security_status.opa_constraints_total) || 0,
                opa_violations: parseInt(dashboardData.security_status.opa_violations) || 0,
                last_updated: dashboardData.cluster_metrics.last_updated || new Date().toISOString()
            };
            return data;
        }

        // Atualizar métricas principais
        function updateMainMetrics() {
            const data = formatData();

            // Nodes
            document.getElementById('nodes-ready').textContent = data.nodes_ready;
            document.getElementById('nodes-total').textContent = data.nodes_total;

            const nodesPercentage = data.nodes_total > 0 ? (data.nodes_ready / data.nodes_total) * 100 : 0;
            document.getElementById('nodes-progress').style.width = nodesPercentage + '%';

            // Pods
            document.getElementById('pods-running').textContent = data.pods_running;
            document.getElementById('pods-total').textContent = data.pods_total;

            const podsPercentage = data.pods_total > 0 ? (data.pods_running / data.pods_total) * 100 : 0;
            document.getElementById('pods-progress').style.width = podsPercentage + '%';

            // Segurança
            document.getElementById('security-policies').textContent = data.opa_constraints;
            document.getElementById('security-violations').textContent = data.opa_violations;

            const securityPercentage = data.opa_constraints > 0 && data.opa_violations === 0 ? 100 :
                                     data.opa_violations === 0 ? 50 :
                                     Math.max(0, 100 - (data.opa_violations * 20));
            document.getElementById('security-progress').style.width = securityPercentage + '%';

            // Performance
            if (data.cpu_usage !== 'N/A') {
                document.getElementById('cpu-usage').textContent = data.cpu_usage + '%';
                document.getElementById('memory-usage').textContent = data.memory_usage + '%';

                const avgUsage = (parseInt(data.cpu_usage) + parseInt(data.memory_usage)) / 2;
                document.getElementById('performance-progress').style.width = (100 - avgUsage) + '%';
            } else {
                document.getElementById('cpu-usage').textContent = 'N/A';
                document.getElementById('memory-usage').textContent = 'N/A';
                document.getElementById('performance-progress').style.width = '50%';
            }

            // Última atualização
            const lastUpdated = new Date(data.last_updated);
            document.getElementById('last-updated').textContent = lastUpdated.toLocaleString('pt-BR');

            // Status geral
            updateOverallStatus(nodesPercentage, podsPercentage, securityPercentage);
        }

        // Atualizar status geral
        function updateOverallStatus(nodesHealth, podsHealth, securityHealth) {
            const avgHealth = (nodesHealth + podsHealth + securityHealth) / 3;
            const statusElement = document.getElementById('overall-status');

            if (avgHealth >= 90) {
                statusElement.className = 'status-badge status-healthy';
                statusElement.textContent = 'Sistema Saudável';
            } else if (avgHealth >= 70) {
                statusElement.className = 'status-badge status-warning';
                statusElement.textContent = 'Atenção Necessária';
            } else {
                statusElement.className = 'status-badge status-critical';
                statusElement.textContent = 'Estado Crítico';
            }
        }

        // Atualizar componentes
        function updateComponents() {
            const componentsGrid = document.getElementById('components-grid');
            componentsGrid.innerHTML = '';

            const namespaces = [
                'neural-gateway',
                'neural-cognitive',
                'neural-orchestration',
                'istio-system',
                'gatekeeper-system',
                'observability'
            ];

            namespaces.forEach(namespace => {
                const status = dashboardData.component_status[namespace + '_status'] || 'not-found';
                const total = parseInt(dashboardData.component_status[namespace + '_pods_total']) || 0;
                const ready = parseInt(dashboardData.component_status[namespace + '_pods_ready']) || 0;
                const health = parseInt(dashboardData.component_status[namespace + '_health_percentage']) || 0;

                const componentCard = document.createElement('div');
                componentCard.className = 'component-card';
                componentCard.innerHTML = `
                    <div class="component-header">
                        <span class="component-name">${namespace.replace(/-/g, ' ')}</span>
                        <div class="health-indicator health-${status}"></div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill progress-${status === 'healthy' ? 'healthy' : status === 'warning' ? 'warning' : 'critical'}"
                             style="width: ${health}%"></div>
                    </div>
                    <div class="component-stats">
                        <div class="stat">
                            <div class="stat-value">${ready}</div>
                            <div class="stat-label">Ready</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">${total}</div>
                            <div class="stat-label">Total</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">${health}%</div>
                            <div class="stat-label">Health</div>
                        </div>
                    </div>
                `;
                componentsGrid.appendChild(componentCard);
            });
        }

        // Função de refresh
        function refreshData() {
            // Em implementação real, faria nova requisição para API
            // Por enquanto, simula refresh dos dados
            console.log('Atualizando dados...');
            updateMainMetrics();
            updateComponents();
        }

        // Auto-refresh
        setInterval(refreshData, 30000);

        // Inicialização
        document.addEventListener('DOMContentLoaded', function() {
            updateMainMetrics();
            updateComponents();
        });
    </script>
</body>
</html>
EOF

    echo "$dashboard_file"
}

# Gerar dashboard estático JSON para APIs
generate_json_dashboard() {
    local json_file="${DASHBOARD_OUTPUT_DIR}/neural-hive-metrics.json"

    cat > "$json_file" <<EOF
{
  "dashboard_metadata": {
    "name": "Neural Hive-Mind Health Dashboard",
    "version": "1.0",
    "generated_at": "$(date -Iseconds)",
    "cluster_context": "$(kubectl config current-context 2>/dev/null || echo 'unknown')",
    "refresh_interval": $DASHBOARD_REFRESH_INTERVAL
  },
  "cluster_metrics": {
EOF

    # Adicionar métricas do cluster
    local first=true
    for key in "${!CLUSTER_METRICS[@]}"; do
        if [[ "$first" == "false" ]]; then
            echo "," >> "$json_file"
        fi
        first=false
        echo "    \"$key\": \"${CLUSTER_METRICS[$key]}\"" >> "$json_file"
    done

    cat >> "$json_file" <<EOF
  },
  "component_status": {
EOF

    # Adicionar status dos componentes
    first=true
    for key in "${!COMPONENT_STATUS[@]}"; do
        if [[ "$first" == "false" ]]; then
            echo "," >> "$json_file"
        fi
        first=false
        echo "    \"$key\": \"${COMPONENT_STATUS[$key]}\"" >> "$json_file"
    done

    cat >> "$json_file" <<EOF
  },
  "resource_utilization": {
EOF

    # Adicionar utilização de recursos
    first=true
    for key in "${!RESOURCE_UTILIZATION[@]}"; do
        if [[ "$first" == "false" ]]; then
            echo "," >> "$json_file"
        fi
        first=false
        echo "    \"$key\": \"${RESOURCE_UTILIZATION[$key]}\"" >> "$json_file"
    done

    cat >> "$json_file" <<EOF
  },
  "security_status": {
EOF

    # Adicionar status de segurança
    first=true
    for key in "${!SECURITY_STATUS[@]}"; do
        if [[ "$first" == "false" ]]; then
            echo "," >> "$json_file"
        fi
        first=false
        echo "    \"$key\": \"${SECURITY_STATUS[$key]}\"" >> "$json_file"
    done

    cat >> "$json_file" <<EOF
  }
}
EOF

    echo "$json_file"
}

# ============================================================================
# SERVIDOR HTTP SIMPLES (OPCIONAL)
# ============================================================================

# Iniciar servidor HTTP simples para servir o dashboard
start_dashboard_server() {
    if [[ "$STATIC_MODE" == "true" ]]; then
        log_info "Modo estático ativado - dashboard salvo em arquivos"
        return 0
    fi

    log_info "Iniciando servidor de dashboard na porta $DASHBOARD_PORT..."

    # Verificar se Python está disponível
    if command -v python3 >/dev/null 2>&1; then
        cd "$DASHBOARD_OUTPUT_DIR"
        python3 -m http.server "$DASHBOARD_PORT" &
        local server_pid=$!
        echo "$server_pid" > "${DASHBOARD_OUTPUT_DIR}/server.pid"

        log_success "Dashboard disponível em: http://localhost:$DASHBOARD_PORT"
        log_info "Para parar o servidor: kill $server_pid"
    else
        log_warning "Python3 não disponível - dashboard salvo apenas como arquivo estático"
    fi
}

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

main() {
    init_report "Gerador de dashboard de saúde Neural Hive-Mind"

    log_info "Iniciando geração do dashboard de saúde..."

    # Verificar pré-requisitos
    if ! check_prerequisites; then
        log_error "Pré-requisitos não atendidos"
        exit 1
    fi

    # Criar diretório de output
    mkdir -p "$DASHBOARD_OUTPUT_DIR"

    # Detectar serviços de monitoramento
    detect_monitoring_services

    # Coletar todas as métricas
    log_info "Coletando métricas do cluster..."
    collect_cluster_metrics
    collect_component_status
    collect_resource_utilization
    collect_security_status
    collect_prometheus_metrics

    # Gerar dashboards
    log_info "Gerando dashboards..."
    local html_dashboard=$(generate_html_dashboard)
    local json_dashboard=$(generate_json_dashboard)

    # Iniciar servidor (se não for modo estático)
    start_dashboard_server

    log_success "=========================================="
    log_success "Dashboard de saúde gerado com sucesso!"
    log_info "Dashboard HTML: $html_dashboard"
    log_info "Métricas JSON: $json_dashboard"
    if [[ "$STATIC_MODE" != "true" ]]; then
        log_info "Servidor: http://localhost:$DASHBOARD_PORT"
    fi
    log_success "=========================================="
}

main "$@"