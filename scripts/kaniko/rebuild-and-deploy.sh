#!/bin/bash
#===============================================================================
# rebuild-and-deploy.sh
# Script orquestrador para rebuild e deploy completo de serviços
# Usando Kaniko para builds no cluster Kubernetes
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NAMESPACE="${NAMESPACE:-neural-hive}"
IMAGE_TAG="${IMAGE_TAG:-1.0.8}"
PARALLEL_JOBS="${PARALLEL_JOBS:-3}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_SYNC="${SKIP_SYNC:-false}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_DEPLOY="${SKIP_DEPLOY:-false}"
RESTART_POLICY="${RESTART_POLICY:-rolling}"  # rolling, recreate

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }
log_phase() { echo -e "${MAGENTA}[PHASE]${NC} $1"; }

print_banner() {
    echo ""
    echo -e "${WHITE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${WHITE}║${NC}                                                                              ${WHITE}║${NC}"
    echo -e "${WHITE}║${NC}  ${CYAN}Neural Hive-Mind - Rebuild & Deploy Pipeline${NC}                              ${WHITE}║${NC}"
    echo -e "${WHITE}║${NC}  ${BLUE}Usando Kaniko para builds in-cluster${NC}                                       ${WHITE}║${NC}"
    echo -e "${WHITE}║${NC}                                                                              ${WHITE}║${NC}"
    echo -e "${WHITE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_header() {
    echo ""
    echo "=============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "=============================================================================="
}

# Lista de serviços que precisam rebuild (da tabela fornecida)
SERVICES_REQUIRING_REBUILD=(
    "analyst-agents"
    "code-forge"
    "execution-ticket-service"
    "explainability-api"
    "gateway-intencoes"
    "guard-agents"
    "mcp-tool-catalog"
    "memory-layer-api"
    "orchestrator-dynamic"
    "queen-agent"
    "scout-agents"
    "self-healing-engine"
    "service-registry"
    "sla-management-system"
)

# Verificar conexão com cluster
check_cluster_connection() {
    log_step "Verificando conexão com cluster..."
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi
    
    local CURRENT_CONTEXT=$(kubectl config current-context)
    log_info "Contexto atual: $CURRENT_CONTEXT"
    
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace $NAMESPACE não existe"
        exit 1
    fi
    
    log_success "Conexão com cluster OK"
}

# Verificar serviços existentes no cluster
check_existing_services() {
    print_header "Verificando Serviços Existentes no Cluster"
    
    local FOUND=()
    local NOT_FOUND=()
    
    for SERVICE in "${SERVICES_REQUIRING_REBUILD[@]}"; do
        if kubectl get deployment "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
            FOUND+=("$SERVICE")
            log_info "  ✓ $SERVICE - Deployment existe"
        elif kubectl get statefulset "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
            FOUND+=("$SERVICE")
            log_info "  ✓ $SERVICE - StatefulSet existe"
        else
            NOT_FOUND+=("$SERVICE")
            log_warn "  ✗ $SERVICE - Não encontrado no cluster"
        fi
    done
    
    echo ""
    log_info "Serviços encontrados: ${#FOUND[@]}"
    log_warn "Serviços não encontrados: ${#NOT_FOUND[@]}"
    
    SERVICES_TO_REBUILD=("${FOUND[@]}")
}

# FASE 1: Sincronizar código com PVC
phase_sync_code() {
    print_header "FASE 1: Sincronização de Código com PVC"
    
    if [[ "$SKIP_SYNC" == "true" ]]; then
        log_warn "Sincronização pulada (--skip-sync)"
        return 0
    fi
    
    log_phase "Executando sincronização completa..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Executaria: ${SCRIPT_DIR}/sync-code-to-pvc.sh full"
        return 0
    fi
    
    "${SCRIPT_DIR}/sync-code-to-pvc.sh" full
    
    log_success "Sincronização concluída"
}

# FASE 2: Build das imagens com Kaniko
phase_build_images() {
    print_header "FASE 2: Build das Imagens com Kaniko"
    
    if [[ "$SKIP_BUILD" == "true" ]]; then
        log_warn "Build pulado (--skip-build)"
        return 0
    fi
    
    local SERVICES_LIST=$(IFS=','; echo "${SERVICES_TO_REBUILD[*]}")
    
    log_phase "Iniciando build de ${#SERVICES_TO_REBUILD[@]} serviços..."
    log_info "Tag: $IMAGE_TAG"
    log_info "Paralelismo: $PARALLEL_JOBS"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Executaria: ${SCRIPT_DIR}/kaniko-build.sh parallel -t $IMAGE_TAG -p $PARALLEL_JOBS -s \"$SERVICES_LIST\""
        return 0
    fi
    
    "${SCRIPT_DIR}/kaniko-build.sh" parallel \
        -t "$IMAGE_TAG" \
        -p "$PARALLEL_JOBS" \
        -s "$SERVICES_LIST"
    
    log_success "Build concluído"
}

# FASE 3: Deploy/Restart dos serviços
phase_deploy_services() {
    print_header "FASE 3: Deploy/Restart dos Serviços"
    
    if [[ "$SKIP_DEPLOY" == "true" ]]; then
        log_warn "Deploy pulado (--skip-deploy)"
        return 0
    fi
    
    log_phase "Atualizando ${#SERVICES_TO_REBUILD[@]} serviços..."
    
    local SUCCESS=()
    local FAILED=()
    
    for SERVICE in "${SERVICES_TO_REBUILD[@]}"; do
        log_step "Atualizando: $SERVICE"
        
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Atualizaria imagem e reiniciaria $SERVICE"
            continue
        fi
        
        # Determinar tipo de recurso
        local RESOURCE_TYPE="deployment"
        if kubectl get statefulset "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
            RESOURCE_TYPE="statefulset"
        fi
        
        # Atualizar a tag da imagem
        local NEW_IMAGE="docker-registry.registry.svc.cluster.local:5000/${SERVICE}:${IMAGE_TAG}"
        
        if kubectl set image "$RESOURCE_TYPE/$SERVICE" \
            -n "$NAMESPACE" \
            "${SERVICE}=${NEW_IMAGE}" 2>/dev/null; then
            
            # Forçar rollout restart se necessário
            if [[ "$RESTART_POLICY" == "recreate" ]]; then
                kubectl rollout restart "$RESOURCE_TYPE/$SERVICE" -n "$NAMESPACE" 2>/dev/null || true
            fi
            
            log_success "  $SERVICE atualizado para $NEW_IMAGE"
            SUCCESS+=("$SERVICE")
        else
            log_warn "  Tentando via patch..."
            # Fallback: usar patch para atualizar
            kubectl patch "$RESOURCE_TYPE" "$SERVICE" -n "$NAMESPACE" \
                --type='json' \
                -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/image", "value": "'"$NEW_IMAGE"'"}]' 2>/dev/null || {
                    log_error "  Falha ao atualizar $SERVICE"
                    FAILED+=("$SERVICE")
                    continue
                }
            SUCCESS+=("$SERVICE")
        fi
    done
    
    # Aguardar rollouts
    if [[ ${#SUCCESS[@]} -gt 0 && "$DRY_RUN" != "true" ]]; then
        log_step "Aguardando rollouts..."
        for SERVICE in "${SUCCESS[@]}"; do
            local RESOURCE_TYPE="deployment"
            kubectl get statefulset "$SERVICE" -n "$NAMESPACE" &> /dev/null && RESOURCE_TYPE="statefulset"
            
            kubectl rollout status "$RESOURCE_TYPE/$SERVICE" -n "$NAMESPACE" --timeout=300s 2>/dev/null || {
                log_warn "Timeout aguardando $SERVICE"
            }
        done
    fi
    
    # Resumo
    echo ""
    log_info "Deploy Summary:"
    log_success "  Sucesso: ${#SUCCESS[@]}"
    if [[ ${#FAILED[@]} -gt 0 ]]; then
        log_error "  Falhas: ${#FAILED[@]}"
        for f in "${FAILED[@]}"; do
            echo "    - $f"
        done
    fi
}

# FASE 4: Validação pós-deploy
phase_validate() {
    print_header "FASE 4: Validação Pós-Deploy"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Pulando validação"
        return 0
    fi
    
    log_step "Verificando health dos serviços..."
    
    local HEALTHY=()
    local UNHEALTHY=()
    
    for SERVICE in "${SERVICES_TO_REBUILD[@]}"; do
        # Verificar se pods estão Running
        local POD_STATUS=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")
        
        if [[ "$POD_STATUS" == "Running" ]]; then
            HEALTHY+=("$SERVICE")
            echo -e "  ${GREEN}✓${NC} $SERVICE - $POD_STATUS"
        else
            UNHEALTHY+=("$SERVICE")
            echo -e "  ${RED}✗${NC} $SERVICE - $POD_STATUS"
        fi
    done
    
    echo ""
    log_info "Validação Summary:"
    log_success "  Healthy: ${#HEALTHY[@]}"
    if [[ ${#UNHEALTHY[@]} -gt 0 ]]; then
        log_warn "  Unhealthy: ${#UNHEALTHY[@]}"
    fi
}

# Gerar relatório final
generate_report() {
    print_header "Relatório Final"
    
    local END_TIME=$(date +%s)
    local DURATION=$((END_TIME - START_TIME))
    local MINUTES=$((DURATION / 60))
    local SECONDS=$((DURATION % 60))
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════╗"
    echo "║                        REBUILD & DEPLOY COMPLETO                        ║"
    echo "╠══════════════════════════════════════════════════════════════════════════╣"
    echo "║  Namespace:       $NAMESPACE"
    echo "║  Tag:             $IMAGE_TAG"
    echo "║  Serviços:        ${#SERVICES_TO_REBUILD[@]}"
    echo "║  Duração:         ${MINUTES}m ${SECONDS}s"
    echo "║  Data:            $(date '+%Y-%m-%d %H:%M:%S')"
    echo "╚══════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Verificar imagens no registry
    log_step "Imagens no Registry:"
    kubectl run --rm -it --restart=Never registry-check-$RANDOM \
        --image=alpine:3.18 -n "$NAMESPACE" \
        --command -- wget -qO- "http://docker-registry.registry.svc.cluster.local:5000/v2/_catalog" 2>/dev/null | head -20 || \
        log_warn "Não foi possível verificar registry"
}

# Ajuda
usage() {
    cat <<EOF
Uso: $0 [OPÇÕES]

Script orquestrador para rebuild e deploy completo de serviços Neural Hive-Mind
usando Kaniko para builds no cluster Kubernetes.

OPÇÕES:
    -t, --tag <tag>         Tag da imagem (padrão: $IMAGE_TAG)
    -p, --parallel <n>      Jobs paralelos para build (padrão: $PARALLEL_JOBS)
    -n, --namespace <ns>    Namespace (padrão: $NAMESPACE)
    --dry-run               Modo simulação (não executa)
    --skip-sync             Pular sincronização de código
    --skip-build            Pular fase de build
    --skip-deploy           Pular fase de deploy
    --restart-policy <p>    Política de restart: rolling|recreate (padrão: rolling)
    -s, --services <list>   Lista de serviços específicos (separados por vírgula)
    -h, --help              Exibir esta ajuda

SERVIÇOS PADRÃO (do cluster):
    analyst-agents, code-forge, execution-ticket-service, explainability-api,
    gateway-intencoes, guard-agents, mcp-tool-catalog, memory-layer-api,
    orchestrator-dynamic, queen-agent, scout-agents, self-healing-engine,
    service-registry, sla-management-system

EXEMPLOS:
    # Rebuild e deploy completo
    $0 -t 1.0.8
    
    # Apenas build (sem deploy)
    $0 -t 1.0.8 --skip-deploy
    
    # Deploy com código já sincronizado
    $0 -t 1.0.8 --skip-sync
    
    # Serviços específicos
    $0 -t 1.0.8 -s "gateway-intencoes,queen-agent"
    
    # Dry run (simulação)
    $0 -t 1.0.8 --dry-run

FLUXO DE EXECUÇÃO:
    1. Sincronização de código para PVC (kubectl cp)
    2. Build de imagens com Kaniko (Jobs no cluster)
    3. Atualização dos Deployments/StatefulSets
    4. Validação de health dos serviços

EOF
}

# Parse argumentos
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            -p|--parallel)
                PARALLEL_JOBS="$2"
                shift 2
                ;;
            -n|--namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --skip-sync)
                SKIP_SYNC="true"
                shift
                ;;
            --skip-build)
                SKIP_BUILD="true"
                shift
                ;;
            --skip-deploy)
                SKIP_DEPLOY="true"
                shift
                ;;
            --restart-policy)
                RESTART_POLICY="$2"
                shift 2
                ;;
            -s|--services)
                IFS=',' read -ra SERVICES_REQUIRING_REBUILD <<< "$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Opção desconhecida: $1"
                usage
                exit 1
                ;;
        esac
    done
}

# Main
main() {
    START_TIME=$(date +%s)
    
    parse_args "$@"
    
    print_banner
    
    log_info "Configuração:"
    log_info "  Namespace:    $NAMESPACE"
    log_info "  Tag:          $IMAGE_TAG"
    log_info "  Paralelismo:  $PARALLEL_JOBS"
    log_info "  Dry-run:      $DRY_RUN"
    log_info "  Skip sync:    $SKIP_SYNC"
    log_info "  Skip build:   $SKIP_BUILD"
    log_info "  Skip deploy:  $SKIP_DEPLOY"
    echo ""
    
    # Pré-verificações
    check_cluster_connection
    check_existing_services
    
    # Se nenhum serviço encontrado, abortar
    if [[ ${#SERVICES_TO_REBUILD[@]} -eq 0 ]]; then
        log_error "Nenhum serviço encontrado para rebuild"
        exit 1
    fi
    
    # Confirmação
    if [[ "$DRY_RUN" != "true" ]]; then
        echo ""
        log_warn "Esta operação irá reconstruir e fazer deploy de ${#SERVICES_TO_REBUILD[@]} serviços."
        read -p "Continuar? [y/N] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Operação cancelada"
            exit 0
        fi
    fi
    
    # Executar fases
    phase_sync_code
    phase_build_images
    phase_deploy_services
    phase_validate
    
    # Relatório
    generate_report
    
    log_success "Pipeline concluído com sucesso!"
}

main "$@"
