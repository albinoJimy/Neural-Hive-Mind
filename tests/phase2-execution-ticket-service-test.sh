#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "⚠️  DEPRECATED: Este script foi movido para tests/e2e/phase2/execution-ticket-test.sh"
echo "   Use: ./tests/run-tests.sh --type e2e --phase 2"
exec "${SCRIPT_DIR}/e2e/phase2/execution-ticket-test.sh" "$@"
