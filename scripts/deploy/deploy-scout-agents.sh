#!/bin/bash
set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações padrão
ENVIRONMENT="${ENVIRONMENT:-dev}"
NAMESPACE="${NAMESPACE:-neural-hive-exploration}"
BUILD_IMAGE="${BUILD_IMAGE:-false}"
REGISTRY="${REGISTRY:-localhost:5000}"
VALUES_FILE="${VALUES_FILE:-}"

# Timestamp para logs
timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
}

log_info() {
    echo -e "${GREEN}[$(timestamp)] INFO:${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(timestamp)} WARN:${NC} $1"
}

log_error() {
    echo -e "${RED}[$(timestamp)] ERROR:${NC} $1"
}

# Validar pré-requisitos
log_info "Validando pré-requisitos..."

if ! command -v kubectl &> /dev/null; then
    log_error "kubectl não encontrado. Instale kubectl primeiro."
    exit 1
fi

if ! command -v helm &> /dev/null; then
    log_error "helm não encontrado. Instale helm primeiro."
    exit 1
fi

# Verificar conexão com cluster
if ! kubectl cluster-info &> /dev/null; then
    log_error "Não foi possível conectar ao cluster Kubernetes."
    exit 1
fi

log_info "Pré-requisitos OK"

# Criar namespace se não existir
log_info "Criando namespace $NAMESPACE se necessário..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Adicionar labels ao namespace
kubectl label namespace "$NAMESPACE" \
    neural-hive.io/layer=exploration \
    istio-injection=enabled \
    --overwrite

log_info "Namespace $NAMESPACE configurado"

# Criar tópicos Kafka
log_info "Criando tópicos Kafka..."
kubectl apply -f ../../k8s/kafka-topics/exploration-signals-topic.yaml
kubectl apply -f ../../k8s/kafka-topics/exploration-opportunities-topic.yaml

log_info "Aguardando tópicos Kafka ficarem prontos..."
sleep 5

# Build e push da imagem se solicitado
if [ "$BUILD_IMAGE" = "true" ]; then
    log_info "Building Docker image..."

    cd ../../services/scout-agents
    docker build -t scout-agents:latest .
    docker tag scout-agents:latest "$REGISTRY/scout-agents:$ENVIRONMENT"

    log_info "Pushing image to registry..."
    docker push "$REGISTRY/scout-agents:$ENVIRONMENT"

    cd -
fi

# Preparar valores do Helm
HELM_ARGS=""
if [ -n "$VALUES_FILE" ]; then
    HELM_ARGS="--values $VALUES_FILE"
fi

# Deploy do Helm chart
log_info "Deploying Scout Agents com Helm..."
helm upgrade --install scout-agents \
    ../../helm-charts/scout-agents \
    --namespace "$NAMESPACE" \
    --set config.service.environment="$ENVIRONMENT" \
    --set image.repository="$REGISTRY/scout-agents" \
    --set image.tag="$ENVIRONMENT" \
    $HELM_ARGS \
    --wait \
    --timeout 5m

log_info "Helm deployment concluído"

# Aguardar pods ficarem ready
log_info "Aguardando pods ficarem ready (timeout 5min)..."
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=scout-agents \
    -n "$NAMESPACE" \
    --timeout=300s

# Verificar registro no Service Registry
log_info "Verificando integração com Service Registry..."
# TODO: Implementar verificação real
log_warn "Verificação de Service Registry ainda não implementada"

# Executar smoke tests
log_info "Executando smoke tests..."

POD=$(kubectl get pods -l app.kubernetes.io/name=scout-agents -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}')

# Test 1: Health check
log_info "Test 1: Liveness check..."
kubectl exec -n "$NAMESPACE" "$POD" -- curl -f http://localhost:8000/health/live || {
    log_error "Liveness check falhou"
    exit 1
}

log_info "Test 2: Readiness check..."
kubectl exec -n "$NAMESPACE" "$POD" -- curl -f http://localhost:8000/health/ready || {
    log_error "Readiness check falhou"
    exit 1
}

log_info "Test 3: Metrics endpoint..."
kubectl exec -n "$NAMESPACE" "$POD" -- curl -f http://localhost:9090/metrics > /dev/null || {
    log_error "Metrics endpoint falhou"
    exit 1
}

log_info "Smoke tests passaram!"

# Exibir logs de startup
log_info "Logs de startup (últimas 20 linhas):"
kubectl logs -n "$NAMESPACE" "$POD" --tail=20

# Exibir NOTES.txt
log_info "===== Deployment Completo ====="
helm get notes scout-agents -n "$NAMESPACE"

log_info "Scout Agents deployado com sucesso!"
log_info "Namespace: $NAMESPACE"
log_info "Environment: $ENVIRONMENT"
log_info "Para ver logs: kubectl logs -f -l app.kubernetes.io/name=scout-agents -n $NAMESPACE"
