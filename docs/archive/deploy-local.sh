#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/deploy/local.sh"
echo "   Use: ./scripts/deploy/local.sh"
exec "$(dirname "$0")/scripts/deploy/local.sh" "$@"
