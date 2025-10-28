#!/usr/bin/env bash

################################################################################
# validate-bootstrap-phase.sh
#
# Focused validation script specifically for the bootstrap phase that verifies
# all foundational components are correctly configured.
#
# Purpose: Validate that Phase 1 (Preparar Ambiente Kubernetes Local)
#          completed successfully
#
# Usage:
#   ./scripts/validation/validate-bootstrap-phase.sh
#
################################################################################

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPORT_DIR="${PROJECT_ROOT}/.tmp"
REPORT_FILE="${REPORT_DIR}/bootstrap-validation-report.json"

# Expected namespaces
EXPECTED_NAMESPACES=(
    "neural-hive-system"
    "neural-hive-cognition"
    "neural-hive-orchestration"
    "neural-hive-execution"
    "neural-hive-observability"
    "cosign-system"
    "gatekeeper-system"
    "cert-manager"
    "auth"
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

log() {
    echo -e "$1"
}

log_info() {
    log "${BLUE}ℹ️  ${1}${NC}"
}

log_success() {
    log "${GREEN}✅ ${1}${NC}"
}

log_warning() {
    log "${YELLOW}⚠️  ${1}${NC}"
}

log_error() {
    log "${RED}❌ ${1}${NC}"
}

log_section() {
    log ""
    log "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    log "${CYAN}  ${1}${NC}"
    log "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

print_banner() {
    log ""
    log "${MAGENTA}╔════════════════════════════════════════════════════════════╗${NC}"
    log "${MAGENTA}║                                                            ║${NC}"
    log "${MAGENTA}║    Neural Hive-Mind - Bootstrap Phase Validation           ║${NC}"
    log "${MAGENTA}║                                                            ║${NC}"
    log "${MAGENTA}╚════════════════════════════════════════════════════════════╝${NC}"
    log ""
}

check() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
}

pass() {
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    log_success "$1"
}

fail() {
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    log_error "$1"
}

warn() {
    WARNING_CHECKS=$((WARNING_CHECKS + 1))
    log_warning "$1"
}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

validate_cluster_connectivity() {
    log_section "1. Cluster Connectivity"

    check
    if kubectl cluster-info &> /dev/null; then
        pass "kubectl can connect to cluster"
        kubectl cluster-info | head -n 2
    else
        fail "Cannot connect to cluster"
        log_error "Remediation: Check if Minikube is running with 'minikube status'"
        return 1
    fi

    check
    local context
    context=$(kubectl config current-context)
    if [[ "${context}" == "minikube" ]]; then
        pass "Current context is 'minikube'"
    else
        fail "Current context is '${context}', expected 'minikube'"
        log_error "Remediation: Run 'kubectl config use-context minikube'"
        return 1
    fi

    return 0
}

validate_node_health() {
    log_section "2. Node Health"

    check
    local node_status
    node_status=$(kubectl get nodes -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}')
    if [[ "${node_status}" == "True" ]]; then
        pass "Node is Ready"
    else
        fail "Node is not Ready (status: ${node_status})"
        return 1
    fi

    check
    local node_name
    node_name=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
    local cpu_capacity
    cpu_capacity=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.capacity.cpu}')
    if [[ ${cpu_capacity} -ge 4 ]]; then
        pass "Node has sufficient CPUs: ${cpu_capacity}"
    else
        warn "Node has only ${cpu_capacity} CPUs (recommended: 4+)"
    fi

    check
    local memory_capacity
    memory_capacity=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.capacity.memory}')
    local memory_gb
    memory_gb=$(echo "${memory_capacity}" | sed 's/Ki$//' | awk '{print int($1/1024/1024)}')
    if [[ ${memory_gb} -ge 8 ]]; then
        pass "Node has sufficient memory: ${memory_gb}GB"
    else
        warn "Node has only ${memory_gb}GB memory (recommended: 8GB+)"
    fi

    check
    local disk_pressure
    disk_pressure=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.conditions[?(@.type=="DiskPressure")].status}')
    local memory_pressure
    memory_pressure=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.conditions[?(@.type=="MemoryPressure")].status}')
    local pid_pressure
    pid_pressure=$(kubectl get nodes "${node_name}" -o jsonpath='{.status.conditions[?(@.type=="PIDPressure")].status}')

    if [[ "${disk_pressure}" == "False" && "${memory_pressure}" == "False" && "${pid_pressure}" == "False" ]]; then
        pass "Node conditions are healthy (no pressure)"
    else
        fail "Node has pressure conditions - DiskPressure:${disk_pressure} MemoryPressure:${memory_pressure} PIDPressure:${pid_pressure}"
    fi

    return 0
}

validate_addons() {
    log_section "3. Minikube Addons"

    # Check if running on minikube
    local context
    context=$(kubectl config current-context 2>/dev/null || echo "")

    local required_addons=("ingress" "metrics-server" "storage-provisioner")
    # Registry is required when running on minikube
    if [[ "${context}" == "minikube" ]]; then
        required_addons+=("registry")
    fi
    local optional_addons=()

    for addon in "${required_addons[@]}"; do
        check
        if minikube addons list | grep "^| ${addon}" | grep -q "enabled"; then
            pass "${addon} addon is enabled"

            # Check if pods are running
            local addon_ns
            case "${addon}" in
                ingress)
                    addon_ns="ingress-nginx"
                    ;;
                metrics-server)
                    addon_ns="kube-system"
                    ;;
                storage-provisioner)
                    addon_ns="kube-system"
                    ;;
            esac

            if [[ -n "${addon_ns}" ]]; then
                local pod_count
                pod_count=$(kubectl get pods -n "${addon_ns}" 2>/dev/null | grep -c "Running" || echo "0")
                if [[ ${pod_count} -gt 0 ]]; then
                    log_info "  ${addon} has ${pod_count} Running pods in ${addon_ns}"
                fi
            fi
        else
            fail "${addon} addon is not enabled"
            log_error "Remediation: Run 'minikube addons enable ${addon}'"
        fi
    done

    return 0
}

validate_namespaces() {
    log_section "4. Namespace Validation"

    local missing_namespaces=()

    for ns in "${EXPECTED_NAMESPACES[@]}"; do
        check
        if kubectl get namespace "${ns}" &> /dev/null; then
            pass "Namespace '${ns}' exists"

            # Check labels
            local layer_label
            layer_label=$(kubectl get namespace "${ns}" -o jsonpath='{.metadata.labels.neuralhive/layer}' 2>/dev/null || echo "")
            if [[ -n "${layer_label}" ]]; then
                log_info "  Layer: ${layer_label}"
            fi

            # Check pod-security labels
            local pod_security
            pod_security=$(kubectl get namespace "${ns}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || echo "")
            if [[ -n "${pod_security}" ]]; then
                log_info "  Pod Security: ${pod_security}"
            fi
        else
            fail "Namespace '${ns}' does not exist"
            missing_namespaces+=("${ns}")
        fi
    done

    if [[ ${#missing_namespaces[@]} -gt 0 ]]; then
        log_error "Missing namespaces: ${missing_namespaces[*]}"
        log_error "Remediation: Run 'scripts/deploy/apply-bootstrap-manifests.sh'"
        return 1
    fi

    return 0
}

validate_rbac() {
    log_section "5. RBAC Configuration"

    check
    local clusterrole_count
    clusterrole_count=$(kubectl get clusterroles | grep -c "neural-hive" || echo "0")
    if [[ ${clusterrole_count} -gt 0 ]]; then
        pass "Found ${clusterrole_count} neural-hive ClusterRoles"
    else
        fail "No neural-hive ClusterRoles found"
        return 1
    fi

    check
    local serviceaccount_count=0
    for ns in "${EXPECTED_NAMESPACES[@]}"; do
        local sa_count
        sa_count=$(kubectl get serviceaccounts -n "${ns}" 2>/dev/null | grep -c "neural-hive" || echo "0")
        serviceaccount_count=$((serviceaccount_count + sa_count))
    done

    if [[ ${serviceaccount_count} -gt 0 ]]; then
        pass "Found ${serviceaccount_count} neural-hive ServiceAccounts across namespaces"
    else
        warn "No neural-hive ServiceAccounts found"
    fi

    check
    local rolebinding_count
    rolebinding_count=$(kubectl get rolebindings -A | grep -c "neural-hive" || echo "0")
    if [[ ${rolebinding_count} -gt 0 ]]; then
        pass "Found ${rolebinding_count} neural-hive RoleBindings"
    else
        warn "No neural-hive RoleBindings found"
    fi

    check
    local clusterrolebinding_count
    clusterrolebinding_count=$(kubectl get clusterrolebindings | grep -c "neural-hive" || echo "0")
    if [[ ${clusterrolebinding_count} -gt 0 ]]; then
        pass "Found ${clusterrolebinding_count} neural-hive ClusterRoleBindings"
    else
        warn "No neural-hive ClusterRoleBindings found"
    fi

    return 0
}

validate_network_policies() {
    log_section "6. Network Policies"

    check
    local netpol_count
    netpol_count=$(kubectl get networkpolicies -A | grep -c "neural-hive" || echo "0")
    if [[ ${netpol_count} -gt 0 ]]; then
        pass "Found ${netpol_count} neural-hive NetworkPolicies"
    else
        warn "No neural-hive NetworkPolicies found"
        log_warning "Network policies may not be configured"
    fi

    for ns in "${EXPECTED_NAMESPACES[@]}"; do
        check
        local ns_netpol_count
        ns_netpol_count=$(kubectl get networkpolicies -n "${ns}" 2>/dev/null | tail -n +2 | wc -l || echo "0")
        if [[ ${ns_netpol_count} -gt 0 ]]; then
            pass "Namespace '${ns}' has ${ns_netpol_count} NetworkPolicies"
        else
            warn "Namespace '${ns}' has no NetworkPolicies"
        fi
    done

    return 0
}

validate_resource_quotas() {
    log_section "7. Resource Quotas and Limits"

    check
    local quota_count
    quota_count=$(kubectl get resourcequotas -A | tail -n +2 | wc -l || echo "0")
    if [[ ${quota_count} -gt 0 ]]; then
        pass "Found ${quota_count} ResourceQuotas"
    else
        warn "No ResourceQuotas found"
    fi

    check
    local limitrange_count
    limitrange_count=$(kubectl get limitranges -A | tail -n +2 | wc -l || echo "0")
    if [[ ${limitrange_count} -gt 0 ]]; then
        pass "Found ${limitrange_count} LimitRanges"
    else
        warn "No LimitRanges found"
    fi

    # Check for placeholder strings (indicates failed substitution)
    check
    local placeholder_found=false
    for ns in "${EXPECTED_NAMESPACES[@]}"; do
        if kubectl get resourcequotas -n "${ns}" -o yaml 2>/dev/null | grep -q "PLACEHOLDER"; then
            fail "ResourceQuota in '${ns}' contains PLACEHOLDER strings"
            placeholder_found=true
        fi
        if kubectl get limitranges -n "${ns}" -o yaml 2>/dev/null | grep -q "PLACEHOLDER"; then
            fail "LimitRange in '${ns}' contains PLACEHOLDER strings"
            placeholder_found=true
        fi
    done

    if [[ "${placeholder_found}" == "false" ]]; then
        pass "No PLACEHOLDER strings found in ResourceQuotas/LimitRanges"
    else
        log_error "Remediation: Check environments/local/bootstrap-config.yaml and re-run apply-bootstrap-manifests.sh"
    fi

    return 0
}

validate_crds() {
    log_section "8. Custom Resource Definitions (Optional)"

    local expected_crds=(
        "apiassets.catalog.neural-hive.io"
        "dataassets.catalog.neural-hive.io"
    )

    local crd_found=false
    for crd in "${expected_crds[@]}"; do
        check
        if kubectl get crd "${crd}" &> /dev/null; then
            pass "CRD '${crd}' is installed"
            crd_found=true
        else
            warn "CRD '${crd}' is not installed (may be installed in later phases)"
        fi
    done

    if [[ "${crd_found}" == "false" ]]; then
        log_info "No data governance CRDs found yet (expected in later phases)"
    fi

    return 0
}

# ============================================================================
# REPORT GENERATION
# ============================================================================

generate_json_report() {
    mkdir -p "${REPORT_DIR}"

    cat > "${REPORT_FILE}" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "phase": "bootstrap",
  "status": "$([ ${FAILED_CHECKS} -eq 0 ] && echo "PASSED" || echo "FAILED")",
  "summary": {
    "total_checks": ${TOTAL_CHECKS},
    "passed": ${PASSED_CHECKS},
    "failed": ${FAILED_CHECKS},
    "warnings": ${WARNING_CHECKS}
  },
  "details": {
    "cluster_context": "$(kubectl config current-context 2>/dev/null || echo "unknown")",
    "node_count": $(kubectl get nodes --no-headers 2>/dev/null | wc -l || echo "0"),
    "namespace_count": ${#EXPECTED_NAMESPACES[@]},
    "addon_checks": "completed",
    "rbac_checks": "completed",
    "network_policy_checks": "completed",
    "resource_quota_checks": "completed"
  }
}
EOF

    log_info "JSON report saved to: ${REPORT_FILE}"
}

print_summary() {
    log_section "Validation Summary"

    log ""
    log "Total Checks:    ${TOTAL_CHECKS}"
    log "${GREEN}Passed:          ${PASSED_CHECKS}${NC}"
    if [[ ${FAILED_CHECKS} -gt 0 ]]; then
        log "${RED}Failed:          ${FAILED_CHECKS}${NC}"
    else
        log "Failed:          ${FAILED_CHECKS}"
    fi
    if [[ ${WARNING_CHECKS} -gt 0 ]]; then
        log "${YELLOW}Warnings:        ${WARNING_CHECKS}${NC}"
    else
        log "Warnings:        ${WARNING_CHECKS}"
    fi
    log ""

    if [[ ${FAILED_CHECKS} -eq 0 ]]; then
        log_success "🎉 Bootstrap phase validation PASSED!"
        log ""
        log_info "Your Minikube cluster is properly configured for Neural Hive-Mind development."
        log_info "Proceed to Phase 2: Deploy Infrastructure Base"
        return 0
    else
        log_error "Bootstrap phase validation FAILED"
        log ""
        log_error "Please address the failed checks above before proceeding."
        log_error "Common remediation steps:"
        log_error "  1. Re-run: ./scripts/setup/setup-minikube-local.sh --clean"
        log_error "  2. Check: minikube status"
        log_error "  3. Verify: kubectl get all -A"
        return 1
    fi
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    print_banner

    # Run all validations
    validate_cluster_connectivity || true
    validate_node_health || true
    validate_addons || true
    validate_namespaces || true
    validate_rbac || true
    validate_network_policies || true
    validate_resource_quotas || true
    validate_crds || true

    # Generate reports
    generate_json_report
    print_summary

    # Exit with appropriate code
    if [[ ${FAILED_CHECKS} -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

main "$@"
