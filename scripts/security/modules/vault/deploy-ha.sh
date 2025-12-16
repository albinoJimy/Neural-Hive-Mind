#!/usr/bin/env bash
# Automates Vault HA deployment wired to Terraform outputs and Helm values.
# Includes dry-run support, idempotent checks, and structured logging.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DRY_RUN=false
AWS_REGION="${AWS_REGION:-${TF_VAR_region:-us-east-1}}"
VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
TERRAFORM_DIR="${TERRAFORM_DIR:-${ROOT_DIR}/infrastructure/terraform}"
VAULT_HELM_CHART="${VAULT_HELM_CHART:-${ROOT_DIR}/helm-charts/vault}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/logs}"
VAULT_OUTPUT_FILE="${VAULT_OUTPUT_FILE:-${OUTPUT_DIR}/vault-ha-outputs.json}"
VAULT_INIT_SECRET_NAME="${VAULT_INIT_SECRET_NAME:-vault-init}"
VAULT_TLS_SECRET_NAME="${VAULT_TLS_SECRET_NAME:-vault-tls}"
AWS_PROFILE="${AWS_PROFILE:-default}"

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
  local tools=(terraform helm kubectl jq openssl aws)
  for tool in "${tools[@]}"; do
    command -v "${tool}" >/dev/null 2>&1 || { log_error "Required tool '${tool}' not found"; exit 1; }
  done
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=true ;;
      --region) AWS_REGION="$2"; shift ;;
      --namespace) VAULT_NAMESPACE="$2"; shift ;;
      --terraform-dir) TERRAFORM_DIR="$2"; shift ;;
      --helm-chart) VAULT_HELM_CHART="$2"; shift ;;
      --output-file) VAULT_OUTPUT_FILE="$2"; shift ;;
      *) log_warn "Ignoring unknown argument: $1" ;;
    esac
    shift || true
  done
}

terraform_apply_vault() {
  log_info "Applying Terraform module.vault-ha in ${TERRAFORM_DIR}"
  run_cmd "terraform -chdir='${TERRAFORM_DIR}' init -upgrade"
  run_cmd "terraform -chdir='${TERRAFORM_DIR}' apply -target=module.vault-ha -auto-approve"
}

capture_terraform_outputs() {
  mkdir -p "${OUTPUT_DIR}"
  log_info "Capturing Terraform outputs for vault-ha into ${VAULT_OUTPUT_FILE}"
  local tmp_out
  tmp_out="$(mktemp)"
  run_cmd "terraform -chdir='${TERRAFORM_DIR}' output -json > '${tmp_out}'"

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping output parsing"
    KMS_KEY_ID="${KMS_KEY_ID:-DRY_RUN_KMS_KEY}"
    VAULT_SERVER_ROLE_ARN="${VAULT_SERVER_ROLE_ARN:-DRY_RUN_ROLE_ARN}"
    AUDIT_LOGS_BUCKET_NAME="${AUDIT_LOGS_BUCKET_NAME:-DRY_RUN_BUCKET}"
    return
  fi

  KMS_KEY_ID="$(jq -r '.kms_key_id.value' "${tmp_out}")"
  VAULT_SERVER_ROLE_ARN="$(jq -r '.vault_server_role_arn.value' "${tmp_out}")"
  AUDIT_LOGS_BUCKET_NAME="$(jq -r '.audit_logs_bucket_name.value' "${tmp_out}")"

  for key in KMS_KEY_ID VAULT_SERVER_ROLE_ARN AUDIT_LOGS_BUCKET_NAME; do
    local val="${!key}"
    if [[ -z "${val}" || "${val}" == "null" ]]; then
      log_error "Terraform output ${key,,} is missing or null; ensure root outputs are exported"
      exit 1
    fi
  done

  jq -n --arg kms_key_id "${KMS_KEY_ID}" \
        --arg role_arn "${VAULT_SERVER_ROLE_ARN}" \
        --arg audit_bucket "${AUDIT_LOGS_BUCKET_NAME}" \
        --arg region "${AWS_REGION}" \
        '{kms_key_id:$kms_key_id, vault_server_role_arn:$role_arn, audit_logs_bucket_name:$audit_bucket, region:$region}' > "${VAULT_OUTPUT_FILE}"

  log_info "Captured kms_key_id=${KMS_KEY_ID}, role_arn=${VAULT_SERVER_ROLE_ARN}, audit_bucket=${AUDIT_LOGS_BUCKET_NAME}"
}

generate_tls_certs() {
  log_info "Generating self-signed TLS certificates for Vault"
  local tmpdir crt key ca
  tmpdir="$(mktemp -d)"
  crt="${tmpdir}/vault.crt"
  key="${tmpdir}/vault.key"
  ca="${tmpdir}/ca.crt"

  run_cmd "openssl req -x509 -newkey rsa:4096 -nodes -keyout '${key}' -out '${crt}' -days 365 -subj '/CN=vault.${VAULT_NAMESPACE}.svc' -addext 'subjectAltName=DNS:vault.${VAULT_NAMESPACE}.svc,DNS:vault.${VAULT_NAMESPACE}.svc.cluster.local'"
  run_cmd "cp '${crt}' '${ca}'"
  run_cmd "openssl verify -CAfile '${ca}' '${crt}'"

  log_info "Creating/updating Kubernetes TLS secret ${VAULT_TLS_SECRET_NAME} in namespace ${VAULT_NAMESPACE}"
  run_cmd "kubectl create namespace '${VAULT_NAMESPACE}' --dry-run=client -o yaml | kubectl apply -f -"
  run_cmd "kubectl create secret tls '${VAULT_TLS_SECRET_NAME}' --cert='${crt}' --key='${key}' -n '${VAULT_NAMESPACE}' --dry-run=client -o yaml | kubectl apply -f -"
}

deploy_vault_helm() {
  if [[ -z "${KMS_KEY_ID:-}" || -z "${VAULT_SERVER_ROLE_ARN:-}" ]]; then
    log_error "KMS_KEY_ID and VAULT_SERVER_ROLE_ARN must be set from Terraform outputs"
    exit 1
  fi

  log_info "Deploying Vault Helm chart from ${VAULT_HELM_CHART}"
  run_cmd "helm upgrade --install vault '${VAULT_HELM_CHART}' \
    --namespace '${VAULT_NAMESPACE}' --create-namespace \
    --set server.serviceAccount.annotations.\"eks\\.amazonaws\\.com/role-arn\"='${VAULT_SERVER_ROLE_ARN}' \
    --set server.ha.raft.config.seal.enabled=true \
    --set server.ha.raft.config.seal.kms_key_id='${KMS_KEY_ID}' \
    --set server.ha.raft.config.seal.region='${AWS_REGION}'"

  log_info "Waiting for Vault pods to become Ready"
  run_cmd "kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=vault -n '${VAULT_NAMESPACE}' --timeout=300s"
}

vault_initialized() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "false"
    return
  fi
  local status_json
  status_json="$(kubectl exec -n "${VAULT_NAMESPACE}" vault-0 -- vault status -format=json 2>/dev/null || true)"
  if [[ -z "${status_json}" ]]; then
    echo "false"
    return
  fi
  jq -r '.initialized' <<<"${status_json}"
}

init_and_unseal_vault() {
  if [[ "$(vault_initialized)" == "true" ]]; then
    log_info "Vault already initialized; skipping operator init"
    return
  fi

  log_info "Initializing Vault cluster (5 key shares, threshold 3)"
  local init_file
  init_file="$(mktemp)"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault operator init -key-shares=5 -key-threshold=3 -format=json > '${init_file}'"

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping secret storage and unseal"
    return
  fi

  mkdir -p "${OUTPUT_DIR}"
  cp "${init_file}" "${OUTPUT_DIR}/vault-init.json"
  export VAULT_ROOT_TOKEN
  VAULT_ROOT_TOKEN="$(jq -r '.root_token' "${init_file}")"
  mapfile -t UNSEAL_KEYS < <(jq -r '.unseal_keys_hex[]' "${init_file}")

  log_info "Storing vault-init payload in AWS Secrets Manager secret ${VAULT_INIT_SECRET_NAME}"
  if aws --profile "${AWS_PROFILE}" secretsmanager describe-secret --secret-id "${VAULT_INIT_SECRET_NAME}" >/dev/null 2>&1; then
    run_cmd "aws --profile '${AWS_PROFILE}' secretsmanager put-secret-value --secret-id '${VAULT_INIT_SECRET_NAME}' --secret-string file://'${init_file}'"
  else
    run_cmd "aws --profile '${AWS_PROFILE}' secretsmanager create-secret --name '${VAULT_INIT_SECRET_NAME}' --secret-string file://'${init_file}'"
  fi

  log_info "Unsealing Vault pods with threshold keys"
  for pod in vault-0 vault-1 vault-2; do
    for i in {0..2}; do
      run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' ${pod} -- vault operator unseal '${UNSEAL_KEYS[$i]}'"
    done
  done

  log_info "Validating Vault status"
  run_cmd "kubectl exec -n '${VAULT_NAMESPACE}' vault-0 -- vault status"
}

configure_pki_and_policies() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "Dry-run: skipping PKI/policy configuration"
    return
  fi

  log_info "Port-forwarding Vault service for PKI and policy configuration"
  kubectl port-forward -n "${VAULT_NAMESPACE}" svc/vault 8200:8200 >/tmp/vault-port-forward.log 2>&1 &
  local pf_pid=$!
  trap 'kill ${pf_pid} >/dev/null 2>&1 || true' EXIT
  sleep 5

  export VAULT_ADDR="http://127.0.0.1:8200"
  export VAULT_TOKEN="${VAULT_ROOT_TOKEN:-}"

  log_info "Running PKI initialization script"
  run_cmd "VAULT_ADDR='${VAULT_ADDR}' VAULT_TOKEN='${VAULT_TOKEN}' '${ROOT_DIR}/scripts/vault-init-pki.sh'"

  log_info "Running policy configuration script"
  run_cmd "VAULT_ADDR='${VAULT_ADDR}' VAULT_TOKEN='${VAULT_TOKEN}' '${ROOT_DIR}/scripts/vault-configure-policies.sh'"

  log_info "Policies available:"
  run_cmd "VAULT_ADDR='${VAULT_ADDR}' VAULT_TOKEN='${VAULT_TOKEN}' vault policy list"
}

main() {
  parse_args "$@"
  ensure_tools
  terraform_apply_vault
  capture_terraform_outputs
  generate_tls_certs
  deploy_vault_helm
  init_and_unseal_vault
  configure_pki_and_policies
  log_info "Vault HA deployment completed"
}

main "$@"
