#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/deploy/phase1-missing.sh"
echo "   Use: ./scripts/deploy/phase1-missing.sh"
exec "$(dirname "$0")/scripts/deploy/phase1-missing.sh" "$@"
