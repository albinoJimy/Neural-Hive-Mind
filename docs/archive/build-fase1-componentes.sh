#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/build/phase1-components.sh"
echo "   Use: ./scripts/build/phase1-components.sh"
exec "$(dirname "$0")/scripts/build/phase1-components.sh" "$@"
