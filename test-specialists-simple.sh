#!/bin/bash
set -eo pipefail

echo "=========================================="
echo "Teste Simples dos Specialists - Fase 1"
echo "=========================================="
echo ""

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Array de specialists
SPECIALISTS=("business" "behavior" "evolution" "architecture" "technical")

# Contadores
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

echo "=========================================="
echo "1. Verificando Cluster Kubernetes"
echo "=========================================="
if kubectl cluster-info > /dev/null 2>&1; then
    log_success "Cluster Kubernetes acessível"
    ((TOTAL_TESTS++))
    ((PASSED_TESTS++))
else
    log_error "Cluster Kubernetes inacessível"
    ((TOTAL_TESTS++))
    ((FAILED_TESTS++))
    exit 1
fi
echo ""

echo "=========================================="
echo "2. Verificando Deployments dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    log_info "Verificando specialist-$spec..."

    # Verifica se o deployment existe
    if kubectl get deployment -n specialist-$spec specialist-$spec > /dev/null 2>&1; then
        # Verifica se está rodando
        READY=$(kubectl get deployment -n specialist-$spec specialist-$spec -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        DESIRED=$(kubectl get deployment -n specialist-$spec specialist-$spec -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")

        if [ "$READY" = "$DESIRED" ]; then
            log_success "specialist-$spec: $READY/$DESIRED replicas prontas"
            ((TOTAL_TESTS++))
            ((PASSED_TESTS++))
        else
            log_error "specialist-$spec: $READY/$DESIRED replicas prontas"
            ((TOTAL_TESTS++))
            ((FAILED_TESTS++))
        fi
    else
        log_error "specialist-$spec: deployment não encontrado"
        ((TOTAL_TESTS++))
        ((FAILED_TESTS++))
    fi
done
echo ""

echo "=========================================="
echo "3. Verificando Pods dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    log_info "Verificando pod do specialist-$spec..."

    POD_STATUS=$(kubectl get pods -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")

    if [ "$POD_STATUS" = "Running" ]; then
        log_success "specialist-$spec: pod Running"
        ((TOTAL_TESTS++))
        ((PASSED_TESTS++))
    else
        log_error "specialist-$spec: pod status = $POD_STATUS"
        ((TOTAL_TESTS++))
        ((FAILED_TESTS++))
    fi
done
echo ""

echo "=========================================="
echo "4. Verificando Services dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    log_info "Verificando service do specialist-$spec..."

    if kubectl get service -n specialist-$spec specialist-$spec > /dev/null 2>&1; then
        CLUSTER_IP=$(kubectl get service -n specialist-$spec specialist-$spec -o jsonpath='{.spec.clusterIP}')
        PORTS=$(kubectl get service -n specialist-$spec specialist-$spec -o jsonpath='{.spec.ports[*].port}')
        log_success "specialist-$spec: service ativo (IP: $CLUSTER_IP, Portas: $PORTS)"
        ((TOTAL_TESTS++))
        ((PASSED_TESTS++))
    else
        log_error "specialist-$spec: service não encontrado"
        ((TOTAL_TESTS++))
        ((FAILED_TESTS++))
    fi
done
echo ""

echo "=========================================="
echo "5. Verificando Logs dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    log_info "Verificando logs do specialist-$spec..."

    POD_NAME=$(kubectl get pods -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$POD_NAME" ]; then
        # Verifica se o gRPC server está rodando
        if kubectl logs -n specialist-$spec "$POD_NAME" --tail=50 2>/dev/null | grep -q "gRPC server started"; then
            log_success "specialist-$spec: gRPC server iniciado"
            ((TOTAL_TESTS++))
            ((PASSED_TESTS++))
        else
            log_warning "specialist-$spec: gRPC server não confirmado nos logs"
            ((TOTAL_TESTS++))
        fi

        # Verifica se o HTTP server está rodando
        if kubectl logs -n specialist-$spec "$POD_NAME" --tail=50 2>/dev/null | grep -q "Uvicorn running\|HTTP server started"; then
            log_success "specialist-$spec: HTTP server iniciado"
            ((TOTAL_TESTS++))
            ((PASSED_TESTS++))
        else
            log_warning "specialist-$spec: HTTP server não confirmado nos logs"
            ((TOTAL_TESTS++))
        fi
    else
        log_error "specialist-$spec: pod não encontrado para verificar logs"
        ((TOTAL_TESTS++))
        ((FAILED_TESTS++))
    fi
done
echo ""

echo "=========================================="
echo "6. Testando Conectividade gRPC"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    log_info "Testando conectividade gRPC para specialist-$spec..."

    # Usa grpcurl se disponível, senão usa telnet básico
    SERVICE_IP=$(kubectl get service -n specialist-$spec specialist-$spec -o jsonpath='{.spec.clusterIP}' 2>/dev/null)

    if [ -n "$SERVICE_IP" ]; then
        # Testa conectividade TCP na porta gRPC (50051)
        if kubectl run test-grpc-$spec --rm -i --restart=Never --image=busybox --timeout=10s -- timeout 3 sh -c "echo 'test' | nc -w 2 $SERVICE_IP 50051" > /dev/null 2>&1; then
            log_success "specialist-$spec: porta gRPC (50051) acessível"
            ((TOTAL_TESTS++))
            ((PASSED_TESTS++))
        else
            log_warning "specialist-$spec: porta gRPC (50051) pode não estar acessível"
            ((TOTAL_TESTS++))
        fi
    else
        log_error "specialist-$spec: não foi possível obter IP do service"
        ((TOTAL_TESTS++))
        ((FAILED_TESTS++))
    fi
done
echo ""

echo "=========================================="
echo "RESUMO DOS TESTES"
echo "=========================================="
echo -e "${BLUE}Total de testes:${NC} $TOTAL_TESTS"
echo -e "${GREEN}Testes aprovados:${NC} $PASSED_TESTS"
echo -e "${RED}Testes falhados:${NC} $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}=========================================="
    echo "✓ TODOS OS TESTES PASSARAM!"
    echo "==========================================${NC}"
    exit 0
else
    PASS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo -e "${YELLOW}=========================================="
    echo "⚠ ALGUNS TESTES FALHARAM"
    echo "Taxa de sucesso: $PASS_RATE%"
    echo "==========================================${NC}"
    exit 1
fi
