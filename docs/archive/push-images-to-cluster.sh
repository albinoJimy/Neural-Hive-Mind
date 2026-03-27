#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/build/push-to-cluster.sh"
echo "   Use: ./scripts/build/push-to-cluster.sh"
exec "$(dirname "$0")/scripts/build/push-to-cluster.sh" "$@"
