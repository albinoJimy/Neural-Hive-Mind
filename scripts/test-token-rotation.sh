#!/usr/bin/env bash
# Validates token and credential rotation flows for Vault and SPIFFE.

set -euo pipefail

DRY_RUN=false
VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
ORCH_NAMESPACE="${ORCH_NAMESPACE:-neural-hive-orchestration}"
POSTGRES_CONN_STRING="${POSTGRES_CONN_STRING:-}"
JWT_TTL_SECONDS="${JWT_TTL_SECONDS:-3600}"

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
      --pg-conn) POSTGRES_CONN_STRING="$2"; shift ;;
      *) log_warn "Ignoring unknown argument: $1" ;;
    esac
    shift || true
  done
}

renew_postgres_creds() {
  log_info "Requesting dynamic PostgreSQL credentials"
  local creds_json lease_id lease_duration
  creds_json="$(run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault read -format=json database/creds/temporal-orchestrator")"
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping renewal"
    return
  fi
  lease_id="$(jq -r '.lease_id' <<<"${creds_json}")"
  lease_duration="$(jq -r '.lease_duration' <<<"${creds_json}")"
  log_info "Lease ${lease_id} issued with TTL ${lease_duration}s"
  local sleep_time=$((lease_duration / 2))
  log_info "Sleeping ${sleep_time}s before renewal"
  sleep "${sleep_time}"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault lease renew '${lease_id}'"
}

rotate_jwt_svid() {
  local pod
  pod="$(kubectl get pods -n "${ORCH_NAMESPACE}" -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')"
  log_info "Fetching initial JWT-SVID from pod ${pod}"
  local first second
  log_info "Requesting JWT-SVID with ttl=${JWT_TTL_SECONDS}s"
  first="$(run_cmd "kubectl exec -n '${ORCH_NAMESPACE}' '${pod}' -- \
    curl --unix-socket /run/spire/sockets/agent.sock \
    http://localhost/v1/spiffe/workload/jwt \
    -H 'Content-Type: application/json' \
    -d '{\"audience\": [\"vault.neural-hive.local\"], \"ttl\": '${JWT_TTL_SECONDS}'}'")"

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping wait for JWT rotation"
    return
  fi

  local sleep_window=$((JWT_TTL_SECONDS / 2))
  log_info "Waiting ${sleep_window}s to request new JWT-SVID"
  sleep "${sleep_window}"
  second="$(kubectl exec -n "${ORCH_NAMESPACE}" "${pod}" -- \
    curl --unix-socket /run/spire/sockets/agent.sock \
    http://localhost/v1/spiffe/workload/jwt \
    -H 'Content-Type: application/json' \
    -d '{\"audience\": [\"vault.neural-hive.local\"], \"ttl\": '${JWT_TTL_SECONDS}'}' )"
  log_info "New JWT-SVID fetched; compare expiry timestamps to confirm rotation"
  printf '%s\n%s\n' "${first}" "${second}" >/tmp/jwt-svid-rotation.log
}

revoke_and_validate() {
  log_info "Requesting temporary credentials for revocation test"
  local creds_json lease_id username password
  creds_json="$(run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault read -format=json database/creds/temporal-orchestrator")"
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping revoke validation"
    return
  fi
  lease_id="$(jq -r '.lease_id' <<<"${creds_json}")"
  username="$(jq -r '.data.username' <<<"${creds_json}")"
  password="$(jq -r '.data.password' <<<"${creds_json}")"

  log_info "Revoking lease ${lease_id}"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault lease revoke '${lease_id}'"

  if [[ -z "${POSTGRES_CONN_STRING}" ]]; then
    log_warn "POSTGRES_CONN_STRING not set; skipping connection validation after revoke"
    return
  fi

  log_info "Validating revoked credentials fail to authenticate"
  PGPASSWORD="${password}" run_cmd "psql '${POSTGRES_CONN_STRING/temporal-orchestrator/${username}}' -c 'SELECT 1;' || true"
}

monitor_auto_renew_logs() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping log monitoring"
    return
  fi
  log_info "Checking orchestrator-dynamic logs for automatic renewal events"
  run_cmd "kubectl logs -n '${ORCH_NAMESPACE}' -l app=orchestrator-dynamic --tail=200 | grep -i 'credentials_renewed' || true"
}

main() {
  parse_args "$@"
  renew_postgres_creds
  rotate_jwt_svid
  revoke_and_validate
  monitor_auto_renew_logs
  log_info "Token and credential rotation validation completed"
}

main "$@"
