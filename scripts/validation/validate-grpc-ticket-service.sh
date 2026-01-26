#!/bin/bash
###############################################################################
# Validacao de Conectividade gRPC do Execution Ticket Service
# 
# Este script valida que o servidor gRPC do Execution Ticket Service esta
# operacional e acessivel pelo Orchestrator Dynamic.
###############################################################################

# set -e desabilitado para permitir que o script continue mesmo com falhas
# set -e

NAMESPACE="${NAMESPACE:-neural-hive}"
SERVICE_NAME="execution-ticket-service"
GRPC_PORT=50052

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNINGS=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

echo "=== Validando gRPC Execution Ticket Service ==="
echo "Namespace: $NAMESPACE"
echo "Service: $SERVICE_NAME"
echo "Porta gRPC: $GRPC_PORT"
echo ""

## 1. Verificar se pod esta rodando
log_info "1. Verificando pods..."
if kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME --no-headers 2>/dev/null | grep -q "Running"; then
    POD_COUNT=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME --no-headers | grep "Running" | wc -l)
    log_pass "Pods rodando: $POD_COUNT"
else
    log_fail "Nenhum pod rodando"
fi

## 2. Verificar logs de inicializacao gRPC
log_info "2. Verificando logs de inicializacao gRPC..."
PODNAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "$PODNAME" ]; then
    if kubectl logs -n $NAMESPACE $PODNAME --tail=100 2>/dev/null | grep -qi "grpc.*start\|grpc.*listen\|server.*50052"; then
        log_pass "gRPC server inicializado (logs indicam startup)"
    else
        log_warn "Log de inicializacao gRPC nao encontrado (pode usar formato diferente)"
    fi
else
    log_fail "Nao foi possivel obter nome do pod"
fi

## 3. Verificar porta gRPC esta aberta
log_info "3. Verificando conectividade de rede na porta gRPC..."
ORCHESTRATOR_POD=$(kubectl get pods -n $NAMESPACE -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "$ORCHESTRATOR_POD" ]; then
    if kubectl exec -n $NAMESPACE $ORCHESTRATOR_POD -- nc -zv $SERVICE_NAME $GRPC_PORT 2>&1 | grep -q "succeeded\|open"; then
        log_pass "Porta gRPC $GRPC_PORT acessivel do orchestrator"
    else
        # Tentar com timeout
        if kubectl exec -n $NAMESPACE $ORCHESTRATOR_POD -- timeout 5 bash -c "echo > /dev/tcp/$SERVICE_NAME/$GRPC_PORT" 2>/dev/null; then
            log_pass "Porta gRPC $GRPC_PORT acessivel do orchestrator"
        else
            log_fail "Porta gRPC $GRPC_PORT nao acessivel do orchestrator"
        fi
    fi
else
    log_warn "Orchestrator pod nao encontrado, testando do proprio pod do service"
    if kubectl exec -n $NAMESPACE $PODNAME -- nc -zv localhost $GRPC_PORT 2>&1 | grep -q "succeeded\|open"; then
        log_pass "Porta gRPC $GRPC_PORT aberta localmente"
    else
        log_warn "Nao foi possivel verificar porta gRPC"
    fi
fi

## 4. Verificar servicos gRPC disponiveis (se grpcurl disponivel)
log_info "4. Verificando servicos gRPC disponiveis..."
if [ -n "$ORCHESTRATOR_POD" ]; then
    GRPC_LIST=$(kubectl exec -n $NAMESPACE $ORCHESTRATOR_POD -- grpcurl -plaintext $SERVICE_NAME:$GRPC_PORT list 2>/dev/null || echo "")
    if [ -n "$GRPC_LIST" ]; then
        log_pass "Servicos gRPC listados com sucesso"
        echo "   Servicos: $(echo $GRPC_LIST | tr '\n' ' ')"
    else
        log_warn "grpcurl nao disponivel ou servico nao responde reflexion"
    fi
else
    log_warn "Nao foi possivel listar servicos gRPC"
fi

## 5. Verificar readiness probe gRPC
log_info "5. Verificando readiness probe..."
PROBE_INFO=$(kubectl get pod -n $NAMESPACE $PODNAME -o jsonpath='{.spec.containers[0].readinessProbe}' 2>/dev/null)

if echo "$PROBE_INFO" | grep -q "grpc"; then
    log_pass "Readiness probe configurado para gRPC"
elif echo "$PROBE_INFO" | grep -q "httpGet"; then
    log_warn "Readiness probe usando HTTP (recomendado: gRPC nativo)"
else
    log_warn "Configuracao de readiness probe nao identificada"
fi

# Verificar status do readiness
READY_STATUS=$(kubectl get pod -n $NAMESPACE $PODNAME -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
if [ "$READY_STATUS" = "True" ]; then
    log_pass "Pod esta Ready"
else
    log_fail "Pod nao esta Ready"
fi

## 6. Verificar metricas gRPC
log_info "6. Verificando metricas gRPC..."
PODNAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$PODNAME" ]; then
    METRICS=$(kubectl exec -n $NAMESPACE $PODNAME -- curl -s localhost:9090/metrics 2>/dev/null || echo "")
    
    if echo "$METRICS" | grep -q "grpc_server_handled_total"; then
        log_pass "Metrica grpc_server_handled_total presente"
    else
        log_warn "Metrica grpc_server_handled_total nao encontrada"
    fi
    
    if echo "$METRICS" | grep -q "grpc_server_handling_seconds"; then
        log_pass "Metrica grpc_server_handling_seconds presente"
    else
        log_warn "Metrica grpc_server_handling_seconds nao encontrada"
    fi
else
    log_warn "Nao foi possivel verificar metricas"
fi

## 7. Verificar service Kubernetes
log_info "7. Verificando Kubernetes Service..."
SVC_PORTS=$(kubectl get svc $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.spec.ports[*].port}' 2>/dev/null)

if echo "$SVC_PORTS" | grep -q "$GRPC_PORT"; then
    log_pass "Service expoe porta gRPC $GRPC_PORT"
else
    log_fail "Service nao expoe porta gRPC $GRPC_PORT"
fi

ENDPOINTS=$(kubectl get endpoints $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.subsets[0].addresses}' 2>/dev/null | wc -w)
if [ "$ENDPOINTS" -gt 0 ]; then
    log_pass "Service tem $ENDPOINTS endpoints ativos"
else
    log_fail "Service sem endpoints ativos"
fi

echo ""
echo "=== Resumo da Validacao ==="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"
echo -e "${RED}Failed: $FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo ""
    log_info "Validacao gRPC concluida com sucesso!"
    exit 0
else
    echo ""
    log_warn "Algumas validacoes falharam. Verificar logs detalhados."
    exit 1
fi
