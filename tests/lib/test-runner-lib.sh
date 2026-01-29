#!/usr/bin/env bash
set -euo pipefail

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${LIB_DIR}/../.." && pwd)"

# Source shared helpers
source "${REPO_ROOT}/scripts/lib/common.sh"
source "${REPO_ROOT}/scripts/helpers/test-helpers.sh"

DEFAULT_TEST_TIMEOUT=600
declare -i TEST_FAILURE_COUNT=0
declare -i TEST_TOTAL_COUNT=0
declare -i TEST_PASSED_COUNT=0
declare -i TEST_FAILED_COUNT=0
declare -i TEST_CASES_TOTAL=0
declare -i TEST_CASES_PASSED=0
declare -i TEST_CASES_FAILED=0
TEST_RESULT_FILE=""
TEST_REPORT_LABEL=""

ensure_output_dir() {
  local target_dir="$1"
  mkdir -p "$target_dir"
}

init_test_report() {
  local label="${1:-neural-hive-mind-tests}"
  TEST_REPORT_LABEL="$label"
  local output_dir="${OUTPUT_DIR:-${LIB_DIR}/../results}"
  ensure_output_dir "$output_dir"
  TEST_RESULT_FILE="${output_dir}/test-results.jsonl"
  : > "$TEST_RESULT_FILE"
  TEST_TOTAL_COUNT=0
  TEST_PASSED_COUNT=0
  TEST_FAILED_COUNT=0
  TEST_CASES_TOTAL=0
  TEST_CASES_PASSED=0
  TEST_CASES_FAILED=0
  TEST_FAILURE_COUNT=0
  TEST_REPORT_JSON=""
  TEST_START_TIME="$(date +%s)"
}

parse_test_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --type)
        TEST_TYPE="${2:-all}"
        shift 2
        ;;
      --phase)
        TEST_PHASE="${2:-all}"
        shift 2
        ;;
      --component)
        TEST_COMPONENT="${2:-}"
        shift 2
        ;;
      --coverage)
        COVERAGE=true
        shift
        ;;
      --report)
        GENERATE_REPORT=true
        shift
        ;;
      --no-report)
        GENERATE_REPORT=false
        shift
        ;;
      --parallel)
        PARALLEL=true
        shift
        ;;
      --jobs)
        PARALLEL_JOBS="${2:-4}"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --debug)
        DEBUG=true
        shift
        ;;
      --output-dir)
      OUTPUT_DIR="${2:-${LIB_DIR}/../results}"
        shift 2
        ;;
      --cleanup-only)
        cleanup_test_resources
        exit 0
        ;;
      --help)
        cat <<HELPOUT
Usage: run-tests.sh [options]
  --type <unit|integration|e2e|all>
  --phase <1|2|all>
  --component <name>
  --coverage
  --report | --no-report
  --parallel
  --jobs <n>
  --dry-run
  --debug
  --output-dir <path>
  --cleanup-only
  --help
HELPOUT
        exit 0
        ;;
      *)
        log_warning "Unknown option: $1"
        shift
        ;;
    esac
  done

  export DEBUG
  OUTPUT_DIR="${OUTPUT_DIR:-${LIB_DIR}/../results}"
}

detect_test_type() {
  local path="$1"
  if [[ "$path" == *"/unit/"* ]]; then
    echo "unit"
    return
  fi
  if [[ "$path" == *"/integration/"* ]]; then
    echo "integration"
    return
  fi
  if [[ "$path" == *"/e2e/phase1/"* ]]; then
    echo "e2e"
    return
  fi
  if [[ "$path" == *"/e2e/phase2/"* ]]; then
    echo "e2e"
    return
  fi
  if [[ "$path" == *"/e2e/specialists/"* ]]; then
    echo "e2e"
    return
  fi
  if [[ "$path" == *"/services/"* ]] || [[ "$path" == *"/specialists/"* ]]; then
    echo "integration"
    return
  fi
  echo "unit"
}

add_test_result() {
  local test_name="$1"
  local status="$2"
  local details="$3"
  local artifact="$4"
  TEST_TOTAL_COUNT=$((TEST_TOTAL_COUNT + 1))
  case "${status,,}" in
    passed)
      TEST_PASSED_COUNT=$((TEST_PASSED_COUNT + 1))
      ;;
    failed)
      TEST_FAILED_COUNT=$((TEST_FAILED_COUNT + 1))
      ;;
  esac
  local entry
  entry=$(jq -c -n --arg name "$test_name" \
    --arg status "$status" \
    --arg details "$details" \
    --arg artifact "$artifact" '{name: $name, status: $status, details: $details, artifact: $artifact}')
  echo "$entry" >> "$TEST_RESULT_FILE"
}

add_bash_tests() {
  local -n _tests_ref=$1
  local dir_path="$2"

  if [[ ! -d "$dir_path" ]]; then
    return
  fi

  while IFS= read -r -d '' file; do
    [[ -f "$file" ]] || continue
    _tests_ref+=("bash|$file")
  done < <(find "$dir_path" -type f -name "*.sh" -print0)
}

add_pytest_tests() {
  local -n _tests_ref=$1
  local dir_path="$2"
  local marker="$3"

  if [[ ! -d "$dir_path" ]]; then
    return
  fi

  _tests_ref+=("pytest|$dir_path|$marker")
}

discover_tests_recursive() {
  local -n arr=$1
  add_pytest_tests arr "${REPO_ROOT}/tests/unit" "unit"
  add_bash_tests arr "${REPO_ROOT}/tests/integration"
  add_pytest_tests arr "${REPO_ROOT}/tests/integration" "integration"
  add_bash_tests arr "${REPO_ROOT}/tests/e2e/phase1"
  add_bash_tests arr "${REPO_ROOT}/tests/e2e/phase2"
  add_bash_tests arr "${REPO_ROOT}/tests/e2e/specialists"
  add_pytest_tests arr "${REPO_ROOT}/tests/e2e" "e2e"
  add_pytest_tests arr "${REPO_ROOT}/tests/specialists" "specialists"
  add_bash_tests arr "${REPO_ROOT}/tests/services"
  add_pytest_tests arr "${REPO_ROOT}/tests/services" "services"
  add_bash_tests arr "${REPO_ROOT}/tests/specialists"
  add_bash_tests arr "${REPO_ROOT}/tests/performance"
}

filter_tests_by_component() {
  local -n arr=$1
  local component="${2,,}"
  local filtered=()
  for entry in "${arr[@]}"; do
    local lower_entry="${entry,,}"
    if [[ "${lower_entry}" == *"${component}"* ]]; then
      filtered+=("$entry")
    fi
  done
  arr=("${filtered[@]}")
}

discover_tests() {
  local -n results=$1
  results=()
  local type="${TEST_TYPE:-all}"
  local phase="${TEST_PHASE:-all}"

  case "$type" in
    unit)
      add_pytest_tests results "${REPO_ROOT}/tests/unit" "unit"
      ;;
    integration)
      add_bash_tests results "${REPO_ROOT}/tests/integration"
      add_pytest_tests results "${REPO_ROOT}/tests/integration" "integration"
      add_bash_tests results "${REPO_ROOT}/tests/services"
      add_bash_tests results "${REPO_ROOT}/tests/specialists"
      ;;
    e2e)
      if [[ "$phase" == "1" || "$phase" == "all" ]]; then
        add_bash_tests results "${REPO_ROOT}/tests/e2e/phase1"
      fi
      if [[ "$phase" == "2" || "$phase" == "all" ]]; then
        add_bash_tests results "${REPO_ROOT}/tests/e2e/phase2"
      fi
      add_bash_tests results "${REPO_ROOT}/tests/e2e/specialists"
      add_pytest_tests results "${REPO_ROOT}/tests/e2e" "e2e"
      ;;
    all)
      discover_tests_recursive results
      ;;
    *)
      log_warning "Tipo de teste desconhecido: $type";
      discover_tests_recursive results
      ;;
  esac

  if [[ -n "${TEST_COMPONENT:-}" ]]; then
    filter_tests_by_component results "$TEST_COMPONENT"
  fi
}

run_bash_test() {
  local test_script="$1"
  local timeout_val="${2:-${TEST_TIMEOUT:-${DEFAULT_TEST_TIMEOUT}}}"
  local test_name
  test_name=$(basename "$test_script" .sh)

  if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[dry-run] bash test: $test_script"
    return 0
  fi

  log_phase "Bash Test: $test_name"
  local start_time
  start_time=$(date +%s)
  local output
  local exit_code=0
  log_debug "Executing bash test with timeout ${timeout_val}s"
  if ! output=$(timeout_command "$timeout_val" bash "$test_script" 2>&1); then
    exit_code=$?
  fi
  local end_time
  end_time=$(date +%s)
  local duration
  duration=$((end_time - start_time))
  local artifact_file="${OUTPUT_DIR}/${test_name}-bash.log"
  printf "%s" "$output" > "$artifact_file"
  local status="passed"
  local details="Duration: ${duration}s"
  if [[ $exit_code -ne 0 ]]; then
    status="failed"
    TEST_FAILURE_COUNT=$((TEST_FAILURE_COUNT + 1))
    details="Duration: ${duration}s | Exit Code: ${exit_code}"
  fi
  add_test_result "bash:${test_name}" "$status" "$details" "$artifact_file"
}

run_pytest_tests() {
  local test_path="$1"
  local markers="$2"
  local suite_name
  suite_name=$(basename "$test_path")

  if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[dry-run] pytest suite: $test_path"
    return 0
  fi

  log_phase "Pytest Suite: $suite_name"
  ensure_output_dir "${OUTPUT_DIR}"
  local junit_file="${OUTPUT_DIR}/pytest-$(date +%s%N).xml"
  local pytest_args=("$test_path" "-v" "--tb=short" "--junit-xml=${junit_file}")
  if [[ -n "$markers" ]]; then
    pytest_args+=("-m" "$markers")
  fi
  if [[ "${COVERAGE:-false}" == "true" ]]; then
    ensure_output_dir "${OUTPUT_DIR}/coverage"
    pytest_args+=("--cov=services" "--cov=libraries" "--cov-report=html:${OUTPUT_DIR}/coverage" "--cov-report=xml:${OUTPUT_DIR}/coverage.xml")
    pytest_args+=("--cov-report=term-missing")
  fi
  if [[ "${PARALLEL:-false}" == "true" ]]; then
    pytest_args+=("-n" "${PARALLEL_JOBS:-4}")
  fi
  local status="passed"
  if ! pytest "${pytest_args[@]}"; then
    status="failed"
    TEST_FAILURE_COUNT=$((TEST_FAILURE_COUNT + 1))
  fi
  parse_junit_results "$junit_file" "$status"
}

parse_junit_results() {
  local junit_file="$1"
  local override_status="${2:-}"
  if [[ ! -f "$junit_file" ]]; then
    log_warning "JUnit XML não encontrado: $junit_file"
    add_test_result "pytest:junit" "failed" "Missing report" "$junit_file"
    return 1
  fi
  local summary
  summary=$(python - "$junit_file" <<'PY'
import sys
import xml.etree.ElementTree as ET
try:
    tree = ET.parse(sys.argv[1])
except ET.ParseError as exc:
    print("0 0 0")
    sys.exit(1)
root = tree.getroot()
tests = 0
failures = 0
errors = 0
for suite in root.iter('testsuite'):
    tests += int(suite.attrib.get('tests', 0))
    failures += int(suite.attrib.get('failures', 0))
    errors += int(suite.attrib.get('errors', 0))
if tests == 0 and root.tag == 'testsuite':
    tests = int(root.attrib.get('tests', 0))
    failures = int(root.attrib.get('failures', 0))
    errors = int(root.attrib.get('errors', 0))
print(tests, failures + errors, tests - (failures + errors))
PY
)
  local total failed passed
  read -r total failed passed <<< "$summary"
  total=${total:-0}
  failed=${failed:-0}
  passed=${passed:-0}
  TEST_CASES_TOTAL=$((TEST_CASES_TOTAL + total))
  TEST_CASES_FAILED=$((TEST_CASES_FAILED + failed))
  TEST_CASES_PASSED=$((TEST_CASES_PASSED + passed))
  local status="${override_status:-$( [[ $failed -gt 0 ]] && echo "failed" || echo "passed" )}"
  local details="Tests: ${total}, Failed: ${failed}, Passed: ${passed}"
  add_test_result "pytest:${junit_file##*/}" "$status" "$details" "$junit_file"
}

run_sequential_tests() {
  local tests=()
  tests+=("$@")
  for entry in "${tests[@]}"; do
    execute_test_entry "$entry"
  done
}

execute_test_entry() {
  local entry="$1"
  IFS='|' read -r entry_type entry_path entry_marker <<< "$entry"
  case "$entry_type" in
    bash)
      run_bash_test "$entry_path"
      ;;
    pytest)
      run_pytest_tests "$entry_path" "$entry_marker"
      ;;
    *)
      log_warning "Tipo de teste desconhecido na entrada: $entry"
      ;;
  esac
}

run_parallel_tests() {
  local tests=()
  tests+=("$@")
  local running=0
  local pids=()
  log_info "Running ${#tests[@]} tests in parallel (jobs: ${PARALLEL_JOBS:-4})"
  for entry in "${tests[@]}"; do
    while [[ $running -ge ${PARALLEL_JOBS:-4} ]]; do
      wait -n || true
      running=$((running - 1))
    done
    execute_test_entry "$entry" &
    pids+=("$!")
    running=$((running + 1))
  done
  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done
}

aggregate_test_results() {
  local tests_array="[]"
  if [[ -f "$TEST_RESULT_FILE" && -s "$TEST_RESULT_FILE" ]]; then
    tests_array=$(jq -s '.' "$TEST_RESULT_FILE" 2>/dev/null || echo "[]")
    # Garantir que tests_array é um array válido
    if ! jq -e 'type == "array"' <<< "$tests_array" >/dev/null 2>&1; then
      tests_array="[]"
    fi
  fi
  TEST_REPORT_JSON=$(jq -n \
    --argjson total_runs "$TEST_TOTAL_COUNT" \
    --argjson passed_runs "$TEST_PASSED_COUNT" \
    --argjson failed_runs "$TEST_FAILED_COUNT" \
    --argjson cases_total "$TEST_CASES_TOTAL" \
    --argjson cases_passed "$TEST_CASES_PASSED" \
    --argjson cases_failed "$TEST_CASES_FAILED" \
    --argjson tests "$tests_array" \
    '{summary: {runs: $total_runs, passed: $passed_runs, failed: $failed_runs, cases_total: $cases_total, cases_passed: $cases_passed, cases_failed: $cases_failed}, tests: $tests}')
}

generate_markdown_summary() {
  local destination="$1"
  if [[ -z "$TEST_REPORT_JSON" ]]; then
    log_warning "Nenhum resultado disponível para gerar resumo"
    return 1
  fi
  local summary
  summary=$(jq -r '.summary' <<< "$TEST_REPORT_JSON")
  local detail_lines
  detail_lines=$(jq -r '(.tests // [])[] | "- [" + .status + "] " + .name + ": " + .details' <<< "$TEST_REPORT_JSON")
  cat <<EOF > "$destination"
# Neural Hive-Mind Test Results

## Summary
- Total Runs: $(jq -r '.summary.runs' <<< "$TEST_REPORT_JSON")
- Passed Runs: $(jq -r '.summary.passed' <<< "$TEST_REPORT_JSON")
- Failed Runs: $(jq -r '.summary.failed' <<< "$TEST_REPORT_JSON")
- Test Cases: $(jq -r '.summary.cases_total' <<< "$TEST_REPORT_JSON")
- Passed Cases: $(jq -r '.summary.cases_passed' <<< "$TEST_REPORT_JSON")
- Failed Cases: $(jq -r '.summary.cases_failed' <<< "$TEST_REPORT_JSON")

## Details
$detail_lines
EOF
}

save_test_report() {
  local destination="$1"
  if [[ -z "$TEST_REPORT_JSON" ]]; then
    log_warning "Não há relatório para salvar"
    return 1
  fi
  printf "%s" "$TEST_REPORT_JSON" > "$destination"
}

generate_unified_report() {
  log_info "Generating unified test report"
  aggregate_test_results
  local timestamp
  timestamp=$(date +%Y%m%d-%H%M%S)
  local json_report="${OUTPUT_DIR}/test-report-${timestamp}.json"
  save_test_report "$json_report"
  local md_report="${OUTPUT_DIR}/test-summary-${timestamp}.md"
  generate_markdown_summary "$md_report"
  log_success "Reports generated:"
  log_info "  JSON: $json_report"
  log_info "  Markdown: $md_report"
  display_test_summary
}

display_test_summary() {
  if [[ -z "$TEST_REPORT_JSON" ]]; then
    log_warning "Nenhum resumo para exibir"
    return
  fi
  local total passed failed
  total=$(jq -r '.summary.runs' <<< "$TEST_REPORT_JSON")
  passed=$(jq -r '.summary.passed' <<< "$TEST_REPORT_JSON")
  failed=$(jq -r '.summary.failed' <<< "$TEST_REPORT_JSON")
  echo ""
  echo "=========================================="
  echo "Test Summary"
  echo "=========================================="
  echo "Total:  $total"
  echo "Passed: $passed"
  echo "Failed: $failed"
  echo "=========================================="
}

cleanup_test_resources() {
  log_info "Cleaning up test resources"
  cleanup_port_forwards || true
}

exit_with_test_status() {
  if [[ $TEST_FAILURE_COUNT -gt 0 ]]; then
    log_error "Detected ${TEST_FAILURE_COUNT} failing tests"
    exit 1
  fi
  log_success "All test runs completed successfully"
  exit 0
}
