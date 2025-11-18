#!/bin/bash
#
# gRPC Comprehensive Test Suite - Orchestration Script
#
# This script orchestrates the execution of comprehensive gRPC tests
# for all Neural Hive specialists with multiple payload scenarios.
#
# Usage:
#   ./run-grpc-comprehensive-tests.sh --all                    # Run all tests
#   ./run-grpc-comprehensive-tests.sh --business               # Test specialist-business only
#   ./run-grpc-comprehensive-tests.sh --specialist technical   # Test specific specialist
#   ./run-grpc-comprehensive-tests.sh --all --cleanup          # Run with cleanup

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

NAMESPACE="${SPECIALISTS_NAMESPACE:-neural-hive}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/grpc-comprehensive-tests}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${OUTPUT_DIR}/test_execution_${TIMESTAMP}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Test script path
TEST_SCRIPT="${SCRIPT_DIR}/test-grpc-comprehensive.py"

# ============================================================================
# Functions
# ============================================================================

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "================================================================================"
    echo "  gRPC COMPREHENSIVE TEST SUITE"
    echo "  Neural Hive Mind - Orchestrated Testing"
    echo "================================================================================"
    echo -e "${NC}"
    echo -e "${BLUE}Namespace:${NC}      ${NAMESPACE}"
    echo -e "${BLUE}Output Dir:${NC}     ${OUTPUT_DIR}"
    echo -e "${BLUE}Timestamp:${NC}      ${TIMESTAMP}"
    echo -e "${BLUE}Log File:${NC}       ${LOG_FILE}"

    # Get Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        echo -e "${BLUE}Python:${NC}         ${PYTHON_VERSION}"
    fi

    # Get Protobuf version
    if command -v python3 &> /dev/null; then
        PROTOBUF_VERSION=$(python3 -c "import google.protobuf; print(google.protobuf.__version__)" 2>/dev/null || echo "unknown")
        echo -e "${BLUE}Protobuf:${NC}       ${PROTOBUF_VERSION}"
    fi

    echo "================================================================================"
    echo ""
}

check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    # Check Python3
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ ERROR: python3 not found${NC}"
        echo "Please install Python 3.8 or higher"
        exit 1
    fi
    echo -e "${GREEN}✅ python3 found${NC}"

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}❌ ERROR: kubectl not found${NC}"
        echo "Please install kubectl"
        exit 1
    fi
    echo -e "${GREEN}✅ kubectl found${NC}"

    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}❌ ERROR: Cannot connect to Kubernetes cluster${NC}"
        echo "Please check your kubeconfig"
        exit 1
    fi
    echo -e "${GREEN}✅ Kubernetes cluster connected${NC}"

    # Check namespace exists
    if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
        echo -e "${RED}❌ ERROR: Namespace '${NAMESPACE}' does not exist${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Namespace '${NAMESPACE}' exists${NC}"

    # Check specialists are running
    local specialists=("business" "technical" "behavior" "evolution" "architecture")
    local all_running=true

    for specialist in "${specialists[@]}"; do
        local pod_count=$(kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/name=specialist-${specialist}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
        if [ "${pod_count}" -eq 0 ]; then
            echo -e "${YELLOW}⚠️  WARNING: specialist-${specialist} has no running pods${NC}"
            all_running=false
        else
            echo -e "${GREEN}✅ specialist-${specialist} is running (${pod_count} pod(s))${NC}"
        fi
    done

    if [ "${all_running}" = false ]; then
        echo -e "${YELLOW}⚠️  WARNING: Some specialists are not running. Tests may fail.${NC}"
        if [ "${ASSUME_YES}" != "true" ]; then
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        else
            echo -e "${YELLOW}Proceeding automatically (--yes flag set)${NC}"
        fi
    fi

    # Check Python libraries
    echo -e "${YELLOW}Checking Python libraries...${NC}"

    local required_libs=("grpc" "structlog" "google.protobuf")
    for lib in "${required_libs[@]}"; do
        if python3 -c "import ${lib}" 2>/dev/null; then
            echo -e "${GREEN}✅ ${lib} installed${NC}"
        else
            echo -e "${RED}❌ ERROR: ${lib} not installed${NC}"
            echo "Please install: pip3 install grpcio structlog protobuf"
            exit 1
        fi
    done

    # Check neural_hive_specialists library
    if python3 -c "from neural_hive_specialists.proto_gen import specialist_pb2" 2>/dev/null; then
        echo -e "${GREEN}✅ neural_hive_specialists library available${NC}"
    else
        echo -e "${RED}❌ ERROR: neural_hive_specialists library not found${NC}"
        echo "Please install the library from libraries/python/neural_hive_specialists/"
        exit 1
    fi

    # Check test script exists
    if [ ! -f "${TEST_SCRIPT}" ]; then
        echo -e "${RED}❌ ERROR: Test script not found: ${TEST_SCRIPT}${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Test script found${NC}"

    echo -e "${GREEN}All prerequisites satisfied!${NC}"
    echo ""
}

create_output_directory() {
    echo -e "${YELLOW}Creating output directories...${NC}"

    mkdir -p "${OUTPUT_DIR}"
    mkdir -p "${OUTPUT_DIR}/stacktraces"
    mkdir -p "${OUTPUT_DIR}/payloads"
    mkdir -p "${OUTPUT_DIR}/logs"

    # Create README in output directory
    cat > "${OUTPUT_DIR}/README.md" << EOF
# gRPC Comprehensive Test Results

## Test Session
- **Timestamp**: ${TIMESTAMP}
- **Namespace**: ${NAMESPACE}
- **Output Directory**: ${OUTPUT_DIR}
- **Log File**: ${LOG_FILE}

## Environment
- **Python Version**: $(python3 --version 2>&1)
- **Protobuf Version**: $(python3 -c "import google.protobuf; print(google.protobuf.__version__)" 2>/dev/null || echo "unknown")
- **gRPC Version**: $(python3 -c "import grpc; print(grpc.__version__)" 2>/dev/null || echo "unknown")

## Directory Structure
- \`stacktraces/\` - Detailed stack traces for failed tests
- \`payloads/\` - JSON payloads that caused failures
- \`logs/\` - Execution logs

## Command Executed
\`\`\`bash
$0 $@
\`\`\`

## Files
- JSON results: \`test_results_*.json\`
- Markdown reports: \`TEST_RESULTS_*.md\`
- Execution log: \`test_execution_${TIMESTAMP}.log\`
EOF

    echo -e "${GREEN}✅ Output directories created: ${OUTPUT_DIR}${NC}"
    echo ""
}

run_test_scenario() {
    local scenario_name="$1"
    local additional_args="$2"

    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}  Running Scenario: ${scenario_name}${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    local cmd="python3 ${TEST_SCRIPT} ${additional_args} --output-dir ${OUTPUT_DIR} --namespace ${NAMESPACE}"

    echo -e "${BLUE}Command:${NC} ${cmd}"
    echo ""

    # Run test and capture output
    if ${cmd} 2>&1 | tee -a "${LOG_FILE}"; then
        local exit_code=0
        echo ""
        echo -e "${GREEN}✅ Scenario '${scenario_name}' completed successfully${NC}"
    else
        local exit_code=$?
        echo ""
        echo -e "${RED}❌ Scenario '${scenario_name}' failed with exit code ${exit_code}${NC}"
    fi

    echo ""
    return ${exit_code}
}

run_all_scenarios() {
    echo -e "${CYAN}${BOLD}Running all test scenarios...${NC}"
    echo ""

    local total_scenarios=0
    local passed_scenarios=0
    local failed_scenarios=0

    # Scenario 1: All specialists, all scenarios
    echo -e "${YELLOW}Scenario 1: Testing all specialists with all scenarios${NC}"
    total_scenarios=$((total_scenarios + 1))
    if run_test_scenario "all_specialists" ""; then
        passed_scenarios=$((passed_scenarios + 1))
    else
        failed_scenarios=$((failed_scenarios + 1))
    fi

    # Scenario 2: Business focused
    echo -e "${YELLOW}Scenario 2: Focused testing for specialist-business${NC}"
    total_scenarios=$((total_scenarios + 1))
    if run_test_scenario "business_focused" "--focus-business"; then
        passed_scenarios=$((passed_scenarios + 1))
    else
        failed_scenarios=$((failed_scenarios + 1))
    fi

    # Scenario 3: Individual specialists
    local specialists=("technical" "behavior" "evolution" "architecture")
    for specialist in "${specialists[@]}"; do
        echo -e "${YELLOW}Scenario: Testing specialist-${specialist} individually${NC}"
        total_scenarios=$((total_scenarios + 1))
        if run_test_scenario "${specialist}_only" "--specialist ${specialist}"; then
            passed_scenarios=$((passed_scenarios + 1))
        else
            failed_scenarios=$((failed_scenarios + 1))
        fi
    done

    echo ""
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}  All Scenarios Summary${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Total Scenarios:${NC}  ${total_scenarios}"
    echo -e "${GREEN}Passed:${NC}           ${passed_scenarios}"
    echo -e "${RED}Failed:${NC}           ${failed_scenarios}"
    echo ""

    if [ ${failed_scenarios} -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

generate_consolidated_report() {
    echo -e "${YELLOW}Generating consolidated report...${NC}"

    local consolidated_file="${OUTPUT_DIR}/CONSOLIDATED_REPORT_${TIMESTAMP}.md"

    # Find all JSON result files
    local json_files=($(find "${OUTPUT_DIR}" -name "test_results_*.json" -type f | sort -r | head -5))

    if [ ${#json_files[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  No result files found to consolidate${NC}"
        return 0
    fi

    cat > "${consolidated_file}" << 'EOF'
# Consolidated Test Results Report

## Overview
This report consolidates results from multiple test executions.

EOF

    echo "## Test Sessions" >> "${consolidated_file}"
    echo "" >> "${consolidated_file}"

    local session_num=1
    for json_file in "${json_files[@]}"; do
        echo "### Session ${session_num}: $(basename ${json_file})" >> "${consolidated_file}"
        echo "" >> "${consolidated_file}"

        # Extract summary if jq is available
        if command -v jq &> /dev/null; then
            local total=$(jq -r '.summary.total_tests // 0' "${json_file}")
            local passed=$(jq -r '.summary.passed // 0' "${json_file}")
            local failed=$(jq -r '.summary.failed // 0' "${json_file}")
            local pass_rate=$(jq -r '.summary.pass_rate // 0' "${json_file}")

            echo "- **Total Tests**: ${total}" >> "${consolidated_file}"
            echo "- **Passed**: ${passed} ✅" >> "${consolidated_file}"
            echo "- **Failed**: ${failed} ❌" >> "${consolidated_file}"
            echo "- **Pass Rate**: ${pass_rate}%" >> "${consolidated_file}"
        else
            echo "- **File**: ${json_file}" >> "${consolidated_file}"
            echo "- (Install jq for detailed statistics)" >> "${consolidated_file}"
        fi

        echo "" >> "${consolidated_file}"
        session_num=$((session_num + 1))
    done

    echo "## Related Files" >> "${consolidated_file}"
    echo "" >> "${consolidated_file}"
    echo "- **Stack Traces**: \`stacktraces/\`" >> "${consolidated_file}"
    echo "- **Payloads**: \`payloads/\`" >> "${consolidated_file}"
    echo "- **Execution Log**: \`${LOG_FILE}\`" >> "${consolidated_file}"
    echo "" >> "${consolidated_file}"

    echo -e "${GREEN}✅ Consolidated report generated: ${consolidated_file}${NC}"
    echo ""
}

display_summary() {
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}  FINAL SUMMARY${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Find most recent JSON result file
    local latest_json=$(find "${OUTPUT_DIR}" -name "test_results_*.json" -type f | sort -r | head -1)

    if [ -z "${latest_json}" ]; then
        echo -e "${YELLOW}⚠️  No result files found${NC}"
        return 0
    fi

    echo -e "${BLUE}Latest Results:${NC} $(basename ${latest_json})"
    echo ""

    # Display summary if jq is available
    if command -v jq &> /dev/null; then
        local total=$(jq -r '.summary.total_tests // 0' "${latest_json}")
        local passed=$(jq -r '.summary.passed // 0' "${latest_json}")
        local failed=$(jq -r '.summary.failed // 0' "${latest_json}")
        local pass_rate=$(jq -r '.summary.pass_rate // 0' "${latest_json}")

        echo -e "${BLUE}Total Tests:${NC}  ${total}"
        echo -e "${GREEN}Passed:${NC}       ${passed} ✅"
        echo -e "${RED}Failed:${NC}       ${failed} ❌"
        echo -e "${BLUE}Pass Rate:${NC}    ${pass_rate}%"
        echo ""

        if [ "${failed}" -gt 0 ]; then
            echo -e "${RED}${BOLD}⚠️  FAILURES DETECTED${NC}"
            echo ""
            echo "Failed tests:"

            # Extract failed test details
            jq -r '.results | to_entries[] | .value[] | select(.success == false) | "  - \(.specialist_type) / \(.scenario_name): \(.error_type)"' "${latest_json}" 2>/dev/null || true

            echo ""
            echo -e "${YELLOW}Review detailed results in:${NC}"
            local latest_md=$(find "${OUTPUT_DIR}" -name "TEST_RESULTS_*.md" -type f | sort -r | head -1)
            if [ -n "${latest_md}" ]; then
                echo -e "  ${latest_md}"
            fi
            echo -e "${YELLOW}Stack traces available in:${NC}"
            echo -e "  ${OUTPUT_DIR}/stacktraces/"
        else
            echo -e "${GREEN}${BOLD}✅ SUCCESS: All tests passed!${NC}"
            echo ""
            echo "The evaluated_at timestamp field is working correctly across all scenarios."
        fi
    else
        echo "Install jq for detailed summary statistics"
        echo "Results file: ${latest_json}"
    fi

    echo ""
    echo -e "${BLUE}All results saved to:${NC} ${OUTPUT_DIR}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

cleanup_old_results() {
    echo -e "${YELLOW}Cleaning up old results...${NC}"

    # Keep only 10 most recent result files
    local json_files=($(find "${OUTPUT_DIR}" -name "test_results_*.json" -type f | sort -r))
    if [ ${#json_files[@]} -gt 10 ]; then
        echo "Keeping 10 most recent result files, deleting ${#json_files[@]} - 10 older files"
        for ((i=10; i<${#json_files[@]}; i++)); do
            rm -f "${json_files[$i]}"
            echo "  Deleted: $(basename ${json_files[$i]})"
        done
    fi

    # Delete files older than 7 days
    find "${OUTPUT_DIR}" -type f -mtime +7 -delete 2>/dev/null || true

    echo -e "${GREEN}✅ Cleanup completed${NC}"
    echo ""
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Orchestrate comprehensive gRPC testing for Neural Hive specialists.

OPTIONS:
    --all                   Run all test scenarios (default)
    --business              Run focused testing for specialist-business only
    --specialist <name>     Run tests for specific specialist (business, technical, behavior, evolution, architecture)
    --scenario <name>       Run specific scenario for all specialists (simple, complex, special_chars, edge_case, minimal)
    --cleanup               Clean up old results before running
    --no-prereq-check       Skip prerequisite checks (not recommended)
    --yes, -y               Assume yes to all prompts (non-interactive mode for CI/automation)
    --namespace <name>      Kubernetes namespace (default: neural-hive)
    --output-dir <path>     Output directory (default: /tmp/grpc-comprehensive-tests)
    -h, --help              Show this help message

EXAMPLES:
    # Run all tests
    $0 --all

    # Test only specialist-business
    $0 --business

    # Test specific specialist
    $0 --specialist technical

    # Test specific scenario
    $0 --scenario complex

    # Run with cleanup
    $0 --all --cleanup

    # Use custom namespace
    $0 --all --namespace my-namespace

    # Run in non-interactive mode (for CI/CD)
    $0 --all --yes

    # Set via environment variable
    ASSUME_YES=true $0 --all

EOF
}

main() {
    local run_mode="all"
    local target_specialist=""
    local target_scenario=""
    local skip_prereq_check=false
    local do_cleanup=false

    # Initialize ASSUME_YES from environment if set, otherwise default to false
    ASSUME_YES="${ASSUME_YES:-false}"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --all)
                run_mode="all"
                shift
                ;;
            --business)
                run_mode="business"
                shift
                ;;
            --specialist)
                run_mode="specialist"
                target_specialist="$2"
                shift 2
                ;;
            --scenario)
                run_mode="scenario"
                target_scenario="$2"
                shift 2
                ;;
            --cleanup)
                do_cleanup=true
                shift
                ;;
            --no-prereq-check)
                skip_prereq_check=true
                shift
                ;;
            --yes|-y)
                ASSUME_YES=true
                shift
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                LOG_FILE="${OUTPUT_DIR}/test_execution_${TIMESTAMP}.log"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                usage
                exit 1
                ;;
        esac
    done

    # Print banner
    print_banner

    # Check prerequisites
    if [ "${skip_prereq_check}" = false ]; then
        check_prerequisites
    else
        echo -e "${YELLOW}⚠️  Skipping prerequisite checks${NC}"
        echo ""
    fi

    # Create output directory
    create_output_directory

    # Cleanup if requested
    if [ "${do_cleanup}" = true ]; then
        cleanup_old_results
    fi

    # Execute tests based on run mode
    local exit_code=0

    case ${run_mode} in
        all)
            if ! run_all_scenarios; then
                exit_code=1
            fi
            ;;
        business)
            if ! run_test_scenario "business_focused" "--focus-business"; then
                exit_code=1
            fi
            ;;
        specialist)
            if ! run_test_scenario "${target_specialist}_tests" "--specialist ${target_specialist}"; then
                exit_code=1
            fi
            ;;
        scenario)
            if ! run_test_scenario "${target_scenario}_scenario" "--scenario ${target_scenario}"; then
                exit_code=1
            fi
            ;;
    esac

    # Generate consolidated report
    generate_consolidated_report

    # Display summary
    display_summary

    return ${exit_code}
}

# Cleanup on exit
cleanup_on_exit() {
    local exit_code=$?
    if [ ${exit_code} -ne 0 ] && [ ${exit_code} -ne 130 ]; then
        echo ""
        echo -e "${RED}Script exited with error code ${exit_code}${NC}"
        echo -e "${YELLOW}Check log file: ${LOG_FILE}${NC}"
    fi
}

trap cleanup_on_exit EXIT

# Execute main function
main "$@"
