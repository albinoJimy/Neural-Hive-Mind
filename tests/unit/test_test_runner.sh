#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/../lib/test-runner-lib.sh"

test_parse_args() {
  parse_test_args --type unit --phase 1 --component specialists
  [ "$TEST_TYPE" = "unit" ] || return 1
  [ "$TEST_PHASE" = "1" ] || return 1
  [ "$TEST_COMPONENT" = "specialists" ] || return 1
}

test_discover_tests() {
  local tests=()
  TEST_TYPE="unit"
  discover_tests tests
  [ ${#tests[@]} -gt 0 ] || return 1
}

if test_parse_args && echo "✓ test_parse_args passed" || echo "✗ test_parse_args failed"; then
  :
else
  exit 1
fi

test_discover_tests && echo "✓ test_discover_tests passed" || echo "✗ test_discover_tests failed"
