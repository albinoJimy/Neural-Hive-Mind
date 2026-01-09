#!/usr/bin/env bash
# =============================================================================
# validate-build-executor.sh
# Valida integração do BUILD Executor com Code Forge
# =============================================================================
set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
WORKER_DEPLOYMENT="${WORKER_DEPLOYMENT:-worker-agents}"

echo "========================================"
echo "BUILD Executor - Code Forge Validation"
echo "========================================"
echo ""

# Verificar conectividade Code Forge
echo "1. Verificando conectividade com Code Forge..."
CODEFORGE_URL="${CODE_FORGE_URL:-http://code-forge.neural-hive-code-forge:8000}"

if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$CODEFORGE_URL/health" &>/dev/null; then
    echo "   ✅ Code Forge está acessível"
else
    echo "   ❌ Code Forge não está acessível"
    echo "   → Verificar: kubectl get pods -n neural-hive-code-forge"
    echo "   → Verificar: kubectl logs deployment/code-forge -n neural-hive-code-forge"
fi

# Verificar token Code Forge
echo ""
echo "2. Verificando token Code Forge..."
if kubectl get secret codeforge-token -n "$NAMESPACE" &>/dev/null; then
    echo "   ✅ Secret codeforge-token existe"
else
    echo "   ⚠️  Secret codeforge-token não encontrado"
    echo "   → Criar: kubectl create secret generic codeforge-token -n $NAMESPACE --from-literal=token=<token>"
fi

# Verificar métricas BUILD
echo ""
echo "3. Verificando métricas Prometheus..."
METRICS=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -s http://localhost:8000/metrics 2>/dev/null || echo "")

if echo "$METRICS" | grep -q "build_tasks_executed_total"; then
    echo "   ✅ Métricas BUILD registradas"
    echo "$METRICS" | grep "build_" | head -5
else
    echo "   ⚠️  Métricas BUILD não encontradas (executor pode não ter executado ainda)"
fi

# Verificar logs recentes
echo ""
echo "4. Verificando logs recentes do BUILD executor..."
kubectl logs deployment/"$WORKER_DEPLOYMENT" -n "$NAMESPACE" --tail=20 2>/dev/null | grep -i "build" || echo "   Nenhum log de BUILD encontrado"

echo ""
echo "========================================"
echo "Validação completa."
echo "Para mais detalhes, consulte: docs/WORKER_AGENTS_INTEGRATION_GUIDE.md"
echo "========================================"
