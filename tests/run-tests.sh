#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${TESTS_DIR}/lib/test-runner-lib.sh"
source "${TESTS_DIR}/../scripts/helpers/test-helpers.sh"

# Default test runner flags
TEST_TYPE="all"
TEST_PHASE="all"
TEST_COMPONENT=""
COVERAGE=false
GENERATE_REPORT=true
PARALLEL=false
PARALLEL_JOBS=4
DRY_RUN=false
DEBUG=false
OUTPUT_DIR="${TESTS_DIR}/results"
TEST_TIMEOUT=${TEST_TIMEOUT:-600}

parse_test_args "$@"

main() {
  log_info "Neural Hive-Mind Test Runner"
  init_test_report "neural-hive-mind-tests"
  local tests_to_run=()
  discover_tests tests_to_run

  if [[ ${#tests_to_run[@]} -eq 0 ]]; then
    log_warning "Nenhum teste encontrado para o filtro solicitado"
    exit_with_test_status
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Dry-run mode enabled. Tests that would run:"
    for entry in "${tests_to_run[@]}"; do
      echo "  - $entry"
    done
    exit 0
  fi

  if [[ "$PARALLEL" == "true" ]]; then
    run_parallel_tests "${tests_to_run[@]}"
  else
    run_sequential_tests "${tests_to_run[@]}"
  fi

  if [[ "$GENERATE_REPORT" == "true" ]]; then
    generate_unified_report
  fi

  cleanup_test_resources
  exit_with_test_status
}

main "$@"
