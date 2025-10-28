#!/bin/bash
set -e

# Script de deploy automatizado para Worker Agents

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

REGISTRY="${REGISTRY:-localhost:5000}"
IMAGE_NAME="${IMAGE_NAME:-worker-agents}"
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
NAMESPACE="${NAMESPACE:-neural-hive-execution}"

SKIP_BUILD=false
SKIP_PUSH=false
DRY_RUN=false
DEBUG=false

# Parse flags
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
        --debug)
            DEBUG=true
            set -x
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "========================================="
echo "Deploying Worker Agents"
echo "========================================="
echo "Registry: $REGISTRY"
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Namespace: $NAMESPACE"
echo ""

# Validar pré-requisitos
echo "Validando pré-requisitos..."

# Verificar kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl não encontrado"
    exit 1
fi

# Verificar acesso ao cluster
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Não foi possível acessar o cluster Kubernetes"
    exit 1
fi

# Verificar Kafka
if ! kubectl get kafkatopics -n kafka &> /dev/null; then
    echo "⚠️  Kafka não parece estar instalado"
fi

# Verificar Service Registry
if ! kubectl get deployment service-registry -n neural-hive-registry &> /dev/null; then
    echo "⚠️  Service Registry não encontrado"
fi

# Verificar Execution Ticket Service
if ! kubectl get deployment execution-ticket-service -n neural-hive-orchestration &> /dev/null; then
    echo "⚠️  Execution Ticket Service não encontrado"
fi

echo "✅ Pré-requisitos validados"
echo ""

# Build da imagem
if [ "$SKIP_BUILD" = false ]; then
    echo "Building Docker image..."
    cd "$PROJECT_ROOT/services/worker-agents"
    docker build -t "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG" .
    echo "✅ Imagem criada: $REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    echo ""
else
    echo "⏭️  Pulando build da imagem"
    echo ""
fi

# Push da imagem
if [ "$SKIP_PUSH" = false ]; then
    echo "Pushing Docker image..."
    docker push "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    echo "✅ Imagem publicada: $REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    echo ""
else
    echo "⏭️  Pulando push da imagem"
    echo ""
fi

# Criar namespace
echo "Criando namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo "✅ Namespace criado: $NAMESPACE"
echo ""

# Criar tópico Kafka execution.results
echo "Criando tópico Kafka execution.results..."
kubectl apply -f "$PROJECT_ROOT/k8s/kafka-topics/execution-results-topic.yaml"
echo "✅ Tópico Kafka criado"
echo ""

# Deploy via Helm
echo "Deploying via Helm..."
cd "$PROJECT_ROOT"

if [ "$DRY_RUN" = true ]; then
    helm upgrade --install worker-agents \
        ./helm-charts/worker-agents/ \
        --namespace $NAMESPACE \
        --create-namespace \
        --set image.repository=$REGISTRY/$IMAGE_NAME \
        --set image.tag=$IMAGE_TAG \
        --dry-run --debug
else
    helm upgrade --install worker-agents \
        ./helm-charts/worker-agents/ \
        --namespace $NAMESPACE \
        --create-namespace \
        --set image.repository=$REGISTRY/$IMAGE_NAME \
        --set image.tag=$IMAGE_TAG \
        --wait
fi

echo "✅ Helm deployment concluído"
echo ""

# Smoke tests
echo "Executando smoke tests..."

# Verificar pods
echo "Verificando pods..."
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=worker-agents

# Aguardar pods ficarem ready
kubectl wait --for=condition=ready pod -n $NAMESPACE -l app.kubernetes.io/name=worker-agents --timeout=300s
echo "✅ Pods estão prontos"
echo ""

# Verificar health endpoint
echo "Verificando health endpoint..."
POD=$(kubectl get pod -n $NAMESPACE -l app.kubernetes.io/name=worker-agents -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n $NAMESPACE $POD -- wget -q -O- http://localhost:8080/health
echo ""
echo "✅ Health endpoint OK"
echo ""

# Exibir logs iniciais
echo "Logs iniciais:"
kubectl logs -n $NAMESPACE $POD --tail=20
echo ""

# Comandos úteis
echo "========================================="
echo "Deployment concluído com sucesso!"
echo "========================================="
echo ""
echo "Comandos úteis:"
echo ""
echo "Ver logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=worker-agents -f"
echo ""
echo "Ver status:"
echo "  kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=worker-agents"
echo ""
echo "Port-forward para métricas:"
echo "  kubectl port-forward -n $NAMESPACE svc/worker-agents 9090:9090"
echo ""
echo "Executar validação:"
echo "  $PROJECT_ROOT/scripts/validation/validate-worker-agents.sh"
echo ""
