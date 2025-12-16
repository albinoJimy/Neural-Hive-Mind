#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"
source "${LIB_DIR}/common.sh"

CLI_SCRIPT="${SCRIPT_DIR}/../deploy.sh"
DEFAULT_ARGS=(--env local --phase 1 --services specialists)

log_warning "⚠️  DEPRECATED: use './scripts/deploy.sh --env local --phase 1 --services specialists' instead"
log_info "Redirecionando para o novo CLI..."
exec "${CLI_SCRIPT}" "${DEFAULT_ARGS[@]}" "$@"
