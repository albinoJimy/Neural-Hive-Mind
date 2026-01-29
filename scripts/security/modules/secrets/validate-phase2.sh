#!/bin/bash
#
# Validate Phase 2 Secrets for Neural Hive Mind
#
# This script validates that all required Kubernetes secrets exist
# and contain the expected keys for Phase 2 services.
#
# Usage:
#   ./scripts/validate-phase2-secrets.sh
#   ./scripts/validate-phase2-secrets.sh --report-file ./reports/secrets-validation.txt
#   ./scripts/validate-phase2-secrets.sh --fix  # Attempt to create missing secrets
#
# Exit codes:
#   0 - All secrets validated successfully
#   1 - One or more secrets are missing or invalid
#

set -euo pipefail

# Check required dependencies
check_dependencies() {
    local missing_deps=()

    if ! command -v kubectl &>/dev/null; then
        missing_deps+=("kubectl")
    fi

    if ! command -v base64 &>/dev/null; then
        missing_deps+=("base64")
    fi

    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        echo -e "\033[0;31m[ERROR]\033[0m Missing required dependencies: ${missing_deps[*]}"
        echo "Please install the missing tools before running this script."
        exit 1
    fi
}

check_dependencies

# Default values
REPORT_FILE="${REPORT_FILE:-./reports/phase2-secrets-validation.txt}"
FIX_MODE="false"
VERBOSE="false"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Counters
TOTAL_SECRETS=0
VALID_SECRETS=0
INVALID_SECRETS=0
MISSING_SECRETS=0
MISSING_KEYS=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "[INFO] $1" >> "$REPORT_FILE"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
    echo "[OK] $1" >> "$REPORT_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[WARN] $1" >> "$REPORT_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[ERROR] $1" >> "$REPORT_FILE"
}

log_detail() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${CYAN}  -> ${NC}$1"
    fi
    echo "  -> $1" >> "$REPORT_FILE"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --report-file)
                REPORT_FILE="$2"
                shift 2
                ;;
            --fix)
                FIX_MODE="true"
                shift
                ;;
            --verbose|-v)
                VERBOSE="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

show_help() {
    cat << EOF
Neural Hive Mind - Phase 2 Secrets Validator

Usage: $0 [OPTIONS]

Options:
    --report-file FILE  Output report file (default: ./reports/phase2-secrets-validation.txt)
    --fix               Attempt to create missing secrets using create-phase2-secrets.sh
    --verbose, -v       Show detailed output
    --help, -h          Show this help message

Examples:
    # Validate all secrets
    $0

    # Validate with verbose output
    $0 --verbose

    # Validate and fix missing secrets
    $0 --fix

EOF
}

# Check if namespace exists
check_namespace() {
    local namespace=$1
    if kubectl get namespace "$namespace" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Validate a single secret
validate_secret() {
    local namespace=$1
    local secret_name=$2
    shift 2
    local required_keys=("$@")

    ((TOTAL_SECRETS++))

    log_info "Validating secret: $secret_name in namespace: $namespace"

    # Check if namespace exists
    if ! check_namespace "$namespace"; then
        log_error "Namespace $namespace does not exist"
        ((MISSING_SECRETS++))
        return 1
    fi

    # Check if secret exists
    if ! kubectl get secret "$secret_name" -n "$namespace" &>/dev/null; then
        log_error "Secret $secret_name not found in namespace $namespace"
        ((MISSING_SECRETS++))
        return 1
    fi

    # Get all keys from the secret (without jq dependency)
    # Uses go-template to extract keys directly
    local existing_keys
    existing_keys=$(kubectl get secret "$secret_name" -n "$namespace" -o go-template='{{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}' 2>/dev/null || echo "")

    if [[ -z "$existing_keys" ]]; then
        log_error "Secret $secret_name exists but has no data"
        ((INVALID_SECRETS++))
        return 1
    fi

    # Validate each required key
    local all_keys_valid=true
    for key in "${required_keys[@]}"; do
        if echo "$existing_keys" | grep -q "^${key}$"; then
            # Check if value is valid base64
            local value
            value=$(kubectl get secret "$secret_name" -n "$namespace" -o jsonpath="{.data.${key}}" 2>/dev/null)
            if [[ -n "$value" ]]; then
                if echo "$value" | base64 -d &>/dev/null; then
                    log_detail "Key $key: present and valid"
                else
                    log_warn "Key $key: present but invalid base64 encoding"
                    all_keys_valid=false
                    ((MISSING_KEYS++))
                fi
            else
                log_warn "Key $key: present but empty"
                all_keys_valid=false
                ((MISSING_KEYS++))
            fi
        else
            log_error "Key $key: MISSING"
            all_keys_valid=false
            ((MISSING_KEYS++))
        fi
    done

    if [[ "$all_keys_valid" == "true" ]]; then
        log_success "Secret $secret_name validated successfully"
        ((VALID_SECRETS++))
        return 0
    else
        log_error "Secret $secret_name has missing or invalid keys"
        ((INVALID_SECRETS++))
        return 1
    fi
}

# Validate secrets connectivity (optional deep validation)
validate_connectivity() {
    local namespace=$1
    local secret_name=$2
    local connection_type=$3
    local connection_key=$4

    log_info "Testing connectivity for $secret_name ($connection_type)"

    case $connection_type in
        mongodb)
            local uri
            uri=$(kubectl get secret "$secret_name" -n "$namespace" -o jsonpath="{.data.${connection_key}}" | base64 -d)
            # Note: Actual connection test would require a test pod
            log_detail "MongoDB URI configured (connectivity test requires test pod)"
            ;;
        postgres)
            log_detail "PostgreSQL credentials configured (connectivity test requires test pod)"
            ;;
        redis)
            log_detail "Redis password configured (connectivity test requires test pod)"
            ;;
        *)
            log_detail "Unknown connection type: $connection_type"
            ;;
    esac
}

# =============================================================================
# SECRET DEFINITIONS BY NAMESPACE
# =============================================================================

validate_orchestration_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-orchestration"
    log_info "=========================================="

    validate_secret "neural-hive-orchestration" "orchestrator-dynamic-secrets" \
        "POSTGRES_USER" \
        "POSTGRES_PASSWORD" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD"

    validate_secret "neural-hive-orchestration" "execution-ticket-service-secrets" \
        "POSTGRES_PASSWORD" \
        "MONGODB_URI" \
        "JWT_SECRET_KEY"
}

validate_queen_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-queen"
    log_info "=========================================="

    validate_secret "neural-hive-queen" "queen-agent-secrets" \
        "MONGODB_URI" \
        "REDIS_CLUSTER_NODES" \
        "REDIS_PASSWORD" \
        "NEO4J_URI" \
        "NEO4J_USER" \
        "NEO4J_PASSWORD"
}

validate_execution_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-execution"
    log_info "=========================================="

    validate_secret "neural-hive-execution" "worker-agents-secrets" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "ARGOCD_TOKEN" \
        "JENKINS_TOKEN" \
        "SONARQUBE_TOKEN" \
        "SNYK_TOKEN"

    validate_secret "neural-hive-execution" "code-forge-secrets" \
        "POSTGRES_USER" \
        "POSTGRES_PASSWORD" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "GIT_USERNAME" \
        "GIT_TOKEN" \
        "OPENAI_API_KEY" \
        "ANTHROPIC_API_KEY"
}

validate_registry_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-registry"
    log_info "=========================================="

    validate_secret "neural-hive-registry" "service-registry-secrets" \
        "REDIS_PASSWORD" \
        "ETCD_USERNAME" \
        "ETCD_PASSWORD"
}

validate_estrategica_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-estrategica"
    log_info "=========================================="

    validate_secret "neural-hive-estrategica" "scout-agents-secrets" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "REDIS_PASSWORD"

    validate_secret "neural-hive-estrategica" "analyst-agents-secrets" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "NEO4J_PASSWORD" \
        "CLICKHOUSE_PASSWORD" \
        "ELASTICSEARCH_PASSWORD"

    validate_secret "neural-hive-estrategica" "optimizer-agents-secrets" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "MLFLOW_TRACKING_TOKEN"
}

validate_resilience_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-resilience"
    log_info "=========================================="

    validate_secret "neural-hive-resilience" "guard-agents-secrets" \
        "MONGODB_PASSWORD" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD"

    validate_secret "neural-hive-resilience" "self-healing-engine-secrets" \
        "MONGODB_PASSWORD" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_PASSWORD" \
        "PAGERDUTY_API_KEY" \
        "SLACK_WEBHOOK_URL"
}

validate_monitoring_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-monitoring"
    log_info "=========================================="

    validate_secret "neural-hive-monitoring" "sla-management-system-secrets" \
        "POSTGRES_USER" \
        "POSTGRES_PASSWORD" \
        "REDIS_PASSWORD" \
        "PROMETHEUS_BEARER_TOKEN"
}

validate_mcp_secrets() {
    log_info "=========================================="
    log_info "Validating namespace: neural-hive-mcp"
    log_info "=========================================="

    validate_secret "neural-hive-mcp" "mcp-tool-catalog-secrets" \
        "MONGODB_URI" \
        "REDIS_PASSWORD" \
        "KAFKA_SASL_USERNAME" \
        "KAFKA_SASL_PASSWORD" \
        "GITHUB_TOKEN" \
        "GITLAB_TOKEN"
}

# Print summary
print_summary() {
    echo ""
    echo "=========================================="
    echo "VALIDATION SUMMARY"
    echo "=========================================="
    echo ""
    echo "Total secrets checked:  $TOTAL_SECRETS"
    echo "Valid secrets:          $VALID_SECRETS"
    echo "Invalid secrets:        $INVALID_SECRETS"
    echo "Missing secrets:        $MISSING_SECRETS"
    echo "Missing keys:           $MISSING_KEYS"
    echo ""

    if [[ $INVALID_SECRETS -eq 0 ]] && [[ $MISSING_SECRETS -eq 0 ]]; then
        echo -e "${GREEN}All Phase 2 secrets are valid!${NC}"
        echo ""
        echo "All Phase 2 secrets are valid!" >> "$REPORT_FILE"
        return 0
    else
        echo -e "${RED}Some secrets are missing or invalid.${NC}"
        echo ""
        echo "Some secrets are missing or invalid." >> "$REPORT_FILE"

        if [[ "$FIX_MODE" == "true" ]]; then
            echo "Attempting to fix missing secrets..."
            echo ""
            if [[ -x "./scripts/create-phase2-secrets.sh" ]]; then
                ./scripts/create-phase2-secrets.sh --mode static --environment dev
                echo ""
                echo "Secrets created. Please re-run validation."
            else
                echo -e "${RED}create-phase2-secrets.sh not found or not executable${NC}"
            fi
        else
            echo "Run with --fix to attempt automatic creation of missing secrets."
            echo "Or manually run: ./scripts/create-phase2-secrets.sh"
        fi
        return 1
    fi
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    parse_args "$@"

    # Ensure report directory exists
    mkdir -p "$(dirname "$REPORT_FILE")"

    # Initialize report file
    echo "Neural Hive Mind - Phase 2 Secrets Validation Report" > "$REPORT_FILE"
    echo "Generated: $(date -Iseconds)" >> "$REPORT_FILE"
    echo "==========================================" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"

    echo ""
    echo "=============================================="
    echo "Neural Hive Mind - Phase 2 Secrets Validator"
    echo "=============================================="
    echo ""

    # Check kubectl connectivity
    if ! kubectl cluster-info &>/dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
        exit 1
    fi
    log_success "Connected to Kubernetes cluster"
    echo ""

    # Validate all namespaces
    validate_orchestration_secrets || true
    validate_queen_secrets || true
    validate_execution_secrets || true
    validate_registry_secrets || true
    validate_estrategica_secrets || true
    validate_resilience_secrets || true
    validate_monitoring_secrets || true
    validate_mcp_secrets || true

    # Print summary
    print_summary

    # Exit with appropriate code
    if [[ $INVALID_SECRETS -eq 0 ]] && [[ $MISSING_SECRETS -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

main "$@"
