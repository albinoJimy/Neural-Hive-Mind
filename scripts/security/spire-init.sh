#!/bin/bash
# SPIRE/SPIRE Initialization Script for Neural Hive-Mind
#
# This script initializes SPIRE server and creates registration entries
# for all Neural Hive-Mind services.
#
# Usage: ./scripts/security/spire-init.sh [namespace]
#   namespace: Kubernetes namespace where SPIRE is deployed (default: spire)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
SPIRE_NAMESPACE="${1:-spire}"
SPIRE_SERVER_POD="spire-server-0"
TRUST_DOMAIN="neural-hive.local"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if SPIRE is ready
check_spire_ready() {
    log_info "Verificando se SPIRE server está pronto..."

    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if kubectl exec -n "$SPIRE_NAMESPACE" "$SPIRE_SERVER_POD" -- /opt/spire/bin/spire-server healthcheck 2>/dev/null; then
            log_info "SPIRE server está pronto"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    log_error "SPIRE server não está pronto após ${max_attempts} tentativas"
    return 1
}

# Create registration entries for services
create_registration_entries() {
    log_info "Criando entradas de registro para serviços..."

    # List of services with their selectors
    local services=(
        "app.kubernetes.io/name=gateway-intencoes:gateway-intencoes"
        "app.kubernetes.io/name=semantic-translation-engine:semantic-translation-engine"
        "app.kubernetes.io/name=consensus-engine:consensus-engine"
        "app.kubernetes.io/name=orchestrator-dynamic:orchestrator-dynamic"
        "app.kubernetes.io/name=approval-service:approval-service"
        "app.kubernetes.io/name=queen-agent:queen-agent"
        "app.kubernetes.io/name=worker-agents:worker-agents"
    )

    for entry in "${services[@]}"; do
        local selector="${entry%%:*}"
        local service_name="${entry##*:}"

        log_info "Registrando $service_name..."

        kubectl exec -n "$SPIRE_NAMESPACE" "$SPIRE_SERVER_POD" -- /opt/spire/bin/spire-server entry create \
            -spiffeID "spiffe://$TRUST_DOMAIN/neural-hive-system/$service_name" \
            -selector "$selector" \
            -parentID "spiffe://$TRUST_DOMAIN/spire/server" \
            -dnsNames "$service_name.neural-hive-system.svc.cluster.local" \
            -admin || log_warn "Entrada para $service_name já existe"
    done

    log_info "Entradas de registro criadas"
}

# Create registration entries for Vault
create_vault_entries() {
    log_info "Registrando Vault..."

    kubectl exec -n "$SPIRE_NAMESPACE" "$SPIRE_SERVER_POD" -- /opt/spire/bin/spire-server entry create \
        -spiffeID "spiffe://$TRUST_DOMAIN/vault/vault" \
        -selector "app.kubernetes.io/name=vault" \
        -parentID "spiffe://$TRUST_DOMAIN/spire/server" \
        -dnsNames "vault.vault.svc.cluster.local" \
        -admin || log_warn "Entrada para Vault já existe"
}

# Generate trust bundle
generate_trust_bundle() {
    log_info "Gerando bundle de confiança..."

    local bundle_file="$PROJECT_ROOT/.spire-bundle.pem"

    kubectl exec -n "$SPIRE_NAMESPACE" "$SPIRE_SERVER_POD" -- /opt/spire/bin/spire-server bundle show \
        -format pem > "$bundle_file" 2>/dev/null || true

    if [ -f "$bundle_file" ]; then
        log_info "Bundle salvo em: $bundle_file"
    fi
}

# Verify SPIRE agent is running
verify_agent() {
    log_info "Verificando SPIRE agents..."

    local pods
    pods=$(kubectl get pods -n "neural-hive-system" -l app.kubernetes.io/name=gateway-intencoes -o name 2>/dev/null || true)

    if [ -n "$pods" ]; then
        log_info "Pods encontrados. Verificando socket SPIRE..."

        local pod_name
        pod_name=$(echo "$pods" | head -1 | cut -d'/' -f2)

        if kubectl exec -n "neural-hive-system" "$pod_name" -- ls /run/spire/sockets/agent.sock 2>/dev/null; then
            log_info "Socket SPIRE encontrado em $pod_name"
        else
            log_warn "Socket SPIRE não encontrado em $pod_name"
            log_warn "Certifique-se de que o SPIRE agent daemonset está rodando"
        fi
    else
        log_warn "Nenhum pod encontrado em neural-hive-system namespace"
    fi
}

# Create registration job template
create_registration_job() {
    log_info "Criando job de registro SPIRE..."

    local job_file="$PROJECT_ROOT/helm-charts/spire/registration-job.yaml"

    # Check if file already exists
    if [ -f "$job_file" ]; then
        log_info "Job de registro já existe em $job_file"
        return
    fi

    # Note: The actual registration job is in the SPIRE Helm chart
    log_info "Job de registro está incluído no Helm chart SPIRE"
}

# Main execution
main() {
    log_info "=== Inicialização do SPIRE para Neural Hive-Mind ==="
    log_info "Namespace: $SPIRE_NAMESPACE"
    log_info "Trust Domain: $TRUST_DOMAIN"

    # Check prerequisites
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    # Check if SPIRE server exists
    if ! kubectl get pod -n "$SPIRE_NAMESPACE" "$SPIRE_SERVER_POD" &> /dev/null; then
        log_error "Pod $SPIRE_SERVER_POD não encontrado no namespace $SPIRE_NAMESPACE"
        log_error "Certifique-se de que o SPIRE está instalado: helm install spire helm-charts/spire"
        exit 1
    fi

    # Initialize SPIRE
    check_spire_ready || exit 1
    create_registration_entries
    create_vault_entries
    generate_trust_bundle
    create_registration_job
    verify_agent

    log_info "=== SPIRE inicializado com sucesso ==="
    log_info ""
    log_info "Para ativar Vault/SPIFFE nos serviços:"
    log_info "  helm upgrade gateway-intencoes helm-charts/gateway-intencoes \\"
    log_info "    --set config.security.vault.enabled=true \\"
    log_info "    --set config.security.spiffe.enabled=true"
    log_info ""
    log_info "Para verificar SVIDs:"
    log_info "  kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry show"
}

# Run main
main "$@"
