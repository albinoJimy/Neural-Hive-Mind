#!/usr/bin/env bash
# =============================================================================
# validate-deploy-executor.sh
# Valida integração do DEPLOY Executor com ArgoCD e Flux
# =============================================================================
set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
WORKER_DEPLOYMENT="${WORKER_DEPLOYMENT:-worker-agents}"
PROVIDER="${1:-all}"  # argocd, flux, ou all

echo "========================================"
echo "DEPLOY Executor - ArgoCD/Flux Validation"
echo "========================================"
echo ""

# Função para validar ArgoCD
validate_argocd() {
    echo "--- ArgoCD Integration ---"
    echo ""

    # Verificar token ArgoCD
    echo "1. Verificando token ArgoCD..."
    if kubectl get secret argocd-token -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret argocd-token existe"
    else
        echo "   ❌ Secret argocd-token não encontrado"
        echo "   → Criar: kubectl create secret generic argocd-token -n $NAMESPACE --from-literal=token=<token>"
    fi

    # Verificar conectividade ArgoCD
    echo ""
    echo "2. Verificando conectividade ArgoCD..."
    ARGOCD_URL="${ARGOCD_URL:-https://argocd.neural-hive-argocd}"

    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -skf "$ARGOCD_URL/api/version" &>/dev/null; then
        echo "   ✅ ArgoCD API está acessível"
    else
        echo "   ⚠️  ArgoCD API não acessível (pode requerer autenticação)"
        echo "   → Verificar: kubectl get pods -n argocd"
    fi

    # Verificar Applications existentes
    echo ""
    echo "3. Verificando Applications ArgoCD..."
    kubectl get applications -n argocd 2>/dev/null | head -10 || echo "   Nenhuma Application encontrada ou namespace argocd não existe"
}

# Função para validar Flux
validate_flux() {
    echo "--- Flux Integration ---"
    echo ""

    # Verificar se Flux está instalado
    echo "1. Verificando instalação Flux..."
    if kubectl get namespace flux-system &>/dev/null; then
        echo "   ✅ Namespace flux-system existe"
    else
        echo "   ❌ Namespace flux-system não existe (Flux não instalado)"
        return
    fi

    # Verificar Flux controllers
    echo ""
    echo "2. Verificando controllers Flux..."
    kubectl get pods -n flux-system 2>/dev/null | head -10 || echo "   Nenhum pod encontrado"

    # Verificar Kustomizations
    echo ""
    echo "3. Verificando Kustomizations..."
    kubectl get kustomizations -n flux-system 2>/dev/null | head -10 || echo "   Nenhuma Kustomization encontrada"

    # Verificar GitRepositories
    echo ""
    echo "4. Verificando GitRepositories..."
    kubectl get gitrepositories -n flux-system 2>/dev/null | head -10 || echo "   Nenhum GitRepository encontrado"
}

# Executar validações
case "$PROVIDER" in
    argocd)
        validate_argocd
        ;;
    flux)
        validate_flux
        ;;
    all|*)
        validate_argocd
        echo ""
        validate_flux
        ;;
esac

# Verificar métricas DEPLOY
echo ""
echo "--- Métricas Prometheus ---"
METRICS=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -s http://localhost:8000/metrics 2>/dev/null || echo "")

if echo "$METRICS" | grep -q "deploy_tasks_executed_total"; then
    echo "✅ Métricas DEPLOY registradas"
    echo "$METRICS" | grep "deploy_" | head -5
else
    echo "⚠️  Métricas DEPLOY não encontradas (executor pode não ter executado ainda)"
fi

echo ""
echo "========================================"
echo "Validação completa."
echo "Para mais detalhes, consulte: docs/WORKER_AGENTS_INTEGRATION_GUIDE.md"
echo "========================================"
