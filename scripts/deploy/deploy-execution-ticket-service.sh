#!/bin/bash

###############################################################################
# Deploy Script - Execution Ticket Service
# Executa deploy do Execution Ticket Service no Kubernetes
###############################################################################

set -e

# Configurações
NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
ENVIRONMENT="${ENVIRONMENT:-development}"
VERSION="${VERSION:-1.0.0}"
REGISTRY="${REGISTRY:-localhost:5000}"
SERVICE_NAME="execution-ticket-service"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando prerequisites..."

    # Verificar ferramentas necessárias
    command -v kubectl >/dev/null 2>&1 || { log_error "kubectl não encontrado"; exit 1; }
    command -v helm >/dev/null 2>&1 || { log_error "helm não encontrado"; exit 1; }
    command -v docker >/dev/null 2>&1 || { log_error "docker não encontrado"; exit 1; }

    # Verificar conexão com cluster
    kubectl cluster-info >/dev/null 2>&1 || { log_error "Não foi possível conectar ao cluster Kubernetes"; exit 1; }

    # Criar namespace se não existir
    if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_info "Criando namespace $NAMESPACE..."
        kubectl create namespace "$NAMESPACE"
    fi

    log_info "Prerequisites OK"
}

build_and_push_image() {
    log_info "Building e pushing imagem Docker..."

    cd services/execution-ticket-service

    # Build
    docker build -t "$REGISTRY/$SERVICE_NAME:$VERSION" \
        --build-arg GIT_COMMIT="$(git rev-parse HEAD)" \
        --build-arg BUILD_DATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
        --build-arg VERSION="$VERSION" \
        .

    # Push (skip em development local)
    if [ "$ENVIRONMENT" != "development" ]; then
        docker push "$REGISTRY/$SERVICE_NAME:$VERSION"
        log_info "Imagem pushed: $REGISTRY/$SERVICE_NAME:$VERSION"
    else
        log_warn "Skipping push (development mode)"
    fi

    cd ../..
}

create_secrets() {
    log_info "Verificando secrets..."

    if kubectl get secret execution-ticket-service-secrets -n "$NAMESPACE" >/dev/null 2>&1; then
        log_warn "Secret já existe, pulando criação"
        return
    fi

    log_info "Criando secret execution-ticket-service-secrets..."

    # Solicitar credenciais
    read -sp "PostgreSQL Password: " POSTGRES_PASSWORD
    echo
    read -sp "MongoDB URI: " MONGODB_URI
    echo
    read -sp "JWT Secret Key: " JWT_SECRET_KEY
    echo

    # Criar secret
    kubectl create secret generic execution-ticket-service-secrets \
        --from-literal=postgres-password="$POSTGRES_PASSWORD" \
        --from-literal=mongodb-uri="$MONGODB_URI" \
        --from-literal=jwt-secret-key="$JWT_SECRET_KEY" \
        -n "$NAMESPACE"

    log_info "Secret criado"
}

run_migrations() {
    log_info "Executando migrations Alembic..."

    # TODO: Criar Job Kubernetes para executar migrations
    log_warn "Migrations devem ser executadas manualmente: alembic upgrade head"
}

deploy_helm_chart() {
    log_info "Deploying Helm chart..."

    helm upgrade --install execution-ticket-service \
        ./helm-charts/execution-ticket-service \
        --namespace "$NAMESPACE" \
        --set image.tag="$VERSION" \
        --set config.environment="$ENVIRONMENT" \
        --wait \
        --timeout 5m

    log_info "Helm chart deployed"
}

run_smoke_tests() {
    log_info "Executando smoke tests..."

    # Aguardar pods ready
    kubectl wait --for=condition=ready pod \
        -l app=execution-ticket-service \
        -n "$NAMESPACE" \
        --timeout=300s

    # Testar health endpoint
    PODNAME=$(kubectl get pods -n "$NAMESPACE" -l app=execution-ticket-service -o jsonpath='{.items[0].metadata.name}')

    kubectl exec "$PODNAME" -n "$NAMESPACE" -- curl -sf http://localhost:8000/health >/dev/null || {
        log_error "Health check failed"
        exit 1
    }

    log_info "Smoke tests passed"
}

main() {
    log_info "===== Deploy Execution Ticket Service ====="
    log_info "Namespace: $NAMESPACE"
    log_info "Environment: $ENVIRONMENT"
    log_info "Version: $VERSION"

    check_prerequisites
    build_and_push_image
    create_secrets
    run_migrations
    deploy_helm_chart
    run_smoke_tests

    log_info "===== Deploy concluído com sucesso! ====="
    log_info "Próximos passos:"
    log_info "  1. Verificar pods: kubectl get pods -n $NAMESPACE"
    log_info "  2. Ver logs: kubectl logs -f -l app=execution-ticket-service -n $NAMESPACE"
    log_info "  3. Executar validação: ./scripts/validation/validate-execution-ticket-service.sh"
}

main "$@"
