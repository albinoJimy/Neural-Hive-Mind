#!/bin/bash
#
# Neural Hive-Mind - Validação Completa Fase 3
# Verifica todos os componentes da aplicação
#
# Autor: Claude Code
# Data: 2025-10-30
#

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Função para track checks
track_check() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ $1 -eq 0 ]; then
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        echo -e "${GREEN}[✓]${NC} $2"
    else
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        echo -e "${RED}[✗]${NC} $2"
    fi
}

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║       NEURAL HIVE-MIND - VALIDAÇÃO COMPLETA FASE 3           ║
║              Serviços de Aplicação + Infraestrutura          ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BLUE}[INFO]${NC} Iniciando validação completa..."
echo ""

# ============================================================================
# FASE 2 - INFRAESTRUTURA
# ============================================================================

echo -e "${YELLOW}=== FASE 2 - INFRAESTRUTURA ===${NC}"
echo ""

echo -e "${BLUE}[INFO]${NC} Verificando Redis..."
kubectl get pods -n redis-cluster -o jsonpath='{.items[0].status.phase}' | grep -q "Running"
track_check $? "Redis pod running"

kubectl exec -n redis-cluster $(kubectl get pod -n redis-cluster -o jsonpath='{.items[0].metadata.name}') -- redis-cli ping | grep -q "PONG"
track_check $? "Redis PING OK"

echo ""
echo -e "${BLUE}[INFO]${NC} Verificando MongoDB..."
kubectl get pods -n mongodb-cluster -o jsonpath='{.items[0].status.phase}' | grep -q "Running"
track_check $? "MongoDB pod running"

kubectl exec -n mongodb-cluster $(kubectl get pod -n mongodb-cluster -l app.kubernetes.io/name=mongodb -o jsonpath='{.items[0].metadata.name}') -- mongosh mongodb://root:local_dev_password@localhost:27017/admin?authSource=admin --eval "db.adminCommand('ping')" --quiet | grep -q "ok.*1"
track_check $? "MongoDB PING OK"

echo ""
echo -e "${BLUE}[INFO]${NC} Verificando Kafka..."
kubectl get pods -n kafka -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].status.phase}' | grep -q "Running"
track_check $? "Kafka broker running"

TOPIC_COUNT=$(kubectl get kafkatopic -n kafka | grep -c intentions- || echo 0)
[ "$TOPIC_COUNT" -eq 5 ]
track_check $? "Kafka topics criados (5 intentions topics)"

# ============================================================================
# FASE 3 - APLICAÇÃO
# ============================================================================

echo ""
echo -e "${YELLOW}=== FASE 3 - APLICAÇÃO ===${NC}"
echo ""

echo -e "${BLUE}[INFO]${NC} Verificando Neo4j..."
kubectl get pods -n neo4j-cluster -o jsonpath='{.items[0].status.phase}' | grep -q "Running"
track_check $? "Neo4j pod running"

echo ""
echo -e "${BLUE}[INFO]${NC} Verificando Schema Registry (Apicurio)..."
kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].status.phase}' | grep -q "Running"
track_check $? "Apicurio Registry pod running"

APICURIO_POD=$(kubectl get pod -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n kafka $APICURIO_POD -- curl -sf http://localhost:8080/health/ready > /dev/null
track_check $? "Apicurio Registry health OK"

kubectl exec -n kafka $APICURIO_POD -- curl -sf http://localhost:8080/apis/ccompat/v6/subjects > /dev/null
track_check $? "Confluent API compatibility enabled"

echo ""
echo -e "${BLUE}[INFO]${NC} Verificando Gateway de Intenções..."
kubectl get pods -n gateway -o jsonpath='{.items[0].status.phase}' | grep -q "Running"
track_check $? "Gateway pod running"

GATEWAY_POD=$(kubectl get pod -n gateway -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n gateway $GATEWAY_POD -- curl -sf http://localhost:8000/health > /dev/null
track_check $? "Gateway health endpoint OK"

# Verificar componentes internos do Gateway
HEALTH_RESPONSE=$(kubectl exec -n gateway $GATEWAY_POD -- curl -s http://localhost:8000/health)
echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"'
track_check $? "Gateway status healthy"

echo "$HEALTH_RESPONSE" | grep -q '"redis":{"status":"healthy"}'
track_check $? "Gateway Redis component healthy"

echo "$HEALTH_RESPONSE" | grep -q '"kafka_producer":{"status":"healthy"}'
track_check $? "Gateway Kafka producer healthy"

# ============================================================================
# TESTE END-TO-END
# ============================================================================

echo ""
echo -e "${YELLOW}=== TESTE END-TO-END ===${NC}"
echo ""

echo -e "${BLUE}[INFO]${NC} Testando envio de intenção..."

# Criar pod temporário para teste
INTENT_RESPONSE=$(kubectl run test-intent-validator --rm -i --restart=Never --image=curlimages/curl -- sh -c '
curl -s -X POST http://gateway-intencoes.gateway.svc.cluster.local:8000/intentions \
  -H "Content-Type: application/json" \
  -d "{
    \"text\": \"Criar sistema de autenticação com multi-fator\",
    \"metadata\": {
      \"source\": \"validation-test\",
      \"user_id\": \"validator-001\"
    }
  }"
' 2>&1 | grep -v "pod.*deleted" | grep -v "command prompt")

echo "$INTENT_RESPONSE" | grep -q '"intent_id"'
track_check $? "Intenção criada com sucesso"

echo "$INTENT_RESPONSE" | grep -q '"status":"processed"'
track_check $? "Intenção processada"

echo "$INTENT_RESPONSE" | grep -q '"domain"'
track_check $? "Domínio classificado"

# Extrair intent_id para verificações futuras
INTENT_ID=$(echo "$INTENT_RESPONSE" | grep -o '"intent_id":"[^"]*"' | cut -d'"' -f4 || echo "")

if [ -n "$INTENT_ID" ]; then
    echo -e "${GREEN}[✓]${NC} Intent ID: $INTENT_ID"

    # Verificar se foi registrado no Schema Registry
    echo -e "${BLUE}[INFO]${NC} Verificando registro no Schema Registry..."
    SUBJECTS=$(kubectl exec -n kafka $APICURIO_POD -- curl -s http://localhost:8080/apis/ccompat/v6/subjects 2>/dev/null || echo "[]")
    echo "$SUBJECTS" | grep -q "intentions"
    track_check $? "Schema registrado no Apicurio"
else
    echo -e "${YELLOW}[!]${NC} Não foi possível extrair Intent ID"
fi

# ============================================================================
# NAMESPACES E SERVIÇOS
# ============================================================================

echo ""
echo -e "${YELLOW}=== NAMESPACES E SERVIÇOS ===${NC}"
echo ""

NAMESPACES=$(kubectl get namespaces -o name | grep -E "(neural-hive|gateway|kafka|redis|mongodb|neo4j)" | wc -l)
[ "$NAMESPACES" -ge 10 ]
track_check $? "Namespaces criados ($NAMESPACES namespaces)"

SERVICES=$(kubectl get svc --all-namespaces -o name | grep -E "(gateway|schema-registry|neo4j|redis|mongodb|kafka)" | wc -l)
[ "$SERVICES" -ge 6 ]
track_check $? "Services expostos ($SERVICES services)"

# ============================================================================
# RESUMO FINAL
# ============================================================================

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    RESUMO DA VALIDAÇÃO${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo "Total de verificações: $TOTAL_CHECKS"
echo -e "Aprovadas: ${GREEN}$PASSED_CHECKS${NC}"
echo -e "Falhadas: ${RED}$FAILED_CHECKS${NC}"
echo ""

SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
echo -e "Taxa de sucesso: ${GREEN}${SUCCESS_RATE}%${NC}"
echo ""

if [ $FAILED_CHECKS -eq 0 ]; then
    echo -e "${GREEN}✅ VALIDAÇÃO APROVADA${NC}"
    echo "Todos os componentes estão operacionais!"
    echo ""
    echo -e "${BLUE}Status do Sistema:${NC}"
    echo "  • Infraestrutura (Fase 2): ✅ 100%"
    echo "  • Aplicação (Fase 3): ✅ 100%"
    echo "  • Schema Registry: ✅ Apicurio com Confluent API"
    echo "  • Gateway: ✅ Processando intenções"
    echo "  • Neo4j: ✅ Operacional"
    echo ""
    echo -e "${GREEN}🎉 SISTEMA PRONTO PARA USO!${NC}"
    exit 0
elif [ $SUCCESS_RATE -ge 80 ]; then
    echo -e "${YELLOW}⚠️  VALIDAÇÃO PARCIAL${NC}"
    echo "Maioria dos componentes operacional, mas há algumas falhas."
    echo ""
    echo "Revise os componentes marcados com [✗] acima."
    exit 1
else
    echo -e "${RED}❌ VALIDAÇÃO FALHADA${NC}"
    echo "Múltiplos componentes com problemas."
    echo ""
    echo "Revise os logs e configurações dos componentes falhados."
    exit 2
fi
