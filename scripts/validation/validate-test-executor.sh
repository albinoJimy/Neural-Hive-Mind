#!/usr/bin/env bash
# =============================================================================
# validate-test-executor.sh
# Valida integração do TEST Executor com CI/CD (GitHub Actions, GitLab CI, Jenkins)
# =============================================================================
set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
WORKER_DEPLOYMENT="${WORKER_DEPLOYMENT:-worker-agents}"
PROVIDER="${1:-all}"  # github, gitlab, jenkins, ou all

echo "========================================"
echo "TEST Executor - CI/CD Validation"
echo "========================================"
echo ""

# Função para validar GitHub Actions
validate_github() {
    echo "--- GitHub Actions Integration ---"
    echo ""

    # Verificar token GitHub
    echo "1. Verificando token GitHub..."
    if kubectl get secret github-token -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret github-token existe"
    else
        echo "   ❌ Secret github-token não encontrado"
        echo "   → Criar: kubectl create secret generic github-token -n $NAMESPACE --from-literal=token=<token>"
        return
    fi

    # Verificar conectividade GitHub API
    echo ""
    echo "2. Verificando conectividade GitHub API..."
    GITHUB_API="${GITHUB_API_URL:-https://api.github.com}"

    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$GITHUB_API" &>/dev/null; then
        echo "   ✅ GitHub API está acessível"
    else
        echo "   ⚠️  GitHub API não acessível"
    fi
}

# Função para validar GitLab CI
validate_gitlab() {
    echo "--- GitLab CI Integration ---"
    echo ""

    # Verificar token GitLab
    echo "1. Verificando token GitLab..."
    if kubectl get secret gitlab-token -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret gitlab-token existe"
    else
        echo "   ⚠️  Secret gitlab-token não encontrado"
        echo "   → Criar: kubectl create secret generic gitlab-token -n $NAMESPACE --from-literal=token=<token>"
        return
    fi

    # Verificar conectividade GitLab API
    echo ""
    echo "2. Verificando conectividade GitLab API..."
    GITLAB_API="${GITLAB_API_URL:-https://gitlab.com/api/v4}"

    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$GITLAB_API" &>/dev/null; then
        echo "   ✅ GitLab API está acessível"
    else
        echo "   ⚠️  GitLab API não acessível"
    fi
}

# Função para validar Jenkins
validate_jenkins() {
    echo "--- Jenkins Integration ---"
    echo ""

    # Verificar token Jenkins
    echo "1. Verificando token Jenkins..."
    if kubectl get secret jenkins-token -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret jenkins-token existe"
    else
        echo "   ⚠️  Secret jenkins-token não encontrado"
        echo "   → Criar: kubectl create secret generic jenkins-token -n $NAMESPACE --from-literal=token=<token>"
        return
    fi

    # Verificar URL Jenkins
    JENKINS_URL="${JENKINS_URL:-}"
    if [[ -z "$JENKINS_URL" ]]; then
        echo ""
        echo "2. JENKINS_URL não configurado"
        echo "   → Configurar via Helm values ou env var JENKINS_URL"
    else
        echo ""
        echo "2. Verificando conectividade Jenkins..."
        if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$JENKINS_URL/api/json" &>/dev/null; then
            echo "   ✅ Jenkins API está acessível"
        else
            echo "   ⚠️  Jenkins API não acessível"
        fi
    fi
}

# Executar validações
case "$PROVIDER" in
    github)
        validate_github
        ;;
    gitlab)
        validate_gitlab
        ;;
    jenkins)
        validate_jenkins
        ;;
    all|*)
        validate_github
        echo ""
        validate_gitlab
        echo ""
        validate_jenkins
        ;;
esac

# Verificar métricas TEST
echo ""
echo "--- Métricas Prometheus ---"
METRICS=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -s http://localhost:8000/metrics 2>/dev/null || echo "")

if echo "$METRICS" | grep -q "test_tasks_executed_total"; then
    echo "✅ Métricas TEST registradas"
    echo "$METRICS" | grep "test_" | head -5
else
    echo "⚠️  Métricas TEST não encontradas (executor pode não ter executado ainda)"
fi

echo ""
echo "========================================"
echo "Validação completa."
echo "Para mais detalhes, consulte: docs/WORKER_AGENTS_INTEGRATION_GUIDE.md"
echo "========================================"
