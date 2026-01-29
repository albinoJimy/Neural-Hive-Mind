#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"
PROJECT_ROOT="$(cd "${LIB_DIR}/.." && pwd)"

source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/k8s.sh"
source "${LIB_DIR}/aws.sh"

MODULE_NAME="security"
MODULE_DEPENDENCIES=("foundation" "infrastructure")

validate_security() {
    log_info "Validando componentes de segurança..."
    check_command_exists kubectl || return 1
    check_command_exists helm || return 1
    check_command_exists aws || return 1
    aws_check_credentials || return 1
    return 0
}

deploy_security() {
    local env="${1:-eks}"
    local dry_run="${2:-false}"
    log_phase "Security Stack (${env})"

    validate_security || return 1

    local command="echo '[security] Implantando Istio/OPA/Sigstore placeholder para ${env}'"
    execute_deploy_command "${command}" "${dry_run}"
    return $?
}

export -f validate_security deploy_security
