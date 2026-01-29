#!/usr/bin/env bash
# Enables Vault and SPIFFE for service Helm releases and redeploys them.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DRY_RUN=false
VAULT_ADDR_VALUE="${VAULT_ADDR_VALUE:-http://vault.vault.svc.cluster.local:8200}"
SPIFFE_SOCKET_PATH="${SPIFFE_SOCKET_PATH:-unix:///run/spire/sockets/agent.sock}"

ORCH_NAMESPACE="${ORCH_NAMESPACE:-neural-hive-orchestration}"
EXEC_NAMESPACE="${EXEC_NAMESPACE:-neural-hive-execution}"

ORCH_HELM_CHART="${ORCH_HELM_CHART:-${ROOT_DIR}/helm-charts/orchestrator-dynamic}"
WORKER_HELM_CHART="${WORKER_HELM_CHART:-${ROOT_DIR}/helm-charts/worker-agents}"
REGISTRY_HELM_CHART="${REGISTRY_HELM_CHART:-${ROOT_DIR}/helm-charts/service-registry}"

log_info() { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
log_warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
log_error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; }

run_cmd() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    printf '[DRY-RUN] %s\n' "$*"
  else
    eval "$@"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=true ;;
      --vault-addr) VAULT_ADDR_VALUE="$2"; shift ;;
      --spiffe-socket) SPIFFE_SOCKET_PATH="$2"; shift ;;
      *) log_warn "Ignoring unknown argument: $1" ;;
    esac
    shift || true
  done
}

upgrade_release() {
  local release="$1" chart="$2" namespace="$3"
  log_info "Upgrading ${release} in namespace ${namespace} with Vault/SPIFFE enabled"
  run_cmd "helm upgrade '${release}' '${chart}' \
    --namespace '${namespace}' --create-namespace \
    --set vault.enabled=true \
    --set vault.address='${VAULT_ADDR_VALUE}' \
    --set spiffe.enabled=true \
    --set spiffe.socketPath='${SPIFFE_SOCKET_PATH}'"
}

check_logs() {
  local namespace="$1" selector="$2"
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping log validation for ${selector} in ${namespace}"
    return
  fi
  log_info "Validating startup logs for selector ${selector} in namespace ${namespace}"
  run_cmd "kubectl logs -n '${namespace}' -l '${selector}' --tail=50 | grep -E '(vault_client_initialized|spiffe_manager_initialized|vault_integration|spiffe)' || true"
}

main() {
  parse_args "$@"

  upgrade_release orchestrator-dynamic "${ORCH_HELM_CHART}" "${ORCH_NAMESPACE}"
  upgrade_release worker-agents "${WORKER_HELM_CHART}" "${EXEC_NAMESPACE}"
  upgrade_release service-registry "${REGISTRY_HELM_CHART}" "${ORCH_NAMESPACE}"

  check_logs "${ORCH_NAMESPACE}" "app=orchestrator-dynamic"
  check_logs "${EXEC_NAMESPACE}" "app=worker-agents"
  check_logs "${ORCH_NAMESPACE}" "app=service-registry"

  log_info "Vault/SPIFFE enablement for services completed"
}

main "$@"
