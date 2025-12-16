#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/../../scripts/lib/common.sh"

echo "=========================================="
echo "Teste de Conectividade entre Specialists"
echo "Data: $(date)"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SPECIALISTS=("business" "behavior" "evolution" "architecture" "technical")

echo "=========================================="
echo "1. Testando DNS Resolution entre Specialists"
echo "=========================================="

for source_spec in "${SPECIALISTS[@]}"; do
    echo -e "${BLUE}ℹ${NC} Testando DNS do specialist-$source_spec..."

    POD=$(kubectl get pods -n specialist-$source_spec -l app.kubernetes.io/name=specialist-$source_spec -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$POD" ]; then
        echo -e "${RED}✗${NC} Pod specialist-$source_spec não encontrado"
        continue
    fi

    # Testa DNS para outros specialists
    for target_spec in "${SPECIALISTS[@]}"; do
        if [ "$source_spec" != "$target_spec" ]; then
            TARGET_HOST="specialist-$target_spec.specialist-$target_spec.svc.cluster.local"

            # Testa resolução DNS
            if kubectl exec -n specialist-$source_spec $POD -- sh -c "getent hosts $TARGET_HOST" &> /dev/null; then
                echo -e "  ${GREEN}✓${NC} $source_spec → $target_spec: DNS resolve OK"
            else
                echo -e "  ${RED}✗${NC} $source_spec → $target_spec: DNS resolution falhou"
            fi
        fi
    done
    echo ""
done

echo "=========================================="
echo "2. Testando Conectividade de Rede (ping/telnet)"
echo "=========================================="

# Usar specialist-business como origem do teste
SOURCE_SPEC="business"
SOURCE_POD=$(kubectl get pods -n specialist-$SOURCE_SPEC -l app.kubernetes.io/name=specialist-$SOURCE_SPEC -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$SOURCE_POD" ]; then
    echo -e "${RED}✗${NC} Pod specialist-$SOURCE_SPEC não encontrado para testes"
else
    echo -e "${BLUE}ℹ${NC} Usando specialist-$SOURCE_SPEC como origem dos testes"
    echo ""

    for target_spec in "${SPECIALISTS[@]}"; do
        if [ "$SOURCE_SPEC" != "$target_spec" ]; then
            echo -e "${BLUE}ℹ${NC} Testando conectividade: $SOURCE_SPEC → $target_spec"

            TARGET_HOST="specialist-$target_spec.specialist-$target_spec.svc.cluster.local"
            TARGET_GRPC_PORT="50051"
            TARGET_HTTP_PORT="8000"

            # Testa porta gRPC (50051)
            if kubectl exec -n specialist-$SOURCE_SPEC $SOURCE_POD -- timeout 3 sh -c "echo 'test' | nc -w 2 $TARGET_HOST $TARGET_GRPC_PORT" &> /dev/null; then
                echo -e "  ${GREEN}✓${NC} Porta gRPC $TARGET_GRPC_PORT acessível"
            else
                echo -e "  ${RED}✗${NC} Porta gRPC $TARGET_GRPC_PORT não acessível"
            fi

            # Testa porta HTTP (8000)
            if kubectl exec -n specialist-$SOURCE_SPEC $SOURCE_POD -- timeout 3 sh -c "echo 'test' | nc -w 2 $TARGET_HOST $TARGET_HTTP_PORT" &> /dev/null; then
                echo -e "  ${GREEN}✓${NC} Porta HTTP $TARGET_HTTP_PORT acessível"
            else
                echo -e "  ${RED}✗${NC} Porta HTTP $TARGET_HTTP_PORT não acessível"
            fi
            echo ""
        fi
    done
fi

echo "=========================================="
echo "3. Testando HTTP Health Endpoints"
echo "=========================================="

if [ -n "$SOURCE_POD" ]; then
    for target_spec in "${SPECIALISTS[@]}"; do
        echo -e "${BLUE}ℹ${NC} Testando health endpoint do specialist-$target_spec"

        TARGET_HOST="specialist-$target_spec.specialist-$target_spec.svc.cluster.local"

        # Testa endpoint /health
        HEALTH_RESPONSE=$(kubectl exec -n specialist-$SOURCE_SPEC $SOURCE_POD -- wget -qO- --timeout=5 http://$TARGET_HOST:8000/health 2>/dev/null)

        if [ $? -eq 0 ]; then
            echo -e "  ${GREEN}✓${NC} Health endpoint respondeu"
            echo "  Resposta: ${HEALTH_RESPONSE:0:100}"
        else
            echo -e "  ${RED}✗${NC} Health endpoint não respondeu"
        fi
        echo ""
    done
fi

echo "=========================================="
echo "4. Resumo da Matriz de Conectividade"
echo "=========================================="

echo ""
echo "Legenda:"
echo "  ✓ = Conectividade OK"
echo "  ✗ = Conectividade FALHOU"
echo ""
echo "Conectividade testada de specialist-$SOURCE_SPEC para todos os outros:"
echo ""

for target_spec in "${SPECIALISTS[@]}"; do
    if [ "$SOURCE_SPEC" != "$target_spec" ]; then
        TARGET_HOST="specialist-$target_spec.specialist-$target_spec.svc.cluster.local"

        # Teste rápido de conectividade
        if kubectl exec -n specialist-$SOURCE_SPEC $SOURCE_POD -- timeout 2 sh -c "echo 'test' | nc -w 1 $TARGET_HOST 50051" &> /dev/null; then
            echo -e "  specialist-$SOURCE_SPEC → specialist-$target_spec: ${GREEN}✓ CONECTADO${NC}"
        else
            echo -e "  specialist-$SOURCE_SPEC → specialist-$target_spec: ${RED}✗ DESCONECTADO${NC}"
        fi
    fi
done

echo ""
echo "=========================================="
echo "TESTE CONCLUÍDO"
echo "=========================================="
