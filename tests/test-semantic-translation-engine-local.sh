#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "⚠️  DEPRECATED: Este script foi movido para tests/services/semantic-translation-engine-test.sh"
echo "   Use: ./tests/run-tests.sh --component semantic-translation-engine"
exec "${SCRIPT_DIR}/services/semantic-translation-engine-test.sh" "$@"
