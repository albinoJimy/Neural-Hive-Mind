#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"

MODULE_NAME="code-forge"
MODULE_DEPENDENCIES=("workers")

validate_code_forge() {
    log_info "Validando Code Forge..."
    check_command_exists kubectl || return 1
    return 0
}

deploy_code_forge() {
    local env="${1:-eks}"
    local dry_run="${2:-false}"
    log_phase "Code Forge (${env})"

    validate_code_forge || return 1

    local command="echo '[code-forge] Deploy placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_code_forge deploy_code_forge
