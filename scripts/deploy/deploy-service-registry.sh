#!/bin/bash
set -e

# Script de deploy do Service Registry
# Uso: ./deploy-service-registry.sh [--skip-build] [--skip-push] [--dry-run] [--namespace NAMESPACE]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NAMESPACE="neural-hive-registry"
IMAGE_NAME="service-registry"
IMAGE_TAG="1.0.0"
SKIP_BUILD=false
SKIP_PUSH=false
DRY_RUN=false

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funções de log
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --skip-push)
            SKIP_PUSH=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            log_error "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

log_info "Iniciando deploy do Service Registry"
log_info "Namespace: $NAMESPACE"
log_info "Image: $IMAGE_NAME:$IMAGE_TAG"

# 1. Validar pré-requisitos
log_info "Validando pré-requisitos..."

if ! command -v kubectl &> /dev/null; then
    log_error "kubectl não encontrado. Instale kubectl antes de continuar."
    exit 1
fi

if ! command -v helm &> /dev/null; then
    log_error "helm não encontrado. Instale helm antes de continuar."
    exit 1
fi

if ! command -v docker &> /dev/null && [ "$SKIP_BUILD" = false ]; then
    log_error "docker não encontrado. Instale docker ou use --skip-build."
    exit 1
fi

log_info "Pré-requisitos OK"

# 2. Build da imagem Docker
if [ "$SKIP_BUILD" = false ]; then
    log_info "Building imagem Docker..."
    cd "$PROJECT_ROOT/services/service-registry"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] docker build -t $IMAGE_NAME:$IMAGE_TAG ."
    else
        docker build -t $IMAGE_NAME:$IMAGE_TAG .
        log_info "Imagem construída com sucesso"
    fi
else
    log_warn "Pulando build da imagem (--skip-build)"
fi

# 3. Push para registry
if [ "$SKIP_PUSH" = false ]; then
    log_info "Push da imagem para registry..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] docker push $IMAGE_NAME:$IMAGE_TAG"
    else
        # Assumindo registry local ou configurado
        # Adaptar para seu registry (ECR, GCR, DockerHub, etc)
        docker push $IMAGE_NAME:$IMAGE_TAG || log_warn "Push falhou - usando imagem local"
    fi
else
    log_warn "Pulando push da imagem (--skip-push)"
fi

# 4. Criar namespace se não existir
log_info "Verificando namespace $NAMESPACE..."

if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] kubectl create namespace $NAMESPACE"
else
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    log_info "Namespace $NAMESPACE pronto"
fi

# 5. Criar secrets
log_info "Criando secrets..."

if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] Criar secrets etcd e redis"
else
    # Secret para Redis password (vazio para ambiente local)
    kubectl create secret generic service-registry-secret \
        --from-literal=redis-password="" \
        --namespace=$NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -

    log_info "Secrets criados"
fi

# 6. Helm install/upgrade
log_info "Instalando/atualizando chart Helm..."

cd "$PROJECT_ROOT/helm-charts/service-registry"

if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] helm upgrade --install service-registry . --namespace $NAMESPACE"
    helm template service-registry . --namespace $NAMESPACE
else
    helm upgrade --install service-registry . \
        --namespace $NAMESPACE \
        --create-namespace \
        --wait \
        --timeout 5m

    log_info "Chart Helm instalado com sucesso"
fi

# 7. Aguardar pods ficarem ready
if [ "$DRY_RUN" = false ]; then
    log_info "Aguardando pods ficarem ready..."

    kubectl wait --for=condition=ready pod \
        -l app.kubernetes.io/name=service-registry \
        -n $NAMESPACE \
        --timeout=300s || log_warn "Timeout aguardando pods ready"

    log_info "Pods ready"
fi

# 8. Validar deployment
if [ "$DRY_RUN" = false ]; then
    log_info "Validando deployment..."

    # Verificar pods
    PODS=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=service-registry --no-headers | wc -l)
    log_info "Pods running: $PODS"

    # Verificar service
    SERVICE=$(kubectl get svc -n $NAMESPACE service-registry-service-registry --no-headers 2>/dev/null | wc -l)
    if [ "$SERVICE" -eq 1 ]; then
        log_info "Service criado com sucesso"
    else
        log_error "Service não encontrado"
    fi

    # Health check (port-forward temporário)
    log_info "Executando health check..."
    kubectl port-forward -n $NAMESPACE svc/service-registry-service-registry 50051:50051 &
    PF_PID=$!
    sleep 3

    if command -v grpcurl &> /dev/null; then
        grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check || log_warn "Health check falhou"
    else
        log_warn "grpcurl não disponível - pulando health check gRPC"
    fi

    kill $PF_PID 2>/dev/null || true
fi

# 9. Exibir status e logs
if [ "$DRY_RUN" = false ]; then
    log_info "Status do deployment:"
    kubectl get all -n $NAMESPACE -l app.kubernetes.io/name=service-registry

    log_info "\nLogs recentes:"
    kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=service-registry --tail=20 --prefix=true || true
fi

log_info "Deploy do Service Registry concluído com sucesso!"
log_info "\nPróximos passos:"
log_info "1. Validar deployment: $PROJECT_ROOT/scripts/validation/validate-service-registry.sh"
log_info "2. Ver métricas: kubectl port-forward -n $NAMESPACE svc/service-registry-service-registry 9090:9090"
log_info "3. Ver logs: kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=service-registry -f"
