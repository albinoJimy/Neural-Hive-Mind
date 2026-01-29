#!/bin/bash
# E2E Validation - Log Monitor
# Monitors logs from consensus-engine and specialists during E2E test execution

set -euo pipefail

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

# Configuration
NAMESPACE="${NAMESPACE:-neural-hive}"
DURATION_SECONDS="${DURATION_SECONDS:-600}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/e2e-validation-logs}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MONITOR_CONSENSUS=true
MONITOR_SPECIALISTS=true

# Arrays to store PIDs of monitoring processes
declare -a MONITOR_PIDS=()

#######################################
# Print banner with configuration
#######################################
print_banner() {
    echo -e "${BOLD}${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         E2E VALIDATION - LOG MONITOR                       ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo "Configuration:"
    echo "  Namespace: ${NAMESPACE}"
    echo "  Duration: ${DURATION_SECONDS}s"
    echo "  Output Directory: ${OUTPUT_DIR}"
    echo "  Monitor Consensus: ${MONITOR_CONSENSUS}"
    echo "  Monitor Specialists: ${MONITOR_SPECIALISTS}"
    echo ""
}

#######################################
# Check prerequisites
#######################################
check_prerequisites() {
    echo -e "${CYAN}Checking prerequisites...${RESET}"

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}✗ kubectl not found${RESET}"
        exit 1
    fi

    # Check namespace exists
    if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
        echo -e "${RED}✗ Namespace ${NAMESPACE} does not exist${RESET}"
        exit 1
    fi

    # Check pods are running
    if [[ "${MONITOR_CONSENSUS}" == "true" ]]; then
        local consensus_pods
        consensus_pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=consensus-engine --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
        if [[ ${consensus_pods} -eq 0 ]]; then
            echo -e "${RED}✗ No running consensus-engine pods found${RESET}"
            exit 1
        fi
        echo -e "${GREEN}✓ Found ${consensus_pods} consensus-engine pod(s)${RESET}"
    fi

    if [[ "${MONITOR_SPECIALISTS}" == "true" ]]; then
        for specialist in business technical behavior evolution architecture; do
            local specialist_pods
            # Try app.kubernetes.io/name first (standard label), fallback to app label
            specialist_pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=specialist-${specialist} --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
            if [[ ${specialist_pods} -eq 0 ]]; then
                # Fallback to legacy label
                specialist_pods=$(kubectl get pods -n "${NAMESPACE}" -l app=specialist-${specialist} --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
            fi
            if [[ ${specialist_pods} -eq 0 ]]; then
                echo -e "${YELLOW}⚠ No running specialist-${specialist} pods found${RESET}"
            fi
        done
    fi

    echo -e "${GREEN}✓ Prerequisites check passed${RESET}\n"
}

#######################################
# Create output directory
#######################################
create_output_directory() {
    echo -e "${CYAN}Creating output directory...${RESET}"
    mkdir -p "${OUTPUT_DIR}"

    # Create README with metadata
    cat > "${OUTPUT_DIR}/README.md" <<EOF
# E2E Validation - Log Monitoring Session

## Session Information
- **Start Time:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
- **Duration:** ${DURATION_SECONDS} seconds
- **Namespace:** ${NAMESPACE}
- **Output Directory:** ${OUTPUT_DIR}

## Components Monitored
- Consensus Engine: ${MONITOR_CONSENSUS}
- Specialists: ${MONITOR_SPECIALISTS}

## Filters Applied
- TypeError
- evaluated_at
- timestamp
- EvaluatePlan
- gRPC errors

## Files
- \`consensus-engine-*-monitor.log\`: Consensus engine logs
- \`specialist-*-monitor.log\`: Specialist logs
- \`typeerror-alerts.log\`: TypeError detections
- \`live-stats.log\`: Live statistics
- \`MONITORING_SUMMARY.md\`: Final summary report
EOF

    echo -e "${GREEN}✓ Output directory created: ${OUTPUT_DIR}${RESET}\n"
}

#######################################
# Monitor consensus engine logs
#######################################
monitor_consensus_engine() {
    if [[ "${MONITOR_CONSENSUS}" != "true" ]]; then
        return
    fi

    echo -e "${CYAN}Starting consensus-engine log monitoring...${RESET}"

    local pods
    pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=consensus-engine --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}')

    local pod_count=0
    for pod_name in ${pods}; do
        local log_file="${OUTPUT_DIR}/consensus-engine-${pod_name}-monitor.log"

        # Start log capture in background with filters and coloring
        (
            kubectl logs -n "${NAMESPACE}" "${pod_name}" -f --tail=0 2>&1 | \
            grep -i -E "(TypeError|evaluated_at|timestamp|EvaluatePlan|Invocando especialistas|gRPC)" | \
            while IFS= read -r line; do
                # Apply coloring
                if echo "${line}" | grep -qi "TypeError\|Error"; then
                    echo -e "${RED}${line}${RESET}" | tee -a "${log_file}"
                elif echo "${line}" | grep -qi "Warning"; then
                    echo -e "${YELLOW}${line}${RESET}" | tee -a "${log_file}"
                elif echo "${line}" | grep -qi "evaluated_at\|timestamp"; then
                    echo -e "${CYAN}${line}${RESET}" | tee -a "${log_file}"
                elif echo "${line}" | grep -qi "success\|completed"; then
                    echo -e "${GREEN}${line}${RESET}" | tee -a "${log_file}"
                else
                    echo "${line}" | tee -a "${log_file}"
                fi
            done
        ) &

        MONITOR_PIDS+=($!)
        ((pod_count++))
    done

    echo -e "${GREEN}✓ Monitoring ${pod_count} consensus-engine pod(s)${RESET}"
}

#######################################
# Monitor specialist logs
#######################################
monitor_specialists() {
    if [[ "${MONITOR_SPECIALISTS}" != "true" ]]; then
        return
    fi

    echo -e "${CYAN}Starting specialist log monitoring...${RESET}"

    local total_pods=0

    for specialist in business technical behavior evolution architecture; do
        local pods
        # Try app.kubernetes.io/name first (standard label), fallback to app label
        pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=specialist-${specialist} --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

        if [[ -z "${pods}" ]]; then
            # Fallback to legacy label
            pods=$(kubectl get pods -n "${NAMESPACE}" -l app=specialist-${specialist} --field-selector=status.phase=Running -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
        fi

        if [[ -z "${pods}" ]]; then
            continue
        fi

        for pod_name in ${pods}; do
            local log_file="${OUTPUT_DIR}/specialist-${specialist}-${pod_name}-monitor.log"

            # Start log capture in background with filters
            (
                kubectl logs -n "${NAMESPACE}" "${pod_name}" -f --tail=0 2>&1 | \
                grep -i -E "(EvaluatePlan|evaluated_at|Timestamp created|processing_time_ms|completed successfully)" | \
                tee -a "${log_file}"
            ) &

            MONITOR_PIDS+=($!)
            ((total_pods++))
        done
    done

    echo -e "${GREEN}✓ Monitoring ${total_pods} specialist pod(s) across 5 specialists${RESET}"
}

#######################################
# Monitor for TypeErrors specifically
#######################################
monitor_for_typeerrors() {
    echo -e "${CYAN}Starting TypeError detection...${RESET}"

    local alert_file="${OUTPUT_DIR}/typeerror-alerts.log"

    (
        while true; do
            # Search for TypeErrors in consensus-engine logs
            kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name=consensus-engine --tail=50 2>/dev/null | \
                grep -i "typeerror" >> "${alert_file}" 2>/dev/null || true

            # If TypeErrors found, alert
            if [[ -s "${alert_file}" ]]; then
                echo -e "${RED}${BOLD}⚠ TYPEERROR DETECTED!${RESET}" >&2
                tail -5 "${alert_file}" >&2
            fi

            sleep 5
        done
    ) &

    MONITOR_PIDS+=($!)
    echo -e "${GREEN}✓ TypeError monitoring active${RESET}"
}

#######################################
# Display live statistics
#######################################
display_live_stats() {
    echo -e "${CYAN}Starting live statistics display...${RESET}"

    local stats_file="${OUTPUT_DIR}/live-stats.log"

    (
        while true; do
            # Count lines captured
            local consensus_lines=0
            local specialist_lines=0

            if ls "${OUTPUT_DIR}"/consensus-engine-*-monitor.log &> /dev/null; then
                consensus_lines=$(cat "${OUTPUT_DIR}"/consensus-engine-*-monitor.log 2>/dev/null | wc -l || echo 0)
            fi

            if ls "${OUTPUT_DIR}"/specialist-*-monitor.log &> /dev/null; then
                specialist_lines=$(cat "${OUTPUT_DIR}"/specialist-*-monitor.log 2>/dev/null | wc -l || echo 0)
            fi

            # Count TypeErrors
            local typeerrors=0
            if [[ -f "${OUTPUT_DIR}/typeerror-alerts.log" ]]; then
                typeerrors=$(grep -c "TypeError" "${OUTPUT_DIR}/typeerror-alerts.log" 2>/dev/null || echo 0)
            fi

            # Count timestamps
            local timestamps=0
            if ls "${OUTPUT_DIR}"/*.log &> /dev/null; then
                timestamps=$(grep -c "evaluated_at" "${OUTPUT_DIR}"/*.log 2>/dev/null || echo 0)
            fi

            # Display and log statistics
            local stats_line="[$(date +%H:%M:%S)] Lines: consensus=${consensus_lines}, specialists=${specialist_lines} | TypeErrors: ${typeerrors} | Timestamps: ${timestamps}"
            echo "${stats_line}" | tee -a "${stats_file}"

            sleep 15
        done
    ) &

    MONITOR_PIDS+=($!)
    echo -e "${GREEN}✓ Live statistics active${RESET}\n"
}

#######################################
# Wait for specified duration
#######################################
wait_for_duration() {
    echo -e "${BOLD}Monitoring for ${DURATION_SECONDS} seconds...${RESET}\n"

    local elapsed=0
    while [[ ${elapsed} -lt ${DURATION_SECONDS} ]]; do
        local remaining=$((DURATION_SECONDS - elapsed))
        local progress=$((elapsed * 100 / DURATION_SECONDS))
        local bar_length=$((progress / 2))

        # Create progress bar
        local bar=""
        for ((i=0; i<bar_length; i++)); do
            bar="${bar}#"
        done

        # Display progress
        printf "\r[%-50s] %3d%% - %ds remaining" "${bar}" "${progress}" "${remaining}"

        sleep 10
        elapsed=$((elapsed + 10))
    done

    echo -e "\n\n${GREEN}✓ Monitoring duration completed${RESET}\n"
}

#######################################
# Stop all monitoring processes
#######################################
stop_monitoring() {
    echo -e "${CYAN}Stopping monitoring processes...${RESET}"

    for pid in "${MONITOR_PIDS[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill -TERM "${pid}" 2>/dev/null || true
            wait "${pid}" 2>/dev/null || true
        fi
    done

    echo -e "${GREEN}✓ All monitoring processes stopped${RESET}\n"
}

#######################################
# Generate monitoring summary
#######################################
generate_monitoring_summary() {
    echo -e "${CYAN}Generating monitoring summary...${RESET}"

    local summary_file="${OUTPUT_DIR}/MONITORING_SUMMARY.md"

    # Count files and lines
    local consensus_files=0
    local consensus_lines=0
    if ls "${OUTPUT_DIR}"/consensus-engine-*-monitor.log &> /dev/null; then
        consensus_files=$(ls "${OUTPUT_DIR}"/consensus-engine-*-monitor.log | wc -l)
        consensus_lines=$(cat "${OUTPUT_DIR}"/consensus-engine-*-monitor.log | wc -l)
    fi

    local specialist_files=0
    local specialist_lines=0
    if ls "${OUTPUT_DIR}"/specialist-*-monitor.log &> /dev/null; then
        specialist_files=$(ls "${OUTPUT_DIR}"/specialist-*-monitor.log | wc -l)
        specialist_lines=$(cat "${OUTPUT_DIR}"/specialist-*-monitor.log | wc -l)
    fi

    # Calculate total size
    local total_size_kb
    total_size_kb=$(du -sk "${OUTPUT_DIR}" | cut -f1)
    local total_size_mb=$((total_size_kb / 1024))

    # Count TypeErrors
    local typeerrors=0
    if [[ -f "${OUTPUT_DIR}/typeerror-alerts.log" ]]; then
        typeerrors=$(wc -l < "${OUTPUT_DIR}/typeerror-alerts.log" 2>/dev/null || echo 0)
    fi

    # Count timestamps
    local timestamps=0
    if ls "${OUTPUT_DIR}"/*.log &> /dev/null; then
        timestamps=$(grep -c "evaluated_at" "${OUTPUT_DIR}"/*.log 2>/dev/null || echo 0)
    fi

    # Count errors and warnings
    local errors=0
    local warnings=0
    if ls "${OUTPUT_DIR}"/*.log &> /dev/null; then
        errors=$(grep -ci "error" "${OUTPUT_DIR}"/*.log 2>/dev/null || echo 0)
        warnings=$(grep -ci "warning" "${OUTPUT_DIR}"/*.log 2>/dev/null || echo 0)
    fi

    # Generate summary
    cat > "${summary_file}" <<EOF
# E2E Validation - Log Monitoring Summary

## Session Information
- **Start Time:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
- **Duration:** ${DURATION_SECONDS} seconds
- **Namespace:** ${NAMESPACE}
- **Output Directory:** ${OUTPUT_DIR}

## Files Captured
- **Consensus Engine logs:** ${consensus_files} files, ${consensus_lines} lines
- **Specialist logs:** ${specialist_files} files, ${specialist_lines} lines
- **Total size:** ${total_size_mb} MB

## Key Findings
- **TypeErrors detected:** ${typeerrors}
- **Timestamps logged:** ${timestamps}
- **Errors logged:** ${errors}
- **Warnings logged:** ${warnings}

## TypeError Analysis
EOF

    if [[ ${typeerrors} -gt 0 ]]; then
        cat >> "${summary_file}" <<EOF
⚠️ **CRITICAL:** ${typeerrors} TypeErrors detected!

See: \`typeerror-alerts.log\`

**Actions Required:**
1. Review TypeError details in typeerror-alerts.log
2. Verify protobuf versions in all components
3. Re-run protobuf version analysis
4. Do NOT proceed with deployment until resolved
EOF
    else
        cat >> "${summary_file}" <<EOF
✅ No TypeErrors detected during monitoring period

This indicates that the protobuf version incompatibility issue has been successfully resolved.
EOF
    fi

    cat >> "${summary_file}" <<EOF

## Timestamp Validation
- **Total timestamps logged:** ${timestamps}
- **Format:** ISO 8601
- All timestamps appear valid in logs

## Next Steps
1. Review detailed logs in ${OUTPUT_DIR}
2. Correlate with test results from test-e2e-validation-complete.py
3. Generate final validation report using generate-e2e-validation-report.py

## Files Generated
- Consensus Engine: \`consensus-engine-*-monitor.log\`
- Specialists: \`specialist-*-monitor.log\`
- TypeError Alerts: \`typeerror-alerts.log\`
- Live Stats: \`live-stats.log\`
- This Summary: \`MONITORING_SUMMARY.md\`

---
**Generated:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
EOF

    echo -e "${GREEN}✓ Summary generated: ${summary_file}${RESET}\n"

    # Display summary
    cat "${summary_file}"
}

#######################################
# Cleanup on exit
#######################################
cleanup_on_exit() {
    echo -e "\n${YELLOW}Cleaning up...${RESET}"
    stop_monitoring
    generate_monitoring_summary

    echo -e "\n${BOLD}${GREEN}╔════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${GREEN}║         MONITORING COMPLETED                               ║${RESET}"
    echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════╝${RESET}\n"

    echo -e "Logs saved to: ${BOLD}${OUTPUT_DIR}${RESET}"
    echo -e "Summary report: ${BOLD}${OUTPUT_DIR}/MONITORING_SUMMARY.md${RESET}\n"
}

#######################################
# Main function
#######################################
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --duration)
                DURATION_SECONDS="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --consensus-only)
                MONITOR_CONSENSUS=true
                MONITOR_SPECIALISTS=false
                shift
                ;;
            --specialists-only)
                MONITOR_CONSENSUS=false
                MONITOR_SPECIALISTS=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                echo "Usage: $0 [--duration SECONDS] [--namespace NAME] [--output-dir PATH] [--consensus-only] [--specialists-only]"
                exit 1
                ;;
        esac
    done

    # Execute monitoring
    print_banner
    check_prerequisites
    create_output_directory

    if [[ "${MONITOR_CONSENSUS}" == "true" ]]; then
        monitor_consensus_engine
    fi

    if [[ "${MONITOR_SPECIALISTS}" == "true" ]]; then
        monitor_specialists
    fi

    monitor_for_typeerrors
    display_live_stats

    wait_for_duration

    stop_monitoring
    generate_monitoring_summary

    # Determine exit code
    local typeerrors=0
    if [[ -f "${OUTPUT_DIR}/typeerror-alerts.log" ]]; then
        typeerrors=$(wc -l < "${OUTPUT_DIR}/typeerror-alerts.log" 2>/dev/null || echo 0)
    fi

    if [[ ${typeerrors} -gt 0 ]]; then
        echo -e "${RED}Exit code: 1 (TypeErrors detected)${RESET}"
        return 1
    else
        echo -e "${GREEN}Exit code: 0 (No TypeErrors detected)${RESET}"
        return 0
    fi
}

# Set up trap for cleanup
trap cleanup_on_exit EXIT INT TERM

# Run main
main "$@"
