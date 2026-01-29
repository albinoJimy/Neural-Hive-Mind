#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Teste abrangente do cluster autoscaler para Neural Hive-Mind
# Valida scale-up/down, multi-zone, node affinity, resource contention e performance
# Version: 2.0

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

# Configurações específicas do teste de autoscaler
SCALE_UP_TIMEOUT=600
SCALE_DOWN_TIMEOUT=900
STRESS_TEST_DURATION=300
NODE_READINESS_TIMEOUT=180

# Configurações de workload
CPU_INTENSIVE_REQUESTS="1000m"
MEMORY_INTENSIVE_REQUESTS="2Gi"
MIXED_WORKLOAD_CPU="500m"
MIXED_WORKLOAD_MEMORY="1Gi"

# Imagens para teste
STRESS_IMAGE="vish/stress"
NGINX_IMAGE="nginx:alpine"
BUSYBOX_IMAGE="busybox:latest"

# Labels para identificação
AUTOSCALER_TEST_LABEL="app=neural-autoscaler-test"

# Variáveis globais para rastreamento
INITIAL_NODES=0
INITIAL_ZONES=()
declare -A INITIAL_NODES_PER_ZONE=()

# ============================================================================
# FUNÇÕES DE ESTADO INICIAL E CONFIGURAÇÃO
# ============================================================================

# Registrar estado inicial detalhado do cluster
record_comprehensive_initial_state() {
    log_info "Registrando estado inicial abrangente do cluster..."

    local start_time=$(date +%s)

    # Contagem total de nodes
    INITIAL_NODES=$(kubectl get nodes --no-headers | wc -l)

    # Mapear nodes por zona de disponibilidade
    while IFS= read -r node_zone; do
        local zone=$(echo "$node_zone" | awk '{print $2}')
        local count=${INITIAL_NODES_PER_ZONE[$zone]:-0}
        INITIAL_NODES_PER_ZONE[$zone]=$((count + 1))

        # Adicionar zona ao array se não existir
        if [[ ! " ${INITIAL_ZONES[@]} " =~ " ${zone} " ]]; then
            INITIAL_ZONES+=("$zone")
        fi
    done < <(kubectl get nodes -o custom-columns="NAME:.metadata.name,ZONE:.metadata.labels['topology\.kubernetes\.io/zone']" --no-headers)

    # Coletar métricas iniciais de recursos
    local total_cpu_capacity=$(kubectl describe nodes | grep -A2 "Capacity:" | grep "cpu:" | awk '{sum += $2} END {print sum}')
    local total_memory_capacity=$(kubectl describe nodes | grep -A2 "Capacity:" | grep "memory:" | awk '{sum += $2} END {print sum}')

    # Verificar configuração do autoscaler
    local autoscaler_config=""
    if kubectl get deployment cluster-autoscaler -n kube-system >/dev/null 2>&1; then
        autoscaler_config="Deployment encontrado"
    else
        autoscaler_config="Gerenciado pelo EKS"
    fi

    local record_time=$(measure_execution_time $start_time)

    add_test_result "record-initial-state" "PASS" "high" \
        "Estado inicial: $INITIAL_NODES nodes, ${#INITIAL_ZONES[@]} zonas, CPU: ${total_cpu_capacity}, Autoscaler: ${autoscaler_config} (${record_time}s)" ""

    log_info "Estado inicial registrado:"
    log_info "  Nodes totais: $INITIAL_NODES"
    log_info "  Zonas: ${INITIAL_ZONES[*]}"
    for zone in "${INITIAL_ZONES[@]}"; do
        log_info "    $zone: ${INITIAL_NODES_PER_ZONE[$zone]} nodes"
    done
}

# Verificar configuração e limites do autoscaler
validate_autoscaler_configuration() {
    log_info "Validando configuração do autoscaler..."

    local config_issues=0

    # Verificar se node groups têm autoscaling habilitado
    if command -v aws >/dev/null 2>&1; then
        local nodegroups=$(aws eks describe-nodegroup --cluster-name "${CLUSTER_NAME:-neural-hive-dev}" --nodegroup-name \
            $(aws eks list-nodegroups --cluster-name "${CLUSTER_NAME:-neural-hive-dev}" --query 'nodegroups[0]' --output text) \
            --query 'nodegroup.scalingConfig' 2>/dev/null || echo "{}")

        if [[ "$nodegroups" != "{}" ]]; then
            local min_size=$(echo "$nodegroups" | jq -r '.minSize // 0')
            local max_size=$(echo "$nodegroups" | jq -r '.maxSize // 0')
            local desired_size=$(echo "$nodegroups" | jq -r '.desiredSize // 0')

            if [[ $max_size -le $min_size ]]; then
                config_issues=$((config_issues + 1))
                add_recommendation "Configurar max_size > min_size no node group" "high"
            fi

            log_info "Configuração do node group: min=$min_size, desired=$desired_size, max=$max_size"
        fi
    fi

    # Verificar cluster autoscaler daemon
    local autoscaler_status="unknown"
    if kubectl get deployment cluster-autoscaler -n kube-system >/dev/null 2>&1; then
        autoscaler_status="deployment-found"

        local ready_replicas=$(kubectl get deployment cluster-autoscaler -n kube-system -o jsonpath='{.status.readyReplicas}')
        if [[ "$ready_replicas" != "1" ]]; then
            config_issues=$((config_issues + 1))
        fi
    else
        autoscaler_status="eks-managed"
    fi

    if [[ $config_issues -eq 0 ]]; then
        add_test_result "autoscaler-configuration" "PASS" "high" \
            "Configuração do autoscaler válida ($autoscaler_status)" ""
    else
        add_test_result "autoscaler-configuration" "WARNING" "medium" \
            "$config_issues problemas de configuração detectados" "Revisar configuração do autoscaler"
    fi
}

# ============================================================================
# TESTES DE SCALE-UP
# ============================================================================

# Teste de scale-up gradual com diferentes tipos de carga
test_gradual_scale_up() {
    log_info "Testando scale-up gradual com diferentes cargas de trabalho..."

    local test_start_time=$(date +%s)
    local scale_up_detected=false

    # Deploy workload CPU-intensive
    deploy_cpu_intensive_workload 5
    sleep 30

    # Deploy workload memory-intensive
    deploy_memory_intensive_workload 3
    sleep 30

    # Deploy workload misto
    deploy_mixed_workload 8

    # Monitorar scale-up
    local timeout_time=$(($(date +%s) + SCALE_UP_TIMEOUT))
    local last_node_count=$INITIAL_NODES

    while [[ $(date +%s) -lt $timeout_time ]]; do
        local current_nodes=$(kubectl get nodes --no-headers | wc -l)
        local pending_pods=$(kubectl get pods --all-namespaces --field-selector=status.phase=Pending --no-headers | wc -l)
        local elapsed=$(($(date +%s) - test_start_time))

        log_debug "Scale-up monitoring: ${elapsed}s, nodes: $current_nodes, pending: $pending_pods"

        if [[ $current_nodes -gt $last_node_count ]]; then
            scale_up_detected=true
            local scale_up_time=$(measure_execution_time $test_start_time)

            add_test_result "gradual-scale-up" "PASS" "high" \
                "Scale-up detectado: $INITIAL_NODES -> $current_nodes nodes em ${scale_up_time}s" ""

            log_success "Scale-up gradual bem-sucedido: $INITIAL_NODES -> $current_nodes nodes"
            break
        fi

        last_node_count=$current_nodes
        sleep 20
    done

    if [[ "$scale_up_detected" == "false" ]]; then
        add_test_result "gradual-scale-up" "FAIL" "critical" \
            "Scale-up não detectado após ${SCALE_UP_TIMEOUT}s" \
            "Verificar configuração do autoscaler e recursos disponíveis"
    fi
}

deploy_cpu_intensive_workload() {
    local replicas="$1"

    log_info "Deployando workload CPU-intensive ($replicas replicas)..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cpu-intensive-test
  namespace: neural-hive-execution
  labels:
    $AUTOSCALER_TEST_LABEL
    workload-type: cpu-intensive
spec:
  replicas: $replicas
  selector:
    matchLabels:
      app: cpu-intensive-test
  template:
    metadata:
      labels:
        app: cpu-intensive-test
        $AUTOSCALER_TEST_LABEL
        workload-type: cpu-intensive
    spec:
      containers:
      - name: cpu-stress
        image: $STRESS_IMAGE
        args:
        - -cpus
        - "1"
        resources:
          requests:
            cpu: $CPU_INTENSIVE_REQUESTS
            memory: 256Mi
          limits:
            cpu: $CPU_INTENSIVE_REQUESTS
            memory: 512Mi
      nodeSelector:
        kubernetes.io/os: linux
      tolerations:
      - key: node.kubernetes.io/not-ready
        operator: Exists
        effect: NoSchedule
EOF
}

deploy_memory_intensive_workload() {
    local replicas="$1"

    log_info "Deployando workload memory-intensive ($replicas replicas)..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-intensive-test
  namespace: neural-hive-execution
  labels:
    $AUTOSCALER_TEST_LABEL
    workload-type: memory-intensive
spec:
  replicas: $replicas
  selector:
    matchLabels:
      app: memory-intensive-test
  template:
    metadata:
      labels:
        app: memory-intensive-test
        $AUTOSCALER_TEST_LABEL
        workload-type: memory-intensive
    spec:
      containers:
      - name: memory-stress
        image: $STRESS_IMAGE
        args:
        - -mem-total
        - "1800Mi"
        - -mem-alloc-size
        - "100Mi"
        resources:
          requests:
            cpu: 100m
            memory: $MEMORY_INTENSIVE_REQUESTS
          limits:
            cpu: 200m
            memory: $MEMORY_INTENSIVE_REQUESTS
      nodeSelector:
        kubernetes.io/os: linux
EOF
}

deploy_mixed_workload() {
    local replicas="$1"

    log_info "Deployando workload misto ($replicas replicas)..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mixed-workload-test
  namespace: neural-hive-execution
  labels:
    $AUTOSCALER_TEST_LABEL
    workload-type: mixed
spec:
  replicas: $replicas
  selector:
    matchLabels:
      app: mixed-workload-test
  template:
    metadata:
      labels:
        app: mixed-workload-test
        $AUTOSCALER_TEST_LABEL
        workload-type: mixed
    spec:
      containers:
      - name: mixed-stress
        image: $STRESS_IMAGE
        args:
        - -cpus
        - "0.5"
        - -mem-total
        - "800Mi"
        - -mem-alloc-size
        - "50Mi"
        resources:
          requests:
            cpu: $MIXED_WORKLOAD_CPU
            memory: $MIXED_WORKLOAD_MEMORY
          limits:
            cpu: $MIXED_WORKLOAD_CPU
            memory: $MIXED_WORKLOAD_MEMORY
EOF
}

# ============================================================================
# TESTES MULTI-ZONE E NODE AFFINITY
# ============================================================================

# Teste de scaling multi-zone
test_multi_zone_scaling() {
    log_info "Testando distribuição multi-zone durante scaling..."

    if [[ ${#INITIAL_ZONES[@]} -lt 2 ]]; then
        add_test_result "multi-zone-scaling" "SKIP" "medium" \
            "Cluster tem apenas ${#INITIAL_ZONES[@]} zona(s)" "Configurar cluster multi-zone para teste completo"
        return 0
    fi

    local test_start_time=$(date +%s)

    # Deploy workloads com anti-affinity para forçar distribuição
    for zone in "${INITIAL_ZONES[@]}"; do
        deploy_zone_specific_workload "$zone" 3
    done

    # Aguardar tempo suficiente para scaling
    sleep 120

    # Verificar distribuição de nodes por zona
    local distribution_valid=true
    local current_distribution=()

    for zone in "${INITIAL_ZONES[@]}"; do
        local current_nodes_in_zone=$(kubectl get nodes -l topology.kubernetes.io/zone="$zone" --no-headers | wc -l)
        current_distribution+=("$zone:$current_nodes_in_zone")

        # Verificar se houve scaling nesta zona
        local initial_in_zone=${INITIAL_NODES_PER_ZONE[$zone]:-0}
        if [[ $current_nodes_in_zone -le $initial_in_zone ]]; then
            distribution_valid=false
        fi
    done

    local test_time=$(measure_execution_time $test_start_time)

    if [[ "$distribution_valid" == "true" ]]; then
        add_test_result "multi-zone-scaling" "PASS" "high" \
            "Scaling multi-zone bem-sucedido: ${current_distribution[*]} (${test_time}s)" ""
    else
        add_test_result "multi-zone-scaling" "WARNING" "medium" \
            "Scaling desbalanceado entre zonas: ${current_distribution[*]}" \
            "Verificar configuração de node groups por zona"
    fi
}

deploy_zone_specific_workload() {
    local zone="$1"
    local replicas="$2"
    local workload_name="zone-specific-${zone//[-.]/-}"

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $workload_name
  namespace: neural-hive-execution
  labels:
    $AUTOSCALER_TEST_LABEL
    target-zone: $zone
spec:
  replicas: $replicas
  selector:
    matchLabels:
      app: $workload_name
  template:
    metadata:
      labels:
        app: $workload_name
        $AUTOSCALER_TEST_LABEL
        target-zone: $zone
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: topology.kubernetes.io/zone
                operator: In
                values:
                - $zone
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - $workload_name
            topologyKey: kubernetes.io/hostname
      containers:
      - name: zone-workload
        image: $STRESS_IMAGE
        args:
        - -cpus
        - "0.8"
        - -mem-total
        - "1Gi"
        resources:
          requests:
            cpu: 800m
            memory: 1Gi
          limits:
            cpu: 800m
            memory: 1Gi
EOF
}

# ============================================================================
# TESTES DE SCALE-DOWN E GRACE PERIOD
# ============================================================================

# Teste de scale-down com grace period adequado
test_graceful_scale_down() {
    log_info "Testando scale-down graceful com node draining..."

    local scale_down_start_time=$(date +%s)

    # Remover todos os workloads de teste
    cleanup_autoscaler_workloads

    # Aguardar pods serem terminados
    if ! wait_for_condition "pods terminated" \
        "! kubectl get pods -n neural-hive-execution -l '$AUTOSCALER_TEST_LABEL' --no-headers 2>/dev/null | grep -v Terminating | grep -q ." \
        120; then
        add_test_result "graceful-scale-down" "WARNING" "medium" \
            "Alguns pods ainda em execução após cleanup" "Verificar graceful termination"
    fi

    # Monitorar scale-down
    local scale_down_detected=false
    local timeout_time=$(($(date +%s) + SCALE_DOWN_TIMEOUT))
    local nodes_before_scale_down=$(kubectl get nodes --no-headers | wc -l)

    while [[ $(date +%s) -lt $timeout_time ]]; do
        local current_nodes=$(kubectl get nodes --no-headers | wc -l)
        local elapsed=$(($(date +%s) - scale_down_start_time))

        log_debug "Scale-down monitoring: ${elapsed}s, nodes: $current_nodes"

        if [[ $current_nodes -lt $nodes_before_scale_down ]]; then
            scale_down_detected=true
            local scale_down_time=$(measure_execution_time $scale_down_start_time)

            add_test_result "graceful-scale-down" "PASS" "high" \
                "Scale-down detectado: $nodes_before_scale_down -> $current_nodes nodes em ${scale_down_time}s" ""

            log_success "Scale-down graceful bem-sucedido"
            break
        fi

        sleep 30
    done

    if [[ "$scale_down_detected" == "false" ]]; then
        add_test_result "graceful-scale-down" "WARNING" "medium" \
            "Scale-down não detectado após ${SCALE_DOWN_TIMEOUT}s" \
            "Scale-down pode ser mais lento que o esperado - isso é normal"
    fi
}

# ============================================================================
# TESTES DE RESOURCE CONTENTION E PERFORMANCE
# ============================================================================

# Teste de contenção de recursos
test_resource_contention() {
    log_info "Testando autoscaling sob contenção de recursos..."

    local test_start_time=$(date +%s)

    # Deploy múltiplos workloads competindo por recursos
    deploy_competing_workloads

    # Monitorar métricas de contenção
    local contention_metrics=()
    local timeout_time=$(($(date +%s) + STRESS_TEST_DURATION))

    while [[ $(date +%s) -lt $timeout_time ]]; do
        local pending_pods=$(kubectl get pods -n neural-hive-execution --field-selector=status.phase=Pending --no-headers | wc -l)
        local running_pods=$(kubectl get pods -n neural-hive-execution --field-selector=status.phase=Running --no-headers | wc -l)
        local failed_pods=$(kubectl get pods -n neural-hive-execution --field-selector=status.phase=Failed --no-headers | wc -l)

        contention_metrics+=("pending:$pending_pods,running:$running_pods,failed:$failed_pods")

        # Se temos muitos pods failed, é problema
        if [[ $failed_pods -gt 5 ]]; then
            break
        fi

        sleep 30
    done

    local test_time=$(measure_execution_time $test_start_time)
    local final_failed=$(kubectl get pods -n neural-hive-execution --field-selector=status.phase=Failed --no-headers | wc -l)

    if [[ $final_failed -le 2 ]]; then
        add_test_result "resource-contention" "PASS" "medium" \
            "Contenção de recursos gerenciada adequadamente: $final_failed pods falharam em ${test_time}s" ""
    else
        add_test_result "resource-contention" "WARNING" "medium" \
            "Contenção alta: $final_failed pods falharam" \
            "Considerar ajustar limites de recursos ou políticas de scheduling"
    fi
}

deploy_competing_workloads() {
    # Deploy workloads que competem pelos mesmos recursos
    for i in {1..5}; do
        cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: competing-workload-$i
  namespace: neural-hive-execution
  labels:
    $AUTOSCALER_TEST_LABEL
    competing-group: "true"
spec:
  replicas: 4
  selector:
    matchLabels:
      app: competing-workload-$i
  template:
    metadata:
      labels:
        app: competing-workload-$i
        $AUTOSCALER_TEST_LABEL
        competing-group: "true"
    spec:
      containers:
      - name: competitor
        image: $STRESS_IMAGE
        args:
        - -cpus
        - "0.7"
        - -mem-total
        - "600Mi"
        resources:
          requests:
            cpu: 700m
            memory: 600Mi
          limits:
            cpu: 1000m
            memory: 800Mi
      priorityClassName: system-node-critical
EOF
    done
}

# ============================================================================
# ANÁLISE DE MÉTRICAS E DECISÕES DO AUTOSCALER
# ============================================================================

# Analisar métricas e decisões do autoscaler
analyze_autoscaler_metrics() {
    log_info "Analisando métricas e decisões do autoscaler..."

    local metrics_collected=0
    local decision_events=0

    # Verificar logs do autoscaler se disponível
    if kubectl get deployment cluster-autoscaler -n kube-system >/dev/null 2>&1; then
        local autoscaler_logs=$(kubectl logs -n kube-system deployment/cluster-autoscaler --tail=100 2>/dev/null || echo "")

        decision_events=$(echo "$autoscaler_logs" | grep -c "scale\|node" || echo "0")
        metrics_collected=1

        # Procurar por decisões interessantes
        local scale_up_decisions=$(echo "$autoscaler_logs" | grep -c "scale up" || echo "0")
        local scale_down_decisions=$(echo "$autoscaler_logs" | grep -c "scale down" || echo "0")

        log_info "Decisões do autoscaler: $scale_up_decisions scale-up, $scale_down_decisions scale-down"
    else
        # Para EKS, verificar eventos
        local cluster_events=$(kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep -i autoscal || echo "")
        decision_events=$(echo "$cluster_events" | wc -l)
        metrics_collected=1
    fi

    # Verificar node utilization
    local high_util_nodes=0
    while IFS= read -r node_info; do
        local cpu_percent=$(echo "$node_info" | awk '{print $3}' | sed 's/%//')
        local memory_percent=$(echo "$node_info" | awk '{print $5}' | sed 's/%//')

        if [[ $cpu_percent -gt 80 || $memory_percent -gt 80 ]]; then
            high_util_nodes=$((high_util_nodes + 1))
        fi
    done < <(kubectl top nodes --no-headers 2>/dev/null || echo "unknown 0% 0% 0% 0%")

    add_test_result "autoscaler-metrics" "PASS" "medium" \
        "Métricas coletadas: $decision_events eventos, $high_util_nodes nodes com alta utilização" \
        "Monitorar continuously para otimização"
}

# ============================================================================
# LIMPEZA E RELATÓRIOS
# ============================================================================

# Limpeza abrangente de workloads de teste
cleanup_autoscaler_workloads() {
    log_info "Limpando workloads de teste do autoscaler..."

    # Usar função da biblioteca comum
    cleanup_resources "neural-hive-execution" "$AUTOSCALER_TEST_LABEL"

    # Limpeza adicional específica
    kubectl delete deployments --all -n neural-hive-execution --ignore-not-found=true >/dev/null 2>&1 || true

    log_success "Limpeza de workloads concluída"
}

trap cleanup_autoscaler_workloads EXIT

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

main() {
    init_report "Teste abrangente do Cluster Autoscaler Neural Hive-Mind"

    log_info "Iniciando testes abrangentes do Cluster Autoscaler..."

    # Verificar pré-requisitos
    if ! check_prerequisites; then
        add_test_result "prerequisites" "FAIL" "critical" "Pré-requisitos não atendidos" "Instalar ferramentas necessárias"
        generate_summary_report
        exit 1
    fi

    # Verificar se namespace existe
    if ! kubectl get namespace neural-hive-execution >/dev/null 2>&1; then
        kubectl create namespace neural-hive-execution
        log_info "Namespace neural-hive-execution criado"
    fi

    add_test_result "prerequisites" "PASS" "high" "Todos os pré-requisitos atendidos" ""

    # Executar suite completa de testes
    record_comprehensive_initial_state
    validate_autoscaler_configuration
    test_gradual_scale_up
    test_multi_zone_scaling
    test_resource_contention
    analyze_autoscaler_metrics
    test_graceful_scale_down

    # Gerar relatórios
    generate_summary_report
    local html_report=$(export_html_report)

    log_success "================================================"
    log_success "Testes do Cluster Autoscaler abrangentes completos!"
    log_info "Relatório JSON: $(export_json_report)"
    log_info "Relatório HTML: $html_report"
    log_success "================================================"
}

main "$@"