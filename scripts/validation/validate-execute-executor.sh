#!/usr/bin/env bash
# =============================================================================
# validate-execute-executor.sh
# Valida integração do EXECUTE Executor com múltiplos runtimes
# =============================================================================
set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
WORKER_DEPLOYMENT="${WORKER_DEPLOYMENT:-worker-agents}"
RUNTIME="${1:-all}"  # k8s, docker, lambda, local, ou all

echo "========================================"
echo "EXECUTE Executor - Multi-Runtime Validation"
echo "========================================"
echo ""

# Função para validar K8s Jobs
validate_k8s() {
    echo "--- Kubernetes Jobs Runtime ---"
    echo ""

    # Verificar RBAC
    echo "1. Verificando RBAC para K8s Jobs..."
    if kubectl auth can-i create jobs --as=system:serviceaccount:"$NAMESPACE":worker-agent-executor -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ ServiceAccount pode criar Jobs"
    else
        echo "   ❌ ServiceAccount não pode criar Jobs"
        echo "   → Verificar RBAC: kubectl describe clusterrole worker-agent-executor"
        echo "   → Verificar binding: kubectl describe clusterrolebinding worker-agent-executor"
    fi

    # Verificar ServiceAccount
    echo ""
    echo "2. Verificando ServiceAccount..."
    if kubectl get serviceaccount worker-agent-executor -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ ServiceAccount worker-agent-executor existe"
    else
        echo "   ⚠️  ServiceAccount worker-agent-executor não encontrado"
        echo "   → Criar: kubectl create serviceaccount worker-agent-executor -n $NAMESPACE"
    fi

    # Verificar Jobs existentes
    echo ""
    echo "3. Verificando Jobs existentes..."
    JOBS=$(kubectl get jobs -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    echo "   Jobs no namespace: $JOBS"
    kubectl get jobs -n "$NAMESPACE" 2>/dev/null | head -5 || echo "   Nenhum Job encontrado"
}

# Função para validar Docker
validate_docker() {
    echo "--- Docker Runtime ---"
    echo ""

    # Verificar Docker socket
    echo "1. Verificando Docker socket..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- ls -la /var/run/docker.sock &>/dev/null; then
        echo "   ✅ Docker socket montado"
    else
        echo "   ❌ Docker socket não montado"
        echo "   → Verificar volumeMount no deployment"
        return
    fi

    # Verificar Docker daemon
    echo ""
    echo "2. Verificando Docker daemon..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- docker ps &>/dev/null; then
        echo "   ✅ Docker daemon acessível"
        echo ""
        echo "   Containers em execução:"
        kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | head -5
    else
        echo "   ❌ Docker daemon não acessível"
        echo "   → Verificar permissões do socket"
    fi
}

# Função para validar Lambda
validate_lambda() {
    echo "--- AWS Lambda Runtime ---"
    echo ""

    # Verificar credenciais AWS
    echo "1. Verificando credenciais AWS..."
    if kubectl get secret aws-credentials -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ Secret aws-credentials existe"
    else
        echo "   ⚠️  Secret aws-credentials não encontrado"
        echo "   → Lambda runtime desabilitado"
        return
    fi

    # Verificar AWS CLI
    echo ""
    echo "2. Verificando AWS CLI..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- aws --version &>/dev/null; then
        AWS_VERSION=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- aws --version 2>/dev/null | head -1)
        echo "   ✅ AWS CLI instalado: $AWS_VERSION"
    else
        echo "   ⚠️  AWS CLI não instalado"
    fi

    # Verificar função Lambda
    LAMBDA_FUNCTION="${LAMBDA_FUNCTION_NAME:-neural-hive-executor}"
    echo ""
    echo "3. Verificando função Lambda: $LAMBDA_FUNCTION"
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- aws lambda get-function --function-name "$LAMBDA_FUNCTION" &>/dev/null; then
        echo "   ✅ Função Lambda existe"
    else
        echo "   ⚠️  Função Lambda não encontrada ou sem permissão"
    fi
}

# Função para validar Local runtime
validate_local() {
    echo "--- Local Runtime (subprocess) ---"
    echo ""

    # Verificar shell
    echo "1. Verificando shell..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- sh -c "echo 'test'" &>/dev/null; then
        echo "   ✅ Shell disponível"
    else
        echo "   ❌ Shell não disponível"
    fi

    # Verificar Python
    echo ""
    echo "2. Verificando Python..."
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- python --version &>/dev/null; then
        PYTHON_VERSION=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- python --version 2>&1)
        echo "   ✅ Python instalado: $PYTHON_VERSION"
    else
        echo "   ⚠️  Python não disponível"
    fi

    # Verificar espaço em disco
    echo ""
    echo "3. Verificando espaço em disco..."
    kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- df -h /tmp 2>/dev/null | head -2 || echo "   Não foi possível verificar"
}

# Executar validações
case "$RUNTIME" in
    k8s)
        validate_k8s
        ;;
    docker)
        validate_docker
        ;;
    lambda)
        validate_lambda
        ;;
    local)
        validate_local
        ;;
    all|*)
        validate_k8s
        echo ""
        validate_docker
        echo ""
        validate_lambda
        echo ""
        validate_local
        ;;
esac

# Verificar métricas EXECUTE
echo ""
echo "--- Métricas Prometheus ---"
METRICS=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -s http://localhost:8000/metrics 2>/dev/null || echo "")

if echo "$METRICS" | grep -q "execute_tasks_executed_total"; then
    echo "✅ Métricas EXECUTE registradas"
    echo "$METRICS" | grep "execute_" | head -5
else
    echo "⚠️  Métricas EXECUTE não encontradas (executor pode não ter executado ainda)"
fi

if echo "$METRICS" | grep -q "execute_runtime_fallbacks_total"; then
    echo ""
    echo "Fallbacks de runtime registrados:"
    echo "$METRICS" | grep "execute_runtime_fallbacks_total" | head -5
fi

echo ""
echo "========================================"
echo "Validação completa."
echo "Para mais detalhes, consulte: docs/WORKER_AGENTS_INTEGRATION_GUIDE.md"
echo "========================================"
