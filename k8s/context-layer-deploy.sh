#!/bin/bash
# Context Layer K8s Deployment Script
# Aplica os manifests do Context Layer na ordem correta

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR"

echo "========================================="
echo "Context Layer K8s Deployment"
echo "========================================="

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para printar mensagens
print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar se kubectl está disponível
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl não encontrado. Por favor instale o kubectl."
    exit 1
fi

# Verificar conexão com cluster
if ! kubectl cluster-info &> /dev/null; then
    print_error "Não foi possível conectar ao cluster Kubernetes."
    exit 1
fi

print_info "Cluster Kubernetes conectado com sucesso."

# Passo 1: Aplicar ConfigMap compartilhado do Context Layer
print_step "1. Aplicando context-layer-configmap.yaml..."
kubectl apply -f "$K8S_DIR/context-layer-configmap.yaml"

# Passo 2: Aplicar Semantic Translation Engine
print_step "2. Aplicando semantic-translation-engine-deployment.yaml..."
kubectl apply -f "$K8S_DIR/semantic-translation-engine-deployment.yaml"

# Passo 3: Aplicar Orchestrator Dynamic
print_step "3. Aplicando orchestrator-dynamic-deployment.yaml..."
kubectl apply -f "$K8S_DIR/orchestrator-dynamic-deployment.yaml"

# Passo 4: Aplicar Gateway com Context Layer
print_step "4. Aplicando gateway-intencoes-context-layer-deployment.yaml..."
kubectl apply -f "$K8S_DIR/gateway-intencoes-context-layer-deployment.yaml"

# Aguardar pods ficarem prontos
print_step "5. Aguardando pods ficarem prontos..."

# STE
print_info "Aguardando semantic-translation-engine pods..."
kubectl wait --for=condition=ready pod -l app=semantic-translation-engine -n semantic-translation-engine --timeout=120s || true

# Orchestrator
print_info "Aguardando orchestrator-dynamic pods..."
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n orchestrator-dynamic --timeout=120s || true

# Gateway
print_info "Aguardando gateway-intencoes pods..."
kubectl wait --for=condition=ready pod -l app=gateway-intencoes -n gateway --timeout=120s || true

# Verificar status dos pods
print_step "6. Verificando status dos pods..."

echo ""
echo "=== Semantic Translation Engine ==="
kubectl get pods -n semantic-translation-engine -l app=semantic-translation-engine

echo ""
echo "=== Orchestrator Dynamic ==="
kubectl get pods -n orchestrator-dynamic -l app=orchestrator-dynamic

echo ""
echo "=== Gateway Intenções ==="
kubectl get pods -n gateway -l app=gateway-intencoes

# Verificar ConfigMaps
print_step "7. Verificando ConfigMaps..."
kubectl get configmap -n semantic-translation-engine | grep -E "NAME|ste-config|context-layer-config"
kubectl get configmap -n orchestrator-dynamic | grep -E "NAME|orchestrator-config|context-layer-config"
kubectl get configmap -n gateway | grep -E "NAME|gateway-config|context-layer-config"

# Verificar HPA
print_step "8. Verificando HPAs..."
kubectl get hpa -n semantic-translation-engine || echo "Nenhum HPA encontrado em semantic-translation-engine"
kubectl get hpa -n orchestrator-dynamic || echo "Nenhum HPA encontrado em orchestrator-dynamic"
kubectl get hpa -n gateway || echo "Nenhum HPA encontrado em gateway"

# Verificar ServiceMonitors
print_step "9. Verificando ServiceMonitors..."
kubectl get servicemonitor -n semantic-translation-engine || echo "Nenhum ServiceMonitor encontrado em semantic-translation-engine"
kubectl get servicemonitor -n orchestrator-dynamic || echo "Nenhum ServiceMonitor encontrado em orchestrator-dynamic"
kubectl get servicemonitor -n gateway || echo "Nenhum ServiceMonitor encontrado em gateway"

echo ""
echo "========================================="
echo -e "${GREEN}Deploy concluído!${NC}"
echo "========================================="
echo ""
echo "Para verificar os logs:"
echo "  kubectl logs -n semantic-translation-engine deployment/semantic-translation-engine -f"
echo "  kubectl logs -n orchestrator-dynamic deployment/orchestrator-dynamic -f"
echo "  kubectl logs -n gateway deployment/gateway-intencoes -f"
echo ""
echo "Para verificar os eventos:"
echo "  kubectl get events -n semantic-translation-engine --sort-by='.lastTimestamp'"
echo "  kubectl get events -n orchestrator-dynamic --sort-by='.lastTimestamp'"
echo "  kubectl get events -n gateway --sort-by='.lastTimestamp'"
