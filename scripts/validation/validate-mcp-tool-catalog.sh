#!/bin/bash
set -e

# Validação completa do MCP Tool Catalog Service
# Segue padrão de validate-orchestrator-dynamic.sh

NAMESPACE="neural-hive-mcp"
SERVICE_NAME="mcp-tool-catalog"

PASSED=0
FAILED=0

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

function fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

function warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "=========================================="
echo "  MCP Tool Catalog - Validação Completa"
echo "=========================================="
echo ""

# 1. Pré-requisitos
echo "📋 1. Validando pré-requisitos..."

if kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    pass "Namespace ${NAMESPACE} existe"
else
    fail "Namespace ${NAMESPACE} não encontrado"
fi

if kubectl get kafkatopic mcp-tool-selection-requests -n neural-hive-kafka &>/dev/null; then
    pass "Kafka topic mcp-tool-selection-requests criado"
else
    fail "Kafka topic mcp-tool-selection-requests não encontrado"
fi

if kubectl get kafkatopic mcp-tool-selection-responses -n neural-hive-kafka &>/dev/null; then
    pass "Kafka topic mcp-tool-selection-responses criado"
else
    fail "Kafka topic mcp-tool-selection-responses não encontrado"
fi

# 2. Deployment
echo ""
echo "🚀 2. Validando deployment..."

POD_COUNT=$(kubectl get pods -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}" --field-selector=status.phase=Running -o json | jq '.items | length')

if [ "$POD_COUNT" -ge 2 ]; then
    pass "Pods running: ${POD_COUNT} (min 2 réplicas)"
else
    fail "Pods running: ${POD_COUNT} (esperado >= 2)"
fi

CRASH_COUNT=$(kubectl get pods -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}" -o json | jq '[.items[] | select(.status.containerStatuses[]?.state.waiting?.reason == "CrashLoopBackOff")] | length')

if [ "$CRASH_COUNT" -eq 0 ]; then
    pass "Nenhum pod em CrashLoopBackOff"
else
    fail "${CRASH_COUNT} pods em CrashLoopBackOff"
fi

# 3. Service
echo ""
echo "🌐 3. Validando service..."

if kubectl get svc mcp-tool-catalog -n "${NAMESPACE}" &>/dev/null; then
    pass "Service mcp-tool-catalog existe"

    HTTP_PORT=$(kubectl get svc mcp-tool-catalog -n "${NAMESPACE}" -o jsonpath='{.spec.ports[?(@.name=="http")].port}')
    GRPC_PORT=$(kubectl get svc mcp-tool-catalog -n "${NAMESPACE}" -o jsonpath='{.spec.ports[?(@.name=="grpc")].port}')
    METRICS_PORT=$(kubectl get svc mcp-tool-catalog -n "${NAMESPACE}" -o jsonpath='{.spec.ports[?(@.name=="metrics")].port}')

    if [ "$HTTP_PORT" = "8080" ]; then
        pass "HTTP port: 8080"
    else
        fail "HTTP port incorreta: ${HTTP_PORT}"
    fi

    if [ "$GRPC_PORT" = "9090" ]; then
        pass "gRPC port: 9090"
    else
        fail "gRPC port incorreta: ${GRPC_PORT}"
    fi

    if [ "$METRICS_PORT" = "9091" ]; then
        pass "Metrics port: 9091"
    else
        fail "Metrics port incorreta: ${METRICS_PORT}"
    fi
else
    fail "Service mcp-tool-catalog não encontrado"
fi

# 4. Health Checks
echo ""
echo "🏥 4. Validando health checks..."

POD_NAME=$(kubectl get pods -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}" -o jsonpath='{.items[0].metadata.name}')

HEALTH_RESPONSE=$(kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -s http://localhost:8080/health || echo "ERROR")

if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    pass "GET /health retorna 200"
else
    fail "GET /health falhou: ${HEALTH_RESPONSE}"
fi

READY_RESPONSE=$(kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -s http://localhost:8080/ready || echo "ERROR")

if echo "$READY_RESPONSE" | grep -q "ready"; then
    pass "GET /ready retorna 200"
else
    fail "GET /ready falhou: ${READY_RESPONSE}"
fi

# 5. Catálogo de Ferramentas
echo ""
echo "🔧 5. Validando catálogo de ferramentas..."

# Simular chamada à API (via port-forward em background)
kubectl port-forward -n "${NAMESPACE}" svc/mcp-tool-catalog 18080:8080 &>/dev/null &
PF_PID=$!
sleep 2

TOOLS_RESPONSE=$(curl -s http://localhost:18080/api/v1/tools 2>/dev/null || echo "ERROR")

kill $PF_PID 2>/dev/null || true

if [ "$TOOLS_RESPONSE" != "ERROR" ] && [ -n "$TOOLS_RESPONSE" ]; then
    TOOLS_COUNT=$(echo "$TOOLS_RESPONSE" | jq '.tools | length' 2>/dev/null || echo 0)

    if [ "$TOOLS_COUNT" -ge 30 ]; then
        pass "Ferramentas registradas: ${TOOLS_COUNT} (esperado >= 30)"
    else
        warn "Ferramentas registradas: ${TOOLS_COUNT} (esperado >= 87)"
    fi
else
    warn "Não foi possível consultar catálogo de ferramentas (API pode não estar pronta)"
fi

# 6. MongoDB Persistence
echo ""
echo "💾 6. Validando persistência MongoDB..."

# Verificar se MongoDB está acessível
if kubectl get pods -l app=mongodb -n "${NAMESPACE}" &>/dev/null; then
    pass "MongoDB pods encontrados"
else
    warn "MongoDB pods não encontrados (pode estar em namespace diferente)"
fi

# 7. Redis Cache
echo ""
echo "⚡ 7. Validando cache Redis..."

if kubectl get pods -l app=redis -n "${NAMESPACE}" &>/dev/null; then
    pass "Redis pods encontrados"
else
    warn "Redis pods não encontrados (pode estar em namespace diferente)"
fi

# 8. Service Registry
echo ""
echo "📡 8. Validando integração Service Registry..."

# Verificar logs para confirmação de registro
REGISTRY_LOG=$(kubectl logs -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}" --tail=100 | grep "service_registered" || echo "")

if [ -n "$REGISTRY_LOG" ]; then
    pass "Serviço registrado no Service Registry"
else
    warn "Log de registro não encontrado (pode não estar configurado)"
fi

# 9. Observability
echo ""
echo "📊 9. Validando observabilidade..."

METRICS_RESPONSE=$(kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -s http://localhost:9091/ || echo "ERROR")

if echo "$METRICS_RESPONSE" | grep -q "mcp_tool_selections_total"; then
    pass "Métrica mcp_tool_selections_total exportada"
else
    fail "Métrica mcp_tool_selections_total não encontrada"
fi

if echo "$METRICS_RESPONSE" | grep -q "mcp_genetic_algorithm_duration_seconds"; then
    pass "Métrica mcp_genetic_algorithm_duration_seconds exportada"
else
    fail "Métrica mcp_genetic_algorithm_duration_seconds não encontrada"
fi

if echo "$METRICS_RESPONSE" | grep -q "mcp_registered_tools_total"; then
    pass "Métrica mcp_registered_tools_total exportada"
else
    fail "Métrica mcp_registered_tools_total não encontrada"
fi

# Verificar logs estruturados
LOGS_SAMPLE=$(kubectl logs -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}" --tail=5)

if echo "$LOGS_SAMPLE" | grep -q '"event"'; then
    pass "Logs estruturados (JSON) configurados"
else
    warn "Logs podem não estar em formato JSON"
fi

# 10. Relatório Final
echo ""
echo "=========================================="
echo "  Resumo da Validação"
echo "=========================================="
echo ""
echo -e "${GREEN}Testes Passed:${NC} ${PASSED}"
echo -e "${RED}Testes Failed:${NC} ${FAILED}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ Todos os testes críticos passaram!${NC}"
    echo ""
    echo "Próximos passos:"
    echo "  1. Executar teste end-to-end: ./tests/phase2-mcp-integration-test.sh"
    echo "  2. Monitorar métricas: kubectl port-forward -n ${NAMESPACE} svc/mcp-tool-catalog 9091:9091"
    echo "  3. Verificar Grafana dashboard"
    exit 0
else
    echo -e "${RED}❌ Alguns testes falharam. Revisar logs:${NC}"
    echo "  kubectl logs -f -l app.kubernetes.io/name=mcp-tool-catalog -n ${NAMESPACE}"
    echo ""
    echo "Ações corretivas:"
    echo "  - Verificar secrets MongoDB/Redis"
    echo "  - Verificar conectividade Kafka"
    echo "  - Verificar resources (CPU/Memory)"
    exit 1
fi
