#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -e

# Script de validação para Worker Agents

NAMESPACE="${NAMESPACE:-neural-hive-execution}"
APP_NAME="worker-agents"

echo "========================================="
echo "Validando Worker Agents"
echo "========================================="
echo ""

TOTAL_CHECKS=0
PASSED_CHECKS=0

check() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    local description="$1"
    local command="$2"

    echo -n "Verificando $description... "
    if eval "$command" &> /dev/null; then
        echo "✅"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo "❌"
        return 1
    fi
}

# 1. Pré-requisitos
echo "=== PRÉ-REQUISITOS ==="
check "Namespace existe" "kubectl get namespace $NAMESPACE"
check "Kafka cluster acessível" "kubectl get kafkatopics -n kafka"
check "Service Registry acessível" "kubectl get deployment service-registry -n neural-hive-registry"
check "Execution Ticket Service acessível" "kubectl get deployment execution-ticket-service -n neural-hive-orchestration"
check "Tópico execution.tickets existe" "kubectl get kafkatopic execution-tickets -n kafka"
check "Tópico execution.results existe" "kubectl get kafkatopic execution-results -n kafka"
echo ""

# 2. Deployment
echo "=== DEPLOYMENT ==="
check "Deployment existe" "kubectl get deployment $APP_NAME -n $NAMESPACE"
check "Pods rodando" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$APP_NAME | grep -q Running"
check "Containers healthy" "kubectl wait --for=condition=ready pod -n $NAMESPACE -l app.kubernetes.io/name=$APP_NAME --timeout=10s"
check "Service existe" "kubectl get service $APP_NAME -n $NAMESPACE"
echo ""

# 3. Health Checks
echo "=== HEALTH CHECKS ==="
POD=$(kubectl get pod -n $NAMESPACE -l app.kubernetes.io/name=$APP_NAME -o jsonpath='{.items[0].metadata.name}')
check "/health endpoint" "kubectl exec -n $NAMESPACE $POD -- wget -q -O- http://localhost:8080/health | grep -q healthy"
check "/ready endpoint" "kubectl exec -n $NAMESPACE $POD -- wget -q -O- http://localhost:8080/ready | grep -q ready"
check "/metrics endpoint" "kubectl exec -n $NAMESPACE $POD -- wget -q -O- http://localhost:9090/metrics | grep -q worker_agent"
echo ""

# 4. Métricas
echo "=== MÉTRICAS PROMETHEUS ==="
check "ServiceMonitor criado" "kubectl get servicemonitor $APP_NAME -n $NAMESPACE"
METRICS=$(kubectl exec -n $NAMESPACE $POD -- wget -q -O- http://localhost:9090/metrics)
check "Métrica startup_total presente" "echo '$METRICS' | grep -q worker_agent_startup_total"
check "Métrica active_tasks presente" "echo '$METRICS' | grep -q worker_agent_active_tasks"
echo ""

# 5. Logs
echo "=== LOGS ==="
LOGS=$(kubectl logs -n $NAMESPACE $POD --tail=50)
check "Logs estruturados em JSON" "echo '$LOGS' | grep -q '\"service\"'"
check "Sem erros críticos" "! echo '$LOGS' | grep -qi 'error.*critical'"
echo ""

# 6. Observabilidade
echo "=== OBSERVABILIDADE ==="
check "HPA criado" "kubectl get hpa $APP_NAME -n $NAMESPACE"
check "PodDisruptionBudget criado" "kubectl get pdb $APP_NAME -n $NAMESPACE"
echo ""

# Resumo
echo "========================================="
echo "RESUMO DA VALIDAÇÃO"
echo "========================================="
echo "Total de verificações: $TOTAL_CHECKS"
echo "Verificações passadas: $PASSED_CHECKS"
echo "Taxa de sucesso: $((PASSED_CHECKS * 100 / TOTAL_CHECKS))%"
echo ""

if [ $PASSED_CHECKS -eq $TOTAL_CHECKS ]; then
    echo "✅ Todas as validações passaram!"
    exit 0
else
    echo "❌ Algumas validações falharam"
    echo ""
    echo "Para troubleshooting, verifique:"
    echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=$APP_NAME"
    echo "  kubectl describe pod -n $NAMESPACE -l app.kubernetes.io/name=$APP_NAME"
    exit 1
fi
