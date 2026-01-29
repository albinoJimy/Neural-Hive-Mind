#!/bin/bash
# ============================================================================
# ⚠️  DEPRECATION WARNING
# ============================================================================
# Este script está deprecated e será removido em versão futura.
# Use o novo CLI unificado: ./scripts/build.sh
#
# Equivalência:
#   ./scripts/build-local-parallel.sh --version 1.0.8
#   → ./scripts/build.sh --target local --version 1.0.8
#
#   ./scripts/push-to-ecr.sh --version 1.0.8
#   → ./scripts/build.sh --target ecr --version 1.0.8
# ============================================================================

echo ""
echo "⚠️  AVISO: Este script está deprecated"
echo "   Use: ./scripts/build.sh --target <local|ecr|registry|all>"
echo "   Documentação: ./scripts/build.sh --help"
echo ""
sleep 2

#===============================================================================
# Script: build-and-push-to-registry.sh
# Description: Build images locally and push to private registry
# Usage: ./build-and-push-to-registry.sh [SERVICE_NAME|all] [TAG]
#===============================================================================

set -euo pipefail

# Configuration
REGISTRY_PRIMARY="${REGISTRY_PRIMARY:-registry.neural-hive.local:5000}"
REGISTRY_SECONDARY="${REGISTRY_SECONDARY:-37.60.241.150:30500}"
REGISTRY_URL="${REGISTRY_PRIMARY}"  # Backward compatibility
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_TAG="${DEFAULT_TAG:-latest}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# All services with Dockerfiles
declare -A SERVICES=(
    ["gateway-intencoes"]="services/gateway-intencoes"
    ["orchestrator-dynamic"]="services/orchestrator-dynamic"
    ["semantic-translation-engine"]="services/semantic-translation-engine"
    ["consensus-engine"]="services/consensus-engine"
    ["specialist-architecture"]="services/specialist-architecture"
    ["specialist-behavior"]="services/specialist-behavior"
    ["specialist-business"]="services/specialist-business"
    ["specialist-evolution"]="services/specialist-evolution"
    ["specialist-technical"]="services/specialist-technical"
    ["worker-agents"]="services/worker-agents"
    ["scout-agents"]="services/scout-agents"
    ["guard-agents"]="services/guard-agents"
    ["analyst-agents"]="services/analyst-agents"
    ["optimizer-agents"]="services/optimizer-agents"
    ["queen-agent"]="services/queen-agent"
    ["code-forge"]="services/code-forge"
    ["execution-ticket-service"]="services/execution-ticket-service"
    ["explainability-api"]="services/explainability-api"
    ["mcp-tool-catalog"]="services/mcp-tool-catalog"
    ["memory-layer-api"]="services/memory-layer-api"
    ["self-healing-engine"]="services/self-healing-engine"
    ["service-registry"]="services/service-registry"
    ["sla-management-system"]="services/sla-management-system"
)

check_registry() {
    log_info "Checking registry availability at ${REGISTRY_URL}..."
    if curl -s -o /dev/null -w '%{http_code}' "http://${REGISTRY_URL}/v2/" | grep -q "200"; then
        log_info "Registry is available"
        return 0
    else
        log_error "Registry not available at http://${REGISTRY_URL}"
        log_error "Deploy the registry first: helm install registry helm-charts/docker-registry -n registry --create-namespace"
        return 1
    fi
}

build_image() {
    local service=$1
    local path=$2
    local tag=$3
    local full_image="${REGISTRY_URL}/${service}:${tag}"

    log_step "Building ${service}..."

    if [[ ! -f "${PROJECT_ROOT}/${path}/Dockerfile" ]]; then
        log_warn "No Dockerfile found for ${service}, skipping..."
        return 1
    fi

    # Build with BuildKit for better caching
    # Use PROJECT_ROOT as context because Dockerfiles reference libraries/ and schemas/
    DOCKER_BUILDKIT=1 docker build \
        -t "${full_image}" \
        -f "${PROJECT_ROOT}/${path}/Dockerfile" \
        "${PROJECT_ROOT}" \
        --build-arg BUILDKIT_INLINE_CACHE=1

    log_info "Built: ${full_image}"
    return 0
}

push_image() {
    local service=$1
    local tag=$2
    local full_image="${REGISTRY_URL}/${service}:${tag}"

    log_step "Pushing ${service}..."
    docker push "${full_image}"
    log_info "Pushed: ${full_image}"
}

build_and_push() {
    local service=$1
    local tag=$2

    if [[ ! -v "SERVICES[$service]" ]]; then
        log_error "Unknown service: ${service}"
        log_info "Available services: ${!SERVICES[*]}"
        return 1
    fi

    local path="${SERVICES[$service]}"

    if build_image "$service" "$path" "$tag"; then
        push_image "$service" "$tag"
    fi
}

build_and_push_all() {
    local tag=$1
    local failed=()
    local success=()

    log_info "Building and pushing all services..."
    log_info "Total services: ${#SERVICES[@]}"

    for service in "${!SERVICES[@]}"; do
        echo ""
        if build_and_push "$service" "$tag" 2>/dev/null; then
            success+=("$service")
        else
            failed+=("$service")
        fi
    done

    echo ""
    log_info "=============================================="
    log_info "Build Summary"
    log_info "=============================================="
    log_info "Successful: ${#success[@]}"
    for s in "${success[@]}"; do
        echo -e "  ${GREEN}✓${NC} $s"
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        log_warn "Failed: ${#failed[@]}"
        for f in "${failed[@]}"; do
            echo -e "  ${RED}✗${NC} $f"
        done
    fi
}

list_services() {
    log_info "Available services:"
    for service in "${!SERVICES[@]}"; do
        echo "  - ${service} (${SERVICES[$service]})"
    done
}

list_registry_images() {
    log_info "Images in registry (${REGISTRY_URL}):"
    curl -s "http://${REGISTRY_URL}/v2/_catalog" | jq -r '.repositories[]' 2>/dev/null || echo "  (empty or error)"
}

usage() {
    cat <<EOF
Usage: $0 [COMMAND] [OPTIONS]

Commands:
    build <service> [tag]    Build and push a single service
    all [tag]                Build and push all services
    list                     List available services
    images                   List images in registry
    check                    Check registry availability

Options:
    service    Service name (e.g., gateway-intencoes)
    tag        Image tag (default: latest)

Environment Variables:
    REGISTRY_PRIMARY    Registry primário DNS (default: registry.neural-hive.local:5000)
    REGISTRY_SECONDARY  Registry secundário IP (default: 37.60.241.150:30500)
    DEFAULT_TAG         Default tag (default: latest)

Examples:
    $0 build gateway-intencoes v1.0.0
    $0 all latest
    $0 list
    $0 images
EOF
}

main() {
    local command="${1:-}"
    local arg1="${2:-}"
    local arg2="${3:-$DEFAULT_TAG}"

    case "$command" in
        build)
            if [[ -z "$arg1" ]]; then
                log_error "Service name required"
                usage
                exit 1
            fi
            check_registry || exit 1
            build_and_push "$arg1" "$arg2"
            ;;
        all)
            check_registry || exit 1
            build_and_push_all "${arg1:-$DEFAULT_TAG}"
            ;;
        list)
            list_services
            ;;
        images)
            check_registry || exit 1
            list_registry_images
            ;;
        check)
            check_registry
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
