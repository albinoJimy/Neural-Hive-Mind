#!/bin/bash
# Neural Hive-Mind Test Helper Library
# This library provides shared functions for test scripts
# Source this file - do not execute directly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/common.sh"
source "${SCRIPT_DIR}/../lib/k8s.sh"
source "${SCRIPT_DIR}/../lib/docker.sh"
source "${SCRIPT_DIR}/../lib/aws.sh"

# Global variables for test reporting
declare -g TEST_REPORT_JSON=""
declare -g TEST_START_TIME=""
declare -a PORT_FORWARDS=()

# Status check function
check_status() {
    local exit_code=$1
    local message=$2
    if [ $exit_code -eq 0 ]; then
        log_success "$message"
        return 0
    else
        log_error "$message"
        return 1
    fi
}

# Command existence check
detect_namespace() {
    local service=$1
    local ns
    ns=$(k8s_detect_namespace "${service}")
    echo "${ns:-$service}"
}

get_pod_name() {
    k8s_get_pod_name "$@"
}

get_pod_logs() {
    k8s_get_pod_logs "$@"
}

wait_for_pod_ready() {
    k8s_wait_for_pod_ready "$@"
}

exec_in_pod() {
    k8s_exec_in_pod "$@"
}

port_forward_with_retry() {
    local namespace=$1
    local service=$2
    local local_port=$3
    local remote_port=$4
    local max_retries=${5:-3}

    local pid
    if pid=$(k8s_port_forward "${namespace}" "svc/${service}" "${local_port}" "${remote_port}" "${max_retries}"); then
        PORT_FORWARDS+=("${pid}")
        echo "${pid}"
        return 0
    fi

    log_error "Failed to establish port-forward after ${max_retries} attempts"
    return 1
}

cleanup_port_forwards() {
    k8s_cleanup_port_forwards
    PORT_FORWARDS=()
}

# Kafka helper functions
kafka_publish_message() {
    local namespace=$1
    local topic=$2
    local message=$3
    local bootstrap_server=${4:-"neural-hive-kafka-bootstrap:9092"}
    local max_retries=${5:-3}

    local pod_name="kafka-producer-test-$$"

    for attempt in $(seq 1 $max_retries); do
        log_debug "Kafka publish attempt $attempt/$max_retries"

        kubectl run "$pod_name" --restart='Never' \
            --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
            --namespace "$namespace" \
            --command -- sh -c "echo '$message' | \
                kafka-console-producer.sh \
                --bootstrap-server $bootstrap_server \
                --topic $topic \
                --request-required-acks 1 \
                --request-timeout-ms 10000" 2>/dev/null

        # Aguardar conclusão do pod
        local timeout=30
        local elapsed=0
        while [ $elapsed -lt $timeout ]; do
            local phase
            phase=$(kubectl get pod "$pod_name" -n "$namespace" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
            if [ "$phase" = "Succeeded" ] || [ "$phase" = "Failed" ]; then
                break
            fi
            sleep 1
            elapsed=$((elapsed + 1))
        done

        local logs
        logs=$(kubectl logs "$pod_name" -n "$namespace" 2>/dev/null || echo "")

        # Verificar por erros nos logs
        if echo "$logs" | grep -qi "error\|exception\|failed"; then
            log_debug "Kafka publish attempt $attempt failed with errors in logs"
            kubectl delete pod "$pod_name" -n "$namespace" --force --grace-period=0 &>/dev/null || true
            [ $attempt -lt $max_retries ] && sleep $((attempt * 2))
            continue
        fi

        # Verificar status do pod
        local phase
        phase=$(kubectl get pod "$pod_name" -n "$namespace" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Failed")

        kubectl delete pod "$pod_name" -n "$namespace" --force --grace-period=0 &>/dev/null || true

        if [ "$phase" = "Succeeded" ]; then
            log_debug "Kafka publish succeeded on attempt $attempt"
            return 0
        fi

        log_debug "Kafka publish attempt $attempt failed (phase: $phase)"
        [ $attempt -lt $max_retries ] && sleep $((attempt * 2))
    done

    log_error "Kafka publish failed after $max_retries attempts"
    return 1
}

kafka_check_topic_exists() {
    local namespace=$1
    local topic=$2
    local kafka_pod=$3

    kubectl exec -n "$namespace" "$kafka_pod" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "^${topic}$"
}

# MongoDB helper functions
mongo_query() {
    local namespace=$1
    local pod_name=$2
    local database=$3
    local query=$4

    kubectl exec -n "$namespace" "$pod_name" -- \
        mongosh --quiet --eval "use $database; $query" 2>/dev/null
}

mongo_count_documents() {
    local namespace=$1
    local pod_name=$2
    local database=$3
    local collection=$4
    local filter=${5:-"{}"}

    mongo_query "$namespace" "$pod_name" "$database" \
        "db.${collection}.countDocuments(${filter})"
}

mongo_check_connection() {
    local namespace=$1
    local pod_name=$2

    kubectl exec -n "$namespace" "$pod_name" -- \
        mongosh --quiet --eval "db.adminCommand('ping')" &>/dev/null
}

# Redis helper functions
redis_get() {
    local namespace=$1
    local pod_name=$2
    local key=$3

    kubectl exec -n "$namespace" "$pod_name" -- \
        redis-cli GET "$key" 2>/dev/null
}

redis_keys() {
    local namespace=$1
    local pod_name=$2
    local pattern=$3

    kubectl exec -n "$namespace" "$pod_name" -- \
        redis-cli KEYS "$pattern" 2>/dev/null
}

redis_check_connection() {
    local namespace=$1
    local pod_name=$2

    kubectl exec -n "$namespace" "$pod_name" -- \
        redis-cli PING 2>/dev/null | grep -q "PONG"
}

# Prometheus helper functions
prometheus_query() {
    local query=$1
    local prometheus_url=${2:-"http://localhost:9090"}

    curl -s "${prometheus_url}/api/v1/query?query=$(echo "$query" | jq -sRr @uri)" 2>/dev/null | jq -r '.data.result'
}

prometheus_query_range() {
    local query=$1
    local start_ts=$2
    local end_ts=$3
    local step=${4:-"15s"}
    local prometheus_url=${5:-"http://localhost:9090"}

    local result
    result=$(curl -s "${prometheus_url}/api/v1/query_range?query=$(echo "$query" | jq -sRr @uri)&start=${start_ts}&end=${end_ts}&step=${step}" 2>/dev/null | jq -r '.data.result')

    if [ "${STRICT:-false}" = "true" ] && [ "$(echo "$result" | jq 'length')" -eq 0 ]; then
        log_debug "prometheus_query_range returned empty result for query: $query"
        return 1
    fi

    echo "$result"
    return 0
}

prometheus_check_metric_exists() {
    local metric=$1
    local prometheus_url=${2:-"http://localhost:9090"}

    local result
    result=$(prometheus_query "$metric" "$prometheus_url")
    [ "$(echo "$result" | jq 'length')" -gt 0 ]
}

# Jaeger helper functions
jaeger_check_connection() {
    local jaeger_url=${1:-"http://localhost:16686"}

    local status_code
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "${jaeger_url}/api/services" 2>/dev/null || echo "000")

    if [ "$status_code" = "200" ]; then
        return 0
    else
        log_debug "Jaeger connection check failed: HTTP $status_code"
        return 1
    fi
}

jaeger_get_trace() {
    local trace_id=$1
    local jaeger_url=${2:-"http://localhost:16686"}

    local result
    result=$(curl -s "${jaeger_url}/api/traces/${trace_id}" 2>/dev/null | jq -r '.data[0]')

    if [ "$result" = "null" ] || [ -z "$result" ]; then
        log_debug "Trace $trace_id not found in Jaeger"
        return 1
    fi

    echo "$result"
    return 0
}

jaeger_search_traces() {
    local service=$1
    local tag=$2
    local jaeger_url=${3:-"http://localhost:16686"}

    curl -s "${jaeger_url}/api/traces?service=${service}&tag=${tag}" 2>/dev/null | jq -r '.data'
}

# Test report functions
init_test_report() {
    TEST_START_TIME=$(date +%s)
    TEST_REPORT_JSON='{"test_name":"","start_time":"","results":[]}'
    TEST_REPORT_JSON=$(echo "$TEST_REPORT_JSON" | jq --arg name "$1" '.test_name = $name')
    TEST_REPORT_JSON=$(echo "$TEST_REPORT_JSON" | jq --arg time "$(date -Iseconds)" '.start_time = $time')
}

add_test_result() {
    local section=$1
    local status=$2
    local message=$3
    local details=${4:-""}

    local result
    result=$(jq -n \
        --arg section "$section" \
        --arg status "$status" \
        --arg message "$message" \
        --arg details "$details" \
        '{section: $section, status: $status, message: $message, details: $details, timestamp: now|todate}')

    TEST_REPORT_JSON=$(echo "$TEST_REPORT_JSON" | jq ".results += [$result]")
}

generate_json_report() {
    local duration=$(($(date +%s) - TEST_START_TIME))
    TEST_REPORT_JSON=$(echo "$TEST_REPORT_JSON" | jq --arg dur "$duration" '.duration_seconds = ($dur | tonumber)')
    TEST_REPORT_JSON=$(echo "$TEST_REPORT_JSON" | jq --arg time "$(date -Iseconds)" '.end_time = $time')

    local passed
    local failed
    passed=$(echo "$TEST_REPORT_JSON" | jq '[.results[] | select(.status == "passed")] | length')
    failed=$(echo "$TEST_REPORT_JSON" | jq '[.results[] | select(.status == "failed")] | length')

    TEST_REPORT_JSON=$(echo "$TEST_REPORT_JSON" | jq --arg p "$passed" --arg f "$failed" \
        '.summary = {total: (.results | length), passed: ($p | tonumber), failed: ($f | tonumber)}')

    echo "$TEST_REPORT_JSON"
}

save_test_report() {
    local output_file=$1
    generate_json_report > "$output_file"
    log_info "Test report saved to: $output_file"
}

# Utility functions
timestamp() {
    date -Iseconds
}

duration() {
    local start=$1
    local end=$2
    echo $((end - start))
}

retry() {
    local max_attempts=$1
    shift
    local command=("$@")

    for i in $(seq 1 "$max_attempts"); do
        if "${command[@]}"; then
            return 0
        fi
        [ "$i" -lt "$max_attempts" ] && sleep $((i * 2))
    done

    return 1
}

timeout_command() {
    local timeout_seconds=$1
    shift

    # Check if timeout command exists
    if command -v timeout &> /dev/null; then
        timeout "$timeout_seconds" "$@"
        return $?
    else
        # Fallback: manual timeout using background process
        log_debug "timeout command not available, using manual timeout"
        "$@" &
        local pid=$!
        local elapsed=0

        while kill -0 $pid 2>/dev/null && [ $elapsed -lt $timeout_seconds ]; do
            sleep 1
            elapsed=$((elapsed + 1))
        done

        if kill -0 $pid 2>/dev/null; then
            log_debug "Command timed out after ${timeout_seconds}s, killing PID $pid"
            kill -TERM $pid 2>/dev/null
            sleep 1
            kill -KILL $pid 2>/dev/null || true
            return 124  # timeout exit code
        fi

        wait $pid
        return $?
    fi
}

generate_markdown_summary() {
    local output_path=$1

    if [ -z "$TEST_REPORT_JSON" ]; then
        log_error "No test report data available"
        return 1
    fi

    {
        echo "# Phase 1 End-to-End Test Summary"
        echo ""
        echo "**Test Date:** $(date -Iseconds)"
        echo "**Test Name:** $(echo "$TEST_REPORT_JSON" | jq -r '.test_name')"

        # Extract IDs if available
        if [ -n "${TEST_INTENT_ID:-}" ]; then
            echo "**Intent ID:** ${TEST_INTENT_ID}"
        fi
        if [ -n "${TEST_PLAN_ID:-}" ]; then
            echo "**Plan ID:** ${TEST_PLAN_ID}"
        fi
        if [ -n "${TEST_DECISION_ID:-}" ]; then
            echo "**Decision ID:** ${TEST_DECISION_ID}"
        fi

        echo ""
        echo "## Test Results"
        echo ""

        # List all results
        echo "$TEST_REPORT_JSON" | jq -r '.results[] | "- [\(.status | ascii_upcase)] \(.section): \(.message)"'

        echo ""
        echo "## Summary"
        echo ""

        # Summary stats
        local total passed failed duration_sec
        total=$(echo "$TEST_REPORT_JSON" | jq -r '.summary.total // 0')
        passed=$(echo "$TEST_REPORT_JSON" | jq -r '.summary.passed // 0')
        failed=$(echo "$TEST_REPORT_JSON" | jq -r '.summary.failed // 0')
        duration_sec=$(echo "$TEST_REPORT_JSON" | jq -r '.duration_seconds // 0')

        echo "- **Total Tests:** $total"
        echo "- **Passed:** $passed"
        echo "- **Failed:** $failed"
        echo "- **Duration:** ${duration_sec}s"

        if [ "$failed" -eq 0 ]; then
            echo ""
            echo "✅ **All tests passed!**"
        else
            echo ""
            echo "❌ **Some tests failed. Please review the results above.**"
        fi
    } > "$output_path"

    log_debug "Markdown summary generated: $output_path"
    return 0
}

# Cleanup function
cleanup_on_exit() {
    log_debug "Cleanup on exit triggered"
    cleanup_port_forwards
}

# Set up trap for cleanup
trap cleanup_on_exit EXIT INT TERM

log_debug "Test helper library loaded"
