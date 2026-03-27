#!/bin/bash
echo "⚠️  DEPRECATED: Este script foi movido para scripts/build/import-to-containerd.sh"
echo "   Use: ./scripts/build/import-to-containerd.sh"
exec "$(dirname "$0")/scripts/build/import-to-containerd.sh" "$@"
