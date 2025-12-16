#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "⚠️  DEPRECATED: Este script foi movido para tests/integration/governance-compliance-test.sh"
echo "   Use: ./tests/run-tests.sh --type integration"
exec "${SCRIPT_DIR}/integration/governance-compliance-test.sh" "$@"
