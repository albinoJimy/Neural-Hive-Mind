#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/build/local.sh"
source "${SCRIPT_DIR}/build/ecr.sh"
source "${SCRIPT_DIR}/build/registry.sh"

TARGET="local"
VERSION="1.0.7"
PARALLEL_JOBS="8"
NO_CACHE=""
SKIP_BASE_IMAGES="false"
BUILD_CHANGED_ONLY="false"
PUSH="false"
SMART_BUILD="false"
PUSH_METRICS="false"
ENV="dev"
AWS_REGION="us-east-1"
REGISTRY_PRIMARY="${REGISTRY_PRIMARY:-registry.neural-hive.local:5000}"
REGISTRY_SECONDARY="${REGISTRY_SECONDARY:-37.60.241.150:30500}"
REGISTRY_URL="${REGISTRY_PRIMARY}"  # Backward compatibility

SERVICES=(
    "gateway-intencoes"
    "semantic-translation-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
    "consensus-engine"
    "memory-layer-api"
    "orchestrator-dynamic"
    "queen-agent"
    "worker-agents"
    "code-forge"
    "service-registry"
    "execution-ticket-service"
    "scout-agents"
    "analyst-agents"
    "guard-agents"
    "sla-management-system"
    "mcp-tool-catalog"
    "self-healing-engine"
    "explainability-api"
)

print_help() {
    cat << EOF
🚀 Neural Hive-Mind - Build CLI Unificado

Uso: $0 [OPTIONS]

OPTIONS:
  --target <local|ecr|registry|all>  Target de build (padrão: local)
  --version <ver>                    Versão das imagens (padrão: 1.0.7)
  --parallel <n>                     Jobs paralelos (padrão: 8)
  --services <list>                  Serviços específicos (separados por vírgula)
  --no-cache                         Build sem cache
  --skip-base-images                 Pular build de imagens base
  --build-changed-only               Build apenas serviços modificados (git diff)
  --smart-build                      Habilita retry e fallback para versões anteriores
  --push-metrics                     Envia métricas de build para Prometheus
  --push                             Executa push para o target escolhido
  --env <env>                        Ambiente (dev/staging/prod, padrão: dev)
  --region <region>                  Região AWS (padrão: us-east-1)
  --registry <url>                   URL do registry local
  --help                             Exibir ajuda

TARGETS:
  local     - Build local apenas (sem push)
  ecr       - Build + push para Amazon ECR
  registry  - Build + push para registry local
  all       - Build + push para ECR e registry local

EXAMPLES:
  # Build local apenas
  $0 --target local
  
  # Build e push para ECR
  $0 --target ecr --version 1.0.8 --push
  
  # Build e push para registry local
  $0 --target registry --push
  
  # Build e push para ambos
  $0 --target all --parallel 8 --push
  
  # Build serviços específicos
  $0 --target ecr --services "gateway-intencoes,consensus-engine" --push

EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --target)
            TARGET="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL_JOBS="$2"
            shift 2
            ;;
        --services)
            IFS=',' read -ra SERVICES <<< "$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --skip-base-images)
            SKIP_BASE_IMAGES="true"
            shift
            ;;
        --build-changed-only)
            BUILD_CHANGED_ONLY="true"
            shift
            ;;
        --smart-build)
            SMART_BUILD="true"
            shift
            ;;
        --push-metrics)
            PUSH_METRICS="true"
            shift
            ;;
        --push)
            PUSH="true"
            shift
            ;;
        --env)
            ENV="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --registry)
            REGISTRY_URL="$2"
            shift 2
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            print_help
            exit 1
            ;;
    esac
done

export VERSION ENV AWS_REGION REGISTRY_URL REGISTRY_PRIMARY REGISTRY_SECONDARY BUILD_CHANGED_ONLY SMART_BUILD PUSH_METRICS

main() {
    log_section "Neural Hive-Mind Build CLI"
    log_info "Target: ${TARGET}"
    log_info "Versão: ${VERSION}"
    log_info "Jobs paralelos: ${PARALLEL_JOBS}"
    log_info "Push habilitado: ${PUSH}"
    log_info "Smart Build: ${SMART_BUILD}"
    log_info "Push Metrics: ${PUSH_METRICS}"
    log_info "Total de serviços: ${#SERVICES[@]}"
    echo ""

    check_build_prerequisites "${TARGET}"

    # Build local first
    build_local "$VERSION" "$PARALLEL_JOBS" "${SERVICES[@]}" "$NO_CACHE" "$SKIP_BASE_IMAGES"

    # Get the list of actually built services (respects --build-changed-only)
    local services_to_push=("${BUILT_SERVICES[@]}")

    # If no services were built, skip push
    if [[ ${#services_to_push[@]} -eq 0 ]]; then
        log_info "Nenhum serviço foi buildado - pulando push"
        log_success "Build concluído com sucesso!"
        return 0
    fi

    case "$TARGET" in
        local)
            # No push needed for local target
            ;;
        ecr)
            if [[ "${PUSH}" == "true" ]]; then
                push_to_ecr "$VERSION" "$PARALLEL_JOBS" "${services_to_push[@]}"
            else
                log_info "Flag --push não fornecida; pulando push para ECR"
            fi
            ;;
        registry)
            if [[ "${PUSH}" == "true" ]]; then
                push_to_registry "$VERSION" "$PARALLEL_JOBS" "${services_to_push[@]}"
            else
                log_info "Flag --push não fornecida; pulando push para registry"
            fi
            ;;
        all)
            if [[ "${PUSH}" == "true" ]]; then
                push_to_ecr "$VERSION" "$PARALLEL_JOBS" "${services_to_push[@]}"
                push_to_registry "$VERSION" "$PARALLEL_JOBS" "${services_to_push[@]}"
            else
                log_info "Flag --push não fornecida; pulando push para ECR e registry"
            fi
            ;;
        *)
            log_error "Target inválido: ${TARGET}"
            print_help
            exit 1
            ;;
    esac

    log_success "Build concluído com sucesso!"

    # Enviar métricas para Prometheus se habilitado
    if [[ "${PUSH_METRICS}" == "true" ]]; then
        log_info "Enviando métricas de build para Prometheus..."
        source "${SCRIPT_DIR}/lib/metrics.sh"
        push_build_metrics "/tmp"
    fi
}

main
