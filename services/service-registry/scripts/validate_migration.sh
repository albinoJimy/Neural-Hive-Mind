#!/bin/bash
# validate_migration.sh - Valida migração etcd→Redis no Service Registry
# Uso: ./validate_migration.sh [namespace]

set -e

NAMESPACE=${1:-neural-hive}
CONTEXT=${KUBECONFIG:-"default"}

echo "=== Validando migração Service Registry ==="
echo "Namespace: $NAMESPACE"
echo "Context: $CONTEXT"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Contadores
PASS=0
FAIL=0
WARN=0

# Funções
check_pass() {
    echo -e "${GREEN}✅ $1${NC}"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}❌ $1${NC}"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    ((WARN++))
}

# 1. Verificar pods
echo "1. Verificando pods..."
POD_COUNT=$(kubectl get pods -n "$NAMESPACE" -l app=service-registry --no-headers 2>/dev/null | wc -l || echo "0")
READY_COUNT=$(kubectl get pods -n "$NAMESPACE" -l app=service-registry --no-headers 2>/dev/null | grep -c Running || true)

if [ "$POD_COUNT" -eq "0" ]; then
    check_fail "Nenhum pod encontrado (label app=service-registry)"
elif [ "$POD_COUNT" -eq "$READY_COUNT" ]; then
    check_pass "Todos os pods running ($READY_COUNT/$POD_COUNT)"
else
    check_fail "Pods não ready: $READY_COUNT/$POD_COUNT"
fi

# 2. Verificar logs por erros
echo ""
echo "2. Verificando logs por erros..."
ERRORS=$(kubectl logs -n "$NAMESPACE" deployment/service-registry --tail=50 2>/dev/null | grep -i "error" || true)
if [ -z "$ERRORS" ]; then
    check_pass "Sem erros nos logs"
else
    check_fail "Erros encontrados nos logs"
    echo "$ERRORS" | head -5
fi

# 3. Verificar warnings de deprecation (esperado na Fase 1)
echo ""
echo "3. Verificando warnings de deprecation..."
DEPRECATED=$(kubectl logs -n "$NAMESPACE" deployment/service-registry 2>/dev/null | grep -i "deprecated" || true)
if [ -n "$DEPRECATED" ]; then
    check_warn "Configs ETCD_* deprecated em uso (normal na Fase 1)"
    echo "$DEPRECATED" | head -3
else
    check_pass "Nenhuma config deprecated em uso"
fi

# 4. Verificar inicialização do Redis client
echo ""
echo "4. Verificando Redis client..."
REDIS_LOG=$(kubectl logs -n "$NAMESPACE" deployment/service-registry 2>/dev/null | grep "redis_registry_client_initialized" || true)
if [ -n "$REDIS_LOG" ]; then
    check_pass "Redis client inicializado"
    echo "$REDIS_LOG" | head -1
else
    check_fail "Redis client não inicializado"
fi

# 5. Health check gRPC
echo ""
echo "5. Verificando health check gRPC..."
HEALTH_OUTPUT=$(kubectl exec -n "$NAMESPACE" deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 grpc.health.v1.Health/Check 2>/dev/null || echo "")

if echo "$HEALTH_OUTPUT" | grep -q "SERVING"; then
    check_pass "gRPC health check: SERVING"
else
    check_fail "gRPC health check falhou"
fi

# 6. ListAgents API
echo ""
echo "6. Verificando API ListAgents..."
API_OUTPUT=$(kubectl exec -n "$NAMESPACE" deployment/service-registry -- \
    grpcurl -plaintext localhost:8000 \
    neural_hive.service_registry.v1.ServiceRegistry/ListAgents 2>/dev/null || echo "")

if echo "$API_OUTPUT" | grep -q "agents"; then
    check_pass "API ListAgents respondendo"
    AGENT_COUNT=$(echo "$API_OUTPUT" | grep -o "agent_id" | wc -l)
    echo "   Agentes registrados: $AGENT_COUNT"
else
    check_fail "API ListAgents não respondendo"
fi

# 7. Verificar ConfigMap
echo ""
echo "7. Verificando ConfigMap..."
CONFIG_HAS_NEW=$(kubectl get configmap -n "$NAMESPACE" service-registry-config -o jsonpath='{.data.REGISTRY_REDIS_ENDPOINTS}' 2>/dev/null || echo "")
CONFIG_HAS_OLD=$(kubectl get configmap -n "$NAMESPACE" service-registry-config -o jsonpath='{.data.ETCD_ENDPOINTS}' 2>/dev/null || echo "")

if [ -n "$CONFIG_HAS_NEW" ]; then
    check_pass "ConfigMap usa REGISTRY_REDIS_* (novos nomes)"
elif [ -n "$CONFIG_HAS_OLD" ]; then
    check_warn "ConfigMap usa ETCD_* (nomes legados, migrar em v1.4.0)"
else
    check_fail "ConfigMap não encontrado ou sem configs relevantes"
fi

# 8. Verificar endpoints
echo ""
echo "8. Verificando Kubernetes endpoints..."
ENDPOINTS=$(kubectl get endpoints -n "$NAMESPACE" service-registry -o jsonpath='{.subsets[*].addresses[*]}' 2>/dev/null || echo "")
if [ -n "$ENDPOINTS" ]; then
    check_pass "Endpoints service-registry disponíveis"
else
    check_fail "Nenhum endpoint service-registry"
fi

# Resumo
echo ""
echo "=== Resumo da Validação ==="
echo -e "${GREEN}Passou: $PASS${NC}"
echo -e "${YELLOW}Warnings: $WARN${NC}"
echo -e "${RED}Falhou: $FAIL${NC}"
echo ""

if [ "$FAIL" -gt "0" ]; then
    echo -e "${RED}❌ Validação FALHOU${NC}"
    echo "Verifique os erros acima ou consulte:"
    echo "  - docs/service-registry/ROLLBACK_ETCD_TO_REDIS.md"
    exit 1
elif [ "$WARN" -gt "0" ]; then
    echo -e "${YELLOW}⚠️  Validação com WARNINGS${NC}"
    echo "Warnings são aceitáveis na Fase 1 (v1.3.0)"
    echo "Planeje migração completa para v1.4.0"
    exit 0
else
    echo -e "${GREEN}✅ Validação COMPLETA${NC}"
    echo "Migração validada com sucesso!"
    exit 0
fi
