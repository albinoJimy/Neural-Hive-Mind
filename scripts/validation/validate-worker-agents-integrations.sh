#!/usr/bin/env bash
# =============================================================================
# validate-worker-agents-integrations.sh
# Script consolidado para validar integrações dos Worker Agents
# =============================================================================
set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
WORKER_DEPLOYMENT="${WORKER_DEPLOYMENT:-worker-agents}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Worker Agents Integration Validation"
echo "========================================"
echo ""

PASSED=0
FAILED=0
WARNINGS=0

# Função para verificar resultado
check_result() {
    local name="$1"
    local result="$2"
    if [[ "$result" == "0" ]]; then
        echo -e "${GREEN}✅ $name: OK${NC}"
        ((PASSED++))
    else
        echo -e "${RED}❌ $name: FAILED${NC}"
        ((FAILED++))
    fi
}

check_warning() {
    local name="$1"
    local message="$2"
    echo -e "${YELLOW}⚠️  $name: $message${NC}"
    ((WARNINGS++))
}

# =============================================================================
# 1. Verificar deployment Worker Agents
# =============================================================================
echo "--- Verificando deployment Worker Agents ---"

if kubectl get deployment "$WORKER_DEPLOYMENT" -n "$NAMESPACE" &>/dev/null; then
    READY=$(kubectl get deployment "$WORKER_DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    DESIRED=$(kubectl get deployment "$WORKER_DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    if [[ "$READY" == "$DESIRED" ]] && [[ "$READY" -gt 0 ]]; then
        check_result "Worker Agents deployment ($READY/$DESIRED pods)" 0
    else
        check_result "Worker Agents deployment ($READY/$DESIRED pods)" 1
    fi
else
    check_result "Worker Agents deployment" 1
fi

echo ""

# =============================================================================
# 2. BUILD Executor - Code Forge Integration
# =============================================================================
echo "--- BUILD Executor - Code Forge Integration ---"

# Verificar se Code Forge está configurado
CODEFORGE_URL=$(kubectl get configmap -n "$NAMESPACE" -l app=worker-agents -o jsonpath='{.items[0].data.CODE_FORGE_URL}' 2>/dev/null || echo "")

if [[ -n "$CODEFORGE_URL" ]]; then
    # Testar conectividade com Code Forge
    if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$CODEFORGE_URL/health" &>/dev/null; then
        check_result "BUILD Executor: Code Forge connectivity" 0
    else
        check_result "BUILD Executor: Code Forge connectivity" 1
    fi
else
    check_warning "BUILD Executor" "Code Forge URL não configurado (fallback para simulação)"
fi

echo ""

# =============================================================================
# 3. DEPLOY Executor - ArgoCD/Flux Integration
# =============================================================================
echo "--- DEPLOY Executor - ArgoCD/Flux Integration ---"

# Verificar ArgoCD
ARGOCD_ENABLED=$(kubectl get configmap -n "$NAMESPACE" -l app=worker-agents -o jsonpath='{.items[0].data.ARGOCD_ENABLED}' 2>/dev/null || echo "false")

if [[ "$ARGOCD_ENABLED" == "true" ]]; then
    # Verificar token ArgoCD
    if kubectl get secret argocd-token -n "$NAMESPACE" &>/dev/null; then
        check_result "DEPLOY Executor: ArgoCD token" 0
    else
        check_result "DEPLOY Executor: ArgoCD token" 1
    fi

    # Verificar conectividade ArgoCD
    ARGOCD_URL=$(kubectl get configmap -n "$NAMESPACE" -l app=worker-agents -o jsonpath='{.items[0].data.ARGOCD_URL}' 2>/dev/null || echo "")
    if [[ -n "$ARGOCD_URL" ]]; then
        if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -skf "$ARGOCD_URL/api/version" &>/dev/null; then
            check_result "DEPLOY Executor: ArgoCD connectivity" 0
        else
            check_warning "DEPLOY Executor" "ArgoCD não acessível (pode requerer token)"
        fi
    fi
else
    check_warning "DEPLOY Executor" "ArgoCD não habilitado"
fi

# Verificar Flux
if kubectl get kustomizations -n flux-system &>/dev/null; then
    check_result "DEPLOY Executor: Flux instalado" 0
else
    check_warning "DEPLOY Executor" "Flux não instalado ou namespace flux-system não existe"
fi

echo ""

# =============================================================================
# 4. TEST Executor - CI/CD Integration
# =============================================================================
echo "--- TEST Executor - CI/CD Integration ---"

# Verificar GitHub token
if kubectl get secret github-token -n "$NAMESPACE" &>/dev/null; then
    check_result "TEST Executor: GitHub token" 0
else
    check_warning "TEST Executor" "GitHub token não configurado"
fi

# Verificar GitLab token
if kubectl get secret gitlab-token -n "$NAMESPACE" &>/dev/null; then
    check_result "TEST Executor: GitLab token" 0
else
    check_warning "TEST Executor" "GitLab token não configurado"
fi

# Verificar Jenkins token
if kubectl get secret jenkins-token -n "$NAMESPACE" &>/dev/null; then
    check_result "TEST Executor: Jenkins token" 0
else
    check_warning "TEST Executor" "Jenkins token não configurado"
fi

echo ""

# =============================================================================
# 5. VALIDATE Executor - OPA/Security Tools Integration
# =============================================================================
echo "--- VALIDATE Executor - OPA/Security Tools Integration ---"

# Verificar OPA
OPA_URL=$(kubectl get configmap -n "$NAMESPACE" -l app=worker-agents -o jsonpath='{.items[0].data.OPA_URL}' 2>/dev/null || echo "http://opa.neural-hive-governance:8181")

if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf "$OPA_URL/health" &>/dev/null; then
    check_result "VALIDATE Executor: OPA connectivity" 0
else
    check_warning "VALIDATE Executor" "OPA não acessível (fallback conservador ativo)"
fi

# Verificar Trivy
if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- trivy --version &>/dev/null; then
    check_result "VALIDATE Executor: Trivy instalado" 0
else
    check_warning "VALIDATE Executor" "Trivy não instalado no container"
fi

# Verificar SonarQube token
if kubectl get secret sonarqube-token -n "$NAMESPACE" &>/dev/null; then
    check_result "VALIDATE Executor: SonarQube token" 0
else
    check_warning "VALIDATE Executor" "SonarQube token não configurado"
fi

# Verificar Snyk token
if kubectl get secret snyk-token -n "$NAMESPACE" &>/dev/null; then
    check_result "VALIDATE Executor: Snyk token" 0
else
    check_warning "VALIDATE Executor" "Snyk token não configurado"
fi

echo ""

# =============================================================================
# 6. EXECUTE Executor - Multi-Runtime Integration
# =============================================================================
echo "--- EXECUTE Executor - Multi-Runtime Integration ---"

# Verificar K8s Jobs RBAC
if kubectl auth can-i create jobs --as=system:serviceaccount:"$NAMESPACE":worker-agent-executor -n "$NAMESPACE" &>/dev/null; then
    check_result "EXECUTE Executor: K8s Jobs RBAC" 0
else
    check_warning "EXECUTE Executor" "RBAC para K8s Jobs não configurado"
fi

# Verificar Docker socket
if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- ls -la /var/run/docker.sock &>/dev/null; then
    check_result "EXECUTE Executor: Docker socket" 0
else
    check_warning "EXECUTE Executor" "Docker socket não montado (runtime Docker desabilitado)"
fi

echo ""

# =============================================================================
# 7. Verificar métricas Prometheus
# =============================================================================
echo "--- Métricas Prometheus ---"

# Verificar endpoint de métricas
if kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -sf http://localhost:8000/metrics &>/dev/null; then
    check_result "Prometheus metrics endpoint" 0

    # Verificar métricas específicas dos executors
    METRICS=$(kubectl exec -n "$NAMESPACE" deployment/"$WORKER_DEPLOYMENT" -- curl -s http://localhost:8000/metrics 2>/dev/null || echo "")

    if echo "$METRICS" | grep -q "build_tasks_executed_total"; then
        check_result "BUILD Executor metrics" 0
    else
        check_warning "BUILD Executor metrics" "Métricas não encontradas (pode não ter executado ainda)"
    fi

    if echo "$METRICS" | grep -q "deploy_tasks_executed_total"; then
        check_result "DEPLOY Executor metrics" 0
    else
        check_warning "DEPLOY Executor metrics" "Métricas não encontradas (pode não ter executado ainda)"
    fi

    if echo "$METRICS" | grep -q "test_tasks_executed_total"; then
        check_result "TEST Executor metrics" 0
    else
        check_warning "TEST Executor metrics" "Métricas não encontradas (pode não ter executado ainda)"
    fi

    if echo "$METRICS" | grep -q "validate_tasks_executed_total"; then
        check_result "VALIDATE Executor metrics" 0
    else
        check_warning "VALIDATE Executor metrics" "Métricas não encontradas (pode não ter executado ainda)"
    fi

    if echo "$METRICS" | grep -q "execute_tasks_executed_total"; then
        check_result "EXECUTE Executor metrics" 0
    else
        check_warning "EXECUTE Executor metrics" "Métricas não encontradas (pode não ter executado ainda)"
    fi
else
    check_result "Prometheus metrics endpoint" 1
fi

echo ""

# =============================================================================
# Resumo
# =============================================================================
echo "========================================"
echo "Resumo da Validação"
echo "========================================"
echo -e "${GREEN}Passou: $PASSED${NC}"
echo -e "${YELLOW}Avisos: $WARNINGS${NC}"
echo -e "${RED}Falhou: $FAILED${NC}"
echo ""

if [[ $FAILED -gt 0 ]]; then
    echo -e "${RED}❌ Validação com falhas. Verifique os itens acima.${NC}"
    exit 1
elif [[ $WARNINGS -gt 0 ]]; then
    echo -e "${YELLOW}⚠️  Validação com avisos. Sistema funcional com fallbacks.${NC}"
    exit 0
else
    echo -e "${GREEN}✅ Todas as integrações validadas com sucesso!${NC}"
    exit 0
fi
