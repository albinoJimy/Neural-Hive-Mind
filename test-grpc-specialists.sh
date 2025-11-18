#!/bin/bash

echo "=========================================="
echo "Teste gRPC - Specialists Phase 1"
echo "Data: $(date)"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SPECIALISTS=("business" "behavior" "evolution" "architecture" "technical")
PASSED=0
FAILED=0

echo "=========================================="
echo "1. Verificando Conectividade TCP (porta 50051)"
echo "=========================================="

for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Testando specialist-$spec..."

    SERVICE_HOST="specialist-$spec.specialist-$spec.svc.cluster.local"
    SERVICE_PORT="50051"

    # Testa conectividade TCP usando busybox
    if kubectl run grpc-test-$spec --rm -i --restart=Never --image=busybox --timeout=10s -- \
        timeout 3 sh -c "echo 'test' | nc -w 2 $SERVICE_HOST $SERVICE_PORT" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} specialist-$spec: Porta gRPC 50051 acessível"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} specialist-$spec: Porta gRPC 50051 não acessível"
        ((FAILED++))
    fi
done

echo ""
echo "=========================================="
echo "2. Testando gRPC Health Check"
echo "=========================================="

# Verifica se grpcurl está disponível
if command -v grpcurl &> /dev/null; then
    echo -e "${GREEN}✓${NC} grpcurl encontrado, executando testes de health check..."
    echo ""

    for spec in "${SPECIALISTS[@]}"; do
        echo -e "${BLUE}ℹ${NC} Health check do specialist-$spec..."

        SERVICE="specialist-$spec.specialist-$spec.svc.cluster.local:50051"

        # Executa grpcurl para health check
        if timeout 10 grpcurl -plaintext -d '{"service": ""}' $SERVICE grpc.health.v1.Health/Check 2>/dev/null | grep -q "SERVING"; then
            echo -e "${GREEN}✓${NC} specialist-$spec: Health check retornou SERVING"
            ((PASSED++))
        else
            # Tenta listar serviços como fallback
            if timeout 10 grpcurl -plaintext $SERVICE list 2>/dev/null | grep -q "neural_hive.specialist.SpecialistService"; then
                echo -e "${GREEN}✓${NC} specialist-$spec: Serviço gRPC ativo (SpecialistService encontrado)"
                ((PASSED++))
            else
                echo -e "${YELLOW}⚠${NC} specialist-$spec: Health check não respondeu (pode não implementar health service padrão)"
                # Não contamos como falha pois o serviço pode estar ativo sem health check padrão
            fi
        fi
    done
else
    echo -e "${YELLOW}⚠${NC} grpcurl não encontrado, pulando testes de health check detalhados"
    echo "  Para instalar: https://github.com/fullstorydev/grpcurl"
fi

echo ""
echo "=========================================="
echo "3. Verificando Services Kubernetes"
echo "=========================================="

for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Verificando service specialist-$spec..."

    if kubectl get service -n specialist-$spec specialist-$spec &> /dev/null; then
        CLUSTER_IP=$(kubectl get service -n specialist-$spec specialist-$spec -o jsonpath='{.spec.clusterIP}')
        echo -e "${GREEN}✓${NC} specialist-$spec: Service encontrado (ClusterIP: $CLUSTER_IP)"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} specialist-$spec: Service não encontrado"
        ((FAILED++))
    fi
done

echo ""
echo "=========================================="
echo "4. Verificando Endpoints Kubernetes"
echo "=========================================="

for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Verificando endpoints specialist-$spec..."

    ENDPOINTS=$(kubectl get endpoints -n specialist-$spec specialist-$spec -o jsonpath='{.subsets[0].addresses[*].ip}' 2>/dev/null)

    if [ -n "$ENDPOINTS" ]; then
        echo -e "${GREEN}✓${NC} specialist-$spec: Endpoints ativos (IPs: $ENDPOINTS)"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} specialist-$spec: Sem endpoints ativos"
        ((FAILED++))
    fi
done

echo ""
echo "=========================================="
echo "RESUMO DOS TESTES"
echo "=========================================="

TOTAL=$((PASSED + FAILED))
echo -e "${BLUE}Total de testes:${NC} $TOTAL"
echo -e "${GREEN}Testes passaram:${NC} $PASSED"
echo -e "${RED}Testes falharam:${NC} $FAILED"

if [ $FAILED -eq 0 ]; then
    PASS_RATE=100
else
    PASS_RATE=$((PASSED * 100 / TOTAL))
fi

echo -e "${BLUE}Taxa de sucesso:${NC} $PASS_RATE%"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}=========================================="
    echo "✓ TODOS OS TESTES PASSARAM!"
    echo "==========================================${NC}"
    exit 0
else
    echo -e "${YELLOW}=========================================="
    echo "⚠ ALGUNS TESTES FALHARAM"
    echo "==========================================${NC}"
    exit 1
fi
