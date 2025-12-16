#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"

MODULE_NAME="observability"
MODULE_DEPENDENCIES=("foundation")

validate_observability() {
    log_info "Validando pilha de observabilidade..."
    check_command_exists kubectl || return 1
    check_command_exists helm || return 1
    return 0
}

deploy_observability() {
    local env="${1:-eks}"
    local dry_run="${2:-false}"
    log_phase "Observability (${env})"

    validate_observability || return 1

    local command="echo '[observability] Deployando Prometheus/Grafana/Jaeger placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_observability deploy_observability
