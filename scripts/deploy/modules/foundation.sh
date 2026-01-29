#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"
source "${LIB_DIR}/aws.sh"

MODULE_NAME="foundation"
MODULE_DEPENDENCIES=()

validate_foundation() {
    log_info "Validando pré-requisitos da fundação..."
    check_command_exists terraform || return 1
    check_command_exists aws || return 1
    aws_check_credentials || return 1
    return 0
}

deploy_foundation() {
    local env="${1:-local}"
    local dry_run="${2:-false}"
    log_phase "Foundation (${env})"

    validate_foundation || return 1

    local command="echo '[foundation] Aplicando Terraform placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_foundation deploy_foundation
