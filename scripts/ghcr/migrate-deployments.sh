#!/bin/bash
#===============================================================================
# migrate-deployments.sh
# Migra todos os deployments do registry interno para GHCR
#===============================================================================

set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive}"
GHCR_PREFIX="ghcr.io/albinojimy/neural-hive-mind"
IMAGE_TAG="${IMAGE_TAG:-v1.1.0}"
DRY_RUN="${DRY_RUN:-false}"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Mapeamento de deployments para nomes de imagens no GHCR
# Alguns deployments podem ter nomes diferentes das imagens
declare -A SERVICE_MAP=(
    ["analyst-agents"]="analyst-agents"
    ["approval-service"]="approval-service"
    ["code-forge"]="code-forge"
    ["consensus-engine"]="consensus-engine"
    ["execution-ticket-service"]="execution-ticket-service"
    ["explainability-api"]="explainability-api"
    ["gateway-intencoes"]="gateway-intencoes"
    ["guard-agents"]="guard-agents"
    ["mcp-tool-catalog"]="mcp-tool-catalog"
    ["memory-layer-api"]="memory-layer-api"
    ["orchestrator-dynamic"]="orchestrator-dynamic"
    ["optimizer-agents"]="optimizer-agents"
    ["queen-agent"]="queen-agent"
    ["scout-agents"]="scout-agents"
    ["self-healing-engine"]="self-healing-engine"
    ["semantic-translation-engine"]="semantic-translation-engine"
    ["service-registry"]="service-registry"
    ["sla-management-system"]="sla-management-system"
    ["worker-agents"]="worker-agents"
)

echo "=============================================="
echo "Migrating deployments to GHCR"
echo "=============================================="
echo "Namespace: $NAMESPACE"
echo "GHCR Prefix: $GHCR_PREFIX"
echo "Image Tag: $IMAGE_TAG"
echo "Dry Run: $DRY_RUN"
echo ""

# Verificar se imagePullSecrets está configurado
if ! kubectl get deployment -n "$NAMESPACE" -o jsonpath='{.items[0].spec.template.spec.imagePullSecrets}' 2>/dev/null | grep -q "ghcr-secret"; then
    log_warn "imagePullSecrets may not be configured. Run this first:"
    echo "  for dep in \$(kubectl get deployments -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}'); do"
    echo "    kubectl patch deployment \"\$dep\" -n $NAMESPACE -p '{\"spec\":{\"template\":{\"spec\":{\"imagePullSecrets\":[{\"name\":\"ghcr-secret\"}]}}}}'"
    echo "  done"
    echo ""
fi

MIGRATED=0
FAILED=0
SKIPPED=0

for deployment in "${!SERVICE_MAP[@]}"; do
    image_name="${SERVICE_MAP[$deployment]}"
    new_image="${GHCR_PREFIX}/${image_name}:${IMAGE_TAG}"
    
    # Verificar se deployment existe
    if ! kubectl get deployment "$deployment" -n "$NAMESPACE" &>/dev/null; then
        log_warn "Deployment $deployment not found, skipping"
        ((SKIPPED++))
        continue
    fi
    
    # Obter imagem atual
    current_image=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)
    
    # Verificar se já está no GHCR
    if [[ "$current_image" == *"ghcr.io"* ]]; then
        log_info "$deployment already using GHCR: $current_image"
        ((SKIPPED++))
        continue
    fi
    
    log_info "Migrating $deployment:"
    echo "    From: $current_image"
    echo "    To:   $new_image"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "    [DRY RUN - not applied]"
    else
        # Obter nome do container principal
        container_name=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].name}')
        
        if kubectl set image "deployment/$deployment" "${container_name}=${new_image}" -n "$NAMESPACE" 2>/dev/null; then
            log_success "$deployment image updated"
            ((MIGRATED++))
        else
            log_error "Failed to update $deployment"
            ((FAILED++))
        fi
    fi
done

echo ""
echo "=============================================="
echo "Migration Summary"
echo "=============================================="
echo "Migrated: $MIGRATED"
echo "Skipped:  $SKIPPED"
echo "Failed:   $FAILED"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo "This was a dry run. To apply changes, run:"
    echo "  DRY_RUN=false IMAGE_TAG=$IMAGE_TAG $0"
fi
