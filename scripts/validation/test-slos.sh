#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -euo pipefail

# Test SLOs (Service Level Objectives) for Neural Hive-Mind
# This script load-tests the system and validates latency <150ms and availability ≥99.9%

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:-observability}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
LOAD_TEST_DURATION="${LOAD_TEST_DURATION:-300}" # 5 minutes
LOAD_TEST_RPS="${LOAD_TEST_RPS:-50}" # 50 requests per second
TIMEOUT="${TIMEOUT:-60}"

# SLO Targets
LATENCY_SLO_MS=150 # 95th percentile < 150ms
AVAILABILITY_SLO=99.9 # >= 99.9%

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Test identifiers
TEST_SESSION_ID="slo-test-$(date +%s)-$$"
TEST_DOMAIN="slo-test"

cleanup() {
    log_info "Cleaning up test resources..."
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null || true
    # Clean up any port-forwards
    pkill -f "kubectl port-forward" || true
}

trap cleanup EXIT

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if kubectl is available and cluster is accessible
    if ! kubectl cluster-info &>/dev/null; then
        log_error "kubectl not available or cluster not accessible"
        exit 1
    fi

    # Check if observability stack is deployed
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        log_error "Observability namespace '$NAMESPACE' not found"
        exit 1
    fi

    # Check if required services exist
    local required_services=("prometheus-kube-prometheus-prometheus")
    for service in "${required_services[@]}"; do
        if ! kubectl get service "$service" -n "$NAMESPACE" &>/dev/null; then
            log_error "Required service '$service' not found in namespace '$NAMESPACE'"
            exit 1
        fi
    done

    # Check if required tools are available
    for tool in jq curl bc; do
        if ! command -v "$tool" &>/dev/null; then
            log_error "$tool is required but not installed"
            exit 1
        fi
    done

    log_success "All prerequisites satisfied"
}

setup_port_forwards() {
    log_info "Setting up port forwards..."

    # Setup Prometheus port forward
    kubectl port-forward -n "$NAMESPACE" service/prometheus-kube-prometheus-prometheus 9090:9090 >/dev/null 2>&1 &

    # Wait for port forward to be ready
    sleep 10

    # Verify connection
    if ! curl -s http://localhost:9090/-/healthy >/dev/null; then
        log_error "Failed to connect to Prometheus"
        exit 1
    fi

    log_success "Port forwards established"
}

generate_load_test_payload() {
    local intent_id="$1"
    cat <<EOF
{
    "intent_id": "$intent_id",
    "domain": "$TEST_DOMAIN",
    "text": "Load test intent for SLO validation",
    "channel": "slo-test",
    "user_id": "slo-test-user",
    "metadata": {
        "test_type": "slo_validation",
        "test_session": "$TEST_SESSION_ID",
        "test_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    }
}
EOF
}

run_load_test() {
    log_info "Starting load test..."
    log_info "Duration: ${LOAD_TEST_DURATION}s"
    log_info "Rate: ${LOAD_TEST_RPS} RPS"
    log_info "Target: $GATEWAY_URL"

    local total_requests=0
    local successful_requests=0
    local failed_requests=0
    local start_time=$(date +%s)
    local end_time=$((start_time + LOAD_TEST_DURATION))

    # Create temp files for results
    local results_file=$(mktemp)
    local timings_file=$(mktemp)

    # Load test loop
    local request_counter=0
    while [[ $(date +%s) -lt $end_time ]]; do
        for ((i=0; i<LOAD_TEST_RPS; i++)); do
            local current_time=$(date +%s)
            if [[ $current_time -ge $end_time ]]; then
                break 2
            fi

            request_counter=$((request_counter + 1))
            local intent_id="slo-intent-${TEST_SESSION_ID}-${request_counter}"

            # Generate payload
            local payload=$(generate_load_test_payload "$intent_id")

            # Send request in background and measure time
            {
                local request_start=$(date +%s.%3N)
                local response=$(curl -s -w "%{http_code}" -X POST \
                    -H "Content-Type: application/json" \
                    -H "X-Neural-Hive-Intent-ID: $intent_id" \
                    -H "X-Neural-Hive-Domain: $TEST_DOMAIN" \
                    -H "X-Neural-Hive-Channel: slo-test" \
                    -d "$payload" \
                    "$GATEWAY_URL/api/v1/intentions" 2>/dev/null)

                local request_end=$(date +%s.%3N)
                local http_code="${response: -3}"
                local duration=$(echo "$request_end - $request_start" | bc -l)

                echo "$http_code|$duration" >> "$results_file"
            } &

            # Limit concurrent requests
            local job_count=$(jobs -r | wc -l)
            if [[ $job_count -ge 20 ]]; then
                wait -n # Wait for any one job to complete
            fi
        done

        # Sleep to maintain rate (approximately)
        sleep 1
    done

    # Wait for all remaining background jobs
    wait

    log_info "Load test completed, analyzing results..."

    # Analyze results
    while IFS='|' read -r http_code duration; do
        if [[ -n "$http_code" && -n "$duration" ]]; then
            total_requests=$((total_requests + 1))
            echo "$duration" >> "$timings_file"

            if [[ "$http_code" =~ ^(200|201|202)$ ]]; then
                successful_requests=$((successful_requests + 1))
            else
                failed_requests=$((failed_requests + 1))
            fi
        fi
    done < "$results_file"

    # Calculate statistics
    local success_rate=0
    if [[ $total_requests -gt 0 ]]; then
        success_rate=$(echo "scale=2; ($successful_requests * 100) / $total_requests" | bc -l)
    fi

    # Calculate latency percentiles from timings
    local p95_latency=0
    local avg_latency=0
    if [[ -s "$timings_file" ]]; then
        # Sort timings and calculate percentiles
        sort -n "$timings_file" > "${timings_file}.sorted"
        local total_timings=$(wc -l < "${timings_file}.sorted")

        if [[ $total_timings -gt 0 ]]; then
            local p95_index=$(echo "($total_timings * 0.95) / 1" | bc)
            p95_latency=$(sed -n "${p95_index}p" "${timings_file}.sorted")
            avg_latency=$(awk '{sum += $1} END {if (NR > 0) print sum / NR}' "${timings_file}.sorted")
        fi
    fi

    # Convert latency to milliseconds
    local p95_latency_ms=$(echo "$p95_latency * 1000" | bc -l)
    local avg_latency_ms=$(echo "$avg_latency * 1000" | bc -l)

    # Store results in global variables for report
    LOAD_TEST_TOTAL_REQUESTS=$total_requests
    LOAD_TEST_SUCCESSFUL_REQUESTS=$successful_requests
    LOAD_TEST_FAILED_REQUESTS=$failed_requests
    LOAD_TEST_SUCCESS_RATE=$success_rate
    LOAD_TEST_P95_LATENCY_MS=$p95_latency_ms
    LOAD_TEST_AVG_LATENCY_MS=$avg_latency_ms

    # Cleanup temp files
    rm -f "$results_file" "$timings_file" "${timings_file}.sorted"

    log_success "Load test analysis completed"
    log_info "Total requests: $total_requests"
    log_info "Success rate: ${success_rate}%"
    log_info "P95 latency: ${p95_latency_ms}ms"
}

validate_latency_slo() {
    log_info "Validating latency SLO (P95 < ${LATENCY_SLO_MS}ms)..."

    # Wait for metrics to be scraped
    sleep 30

    # Query Prometheus for P95 latency
    local query="histogram_quantile(0.95, rate(neural_hive_captura_duration_seconds_bucket{domain=\"$TEST_DOMAIN\"}[5m]))"
    local url="http://localhost:9090/api/v1/query?query=$(echo "$query" | sed 's/ /%20/g')"

    local response=$(curl -s "$url")

    if echo "$response" | jq -e '.data.result | length > 0' >/dev/null; then
        local p95_seconds=$(echo "$response" | jq -r '.data.result[0].value[1] // "0"')
        local p95_ms=$(echo "$p95_seconds * 1000" | bc -l)

        PROMETHEUS_P95_LATENCY_MS=$p95_ms

        if (( $(echo "$p95_ms <= $LATENCY_SLO_MS" | bc -l) )); then
            log_success "Latency SLO MET: P95 ${p95_ms}ms <= ${LATENCY_SLO_MS}ms"
            return 0
        else
            log_error "Latency SLO VIOLATED: P95 ${p95_ms}ms > ${LATENCY_SLO_MS}ms"
            return 1
        fi
    else
        log_warning "No latency metrics found in Prometheus"

        # Fallback to load test results
        if [[ -n "${LOAD_TEST_P95_LATENCY_MS:-}" ]]; then
            PROMETHEUS_P95_LATENCY_MS=$LOAD_TEST_P95_LATENCY_MS

            if (( $(echo "$LOAD_TEST_P95_LATENCY_MS <= $LATENCY_SLO_MS" | bc -l) )); then
                log_success "Latency SLO MET (load test): P95 ${LOAD_TEST_P95_LATENCY_MS}ms <= ${LATENCY_SLO_MS}ms"
                return 0
            else
                log_error "Latency SLO VIOLATED (load test): P95 ${LOAD_TEST_P95_LATENCY_MS}ms > ${LATENCY_SLO_MS}ms"
                return 1
            fi
        fi

        return 1
    fi
}

validate_availability_slo() {
    log_info "Validating availability SLO (>= ${AVAILABILITY_SLO}%)..."

    # Query Prometheus for error rate
    local error_query="sum(rate(neural_hive_requests_total{domain=\"$TEST_DOMAIN\",status=~\"error|failed\"}[5m]))"
    local total_query="sum(rate(neural_hive_requests_total{domain=\"$TEST_DOMAIN\"}[5m]))"

    local error_url="http://localhost:9090/api/v1/query?query=$(echo "$error_query" | sed 's/ /%20/g')"
    local total_url="http://localhost:9090/api/v1/query?query=$(echo "$total_query" | sed 's/ /%20/g')"

    local error_response=$(curl -s "$error_url")
    local total_response=$(curl -s "$total_url")

    local error_rate=0
    local total_rate=0

    if echo "$error_response" | jq -e '.data.result | length > 0' >/dev/null; then
        error_rate=$(echo "$error_response" | jq -r '.data.result[0].value[1] // "0"')
    fi

    if echo "$total_response" | jq -e '.data.result | length > 0' >/dev/null; then
        total_rate=$(echo "$total_response" | jq -r '.data.result[0].value[1] // "0"')
    fi

    local availability=100
    if (( $(echo "$total_rate > 0" | bc -l) )); then
        local error_percentage=$(echo "($error_rate / $total_rate) * 100" | bc -l)
        availability=$(echo "100 - $error_percentage" | bc -l)
    else
        # Fallback to load test results
        if [[ -n "${LOAD_TEST_SUCCESS_RATE:-}" ]]; then
            availability=$LOAD_TEST_SUCCESS_RATE
            log_info "Using load test availability: ${availability}%"
        fi
    fi

    PROMETHEUS_AVAILABILITY=$availability

    if (( $(echo "$availability >= $AVAILABILITY_SLO" | bc -l) )); then
        log_success "Availability SLO MET: ${availability}% >= ${AVAILABILITY_SLO}%"
        return 0
    else
        log_error "Availability SLO VIOLATED: ${availability}% < ${AVAILABILITY_SLO}%"
        return 1
    fi
}

validate_prometheus_alerts() {
    log_info "Checking Prometheus alerts related to SLOs..."

    local alerts_url="http://localhost:9090/api/v1/alerts"
    local alerts_response=$(curl -s "$alerts_url")

    local active_alerts_count=0
    if echo "$alerts_response" | jq -e '.data.alerts | length > 0' >/dev/null; then
        active_alerts_count=$(echo "$alerts_response" | jq '.data.alerts | length')

        # Check for SLO-related alerts
        local slo_alerts=$(echo "$alerts_response" | jq -r '.data.alerts[] | select(.labels.alertname | contains("SLO") or contains("Latency") or contains("Availability")) | .labels.alertname')

        if [[ -n "$slo_alerts" ]]; then
            log_warning "Active SLO-related alerts found:"
            echo "$slo_alerts" | while read -r alert_name; do
                log_warning "  - $alert_name"
            done
        fi
    fi

    log_info "Total active alerts: $active_alerts_count"
}

generate_slo_report() {
    log_info "Generating SLO validation report..."

    local latency_status="UNKNOWN"
    local availability_status="UNKNOWN"

    # Run SLO validations
    if validate_latency_slo; then
        latency_status="PASSED"
    else
        latency_status="FAILED"
    fi

    if validate_availability_slo; then
        availability_status="PASSED"
    else
        availability_status="FAILED"
    fi

    validate_prometheus_alerts

    cat << EOF

═══════════════════════════════════════
 SLO VALIDATION REPORT
═══════════════════════════════════════

Test Session: $TEST_SESSION_ID
Test Domain: $TEST_DOMAIN
Test Duration: ${LOAD_TEST_DURATION}s
Test Rate: ${LOAD_TEST_RPS} RPS
Timestamp: $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)

Load Test Results:
------------------
Total Requests: ${LOAD_TEST_TOTAL_REQUESTS:-0}
Successful Requests: ${LOAD_TEST_SUCCESSFUL_REQUESTS:-0}
Failed Requests: ${LOAD_TEST_FAILED_REQUESTS:-0}
Success Rate: ${LOAD_TEST_SUCCESS_RATE:-0}%
P95 Latency (Load Test): ${LOAD_TEST_P95_LATENCY_MS:-0}ms
Avg Latency (Load Test): ${LOAD_TEST_AVG_LATENCY_MS:-0}ms

SLO Validation Results:
-----------------------
Latency SLO (P95 < ${LATENCY_SLO_MS}ms): $latency_status
  - Prometheus P95: ${PROMETHEUS_P95_LATENCY_MS:-N/A}ms
  - Load Test P95: ${LOAD_TEST_P95_LATENCY_MS:-N/A}ms

Availability SLO (>= ${AVAILABILITY_SLO}%): $availability_status
  - Prometheus Availability: ${PROMETHEUS_AVAILABILITY:-N/A}%
  - Load Test Availability: ${LOAD_TEST_SUCCESS_RATE:-N/A}%

SLO Summary:
------------
EOF

    if [[ "$latency_status" == "PASSED" && "$availability_status" == "PASSED" ]]; then
        echo "✓ ALL SLOs PASSED - System meets performance targets"
    else
        echo "✗ SLO VIOLATIONS DETECTED - System performance below targets"
    fi

    cat << EOF

Recommendations:
----------------
EOF

    if [[ "$latency_status" == "FAILED" ]]; then
        echo "- Investigate high latency causes"
        echo "- Check system resources and scaling"
        echo "- Review application performance optimizations"
    fi

    if [[ "$availability_status" == "FAILED" ]]; then
        echo "- Investigate error rates and failure patterns"
        echo "- Check system health and dependencies"
        echo "- Review error handling and retry logic"
    fi

    if [[ "$latency_status" == "PASSED" && "$availability_status" == "PASSED" ]]; then
        echo "- System performing within SLO targets"
        echo "- Continue monitoring for sustained performance"
    fi

    cat << EOF

PromQL Queries for Manual Verification:
---------------------------------------
Latency P95:
histogram_quantile(0.95, rate(neural_hive_captura_duration_seconds_bucket{domain="$TEST_DOMAIN"}[5m]))

Availability:
(sum(rate(neural_hive_requests_total{domain="$TEST_DOMAIN"}[5m])) - sum(rate(neural_hive_requests_total{domain="$TEST_DOMAIN",status=~"error|failed"}[5m]))) / sum(rate(neural_hive_requests_total{domain="$TEST_DOMAIN"}[5m])) * 100

Error Rate:
sum(rate(neural_hive_requests_total{domain="$TEST_DOMAIN",status=~"error|failed"}[5m])) / sum(rate(neural_hive_requests_total{domain="$TEST_DOMAIN"}[5m])) * 100

═══════════════════════════════════════
 SLO VALIDATION COMPLETE
═══════════════════════════════════════

EOF
}

main() {
    log_info "Starting Neural Hive-Mind SLO validation test..."

    check_prerequisites
    setup_port_forwards
    run_load_test
    generate_slo_report

    log_success "SLO validation test completed!"
}

# Global variables for results
LOAD_TEST_TOTAL_REQUESTS=0
LOAD_TEST_SUCCESSFUL_REQUESTS=0
LOAD_TEST_FAILED_REQUESTS=0
LOAD_TEST_SUCCESS_RATE=0
LOAD_TEST_P95_LATENCY_MS=0
LOAD_TEST_AVG_LATENCY_MS=0
PROMETHEUS_P95_LATENCY_MS=0
PROMETHEUS_AVAILABILITY=0

# Run main function
main "$@"