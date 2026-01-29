#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"

MODULE_NAME="queen-agent"
MODULE_DEPENDENCIES=("workers")

validate_queen_agent() {
    log_info "Validando Queen Agent..."
    check_command_exists kubectl || return 1
    return 0
}

deploy_queen_agent() {
    local env="${1:-eks}"
    local dry_run="${2:-false}"
    log_phase "Queen Agent (${env})"

    validate_queen_agent || return 1

    local command="echo '[queen-agent] Deploy placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_queen_agent deploy_queen_agent
