#!/bin/bash
# E2E Validation Suite - Orchestrator
# Executes E2E tests + log monitoring simultaneously and generates final report

set -euo pipefail

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

# Configuration
NUM_ITERATIONS="${NUM_ITERATIONS:-10}"
GATEWAY_URL="${GATEWAY_URL:-http://10.97.189.184:8000}"
NAMESPACE="${NAMESPACE:-neural-hive}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/e2e-validation-suite-$(date +%Y%m%d_%H%M%S)}"
MONITORING_DURATION="${MONITORING_DURATION:-660}"  # 11 minutes - safety margin
GENERATE_REPORT=true

# Process IDs
MONITOR_PID=""
TEST_EXIT_CODE=0
MONITOR_EXIT_CODE=0
REPORT_EXIT_CODE=0

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT="${SCRIPT_DIR}/test-e2e-validation-complete.py"
MONITOR_SCRIPT="${SCRIPT_DIR}/monitor-e2e-logs.sh"
REPORT_SCRIPT="${SCRIPT_DIR}/generate-e2e-validation-report.py"

#######################################
# Print banner with configuration
#######################################
print_banner() {
    echo -e "${BOLD}${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║            E2E VALIDATION SUITE                            ║"
    echo "║         Comprehensive End-to-End Validation                ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo "Configuration:"
    echo "  Iterations: ${NUM_ITERATIONS}"
    echo "  Gateway URL: ${GATEWAY_URL}"
    echo "  Namespace: ${NAMESPACE}"
    echo "  Output Directory: ${OUTPUT_DIR}"
    echo "  Monitoring Duration: ${MONITORING_DURATION}s"
    echo ""
    echo "Components Tested:"
    echo "  ✓ Gateway API"
    echo "  ✓ Semantic Translation Engine"
    echo "  ✓ Consensus Engine"
    echo "  ✓ 5 Specialists (business, technical, behavior, evolution, architecture)"
    echo ""
}

#######################################
# Check prerequisites
#######################################
check_prerequisites() {
    echo -e "${CYAN}Checking prerequisites...${RESET}"

    local all_ok=true

    # Check python3
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}✗ python3 not found${RESET}"
        all_ok=false
    else
        echo -e "${GREEN}✓ python3 found${RESET}"
    fi

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}✗ kubectl not found${RESET}"
        all_ok=false
    else
        echo -e "${GREEN}✓ kubectl found${RESET}"
    fi

    # Check scripts exist
    if [[ ! -f "${TEST_SCRIPT}" ]]; then
        echo -e "${RED}✗ Test script not found: ${TEST_SCRIPT}${RESET}"
        all_ok=false
    else
        echo -e "${GREEN}✓ Test script found${RESET}"
    fi

    if [[ ! -f "${MONITOR_SCRIPT}" ]]; then
        echo -e "${RED}✗ Monitor script not found: ${MONITOR_SCRIPT}${RESET}"
        all_ok=false
    else
        echo -e "${GREEN}✓ Monitor script found${RESET}"
    fi

    if [[ ! -f "${REPORT_SCRIPT}" ]]; then
        echo -e "${YELLOW}⚠ Report script not found: ${REPORT_SCRIPT}${RESET}"
        echo -e "${YELLOW}  Report generation will be skipped${RESET}"
        GENERATE_REPORT=false
    else
        echo -e "${GREEN}✓ Report script found${RESET}"
    fi

    # Check Gateway is accessible
    echo -e "${CYAN}Checking Gateway accessibility...${RESET}"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/health" || echo "000")

    if [[ "${http_code}" == "200" ]]; then
        echo -e "${GREEN}✓ Gateway is accessible (HTTP ${http_code})${RESET}"
    else
        echo -e "${RED}✗ Gateway not accessible (HTTP ${http_code})${RESET}"
        echo -e "${RED}  URL: ${GATEWAY_URL}/health${RESET}"
        all_ok=false
    fi

    # Check pods are running
    echo -e "${CYAN}Checking Kubernetes pods...${RESET}"

    # Consensus Engine
    local consensus_pods
    consensus_pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=consensus-engine --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
    if [[ ${consensus_pods} -gt 0 ]]; then
        echo -e "${GREEN}✓ Consensus Engine: ${consensus_pods} pod(s) running${RESET}"
    else
        echo -e "${RED}✗ Consensus Engine: No running pods${RESET}"
        all_ok=false
    fi

    # Specialists
    for specialist in business technical behavior evolution architecture; do
        local specialist_pods
        # Try app.kubernetes.io/name first (standard label), fallback to app label
        specialist_pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=specialist-${specialist} --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
        if [[ ${specialist_pods} -eq 0 ]]; then
            # Fallback to legacy label
            specialist_pods=$(kubectl get pods -n "${NAMESPACE}" -l app=specialist-${specialist} --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
        fi
        if [[ ${specialist_pods} -gt 0 ]]; then
            echo -e "${GREEN}✓ Specialist ${specialist}: ${specialist_pods} pod(s) running${RESET}"
        else
            echo -e "${YELLOW}⚠ Specialist ${specialist}: No running pods${RESET}"
        fi
    done

    if [[ "${all_ok}" != "true" ]]; then
        echo -e "\n${RED}${BOLD}✗ Prerequisites check failed${RESET}"
        echo -e "${RED}Please resolve the issues above before running the validation suite${RESET}\n"
        exit 1
    fi

    echo -e "${GREEN}✓ All prerequisites met${RESET}\n"
}

#######################################
# Create output directory structure
#######################################
create_output_structure() {
    echo -e "${CYAN}Creating output directory structure...${RESET}"

    mkdir -p "${OUTPUT_DIR}/test-results"
    mkdir -p "${OUTPUT_DIR}/logs"
    mkdir -p "${OUTPUT_DIR}/reports"

    # Create README
    cat > "${OUTPUT_DIR}/README.md" <<EOF
# E2E Validation Suite - Session $(date +%Y%m%d_%H%M%S)

## Configuration
- **Iterations:** ${NUM_ITERATIONS}
- **Gateway URL:** ${GATEWAY_URL}
- **Namespace:** ${NAMESPACE}
- **Start Time:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")

## Directory Structure
- \`test-results/\`: Test execution results (JSON, logs)
- \`logs/\`: Kubernetes logs captured during tests
- \`reports/\`: Final validation reports (Markdown, HTML)

## Execution
- **Test Script:** test-e2e-validation-complete.py
- **Log Monitor:** monitor-e2e-logs.sh
- **Report Generator:** generate-e2e-validation-report.py

## Results
Results will be available after test completion.

---
**Session ID:** $(basename "${OUTPUT_DIR}")
EOF

    echo -e "${GREEN}✓ Output structure created${RESET}\n"
}

#######################################
# Start log monitoring
#######################################
start_log_monitoring() {
    echo -e "${CYAN}Starting log monitoring...${RESET}"

    # Start monitoring in background
    OUTPUT_DIR="${OUTPUT_DIR}/logs" \
    DURATION_SECONDS="${MONITORING_DURATION}" \
    NAMESPACE="${NAMESPACE}" \
    "${MONITOR_SCRIPT}" > "${OUTPUT_DIR}/monitor-output.log" 2>&1 &

    MONITOR_PID=$!

    # Wait for monitoring to initialize
    sleep 5

    # Verify monitoring is running
    if ! kill -0 "${MONITOR_PID}" 2>/dev/null; then
        echo -e "${RED}✗ Log monitoring failed to start${RESET}"
        echo -e "${RED}Check ${OUTPUT_DIR}/monitor-output.log for details${RESET}"
        exit 1
    fi

    echo -e "${GREEN}✓ Log monitoring started (PID: ${MONITOR_PID})${RESET}\n"
}

#######################################
# Run E2E tests
#######################################
run_e2e_tests() {
    local padding_length=$((46 - ${#NUM_ITERATIONS}))
    local padding=$(printf '%*s' "${padding_length}" '')
    echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║         STARTING E2E TESTS (${NUM_ITERATIONS} iterations)${padding}║${RESET}"
    echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════╝${RESET}\n"

    # Run tests
    python3 "${TEST_SCRIPT}" \
        --iterations "${NUM_ITERATIONS}" \
        --gateway-url "${GATEWAY_URL}" \
        --output-dir "${OUTPUT_DIR}/test-results" \
        2>&1 | tee "${OUTPUT_DIR}/test-execution.log"

    TEST_EXIT_CODE=$?

    # Analyze result
    if [[ ${TEST_EXIT_CODE} -eq 0 ]]; then
        echo -e "\n${GREEN}${BOLD}✓ E2E tests completed successfully${RESET}\n"
    elif [[ ${TEST_EXIT_CODE} -eq 1 ]]; then
        echo -e "\n${YELLOW}${BOLD}⚠ E2E tests completed with failures${RESET}\n"
    else
        echo -e "\n${RED}${BOLD}✗ E2E tests failed with errors${RESET}\n"
    fi

    return ${TEST_EXIT_CODE}
}

#######################################
# Wait for monitoring completion
#######################################
wait_for_monitoring_completion() {
    echo -e "${CYAN}Waiting for log monitoring to complete...${RESET}"

    if kill -0 "${MONITOR_PID}" 2>/dev/null; then
        wait "${MONITOR_PID}" 2>/dev/null || true
        MONITOR_EXIT_CODE=$?
    else
        MONITOR_EXIT_CODE=0  # Already terminated
    fi

    # Analyze result
    if [[ ${MONITOR_EXIT_CODE} -eq 0 ]]; then
        echo -e "${GREEN}✓ Log monitoring completed (no TypeErrors detected)${RESET}\n"
    elif [[ ${MONITOR_EXIT_CODE} -eq 1 ]]; then
        echo -e "${YELLOW}⚠ Log monitoring completed (TypeErrors detected!)${RESET}\n"
    fi

    return ${MONITOR_EXIT_CODE}
}

#######################################
# Generate final report
#######################################
generate_final_report() {
    if [[ "${GENERATE_REPORT}" != "true" ]]; then
        echo -e "${YELLOW}Skipping report generation (script not available)${RESET}\n"
        return 0
    fi

    echo -e "${CYAN}Generating final validation report...${RESET}"

    python3 "${REPORT_SCRIPT}" \
        --test-results "${OUTPUT_DIR}/test-results" \
        --logs "${OUTPUT_DIR}/logs" \
        --output "${OUTPUT_DIR}/reports/FINAL_VALIDATION_REPORT.md" \
        2>&1 | tee "${OUTPUT_DIR}/report-generation.log"

    REPORT_EXIT_CODE=$?

    if [[ ${REPORT_EXIT_CODE} -eq 0 ]]; then
        echo -e "${GREEN}✓ Final report generated${RESET}"
        echo -e "${GREEN}  Location: ${OUTPUT_DIR}/reports/FINAL_VALIDATION_REPORT.md${RESET}\n"
    else
        echo -e "${YELLOW}⚠ Report generation failed${RESET}"
        echo -e "${YELLOW}  Check ${OUTPUT_DIR}/report-generation.log for details${RESET}\n"
    fi

    return ${REPORT_EXIT_CODE}
}

#######################################
# Helper function to calculate padding
#######################################
calc_padding() {
    local text="$1"
    local total_width=57  # Total width inside box (excluding │ and spaces)
    local text_length=${#text}
    local padding_length=$((total_width - text_length))
    printf '%*s' "${padding_length}" ''
}

#######################################
# Display summary
#######################################
display_summary() {
    echo -e "\n${BOLD}╔════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║         E2E VALIDATION SUITE - EXECUTION SUMMARY           ║${RESET}"
    echo -e "${BOLD}╚════════════════════════════════════════════════════════════╝${RESET}\n"

    echo -e "${BOLD}Session ID:${RESET} $(basename "${OUTPUT_DIR}")"
    echo -e "${BOLD}Output Directory:${RESET} ${OUTPUT_DIR}\n"

    # Component results
    echo -e "${BOLD}┌─────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${BOLD}│ COMPONENT RESULTS                                       │${RESET}"
    echo -e "${BOLD}├─────────────────────────────────────────────────────────┤${RESET}"

    # E2E Tests
    if [[ ${TEST_EXIT_CODE} -eq 0 ]]; then
        echo -e "${BOLD}│ E2E Tests:          ${GREEN}✓ PASSED${RESET}${BOLD}                            │${RESET}"
    elif [[ ${TEST_EXIT_CODE} -eq 1 ]]; then
        echo -e "${BOLD}│ E2E Tests:          ${YELLOW}⚠ FAILED${RESET}${BOLD}                            │${RESET}"
    else
        echo -e "${BOLD}│ E2E Tests:          ${RED}✗ ERROR${RESET}${BOLD}                             │${RESET}"
    fi

    # Log Monitoring
    if [[ ${MONITOR_EXIT_CODE} -eq 0 ]]; then
        echo -e "${BOLD}│ Log Monitoring:     ${GREEN}✓ NO ERRORS${RESET}${BOLD}                         │${RESET}"
    else
        echo -e "${BOLD}│ Log Monitoring:     ${YELLOW}⚠ TYPEERRORS${RESET}${BOLD}                        │${RESET}"
    fi

    # Report Generation
    if [[ "${GENERATE_REPORT}" == "true" ]]; then
        if [[ ${REPORT_EXIT_CODE} -eq 0 ]]; then
            echo -e "${BOLD}│ Report Generation:  ${GREEN}✓ SUCCESS${RESET}${BOLD}                           │${RESET}"
        else
            echo -e "${BOLD}│ Report Generation:  ${YELLOW}⚠ FAILED${RESET}${BOLD}                            │${RESET}"
        fi
    else
        echo -e "${BOLD}│ Report Generation:  ${YELLOW}○ SKIPPED${RESET}${BOLD}                           │${RESET}"
    fi

    echo -e "${BOLD}└─────────────────────────────────────────────────────────┘${RESET}\n"

    # Key metrics (from test results if available)
    local metrics_file
    metrics_file=$(find "${OUTPUT_DIR}/test-results" -name "e2e-metrics-*.json" -type f 2>/dev/null | head -1)

    if [[ -n "${metrics_file}" && -f "${metrics_file}" ]]; then
        echo -e "${BOLD}┌─────────────────────────────────────────────────────────┐${RESET}"
        echo -e "${BOLD}│ KEY METRICS (from test results)                         │${RESET}"
        echo -e "${BOLD}├─────────────────────────────────────────────────────────┤${RESET}"

        local total_tests passed_tests success_rate timestamp_rate
        total_tests=$(python3 -c "import json; print(json.load(open('${metrics_file}'))['summary_statistics']['total_tests'])" 2>/dev/null || echo "N/A")
        passed_tests=$(python3 -c "import json; print(json.load(open('${metrics_file}'))['summary_statistics']['passed_tests'])" 2>/dev/null || echo "N/A")
        success_rate=$(python3 -c "import json; print(f\"{json.load(open('${metrics_file}'))['summary_statistics']['success_rate']:.1f}\")" 2>/dev/null || echo "N/A")
        timestamp_rate=$(python3 -c "import json; print(f\"{json.load(open('${metrics_file}'))['summary_statistics']['timestamp_validation_rate']:.1f}\")" 2>/dev/null || echo "N/A")

        local line1="Total Tests:        ${total_tests}"
        local line2="Tests Passed:       ${passed_tests}/${total_tests} (${success_rate}%)"
        local line3="Timestamps Valid:   ${timestamp_rate}%"
        echo -e "${BOLD}│ ${line1}$(calc_padding "${line1}") │${RESET}"
        echo -e "${BOLD}│ ${line2}$(calc_padding "${line2}") │${RESET}"
        echo -e "${BOLD}│ ${line3}$(calc_padding "${line3}") │${RESET}"

        echo -e "${BOLD}└─────────────────────────────────────────────────────────┘${RESET}\n"
    fi

    # Files generated
    echo -e "${BOLD}┌─────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${BOLD}│ FILES GENERATED                                         │${RESET}"
    echo -e "${BOLD}├─────────────────────────────────────────────────────────┤${RESET}"
    local file1="Test Results:       ${OUTPUT_DIR}/test-results/"
    local file2="Logs:               ${OUTPUT_DIR}/logs/"
    local file3="Final Report:       ${OUTPUT_DIR}/reports/"
    local file4="Execution Log:      ${OUTPUT_DIR}/test-execution.log"
    echo -e "${BOLD}│ ${file1}$(calc_padding "${file1}") │${RESET}"
    echo -e "${BOLD}│ ${file2}$(calc_padding "${file2}") │${RESET}"
    echo -e "${BOLD}│ ${file3}$(calc_padding "${file3}") │${RESET}"
    echo -e "${BOLD}│ ${file4}$(calc_padding "${file4}") │${RESET}"
    echo -e "${BOLD}└─────────────────────────────────────────────────────────┘${RESET}\n"

    # Final verdict
    echo -e "${BOLD}┌─────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${BOLD}│ FINAL VERDICT                                           │${RESET}"
    echo -e "${BOLD}├─────────────────────────────────────────────────────────┤${RESET}"

    local verdict_color verdict_text

    if [[ ${TEST_EXIT_CODE} -eq 0 && ${MONITOR_EXIT_CODE} -eq 0 ]]; then
        verdict_color="${GREEN}"
        verdict_text="✓ VALIDATION PASSED - System is stable and ready"
    elif [[ ${TEST_EXIT_CODE} -le 1 && ${MONITOR_EXIT_CODE} -eq 0 ]]; then
        verdict_color="${YELLOW}"
        verdict_text="⚠ VALIDATION PASSED WITH WARNINGS - Review failures"
    else
        verdict_color="${RED}"
        verdict_text="✗ VALIDATION FAILED - Critical issues detected"
    fi

    # Strip ANSI codes for padding calculation
    local verdict_text_plain="${verdict_text}"
    local padding=$(calc_padding "${verdict_text_plain}")
    echo -e "${BOLD}│ ${verdict_color}${verdict_text}${RESET}${BOLD}${padding} │${RESET}"
    echo -e "${BOLD}└─────────────────────────────────────────────────────────┘${RESET}\n"
}

#######################################
# Cleanup on exit
#######################################
cleanup_on_exit() {
    echo -e "\n${YELLOW}Cleaning up...${RESET}"

    # Stop monitoring if still running
    if [[ -n "${MONITOR_PID}" ]] && kill -0 "${MONITOR_PID}" 2>/dev/null; then
        echo -e "${CYAN}Stopping log monitoring...${RESET}"
        kill -TERM "${MONITOR_PID}" 2>/dev/null || true
        wait "${MONITOR_PID}" 2>/dev/null || true
    fi

    echo -e "${GREEN}✓ Cleanup completed${RESET}"
}

#######################################
# Main function
#######################################
main() {
    local tests_only=false
    local monitoring_only=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --iterations)
                NUM_ITERATIONS="$2"
                shift 2
                ;;
            --gateway-url)
                GATEWAY_URL="$2"
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
            --no-report)
                GENERATE_REPORT=false
                shift
                ;;
            --monitoring-only)
                monitoring_only=true
                shift
                ;;
            --tests-only)
                tests_only=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                echo "Usage: $0 [--iterations N] [--gateway-url URL] [--namespace NAME] [--output-dir PATH] [--no-report] [--monitoring-only] [--tests-only]"
                exit 1
                ;;
        esac
    done

    # Execute validation suite
    print_banner
    check_prerequisites
    create_output_structure

    # Start log monitoring (unless tests-only)
    if [[ "${tests_only}" != "true" ]]; then
        start_log_monitoring
        echo -e "${YELLOW}Waiting 5 seconds for monitoring to stabilize...${RESET}\n"
        sleep 5
    fi

    # Run tests (unless monitoring-only)
    if [[ "${monitoring_only}" != "true" ]]; then
        run_e2e_tests || true  # Don't exit on test failure
    fi

    # Wait for monitoring to complete (unless tests-only)
    if [[ "${tests_only}" != "true" ]]; then
        wait_for_monitoring_completion || true  # Don't exit on monitoring issues
    fi

    # Generate final report
    if [[ "${monitoring_only}" != "true" && "${tests_only}" != "true" ]]; then
        generate_final_report || true  # Don't exit on report generation failure
    fi

    # Display summary
    display_summary

    # Determine final exit code
    local final_exit_code=0

    if [[ ${TEST_EXIT_CODE} -ne 0 ]]; then
        final_exit_code=1
    fi

    if [[ ${MONITOR_EXIT_CODE} -ne 0 ]]; then
        final_exit_code=2  # Critical: TypeErrors detected
    fi

    if [[ ${final_exit_code} -eq 0 ]]; then
        echo -e "${GREEN}${BOLD}Exit code: 0 (All validations passed)${RESET}\n"
    elif [[ ${final_exit_code} -eq 1 ]]; then
        echo -e "${YELLOW}${BOLD}Exit code: 1 (Some tests failed, but no critical issues)${RESET}\n"
    else
        echo -e "${RED}${BOLD}Exit code: 2 (Critical issues detected - TypeErrors present)${RESET}\n"
    fi

    return ${final_exit_code}
}

# Set up trap for cleanup
trap cleanup_on_exit EXIT INT TERM

# Run main
main "$@"
