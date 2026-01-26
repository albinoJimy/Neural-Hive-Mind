#!/bin/bash
#===============================================================================
# sync-code-to-pvc.sh
# Sincroniza código fonte do projeto para o PVC do cluster Kubernetes
# para uso com Kaniko builds
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NAMESPACE="${NAMESPACE:-neural-hive}"
CONTEXT_POD="kaniko-context-loader"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

print_header() {
    echo ""
    echo "=============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "=============================================================================="
}

# Verificar se kubectl está disponível
check_prerequisites() {
    log_step "Verificando pré-requisitos..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi
    
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace $NAMESPACE não existe"
        exit 1
    fi
    
    log_success "Pré-requisitos OK"
}

# Criar/Verificar PVCs e Pod Loader
setup_pvc_infrastructure() {
    print_header "Configurando Infraestrutura de Build"
    
    log_step "Aplicando PVCs..."
    kubectl apply -f "${PROJECT_ROOT}/k8s/kaniko/pvc-build-context.yaml"
    
    log_step "Aplicando ConfigMap..."
    kubectl apply -f "${PROJECT_ROOT}/k8s/kaniko/configmap-build-config.yaml"
    
    log_step "Verificando/Criando Pod Context Loader..."
    if kubectl get pod "$CONTEXT_POD" -n "$NAMESPACE" &> /dev/null; then
        POD_STATUS=$(kubectl get pod "$CONTEXT_POD" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
        if [[ "$POD_STATUS" != "Running" ]]; then
            log_warn "Pod $CONTEXT_POD não está Running (status: $POD_STATUS). Recriando..."
            kubectl delete pod "$CONTEXT_POD" -n "$NAMESPACE" --ignore-not-found
            sleep 2
            kubectl apply -f "${PROJECT_ROOT}/k8s/kaniko/pod-context-loader.yaml"
        fi
    else
        kubectl apply -f "${PROJECT_ROOT}/k8s/kaniko/pod-context-loader.yaml"
    fi
    
    log_step "Aguardando Pod ficar Ready..."
    kubectl wait --for=condition=Ready pod/"$CONTEXT_POD" -n "$NAMESPACE" --timeout=120s || {
        log_error "Timeout aguardando Pod $CONTEXT_POD"
        kubectl describe pod "$CONTEXT_POD" -n "$NAMESPACE"
        exit 1
    }
    
    log_success "Infraestrutura configurada"
}

# Variável global para path do temp
PREPARED_TEMP_DIR=""

# Preparar código para sincronização
prepare_code() {
    print_header "Preparando Código para Sincronização"
    
    PREPARED_TEMP_DIR="/tmp/kaniko-sync-$$"
    mkdir -p "$PREPARED_TEMP_DIR"
    
    log_step "Copiando arquivos relevantes para $PREPARED_TEMP_DIR..."
    
    # Criar estrutura de diretórios
    mkdir -p "$PREPARED_TEMP_DIR/services"
    mkdir -p "$PREPARED_TEMP_DIR/libraries"
    mkdir -p "$PREPARED_TEMP_DIR/schemas"
    mkdir -p "$PREPARED_TEMP_DIR/base-images"
    mkdir -p "$PREPARED_TEMP_DIR/libs"
    
    # Copiar services (apenas os necessários)
    for service_dir in "$PROJECT_ROOT"/services/*/; do
        if [[ -f "${service_dir}Dockerfile" ]]; then
            service_name=$(basename "$service_dir")
            log_info "  Copiando service: $service_name"
            cp -r "$service_dir" "$PREPARED_TEMP_DIR/services/"
        fi
    done
    
    # Copiar libraries compartilhadas
    if [[ -d "$PROJECT_ROOT/libraries" ]]; then
        log_info "  Copiando libraries/"
        cp -r "$PROJECT_ROOT/libraries"/* "$PREPARED_TEMP_DIR/libraries/" 2>/dev/null || true
    fi
    
    # Copiar schemas
    if [[ -d "$PROJECT_ROOT/schemas" ]]; then
        log_info "  Copiando schemas/"
        cp -r "$PROJECT_ROOT/schemas"/* "$PREPARED_TEMP_DIR/schemas/" 2>/dev/null || true
    fi
    
    # Copiar base-images
    if [[ -d "$PROJECT_ROOT/base-images" ]]; then
        log_info "  Copiando base-images/"
        cp -r "$PROJECT_ROOT/base-images"/* "$PREPARED_TEMP_DIR/base-images/" 2>/dev/null || true
    fi
    
    # Copiar libs
    if [[ -d "$PROJECT_ROOT/libs" ]]; then
        log_info "  Copiando libs/"
        cp -r "$PROJECT_ROOT/libs"/* "$PREPARED_TEMP_DIR/libs/" 2>/dev/null || true
    fi
    
    # Copiar arquivos raiz necessários
    for file in requirements.txt pyproject.toml setup.py setup.cfg; do
        if [[ -f "$PROJECT_ROOT/$file" ]]; then
            cp "$PROJECT_ROOT/$file" "$PREPARED_TEMP_DIR/"
        fi
    done
    
    # Mostrar tamanho
    local SIZE=$(du -sh "$PREPARED_TEMP_DIR" | cut -f1)
    log_info "Tamanho total: $SIZE"
}

# Sincronizar código para o PVC via kubectl cp
sync_to_pvc() {
    local TEMP_DIR="$1"
    
    print_header "Sincronizando Código para PVC"
    
    log_step "Limpando contexto anterior no PVC..."
    kubectl exec "$CONTEXT_POD" -n "$NAMESPACE" -- sh -c "rm -rf /context/* 2>/dev/null || true"
    
    log_step "Copiando código para PVC (pode demorar alguns minutos)..."
    
    # Copiar usando tar para maior eficiência
    tar -C "$TEMP_DIR" -cf - . | kubectl exec -i "$CONTEXT_POD" -n "$NAMESPACE" -- tar -C /context -xf -
    
    log_step "Verificando sincronização..."
    kubectl exec "$CONTEXT_POD" -n "$NAMESPACE" -- sh -c "ls -la /context/"
    kubectl exec "$CONTEXT_POD" -n "$NAMESPACE" -- sh -c "ls -la /context/services/ | head -20"
    
    # Contar Dockerfiles
    local DOCKERFILE_COUNT=$(kubectl exec "$CONTEXT_POD" -n "$NAMESPACE" -- sh -c "find /context/services -name 'Dockerfile' | wc -l")
    log_success "Sincronização concluída. Dockerfiles encontrados: $DOCKERFILE_COUNT"
    
    # Limpar temp
    rm -rf "$TEMP_DIR"
}

# Sincronização incremental (apenas arquivos modificados)
sync_incremental() {
    local SINCE="${1:-1 hour ago}"
    
    print_header "Sincronização Incremental (modificados desde: $SINCE)"
    
    local TEMP_DIR="/tmp/kaniko-sync-incremental-$$"
    mkdir -p "$TEMP_DIR"
    
    log_step "Buscando arquivos modificados..."
    
    # Usar git para encontrar arquivos modificados (se disponível)
    if [[ -d "$PROJECT_ROOT/.git" ]]; then
        cd "$PROJECT_ROOT"
        git diff --name-only HEAD~1 HEAD 2>/dev/null | while read -r file; do
            if [[ -f "$file" ]]; then
                local dir=$(dirname "$file")
                mkdir -p "$TEMP_DIR/$dir"
                cp "$file" "$TEMP_DIR/$file"
                log_info "  + $file"
            fi
        done
    else
        # Fallback: usar find com -mtime
        find "$PROJECT_ROOT/services" -type f -mmin -60 2>/dev/null | while read -r file; do
            local rel_path="${file#$PROJECT_ROOT/}"
            local dir=$(dirname "$rel_path")
            mkdir -p "$TEMP_DIR/$dir"
            cp "$file" "$TEMP_DIR/$rel_path"
            log_info "  + $rel_path"
        done
    fi
    
    if [[ -z "$(ls -A $TEMP_DIR 2>/dev/null)" ]]; then
        log_warn "Nenhum arquivo modificado encontrado"
        rm -rf "$TEMP_DIR"
        return 0
    fi
    
    log_step "Sincronizando arquivos incrementais..."
    tar -C "$TEMP_DIR" -cf - . | kubectl exec -i "$CONTEXT_POD" -n "$NAMESPACE" -- tar -C /context -xf -
    
    log_success "Sincronização incremental concluída"
    rm -rf "$TEMP_DIR"
}

# Verificar status do PVC
check_status() {
    print_header "Status do Sistema de Build"
    
    log_step "PVCs:"
    kubectl get pvc -n "$NAMESPACE" | grep kaniko || echo "  Nenhum PVC kaniko encontrado"
    
    log_step "Pod Context Loader:"
    kubectl get pod "$CONTEXT_POD" -n "$NAMESPACE" 2>/dev/null || echo "  Pod não encontrado"
    
    log_step "Jobs Kaniko ativos:"
    kubectl get jobs -n "$NAMESPACE" -l app=kaniko-build 2>/dev/null || echo "  Nenhum job ativo"
    
    log_step "Conteúdo do PVC:"
    if kubectl get pod "$CONTEXT_POD" -n "$NAMESPACE" &> /dev/null; then
        kubectl exec "$CONTEXT_POD" -n "$NAMESPACE" -- sh -c "du -sh /context/* 2>/dev/null" || echo "  PVC vazio"
    fi
}

# Limpar recursos
cleanup() {
    print_header "Limpando Recursos Kaniko"
    
    log_step "Removendo Jobs concluídos..."
    kubectl delete jobs -n "$NAMESPACE" -l app=kaniko-build --field-selector=status.successful=1 2>/dev/null || true
    
    log_step "Removendo Jobs falhos..."
    kubectl delete jobs -n "$NAMESPACE" -l app=kaniko-build --field-selector=status.failed=1 2>/dev/null || true
    
    log_success "Limpeza concluída"
}

# Ajuda
usage() {
    cat <<EOF
Uso: $0 [COMANDO] [OPÇÕES]

Comandos:
    full            Sincronização completa (padrão)
    incremental     Sincronização apenas de arquivos modificados
    setup           Apenas configurar infraestrutura (PVCs, Pod)
    status          Verificar status do sistema
    cleanup         Limpar jobs concluídos/falhos

Opções:
    -n, --namespace     Namespace Kubernetes (padrão: neural-hive)
    -h, --help          Exibir esta ajuda

Exemplos:
    $0 full                 # Sincronização completa
    $0 incremental          # Apenas arquivos modificados
    $0 setup                # Configurar infraestrutura
    $0 status               # Verificar status
    
EOF
}

# Main
main() {
    local COMMAND="${1:-full}"
    
    case "$COMMAND" in
        full)
            check_prerequisites
            setup_pvc_infrastructure
            prepare_code
            sync_to_pvc "$PREPARED_TEMP_DIR"
            ;;
        incremental)
            check_prerequisites
            sync_incremental "${2:-}"
            ;;
        setup)
            check_prerequisites
            setup_pvc_infrastructure
            ;;
        status)
            check_status
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
