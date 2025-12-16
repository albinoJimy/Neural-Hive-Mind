#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

# validate-performance-benchmarks.sh
# Script para executar benchmarks de performance do Neural Hive-Mind
# Testa throughput, latência, eficiência de recursos e performance de armazenamento

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

# Configurações padrão
NAMESPACE="${NEURAL_NAMESPACE:-neural-hive-mind}"
BENCHMARK_DURATION="${BENCHMARK_DURATION:-300}"  # 5 minutos
CONCURRENT_USERS="${CONCURRENT_USERS:-50}"
THROUGHPUT_TARGET="${THROUGHPUT_TARGET:-1000}"   # requests/sec
LATENCY_P95_TARGET="${LATENCY_P95_TARGET:-500}"  # ms
RESOURCE_EFFICIENCY_TARGET="${RESOURCE_EFFICIENCY_TARGET:-80}" # %
STORAGE_IOPS_TARGET="${STORAGE_IOPS_TARGET:-1000}"

# Configurações de diretórios e arquivos
TEST_RUN_ID="performance-benchmarks-$(date -u +%Y%m%d_%H%M%S)"
RESULTS_DIR="${REPORT_DIR:-/tmp/neural-hive-validation}/performance-benchmarks"
METRICS_FILE="${RESULTS_DIR}/metrics.txt"

# Função principal
main() {
    log_info "Iniciando validação de benchmarks de performance do Neural Hive-Mind"

    # Criar diretório de resultados
    mkdir -p "${RESULTS_DIR}"

    # Inicializar arquivo de métricas
    echo "# Performance Benchmark Metrics - ${TEST_RUN_ID}" > "${METRICS_FILE}"
    echo "# Generated at: $(date -u +%Y-%m-%d_%H:%M:%S)" >> "${METRICS_FILE}"

    init_report "Performance Benchmarks - Neural Hive-Mind"

    check_prerequisites

    # Executar benchmarks individuais
    test_api_throughput_benchmark
    test_latency_benchmark
    test_resource_efficiency_benchmark
    test_storage_performance_benchmark
    test_concurrent_users_benchmark
    test_memory_pressure_benchmark
    test_network_throughput_benchmark
    test_database_performance_benchmark

    generate_performance_report
    generate_summary_report

    log_info "Validação de benchmarks de performance concluída"
}

# Verificar pré-requisitos específicos para benchmarks
check_prerequisites() {
    log_info "Verificando pré-requisitos para benchmarks de performance"

    # Verificar se o cluster está pronto
    if ! kubectl get nodes | grep -q Ready; then
        add_test_result "Prerequisites" "FAIL" "Nem todos os nós estão prontos"
        exit 1
    fi

    # Verificar se o namespace existe
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        add_test_result "Prerequisites" "FAIL" "Namespace $NAMESPACE não encontrado"
        exit 1
    fi

    # Verificar se os pods estão rodando
    local ready_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers | wc -l)
    if [ "$ready_pods" -eq 0 ]; then
        add_test_result "Prerequisites" "FAIL" "Nenhum pod está rodando no namespace $NAMESPACE"
        exit 1
    fi

    # Verificar se hay2 está disponível para load testing
    if ! command -v hey &> /dev/null; then
        log_warn "Hey load testing tool não encontrado. Tentando instalar..."
        install_hey_tool
    fi

    # Verificar se kubectl top está funcionando
    if ! kubectl top nodes &>/dev/null; then
        log_warn "Metrics server pode não estar disponível"
    fi

    add_test_result "Prerequisites" "PASS" "Todos os pré-requisitos verificados"
}

# Instalar ferramenta hey para load testing
install_hey_tool() {
    log_info "Instalando hey load testing tool"

    if command -v go &> /dev/null; then
        go install github.com/rakyll/hey@latest
        export PATH=$PATH:$(go env GOPATH)/bin
    else
        log_warn "Go não encontrado. Baixando hey binary..."
        wget -O /tmp/hey https://hey-release.s3.us-east-2.amazonaws.com/hey_linux_amd64
        chmod +x /tmp/hey
        sudo mv /tmp/hey /usr/local/bin/
    fi
}

# Teste de throughput da API
test_api_throughput_benchmark() {
    log_info "Executando benchmark de throughput da API"

    local service_url=$(get_service_url)
    if [ -z "$service_url" ]; then
        add_test_result "API Throughput" "FAIL" "Não foi possível obter URL do serviço"
        return 1
    fi

    # Aquecimento
    log_info "Aquecendo sistema com requisições leves..."
    hey -n 100 -c 10 "$service_url/health" &>/dev/null || true

    sleep 5

    # Benchmark principal
    log_info "Executando benchmark de throughput por $BENCHMARK_DURATION segundos..."
    local results_file="/tmp/throughput_results_$(date +%s).txt"

    timeout "$BENCHMARK_DURATION" hey -z "${BENCHMARK_DURATION}s" -c 20 -o csv "$service_url/health" > "$results_file" 2>&1 || true

    # Analisar resultados
    if [ -f "$results_file" ]; then
        local avg_rps=$(grep -v '^response-time' "$results_file" | wc -l)
        avg_rps=$((avg_rps / BENCHMARK_DURATION))

        log_info "Throughput médio: $avg_rps req/s (target: $THROUGHPUT_TARGET req/s)"

        if [ "$avg_rps" -ge "$THROUGHPUT_TARGET" ]; then
            add_test_result "API Throughput" "PASS" "Throughput: $avg_rps req/s >= $THROUGHPUT_TARGET req/s"
        else
            add_test_result "API Throughput" "FAIL" "Throughput: $avg_rps req/s < $THROUGHPUT_TARGET req/s"
        fi

        # Salvar métricas
        echo "throughput_rps:$avg_rps" >> "$METRICS_FILE"
    else
        add_test_result "API Throughput" "FAIL" "Não foi possível executar benchmark"
    fi

    rm -f "$results_file"
}

# Teste de latência
test_latency_benchmark() {
    log_info "Executando benchmark de latência"

    local service_url=$(get_service_url)
    if [ -z "$service_url" ]; then
        add_test_result "API Latency" "FAIL" "Não foi possível obter URL do serviço"
        return 1
    fi

    # Teste de latência com carga moderada
    log_info "Testando latência com 10 usuários concorrentes..."
    local results_file="/tmp/latency_results_$(date +%s).txt"

    hey -n 1000 -c 10 "$service_url/health" > "$results_file" 2>&1

    # Extrair P95 latency
    local p95_latency=$(grep "95%" "$results_file" | awk '{print $2}' | sed 's/s$//' | awk '{print $1*1000}')

    if [ -n "$p95_latency" ]; then
        local p95_ms=$(echo "$p95_latency" | cut -d. -f1)
        log_info "Latência P95: ${p95_ms}ms (target: ${LATENCY_P95_TARGET}ms)"

        if [ "$p95_ms" -le "$LATENCY_P95_TARGET" ]; then
            add_test_result "API Latency P95" "PASS" "Latência P95: ${p95_ms}ms <= ${LATENCY_P95_TARGET}ms"
        else
            add_test_result "API Latency P95" "FAIL" "Latência P95: ${p95_ms}ms > ${LATENCY_P95_TARGET}ms"
        fi

        echo "latency_p95_ms:$p95_ms" >> "$METRICS_FILE"
    else
        add_test_result "API Latency P95" "FAIL" "Não foi possível extrair latência P95"
    fi

    rm -f "$results_file"
}

# Teste de eficiência de recursos
test_resource_efficiency_benchmark() {
    log_info "Executando benchmark de eficiência de recursos"

    # Coletar métricas de baseline
    local baseline_cpu=$(get_cluster_cpu_usage)
    local baseline_memory=$(get_cluster_memory_usage)

    log_info "Baseline - CPU: ${baseline_cpu}%, Memory: ${baseline_memory}%"

    # Executar carga de trabalho
    local service_url=$(get_service_url)
    if [ -n "$service_url" ]; then
        log_info "Aplicando carga por 2 minutos..."
        timeout 120 hey -z 120s -c 15 "$service_url/health" &>/dev/null &
        local load_pid=$!

        sleep 60  # Aguardar estabilização

        # Coletar métricas sob carga
        local load_cpu=$(get_cluster_cpu_usage)
        local load_memory=$(get_cluster_memory_usage)

        log_info "Sob carga - CPU: ${load_cpu}%, Memory: ${load_memory}%"

        # Parar carga
        kill $load_pid 2>/dev/null || true
        wait $load_pid 2>/dev/null || true

        # Calcular eficiência
        local cpu_increase=$((load_cpu - baseline_cpu))
        local memory_increase=$((load_memory - baseline_memory))

        # Eficiência = recursos não utilizados sob carga
        local cpu_efficiency=$((100 - load_cpu))
        local memory_efficiency=$((100 - load_memory))
        local overall_efficiency=$(((cpu_efficiency + memory_efficiency) / 2))

        log_info "Eficiência de recursos: ${overall_efficiency}% (target: ${RESOURCE_EFFICIENCY_TARGET}%)"

        if [ "$overall_efficiency" -ge "$RESOURCE_EFFICIENCY_TARGET" ]; then
            add_test_result "Resource Efficiency" "PASS" "Eficiência: ${overall_efficiency}% >= ${RESOURCE_EFFICIENCY_TARGET}%"
        else
            add_test_result "Resource Efficiency" "FAIL" "Eficiência: ${overall_efficiency}% < ${RESOURCE_EFFICIENCY_TARGET}%"
        fi

        echo "resource_efficiency_percent:$overall_efficiency" >> "$METRICS_FILE"
        echo "cpu_usage_under_load:$load_cpu" >> "$METRICS_FILE"
        echo "memory_usage_under_load:$load_memory" >> "$METRICS_FILE"
    else
        add_test_result "Resource Efficiency" "FAIL" "Não foi possível obter URL do serviço"
    fi
}

# Teste de performance de armazenamento
test_storage_performance_benchmark() {
    log_info "Executando benchmark de performance de armazenamento"

    # Criar job para teste de I/O
    local test_job="storage-benchmark-$(date +%s)"

    cat <<EOF | kubectl apply -f - &>/dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: $test_job
  namespace: $NAMESPACE
spec:
  template:
    spec:
      containers:
      - name: fio-test
        image: ljishen/fio
        command:
        - fio
        - --name=random-readwrite
        - --ioengine=libaio
        - --iodepth=16
        - --rw=randrw
        - --bs=4k
        - --direct=1
        - --size=1G
        - --numjobs=1
        - --runtime=60
        - --group_reporting
        - --filename=/tmp/test-file
        volumeMounts:
        - name: test-volume
          mountPath: /tmp
      volumes:
      - name: test-volume
        emptyDir: {}
      restartPolicy: Never
  backoffLimit: 1
EOF

    # Aguardar conclusão do job
    log_info "Aguardando conclusão do teste de I/O..."
    kubectl wait --for=condition=complete job/$test_job -n "$NAMESPACE" --timeout=300s

    # Obter resultados
    local job_logs=$(kubectl logs job/$test_job -n "$NAMESPACE" 2>/dev/null || echo "")

    if echo "$job_logs" | grep -q "IOPS"; then
        local read_iops=$(echo "$job_logs" | grep "read:" | grep -o "IOPS=[0-9]*" | cut -d= -f2)
        local write_iops=$(echo "$job_logs" | grep "write:" | grep -o "IOPS=[0-9]*" | cut -d= -f2)

        local avg_iops=$(((read_iops + write_iops) / 2))

        log_info "Performance de armazenamento: ${avg_iops} IOPS (target: ${STORAGE_IOPS_TARGET} IOPS)"

        if [ "$avg_iops" -ge "$STORAGE_IOPS_TARGET" ]; then
            add_test_result "Storage Performance" "PASS" "IOPS: $avg_iops >= $STORAGE_IOPS_TARGET"
        else
            add_test_result "Storage Performance" "FAIL" "IOPS: $avg_iops < $STORAGE_IOPS_TARGET"
        fi

        echo "storage_iops:$avg_iops" >> "$METRICS_FILE"
    else
        add_test_result "Storage Performance" "FAIL" "Não foi possível extrair métricas de IOPS"
    fi

    # Limpeza
    kubectl delete job $test_job -n "$NAMESPACE" &>/dev/null || true
}

# Teste de usuários concorrentes
test_concurrent_users_benchmark() {
    log_info "Executando benchmark de usuários concorrentes"

    local service_url=$(get_service_url)
    if [ -z "$service_url" ]; then
        add_test_result "Concurrent Users" "FAIL" "Não foi possível obter URL do serviço"
        return 1
    fi

    log_info "Testando $CONCURRENT_USERS usuários concorrentes por 2 minutos..."

    local results_file="/tmp/concurrent_results_$(date +%s).txt"
    local error_file="/tmp/concurrent_errors_$(date +%s).txt"

    # Executar teste de concorrência
    hey -z 120s -c "$CONCURRENT_USERS" "$service_url/health" > "$results_file" 2>"$error_file"

    # Analisar resultados
    local total_requests=$(grep "Total:" "$results_file" | awk '{print $2}')
    local failed_requests=$(grep "Failed:" "$results_file" | awk '{print $2}' || echo "0")
    local success_rate=$(((total_requests - failed_requests) * 100 / total_requests))

    log_info "Taxa de sucesso com $CONCURRENT_USERS usuários: ${success_rate}%"

    if [ "$success_rate" -ge 95 ]; then
        add_test_result "Concurrent Users" "PASS" "Taxa de sucesso: ${success_rate}% com $CONCURRENT_USERS usuários"
    else
        add_test_result "Concurrent Users" "FAIL" "Taxa de sucesso: ${success_rate}% < 95% com $CONCURRENT_USERS usuários"
    fi

    echo "concurrent_users_success_rate:$success_rate" >> "$METRICS_FILE"
    echo "concurrent_users_count:$CONCURRENT_USERS" >> "$METRICS_FILE"

    rm -f "$results_file" "$error_file"
}

# Teste de pressão de memória
test_memory_pressure_benchmark() {
    log_info "Executando benchmark de pressão de memória"

    # Criar job para teste de memória
    local test_job="memory-pressure-$(date +%s)"

    cat <<EOF | kubectl apply -f - &>/dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: $test_job
  namespace: $NAMESPACE
spec:
  template:
    spec:
      containers:
      - name: memory-test
        image: progrium/stress
        args:
        - "--vm"
        - "2"
        - "--vm-bytes"
        - "512M"
        - "--timeout"
        - "60s"
        resources:
          requests:
            memory: "1Gi"
          limits:
            memory: "1Gi"
      restartPolicy: Never
  backoffLimit: 1
EOF

    # Monitorar métricas durante o teste
    local start_time=$(date +%s)
    kubectl wait --for=condition=complete job/$test_job -n "$NAMESPACE" --timeout=120s &
    local wait_pid=$!

    sleep 30  # Aguardar início do teste

    # Coletar métricas de memória
    local memory_usage=$(get_cluster_memory_usage)
    local pod_memory=$(kubectl top pods -n "$NAMESPACE" --no-headers | awk '{sum+=$3} END {print sum}' | sed 's/Mi//')

    wait $wait_pid
    local job_status=$?

    if [ $job_status -eq 0 ]; then
        log_info "Teste de pressão de memória concluído. Uso de memória: ${memory_usage}%"

        if [ "$memory_usage" -lt 90 ]; then
            add_test_result "Memory Pressure" "PASS" "Sistema estável sob pressão de memória (${memory_usage}% uso)"
        else
            add_test_result "Memory Pressure" "WARN" "Alto uso de memória detectado (${memory_usage}%)"
        fi

        echo "memory_pressure_test_usage:$memory_usage" >> "$METRICS_FILE"
    else
        add_test_result "Memory Pressure" "FAIL" "Teste de pressão de memória falhou"
    fi

    # Limpeza
    kubectl delete job $test_job -n "$NAMESPACE" &>/dev/null || true
}

# Teste de throughput de rede
test_network_throughput_benchmark() {
    log_info "Executando benchmark de throughput de rede"

    # Criar pods de teste de rede
    local client_pod="network-client-$(date +%s)"
    local server_pod="network-server-$(date +%s)"

    # Servidor iperf3
    cat <<EOF | kubectl apply -f - &>/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: $server_pod
  namespace: $NAMESPACE
  labels:
    app: network-test-server
spec:
  containers:
  - name: iperf3-server
    image: networkstatic/iperf3
    args: ["-s"]
    ports:
    - containerPort: 5201
EOF

    # Aguardar servidor estar pronto
    kubectl wait --for=condition=ready pod/$server_pod -n "$NAMESPACE" --timeout=60s

    # Cliente iperf3
    cat <<EOF | kubectl apply -f - &>/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: $client_pod
  namespace: $NAMESPACE
spec:
  containers:
  - name: iperf3-client
    image: networkstatic/iperf3
    command: ["sleep", "300"]
EOF

    kubectl wait --for=condition=ready pod/$client_pod -n "$NAMESPACE" --timeout=60s

    # Obter IP do servidor
    local server_ip=$(kubectl get pod $server_pod -n "$NAMESPACE" -o jsonpath='{.status.podIP}')

    # Executar teste de throughput
    log_info "Executando teste de throughput de rede..."
    local throughput_result=$(kubectl exec $client_pod -n "$NAMESPACE" -- iperf3 -c "$server_ip" -t 30 -J 2>/dev/null | jq -r '.end.sum_received.bits_per_second // empty' | head -1)

    if [ -n "$throughput_result" ]; then
        local throughput_mbps=$(echo "scale=2; $throughput_result / 1000000" | bc)
        log_info "Throughput de rede: ${throughput_mbps} Mbps"

        # Considerar 100 Mbps como target mínimo
        local throughput_check=$(echo "$throughput_mbps > 100" | bc)
        if [ "$throughput_check" -eq 1 ]; then
            add_test_result "Network Throughput" "PASS" "Throughput: ${throughput_mbps} Mbps > 100 Mbps"
        else
            add_test_result "Network Throughput" "FAIL" "Throughput: ${throughput_mbps} Mbps < 100 Mbps"
        fi

        echo "network_throughput_mbps:$throughput_mbps" >> "$METRICS_FILE"
    else
        add_test_result "Network Throughput" "FAIL" "Não foi possível medir throughput de rede"
    fi

    # Limpeza
    kubectl delete pod $server_pod $client_pod -n "$NAMESPACE" &>/dev/null || true
}

# Teste de performance de banco de dados
test_database_performance_benchmark() {
    log_info "Executando benchmark de performance de banco de dados"

    # Verificar se há um pod de banco de dados
    local db_pods=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o name 2>/dev/null || kubectl get pods -n "$NAMESPACE" -l app=mysql -o name 2>/dev/null || echo "")

    if [ -z "$db_pods" ]; then
        add_test_result "Database Performance" "SKIP" "Nenhum banco de dados encontrado"
        return 0
    fi

    local db_pod=$(echo "$db_pods" | head -1 | cut -d/ -f2)
    log_info "Testando performance do banco de dados no pod: $db_pod"

    # Teste simples de conectividade e tempo de resposta
    local start_time=$(date +%s%N)
    local db_test_result=$(kubectl exec "$db_pod" -n "$NAMESPACE" -- psql -U postgres -c "SELECT 1;" 2>/dev/null || kubectl exec "$db_pod" -n "$NAMESPACE" -- mysql -u root -e "SELECT 1;" 2>/dev/null || echo "FAIL")
    local end_time=$(date +%s%N)

    local response_time_ms=$(((end_time - start_time) / 1000000))

    if echo "$db_test_result" | grep -q "1"; then
        log_info "Tempo de resposta do banco: ${response_time_ms}ms"

        if [ "$response_time_ms" -lt 100 ]; then
            add_test_result "Database Performance" "PASS" "Tempo de resposta: ${response_time_ms}ms < 100ms"
        else
            add_test_result "Database Performance" "WARN" "Tempo de resposta: ${response_time_ms}ms >= 100ms"
        fi

        echo "database_response_time_ms:$response_time_ms" >> "$METRICS_FILE"
    else
        add_test_result "Database Performance" "FAIL" "Não foi possível conectar ao banco de dados"
    fi
}

# Obter URL do serviço
get_service_url() {
    local service_name=$(kubectl get services -n "$NAMESPACE" -o name | head -1 | cut -d/ -f2)
    if [ -n "$service_name" ]; then
        local service_port=$(kubectl get service "$service_name" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}')
        echo "http://${service_name}.${NAMESPACE}.svc.cluster.local:${service_port}"
    fi
}

# Obter uso de CPU do cluster
get_cluster_cpu_usage() {
    kubectl top nodes --no-headers | awk '{sum+=$3} END {print sum}' | sed 's/%//' || echo "0"
}

# Obter uso de memória do cluster
get_cluster_memory_usage() {
    kubectl top nodes --no-headers | awk '{sum+=$5} END {print sum}' | sed 's/%//' || echo "0"
}

# Gerar relatório de performance
generate_performance_report() {
    log_info "Gerando relatório de performance"

    local report_file="$RESULTS_DIR/performance_benchmark_report.html"

    cat > "$report_file" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Neural Hive-Mind - Relatório de Performance</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #2196F3; color: white; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .metric { display: inline-block; margin: 10px; padding: 10px; background: #f5f5f5; border-radius: 3px; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .warn { color: orange; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Neural Hive-Mind - Relatório de Performance</h1>
        <p>Gerado em: $(date)</p>
    </div>

    <div class="section">
        <h2>Resumo de Performance</h2>
        <div class="metric">
            <strong>Throughput:</strong> $(grep "throughput_rps:" "$METRICS_FILE" | cut -d: -f2 || echo "N/A") req/s
        </div>
        <div class="metric">
            <strong>Latência P95:</strong> $(grep "latency_p95_ms:" "$METRICS_FILE" | cut -d: -f2 || echo "N/A") ms
        </div>
        <div class="metric">
            <strong>Eficiência de Recursos:</strong> $(grep "resource_efficiency_percent:" "$METRICS_FILE" | cut -d: -f2 || echo "N/A")%
        </div>
        <div class="metric">
            <strong>IOPS de Armazenamento:</strong> $(grep "storage_iops:" "$METRICS_FILE" | cut -d: -f2 || echo "N/A")
        </div>
    </div>

    <div class="section">
        <h2>Resultados dos Testes</h2>
        <table>
            <tr><th>Teste</th><th>Resultado</th><th>Detalhes</th></tr>
EOF

    # Adicionar resultados dos testes
    while IFS=: read -r test_name status details; do
        local css_class="pass"
        [ "$status" = "FAIL" ] && css_class="fail"
        [ "$status" = "WARN" ] && css_class="warn"

        echo "            <tr><td>$test_name</td><td class=\"$css_class\">$status</td><td>$details</td></tr>" >> "$report_file"
    done < <(jq -r '.test_results | to_entries[] | "\(.key):\(.value.status):\(.value.details)"' "$REPORT_FILE" 2>/dev/null)

    cat >> "$report_file" << EOF
        </table>
    </div>

    <div class="section">
        <h2>Métricas Detalhadas</h2>
        <pre>$(cat "$METRICS_FILE" 2>/dev/null | sort)</pre>
    </div>
</body>
</html>
EOF

    log_info "Relatório de performance salvo em: $report_file"
}

# Executar função principal se script for chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi