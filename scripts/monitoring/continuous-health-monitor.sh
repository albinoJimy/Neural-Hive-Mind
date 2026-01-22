#!/bin/bash

# =============================================================================
# Neural Hive-Mind Continuous Health Monitor
# =============================================================================
# Continuously monitors infrastructure health and sends alerts when issues
# are detected. Designed to run as a sidecar or standalone monitoring process.
#
# Usage:
#   ./continuous-health-monitor.sh [options]
#
# Options:
#   --interval <seconds>   Check interval (default: 60)
#   --webhook <url>        Slack/Teams webhook for alerts
#   --prometheus-push <url> Prometheus Pushgateway URL
#   --log-file <path>      Log file path (default: stdout)
#   --daemon               Run in daemon mode (background)
#   --once                 Run once and exit
#   --help                 Show this help message
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATION_SCRIPT="${SCRIPT_DIR}/../validation/validate-infrastructure-health.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_NAME="continuous-health-monitor"
SCRIPT_VERSION="1.0.0"

# Default settings
CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-}"
LOG_FILE="${LOG_FILE:-/dev/stdout}"
DAEMON_MODE=false
RUN_ONCE=false

# Alert thresholds
HEALTH_WARNING_THRESHOLD=75
HEALTH_CRITICAL_THRESHOLD=50

# State tracking
LAST_HEALTH_SCORE=100
CONSECUTIVE_FAILURES=0
MAX_CONSECUTIVE_FAILURES=3
ALERT_SENT=false

# Namespaces
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
CLICKHOUSE_NAMESPACE="${CLICKHOUSE_NAMESPACE:-clickhouse}"
OBSERVABILITY_NAMESPACE="${OBSERVABILITY_NAMESPACE:-observability}"
APP_NAMESPACE="${APP_NAMESPACE:-neural-hive-mind}"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

show_help() {
    cat << EOF
Neural Hive-Mind Continuous Health Monitor

Usage: $0 [options]

Options:
    --interval <seconds>      Check interval in seconds (default: 60)
    --webhook <url>           Slack/Teams webhook URL for alerts
    --prometheus-push <url>   Prometheus Pushgateway URL for metrics
    --log-file <path>         Log file path (default: stdout)
    --daemon                  Run in daemon mode (background)
    --once                    Run once and exit
    --help                    Show this help message

Environment Variables:
    CHECK_INTERVAL            Check interval in seconds
    ALERT_WEBHOOK             Webhook URL for alerts
    PROMETHEUS_PUSHGATEWAY    Pushgateway URL
    KAFKA_NAMESPACE           Kafka namespace (default: neural-hive-kafka)
    CLICKHOUSE_NAMESPACE      ClickHouse namespace (default: clickhouse)
    OBSERVABILITY_NAMESPACE   Observability namespace (default: observability)
    APP_NAMESPACE             Application namespace (default: neural-hive-mind)

Examples:
    $0 --interval 30                           # Check every 30 seconds
    $0 --webhook https://hooks.slack.com/...   # Send alerts to Slack
    $0 --daemon --log-file /var/log/health.log # Run as daemon
    $0 --once                                  # Single check and exit
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --interval)
                CHECK_INTERVAL="$2"
                shift 2
                ;;
            --webhook)
                ALERT_WEBHOOK="$2"
                shift 2
                ;;
            --prometheus-push)
                PROMETHEUS_PUSHGATEWAY="$2"
                shift 2
                ;;
            --log-file)
                LOG_FILE="$2"
                shift 2
                ;;
            --daemon)
                DAEMON_MODE=true
                shift
                ;;
            --once)
                RUN_ONCE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    local color=""
    case "$level" in
        "INFO") color="$CYAN" ;;
        "WARN") color="$YELLOW" ;;
        "ERROR") color="$RED" ;;
        "OK") color="$GREEN" ;;
    esac

    if [[ "$LOG_FILE" == "/dev/stdout" ]]; then
        echo -e "${color}[$timestamp] [$level]${NC} $message"
    else
        echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    fi
}

# =============================================================================
# HEALTH CHECK FUNCTIONS
# =============================================================================

run_quick_health_check() {
    local result
    local health_score=0
    local total_checks=0
    local passed_checks=0

    # Kafka quick check
    local kafka_ok=false
    local kafka_pod=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$kafka_pod" ]]; then
        local kafka_status=$(kubectl get pod "$kafka_pod" -n "$KAFKA_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
        if [[ "$kafka_status" == "Running" ]]; then
            kafka_ok=true
            passed_checks=$((passed_checks + 1))
        fi
    fi
    total_checks=$((total_checks + 1))

    # ClickHouse quick check
    local clickhouse_ok=false
    local ch_pod=$(kubectl get pods -n "$CLICKHOUSE_NAMESPACE" --no-headers 2>/dev/null | grep -i clickhouse | grep "Running" | head -1 || echo "")
    if [[ -n "$ch_pod" ]]; then
        clickhouse_ok=true
        passed_checks=$((passed_checks + 1))
    fi
    total_checks=$((total_checks + 1))

    # OTEL quick check
    local otel_ok=false
    local otel_pod=$(kubectl get pods -n "$OBSERVABILITY_NAMESPACE" --no-headers 2>/dev/null | grep -i otel | grep "Running" | head -1 || echo "")
    if [[ -n "$otel_pod" ]]; then
        otel_ok=true
        passed_checks=$((passed_checks + 1))
    fi
    total_checks=$((total_checks + 1))

    # Jaeger quick check
    local jaeger_ok=false
    local jaeger_pod=$(kubectl get pods -n "$OBSERVABILITY_NAMESPACE" --no-headers 2>/dev/null | grep -i jaeger | grep "Running" | head -1 || echo "")
    if [[ -n "$jaeger_pod" ]]; then
        jaeger_ok=true
        passed_checks=$((passed_checks + 1))
    fi
    total_checks=$((total_checks + 1))

    # Calculate health score
    if [[ $total_checks -gt 0 ]]; then
        health_score=$((passed_checks * 100 / total_checks))
    fi

    # Build result JSON
    echo "{
        \"timestamp\": \"$(date -Iseconds)\",
        \"health_score\": $health_score,
        \"total_checks\": $total_checks,
        \"passed_checks\": $passed_checks,
        \"components\": {
            \"kafka\": $kafka_ok,
            \"clickhouse\": $clickhouse_ok,
            \"otel\": $otel_ok,
            \"jaeger\": $jaeger_ok
        }
    }"
}

run_full_health_check() {
    if [[ -x "$VALIDATION_SCRIPT" ]]; then
        "$VALIDATION_SCRIPT" --json --quick 2>/dev/null
    else
        run_quick_health_check
    fi
}

# =============================================================================
# ALERTING FUNCTIONS
# =============================================================================

send_slack_alert() {
    local severity="$1"
    local message="$2"
    local health_score="$3"

    if [[ -z "$ALERT_WEBHOOK" ]]; then
        return 0
    fi

    local color=""
    local emoji=""
    case "$severity" in
        "critical")
            color="#dc3545"
            emoji=":rotating_light:"
            ;;
        "warning")
            color="#ffc107"
            emoji=":warning:"
            ;;
        "resolved")
            color="#28a745"
            emoji=":white_check_mark:"
            ;;
    esac

    local payload=$(cat <<EOF
{
    "attachments": [
        {
            "color": "$color",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "$emoji Neural Hive-Mind Infrastructure Alert",
                        "emoji": true
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*Severity:*\n${severity^}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Health Score:*\n${health_score}%"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Details:*\n$message"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Timestamp: $(date '+%Y-%m-%d %H:%M:%S UTC')"
                        }
                    ]
                }
            ]
        }
    ]
}
EOF
)

    curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$ALERT_WEBHOOK" > /dev/null 2>&1
    log "INFO" "Alert sent to webhook: $severity"
}

push_metrics_to_prometheus() {
    local health_score="$1"
    local kafka_ok="$2"
    local clickhouse_ok="$3"
    local otel_ok="$4"
    local jaeger_ok="$5"

    if [[ -z "$PROMETHEUS_PUSHGATEWAY" ]]; then
        return 0
    fi

    # Convert boolean to 0/1
    local kafka_metric=$([ "$kafka_ok" == "true" ] && echo "1" || echo "0")
    local clickhouse_metric=$([ "$clickhouse_ok" == "true" ] && echo "1" || echo "0")
    local otel_metric=$([ "$otel_ok" == "true" ] && echo "1" || echo "0")
    local jaeger_metric=$([ "$jaeger_ok" == "true" ] && echo "1" || echo "0")

    local metrics=$(cat <<EOF
# HELP neural_hive_infrastructure_health_score Overall infrastructure health score (0-100)
# TYPE neural_hive_infrastructure_health_score gauge
neural_hive_infrastructure_health_score $health_score

# HELP neural_hive_component_healthy Component health status (1=healthy, 0=unhealthy)
# TYPE neural_hive_component_healthy gauge
neural_hive_component_healthy{component="kafka"} $kafka_metric
neural_hive_component_healthy{component="clickhouse"} $clickhouse_metric
neural_hive_component_healthy{component="otel"} $otel_metric
neural_hive_component_healthy{component="jaeger"} $jaeger_metric

# HELP neural_hive_health_check_timestamp Timestamp of last health check
# TYPE neural_hive_health_check_timestamp gauge
neural_hive_health_check_timestamp $(date +%s)
EOF
)

    echo "$metrics" | curl -s --data-binary @- "$PROMETHEUS_PUSHGATEWAY/metrics/job/neural_hive_health_monitor" > /dev/null 2>&1
    log "INFO" "Metrics pushed to Prometheus Pushgateway"
}

# =============================================================================
# MAIN MONITORING LOOP
# =============================================================================

process_health_result() {
    local result="$1"

    # Parse result
    local health_score=$(echo "$result" | jq -r '.health_score // .summary.health_percentage // 0' 2>/dev/null || echo "0")
    local kafka_ok=$(echo "$result" | jq -r '.components.kafka // false' 2>/dev/null || echo "false")
    local clickhouse_ok=$(echo "$result" | jq -r '.components.clickhouse // false' 2>/dev/null || echo "false")
    local otel_ok=$(echo "$result" | jq -r '.components.otel // false' 2>/dev/null || echo "false")
    local jaeger_ok=$(echo "$result" | jq -r '.components.jaeger // false' 2>/dev/null || echo "false")

    # Log status
    if [[ "$health_score" -ge 90 ]]; then
        log "OK" "Health score: ${health_score}% - All systems operational"
    elif [[ "$health_score" -ge "$HEALTH_WARNING_THRESHOLD" ]]; then
        log "INFO" "Health score: ${health_score}% - Minor issues detected"
    elif [[ "$health_score" -ge "$HEALTH_CRITICAL_THRESHOLD" ]]; then
        log "WARN" "Health score: ${health_score}% - Degraded performance"
    else
        log "ERROR" "Health score: ${health_score}% - Critical issues detected"
    fi

    # Build component status message
    local failed_components=""
    [[ "$kafka_ok" != "true" ]] && failed_components="$failed_components Kafka"
    [[ "$clickhouse_ok" != "true" ]] && failed_components="$failed_components ClickHouse"
    [[ "$otel_ok" != "true" ]] && failed_components="$failed_components OTEL"
    [[ "$jaeger_ok" != "true" ]] && failed_components="$failed_components Jaeger"

    # Alert logic
    if [[ "$health_score" -lt "$HEALTH_CRITICAL_THRESHOLD" ]]; then
        CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))

        if [[ $CONSECUTIVE_FAILURES -ge $MAX_CONSECUTIVE_FAILURES ]] && [[ "$ALERT_SENT" != "true" ]]; then
            send_slack_alert "critical" "Critical infrastructure issues detected. Failed components:$failed_components" "$health_score"
            ALERT_SENT=true
        fi
    elif [[ "$health_score" -lt "$HEALTH_WARNING_THRESHOLD" ]]; then
        CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))

        if [[ $CONSECUTIVE_FAILURES -ge $MAX_CONSECUTIVE_FAILURES ]] && [[ "$ALERT_SENT" != "true" ]]; then
            send_slack_alert "warning" "Infrastructure degradation detected. Issues with:$failed_components" "$health_score"
            ALERT_SENT=true
        fi
    else
        # Health recovered
        if [[ "$ALERT_SENT" == "true" ]]; then
            send_slack_alert "resolved" "Infrastructure health restored. All components operational." "$health_score"
        fi
        CONSECUTIVE_FAILURES=0
        ALERT_SENT=false
    fi

    # Push metrics
    push_metrics_to_prometheus "$health_score" "$kafka_ok" "$clickhouse_ok" "$otel_ok" "$jaeger_ok"

    # Update state
    LAST_HEALTH_SCORE=$health_score
}

run_monitoring_loop() {
    log "INFO" "Starting Neural Hive-Mind Continuous Health Monitor v$SCRIPT_VERSION"
    log "INFO" "Check interval: ${CHECK_INTERVAL}s"
    [[ -n "$ALERT_WEBHOOK" ]] && log "INFO" "Alerts enabled via webhook"
    [[ -n "$PROMETHEUS_PUSHGATEWAY" ]] && log "INFO" "Metrics push enabled to $PROMETHEUS_PUSHGATEWAY"

    while true; do
        log "INFO" "Running health check..."

        local result
        result=$(run_quick_health_check)

        if [[ -n "$result" ]]; then
            process_health_result "$result"
        else
            log "ERROR" "Failed to run health check"
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
        fi

        if [[ "$RUN_ONCE" == "true" ]]; then
            log "INFO" "Single run mode - exiting"
            break
        fi

        sleep "$CHECK_INTERVAL"
    done
}

# =============================================================================
# SIGNAL HANDLERS
# =============================================================================

cleanup() {
    log "INFO" "Shutting down health monitor..."
    exit 0
}

trap cleanup SIGTERM SIGINT

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    parse_args "$@"

    # Create log directory if needed
    if [[ "$LOG_FILE" != "/dev/stdout" ]]; then
        local log_dir=$(dirname "$LOG_FILE")
        mkdir -p "$log_dir"
    fi

    # Run in daemon mode if requested
    if [[ "$DAEMON_MODE" == "true" ]]; then
        log "INFO" "Starting in daemon mode..."
        run_monitoring_loop &
        echo $! > /tmp/neural-hive-health-monitor.pid
        log "INFO" "Daemon started with PID $(cat /tmp/neural-hive-health-monitor.pid)"
    else
        run_monitoring_loop
    fi
}

main "$@"
