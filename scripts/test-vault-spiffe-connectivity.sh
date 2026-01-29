#!/usr/bin/env bash
# Runs end-to-end validation for Vault/SPIFFE connectivity and authentication.

set -euo pipefail

DRY_RUN=false
VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
SPIRE_NAMESPACE="${SPIRE_NAMESPACE:-spire-system}"
ORCH_NAMESPACE="${ORCH_NAMESPACE:-neural-hive-orchestration}"
EXEC_NAMESPACE="${EXEC_NAMESPACE:-neural-hive-execution}"
TRUST_DOMAIN="${TRUST_DOMAIN:-neural-hive.local}"

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
      *) log_warn "Ignoring unknown argument: $1" ;;
    esac
    shift || true
  done
}

get_first_pod() {
  local ns="$1" selector="$2"
  kubectl get pods -n "${ns}" -l "${selector}" -o jsonpath='{.items[0].metadata.name}'
}

check_vault_health() {
  log_info "Checking Vault status and Raft peers"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault status"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault operator raft list-peers"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault read pki/cert/ca"
}

check_spire_health() {
  log_info "Checking SPIRE server health and entries"
  run_cmd "kubectl exec -n '${SPIRE_NAMESPACE}' spire-server-0 -- spire-server healthcheck"
  run_cmd "kubectl exec -n '${SPIRE_NAMESPACE}' spire-server-0 -- spire-server entry show"
}

fetch_jwt_svid() {
  local pod
  pod="$(get_first_pod "${ORCH_NAMESPACE}" "app=orchestrator-dynamic")"
  log_info "Fetching JWT-SVID from pod ${pod}"
  run_cmd "kubectl exec -n '${ORCH_NAMESPACE}' '${pod}' -- \
    curl --unix-socket /run/spire/sockets/agent.sock \
    http://localhost/v1/spiffe/workload/jwt \
    -H 'Content-Type: application/json' \
    -d '{\"audience\": [\"vault.${TRUST_DOMAIN}\"]}'"
}

vault_login_with_jwt() {
  local pod
  pod="$(get_first_pod "${ORCH_NAMESPACE}" "app=orchestrator-dynamic")"
  log_info "Testing Vault login via Kubernetes auth from pod ${pod}"
  run_cmd "kubectl exec -n '${ORCH_NAMESPACE}' '${pod}' -- \
    vault write auth/kubernetes/login role=orchestrator-dynamic jwt=\$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
}

fetch_vault_secrets() {
  log_info "Fetching Vault secrets and dynamic credentials"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault kv get secret/orchestrator/mongodb"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault read database/creds/temporal-orchestrator"
}

run_e2e_tests() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping pytest execution"
    return
  fi
  log_info "Running E2E tests for Vault/SPIFFE integration"
  RUN_VAULT_SPIFFE_E2E=true run_cmd "cd '${ROOT_DIR:-.}' && pytest tests/e2e/test_vault_spiffe_integration_full.py -v"
  RUN_VAULT_SPIFFE_E2E=true run_cmd "cd '${ROOT_DIR:-.}' && pytest tests/e2e/test_spiffe_grpc_auth_e2e.py -v"
}

main() {
  parse_args "$@"
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  check_vault_health
  check_spire_health
  fetch_jwt_svid
  vault_login_with_jwt
  fetch_vault_secrets
  run_e2e_tests
  log_info "Vault/SPIFFE connectivity validation completed"
}

main "$@"
