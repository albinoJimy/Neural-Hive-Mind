#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -e

echo "=== Validação de Políticas OPA ==="

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Verificar se OPA está instalado
if ! command -v opa &> /dev/null; then
    echo -e "${RED}❌ OPA CLI não encontrado. Instale com: brew install opa${NC}"
    exit 1
fi

echo -e "${GREEN}✅ OPA CLI encontrado${NC}"

# Diretório de políticas
POLICIES_DIR="policies/rego/orchestrator"

# 1. Validar sintaxe das políticas
echo ""
echo "=== 1. Validando sintaxe das políticas ==="
for policy in "$POLICIES_DIR"/*.rego; do
    echo -n "Validando $(basename "$policy")... "
    if opa check "$policy" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        opa check "$policy"
        exit 1
    fi
done

# 2. Executar testes unitários
echo ""
echo "=== 2. Executando testes unitários ==="
if opa test "$POLICIES_DIR" -v; then
    echo -e "${GREEN}✅ Todos os testes passaram${NC}"
else
    echo -e "${RED}❌ Alguns testes falharam${NC}"
    exit 1
fi

# 3. Verificar coverage
echo ""
echo "=== 3. Verificando coverage ==="
COVERAGE=$(opa test "$POLICIES_DIR" --coverage --format=json | jq -r '.coverage')
echo "Coverage: ${COVERAGE}%"

if (( $(echo "$COVERAGE >= 80" | bc -l) )); then
    echo -e "${GREEN}✅ Coverage acima de 80%${NC}"
else
    echo -e "${YELLOW}⚠️  Coverage abaixo de 80%${NC}"
fi

# 4. Validar políticas contra schema
echo ""
echo "=== 4. Validando políticas contra schema ==="
# TODO: Implementar validação de schema se disponível

# 5. Testar políticas com OPA server local
echo ""
echo "=== 5. Testando com OPA server local ==="
echo "Iniciando OPA server..."
opa run --server --addr=localhost:8282 "$POLICIES_DIR" &
OPA_PID=$!
sleep 2

# Testar endpoint de health
if curl -s http://localhost:8282/health | grep -q "ok"; then
    echo -e "${GREEN}✅ OPA server respondendo${NC}"
else
    echo -e "${RED}❌ OPA server não respondeu${NC}"
    kill $OPA_PID
    exit 1
fi

# Testar avaliação de política
echo "Testando avaliação de security_constraints..."
RESULT=$(curl -s -X POST http://localhost:8282/v1/data/neuralhive/orchestrator/security_constraints \
    -H "Content-Type: application/json" \
    -d '{
        "input": {
            "resource": {
                "ticket_id": "test-123",
                "tenant_id": "tenant-123",
                "namespace": "production",
                "required_capabilities": ["code_generation"],
                "data_classification": "confidential",
                "contains_pii": true
            },
            "context": {
                "current_time": 1700000000000,
                "user_id": "user@example.com",
                "jwt_token": "eyJhbGc.eyJzdWI.signature",
                "source_ip": "10.0.0.1",
                "request_count_last_minute": 45
            },
            "security": {
                "spiffe_enabled": true,
                "allowed_tenants": ["tenant-123"],
                "rbac_roles": {"user@example.com": ["developer"]},
                "tenant_rate_limits": {"tenant-123": 100}
            }
        }
    }')

if echo "$RESULT" | jq -e '.result.allow == true' > /dev/null; then
    echo -e "${GREEN}✅ Política avaliada com sucesso${NC}"
else
    echo -e "${RED}❌ Erro na avaliação da política${NC}"
    echo "$RESULT" | jq .
    kill $OPA_PID
    exit 1
fi

# Cleanup
kill $OPA_PID
echo ""
echo -e "${GREEN}=== ✅ Todas as validações passaram ===${NC}"
