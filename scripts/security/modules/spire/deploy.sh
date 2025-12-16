#!/usr/bin/env bash
# Automates SPIRE deployment with Terraform-backed datastore and Helm installation.
# Includes dry-run support, idempotent secret creation, and workload registration.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DRY_RUN=false
AWS_REGION="${AWS_REGION:-${TF_VAR_region:-us-east-1}}"
SPIRE_NAMESPACE="${SPIRE_NAMESPACE:-spire-system}"
TERRAFORM_DIR="${TERRAFORM_DIR:-${ROOT_DIR}/infrastructure/terraform}"
SPIRE_HELM_CHART="${SPIRE_HELM_CHART:-${ROOT_DIR}/helm-charts/spire}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/logs}"
SPIRE_OUTPUT_FILE="${SPIRE_OUTPUT_FILE:-${OUTPUT_DIR}/spire-datastore-outputs.json}"
SPIRE_DB_SECRET_NAME="${SPIRE_DB_SECRET_NAME:-spire-database-secret}"
USE_EXTERNAL_SECRETS="${USE_EXTERNAL_SECRETS:-false}"
TRUST_DOMAIN="${TRUST_DOMAIN:-neural-hive.local}"
CLUSTER_NAME="${CLUSTER_NAME:-neural-hive}"
SECRET_STORE_KIND="${SECRET_STORE_KIND:-ClusterSecretStore}"

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

ensure_tools() {
  local tools=(terraform helm kubectl jq aws)
  for tool in "${tools[@]}"; do
    command -v "${tool}" >/dev/null 2>&1 || { log_error "Required tool '${tool}' not found"; exit 1; }
  done
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=true ;;
      --namespace) SPIRE_NAMESPACE="$2"; shift ;;
      --region) AWS_REGION="$2"; shift ;;
      --terraform-dir) TERRAFORM_DIR="$2"; shift ;;
      --helm-chart) SPIRE_HELM_CHART="$2"; shift ;;
      --output-file) SPIRE_OUTPUT_FILE="$2"; shift ;;
      --use-external-secrets) USE_EXTERNAL_SECRETS=true ;;
      *) log_warn "Ignoring unknown argument: $1" ;;
    esac
    shift || true
  done
}

terraform_apply_spire() {
  log_info "Applying Terraform module.spire-datastore in ${TERRAFORM_DIR}"
  run_cmd "terraform -chdir='${TERRAFORM_DIR}' init -upgrade"
  run_cmd "terraform -chdir='${TERRAFORM_DIR}' apply -target=module.spire-datastore -auto-approve"
}

capture_spire_outputs() {
  mkdir -p "${OUTPUT_DIR}"
  log_info "Capturing Terraform outputs for spire-datastore into ${SPIRE_OUTPUT_FILE}"
  local tmp_out
  tmp_out="$(mktemp)"
  run_cmd "terraform -chdir='${TERRAFORM_DIR}' output -json > '${tmp_out}'"

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping output parsing"
    CONNECTION_STRING="${CONNECTION_STRING:-DRY_RUN_CONNECTION_STRING}"
    SECRET_ARN="${SECRET_ARN:-DRY_RUN_SECRET_ARN}"
    SECRET_NAME="${SECRET_NAME:-DRY_RUN_SECRET_NAME}"
    return
  fi

  CONNECTION_STRING="$(jq -r '.connection_string.value' "${tmp_out}")"
  SECRET_ARN="$(jq -r '.secret_arn.value' "${tmp_out}")"
  SECRET_NAME="$(jq -r '.secret_name.value' "${tmp_out}")"

  for key in CONNECTION_STRING SECRET_ARN SECRET_NAME; do
    local val="${!key}"
    if [[ -z "${val}" || "${val}" == "null" ]]; then
      log_error "Terraform output ${key,,} is missing or null; ensure root outputs are exported"
      exit 1
    fi
  done

  jq -n --arg connection_string "${CONNECTION_STRING}" \
        --arg secret_arn "${SECRET_ARN}" \
        --arg secret_name "${SECRET_NAME}" \
        --arg region "${AWS_REGION}" \
        '{connection_string:$connection_string, secret_arn:$secret_arn, secret_name:$secret_name, region:$region}' > "${SPIRE_OUTPUT_FILE}"

  log_info "Captured connection_string and secret metadata (secret_name=${SECRET_NAME})"
}

validate_rds_connectivity() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping RDS connectivity check"
    return
  fi
  if ! command -v psql >/dev/null 2>&1; then
    log_warn "psql not found; skipping connectivity check"
    return
  fi
  log_info "Validating RDS connectivity with psql"
  PGPASSWORD='' run_cmd "psql '${CONNECTION_STRING}' -c 'SELECT 1;'"
}

create_db_secret() {
  run_cmd "kubectl create namespace '${SPIRE_NAMESPACE}' --dry-run=client -o yaml | kubectl apply -f -"

  if [[ "${USE_EXTERNAL_SECRETS}" == "true" ]]; then
    log_info "Creating ExternalSecret for SPIRE datastore (secret ${SECRET_NAME}) using ${SECRET_STORE_KIND}/aws-secrets-manager"
    cat <<EOF | run_cmd "kubectl apply -f -"
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ${SPIRE_DB_SECRET_NAME}
  namespace: ${SPIRE_NAMESPACE}
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ${SECRET_STORE_KIND}
    name: aws-secrets-manager
  target:
    name: ${SPIRE_DB_SECRET_NAME}
  data:
    - secretKey: connection-string
      remoteRef:
        key: ${SECRET_NAME}
        property: connection_string
EOF
  else
    log_info "Creating Kubernetes secret ${SPIRE_DB_SECRET_NAME} with connection string"
    run_cmd "kubectl create secret generic '${SPIRE_DB_SECRET_NAME}' --from-literal=connection-string='${CONNECTION_STRING}' -n '${SPIRE_NAMESPACE}' --dry-run=client -o yaml | kubectl apply -f -"
  fi

  if [[ "${DRY_RUN}" != "true" ]]; then
    log_info "Validating secret content"
    run_cmd "kubectl get secret '${SPIRE_DB_SECRET_NAME}' -n '${SPIRE_NAMESPACE}' -o jsonpath='{.data.connection-string}' | base64 -d"
  fi
}

deploy_spire_helm() {
  log_info "Deploying SPIRE Helm chart from ${SPIRE_HELM_CHART}"
  run_cmd "helm upgrade --install spire '${SPIRE_HELM_CHART}' \
    --namespace '${SPIRE_NAMESPACE}' --create-namespace \
    --set server.datastore.sql.connectionStringSecret.enabled=true \
    --set server.datastore.sql.connectionStringSecret.name='${SPIRE_DB_SECRET_NAME}' \
    --set global.trustDomain='${TRUST_DOMAIN}' \
    --set server.nodeAttestor.k8sPsat.cluster='${CLUSTER_NAME}'"

  log_info "Waiting for SPIRE Server pods"
  run_cmd "kubectl wait --for=condition=Ready pod -l app=spire-server -n '${SPIRE_NAMESPACE}' --timeout=300s"
  log_info "Waiting for SPIRE Agent pods"
  run_cmd "kubectl wait --for=condition=Ready pod -l app=spire-agent -n '${SPIRE_NAMESPACE}' --timeout=300s"
}

register_workloads() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping workload registration"
    return
  fi
  log_info "Registering workload entries via spire-register-entries.sh"
  run_cmd "'${ROOT_DIR}/scripts/spire-register-entries.sh'"
  log_info "Current entries:"
  run_cmd "kubectl exec -n '${SPIRE_NAMESPACE}' spire-server-0 -- spire-server entry show"
}

validate_spire_health() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping health validation"
    return
  fi
  log_info "Running SPIRE server healthcheck"
  run_cmd "kubectl exec -n '${SPIRE_NAMESPACE}' spire-server-0 -- spire-server healthcheck"
  log_info "Validating agent sockets presence"
  run_cmd "kubectl exec -n neural-hive-orchestration \$(kubectl get pods -n neural-hive-orchestration -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}') -- ls -la /run/spire/sockets/agent.sock"
}

main() {
  parse_args "$@"
  ensure_tools
  terraform_apply_spire
  capture_spire_outputs
  validate_rds_connectivity
  create_db_secret
  deploy_spire_helm
  register_workloads
  validate_spire_health
  log_info "SPIRE deployment completed"
}

main "$@"
