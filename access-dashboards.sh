#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/observability/access-dashboards.sh"
echo "   Use: ./scripts/observability/access-dashboards.sh"
exec "$(dirname "$0")/scripts/observability/access-dashboards.sh" "$@"
