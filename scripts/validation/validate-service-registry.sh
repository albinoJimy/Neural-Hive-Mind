#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -e

# Script de validação do Service Registry
# Uso: ./validate-service-registry.sh [--namespace NAMESPACE]

NAMESPACE="neural-hive-registry"
FAILED_TESTS=0
TOTAL_TESTS=0

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

test_result() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            log_error "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

log_info "Iniciando validação do Service Registry"
log_info "Namespace: $NAMESPACE"
echo ""

# TESTE 1: Verificar pods running
log_info "TESTE 1: Verificar pods running"
PODS_RUNNING=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=service-registry --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
if [ "$PODS_RUNNING" -ge 1 ]; then
    test_result 0 "Pods running: $PODS_RUNNING"
else
    test_result 1 "Nenhum pod running"
fi
echo ""

# TESTE 2: Verificar service endpoints
log_info "TESTE 2: Verificar service endpoints"
ENDPOINTS=$(kubectl get endpoints -n $NAMESPACE service-registry-service-registry -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | wc -w)
if [ "$ENDPOINTS" -ge 1 ]; then
    test_result 0 "Service endpoints ativos: $ENDPOINTS"
else
    test_result 1 "Nenhum endpoint ativo"
fi
echo ""

# TESTE 3: Testar health check gRPC
log_info "TESTE 3: Testar health check gRPC"
kubectl port-forward -n $NAMESPACE svc/service-registry-service-registry 50051:50051 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

if command -v grpcurl &> /dev/null; then
    if grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check > /dev/null 2>&1; then
        test_result 0 "Health check gRPC OK"
    else
        test_result 1 "Health check gRPC falhou"
    fi
else
    log_warn "grpcurl não disponível - pulando teste gRPC"
fi

kill $PF_PID 2>/dev/null || true
echo ""

# TESTE 4: Verificar métricas Prometheus
log_info "TESTE 4: Verificar métricas Prometheus"
kubectl port-forward -n $NAMESPACE svc/service-registry-service-registry 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

if curl -s http://localhost:9090/metrics | grep -q "agents_registered_total"; then
    test_result 0 "Métricas Prometheus expostas corretamente"
else
    test_result 1 "Métricas Prometheus não encontradas"
fi

kill $PF_PID 2>/dev/null || true
echo ""

# TESTE 5: Verificar logs do serviço
log_info "TESTE 5: Verificar logs do serviço"
LOGS=$(kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=service-registry --tail=50 2>/dev/null)

if echo "$LOGS" | grep -q "service_registry_initialized"; then
    test_result 0 "Service Registry inicializado nos logs"
else
    test_result 1 "Mensagem de inicialização não encontrada nos logs"
fi

if echo "$LOGS" | grep -q "etcd_client_initialized"; then
    test_result 0 "Cliente etcd inicializado"
else
    test_result 1 "Cliente etcd não inicializado"
fi

if echo "$LOGS" | grep -q "pheromone_client_initialized"; then
    test_result 0 "Cliente de feromônios inicializado"
else
    log_warn "Cliente de feromônios não inicializado (pode ser esperado)"
fi
echo ""

# TESTE 6: Verificar conectividade com etcd
log_info "TESTE 6: Verificar conectividade com etcd"
if echo "$LOGS" | grep -q "etcd_client_initialization_failed"; then
    test_result 1 "Falha ao conectar com etcd"
else
    test_result 0 "Conectividade com etcd OK"
fi
echo ""

# TESTE 7: Verificar recursos (CPU/Memory)
log_info "TESTE 7: Verificar uso de recursos"
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=service-registry --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "$POD_NAME" ]; then
    METRICS=$(kubectl top pod -n $NAMESPACE $POD_NAME 2>/dev/null || echo "metrics-server não disponível")
    if echo "$METRICS" | grep -q "CPU"; then
        test_result 0 "Métricas de recursos disponíveis"
        echo "$METRICS"
    else
        log_warn "metrics-server não disponível"
    fi
fi
echo ""

# TESTE 8: Verificar CRDs e configurações
log_info "TESTE 8: Verificar configurações"

# ConfigMap
if kubectl get configmap -n $NAMESPACE service-registry-service-registry-config > /dev/null 2>&1; then
    test_result 0 "ConfigMap presente"
else
    test_result 1 "ConfigMap não encontrado"
fi

# Secret
if kubectl get secret -n $NAMESPACE service-registry-service-registry-secret > /dev/null 2>&1; then
    test_result 0 "Secret presente"
else
    test_result 1 "Secret não encontrado"
fi

# ServiceMonitor (se Prometheus Operator instalado)
if kubectl get servicemonitor -n $NAMESPACE service-registry-service-registry > /dev/null 2>&1; then
    test_result 0 "ServiceMonitor configurado"
else
    log_warn "ServiceMonitor não encontrado (Prometheus Operator pode não estar instalado)"
fi
echo ""

# Relatório final
echo "========================================"
echo "RELATÓRIO DE VALIDAÇÃO"
echo "========================================"
echo "Total de testes: $TOTAL_TESTS"
echo "Testes aprovados: $((TOTAL_TESTS - FAILED_TESTS))"
echo "Testes falhados: $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    log_info "✅ Todos os testes passaram!"
    exit 0
else
    log_error "❌ $FAILED_TESTS teste(s) falharam"
    echo ""
    log_info "Dicas de troubleshooting:"
    log_info "1. Verificar logs completos: kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=service-registry"
    log_info "2. Verificar eventos: kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
    log_info "3. Verificar pods: kubectl describe pods -n $NAMESPACE -l app.kubernetes.io/name=service-registry"
    exit 1
fi
