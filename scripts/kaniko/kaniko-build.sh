#!/bin/bash
#===============================================================================
# kaniko-build.sh
# Executa builds usando Kaniko no cluster Kubernetes
# Constrói imagens Docker sem necessidade de Docker daemon
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NAMESPACE="${NAMESPACE:-neural-hive}"
REGISTRY_URL="${REGISTRY_URL:-docker-registry.registry.svc.cluster.local:5000}"
IMAGE_TAG="${IMAGE_TAG:-1.0.8}"
PARALLEL_JOBS="${PARALLEL_JOBS:-3}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600}"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }
log_build() { echo -e "${MAGENTA}[BUILD]${NC} $1"; }

print_header() {
    echo ""
    echo "=============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "=============================================================================="
}

# Mapeamento de serviços para Dockerfiles
declare -A SERVICE_DOCKERFILES=(
    ["analyst-agents"]="services/analyst-agents/Dockerfile"
    ["code-forge"]="services/code-forge/Dockerfile"
    ["execution-ticket-service"]="services/execution-ticket-service/Dockerfile"
    ["explainability-api"]="services/explainability-api/Dockerfile"
    ["gateway-intencoes"]="services/gateway-intencoes/Dockerfile"
    ["guard-agents"]="services/guard-agents/Dockerfile"
    ["mcp-tool-catalog"]="services/mcp-tool-catalog/Dockerfile"
    ["memory-layer-api"]="services/memory-layer-api/Dockerfile"
    ["orchestrator-dynamic"]="services/orchestrator-dynamic/Dockerfile"
    ["queen-agent"]="services/queen-agent/Dockerfile"
    ["scout-agents"]="services/scout-agents/Dockerfile"
    ["self-healing-engine"]="services/self-healing-engine/Dockerfile"
    ["service-registry"]="services/service-registry/Dockerfile"
    ["sla-management-system"]="services/sla-management-system/Dockerfile"
)

# Lista padrão de serviços que precisam rebuild
DEFAULT_SERVICES=(
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

# Gerar manifesto do Job Kaniko para um serviço
generate_kaniko_job() {
    local SERVICE_NAME="$1"
    local DOCKERFILE_PATH="$2"
    local TAG="$3"
    
    cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: kaniko-build-${SERVICE_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: kaniko-build
    service: ${SERVICE_NAME}
    build-tag: "${TAG}"
spec:
  ttlSecondsAfterFinished: 600
  backoffLimit: 2
  template:
    metadata:
      labels:
        app: kaniko-build
        service: ${SERVICE_NAME}
    spec:
      restartPolicy: Never
      initContainers:
        - name: check-context
          image: alpine:3.18
          command:
            - /bin/sh
            - -c
            - |
              echo "Verificando contexto de build para ${SERVICE_NAME}..."
              if [ ! -f "/context/${DOCKERFILE_PATH}" ]; then
                echo "ERRO: Dockerfile nao encontrado: /context/${DOCKERFILE_PATH}"
                echo "Arquivos disponíveis em /context/services/:"
                ls -la /context/services/ 2>/dev/null || echo "(vazio)"
                exit 1
              fi
              echo "Contexto OK."
          volumeMounts:
            - name: context
              mountPath: /context
              readOnly: true
      containers:
        - name: kaniko
          image: gcr.io/kaniko-project/executor:v1.19.2
          args:
            - "--dockerfile=${DOCKERFILE_PATH}"
            - "--context=dir:///context"
            - "--destination=${REGISTRY_URL}/${SERVICE_NAME}:${TAG}"
            - "--destination=${REGISTRY_URL}/${SERVICE_NAME}:latest"
            - "--cache=true"
            - "--cache-dir=/cache"
            - "--insecure"
            - "--skip-tls-verify"
            - "--single-snapshot"
            - "--snapshotMode=redo"
            - "--verbosity=info"
          volumeMounts:
            - name: context
              mountPath: /context
              readOnly: true
            - name: cache
              mountPath: /cache
          resources:
            limits:
              memory: "4Gi"
              cpu: "2"
            requests:
              memory: "2Gi"
              cpu: "1"
      volumes:
        - name: context
          persistentVolumeClaim:
            claimName: kaniko-build-context
        - name: cache
          persistentVolumeClaim:
            claimName: kaniko-cache
EOF
}

# Parar context-loader para liberar PVC (RWO)
stop_context_loader() {
    log_step "Parando context-loader para liberar PVC..."
    kubectl delete pod kaniko-context-loader -n "$NAMESPACE" --ignore-not-found --wait=true 2>/dev/null || true
    sleep 2
}

# Reiniciar context-loader após builds
start_context_loader() {
    log_step "Reiniciando context-loader..."
    kubectl apply -f "${PROJECT_ROOT}/k8s/kaniko/pod-context-loader.yaml" 2>/dev/null || true
}

# Verificar pré-requisitos
check_prerequisites() {
    log_step "Verificando pré-requisitos..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi
    
    # Verificar PVCs
    if ! kubectl get pvc kaniko-build-context -n "$NAMESPACE" &> /dev/null; then
        log_error "PVC kaniko-build-context não encontrado. Execute primeiro: ./sync-code-to-pvc.sh setup"
        exit 1
    fi
    
    # Verificar se contexto tem arquivos
    local CONTEXT_POD=$(kubectl get pods -n "$NAMESPACE" -l component=context-loader -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$CONTEXT_POD" ]]; then
        local FILE_COUNT=$(kubectl exec "$CONTEXT_POD" -n "$NAMESPACE" -- sh -c "find /context/services -name 'Dockerfile' 2>/dev/null | wc -l" 2>/dev/null || echo "0")
        if [[ "$FILE_COUNT" -eq 0 ]]; then
            log_error "Nenhum Dockerfile encontrado no PVC. Execute primeiro: ./sync-code-to-pvc.sh full"
            exit 1
        fi
        log_info "Dockerfiles no PVC: $FILE_COUNT"
    fi
    
    # Parar context-loader para liberar PVC (necessário com RWO)
    stop_context_loader
    
    log_success "Pré-requisitos OK"
}

# Limpar job anterior se existir
cleanup_previous_job() {
    local SERVICE_NAME="$1"
    local JOB_NAME="kaniko-build-${SERVICE_NAME}"
    
    if kubectl get job "$JOB_NAME" -n "$NAMESPACE" &> /dev/null; then
        log_info "Removendo job anterior: $JOB_NAME"
        kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --wait=false 2>/dev/null || true
        sleep 2
    fi
}

# Build de um único serviço
build_service() {
    local SERVICE_NAME="$1"
    local TAG="$2"
    
    if [[ ! -v "SERVICE_DOCKERFILES[$SERVICE_NAME]" ]]; then
        log_error "Serviço desconhecido: $SERVICE_NAME"
        log_info "Serviços disponíveis: ${!SERVICE_DOCKERFILES[*]}"
        return 1
    fi
    
    local DOCKERFILE_PATH="${SERVICE_DOCKERFILES[$SERVICE_NAME]}"
    local JOB_NAME="kaniko-build-${SERVICE_NAME}"
    
    log_build "Building: $SERVICE_NAME (tag: $TAG)"
    
    # Limpar job anterior
    cleanup_previous_job "$SERVICE_NAME"
    
    # Gerar e aplicar o Job
    generate_kaniko_job "$SERVICE_NAME" "$DOCKERFILE_PATH" "$TAG" | kubectl apply -f -
    
    log_info "Job criado: $JOB_NAME"
    
    return 0
}

# Aguardar conclusão de um job
wait_for_job() {
    local SERVICE_NAME="$1"
    local JOB_NAME="kaniko-build-${SERVICE_NAME}"
    local TIMEOUT="${2:-$WAIT_TIMEOUT}"
    
    log_step "Aguardando conclusão de $JOB_NAME (timeout: ${TIMEOUT}s)..."
    
    if kubectl wait --for=condition=complete job/"$JOB_NAME" -n "$NAMESPACE" --timeout="${TIMEOUT}s" 2>/dev/null; then
        log_success "$SERVICE_NAME: Build concluído com sucesso"
        return 0
    elif kubectl wait --for=condition=failed job/"$JOB_NAME" -n "$NAMESPACE" --timeout=5s 2>/dev/null; then
        log_error "$SERVICE_NAME: Build falhou"
        # Mostrar logs do erro
        local POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [[ -n "$POD_NAME" ]]; then
            log_error "Logs do pod $POD_NAME:"
            kubectl logs "$POD_NAME" -n "$NAMESPACE" --tail=50 2>/dev/null || true
        fi
        return 1
    else
        log_warn "$SERVICE_NAME: Timeout ou status desconhecido"
        return 2
    fi
}

# Build de múltiplos serviços (sequencial pois PVC é RWO)
# Nota: Com Longhorn RWO, builds são executados um de cada vez
build_services_parallel() {
    local TAG="$1"
    shift
    local SERVICES=("$@")
    
    print_header "Build de ${#SERVICES[@]} Serviços (Sequencial - PVC RWO)"
    log_warn "Usando modo sequencial pois o PVC é ReadWriteOnce (Longhorn)"
    
    local TOTAL=${#SERVICES[@]}
    local CURRENT=0
    local SUCCESS=()
    local FAILED=()
    local START_TIME=$(date +%s)
    
    for SERVICE in "${SERVICES[@]}"; do
        CURRENT=$((CURRENT + 1))
        echo ""
        log_step "[$CURRENT/$TOTAL] Building: $SERVICE"
        
        if build_service "$SERVICE" "$TAG"; then
            if wait_for_job "$SERVICE"; then
                SUCCESS+=("$SERVICE")
                log_success "$SERVICE: Build concluído"
            else
                FAILED+=("$SERVICE")
                log_error "$SERVICE: Build falhou"
            fi
        else
            FAILED+=("$SERVICE")
            log_error "$SERVICE: Falha ao criar job"
        fi
        
        # Limpar job concluído para liberar recursos
        kubectl delete job "kaniko-build-${SERVICE}" -n "$NAMESPACE" --ignore-not-found 2>/dev/null || true
    done
    
    local END_TIME=$(date +%s)
    local DURATION=$((END_TIME - START_TIME))
    
    # Resumo
    print_header "Resumo do Build"
    echo ""
    log_info "Total: $TOTAL"
    log_info "Duração: ${DURATION}s"
    log_success "Sucesso: ${#SUCCESS[@]}"
    for s in "${SUCCESS[@]}"; do
        echo -e "  ${GREEN}✓${NC} $s"
    done
    
    if [[ ${#FAILED[@]} -gt 0 ]]; then
        log_error "Falhas: ${#FAILED[@]}"
        for f in "${FAILED[@]}"; do
            echo -e "  ${RED}✗${NC} $f"
        done
        # Reiniciar context-loader
        start_context_loader
        return 1
    fi
    
    # Reiniciar context-loader após builds
    start_context_loader
    return 0
}

# Build sequencial (mais fácil de debugar)
build_services_sequential() {
    local TAG="$1"
    shift
    local SERVICES=("$@")
    
    print_header "Build Sequencial de ${#SERVICES[@]} Serviços"
    
    local TOTAL=${#SERVICES[@]}
    local CURRENT=0
    local SUCCESS=()
    local FAILED=()
    
    for SERVICE in "${SERVICES[@]}"; do
        CURRENT=$((CURRENT + 1))
        echo ""
        log_step "[$CURRENT/$TOTAL] $SERVICE"
        
        if build_service "$SERVICE" "$TAG"; then
            if wait_for_job "$SERVICE"; then
                SUCCESS+=("$SERVICE")
            else
                FAILED+=("$SERVICE")
            fi
        else
            FAILED+=("$SERVICE")
        fi
        
        # Limpar job concluído
        kubectl delete job "kaniko-build-${SERVICE}" -n "$NAMESPACE" --ignore-not-found 2>/dev/null || true
    done
    
    # Resumo
    print_header "Resumo do Build"
    log_info "Total: $TOTAL"
    log_success "Sucesso: ${#SUCCESS[@]}"
    if [[ ${#FAILED[@]} -gt 0 ]]; then
        log_error "Falhas: ${#FAILED[@]}"
        for f in "${FAILED[@]}"; do
            echo "  - $f"
        done
        start_context_loader
        return 1
    fi
    
    start_context_loader
    return 0
}

# Listar serviços disponíveis
list_services() {
    print_header "Serviços Disponíveis"
    for service in "${!SERVICE_DOCKERFILES[@]}"; do
        echo "  - $service -> ${SERVICE_DOCKERFILES[$service]}"
    done | sort
}

# Verificar status dos builds
check_status() {
    print_header "Status dos Jobs Kaniko"
    
    log_step "Jobs ativos:"
    kubectl get jobs -n "$NAMESPACE" -l app=kaniko-build -o wide 2>/dev/null || echo "  Nenhum job encontrado"
    
    echo ""
    log_step "Pods de build:"
    kubectl get pods -n "$NAMESPACE" -l app=kaniko-build -o wide 2>/dev/null || echo "  Nenhum pod encontrado"
}

# Logs de um build específico
show_logs() {
    local SERVICE_NAME="$1"
    local JOB_NAME="kaniko-build-${SERVICE_NAME}"
    
    local POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$POD_NAME" ]]; then
        log_error "Pod não encontrado para job $JOB_NAME"
        return 1
    fi
    
    log_info "Logs do pod: $POD_NAME"
    kubectl logs "$POD_NAME" -n "$NAMESPACE" -f
}

# Limpar jobs concluídos
cleanup() {
    print_header "Limpando Jobs Kaniko"
    
    log_step "Removendo jobs concluídos com sucesso..."
    kubectl delete jobs -n "$NAMESPACE" -l app=kaniko-build --field-selector=status.successful=1 2>/dev/null || true
    
    log_step "Removendo jobs falhos..."
    kubectl delete jobs -n "$NAMESPACE" -l app=kaniko-build 2>/dev/null || true
    
    log_success "Limpeza concluída"
}

# Ajuda
usage() {
    cat <<EOF
Uso: $0 [COMANDO] [OPÇÕES]

Comandos:
    build <service>         Build de um serviço específico
    all                     Build de todos os serviços (padrão)
    parallel                Build paralelo de serviços específicos
    list                    Listar serviços disponíveis
    status                  Verificar status dos builds
    logs <service>          Mostrar logs de um build
    cleanup                 Limpar jobs concluídos

Opções:
    -t, --tag <tag>         Tag da imagem (padrão: $IMAGE_TAG)
    -p, --parallel <n>      Número de jobs paralelos (padrão: $PARALLEL_JOBS)
    -s, --services <list>   Lista de serviços separados por vírgula
    -n, --namespace <ns>    Namespace (padrão: $NAMESPACE)
    --timeout <seconds>     Timeout por build (padrão: $WAIT_TIMEOUT)
    -h, --help              Exibir esta ajuda

Exemplos:
    # Build de todos os serviços
    $0 all -t 1.0.8
    
    # Build de um serviço específico
    $0 build gateway-intencoes -t 1.0.8
    
    # Build paralelo de serviços específicos
    $0 parallel -s "gateway-intencoes,queen-agent,orchestrator-dynamic" -t 1.0.8
    
    # Verificar status
    $0 status
    
    # Ver logs de um build
    $0 logs gateway-intencoes

EOF
}

# Parse de argumentos
parse_args() {
    COMMAND="${1:-all}"
    shift || true
    
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
            -s|--services)
                IFS=',' read -ra SELECTED_SERVICES <<< "$2"
                shift 2
                ;;
            -n|--namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --timeout)
                WAIT_TIMEOUT="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                # Pode ser nome de serviço para comando build/logs
                SERVICE_ARG="$1"
                shift
                ;;
        esac
    done
}

# Main
main() {
    parse_args "$@"
    
    case "$COMMAND" in
        build)
            if [[ -z "${SERVICE_ARG:-}" ]]; then
                log_error "Nome do serviço requerido"
                usage
                exit 1
            fi
            check_prerequisites
            build_service "$SERVICE_ARG" "$IMAGE_TAG"
            wait_for_job "$SERVICE_ARG"
            ;;
        all)
            check_prerequisites
            build_services_parallel "$IMAGE_TAG" "${DEFAULT_SERVICES[@]}"
            ;;
        parallel)
            check_prerequisites
            local SERVICES_TO_BUILD=("${SELECTED_SERVICES[@]:-${DEFAULT_SERVICES[@]}}")
            build_services_parallel "$IMAGE_TAG" "${SERVICES_TO_BUILD[@]}"
            ;;
        sequential)
            check_prerequisites
            local SERVICES_TO_BUILD=("${SELECTED_SERVICES[@]:-${DEFAULT_SERVICES[@]}}")
            build_services_sequential "$IMAGE_TAG" "${SERVICES_TO_BUILD[@]}"
            ;;
        list)
            list_services
            ;;
        status)
            check_status
            ;;
        logs)
            if [[ -z "${SERVICE_ARG:-}" ]]; then
                log_error "Nome do serviço requerido"
                exit 1
            fi
            show_logs "$SERVICE_ARG"
            ;;
        cleanup)
            cleanup
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            log_error "Comando desconhecido: $COMMAND"
            usage
            exit 1
            ;;
    esac
}

main "$@"
