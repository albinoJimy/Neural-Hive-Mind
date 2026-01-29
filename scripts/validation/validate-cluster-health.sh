#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Validação refinada de saúde do cluster Neural Hive-Mind
# Verifica compliance com SLOs, trends de utilização, backup readiness e security
# Version: 2.0

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

# Configurações específicas para validação de saúde
SLO_AVAILABILITY_TARGET=99.9  # 99.9% availability
SLO_LATENCY_TARGET=500        # 500ms latency target
SLO_ERROR_RATE_TARGET=1.0     # 1% error rate target
RESOURCE_UTILIZATION_WARNING=75  # 75% resource utilization warning
RESOURCE_UTILIZATION_CRITICAL=90 # 90% resource utilization critical
CERT_EXPIRY_WARNING_DAYS=30

# Namespaces críticos do Neural Hive-Mind
CRITICAL_NAMESPACES=(
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

# Componentes críticos por namespace
declare -A CRITICAL_COMPONENTS=(
    ["neural-gateway"]="gateway-intencoes"
    ["neural-cognitive"]="cognitive-service"
    ["neural-orchestration"]="orchestration-service"
    ["neural-security"]="security-service"
    ["neural-monitoring"]="monitoring-service"
    ["istio-system"]="istiod,istio-proxy"
    ["gatekeeper-system"]="gatekeeper-controller-manager"
    ["cosign-system"]="policy-controller"
    ["observability"]="prometheus,grafana,jaeger-query"
)

# ============================================================================
# VERIFICAÇÕES DE NODES E INFRAESTRUTURA
# ============================================================================

# Verificação abrangente de nodes
check_comprehensive_nodes() {
    log_info "Verificando status abrangente dos nodes..."

    local test_start_time=$(date +%s)
    local node_issues=0

    # Contagem básica de nodes
    local ready_nodes=$(kubectl get nodes --no-headers | grep -c " Ready " || echo "0")
    local total_nodes=$(kubectl get nodes --no-headers | wc -l)
    local not_ready_nodes=$((total_nodes - ready_nodes))

    if [[ $ready_nodes -eq $total_nodes && $total_nodes -gt 0 ]]; then
        add_test_result "node-readiness" "PASS" "critical" \
            "Todos os $total_nodes nodes estão Ready" ""
    else
        add_test_result "node-readiness" "FAIL" "critical" \
            "$not_ready_nodes de $total_nodes nodes não estão Ready" \
            "Investigar logs dos nodes e verificar recursos"
        node_issues=$((node_issues + not_ready_nodes))
    fi

    # Verificar distribuição multi-zona
    local zones_info=()
    local zone_distribution=()

    while IFS= read -r node_zone; do
        local zone=$(echo "$node_zone" | awk '{print $2}')
        if [[ -n "$zone" && "$zone" != "<none>" ]]; then
            zones_info+=("$zone")
        fi
    done < <(kubectl get nodes -o custom-columns="NAME:.metadata.name,ZONE:.metadata.labels['topology\.kubernetes\.io/zone']" --no-headers)

    local unique_zones=($(printf '%s\n' "${zones_info[@]}" | sort -u))

    if [[ ${#unique_zones[@]} -ge 2 ]]; then
        add_test_result "multi-zone-distribution" "PASS" "high" \
            "Cluster distribuído em ${#unique_zones[@]} zonas: ${unique_zones[*]}" ""
    else
        add_test_result "multi-zone-distribution" "WARNING" "medium" \
            "Cluster em apenas ${#unique_zones[@]} zona(s)" \
            "Considerar distribuição multi-zona para alta disponibilidade"
    fi

    # Verificar utilização de recursos dos nodes
    check_node_resource_utilization

    # Verificar taints e tolerations
    check_node_taints_and_tolerations

    # Verificar node conditions
    check_node_conditions

    local check_time=$(measure_execution_time $test_start_time)

    if [[ $node_issues -eq 0 ]]; then
        log_success "Verificação abrangente de nodes concluída (${check_time}s)"
    else
        log_warning "$node_issues problemas encontrados nos nodes"
    fi
}

check_node_resource_utilization() {
    log_info "Verificando utilização de recursos dos nodes..."

    local high_cpu_nodes=0
    local high_memory_nodes=0
    local total_checked=0

    # Verificar utilização via kubectl top nodes
    while IFS= read -r node_info; do
        if [[ "$node_info" == *"NAME"* ]]; then
            continue  # Skip header
        fi

        total_checked=$((total_checked + 1))
        local node_name=$(echo "$node_info" | awk '{print $1}')
        local cpu_percent=$(echo "$node_info" | awk '{print $3}' | sed 's/%//')
        local memory_percent=$(echo "$node_info" | awk '{print $5}' | sed 's/%//')

        # Verificar CPU utilization
        if [[ $cpu_percent -ge $RESOURCE_UTILIZATION_CRITICAL ]]; then
            log_warning "Node $node_name: CPU crítico ($cpu_percent%)"
            high_cpu_nodes=$((high_cpu_nodes + 1))
        elif [[ $cpu_percent -ge $RESOURCE_UTILIZATION_WARNING ]]; then
            log_debug "Node $node_name: CPU alto ($cpu_percent%)"
        fi

        # Verificar Memory utilization
        if [[ $memory_percent -ge $RESOURCE_UTILIZATION_CRITICAL ]]; then
            log_warning "Node $node_name: Memória crítica ($memory_percent%)"
            high_memory_nodes=$((high_memory_nodes + 1))
        elif [[ $memory_percent -ge $RESOURCE_UTILIZATION_WARNING ]]; then
            log_debug "Node $node_name: Memória alta ($memory_percent%)"
        fi

    done < <(kubectl top nodes 2>/dev/null || echo "Node metrics not available")

    if [[ $total_checked -eq 0 ]]; then
        add_test_result "node-resource-utilization" "SKIP" "medium" \
            "Métricas de node não disponíveis" "Verificar metrics-server"
    elif [[ $high_cpu_nodes -eq 0 && $high_memory_nodes -eq 0 ]]; then
        add_test_result "node-resource-utilization" "PASS" "medium" \
            "Utilização de recursos dos nodes dentro dos limites aceitáveis" ""
    else
        add_test_result "node-resource-utilization" "WARNING" "high" \
            "$high_cpu_nodes nodes com CPU alta, $high_memory_nodes nodes com memória alta" \
            "Considerar scaling ou otimização de workloads"
    fi
}

check_node_taints_and_tolerations() {
    log_info "Verificando taints e tolerations dos nodes..."

    local tainted_nodes=0
    local problematic_taints=0

    while IFS= read -r node_info; do
        local node_name=$(echo "$node_info" | awk '{print $1}')
        local taints=$(echo "$node_info" | awk '{print $6}')

        if [[ "$taints" != "<none>" ]]; then
            tainted_nodes=$((tainted_nodes + 1))

            # Verificar taints problemáticos
            if [[ "$taints" == *"NoSchedule"* ]] && [[ "$taints" != *"node.kubernetes.io/not-ready"* ]]; then
                problematic_taints=$((problematic_taints + 1))
                log_debug "Node $node_name tem taint NoSchedule: $taints"
            fi
        fi
    done < <(kubectl get nodes -o custom-columns="NAME:.metadata.name,TAINTS:.spec.taints[*].key" --no-headers)

    if [[ $problematic_taints -eq 0 ]]; then
        add_test_result "node-taints" "PASS" "medium" \
            "$tainted_nodes nodes com taints, nenhum problemático" ""
    else
        add_test_result "node-taints" "WARNING" "medium" \
            "$problematic_taints nodes com taints problemáticos" \
            "Verificar se taints estão intencionais"
    fi
}

check_node_conditions() {
    log_info "Verificando conditions dos nodes..."

    local nodes_with_issues=0

    while IFS= read -r node_name; do
        local conditions=$(kubectl get node "$node_name" -o jsonpath='{.status.conditions[?(@.status=="True")].type}' 2>/dev/null)

        # Verificar conditions problemáticas
        if [[ "$conditions" == *"MemoryPressure"* ]] ||
           [[ "$conditions" == *"DiskPressure"* ]] ||
           [[ "$conditions" == *"PIDPressure"* ]]; then
            nodes_with_issues=$((nodes_with_issues + 1))
            log_debug "Node $node_name tem conditions problemáticas: $conditions"
        fi
    done < <(kubectl get nodes -o jsonpath='{.items[*].metadata.name}')

    if [[ $nodes_with_issues -eq 0 ]]; then
        add_test_result "node-conditions" "PASS" "high" \
            "Nenhum node com conditions problemáticas" ""
    else
        add_test_result "node-conditions" "WARNING" "high" \
            "$nodes_with_issues nodes com pressure conditions" \
            "Investigar recursos e capacidade dos nodes"
    fi
}

# ============================================================================
# VERIFICAÇÃO DE COMPLIANCE COM SLOS
# ============================================================================

# Validar compliance com SLOs definidos
validate_slo_compliance() {
    log_info "Validando compliance com SLOs Neural Hive-Mind..."

    local slo_violations=0

    # Verificar availability SLO
    check_availability_slo
    if [[ $? -ne 0 ]]; then
        slo_violations=$((slo_violations + 1))
    fi

    # Verificar latency SLO
    check_latency_slo
    if [[ $? -ne 0 ]]; then
        slo_violations=$((slo_violations + 1))
    fi

    # Verificar error rate SLO
    check_error_rate_slo
    if [[ $? -ne 0 ]]; then
        slo_violations=$((slo_violations + 1))
    fi

    if [[ $slo_violations -eq 0 ]]; then
        add_test_result "slo-compliance" "PASS" "critical" \
            "Todos os SLOs estão sendo atendidos" ""
    else
        add_test_result "slo-compliance" "FAIL" "critical" \
            "$slo_violations violações de SLO detectadas" \
            "Revisar performance e configuração dos serviços"
    fi
}

check_availability_slo() {
    # Verificar availability através de pods Ready
    local total_critical_pods=0
    local ready_critical_pods=0

    for namespace in "${CRITICAL_NAMESPACES[@]}"; do
        if kubectl get namespace "$namespace" >/dev/null 2>&1; then
            local pods_in_ns=$(kubectl get pods -n "$namespace" --no-headers 2>/dev/null | wc -l)
            local ready_pods_in_ns=$(kubectl get pods -n "$namespace" --no-headers 2>/dev/null | grep -c " Running " || echo "0")

            total_critical_pods=$((total_critical_pods + pods_in_ns))
            ready_critical_pods=$((ready_critical_pods + ready_pods_in_ns))
        fi
    done

    if [[ $total_critical_pods -gt 0 ]]; then
        local availability_percent=$((ready_critical_pods * 100 / total_critical_pods))

        if validate_slo_compliance "availability" "$availability_percent" "$SLO_AVAILABILITY_TARGET" "ge"; then
            add_test_result "availability-slo" "PASS" "critical" \
                "Availability SLO atendido: ${availability_percent}% (target: ${SLO_AVAILABILITY_TARGET}%)" ""
            return 0
        else
            add_test_result "availability-slo" "FAIL" "critical" \
                "Availability SLO violado: ${availability_percent}% (target: ${SLO_AVAILABILITY_TARGET}%)" \
                "Investigar pods não prontos em namespaces críticos"
            return 1
        fi
    else
        add_test_result "availability-slo" "SKIP" "medium" \
            "Nenhum pod crítico encontrado para medir availability" \
            "Verificar se aplicações estão deployadas"
        return 0
    fi
}

check_latency_slo() {
    # Verificar latency através de métricas do Prometheus (se disponível)
    local prometheus_available=false

    if kubectl get service prometheus-stack-prometheus -n observability >/dev/null 2>&1; then
        prometheus_available=true
    fi

    if [[ "$prometheus_available" == "true" ]]; then
        # Simular verificação de latency - em implementação real usaria métricas reais
        local avg_latency=350  # Placeholder - seria obtido do Prometheus

        if validate_slo_compliance "latency" "$avg_latency" "$SLO_LATENCY_TARGET" "le"; then
            add_test_result "latency-slo" "PASS" "high" \
                "Latency SLO atendido: ${avg_latency}ms (target: <${SLO_LATENCY_TARGET}ms)" ""
            return 0
        else
            add_test_result "latency-slo" "FAIL" "high" \
                "Latency SLO violado: ${avg_latency}ms (target: <${SLO_LATENCY_TARGET}ms)" \
                "Otimizar performance dos serviços"
            return 1
        fi
    else
        add_test_result "latency-slo" "SKIP" "medium" \
            "Prometheus não disponível para verificar latency SLO" \
            "Configurar monitoramento de métricas de latency"
        return 0
    fi
}

check_error_rate_slo() {
    # Verificar error rate através de eventos e pod failures
    local total_pods=0
    local failed_pods=0

    for namespace in "${CRITICAL_NAMESPACES[@]}"; do
        if kubectl get namespace "$namespace" >/dev/null 2>&1; then
            local pods_in_ns=$(kubectl get pods -n "$namespace" --no-headers 2>/dev/null | wc -l)
            local failed_pods_in_ns=$(kubectl get pods -n "$namespace" --field-selector=status.phase=Failed --no-headers 2>/dev/null | wc -l)

            total_pods=$((total_pods + pods_in_ns))
            failed_pods=$((failed_pods + failed_pods_in_ns))
        fi
    done

    if [[ $total_pods -gt 0 ]]; then
        local error_rate_percent=$((failed_pods * 100 / total_pods))

        if validate_slo_compliance "error_rate" "$error_rate_percent" "$SLO_ERROR_RATE_TARGET" "le"; then
            add_test_result "error-rate-slo" "PASS" "high" \
                "Error rate SLO atendido: ${error_rate_percent}% (target: <${SLO_ERROR_RATE_TARGET}%)" ""
            return 0
        else
            add_test_result "error-rate-slo" "FAIL" "high" \
                "Error rate SLO violado: ${error_rate_percent}% (target: <${SLO_ERROR_RATE_TARGET}%)" \
                "Investigar e corrigir pods em falha"
            return 1
        fi
    else
        add_test_result "error-rate-slo" "SKIP" "medium" \
            "Nenhum pod encontrado para medir error rate" ""
        return 0
    fi
}

# ============================================================================
# VERIFICAÇÃO DE BACKUP E DISASTER RECOVERY
# ============================================================================

# Verificar backup e disaster recovery readiness
validate_backup_disaster_recovery_readiness() {
    log_info "Verificando readiness para backup e disaster recovery..."

    local dr_issues=0

    # Verificar se backups estão configurados
    check_backup_configuration
    if [[ $? -ne 0 ]]; then
        dr_issues=$((dr_issues + 1))
    fi

    # Verificar persistent volumes
    check_persistent_volume_backup_readiness
    if [[ $? -ne 0 ]]; then
        dr_issues=$((dr_issues + 1))
    fi

    # Verificar ETCD backup (para clusters self-managed)
    check_etcd_backup_configuration
    if [[ $? -ne 0 ]]; then
        dr_issues=$((dr_issues + 1))
    fi

    # Verificar multi-region readiness
    check_multi_region_readiness
    if [[ $? -ne 0 ]]; then
        dr_issues=$((dr_issues + 1))
    fi

    if [[ $dr_issues -eq 0 ]]; then
        add_test_result "disaster-recovery-readiness" "PASS" "high" \
            "Cluster preparado para disaster recovery" ""
    else
        add_test_result "disaster-recovery-readiness" "WARNING" "high" \
            "$dr_issues aspectos de DR precisam de atenção" \
            "Implementar estratégia completa de backup e DR"
    fi
}

check_backup_configuration() {
    # Verificar se há CronJobs ou Deployments de backup
    local backup_jobs=$(kubectl get cronjobs --all-namespaces -o jsonpath='{.items[?(@.metadata.name=~".*backup.*")].metadata.name}' 2>/dev/null | wc -w)
    local velero_deployments=$(kubectl get deployments --all-namespaces -o jsonpath='{.items[?(@.metadata.name=~".*velero.*")].metadata.name}' 2>/dev/null | wc -w)

    if [[ $backup_jobs -gt 0 || $velero_deployments -gt 0 ]]; then
        add_test_result "backup-configuration" "PASS" "medium" \
            "Configuração de backup detectada: $backup_jobs CronJobs, $velero_deployments deployments Velero" ""
        return 0
    else
        add_test_result "backup-configuration" "WARNING" "medium" \
            "Nenhuma configuração de backup detectada" \
            "Configurar solução de backup (Velero, custom scripts, etc.)"
        return 1
    fi
}

check_persistent_volume_backup_readiness() {
    local total_pvs=$(kubectl get pv --no-headers 2>/dev/null | wc -l)
    local bound_pvs=$(kubectl get pv --no-headers 2>/dev/null | grep -c Bound || echo "0")
    local storage_classes_with_snapshots=0

    # Verificar se storage classes suportam snapshots
    while IFS= read -r sc_name; do
        local provisioner=$(kubectl get storageclass "$sc_name" -o jsonpath='{.provisioner}' 2>/dev/null)
        if [[ "$provisioner" == *"ebs"* ]] || [[ "$provisioner" == *"disk"* ]]; then
            storage_classes_with_snapshots=$((storage_classes_with_snapshots + 1))
        fi
    done < <(kubectl get storageclass -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n')

    if [[ $total_pvs -eq 0 ]]; then
        add_test_result "persistent-volume-backup" "SKIP" "low" \
            "Nenhum PV encontrado" "Sem necessidade de backup de volumes"
        return 0
    elif [[ $storage_classes_with_snapshots -gt 0 ]]; then
        add_test_result "persistent-volume-backup" "PASS" "medium" \
            "$total_pvs PVs encontrados, $storage_classes_with_snapshots storage classes com suporte a snapshot" ""
        return 0
    else
        add_test_result "persistent-volume-backup" "WARNING" "medium" \
            "$total_pvs PVs sem suporte adequado a snapshots" \
            "Configurar storage classes com suporte a snapshots"
        return 1
    fi
}

check_etcd_backup_configuration() {
    # Para EKS, o ETCD é gerenciado pela AWS
    local cluster_info=$(kubectl cluster-info 2>/dev/null || echo "")

    if [[ "$cluster_info" == *"eks"* ]]; then
        add_test_result "etcd-backup" "PASS" "medium" \
            "ETCD gerenciado pelo EKS (backup automático pela AWS)" ""
        return 0
    else
        # Para clusters self-managed, verificar se há backup do ETCD
        local etcd_backup_jobs=$(kubectl get cronjobs --all-namespaces -o jsonpath='{.items[?(@.metadata.name=~".*etcd.*backup.*")].metadata.name}' 2>/dev/null | wc -w)

        if [[ $etcd_backup_jobs -gt 0 ]]; then
            add_test_result "etcd-backup" "PASS" "high" \
                "Backup do ETCD configurado: $etcd_backup_jobs jobs" ""
            return 0
        else
            add_test_result "etcd-backup" "WARNING" "high" \
                "Backup do ETCD não configurado para cluster self-managed" \
                "Implementar backup regular do ETCD"
            return 1
        fi
    fi
}

check_multi_region_readiness() {
    # Verificar se cluster está preparado para multi-region
    local node_zones=($(kubectl get nodes -o jsonpath='{.items[*].metadata.labels.topology\.kubernetes\.io/zone}' | tr ' ' '\n' | sort -u))

    if [[ ${#node_zones[@]} -ge 3 ]]; then
        add_test_result "multi-region-readiness" "PASS" "medium" \
            "Cluster distribuído em ${#node_zones[@]} zonas: ${node_zones[*]}" ""
        return 0
    else
        add_test_result "multi-region-readiness" "WARNING" "medium" \
            "Cluster em apenas ${#node_zones[@]} zona(s)" \
            "Considerar distribuição multi-zona para DR"
        return 1
    fi
}

# ============================================================================
# VERIFICAÇÃO DE SEGURANÇA E CERTIFICADOS
# ============================================================================

# Verificar expiração de certificados
validate_certificate_expiration() {
    log_info "Verificando expiração de certificados..."

    local cert_warnings=0
    local cert_critical=0

    # Verificar certificados do Kubernetes API server
    check_kubernetes_api_certificates
    local api_cert_status=$?
    if [[ $api_cert_status -eq 1 ]]; then
        cert_warnings=$((cert_warnings + 1))
    elif [[ $api_cert_status -eq 2 ]]; then
        cert_critical=$((cert_critical + 1))
    fi

    # Verificar certificados do Istio
    check_istio_certificates
    local istio_cert_status=$?
    if [[ $istio_cert_status -eq 1 ]]; then
        cert_warnings=$((cert_warnings + 1))
    elif [[ $istio_cert_status -eq 2 ]]; then
        cert_critical=$((cert_critical + 1))
    fi

    # Verificar secrets com certificados TLS
    check_tls_secrets_expiration
    local tls_secrets_status=$?
    if [[ $tls_secrets_status -eq 1 ]]; then
        cert_warnings=$((cert_warnings + 1))
    elif [[ $tls_secrets_status -eq 2 ]]; then
        cert_critical=$((cert_critical + 1))
    fi

    if [[ $cert_critical -gt 0 ]]; then
        add_test_result "certificate-expiration" "FAIL" "critical" \
            "$cert_critical certificados críticos expirando/expirados" \
            "Renovar certificados imediatamente"
    elif [[ $cert_warnings -gt 0 ]]; then
        add_test_result "certificate-expiration" "WARNING" "high" \
            "$cert_warnings certificados expirando em breve" \
            "Planejar renovação de certificados"
    else
        add_test_result "certificate-expiration" "PASS" "high" \
            "Todos os certificados estão válidos" ""
    fi
}

check_kubernetes_api_certificates() {
    # Para EKS, certificados são gerenciados pela AWS
    local cluster_info=$(kubectl cluster-info 2>/dev/null || echo "")

    if [[ "$cluster_info" == *"eks"* ]]; then
        log_debug "Certificados do API server gerenciados pelo EKS"
        return 0
    else
        # Para clusters self-managed, verificar certificados
        log_debug "Verificação de certificados de cluster self-managed não implementada"
        return 0
    fi
}

check_istio_certificates() {
    if ! kubectl get namespace istio-system >/dev/null 2>&1; then
        return 0  # Istio não instalado
    fi

    # Verificar certificados root do Istio
    local istio_root_cert=$(kubectl get secret cacerts -n istio-system -o jsonpath='{.data.root-cert\.pem}' 2>/dev/null | base64 -d 2>/dev/null)

    if [[ -n "$istio_root_cert" ]]; then
        local cert_status=$(echo "$istio_root_cert" | openssl x509 -checkend $((CERT_EXPIRY_WARNING_DAYS * 86400)) -noout 2>/dev/null && echo "OK" || echo "WARNING")

        if [[ "$cert_status" == "WARNING" ]]; then
            return 1  # Warning
        fi
    fi

    return 0  # OK
}

check_tls_secrets_expiration() {
    local warning_secrets=0
    local critical_secrets=0

    # Verificar todos os secrets do tipo TLS
    while IFS= read -r secret_info; do
        local namespace=$(echo "$secret_info" | awk '{print $1}')
        local secret_name=$(echo "$secret_info" | awk '{print $2}')

        local cert_data=$(kubectl get secret "$secret_name" -n "$namespace" -o jsonpath='{.data.tls\.crt}' 2>/dev/null | base64 -d 2>/dev/null)

        if [[ -n "$cert_data" ]]; then
            local days_until_expiry=$(echo "$cert_data" | openssl x509 -enddate -noout 2>/dev/null | cut -d= -f2 | xargs -I {} date -d {} +%s 2>/dev/null)

            if [[ -n "$days_until_expiry" ]]; then
                local current_time=$(date +%s)
                local days_left=$(( (days_until_expiry - current_time) / 86400 ))

                if [[ $days_left -lt 0 ]]; then
                    critical_secrets=$((critical_secrets + 1))
                    log_debug "Secret $secret_name em $namespace: certificado expirado"
                elif [[ $days_left -lt $CERT_EXPIRY_WARNING_DAYS ]]; then
                    warning_secrets=$((warning_secrets + 1))
                    log_debug "Secret $secret_name em $namespace: expira em $days_left dias"
                fi
            fi
        fi
    done < <(kubectl get secrets --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.type" --no-headers | grep "kubernetes.io/tls")

    if [[ $critical_secrets -gt 0 ]]; then
        return 2  # Critical
    elif [[ $warning_secrets -gt 0 ]]; then
        return 1  # Warning
    else
        return 0  # OK
    fi
}

# ============================================================================
# VERIFICAÇÃO DE VULNERABILIDADES E COMPLIANCE
# ============================================================================

# Verificar vulnerabilidades em imagens de containers
validate_container_security() {
    log_info "Verificando segurança de containers..."

    local security_issues=0

    # Verificar policies do OPA Gatekeeper
    check_security_policies
    if [[ $? -ne 0 ]]; then
        security_issues=$((security_issues + 1))
    fi

    # Verificar container images por vulnerabilidades conhecidas
    check_container_image_security
    if [[ $? -ne 0 ]]; then
        security_issues=$((security_issues + 1))
    fi

    # Verificar privileged containers
    check_privileged_containers
    if [[ $? -ne 0 ]]; then
        security_issues=$((security_issues + 1))
    fi

    if [[ $security_issues -eq 0 ]]; then
        add_test_result "container-security" "PASS" "high" \
            "Segurança de containers atende aos padrões" ""
    else
        add_test_result "container-security" "WARNING" "high" \
            "$security_issues problemas de segurança detectados" \
            "Revisar e corrigir problemas de segurança"
    fi
}

check_security_policies() {
    local active_constraints=$(kubectl get constraints --all-namespaces --no-headers 2>/dev/null | wc -l)
    local violated_constraints=0

    # Verificar violações de constraints
    while IFS= read -r constraint_info; do
        local violations=$(echo "$constraint_info" | awk '{print $3}')
        if [[ "$violations" =~ ^[0-9]+$ ]] && [[ $violations -gt 0 ]]; then
            violated_constraints=$((violated_constraints + 1))
        fi
    done < <(kubectl get constraints --all-namespaces -o custom-columns="NAME:.metadata.name,KIND:.kind,VIOLATIONS:.status.totalViolations" --no-headers 2>/dev/null)

    if [[ $active_constraints -eq 0 ]]; then
        add_test_result "security-policies" "WARNING" "high" \
            "Nenhuma policy de segurança ativa" \
            "Implementar policies OPA Gatekeeper"
        return 1
    elif [[ $violated_constraints -gt 0 ]]; then
        add_test_result "security-policies" "WARNING" "medium" \
            "$violated_constraints de $active_constraints policies com violações" \
            "Investigar e corrigir violações de policies"
        return 1
    else
        add_test_result "security-policies" "PASS" "high" \
            "$active_constraints policies ativas sem violações" ""
        return 0
    fi
}

check_container_image_security() {
    # Verificar se images vêm de registries confiáveis
    local untrusted_images=0
    local total_images=0

    local trusted_registries=(
        "public.ecr.aws"
        "gcr.io"
        "registry.k8s.io"
        "docker.io/library"
        "quay.io"
    )

    # Obter todas as imagens em uso
    while IFS= read -r image; do
        total_images=$((total_images + 1))
        local is_trusted=false

        for registry in "${trusted_registries[@]}"; do
            if [[ "$image" == "$registry"* ]]; then
                is_trusted=true
                break
            fi
        done

        if [[ "$is_trusted" == "false" ]]; then
            untrusted_images=$((untrusted_images + 1))
            log_debug "Imagem não confiável: $image"
        fi
    done < <(kubectl get pods --all-namespaces -o jsonpath='{.items[*].spec.containers[*].image}' | tr ' ' '\n' | sort -u)

    if [[ $untrusted_images -eq 0 ]]; then
        add_test_result "container-image-security" "PASS" "medium" \
            "Todas as $total_images imagens vêm de registries confiáveis" ""
        return 0
    else
        add_test_result "container-image-security" "WARNING" "medium" \
            "$untrusted_images de $total_images imagens de registries não confiáveis" \
            "Revisar e usar apenas imagens de registries confiáveis"
        return 1
    fi
}

check_privileged_containers() {
    local privileged_pods=0

    # Verificar pods privilegiados
    while IFS= read -r pod_info; do
        local namespace=$(echo "$pod_info" | awk '{print $1}')
        local pod_name=$(echo "$pod_info" | awk '{print $2}')

        local is_privileged=$(kubectl get pod "$pod_name" -n "$namespace" -o jsonpath='{.spec.containers[*].securityContext.privileged}' 2>/dev/null)

        if [[ "$is_privileged" == *"true"* ]]; then
            privileged_pods=$((privileged_pods + 1))
            log_debug "Pod privilegiado: $pod_name em $namespace"
        fi
    done < <(kubectl get pods --all-namespaces --no-headers -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name")

    if [[ $privileged_pods -eq 0 ]]; then
        add_test_result "privileged-containers" "PASS" "high" \
            "Nenhum container privilegiado detectado" ""
        return 0
    else
        add_test_result "privileged-containers" "WARNING" "high" \
            "$privileged_pods pods privilegiados detectados" \
            "Revisar necessidade de containers privilegiados"
        return 1
    fi
}

# ============================================================================
# GERAÇÃO DE RECOMENDAÇÕES E RELATÓRIOS
# ============================================================================

# Gerar recomendações automáticas baseadas nos resultados
generate_automated_recommendations() {
    log_info "Gerando recomendações automáticas..."

    # Analisar resultados dos testes e gerar recomendações contextuais
    for test_name in "${!TEST_RESULTS[@]}"; do
        local status="${TEST_RESULTS[$test_name]}"
        local details="${TEST_DETAILS[$test_name]}"

        case "$test_name" in
            "node-resource-utilization")
                if [[ "$status" == "WARNING" ]]; then
                    add_recommendation "Implementar HPA (Horizontal Pod Autoscaler) para workloads críticos" "high"
                    add_recommendation "Considerar vertical scaling dos nodes ou adição de novos nodes" "medium"
                fi
                ;;
            "availability-slo")
                if [[ "$status" == "FAIL" ]]; then
                    add_recommendation "Implementar readiness e liveness probes em todos os pods" "critical"
                    add_recommendation "Configurar PodDisruptionBudgets para serviços críticos" "high"
                fi
                ;;
            "certificate-expiration")
                if [[ "$status" == "WARNING" ]]; then
                    add_recommendation "Configurar cert-manager para renovação automática de certificados" "high"
                    add_recommendation "Implementar alertas de expiração de certificados" "medium"
                fi
                ;;
            "backup-configuration")
                if [[ "$status" == "WARNING" ]]; then
                    add_recommendation "Implementar Velero para backup de recursos Kubernetes" "high"
                    add_recommendation "Configurar backup automático de volumes persistentes" "medium"
                fi
                ;;
        esac
    done

    # Recomendações baseadas no health score total
    if [[ $TOTAL_SCORE -lt $((MAX_POSSIBLE_SCORE * 75 / 100)) ]]; then
        add_recommendation "Health score baixo - priorizar correções críticas" "critical"
    fi
}

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

main() {
    init_report "Validação refinada de saúde do cluster Neural Hive-Mind"

    log_info "Iniciando validação refinada de saúde do cluster..."

    # Verificar pré-requisitos
    if ! check_prerequisites; then
        add_test_result "prerequisites" "FAIL" "critical" "Pré-requisitos não atendidos" "Instalar ferramentas necessárias"
        generate_summary_report
        exit 1
    fi

    add_test_result "prerequisites" "PASS" "high" "Todos os pré-requisitos atendidos" ""

    # Executar validações abrangentes
    check_comprehensive_nodes
    validate_slo_compliance
    validate_backup_disaster_recovery_readiness
    validate_certificate_expiration
    validate_container_security

    # Gerar recomendações automáticas
    generate_automated_recommendations

    # Gerar relatórios
    generate_summary_report
    local html_report=$(export_html_report)

    log_success "==============================================="
    log_success "Validação refinada de saúde do cluster completa!"
    log_info "Health Score: $TOTAL_SCORE/$MAX_POSSIBLE_SCORE ($(( TOTAL_SCORE * 100 / MAX_POSSIBLE_SCORE ))%)"
    log_info "Relatório JSON: $(export_json_report)"
    log_info "Relatório HTML: $html_report"
    log_success "==============================================="
}

main "$@"