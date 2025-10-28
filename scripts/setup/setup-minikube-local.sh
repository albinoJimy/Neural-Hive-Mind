#!/usr/bin/env bash

################################################################################
# setup-minikube-local.sh
#
# Comprehensive Minikube initialization script that orchestrates the complete
# local cluster setup process for Neural Hive-Mind development.
#
# Purpose: Automate the entire Phase 1 bootstrap process for local development
#
# Usage:
#   ./scripts/setup/setup-minikube-local.sh [OPTIONS]
#
# Options:
#   --clean            Delete existing Minikube cluster and start fresh
#   --skip-validation  Skip validation steps
#   --help             Display this help message
#
################################################################################

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="/tmp"
LOG_FILE="${LOG_DIR}/minikube-setup-$(date +%Y%m%d-%H%M%S).log"

# Minikube Configuration
MINIKUBE_CPUS="${MINIKUBE_CPUS:-4}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-8192}"
MINIKUBE_DISK_SIZE="${MINIKUBE_DISK_SIZE:-20g}"
MINIKUBE_DRIVER="${MINIKUBE_DRIVER:-docker}"
KUBERNETES_VERSION="${KUBERNETES_VERSION:-v1.29.0}"

# Addons to enable
REQUIRED_ADDONS=("ingress" "metrics-server" "storage-provisioner" "registry")

# Flags
CLEAN_INSTALL=false
SKIP_VALIDATION=false
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

log() {
    local message="$1"
    echo -e "${message}" | tee -a "${LOG_FILE}"
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
    log "${MAGENTA}║          Neural Hive-Mind - Minikube Setup                 ║${NC}"
    log "${MAGENTA}║              Phase 1: Bootstrap Local Cluster              ║${NC}"
    log "${MAGENTA}║                                                            ║${NC}"
    log "${MAGENTA}╚════════════════════════════════════════════════════════════╝${NC}"
    log ""
}

cleanup() {
    local exit_code=$?
    if [ ${exit_code} -ne 0 ]; then
        log_error "Setup failed with exit code ${exit_code}"
        log_info "Check logs at: ${LOG_FILE}"
    fi
}

trap cleanup EXIT

# ============================================================================
# COMMAND LINE ARGUMENT PARSING
# ============================================================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --clean)
                CLEAN_INSTALL=true
                shift
                ;;
            --skip-validation)
                SKIP_VALIDATION=true
                shift
                ;;
            --help)
                cat << EOF
Usage: $0 [OPTIONS]

Comprehensive Minikube setup for Neural Hive-Mind local development.

Options:
  --clean            Delete existing Minikube cluster and start fresh
  --skip-validation  Skip validation steps
  --help             Display this help message

Examples:
  $0                    # Normal setup
  $0 --clean            # Clean install
  $0 --skip-validation  # Skip validation

Environment Variables:
  MINIKUBE_CPUS         CPU cores for Minikube (default: 4)
  MINIKUBE_MEMORY       Memory in MB (default: 8192)
  MINIKUBE_DISK_SIZE    Disk size (default: 20g)
  MINIKUBE_DRIVER       Driver to use (default: docker)
  KUBERNETES_VERSION    Kubernetes version (default: v1.29.0)
  CONTINUE_ON_ERROR     Continue on non-critical errors (default: false)

EOF
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                log_info "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}

# ============================================================================
# PREREQUISITE CHECKS
# ============================================================================

check_command() {
    local cmd="$1"
    local min_version="${2:-}"

    if ! command -v "${cmd}" &> /dev/null; then
        log_error "${cmd} is not installed"
        return 1
    fi

    log_success "${cmd} is installed"

    if [ -n "${min_version}" ]; then
        local version
        case "${cmd}" in
            docker)
                version=$(docker --version | awk '{print $3}' | tr -d ',')
                ;;
            minikube)
                version=$(minikube version --short | sed 's/v//')
                ;;
            kubectl)
                version=$(kubectl version --client --short 2>/dev/null | awk '{print $3}' | sed 's/v//')
                ;;
            helm)
                version=$(helm version --short | awk '{print $1}' | sed 's/v//')
                ;;
            yq)
                version=$(yq --version | awk '{print $3}')
                ;;
        esac
        log_info "  Version: ${version} (required: ${min_version}+)"
    fi

    return 0
}

check_prerequisites() {
    log_section "Checking Prerequisites"

    local all_ok=true

    # Check Docker
    if ! check_command docker "24.0.0"; then
        log_error "Docker >= 24.0.0 is required"
        log_info "Install from: https://docs.docker.com/get-docker/"
        all_ok=false
    fi

    # Check if Docker daemon is running
    if command -v docker &> /dev/null; then
        if ! docker info &> /dev/null; then
            log_error "Docker daemon is not running"
            log_info "Start Docker and try again"
            all_ok=false
        fi
    fi

    # Check Minikube
    if ! check_command minikube "1.32.0"; then
        log_error "Minikube >= 1.32.0 is required"
        log_info "Install from: https://minikube.sigs.k8s.io/docs/start/"
        all_ok=false
    fi

    # Check kubectl
    if ! check_command kubectl "1.28.0"; then
        log_error "kubectl >= 1.28.0 is required"
        log_info "Install from: https://kubernetes.io/docs/tasks/tools/"
        all_ok=false
    fi

    # Check Helm
    if ! check_command helm "3.13.0"; then
        log_error "Helm >= 3.13.0 is required"
        log_info "Install from: https://helm.sh/docs/intro/install/"
        all_ok=false
    fi

    # Check yq
    if ! check_command yq "4.0"; then
        log_warning "yq >= 4.0 is recommended"
        log_info "Install from: https://github.com/mikefarah/yq"
        if [ "${CONTINUE_ON_ERROR}" != "true" ]; then
            all_ok=false
        fi
    fi

    # Check envsubst
    if ! check_command envsubst; then
        log_warning "envsubst is recommended (from gettext package)"
        if [ "${CONTINUE_ON_ERROR}" != "true" ]; then
            all_ok=false
        fi
    fi

    if [ "${all_ok}" != "true" ]; then
        log_error "Prerequisites check failed"
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

# ============================================================================
# CONFIGURATION SUMMARY
# ============================================================================

display_configuration() {
    log_section "Configuration Summary"

    log_info "Minikube Configuration:"
    log "  CPUs: ${MINIKUBE_CPUS}"
    log "  Memory: ${MINIKUBE_MEMORY}MB ($(echo "scale=2; ${MINIKUBE_MEMORY}/1024" | bc)GB)"
    log "  Disk: ${MINIKUBE_DISK_SIZE}"
    log "  Driver: ${MINIKUBE_DRIVER}"
    log "  Kubernetes: ${KUBERNETES_VERSION}"
    log ""
    log_info "Options:"
    log "  Clean Install: ${CLEAN_INSTALL}"
    log "  Skip Validation: ${SKIP_VALIDATION}"
    log ""
    log_info "Logs: ${LOG_FILE}"
}

# ============================================================================
# MINIKUBE MANAGEMENT
# ============================================================================

handle_existing_cluster() {
    log_section "Checking Existing Cluster"

    if minikube status &> /dev/null; then
        log_info "Existing Minikube cluster detected"

        if [ "${CLEAN_INSTALL}" = true ]; then
            log_warning "Deleting existing cluster (--clean flag set)"
            minikube delete
            log_success "Cluster deleted"
        else
            log_info "Current cluster status:"
            minikube status || true
            log_warning "Use --clean flag to delete and recreate cluster"
        fi
    else
        log_info "No existing cluster found"
    fi
}

start_minikube() {
    log_section "Starting Minikube"

    log_info "Starting Minikube with:"
    log "  minikube start --driver=${MINIKUBE_DRIVER} --cpus=${MINIKUBE_CPUS} --memory=${MINIKUBE_MEMORY} --disk-size=${MINIKUBE_DISK_SIZE} --kubernetes-version=${KUBERNETES_VERSION}"

    local max_retries=3
    local retry=0

    while [ ${retry} -lt ${max_retries} ]; do
        if minikube start \
            --driver="${MINIKUBE_DRIVER}" \
            --cpus="${MINIKUBE_CPUS}" \
            --memory="${MINIKUBE_MEMORY}" \
            --disk-size="${MINIKUBE_DISK_SIZE}" \
            --kubernetes-version="${KUBERNETES_VERSION}"; then
            log_success "Minikube started successfully"
            return 0
        else
            retry=$((retry + 1))
            log_warning "Minikube start failed (attempt ${retry}/${max_retries})"
            if [ ${retry} -lt ${max_retries} ]; then
                log_info "Retrying in 5 seconds..."
                sleep 5
            fi
        fi
    done

    log_error "Failed to start Minikube after ${max_retries} attempts"
    return 1
}

enable_addons() {
    log_section "Enabling Minikube Addons"

    for addon in "${REQUIRED_ADDONS[@]}"; do
        log_info "Enabling addon: ${addon}"
        if minikube addons enable "${addon}"; then
            log_success "${addon} enabled"
        else
            log_error "Failed to enable ${addon}"
            return 1
        fi
    done

    log_info "Waiting for addons to be ready..."
    sleep 10

    log_success "All addons enabled"
}

wait_for_cluster() {
    log_section "Waiting for Cluster to be Ready"

    log_info "Setting kubectl context to minikube..."
    kubectl config use-context minikube

    log_info "Waiting for node to be Ready..."
    local max_wait=120
    local waited=0

    while [ ${waited} -lt ${max_wait} ]; do
        if kubectl get nodes | grep -q "Ready"; then
            log_success "Node is Ready"
            break
        fi
        sleep 5
        waited=$((waited + 5))
        log_info "  Waited ${waited}s/${max_wait}s..."
    done

    if [ ${waited} -ge ${max_wait} ]; then
        log_error "Timeout waiting for node to be Ready"
        return 1
    fi

    log_info "Waiting for kube-system pods..."
    kubectl wait --for=condition=Ready pods --all -n kube-system --timeout=180s || true

    log_success "Cluster is operational"
}

# ============================================================================
# BOOTSTRAP APPLICATION
# ============================================================================

apply_bootstrap() {
    log_section "Applying Bootstrap Configuration"

    export ENVIRONMENT=local
    log_info "Environment: ${ENVIRONMENT}"

    local bootstrap_script="${PROJECT_ROOT}/scripts/deploy/apply-bootstrap-manifests.sh"

    if [ ! -f "${bootstrap_script}" ]; then
        log_error "Bootstrap script not found: ${bootstrap_script}"
        return 1
    fi

    log_info "Executing: ${bootstrap_script}"

    if bash "${bootstrap_script}"; then
        log_success "Bootstrap configuration applied"
    else
        log_error "Failed to apply bootstrap configuration"
        return 1
    fi
}

# ============================================================================
# VALIDATION
# ============================================================================

run_basic_validation() {
    log_section "Running Basic Validation"

    log_info "Checking cluster connectivity..."
    if kubectl cluster-info &> /dev/null; then
        log_success "Cluster is accessible"
    else
        log_error "Cannot connect to cluster"
        return 1
    fi

    log_info "Checking namespaces..."
    local expected_namespaces=("neural-hive-system" "neural-hive-cognition" "neural-hive-orchestration" "neural-hive-execution" "neural-hive-observability" "cosign-system" "gatekeeper-system" "cert-manager" "auth")
    local missing_namespaces=()

    for ns in "${expected_namespaces[@]}"; do
        if kubectl get namespace "${ns}" &> /dev/null; then
            log_success "  ✓ ${ns}"
        else
            log_error "  ✗ ${ns}"
            missing_namespaces+=("${ns}")
        fi
    done

    if [ ${#missing_namespaces[@]} -gt 0 ]; then
        log_error "Missing namespaces: ${missing_namespaces[*]}"
        return 1
    fi

    log_info "Checking RBAC..."
    if kubectl get clusterroles | grep -q "neural-hive"; then
        log_success "RBAC resources found"
    else
        log_warning "No neural-hive ClusterRoles found"
    fi

    log_info "Checking network policies..."
    if kubectl get networkpolicies -A | grep -q "neural-hive"; then
        log_success "Network policies found"
    else
        log_warning "No network policies found"
    fi

    log_success "Basic validation passed"
}

run_full_validation() {
    log_section "Running Full Validation"

    local validation_script="${PROJECT_ROOT}/scripts/validation/validate-bootstrap-phase.sh"

    if [ ! -f "${validation_script}" ]; then
        log_warning "Validation script not found: ${validation_script}"
        log_info "Skipping full validation"
        return 0
    fi

    log_info "Executing: ${validation_script}"

    if bash "${validation_script}"; then
        log_success "Full validation passed"
    else
        log_error "Full validation failed"
        if [ "${CONTINUE_ON_ERROR}" != "true" ]; then
            return 1
        fi
    fi
}

# ============================================================================
# STATUS REPORT
# ============================================================================

generate_status_report() {
    log_section "Setup Complete - Status Report"

    log_success "Minikube cluster is ready!"
    log ""

    log_info "Cluster Information:"
    kubectl cluster-info | head -n 3
    log ""

    log_info "Node Status:"
    kubectl get nodes
    log ""

    log_info "Namespaces:"
    kubectl get namespaces | grep -E "NAME|neural-hive|cosign|gatekeeper|cert-manager|auth"
    log ""

    log_info "Resource Quotas:"
    kubectl get resourcequotas -A | head -n 10
    log ""

    log_section "Useful Commands"
    log ""
    log "${GREEN}View cluster status:${NC}"
    log "  minikube status"
    log "  kubectl get nodes"
    log ""
    log "${GREEN}Access Kubernetes dashboard:${NC}"
    log "  minikube dashboard"
    log ""
    log "${GREEN}View logs:${NC}"
    log "  minikube logs"
    log ""
    log "${GREEN}SSH into node:${NC}"
    log "  minikube ssh"
    log ""
    log "${GREEN}Stop cluster:${NC}"
    log "  minikube stop"
    log ""
    log "${GREEN}Delete cluster:${NC}"
    log "  minikube delete"
    log ""

    log_section "Next Steps"
    log ""
    log "Phase 1 (Bootstrap) is complete! ✅"
    log ""
    log "Proceed to Phase 2: Deploy Infrastructure Base"
    log "  - Kafka, Redis, MongoDB, Neo4j, ClickHouse"
    log "  - Keycloak for authentication"
    log ""
    log "See: ${PROJECT_ROOT}/DEPLOYMENT_LOCAL.md"
    log ""
    log "Logs saved to: ${LOG_FILE}"
    log ""
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    parse_arguments "$@"

    print_banner
    display_configuration

    check_prerequisites
    handle_existing_cluster
    start_minikube
    enable_addons
    wait_for_cluster
    apply_bootstrap

    if [ "${SKIP_VALIDATION}" != true ]; then
        run_basic_validation
        run_full_validation
    else
        log_warning "Validation skipped (--skip-validation flag set)"
    fi

    generate_status_report

    log_success "Setup completed successfully! 🎉"
}

main "$@"
