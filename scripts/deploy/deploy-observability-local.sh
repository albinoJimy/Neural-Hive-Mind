#!/bin/bash
# Wrapper para deploy da stack de observabilidade em ambiente local

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Configurações para ambiente local
export NAMESPACE="neural-hive-observability"
export ENVIRONMENT="development"
export SKIP_TERRAFORM="true"
export SKIP_VALIDATION="false"

log "Deploy da Stack de Observabilidade - Ambiente Local"
log "Namespace: $NAMESPACE"
log "Environment: $ENVIRONMENT"

# Verificar se Minikube/Kind está rodando
if kubectl cluster-info | grep -q "Kubernetes control plane"; then
    success "Cluster Kubernetes detectado"
else
    error "Cluster Kubernetes não acessível"
    exit 1
fi

# Criar namespace se não existir
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log "Criando namespace $NAMESPACE..."
    kubectl create namespace "$NAMESPACE"
    kubectl label namespace "$NAMESPACE" \
        neural.hive/component=observability \
        neural.hive/layer=observabilidade
else
    success "Namespace $NAMESPACE já existe"
fi

# Adicionar repositórios Helm
log "Adicionando repositórios Helm..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
helm repo add grafana https://grafana.github.io/helm-charts || true
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts || true
helm repo update

# Deploy Prometheus Stack
log "Deployando Prometheus Stack..."
helm upgrade --install neural-hive-prometheus "$PROJECT_ROOT/helm-charts/prometheus-stack" \
    --namespace "$NAMESPACE" \
    --values "$PROJECT_ROOT/helm-charts/prometheus-stack/values-local.yaml" \
    --wait \
    --timeout=10m

success "Prometheus Stack deployed"

# Deploy Grafana
log "Deployando Grafana..."
helm upgrade --install neural-hive-grafana "$PROJECT_ROOT/helm-charts/grafana" \
    --namespace "$NAMESPACE" \
    --values "$PROJECT_ROOT/helm-charts/grafana/values-local.yaml" \
    --wait \
    --timeout=5m

success "Grafana deployed"

# Deploy Jaeger
log "Deployando Jaeger..."
helm upgrade --install neural-hive-jaeger "$PROJECT_ROOT/helm-charts/jaeger" \
    --namespace "$NAMESPACE" \
    --values "$PROJECT_ROOT/helm-charts/jaeger/values-local.yaml" \
    --wait \
    --timeout=5m

success "Jaeger deployed"

success "Deploy concluído!"

# Aguardar pods estarem prontos
log "Aguardando pods estarem prontos..."
kubectl wait --namespace "$NAMESPACE" \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/part-of=kube-prometheus-stack \
    --timeout=300s || warning "Prometheus pods demoraram para ficar prontos"

kubectl wait --namespace "$NAMESPACE" \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/name=grafana \
    --timeout=300s || warning "Grafana pod demorou para ficar pronto"

kubectl wait --namespace "$NAMESPACE" \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/name=jaeger \
    --timeout=300s || warning "Jaeger pod demorou para ficar pronto"

# Mostrar status
log "Status dos pods:"
kubectl get pods -n "$NAMESPACE"

# Instruções de acesso
echo ""
success "Stack de Observabilidade deployada com sucesso!"
echo ""
echo "Para acessar os serviços, execute:"
echo "  Prometheus:  kubectl port-forward -n $NAMESPACE svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090"
echo "  Grafana:     kubectl port-forward -n $NAMESPACE svc/neural-hive-grafana 3000:80"
echo "  Jaeger:      kubectl port-forward -n $NAMESPACE svc/neural-hive-jaeger 16686:16686"
echo ""
echo "Credenciais Grafana:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
