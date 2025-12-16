#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/observability/stop-dashboards.sh"
echo "   Use: ./scripts/observability/stop-dashboards.sh"
exec "$(dirname "$0")/scripts/observability/stop-dashboards.sh" "$@"
