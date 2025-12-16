#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"

MODULE_NAME="orchestrator"
MODULE_DEPENDENCIES=("infrastructure")

validate_orchestrator() {
    log_info "Validando Orchestrator..."
    check_command_exists kubectl || return 1
    return 0
}

deploy_orchestrator() {
    local env="${1:-eks}"
    local dry_run="${2:-false}"
    log_phase "Orchestrator (${env})"

    validate_orchestrator || return 1

    local command="echo '[orchestrator] Deploy placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_orchestrator deploy_orchestrator
