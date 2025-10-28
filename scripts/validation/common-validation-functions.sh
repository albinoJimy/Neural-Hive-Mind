#!/bin/bash

# Common Validation Functions Library for Neural Hive-Mind
# Provides standardized logging, reporting, and utility functions for all validation scripts
# Version: 1.0

set -euo pipefail

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

# Script metadata
SCRIPT_NAME="${SCRIPT_NAME:-$(basename "${BASH_SOURCE[0]}")}"
SCRIPT_VERSION="1.0"
SCRIPT_START_TIME=$(date +%s)

# Default timeouts (seconds)
DEFAULT_TIMEOUT=300
KUBECTL_TIMEOUT=60
CURL_TIMEOUT=30
POD_READY_TIMEOUT=300

# Test namespaces for Neural Hive-Mind components
NEURAL_NAMESPACES=(
    "neural-gateway"
    "neural-cognitive"
    "neural-orchestration"
    "neural-security"
    "neural-monitoring"
    "istio-system"
    "opa-gatekeeper-system"
    "sigstore-system"
)

# Report configuration
REPORT_DIR="${REPORT_DIR:-/tmp/neural-hive-validation-reports}"
REPORT_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${REPORT_DIR}/${SCRIPT_NAME}_${REPORT_TIMESTAMP}.json"
HTML_REPORT_FILE="${REPORT_DIR}/${SCRIPT_NAME}_${REPORT_TIMESTAMP}.html"

# Scoring system weights by criticality
declare -A CRITICALITY_WEIGHTS=(
    ["critical"]=10
    ["high"]=7
    ["medium"]=5
    ["low"]=3
    ["info"]=1
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Global variables for report tracking
declare -A TEST_RESULTS=()
declare -A TEST_SCORES=()
declare -A TEST_DETAILS=()
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
TOTAL_SCORE=0
MAX_POSSIBLE_SCORE=0

# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

log_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
    local message="$1"
    echo -e "${BLUE}[INFO]${NC} $(log_timestamp) - ${message}" >&2
}

log_success() {
    local message="$1"
    echo -e "${GREEN}[SUCCESS]${NC} $(log_timestamp) - ${message}" >&2
}

log_error() {
    local message="$1"
    echo -e "${RED}[ERROR]${NC} $(log_timestamp) - ${message}" >&2
}

log_warning() {
    local message="$1"
    echo -e "${YELLOW}[WARNING]${NC} $(log_timestamp) - ${message}" >&2
}

log_test() {
    local test_name="$1"
    local status="$2"
    local details="${3:-}"

    if [[ "$status" == "PASS" ]]; then
        echo -e "${GREEN}[TEST]${NC} $(log_timestamp) - ${test_name}: ${GREEN}PASS${NC}" >&2
    elif [[ "$status" == "FAIL" ]]; then
        echo -e "${RED}[TEST]${NC} $(log_timestamp) - ${test_name}: ${RED}FAIL${NC}" >&2
    else
        echo -e "${YELLOW}[TEST]${NC} $(log_timestamp) - ${test_name}: ${YELLOW}${status}${NC}" >&2
    fi

    if [[ -n "$details" ]]; then
        echo -e "       Details: $details" >&2
    fi
}

log_debug() {
    local message="$1"
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${PURPLE}[DEBUG]${NC} $(log_timestamp) - ${message}" >&2
    fi
}

# ============================================================================
# REPORT MANAGEMENT FUNCTIONS
# ============================================================================

init_report() {
    local script_description="$1"

    mkdir -p "$REPORT_DIR"

    # Initialize JSON report structure
    cat > "$REPORT_FILE" <<EOF
{
  "report_metadata": {
    "script_name": "$SCRIPT_NAME",
    "script_version": "$SCRIPT_VERSION",
    "description": "$script_description",
    "timestamp": "$(date -Iseconds)",
    "execution_start": "$SCRIPT_START_TIME",
    "cluster_context": "$(kubectl config current-context 2>/dev/null || echo 'unknown')",
    "kubernetes_version": "$(kubectl version --short 2>/dev/null | grep 'Server Version' | cut -d: -f2 | tr -d ' ' || echo 'unknown')"
  },
  "test_results": {},
  "summary": {
    "total_tests": 0,
    "passed_tests": 0,
    "failed_tests": 0,
    "total_score": 0,
    "max_possible_score": 0,
    "health_percentage": 0
  },
  "recommendations": []
}
EOF

    log_info "Initialized report file: $REPORT_FILE"
}

add_test_result() {
    local test_name="$1"
    local status="$2"          # PASS, FAIL, SKIP, WARNING
    local criticality="$3"     # critical, high, medium, low, info
    local details="$4"
    local recommendations="${5:-}"
    local execution_time="${6:-0}"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [[ "$status" == "PASS" ]]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        local score=${CRITICALITY_WEIGHTS[$criticality]}
        TOTAL_SCORE=$((TOTAL_SCORE + score))
        TEST_SCORES["$test_name"]=$score
    elif [[ "$status" == "FAIL" ]]; then
        FAILED_TESTS=$((FAILED_TESTS + 1))
        TEST_SCORES["$test_name"]=0
    else
        # SKIP or WARNING - partial credit
        local score=$((${CRITICALITY_WEIGHTS[$criticality]} / 2))
        TOTAL_SCORE=$((TOTAL_SCORE + score))
        TEST_SCORES["$test_name"]=$score
    fi

    MAX_POSSIBLE_SCORE=$((MAX_POSSIBLE_SCORE + ${CRITICALITY_WEIGHTS[$criticality]}))

    TEST_RESULTS["$test_name"]="$status"
    TEST_DETAILS["$test_name"]="$details"

    # Update JSON report
    local temp_file=$(mktemp)
    jq --arg name "$test_name" \
       --arg status "$status" \
       --arg criticality "$criticality" \
       --arg details "$details" \
       --arg recommendations "$recommendations" \
       --arg execution_time "$execution_time" \
       --argjson score "${TEST_SCORES[$test_name]}" \
       '.test_results[$name] = {
         "status": $status,
         "criticality": $criticality,
         "details": $details,
         "recommendations": $recommendations,
         "execution_time": ($execution_time | tonumber),
         "score": $score,
         "timestamp": (now | strftime("%Y-%m-%d %H:%M:%S"))
       }' "$REPORT_FILE" > "$temp_file" && mv "$temp_file" "$REPORT_FILE"

    log_test "$test_name" "$status" "$details"
}

generate_summary_report() {
    local health_percentage=0
    if [[ $MAX_POSSIBLE_SCORE -gt 0 ]]; then
        health_percentage=$((TOTAL_SCORE * 100 / MAX_POSSIBLE_SCORE))
    fi

    local execution_time=$(($(date +%s) - SCRIPT_START_TIME))

    # Update summary in JSON report
    local temp_file=$(mktemp)
    jq --argjson total "$TOTAL_TESTS" \
       --argjson passed "$PASSED_TESTS" \
       --argjson failed "$FAILED_TESTS" \
       --argjson score "$TOTAL_SCORE" \
       --argjson max_score "$MAX_POSSIBLE_SCORE" \
       --argjson health "$health_percentage" \
       --argjson exec_time "$execution_time" \
       '.summary = {
         "total_tests": $total,
         "passed_tests": $passed,
         "failed_tests": $failed,
         "total_score": $score,
         "max_possible_score": $max_score,
         "health_percentage": $health,
         "execution_time": $exec_time,
         "completion_timestamp": (now | strftime("%Y-%m-%d %H:%M:%S"))
       }' "$REPORT_FILE" > "$temp_file" && mv "$temp_file" "$REPORT_FILE"

    # Generate console summary
    echo ""
    echo "============================================================================"
    echo -e "${CYAN}VALIDATION SUMMARY${NC}"
    echo "============================================================================"
    echo "Script: $SCRIPT_NAME"
    echo "Execution Time: ${execution_time}s"
    echo "Total Tests: $TOTAL_TESTS"
    echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
    echo "Health Score: $TOTAL_SCORE/$MAX_POSSIBLE_SCORE (${health_percentage}%)"

    if [[ $health_percentage -ge 90 ]]; then
        echo -e "Overall Status: ${GREEN}EXCELLENT${NC}"
    elif [[ $health_percentage -ge 75 ]]; then
        echo -e "Overall Status: ${GREEN}GOOD${NC}"
    elif [[ $health_percentage -ge 50 ]]; then
        echo -e "Overall Status: ${YELLOW}FAIR${NC}"
    else
        echo -e "Overall Status: ${RED}POOR${NC}"
    fi

    # Show failed tests
    if [[ $FAILED_TESTS -gt 0 ]]; then
        echo ""
        echo -e "${RED}FAILED TESTS:${NC}"
        for test_name in "${!TEST_RESULTS[@]}"; do
            if [[ "${TEST_RESULTS[$test_name]}" == "FAIL" ]]; then
                echo -e "  ${RED}✗${NC} $test_name: ${TEST_DETAILS[$test_name]}"
            fi
        done
    fi

    echo "============================================================================"
    echo "Report saved to: $REPORT_FILE"
}

export_json_report() {
    echo "$REPORT_FILE"
}

export_html_report() {
    local health_percentage=$((TOTAL_SCORE * 100 / MAX_POSSIBLE_SCORE))

    cat > "$HTML_REPORT_FILE" <<EOF
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Neural Hive-Mind Validation Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header { text-align: center; border-bottom: 2px solid #ddd; padding-bottom: 20px; margin-bottom: 30px; }
        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .summary-card { background: #f8f9fa; padding: 15px; border-radius: 6px; text-align: center; border-left: 4px solid #007bff; }
        .test-results { margin-top: 30px; }
        .test-item { margin: 10px 0; padding: 15px; border-radius: 6px; border-left: 4px solid #ddd; }
        .test-pass { border-left-color: #28a745; background-color: #d4edda; }
        .test-fail { border-left-color: #dc3545; background-color: #f8d7da; }
        .test-warning { border-left-color: #ffc107; background-color: #fff3cd; }
        .health-bar { width: 100%; height: 20px; background-color: #e9ecef; border-radius: 10px; overflow: hidden; }
        .health-fill { height: 100%; transition: width 0.3s ease; }
        .criticality { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; color: white; }
        .crit-critical { background-color: #dc3545; }
        .crit-high { background-color: #fd7e14; }
        .crit-medium { background-color: #ffc107; color: #000; }
        .crit-low { background-color: #6c757d; }
        .crit-info { background-color: #17a2b8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Neural Hive-Mind Validation Report</h1>
            <h2>$SCRIPT_NAME</h2>
            <p>Generated: $(date)</p>
        </div>

        <div class="summary">
            <div class="summary-card">
                <h3>Total Tests</h3>
                <h2>$TOTAL_TESTS</h2>
            </div>
            <div class="summary-card">
                <h3>Passed</h3>
                <h2 style="color: #28a745;">$PASSED_TESTS</h2>
            </div>
            <div class="summary-card">
                <h3>Failed</h3>
                <h2 style="color: #dc3545;">$FAILED_TESTS</h2>
            </div>
            <div class="summary-card">
                <h3>Health Score</h3>
                <h2>${health_percentage}%</h2>
                <div class="health-bar">
                    <div class="health-fill" style="width: ${health_percentage}%; background-color: $(
                        if [[ $health_percentage -ge 75 ]]; then echo "#28a745"
                        elif [[ $health_percentage -ge 50 ]]; then echo "#ffc107"
                        else echo "#dc3545"
                        fi
                    );"></div>
                </div>
            </div>
        </div>

        <div class="test-results">
            <h2>Test Results</h2>
EOF

    # Add test results from JSON
    if command -v jq >/dev/null 2>&1; then
        jq -r '.test_results | to_entries[] | @base64' "$REPORT_FILE" | while read -r entry; do
            local decoded=$(echo "$entry" | base64 -d)
            local name=$(echo "$decoded" | jq -r '.key')
            local status=$(echo "$decoded" | jq -r '.value.status')
            local criticality=$(echo "$decoded" | jq -r '.value.criticality')
            local details=$(echo "$decoded" | jq -r '.value.details')

            local css_class=""
            case "$status" in
                "PASS") css_class="test-pass" ;;
                "FAIL") css_class="test-fail" ;;
                *) css_class="test-warning" ;;
            esac

            cat >> "$HTML_REPORT_FILE" <<EOF
            <div class="test-item $css_class">
                <h4>$name <span class="criticality crit-$criticality">$criticality</span></h4>
                <p><strong>Status:</strong> $status</p>
                <p><strong>Details:</strong> $details</p>
            </div>
EOF
        done
    fi

    cat >> "$HTML_REPORT_FILE" <<EOF
        </div>
    </div>
</body>
</html>
EOF

    echo "$HTML_REPORT_FILE"
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

check_prerequisites() {
    local required_tools=("kubectl" "jq" "curl")
    local missing_tools=()

    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_tools+=("$tool")
        fi
    done

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        return 1
    fi

    # Check kubectl connectivity
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    log_success "All prerequisites checked successfully"
    return 0
}

wait_for_condition() {
    local description="$1"
    local command="$2"
    local timeout="${3:-$DEFAULT_TIMEOUT}"
    local interval="${4:-5}"

    log_info "Waiting for condition: $description (timeout: ${timeout}s)"

    local start_time=$(date +%s)
    while true; do
        if eval "$command" >/dev/null 2>&1; then
            local elapsed=$(($(date +%s) - start_time))
            log_success "Condition met: $description (after ${elapsed}s)"
            return 0
        fi

        local elapsed=$(($(date +%s) - start_time))
        if [[ $elapsed -ge $timeout ]]; then
            log_error "Timeout waiting for condition: $description"
            return 1
        fi

        sleep "$interval"
    done
}

cleanup_resources() {
    local namespace="$1"
    local label_selector="${2:-app=neural-validation-test}"

    log_info "Cleaning up test resources in namespace: $namespace"

    kubectl delete pods,services,deployments -n "$namespace" -l "$label_selector" --ignore-not-found=true >/dev/null 2>&1 || true

    # Wait for cleanup to complete
    wait_for_condition "resource cleanup" \
        "! kubectl get pods -n $namespace -l $label_selector --no-headers 2>/dev/null | grep -q ." \
        60
}

measure_execution_time() {
    local start_time="$1"
    local end_time="${2:-$(date +%s)}"
    echo $((end_time - start_time))
}

generate_random_string() {
    local length="${1:-8}"
    head /dev/urandom | tr -dc a-z0-9 | head -c "$length"
}

# ============================================================================
# METRICS COLLECTION FUNCTIONS
# ============================================================================

collect_cluster_metrics() {
    local metrics=()

    # Node metrics
    local node_count=$(kubectl get nodes --no-headers | wc -l)
    local ready_nodes=$(kubectl get nodes --no-headers | grep -c " Ready ")
    metrics+=("nodes_total:$node_count")
    metrics+=("nodes_ready:$ready_nodes")

    # Pod metrics
    local pod_count=$(kubectl get pods --all-namespaces --no-headers | wc -l)
    local running_pods=$(kubectl get pods --all-namespaces --no-headers | grep -c " Running ")
    metrics+=("pods_total:$pod_count")
    metrics+=("pods_running:$running_pods")

    # Namespace metrics
    local namespace_count=$(kubectl get namespaces --no-headers | wc -l)
    metrics+=("namespaces_total:$namespace_count")

    printf '%s\n' "${metrics[@]}"
}

validate_slo_compliance() {
    local slo_type="$1"
    local current_value="$2"
    local threshold="$3"
    local operator="${4:-ge}"  # ge, le, eq, ne

    case "$operator" in
        "ge") [[ $(echo "$current_value >= $threshold" | bc -l) -eq 1 ]] ;;
        "le") [[ $(echo "$current_value <= $threshold" | bc -l) -eq 1 ]] ;;
        "eq") [[ $(echo "$current_value == $threshold" | bc -l) -eq 1 ]] ;;
        "ne") [[ $(echo "$current_value != $threshold" | bc -l) -eq 1 ]] ;;
        *) return 1 ;;
    esac
}

check_resource_utilization() {
    local namespace="$1"
    local resource_type="${2:-cpu}"  # cpu, memory

    # Get resource requests and limits
    local requests=$(kubectl top pods -n "$namespace" --no-headers 2>/dev/null | \
        awk -v type="$resource_type" '{
            if (type == "cpu") sum += $2
            else sum += $3
        } END {print sum+0}')

    echo "${requests:-0}"
}

# ============================================================================
# NETWORK AND CONNECTIVITY FUNCTIONS
# ============================================================================

test_service_connectivity() {
    local source_namespace="$1"
    local target_service="$2"
    local target_namespace="$3"
    local port="${4:-80}"
    local timeout="${5:-$CURL_TIMEOUT}"

    local test_pod="connectivity-test-$(generate_random_string)"

    # Create test pod
    kubectl run "$test_pod" -n "$source_namespace" \
        --image=curlimages/curl:latest \
        --rm -i --restart=Never \
        --timeout="${timeout}s" \
        -- curl -s -o /dev/null -w "%{http_code}" \
        "http://${target_service}.${target_namespace}.svc.cluster.local:${port}/health" \
        2>/dev/null || echo "000"
}

test_dns_resolution() {
    local namespace="$1"
    local fqdn="$2"

    local test_pod="dns-test-$(generate_random_string)"

    kubectl run "$test_pod" -n "$namespace" \
        --image=busybox:latest \
        --rm -i --restart=Never \
        --timeout="30s" \
        -- nslookup "$fqdn" >/dev/null 2>&1
}

# ============================================================================
# CERTIFICATE AND TLS FUNCTIONS
# ============================================================================

check_certificate_expiry() {
    local cert_path="$1"
    local warning_days="${2:-30}"

    if [[ ! -f "$cert_path" ]]; then
        echo "MISSING"
        return 1
    fi

    local expiry_date=$(openssl x509 -in "$cert_path" -noout -enddate 2>/dev/null | cut -d= -f2)
    local expiry_epoch=$(date -d "$expiry_date" +%s 2>/dev/null || echo 0)
    local current_epoch=$(date +%s)
    local days_until_expiry=$(( (expiry_epoch - current_epoch) / 86400 ))

    if [[ $days_until_expiry -lt 0 ]]; then
        echo "EXPIRED"
        return 1
    elif [[ $days_until_expiry -lt $warning_days ]]; then
        echo "WARNING:$days_until_expiry"
        return 1
    else
        echo "OK:$days_until_expiry"
        return 0
    fi
}

validate_mtls_config() {
    local namespace="$1"
    local service="$2"

    # Check if mTLS is enabled via Istio PeerAuthentication
    local peer_auth=$(kubectl get peerauthentication -n "$namespace" -o json 2>/dev/null | \
        jq -r --arg svc "$service" '.items[] | select(.spec.selector.matchLabels.app == $svc) | .spec.mtls.mode // "UNSET"')

    echo "${peer_auth:-UNSET}"
}

# ============================================================================
# KUBERNETES RESOURCE FUNCTIONS
# ============================================================================

wait_for_pod_ready() {
    local namespace="$1"
    local pod_selector="$2"
    local timeout="${3:-$POD_READY_TIMEOUT}"

    wait_for_condition "pod ready" \
        "kubectl get pods -n $namespace -l $pod_selector -o jsonpath='{.items[*].status.conditions[?(@.type==\"Ready\")].status}' | grep -q True" \
        "$timeout"
}

get_pod_logs() {
    local namespace="$1"
    local pod_selector="$2"
    local container="${3:-}"
    local lines="${4:-100}"

    local pod_name=$(kubectl get pods -n "$namespace" -l "$pod_selector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -n "$pod_name" ]]; then
        if [[ -n "$container" ]]; then
            kubectl logs -n "$namespace" "$pod_name" -c "$container" --tail="$lines" 2>/dev/null || echo "No logs available"
        else
            kubectl logs -n "$namespace" "$pod_name" --tail="$lines" 2>/dev/null || echo "No logs available"
        fi
    else
        echo "No pod found with selector: $pod_selector"
    fi
}

check_resource_exists() {
    local resource_type="$1"
    local resource_name="$2"
    local namespace="${3:-}"

    if [[ -n "$namespace" ]]; then
        kubectl get "$resource_type" "$resource_name" -n "$namespace" >/dev/null 2>&1
    else
        kubectl get "$resource_type" "$resource_name" >/dev/null 2>&1
    fi
}

# ============================================================================
# SCORING AND HEALTH FUNCTIONS
# ============================================================================

calculate_component_health() {
    local component="$1"
    shift
    local tests=("$@")

    local component_score=0
    local component_max_score=0

    for test in "${tests[@]}"; do
        if [[ -n "${TEST_SCORES[$test]:-}" ]]; then
            component_score=$((component_score + TEST_SCORES[$test]))
        fi

        # Extract criticality from test details (this would need to be stored separately in practice)
        component_max_score=$((component_max_score + 5))  # Default medium criticality
    done

    local health_percentage=0
    if [[ $component_max_score -gt 0 ]]; then
        health_percentage=$((component_score * 100 / component_max_score))
    fi

    echo "$health_percentage"
}

add_recommendation() {
    local recommendation="$1"
    local priority="${2:-medium}"  # critical, high, medium, low

    local temp_file=$(mktemp)
    jq --arg rec "$recommendation" \
       --arg prio "$priority" \
       '.recommendations += [{"recommendation": $rec, "priority": $prio, "timestamp": (now | strftime("%Y-%m-%d %H:%M:%S"))}]' \
       "$REPORT_FILE" > "$temp_file" && mv "$temp_file" "$REPORT_FILE"
}

# ============================================================================
# INITIALIZATION
# ============================================================================

# Ensure report directory exists
mkdir -p "$REPORT_DIR"

# Export functions for use in other scripts
export -f log_info log_success log_error log_warning log_test log_debug
export -f init_report add_test_result generate_summary_report export_json_report export_html_report
export -f check_prerequisites wait_for_condition cleanup_resources measure_execution_time
export -f collect_cluster_metrics validate_slo_compliance check_resource_utilization
export -f test_service_connectivity test_dns_resolution
export -f check_certificate_expiry validate_mtls_config
export -f wait_for_pod_ready get_pod_logs check_resource_exists
export -f calculate_component_health add_recommendation generate_random_string

# Export global variables
export REPORT_DIR REPORT_FILE HTML_REPORT_FILE
export DEFAULT_TIMEOUT KUBECTL_TIMEOUT CURL_TIMEOUT POD_READY_TIMEOUT
export -a NEURAL_NAMESPACES
export -A CRITICALITY_WEIGHTS

log_info "Common validation functions library loaded successfully"