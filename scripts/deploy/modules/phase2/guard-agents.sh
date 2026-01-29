#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"

MODULE_NAME="guard-agents"
MODULE_DEPENDENCIES=("queen-agent")

validate_guard_agents() {
    log_info "Validando Guard Agents..."
    check_command_exists kubectl || return 1
    return 0
}

deploy_guard_agents() {
    local env="${1:-eks}"
    local dry_run="${2:-false}"
    log_phase "Guard Agents (${env})"

    validate_guard_agents || return 1

    local command="echo '[guard-agents] Deploy placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_guard_agents deploy_guard_agents
