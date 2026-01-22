#!/bin/bash

# =============================================================================
# Neural Hive-Mind Infrastructure Health Validation Script
# =============================================================================
# Validates health of all critical infrastructure components:
# - Kafka topics and connectivity
# - ClickHouse schema and connectivity
# - OTEL Collector and Jaeger tracing pipeline
# - End-to-end integration health
#
# Usage:
#   ./validate-infrastructure-health.sh [options]
#
# Options:
#   --quick           Run quick checks only (skip detailed validation)
#   --kafka-only      Check only Kafka components
#   --clickhouse-only Check only ClickHouse components
#   --otel-only       Check only OTEL/Jaeger components
#   --json            Output results in JSON format
#   --help            Show this help message
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common functions (with fallback)
if [[ -f "${SCRIPT_DIR}/common-validation-functions.sh" ]]; then
    source "${SCRIPT_DIR}/common-validation-functions.sh"
else
    # Minimal fallback for standalone execution
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    NC='\033[0m'

    log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
    log_success() { echo -e "${GREEN}[PASS]${NC} $1"; }
    log_error() { echo -e "${RED}[FAIL]${NC} $1"; }
    log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fi

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_NAME="validate-infrastructure-health"
SCRIPT_VERSION="1.0.0"

# Namespaces
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
CLICKHOUSE_NAMESPACE="${CLICKHOUSE_NAMESPACE:-clickhouse}"
OBSERVABILITY_NAMESPACE="${OBSERVABILITY_NAMESPACE:-observability}"
APP_NAMESPACE="${APP_NAMESPACE:-neural-hive-mind}"

# Expected configurations
EXPECTED_KAFKA_TOPICS=(
    "intentions.business"
    "intentions.technical"
    "intentions.infrastructure"
    "intentions.security"
)

EXPECTED_CLICKHOUSE_TABLES=(
    "execution_logs"
    "telemetry_metrics"
    "worker_utilization"
    "queue_snapshots"
    "ml_model_performance"
    "scheduling_decisions"
)

EXPECTED_CLICKHOUSE_VIEWS=(
    "hourly_ticket_volume"
    "daily_worker_stats"
)

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Options
QUICK_MODE=false
KAFKA_ONLY=false
CLICKHOUSE_ONLY=false
OTEL_ONLY=false
JSON_OUTPUT=false

# Results storage for JSON output
declare -a RESULTS=()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

show_help() {
    cat << EOF
Neural Hive-Mind Infrastructure Health Validation

Usage: $0 [options]

Options:
    --quick             Run quick checks only (skip detailed validation)
    --kafka-only        Check only Kafka components
    --clickhouse-only   Check only ClickHouse components
    --otel-only         Check only OTEL/Jaeger components
    --json              Output results in JSON format
    --help              Show this help message

Examples:
    $0                      # Run all checks
    $0 --quick              # Run quick health check
    $0 --kafka-only         # Check only Kafka
    $0 --json               # Output as JSON

Environment Variables:
    KAFKA_NAMESPACE         Kafka namespace (default: neural-hive-kafka)
    CLICKHOUSE_NAMESPACE    ClickHouse namespace (default: clickhouse)
    OBSERVABILITY_NAMESPACE Observability namespace (default: observability)
    APP_NAMESPACE           Application namespace (default: neural-hive-mind)
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                QUICK_MODE=true
                shift
                ;;
            --kafka-only)
                KAFKA_ONLY=true
                shift
                ;;
            --clickhouse-only)
                CLICKHOUSE_ONLY=true
                shift
                ;;
            --otel-only)
                OTEL_ONLY=true
                shift
                ;;
            --json)
                JSON_OUTPUT=true
                shift
                ;;
            --help)
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

record_result() {
    local component="$1"
    local check_name="$2"
    local status="$3"
    local details="${4:-}"

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    case "$status" in
        "PASS")
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            if [[ "$JSON_OUTPUT" == "false" ]]; then
                log_success "$component: $check_name"
            fi
            ;;
        "FAIL")
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
            if [[ "$JSON_OUTPUT" == "false" ]]; then
                log_error "$component: $check_name - $details"
            fi
            ;;
        "WARN")
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
            if [[ "$JSON_OUTPUT" == "false" ]]; then
                log_warning "$component: $check_name - $details"
            fi
            ;;
    esac

    RESULTS+=("{\"component\":\"$component\",\"check\":\"$check_name\",\"status\":\"$status\",\"details\":\"$details\"}")
}

# =============================================================================
# KAFKA HEALTH CHECKS
# =============================================================================

check_kafka_health() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo ""
        echo "============================================================================"
        echo -e "${CYAN}KAFKA HEALTH CHECK${NC}"
        echo "============================================================================"
    fi

    # Check if Kafka pods are running
    local kafka_pods=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app.kubernetes.io/name=kafka --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [[ "$kafka_pods" -gt 0 ]]; then
        record_result "Kafka" "Broker pods running" "PASS" "$kafka_pods pods running"
    else
        record_result "Kafka" "Broker pods running" "FAIL" "No Kafka pods found running"
        return 1
    fi

    # Get Kafka pod name
    local kafka_pod=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$kafka_pod" ]]; then
        record_result "Kafka" "Pod discovery" "FAIL" "Could not find Kafka pod"
        return 1
    fi

    # Check broker connectivity
    local broker_check=$(kubectl exec -it "$kafka_pod" -n "$KAFKA_NAMESPACE" -- \
        kafka-broker-api-versions.sh --bootstrap-server localhost:9092 2>&1 | head -1 || echo "ERROR")

    if [[ "$broker_check" != *"ERROR"* ]] && [[ "$broker_check" != "" ]]; then
        record_result "Kafka" "Broker connectivity" "PASS"
    else
        record_result "Kafka" "Broker connectivity" "FAIL" "Cannot connect to broker"
    fi

    # Check topics existence
    local existing_topics=$(kubectl exec -it "$kafka_pod" -n "$KAFKA_NAMESPACE" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | tr -d '\r' || echo "")

    local missing_topics=()
    for topic in "${EXPECTED_KAFKA_TOPICS[@]}"; do
        if echo "$existing_topics" | grep -q "^${topic}$"; then
            record_result "Kafka" "Topic exists: $topic" "PASS"
        else
            record_result "Kafka" "Topic exists: $topic" "FAIL" "Topic not found"
            missing_topics+=("$topic")
        fi
    done

    # Check for incorrect topic naming (hyphen instead of dot)
    local incorrect_topics=$(echo "$existing_topics" | grep "^intentions-" || echo "")
    if [[ -n "$incorrect_topics" ]]; then
        record_result "Kafka" "Topic naming convention" "WARN" "Found topics with incorrect naming: $incorrect_topics"
    else
        record_result "Kafka" "Topic naming convention" "PASS"
    fi

    if [[ "$QUICK_MODE" == "false" ]]; then
        # Check consumer groups
        local consumer_groups=$(kubectl exec -it "$kafka_pod" -n "$KAFKA_NAMESPACE" -- \
            kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l || echo "0")

        if [[ "$consumer_groups" -gt 0 ]]; then
            record_result "Kafka" "Consumer groups active" "PASS" "$consumer_groups groups"
        else
            record_result "Kafka" "Consumer groups active" "WARN" "No consumer groups found"
        fi

        # Check for high consumer lag
        local high_lag=$(kubectl exec -it "$kafka_pod" -n "$KAFKA_NAMESPACE" -- \
            kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups 2>/dev/null | \
            awk 'NR>1 && $6 ~ /^[0-9]+$/ && $6 > 1000 {print $1":"$3":"$6}' | head -5 || echo "")

        if [[ -z "$high_lag" ]]; then
            record_result "Kafka" "Consumer lag" "PASS"
        else
            record_result "Kafka" "Consumer lag" "WARN" "High lag detected: $high_lag"
        fi

        # Check Schema Registry
        local schema_registry_pod=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app=schema-registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [[ -n "$schema_registry_pod" ]]; then
            local sr_status=$(kubectl get pod "$schema_registry_pod" -n "$KAFKA_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
            if [[ "$sr_status" == "Running" ]]; then
                record_result "Kafka" "Schema Registry" "PASS"
            else
                record_result "Kafka" "Schema Registry" "WARN" "Status: $sr_status"
            fi
        else
            record_result "Kafka" "Schema Registry" "WARN" "Not found"
        fi
    fi
}

# =============================================================================
# CLICKHOUSE HEALTH CHECKS
# =============================================================================

check_clickhouse_health() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo ""
        echo "============================================================================"
        echo -e "${CYAN}CLICKHOUSE HEALTH CHECK${NC}"
        echo "============================================================================"
    fi

    # Check if ClickHouse pods are running
    local ch_pod=$(kubectl get pods -n "$CLICKHOUSE_NAMESPACE" -l app.kubernetes.io/name=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                   kubectl get pods -n "$CLICKHOUSE_NAMESPACE" -l app=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$ch_pod" ]]; then
        # Try to find any clickhouse pod
        ch_pod=$(kubectl get pods -n "$CLICKHOUSE_NAMESPACE" --no-headers 2>/dev/null | grep -i clickhouse | awk '{print $1}' | head -1 || echo "")
    fi

    if [[ -z "$ch_pod" ]]; then
        record_result "ClickHouse" "Pod discovery" "FAIL" "No ClickHouse pod found"
        return 1
    fi

    local ch_status=$(kubectl get pod "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    if [[ "$ch_status" == "Running" ]]; then
        record_result "ClickHouse" "Pod status" "PASS"
    else
        record_result "ClickHouse" "Pod status" "FAIL" "Status: $ch_status"
        return 1
    fi

    # Check connectivity
    local conn_check=$(kubectl exec -it "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -- \
        clickhouse-client --query "SELECT 1" 2>&1 | tr -d '\r\n' || echo "ERROR")

    if [[ "$conn_check" == "1" ]]; then
        record_result "ClickHouse" "Connectivity" "PASS"
    else
        record_result "ClickHouse" "Connectivity" "FAIL" "Cannot execute query"
        return 1
    fi

    # Check database exists
    local db_exists=$(kubectl exec -it "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -- \
        clickhouse-client --query "SELECT count() FROM system.databases WHERE name = 'neural_hive'" 2>/dev/null | tr -d '\r\n' || echo "0")

    if [[ "$db_exists" == "1" ]]; then
        record_result "ClickHouse" "Database neural_hive" "PASS"
    else
        record_result "ClickHouse" "Database neural_hive" "FAIL" "Database does not exist"
        return 1
    fi

    # Check tables
    local existing_tables=$(kubectl exec -it "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -- \
        clickhouse-client --query "SELECT name FROM system.tables WHERE database = 'neural_hive' AND engine NOT LIKE '%View%'" 2>/dev/null | tr -d '\r' || echo "")

    local table_count=0
    for table in "${EXPECTED_CLICKHOUSE_TABLES[@]}"; do
        if echo "$existing_tables" | grep -q "^${table}$"; then
            record_result "ClickHouse" "Table exists: $table" "PASS"
            table_count=$((table_count + 1))
        else
            record_result "ClickHouse" "Table exists: $table" "FAIL" "Table not found"
        fi
    done

    # Summary of tables
    if [[ "$table_count" -eq "${#EXPECTED_CLICKHOUSE_TABLES[@]}" ]]; then
        record_result "ClickHouse" "Schema completeness" "PASS" "$table_count/${#EXPECTED_CLICKHOUSE_TABLES[@]} tables"
    else
        record_result "ClickHouse" "Schema completeness" "FAIL" "$table_count/${#EXPECTED_CLICKHOUSE_TABLES[@]} tables"
    fi

    if [[ "$QUICK_MODE" == "false" ]]; then
        # Check materialized views
        local existing_views=$(kubectl exec -it "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -- \
            clickhouse-client --query "SELECT name FROM system.tables WHERE database = 'neural_hive' AND engine LIKE '%View%'" 2>/dev/null | tr -d '\r' || echo "")

        local view_count=0
        for view in "${EXPECTED_CLICKHOUSE_VIEWS[@]}"; do
            if echo "$existing_views" | grep -q "^${view}$"; then
                record_result "ClickHouse" "View exists: $view" "PASS"
                view_count=$((view_count + 1))
            else
                record_result "ClickHouse" "View exists: $view" "WARN" "Materialized view not found"
            fi
        done

        # Check disk usage
        local disk_usage=$(kubectl exec -it "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -- \
            clickhouse-client --query "SELECT round(sum(bytes) / 1024 / 1024, 2) as size_mb FROM system.parts WHERE database = 'neural_hive'" 2>/dev/null | tr -d '\r\n' || echo "0")

        record_result "ClickHouse" "Data size" "PASS" "${disk_usage} MB"

        # Check for recent data
        local last_insert=$(kubectl exec -it "$ch_pod" -n "$CLICKHOUSE_NAMESPACE" -- \
            clickhouse-client --query "SELECT max(modification_time) FROM system.parts WHERE database = 'neural_hive'" 2>/dev/null | tr -d '\r\n' || echo "")

        if [[ -n "$last_insert" ]] && [[ "$last_insert" != "1970-01-01 00:00:00" ]]; then
            record_result "ClickHouse" "Recent data activity" "PASS" "Last: $last_insert"
        else
            record_result "ClickHouse" "Recent data activity" "WARN" "No recent data found"
        fi
    fi
}

# =============================================================================
# OTEL/JAEGER HEALTH CHECKS
# =============================================================================

check_otel_health() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo ""
        echo "============================================================================"
        echo -e "${CYAN}OTEL/JAEGER HEALTH CHECK${NC}"
        echo "============================================================================"
    fi

    # Check OTEL Collector
    local otel_pod=$(kubectl get pods -n "$OBSERVABILITY_NAMESPACE" -l app=opentelemetry-collector -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                     kubectl get pods -n "$OBSERVABILITY_NAMESPACE" -l app.kubernetes.io/name=opentelemetry-collector -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$otel_pod" ]]; then
        # Try broader search
        otel_pod=$(kubectl get pods -n "$OBSERVABILITY_NAMESPACE" --no-headers 2>/dev/null | grep -i otel | awk '{print $1}' | head -1 || echo "")
    fi

    if [[ -n "$otel_pod" ]]; then
        local otel_status=$(kubectl get pod "$otel_pod" -n "$OBSERVABILITY_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
        if [[ "$otel_status" == "Running" ]]; then
            record_result "OTEL" "Collector pod status" "PASS"
        else
            record_result "OTEL" "Collector pod status" "FAIL" "Status: $otel_status"
        fi

        # Check if metrics endpoint is accessible
        local metrics_check=$(kubectl exec -it "$otel_pod" -n "$OBSERVABILITY_NAMESPACE" -- \
            curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/metrics 2>/dev/null || echo "000")

        if [[ "$metrics_check" == "200" ]]; then
            record_result "OTEL" "Metrics endpoint" "PASS"
        else
            record_result "OTEL" "Metrics endpoint" "WARN" "HTTP $metrics_check"
        fi

        if [[ "$QUICK_MODE" == "false" ]]; then
            # Check span acceptance rate
            local accepted_spans=$(kubectl exec -it "$otel_pod" -n "$OBSERVABILITY_NAMESPACE" -- \
                curl -s http://localhost:8888/metrics 2>/dev/null | grep "otelcol_receiver_accepted_spans" | head -1 || echo "")

            local refused_spans=$(kubectl exec -it "$otel_pod" -n "$OBSERVABILITY_NAMESPACE" -- \
                curl -s http://localhost:8888/metrics 2>/dev/null | grep "otelcol_receiver_refused_spans" | head -1 || echo "")

            if [[ -n "$accepted_spans" ]]; then
                local accepted_count=$(echo "$accepted_spans" | awk '{print $NF}' | head -1 || echo "0")
                record_result "OTEL" "Spans accepted" "PASS" "$accepted_count total"
            fi

            if [[ -n "$refused_spans" ]]; then
                local refused_count=$(echo "$refused_spans" | awk '{print $NF}' | head -1 || echo "0")
                if [[ "$refused_count" != "0" ]] && [[ "$refused_count" -gt 100 ]]; then
                    record_result "OTEL" "Spans refused" "WARN" "$refused_count refused"
                else
                    record_result "OTEL" "Spans refused" "PASS" "$refused_count refused"
                fi
            fi
        fi
    else
        record_result "OTEL" "Collector pod" "FAIL" "Not found in namespace $OBSERVABILITY_NAMESPACE"
    fi

    # Check Jaeger
    local jaeger_pod=$(kubectl get pods -n "$OBSERVABILITY_NAMESPACE" -l app=jaeger -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                       kubectl get pods -n "$OBSERVABILITY_NAMESPACE" -l app.kubernetes.io/name=jaeger -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$jaeger_pod" ]]; then
        jaeger_pod=$(kubectl get pods -n "$OBSERVABILITY_NAMESPACE" --no-headers 2>/dev/null | grep -i jaeger | awk '{print $1}' | head -1 || echo "")
    fi

    if [[ -n "$jaeger_pod" ]]; then
        local jaeger_status=$(kubectl get pod "$jaeger_pod" -n "$OBSERVABILITY_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
        if [[ "$jaeger_status" == "Running" ]]; then
            record_result "Jaeger" "Pod status" "PASS"
        else
            record_result "Jaeger" "Pod status" "FAIL" "Status: $jaeger_status"
        fi

        if [[ "$QUICK_MODE" == "false" ]]; then
            # Check services count
            local services_response=$(kubectl exec -it "$jaeger_pod" -n "$OBSERVABILITY_NAMESPACE" -- \
                curl -s http://localhost:16686/api/services 2>/dev/null || echo "{}")

            local services_count=$(echo "$services_response" | jq -r '.data | length' 2>/dev/null || echo "0")

            if [[ "$services_count" -gt 0 ]]; then
                record_result "Jaeger" "Services reporting" "PASS" "$services_count services"
            else
                record_result "Jaeger" "Services reporting" "WARN" "No services found"
            fi
        fi
    else
        record_result "Jaeger" "Pod" "WARN" "Not found in namespace $OBSERVABILITY_NAMESPACE"
    fi
}

# =============================================================================
# INTEGRATION HEALTH CHECK
# =============================================================================

check_integration_health() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo ""
        echo "============================================================================"
        echo -e "${CYAN}END-TO-END INTEGRATION CHECK${NC}"
        echo "============================================================================"
    fi

    # Check if main application services are running
    local app_pods=$(kubectl get pods -n "$APP_NAMESPACE" --no-headers 2>/dev/null | grep -c "Running" || echo "0")

    if [[ "$app_pods" -gt 0 ]]; then
        record_result "Integration" "Application pods" "PASS" "$app_pods running"
    else
        record_result "Integration" "Application pods" "WARN" "No application pods found"
    fi

    # Check key services
    local key_services=("gateway-intencoes" "orchestrator-dynamic" "semantic-translation-engine")

    for service in "${key_services[@]}"; do
        local svc_pod=$(kubectl get pods -n "$APP_NAMESPACE" -l "app.kubernetes.io/name=$service" --no-headers 2>/dev/null | grep "Running" | head -1 || echo "")

        if [[ -n "$svc_pod" ]]; then
            record_result "Integration" "Service: $service" "PASS"
        else
            # Try alternative label
            svc_pod=$(kubectl get pods -n "$APP_NAMESPACE" -l "app=$service" --no-headers 2>/dev/null | grep "Running" | head -1 || echo "")
            if [[ -n "$svc_pod" ]]; then
                record_result "Integration" "Service: $service" "PASS"
            else
                record_result "Integration" "Service: $service" "WARN" "Not found or not running"
            fi
        fi
    done
}

# =============================================================================
# OUTPUT FUNCTIONS
# =============================================================================

print_summary() {
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        local health_percentage=0
        if [[ $TOTAL_CHECKS -gt 0 ]]; then
            health_percentage=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
        fi

        echo "{"
        echo "  \"summary\": {"
        echo "    \"total_checks\": $TOTAL_CHECKS,"
        echo "    \"passed\": $PASSED_CHECKS,"
        echo "    \"failed\": $FAILED_CHECKS,"
        echo "    \"warnings\": $WARNING_CHECKS,"
        echo "    \"health_percentage\": $health_percentage"
        echo "  },"
        echo "  \"results\": ["

        local first=true
        for result in "${RESULTS[@]}"; do
            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo ","
            fi
            echo -n "    $result"
        done

        echo ""
        echo "  ],"
        echo "  \"timestamp\": \"$(date -Iseconds)\""
        echo "}"
    else
        echo ""
        echo "============================================================================"
        echo -e "${CYAN}INFRASTRUCTURE HEALTH SUMMARY${NC}"
        echo "============================================================================"
        echo "Total Checks: $TOTAL_CHECKS"
        echo -e "Passed: ${GREEN}$PASSED_CHECKS${NC}"
        echo -e "Failed: ${RED}$FAILED_CHECKS${NC}"
        echo -e "Warnings: ${YELLOW}$WARNING_CHECKS${NC}"

        local health_percentage=0
        if [[ $TOTAL_CHECKS -gt 0 ]]; then
            health_percentage=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
        fi

        echo ""
        echo "Health Score: ${health_percentage}%"

        if [[ $health_percentage -ge 90 ]]; then
            echo -e "Overall Status: ${GREEN}EXCELLENT${NC}"
        elif [[ $health_percentage -ge 75 ]]; then
            echo -e "Overall Status: ${GREEN}GOOD${NC}"
        elif [[ $health_percentage -ge 50 ]]; then
            echo -e "Overall Status: ${YELLOW}FAIR${NC}"
        else
            echo -e "Overall Status: ${RED}POOR${NC}"
        fi

        echo "============================================================================"

        # Show recommendations if there are failures
        if [[ $FAILED_CHECKS -gt 0 ]]; then
            echo ""
            echo -e "${YELLOW}RECOMMENDATIONS:${NC}"
            echo "  1. Run individual validation scripts for detailed diagnostics:"
            echo "     - ./scripts/validation/validate-kafka-topics.sh"
            echo "  2. Check troubleshooting guide: docs/operations/troubleshooting-guide.md"
            echo "  3. Review Grafana dashboard: Neural Hive-Mind Diagnostic Dashboard"
        fi
    fi
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    parse_args "$@"

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo ""
        echo "============================================================================"
        echo " Neural Hive-Mind Infrastructure Health Validation"
        echo " Version: $SCRIPT_VERSION"
        echo " Timestamp: $(date)"
        echo "============================================================================"
    fi

    # Run checks based on options
    if [[ "$KAFKA_ONLY" == "true" ]]; then
        check_kafka_health
    elif [[ "$CLICKHOUSE_ONLY" == "true" ]]; then
        check_clickhouse_health
    elif [[ "$OTEL_ONLY" == "true" ]]; then
        check_otel_health
    else
        # Run all checks
        check_kafka_health || true
        check_clickhouse_health || true
        check_otel_health || true

        if [[ "$QUICK_MODE" == "false" ]]; then
            check_integration_health || true
        fi
    fi

    print_summary

    # Exit with appropriate code
    if [[ $FAILED_CHECKS -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main "$@"
