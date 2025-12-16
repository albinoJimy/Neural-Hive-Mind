#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"

MODULE_NAME="memory"
MODULE_DEPENDENCIES=("infrastructure")

validate_memory() {
    log_info "Validando camada de memória..."
    check_command_exists kubectl || return 1
    return 0
}

deploy_memory() {
    local env="${1:-local}"
    local dry_run="${2:-false}"
    log_phase "Memory Layer (${env})"

    validate_memory || return 1

    local command="echo '[memory] Deploy placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_memory deploy_memory
