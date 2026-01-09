#!/usr/bin/env bash
# =============================================================================
# validate-validate-executor.sh
# Valida integração do VALIDATE Executor com OPA e ferramentas de segurança
# =============================================================================
set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
WORKER_DEPLOYMENT="${WORKER_DEPLOYMENT:-worker-agents}"
TOOL="${1:-all}"  # opa, trivy, sonarqube, snyk, checkov, ou all

echo "========================================"
echo "VALIDATE Executor - OPA/Security Tools Validation"
echo "========================================"
echo ""

# Função para validar OPA
validate_opa() {
    echo "--- OPA Gatekeeper Integration ---"
    echo ""

    # Verificar conectividade OPA
    echo "1. Verificando conectividade OPA..."
    OPA_URL="${OPA_URL:-http://opa.neural-hive-governance:8181}"

    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$OPA_URL/health" &>/dev/null; then
        echo "   ✅ OPA está acessível"
    else
        echo "   ❌ OPA não está acessível"
        echo "   → Fallback conservador ativo (validações retornarão FALHA)"
        echo "   → Verificar: kubectl get pods -n neural-hive-governance"
    fi

    # Verificar políticas OPA
    echo ""
    echo "2. Verificando políticas OPA..."
    if kubectl get constraints 2>/dev/null | head -10; then
        echo "   ✅ Constraints OPA encontrados"
    else
        echo "   ⚠️  Nenhum Constraint OPA encontrado"
    fi
}

# Função para validar Trivy
validate_trivy() {
    echo "--- Trivy Integration ---"
    echo ""

    echo "1. Verificando instalação Trivy..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- trivy --version &>/dev/null; then
        TRIVY_VERSION=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- trivy --version 2>/dev/null | head -1)
        echo "   ✅ Trivy instalado: $TRIVY_VERSION"
    else
        echo "   ❌ Trivy não instalado no container"
        echo "   → Verificar Dockerfile do worker-agents"
    fi

    # Verificar banco de vulnerabilidades
    echo ""
    echo "2. Verificando banco de vulnerabilidades..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- ls -la /root/.cache/trivy &>/dev/null; then
        echo "   ✅ Banco de vulnerabilidades presente"
    else
        echo "   ⚠️  Banco de vulnerabilidades pode não estar atualizado"
        echo "   → Executar: trivy image --download-db-only"
    fi
}

# Função para validar SonarQube
validate_sonarqube() {
    echo "--- SonarQube Integration ---"
    echo ""

    echo "1. Verificando token SonarQube..."
    if kubectl get secret sonarqube-token -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret sonarqube-token existe"
    else
        echo "   ⚠️  Secret sonarqube-token não encontrado"
        echo "   → Criar: kubectl create secret generic sonarqube-token -n $NAMESPACE --from-literal=token=<token>"
        return
    fi

    # Verificar conectividade SonarQube
    SONARQUBE_URL="${SONARQUBE_URL:-}"
    if [[ -n "$SONARQUBE_URL" ]]; then
        echo ""
        echo "2. Verificando conectividade SonarQube..."
        if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$SONARQUBE_URL/api/system/status" &>/dev/null; then
            echo "   ✅ SonarQube API está acessível"
        else
            echo "   ⚠️  SonarQube API não acessível"
        fi
    else
        echo ""
        echo "2. SONARQUBE_URL não configurado"
    fi
}

# Função para validar Snyk
validate_snyk() {
    echo "--- Snyk Integration ---"
    echo ""

    echo "1. Verificando token Snyk..."
    if kubectl get secret snyk-token -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret snyk-token existe"
    else
        echo "   ⚠️  Secret snyk-token não encontrado"
        echo "   → Criar: kubectl create secret generic snyk-token -n $NAMESPACE --from-literal=token=<token>"
    fi

    # Verificar Snyk CLI
    echo ""
    echo "2. Verificando Snyk CLI..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- snyk --version &>/dev/null; then
        SNYK_VERSION=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- snyk --version 2>/dev/null | head -1)
        echo "   ✅ Snyk CLI instalado: $SNYK_VERSION"
    else
        echo "   ⚠️  Snyk CLI não instalado (usando API diretamente)"
    fi
}

# Função para validar Checkov
validate_checkov() {
    echo "--- Checkov Integration ---"
    echo ""

    echo "1. Verificando instalação Checkov..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- checkov --version &>/dev/null; then
        CHECKOV_VERSION=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- checkov --version 2>/dev/null | head -1)
        echo "   ✅ Checkov instalado: $CHECKOV_VERSION"
    else
        echo "   ⚠️  Checkov não instalado"
        echo "   → Verificar Dockerfile do worker-agents"
    fi
}

# Executar validações
case "$TOOL" in
    opa)
        validate_opa
        ;;
    trivy)
        validate_trivy
        ;;
    sonarqube)
        validate_sonarqube
        ;;
    snyk)
        validate_snyk
        ;;
    checkov)
        validate_checkov
        ;;
    all|*)
        validate_opa
        echo ""
        validate_trivy
        echo ""
        validate_sonarqube
        echo ""
        validate_snyk
        echo ""
        validate_checkov
        ;;
esac

# Verificar métricas VALIDATE
echo ""
echo "--- Métricas Prometheus ---"
METRICS=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -s http://localhost:8000/metrics 2>/dev/null || echo "")

if echo "$METRICS" | grep -q "validate_tasks_executed_total"; then
    echo "✅ Métricas VALIDATE registradas"
    echo "$METRICS" | grep "validate_" | head -5
else
    echo "⚠️  Métricas VALIDATE não encontradas (executor pode não ter executado ainda)"
fi

if echo "$METRICS" | grep -q "policy_violations_total"; then
    echo ""
    echo "Violações de política registradas:"
    echo "$METRICS" | grep "policy_violations_total" | head -5
fi

echo ""
echo "========================================"
echo "Validação completa."
echo "Para mais detalhes, consulte: docs/WORKER_AGENTS_INTEGRATION_GUIDE.md"
echo "========================================"
