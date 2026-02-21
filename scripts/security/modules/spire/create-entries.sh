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

# Create node alias first (used as parentID for workload entries)
log "Creating node alias: spiffe://${TRUST_DOMAIN}/cluster/neural-hive"
run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/cluster/neural-hive" \
  -selector k8s_psat:cluster:neural-hive \
  -node || log "Node alias already exists"

run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/ns/neural-hive-orchestration/sa/orchestrator-dynamic" \
  -parentID "spiffe://${TRUST_DOMAIN}/cluster/neural-hive" \
  -selector k8s:ns:neural-hive-orchestration \
  -selector k8s:sa:orchestrator-dynamic \
  -selector k8s:pod-label:app:orchestrator-dynamic

run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/ns/neural-hive-execution/sa/worker-agents" \
  -parentID "spiffe://${TRUST_DOMAIN}/cluster/neural-hive" \
  -selector k8s:ns:neural-hive-execution \
  -selector k8s:sa:worker-agents \
  -selector k8s:pod-label:app:worker-agents

run_spire entry create \
  -spiffeID "spiffe://${TRUST_DOMAIN}/ns/neural-hive-core/sa/service-registry" \
  -parentID "spiffe://${TRUST_DOMAIN}/cluster/neural-hive" \
  -selector k8s:ns:neural-hive-core \
  -selector k8s:sa:service-registry \
  -selector k8s:pod-label:app:service-registry

log "Entries criados. Verificando..."
run_spire entry show || log "Falha ao listar entries"
