#!/usr/bin/env bash
# =============================================================================
# DEPRECATED: Use './scripts/security.sh secrets create --phase 2' instead
# =============================================================================
# Este script foi consolidado no CLI unificado de segurança.
# Mantido apenas para retrocompatibilidade.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================" >&2
echo "DEPRECATED: Este script foi descontinuado." >&2
echo "Use: ./scripts/security.sh secrets create --phase 2" >&2
echo "Redirecionando para o novo CLI..." >&2
echo "============================================================" >&2

exec "${SCRIPT_DIR}/security.sh" secrets create --phase 2 "$@"
