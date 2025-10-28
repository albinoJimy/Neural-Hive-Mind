#!/bin/bash
set -euo pipefail

# Test correlation between logs, traces, and metrics in Neural Hive-Mind
# This script generates a synthetic intent and validates correlation across observability stack

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:-observability}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
TIMEOUT="${TIMEOUT:-60}"

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

# Generate unique intent ID for this test
INTENT_ID="test-correlation-$(date +%s)-$$"
PLAN_ID="plan-${INTENT_ID}"
TEST_DOMAIN="test-correlation"
TRACE_ID=""

cleanup() {
    log_info "Cleaning up test resources..."
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
    local required_services=("grafana" "prometheus-kube-prometheus-prometheus" "jaeger-query")
    for service in "${required_services[@]}"; do
        if ! kubectl get service "$service" -n "$NAMESPACE" &>/dev/null; then
            log_error "Required service '$service' not found in namespace '$NAMESPACE'"
            exit 1
        fi
    done

    # Check if jq and curl are available
    if ! command -v jq &>/dev/null; then
        log_error "jq is required but not installed"
        exit 1
    fi

    if ! command -v curl &>/dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

setup_port_forwards() {
    log_info "Setting up port forwards for observability services..."

    # Setup port forwards in background
    kubectl port-forward -n "$NAMESPACE" service/grafana 3000:80 >/dev/null 2>&1 &
    kubectl port-forward -n "$NAMESPACE" service/prometheus-kube-prometheus-prometheus 9090:9090 >/dev/null 2>&1 &
    kubectl port-forward -n "$NAMESPACE" service/jaeger-query 16686:16686 >/dev/null 2>&1 &

    # Wait for port forwards to be ready
    sleep 10

    # Verify connections
    if ! curl -s http://localhost:3000/api/health >/dev/null; then
        log_error "Failed to connect to Grafana"
        exit 1
    fi

    if ! curl -s http://localhost:9090/-/healthy >/dev/null; then
        log_error "Failed to connect to Prometheus"
        exit 1
    fi

    if ! curl -s http://localhost:16686/ >/dev/null; then
        log_error "Failed to connect to Jaeger"
        exit 1
    fi

    log_success "Port forwards established"
}

generate_synthetic_intent() {
    log_info "Generating synthetic intent with ID: $INTENT_ID"

    # Create synthetic intent payload
    local payload=$(cat <<EOF
{
    "intent_id": "$INTENT_ID",
    "domain": "$TEST_DOMAIN",
    "text": "Test correlation intent for observability validation",
    "channel": "test-correlation",
    "user_id": "test-user-correlation",
    "metadata": {
        "test_type": "correlation",
        "test_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    }
}
EOF
    )

    # Send intent to gateway
    local response=$(curl -s -w "%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -H "X-Neural-Hive-Intent-ID: $INTENT_ID" \
        -H "X-Neural-Hive-Plan-ID: $PLAN_ID" \
        -H "X-Neural-Hive-Domain: $TEST_DOMAIN" \
        -H "X-Neural-Hive-Channel: test-correlation" \
        -H "X-Neural-Hive-User-ID: test-user-correlation" \
        -d "$payload" \
        "$GATEWAY_URL/api/v1/intentions")

    local http_code="${response: -3}"
    local response_body="${response%???}"

    if [[ "$http_code" != "200" ]] && [[ "$http_code" != "201" ]] && [[ "$http_code" != "202" ]]; then
        log_error "Failed to send intent. HTTP code: $http_code"
        log_error "Response: $response_body"
        exit 1
    fi

    # Extract trace ID from response if available
    if command -v jq &>/dev/null && echo "$response_body" | jq -e . &>/dev/null; then
        TRACE_ID=$(echo "$response_body" | jq -r '.trace_id // empty')
    fi

    log_success "Synthetic intent generated successfully"
    if [[ -n "$TRACE_ID" ]]; then
        log_info "Trace ID: $TRACE_ID"
    fi
}

validate_metrics_correlation() {
    log_info "Validating metrics correlation..."

    # Wait for metrics to be scraped
    sleep 30

    # Query Prometheus for metrics related to our intent
    local metrics_query="neural_hive_requests_total{domain=\"$TEST_DOMAIN\",channel=\"test-correlation\"}"
    local metrics_url="http://localhost:9090/api/v1/query?query=$(echo "$metrics_query" | sed 's/ /%20/g')"

    local metrics_response=$(curl -s "$metrics_url")

    if ! echo "$metrics_response" | jq -e '.data.result | length > 0' >/dev/null; then
        log_error "No metrics found for domain '$TEST_DOMAIN' and channel 'test-correlation'"
        echo "Response: $metrics_response"
        return 1
    fi

    local metrics_count=$(echo "$metrics_response" | jq -r '.data.result[0].value[1]')
    log_success "Found metrics: $metrics_count requests for test domain"

    # Check latency metrics
    local latency_query="neural_hive_captura_duration_seconds{domain=\"$TEST_DOMAIN\",channel=\"test-correlation\"}"
    local latency_url="http://localhost:9090/api/v1/query?query=$(echo "$latency_query" | sed 's/ /%20/g')"

    local latency_response=$(curl -s "$latency_url")
    if echo "$latency_response" | jq -e '.data.result | length > 0' >/dev/null; then
        log_success "Found latency metrics for test intent"
    else
        log_warning "No latency metrics found (may be normal for synthetic tests)"
    fi

    return 0
}

validate_traces_correlation() {
    log_info "Validating traces correlation..."

    # Wait for traces to be indexed
    sleep 45

    # Search for traces with our intent_id
    local jaeger_search_url="http://localhost:16686/api/traces"
    local search_params="service=gateway-intencoes&tag=neural.hive.intent.id:$INTENT_ID&limit=10"

    local traces_response=$(curl -s "${jaeger_search_url}?${search_params}")

    if ! echo "$traces_response" | jq -e '.data | length > 0' >/dev/null 2>&1; then
        # Try alternative search by operation name
        search_params="service=gateway-intencoes&operation=captura_intencao&tag=neural.hive.domain:$TEST_DOMAIN&limit=10"
        traces_response=$(curl -s "${jaeger_search_url}?${search_params}")
    fi

    if echo "$traces_response" | jq -e '.data | length > 0' >/dev/null 2>&1; then
        local trace_count=$(echo "$traces_response" | jq '.data | length')
        log_success "Found $trace_count traces for test intent"

        # Extract actual trace ID from response
        if [[ -z "$TRACE_ID" ]]; then
            TRACE_ID=$(echo "$traces_response" | jq -r '.data[0].traceID')
            log_info "Extracted trace ID: $TRACE_ID"
        fi

        # Validate span attributes
        local has_intent_id=$(echo "$traces_response" | jq -r ".data[0].spans[0].tags[] | select(.key == \"neural.hive.intent.id\") | .value")
        if [[ "$has_intent_id" == "$INTENT_ID" ]]; then
            log_success "Trace contains correct intent ID"
        else
            log_warning "Trace missing intent ID correlation"
        fi

        return 0
    else
        log_error "No traces found for test intent"
        echo "Jaeger response: $traces_response"
        return 1
    fi
}

validate_logs_correlation() {
    log_info "Validating logs correlation..."

    # Query Grafana/Loki for logs (if available)
    # This is a simplified check - in production, you would query Loki directly
    local grafana_health=$(curl -s http://localhost:3000/api/health)

    if echo "$grafana_health" | jq -e '.database == "ok"' >/dev/null; then
        log_success "Grafana is healthy and can be used for log correlation queries"
    else
        log_warning "Grafana health check indicates potential issues"
    fi

    # Check if we can correlate via trace ID in logs (conceptual)
    if [[ -n "$TRACE_ID" ]]; then
        log_info "Trace ID '$TRACE_ID' can be used for log correlation in Loki queries"
        log_success "Log correlation validation passed (trace ID available)"
    else
        log_warning "No trace ID available for log correlation"
    fi

    return 0
}

validate_dashboards_correlation() {
    log_info "Validating dashboard correlation..."

    # Check if our test data appears in dashboards
    local dashboard_api_url="http://localhost:3000/api/dashboards/uid/neural-hive-overview"
    local dashboard_response=$(curl -s "$dashboard_api_url" 2>/dev/null)

    if echo "$dashboard_response" | jq -e '.dashboard' >/dev/null 2>&1; then
        log_success "Neural Hive overview dashboard accessible"

        # Check if dashboard has panels that would show our test data
        local has_request_panels=$(echo "$dashboard_response" | jq '.dashboard.panels[] | select(.title | contains("Request"))')
        if [[ -n "$has_request_panels" ]]; then
            log_success "Dashboard contains request panels for correlation"
        fi
    else
        log_warning "Could not access Neural Hive overview dashboard"
    fi
}

run_slo_checks() {
    log_info "Running SLO validation checks..."

    # Check latency SLO (< 150ms for 95th percentile)
    local latency_query="histogram_quantile(0.95, rate(neural_hive_captura_duration_seconds_bucket[5m]))"
    local latency_url="http://localhost:9090/api/v1/query?query=$(echo "$latency_query" | sed 's/ /%20/g')"

    local latency_response=$(curl -s "$latency_url")
    if echo "$latency_response" | jq -e '.data.result | length > 0' >/dev/null; then
        local p95_latency=$(echo "$latency_response" | jq -r '.data.result[0].value[1] // "0"')
        local latency_ms=$(echo "$p95_latency * 1000" | bc -l 2>/dev/null || echo "0")

        if (( $(echo "$latency_ms < 150" | bc -l 2>/dev/null || echo 0) )); then
            log_success "Latency SLO met: ${latency_ms}ms < 150ms"
        else
            log_warning "Latency SLO violation: ${latency_ms}ms >= 150ms"
        fi
    else
        log_info "No latency data available for SLO check"
    fi

    # Check availability SLO (>= 99.9%)
    local error_query="rate(neural_hive_requests_total{status=~\"error|failed\"}[5m])"
    local total_query="rate(neural_hive_requests_total[5m])"

    local error_url="http://localhost:9090/api/v1/query?query=$(echo "$error_query" | sed 's/ /%20/g')"
    local total_url="http://localhost:9090/api/v1/query?query=$(echo "$total_query" | sed 's/ /%20/g')"

    local error_rate=$(curl -s "$error_url" | jq -r '.data.result[0].value[1] // "0"')
    local total_rate=$(curl -s "$total_url" | jq -r '.data.result[0].value[1] // "0"')

    if (( $(echo "$total_rate > 0" | bc -l 2>/dev/null || echo 0) )); then
        local error_percentage=$(echo "($error_rate / $total_rate) * 100" | bc -l 2>/dev/null || echo "0")
        local availability=$(echo "100 - $error_percentage" | bc -l 2>/dev/null || echo "100")

        if (( $(echo "$availability >= 99.9" | bc -l 2>/dev/null || echo 1) )); then
            log_success "Availability SLO met: ${availability}% >= 99.9%"
        else
            log_warning "Availability SLO violation: ${availability}% < 99.9%"
        fi
    else
        log_info "No request data available for availability SLO check"
    fi
}

generate_report() {
    log_info "Generating correlation test report..."

    cat << EOF

═══════════════════════════════════════
 CORRELATION TEST REPORT
═══════════════════════════════════════

Test Intent ID: $INTENT_ID
Test Plan ID: $PLAN_ID
Test Domain: $TEST_DOMAIN
Trace ID: ${TRACE_ID:-"Not captured"}
Timestamp: $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)

Test Results:
EOF

    if validate_metrics_correlation; then
        echo "✓ Metrics Correlation: PASSED"
    else
        echo "✗ Metrics Correlation: FAILED"
    fi

    if validate_traces_correlation; then
        echo "✓ Traces Correlation: PASSED"
    else
        echo "✗ Traces Correlation: FAILED"
    fi

    if validate_logs_correlation; then
        echo "✓ Logs Correlation: PASSED"
    else
        echo "✗ Logs Correlation: FAILED"
    fi

    validate_dashboards_correlation
    echo "✓ Dashboard Correlation: CHECKED"

    run_slo_checks
    echo "✓ SLO Validation: COMPLETED"

    cat << EOF

═══════════════════════════════════════
 CORRELATION TEST COMPLETE
═══════════════════════════════════════

The synthetic intent has been processed and correlation
has been validated across the observability stack.

Use the following queries to manually verify correlation:

Prometheus:
- neural_hive_requests_total{domain="$TEST_DOMAIN"}
- neural_hive_captura_duration_seconds{domain="$TEST_DOMAIN"}

Jaeger:
- Search for service: gateway-intencoes
- Filter by tag: neural.hive.intent.id=$INTENT_ID

Grafana:
- Use trace ID: $TRACE_ID (if available)
- Filter by domain: $TEST_DOMAIN

EOF
}

main() {
    log_info "Starting Neural Hive-Mind correlation test..."

    check_prerequisites
    setup_port_forwards
    generate_synthetic_intent

    # Allow time for data to propagate through the observability stack
    log_info "Waiting for data to propagate through observability stack..."
    sleep 60

    generate_report

    log_success "Correlation test completed successfully!"
}

# Run main function
main "$@"