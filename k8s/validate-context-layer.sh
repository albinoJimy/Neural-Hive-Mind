#!/bin/bash
# Context Layer K8s Validation Script
# Valida os manifests antes do deploy

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR"

echo "========================================="
echo "Context Layer K8s Validation"
echo "========================================="

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL_COUNT++))
}

check_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

# Verificar se kubectl está disponível
check_info "Verificando kubectl..."
if command -v kubectl &> /dev/null; then
    check_pass "kubectl encontrado: $(kubectl version --client --short 2>/dev/null || echo 'version unknown')"
else
    check_fail "kubectl não encontrado"
fi

# Verificar conexão com cluster
check_info "Verificando conexão com cluster..."
if kubectl cluster-info &> /dev/null; then
    check_pass "Cluster Kubernetes conectado"
    CLUSTER_VERSION=$(kubectl version --short 2>/dev/null | grep Server | head -1 || echo "unknown")
    check_info "Versão do cluster: $CLUSTER_VERSION"
else
    check_fail "Não foi possível conectar ao cluster Kubernetes"
fi

# Validar sintaxe dos manifests
check_info "Validando sintaxe dos manifests YAML..."

MANIFESTS=(
    "$K8S_DIR/context-layer-configmap.yaml"
    "$K8S_DIR/semantic-translation-engine-deployment.yaml"
    "$K8S_DIR/orchestrator-dynamic-deployment.yaml"
    "$K8S_DIR/gateway-intencoes-context-layer-deployment.yaml"
)

for manifest in "${MANIFESTS[@]}"; do
    if [ -f "$manifest" ]; then
        if kubectl apply --dry-run=client -f "$manifest" &> /dev/null; then
            check_pass "Sintaxe válida: $(basename "$manifest")"
        else
            check_fail "Erro de sintaxe em: $(basename "$manifest")"
            kubectl apply --dry-run=client -f "$manifest" 2>&1 | head -5
        fi
    else
        check_fail "Arquivo não encontrado: $(basename "$manifest")"
    fi
done

# Verificar namespaces duplicados
check_info "Verificando conflitos de namespaces..."
NAMESPACES=$(grep -h "^kind: Namespace$" -A1 "$K8S_DIR"/*context-layer*.yaml "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*.yaml 2>/dev/null | grep "^  name:" | sort | uniq -d)
if [ -z "$NAMESPACES" ]; then
    check_pass "Sem conflitos de namespaces"
else
    check_fail "Namespaces duplicados encontrados: $NAMESPACES"
fi

# Verificar ConfigMaps duplicados
check_info "Verificando ConfigMaps duplicados..."
DUPLICATE_CONFIGS=$(grep -h "^kind: ConfigMap$" -A2 "$K8S_DIR"/*context-layer*.yaml "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*.yaml 2>/dev/null | grep "^  name:" | sort | uniq -d)
if [ -z "$DUPLICATE_CONFIGS" ]; then
    check_pass "Sem ConfigMaps duplicados"
else
    check_fail "ConfigMaps duplicados: $DUPLICATE_CONFIGS"
fi

# Verificar referências ao context-layer-config
check_info "Verificando referências ao context-layer-config..."
REF_COUNT=$(grep -r "context-layer-config" "$K8S_DIR"/*.yaml 2>/dev/null | wc -l)
if [ "$REF_COUNT" -ge 3 ]; then
    check_pass "context-layer-config referenciado em $REF_COUNT arquivos"
else
    check_fail "context-layer-config referenciado em apenas $REF_COUNT arquivos (esperado: 3+)"
fi

# Verificar initContainers para instalação do neural_hive_context
check_info "Verificando initContainers para neural_hive_context..."
INIT_CONTAINERS=$(grep -h "install-neural-hive-context" "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*-*.yaml 2>/dev/null | wc -l)
if [ "$INIT_CONTAINERS" -ge 3 ]; then
    check_pass "initContainer neural_hive_context encontrado em $INIT_CONTAINERS deployments"
else
    check_fail "initContainer neural_hive_context encontrado em apenas $INIT_CONTAINERS deployments (esperado: 3)"
fi

# Verificar PYTHONPATH configuration
check_info "Verificando PYTHONPATH configuration..."
PYTHONPATH_COUNT=$(grep -h "PYTHONPATH" "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*-*.yaml 2>/dev/null | grep -c "name: PYTHONPATH" || echo 0)
if [ "$PYTHONPATH_COUNT" -ge 3 ]; then
    check_pass "PYTHONPATH configurado em $PYTHONPATH_COUNT deployments"
else
    check_fail "PYTHONPATH configurado em apenas $PYTHONPATH_COUNT deployments (esperado: 3)"
fi

# Verificar volumes para python-libs
check_info "Verificando volumes python-libs..."
VOLUME_COUNT=$(grep -h "name: python-libs" "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*-*.yaml 2>/dev/null | wc -l)
if [ "$VOLUME_COUNT" -ge 3 ]; then
    check_pass "Volume python-libs encontrado em $VOLUME_COUNT deployments"
else
    check_fail "Volume python-libs encontrado em apenas $VOLUME_COUNT deployments (esperado: 3)"
fi

# Verificar ServiceMonitors
check_info "Verificando ServiceMonitors..."
SERVICEMONITOR_COUNT=$(grep -h "^kind: ServiceMonitor$" "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*-*.yaml 2>/dev/null | wc -l)
if [ "$SERVICEMONITOR_COUNT" -ge 3 ]; then
    check_pass "ServiceMonitors definidos: $SERVICEMONITOR_COUNT"
else
    check_fail "ServiceMonitors definidos: $SERVICEMONITOR_COUNT (esperado: 3)"
fi

# Verificar HPAs
check_info "Verificando HorizontalPodAutoscalers..."
HPA_COUNT=$(grep -h "^kind: HorizontalPodAutoscaler$" "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*-*.yaml 2>/dev/null | wc -l)
if [ "$HPA_COUNT" -ge 3 ]; then
    check_pass "HPAs definidos: $HPA_COUNT"
else
    check_fail "HPAs definidos: $HPA_COUNT (esperado: 3)"
fi

# Verificar NetworkPolicies
check_info "Verificando NetworkPolicies..."
NETPOL_COUNT=$(grep -h "^kind: NetworkPolicy$" "$K8S_DIR"/semantic-*.yaml "$K8S_DIR"/orchestrator-*.yaml "$K8S_DIR"/gateway-*-*.yaml 2>/dev/null | wc -l)
if [ "$NETPOL_COUNT" -ge 3 ]; then
    check_pass "NetworkPolicies definidos: $NETPOL_COUNT"
else
    check_fail "NetworkPolicies definidos: $NETPOL_COUNT (esperado: 3)"
fi

# Verificar Context Layer env vars
check_info "Verificando Context Layer environment variables..."
CONTEXT_VARS=(
    "CONTEXT_LAYER_ENABLED"
    "WORKFLOW_CLASSIFIER_TYPE"
    "PII_DETECTOR_ENABLED"
    "PII_DETECTOR_ANGOLAN_ENABLED"
)

for var in "${CONTEXT_VARS[@]}"; do
    VAR_COUNT=$(grep -h "$var:" "$K8S_DIR"/context-layer-configmap.yaml 2>/dev/null | wc -l)
    if [ "$VAR_COUNT" -gt 0 ]; then
        check_pass "$var definido no ConfigMap"
    else
        check_fail "$var NÃO definido no ConfigMap"
    fi
done

# Summary
echo ""
echo "========================================="
echo "Validation Summary"
echo "========================================="
echo -e "${GREEN}Passed:${NC} $PASS_COUNT"
echo -e "${RED}Failed:${NC} $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ All validations passed!${NC}"
    echo "You can now run: ./k8s/context-layer-deploy.sh"
    exit 0
else
    echo -e "${RED}✗ Some validations failed. Please review and fix.${NC}"
    exit 1
fi
