#!/bin/bash

echo "=========================================="
echo "Teste Simples dos Specialists - Fase 1"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SPECIALISTS=("business" "behavior" "evolution" "architecture" "technical")

echo "=========================================="
echo "1. Verificando Cluster Kubernetes"
echo "=========================================="
if kubectl cluster-info > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Cluster Kubernetes acessível"
else
    echo -e "${RED}✗${NC} Cluster Kubernetes inacessível"
    exit 1
fi
echo ""

echo "=========================================="
echo "2. Verificando Deployments dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Verificando specialist-$spec..."

    if kubectl get deployment -n specialist-$spec specialist-$spec > /dev/null 2>&1; then
        READY=$(kubectl get deployment -n specialist-$spec specialist-$spec -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        DESIRED=$(kubectl get deployment -n specialist-$spec specialist-$spec -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")

        if [ "$READY" = "$DESIRED" ]; then
            echo -e "${GREEN}✓${NC} specialist-$spec: $READY/$DESIRED replicas prontas"
        else
            echo -e "${RED}✗${NC} specialist-$spec: $READY/$DESIRED replicas prontas"
        fi
    else
        echo -e "${RED}✗${NC} specialist-$spec: deployment não encontrado"
    fi
done
echo ""

echo "=========================================="
echo "3. Verificando Pods dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Verificando pod do specialist-$spec..."

    POD_STATUS=$(kubectl get pods -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")

    if [ "$POD_STATUS" = "Running" ]; then
        echo -e "${GREEN}✓${NC} specialist-$spec: pod Running"
    else
        echo -e "${RED}✗${NC} specialist-$spec: pod status = $POD_STATUS"
    fi
done
echo ""

echo "=========================================="
echo "4. Verificando Services dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Verificando service do specialist-$spec..."

    if kubectl get service -n specialist-$spec specialist-$spec > /dev/null 2>&1; then
        CLUSTER_IP=$(kubectl get service -n specialist-$spec specialist-$spec -o jsonpath='{.spec.clusterIP}')
        PORTS=$(kubectl get service -n specialist-$spec specialist-$spec -o jsonpath='{.spec.ports[*].port}')
        echo -e "${GREEN}✓${NC} specialist-$spec: service ativo (IP: $CLUSTER_IP, Portas: $PORTS)"
    else
        echo -e "${RED}✗${NC} specialist-$spec: service não encontrado"
    fi
done
echo ""

echo "=========================================="
echo "5. Verificando Logs dos Specialists"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Verificando logs do specialist-$spec..."

    POD_NAME=$(kubectl get pods -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$POD_NAME" ]; then
        if kubectl logs -n specialist-$spec "$POD_NAME" --tail=50 2>/dev/null | grep -q "gRPC server started"; then
            echo -e "${GREEN}✓${NC} specialist-$spec: gRPC server iniciado"
        else
            echo -e "${YELLOW}⚠${NC} specialist-$spec: gRPC server não confirmado nos logs"
        fi

        if kubectl logs -n specialist-$spec "$POD_NAME" --tail=50 2>/dev/null | grep -q "Uvicorn running\|HTTP server started"; then
            echo -e "${GREEN}✓${NC} specialist-$spec: HTTP server iniciado"
        else
            echo -e "${YELLOW}⚠${NC} specialist-$spec: HTTP server não confirmado nos logs"
        fi
    else
        echo -e "${RED}✗${NC} specialist-$spec: pod não encontrado para verificar logs"
    fi
done
echo ""

echo "=========================================="
echo "6. Verificando Últimas Linhas dos Logs"
echo "=========================================="
for spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Últimas 5 linhas do specialist-$spec:"

    POD_NAME=$(kubectl get pods -n specialist-$spec -l app.kubernetes.io/name=specialist-$spec -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$POD_NAME" ]; then
        kubectl logs -n specialist-$spec "$POD_NAME" --tail=5 2>/dev/null | sed 's/^/  /'
    else
        echo -e "${RED}✗${NC} Pod não encontrado"
    fi
    echo ""
done

echo "=========================================="
echo "TESTE CONCLUÍDO"
echo "=========================================="
