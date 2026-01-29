#!/usr/bin/env bash
# Validação automatizada da integração Vault/SPIFFE em produção.
# Nota: validação de autenticação gRPC (JWT-SVID) pode ser exercida via testes E2E
# `tests/e2e/test_spiffe_grpc_auth_e2e.py` e `tests/e2e/test_vault_spiffe_integration_full.py`
# executando, por exemplo: RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_spiffe_grpc_auth_e2e.py -v

set -euo pipefail

VAULT_ADDR=${VAULT_ADDR:-http://vault.vault.svc.cluster.local:8200}
SPIRE_NAMESPACE=${SPIRE_NAMESPACE:-spire-system}
SPIRE_AGENT_SOCKET=${SPIFFE_SOCKET_PATH:-/run/spire/sockets/agent.sock}
EXECUTION_TICKET_HOST=${EXECUTION_TICKET_HOST:-execution-ticket-service.neural-hive-execution.svc.cluster.local:50052}
SERVICE_REGISTRY_HOST=${SERVICE_REGISTRY_HOST:-service-registry.neural-hive-execution.svc.cluster.local:50051}

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*" >&2; }
error() { echo "[ERROR] $*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Comando obrigatório não encontrado: $1"
    exit 1
  fi
}

check_vault_health() {
  info "Verificando pods do Vault..."
  kubectl get pods -n vault || warn "Não foi possível listar pods do Vault"

  info "Verificando status de selagem..."
  vault status || warn "vault status falhou"
}

check_spire_health() {
  info "Verificando pods SPIRE..."
  kubectl get pods -n "${SPIRE_NAMESPACE}" || warn "Não foi possível listar pods SPIRE"

  info "Listando entries SPIRE..."
  kubectl exec -n "${SPIRE_NAMESPACE}" spire-server-0 -- spire-server entry show || warn "Falha ao listar entries"
}

test_vault_auth() {
  info "Testando autenticação Kubernetes no Vault..."
  if vault write auth/kubernetes/login role=orchestrator-dynamic jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token 2>/dev/null)" >/tmp/vault-login.json 2>/dev/null; then
    info "Autenticação Kubernetes bem-sucedida"
  else
    warn "Falha na autenticação Kubernetes - verifique role e service account"
  fi
}

test_secret_fetch() {
  info "Buscando segredos estáticos (MongoDB, Kafka, Redis)..."
  vault kv get -field=uri secret/orchestrator/mongodb || warn "MongoDB URI não encontrada"
  vault kv get -field=password secret/orchestrator/redis || warn "Senha Redis não encontrada"
  vault kv get secret/orchestrator/kafka || warn "Credenciais Kafka não encontradas"

  info "Gerando credenciais dinâmicas PostgreSQL..."
  vault read database/creds/temporal-orchestrator || warn "Falha ao gerar credenciais dinâmicas"
}

test_spiffe_jwt() {
  info "Testando acesso ao socket do SPIRE Agent (${SPIRE_AGENT_SOCKET})"
  if [[ ! -S "${SPIRE_AGENT_SOCKET#unix://}" && ! -S "${SPIRE_AGENT_SOCKET}" ]]; then
    warn "Socket SPIRE Agent não encontrado em ${SPIRE_AGENT_SOCKET}"
  fi
}

test_grpc_auth_calls() {
  info "Validando gRPC com JWT-SVID (usar testes E2E dedicados em ambiente seguro)..."
  info "Exemplo: RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_spiffe_grpc_auth_e2e.py -v"
  info "Exemplo: RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_vault_spiffe_integration_full.py -v"
}

main() {
  require_cmd kubectl
  require_cmd vault

  info "Iniciando validação Vault/SPIFFE"
  export VAULT_ADDR

  check_vault_health
  check_spire_health
  test_vault_auth
  test_secret_fetch
  test_spiffe_jwt
  test_grpc_auth_calls

  info "Validação concluída. Revise avisos acima para ações corretivas."
}

main "$@"
