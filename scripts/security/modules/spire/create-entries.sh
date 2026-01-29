#!/usr/bin/env bash
# Cria registration entries no SPIRE para todos os serviços.

set -euo pipefail

SPIRE_NAMESPACE=${SPIRE_NAMESPACE:-spire-system}
SPIRE_SERVER_POD=${SPIRE_SERVER_POD:-spire-server-0}
TRUST_DOMAIN=${TRUST_DOMAIN:-neural-hive.local}

log() { echo "[spire-create-entries] $*"; }

run_spire() {
  kubectl exec -n "${SPIRE_NAMESPACE}" "${SPIRE_SERVER_POD}" -- spire-server "$@"
}

log "Criando entries SPIRE no domínio ${TRUST_DOMAIN}..."

run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/ns/neural-hive-orchestration/sa/orchestrator-dynamic" \
  -selector k8s_psat:cluster:neural-hive \
  -selector k8s_psat:agent_ns:neural-hive-orchestration \
  -selector k8s_psat:agent_sa:orchestrator-dynamic \
  -selector k8s_psat:pod-label:app:orchestrator-dynamic

run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/ns/neural-hive-execution/sa/worker-agents" \
  -selector k8s_psat:cluster:neural-hive \
  -selector k8s_psat:agent_ns:neural-hive-execution \
  -selector k8s_psat:agent_sa:worker-agents \
  -selector k8s_psat:pod-label:app:worker-agents

run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/ns/neural-hive-core/sa/service-registry" \
  -selector k8s_psat:cluster:neural-hive \
  -selector k8s_psat:agent_ns:neural-hive-core \
  -selector k8s_psat:agent_sa:service-registry \
  -selector k8s_psat:pod-label:app:service-registry

log "Entries criados. Verificando..."
run_spire entry show || log "Falha ao listar entries"
