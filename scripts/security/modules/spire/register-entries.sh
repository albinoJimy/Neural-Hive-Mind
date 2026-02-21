#!/bin/bash
# Script para criar registration entries SPIRE
set -euo pipefail

SPIRE_NAMESPACE="${SPIRE_NAMESPACE:-spire-system}"
SPIRE_SERVER_POD="spire-server-0"
TRUST_DOMAIN="neural-hive.local"

log_info() { echo "[INFO] $1"; }
log_error() { echo "[ERROR] $1" >&2; }

# Criar entry para orchestrator-dynamic
create_orchestrator_entry() {
    log_info "Criando SPIRE entry para orchestrator-dynamic..."

    kubectl exec -n $SPIRE_NAMESPACE $SPIRE_SERVER_POD -- \
        /opt/spire/bin/spire-server entry create \
        -spiffeID spiffe://$TRUST_DOMAIN/ns/neural-hive-orchestration/sa/orchestrator-dynamic \
        -parentID spiffe://$TRUST_DOMAIN/cluster/neural-hive \
        -selector k8s:ns:neural-hive-orchestration \
        -selector k8s:sa:orchestrator-dynamic \
        -selector k8s:pod-label:app:orchestrator-dynamic \
        -dns orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local \
        -ttl 3600 || log_error "Entry já existe ou falhou"
}

# Criar entry para worker-agents
create_worker_entry() {
    log_info "Criando SPIRE entry para worker-agents..."

    kubectl exec -n $SPIRE_NAMESPACE $SPIRE_SERVER_POD -- \
        /opt/spire/bin/spire-server entry create \
        -spiffeID spiffe://$TRUST_DOMAIN/ns/neural-hive-execution/sa/worker-agents \
        -parentID spiffe://$TRUST_DOMAIN/cluster/neural-hive \
        -selector k8s:ns:neural-hive-execution \
        -selector k8s:sa:worker-agents \
        -selector k8s:pod-label:app:worker-agents \
        -dns worker-agents.neural-hive-execution.svc.cluster.local \
        -ttl 3600 || log_error "Entry já existe ou falhou"
}

# Criar entry para service-registry
create_registry_entry() {
    log_info "Criando SPIRE entry para service-registry..."

    kubectl exec -n $SPIRE_NAMESPACE $SPIRE_SERVER_POD -- \
        /opt/spire/bin/spire-server entry create \
        -spiffeID spiffe://$TRUST_DOMAIN/ns/neural-hive-core/sa/service-registry \
        -parentID spiffe://$TRUST_DOMAIN/cluster/neural-hive \
        -selector k8s:ns:neural-hive-core \
        -selector k8s:sa:service-registry \
        -selector k8s:pod-label:app:service-registry \
        -dns service-registry.neural-hive-core.svc.cluster.local \
        -ttl 3600 || log_error "Entry já existe ou falhou"
}

# Listar todos os entries
list_entries() {
    log_info "Listando todos os SPIRE entries..."
    kubectl exec -n $SPIRE_NAMESPACE $SPIRE_SERVER_POD -- \
        /opt/spire/bin/spire-server entry show
}

main() {
    log_info "Criando SPIRE registration entries..."

    create_orchestrator_entry
    create_worker_entry
    create_registry_entry

    log_info "Registro completo!"
    list_entries
}

main "$@"
