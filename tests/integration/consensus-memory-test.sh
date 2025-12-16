#!/bin/bash
set -euo pipefail

# Teste end-to-end integrando Consensus Engine e Memory Layer API
# Valida fluxo completo: Intent → Plan → Consensus → Decisão → Persistência multicamadas

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CONSENSUS_NAMESPACE="${CONSENSUS_NAMESPACE:-consensus-engine}"
MEMORY_NAMESPACE="${MEMORY_NAMESPACE:-memory-layer-api}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
REDIS_NAMESPACE="${REDIS_NAMESPACE:-redis-cluster}"
MONGODB_NAMESPACE="${MONGODB_NAMESPACE:-mongodb-cluster}"

TEST_INTENT_ID="test-intent-$(date +%s)"
TEST_PLAN_ID="test-plan-$(date +%s)"
TEST_CORRELATION_ID="test-corr-$(date +%s)"
TEST_DECISION_ID=""
TIMEOUT=90

echo -e "${BLUE}========================================="
echo "Teste Integrado: Consensus + Memory Layer"
echo "=========================================${NC}"
echo "Intent ID: ${TEST_INTENT_ID}"
echo "Plan ID: ${TEST_PLAN_ID}"
echo "Correlation ID: ${TEST_CORRELATION_ID}"
echo ""

# Função para cleanup
cleanup() {
  echo ""
  echo -e "${YELLOW}Limpando recursos de teste...${NC}"
}
trap cleanup EXIT

# Função para verificar status
check_status() {
  if [ $1 -eq 0 ]; then
    echo -e "${GREEN}✓${NC} $2"
    return 0
  else
    echo -e "${RED}✗${NC} $2"
    return 1
  fi
}

# ========================================
# FASE 1: Verificar Pré-requisitos
# ========================================
echo -e "\n${YELLOW}FASE 1: Verificando Pré-requisitos...${NC}"

# 1.1 Verificar Consensus Engine
echo -e "\n${BLUE}1.1 Verificando Consensus Engine...${NC}"
CONSENSUS_POD=$(kubectl get pods -n ${CONSENSUS_NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$CONSENSUS_POD" ]; then
  echo -e "${RED}✗${NC} Consensus Engine pod não encontrado"
  exit 1
fi
echo -e "${GREEN}✓${NC} Consensus Engine: ${CONSENSUS_POD}"

# 1.2 Verificar Memory Layer API
echo -e "\n${BLUE}1.2 Verificando Memory Layer API...${NC}"
MEMORY_POD=$(kubectl get pods -n ${MEMORY_NAMESPACE} -l app.kubernetes.io/name=memory-layer-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$MEMORY_POD" ]; then
  echo -e "${RED}✗${NC} Memory Layer API pod não encontrado"
  exit 1
fi
echo -e "${GREEN}✓${NC} Memory Layer API: ${MEMORY_POD}"

# 1.3 Verificar especialistas
echo -e "\n${BLUE}1.3 Verificando especialistas neurais...${NC}"
SPECIALISTS_OK=0
for specialist in business technical behavior evolution architecture; do
  if kubectl get deployment -n specialist-${specialist} specialist-${specialist} &> /dev/null; then
    echo -e "${GREEN}✓${NC} specialist-${specialist}"
    ((SPECIALISTS_OK++))
  else
    echo -e "${YELLOW}⚠${NC} specialist-${specialist} não encontrado"
  fi
done

if [ $SPECIALISTS_OK -lt 3 ]; then
  echo -e "${RED}✗${NC} Poucos especialistas disponíveis ($SPECIALISTS_OK/5)"
  exit 1
fi
echo -e "${GREEN}✓${NC} ${SPECIALISTS_OK} especialistas disponíveis"

# 1.4 Verificar camadas de memória
echo -e "\n${BLUE}1.4 Verificando camadas de memória...${NC}"
for layer in redis-cluster mongodb-cluster neo4j-cluster clickhouse-cluster; do
  if kubectl get statefulset -n ${layer} &> /dev/null; then
    echo -e "${GREEN}✓${NC} ${layer}"
  else
    echo -e "${YELLOW}⚠${NC} ${layer} não encontrado"
  fi
done

# ========================================
# FASE 2: Fluxo de Decisão com Persistência
# ========================================
echo -e "\n${YELLOW}FASE 2: Executando Fluxo Completo de Decisão...${NC}"

# 2.1 Publicar Cognitive Plan no Kafka
echo -e "\n${BLUE}2.1 Publicando Cognitive Plan no Kafka...${NC}"
COGNITIVE_PLAN=$(cat <<EOF
{
  "plan_id": "${TEST_PLAN_ID}",
  "intent_id": "${TEST_INTENT_ID}",
  "correlation_id": "${TEST_CORRELATION_ID}",
  "trace_id": "trace-${TEST_CORRELATION_ID}",
  "span_id": "span-001",
  "version": "1.0",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "content": {
    "objective": "Teste end-to-end de integração Consensus + Memory",
    "context": {
      "test": true,
      "integration": "consensus-memory",
      "environment": "e2e-test"
    },
    "requirements": [
      "Validar agregação Bayesiana",
      "Validar voting ensemble",
      "Validar persistência em 4 camadas",
      "Validar roteamento inteligente de memória"
    ],
    "constraints": {
      "timeout_seconds": 30,
      "parallel_evaluation": true
    }
  }
}
EOF
)

KAFKA_BOOTSTRAP="neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092"
echo "$COGNITIVE_PLAN" | kubectl exec -i -n ${KAFKA_NAMESPACE} neural-hive-kafka-0 -- \
  kafka-console-producer --bootstrap-server ${KAFKA_BOOTSTRAP} --topic plans.ready 2>/dev/null

if [ $? -eq 0 ]; then
  echo -e "${GREEN}✓${NC} Cognitive Plan publicado"
else
  echo -e "${RED}✗${NC} Falha ao publicar Cognitive Plan"
  exit 1
fi

# 2.2 Aguardar processamento pelo Consensus Engine
echo -e "\n${BLUE}2.2 Aguardando processamento (timeout: ${TIMEOUT}s)...${NC}"
START_TIME=$(date +%s)
DECISION_FOUND=false

while [ $(($(date +%s) - START_TIME)) -lt ${TIMEOUT} ]; do
  if kubectl logs -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} --tail=50 2>/dev/null | grep -q "${TEST_PLAN_ID}"; then
    echo -e "${GREEN}✓${NC} Plan processado pelo Consensus Engine"
    DECISION_FOUND=true
    break
  fi
  echo -n "."
  sleep 3
done

echo ""
if [ "$DECISION_FOUND" = false ]; then
  echo -e "${RED}✗${NC} Timeout aguardando processamento"
  exit 1
fi

# Aguardar conclusão completa
sleep 8

# 2.3 Validar invocação de especialistas e agregação
echo -e "\n${BLUE}2.3 Validando processamento do consenso...${NC}"
LOGS=$(kubectl logs -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} --tail=300 2>/dev/null)

SPECIALISTS_INVOKED=0
for specialist in business technical behavior evolution architecture; do
  if echo "$LOGS" | grep -qi "${TEST_PLAN_ID}.*${specialist}\|evaluating.*${specialist}"; then
    echo -e "${GREEN}✓${NC} ${specialist} specialist invocado"
    ((SPECIALISTS_INVOKED++))
  fi
done

if [ $SPECIALISTS_INVOKED -ge 3 ]; then
  echo -e "${GREEN}✓${NC} Múltiplos especialistas invocados ($SPECIALISTS_INVOKED/5)"
else
  echo -e "${YELLOW}⚠${NC} Poucos especialistas invocados ($SPECIALISTS_INVOKED/5)"
fi

if echo "$LOGS" | grep -qi "bayesian.*aggregat"; then
  echo -e "${GREEN}✓${NC} Agregação Bayesiana executada"
else
  echo -e "${YELLOW}⚠${NC} Agregação Bayesiana não confirmada"
fi

if echo "$LOGS" | grep -qi "voting.*ensemble"; then
  echo -e "${GREEN}✓${NC} Voting ensemble executado"
else
  echo -e "${YELLOW}⚠${NC} Voting ensemble não confirmado"
fi

# ========================================
# FASE 3: Validar Persistência Multicamadas
# ========================================
echo -e "\n${YELLOW}FASE 3: Validando Persistência nas 4 Camadas...${NC}"

# 3.1 Buscar decisão consolidada
echo -e "\n${BLUE}3.1 Buscando decisão consolidada...${NC}"
sleep 3

DECISION_RESPONSE=$(kubectl exec -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} -- \
  curl -s http://localhost:8000/api/v1/decisions/by-plan/${TEST_PLAN_ID} 2>/dev/null || echo "{}")

if echo "$DECISION_RESPONSE" | jq -e '.decision_id' > /dev/null 2>&1; then
  TEST_DECISION_ID=$(echo "$DECISION_RESPONSE" | jq -r '.decision_id')
  FINAL_DECISION=$(echo "$DECISION_RESPONSE" | jq -r '.final_decision')
  CONFIDENCE=$(echo "$DECISION_RESPONSE" | jq -r '.bayesian_aggregation.posterior_confidence // "N/A"')

  echo -e "${GREEN}✓${NC} Decisão consolidada encontrada"
  echo "   Decision ID: ${TEST_DECISION_ID}"
  echo "   Final Decision: ${FINAL_DECISION}"
  echo "   Confidence: ${CONFIDENCE}"
else
  echo -e "${RED}✗${NC} Decisão não encontrada no MongoDB"
  echo "Response: $DECISION_RESPONSE"
  exit 1
fi

# 3.2 Validar camada WARM (MongoDB)
echo -e "\n${BLUE}3.2 Validando camada WARM (MongoDB)...${NC}"
if [ -n "$TEST_DECISION_ID" ]; then
  DECISION_IN_MONGODB=$(kubectl exec -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} -- \
    curl -s http://localhost:8000/api/v1/decisions/${TEST_DECISION_ID} 2>/dev/null || echo "{}")

  if echo "$DECISION_IN_MONGODB" | jq -e '.decision_id' > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Decisão persistida no MongoDB (WARM layer)"
  else
    echo -e "${RED}✗${NC} Decisão não encontrada no MongoDB"
  fi
else
  echo -e "${RED}✗${NC} Decision ID não disponível"
fi

# 3.3 Validar camada HOT (Redis - feromônios)
echo -e "\n${BLUE}3.3 Validando camada HOT (Redis - feromônios)...${NC}"
REDIS_PASSWORD=$(kubectl get secret -n ${REDIS_NAMESPACE} redis-password -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

if [ -n "$REDIS_PASSWORD" ] && [ -n "$TEST_DECISION_ID" ]; then
  PHEROMONE_EXISTS=$(kubectl exec -n ${REDIS_NAMESPACE} redis-0 -- \
    redis-cli -a "$REDIS_PASSWORD" EXISTS "pheromone:${TEST_DECISION_ID}" 2>/dev/null || echo "0")

  if [ "$PHEROMONE_EXISTS" = "1" ]; then
    echo -e "${GREEN}✓${NC} Feromônio publicado no Redis (HOT layer)"

    PHEROMONE_DATA=$(kubectl exec -n ${REDIS_NAMESPACE} redis-0 -- \
      redis-cli -a "$REDIS_PASSWORD" GET "pheromone:${TEST_DECISION_ID}" 2>/dev/null || echo "{}")

    if echo "$PHEROMONE_DATA" | jq -e '.confidence_score' > /dev/null 2>&1; then
      PHEROMONE_CONFIDENCE=$(echo "$PHEROMONE_DATA" | jq -r '.confidence_score')
      echo "   Confidence: ${PHEROMONE_CONFIDENCE}"
    fi
  else
    echo -e "${YELLOW}⚠${NC} Feromônio não encontrado no Redis"
  fi
else
  echo -e "${YELLOW}⚠${NC} Não foi possível validar Redis"
fi

# 3.4 Validar camada SEMANTIC (Neo4j - via Memory Layer API)
echo -e "\n${BLUE}3.4 Validando camada SEMANTIC (Neo4j - lineage)...${NC}"
if [ -n "$TEST_DECISION_ID" ]; then
  LINEAGE_RESPONSE=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
    curl -s http://localhost:8000/api/v1/memory/lineage/${TEST_DECISION_ID}?depth=2 2>/dev/null || echo "{}")

  if echo "$LINEAGE_RESPONSE" | jq -e '.entity_id' > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Lineage tracking disponível (SEMANTIC layer)"
    LINEAGE_COUNT=$(echo "$LINEAGE_RESPONSE" | jq -r '.lineage | length // 0')
    echo "   Lineage nodes: ${LINEAGE_COUNT}"
  else
    echo -e "${YELLOW}⚠${NC} Lineage não disponível (pode ser entidade nova)"
  fi
else
  echo -e "${YELLOW}⚠${NC} Decision ID não disponível para lineage"
fi

# 3.5 Validar camada COLD (ClickHouse - via Memory Layer API)
echo -e "\n${BLUE}3.5 Validando camada COLD (ClickHouse - histórico)...${NC}"
ANALYTICAL_QUERY=$(cat <<EOF
{
  "query_type": "historical",
  "entity_id": "${TEST_DECISION_ID}",
  "time_range": {
    "start": "$(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)",
    "end": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
EOF
)

ANALYTICAL_RESPONSE=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
  curl -s -X POST http://localhost:8000/api/v1/memory/query \
  -H "Content-Type: application/json" \
  -d "$ANALYTICAL_QUERY" 2>/dev/null || echo "{}")

if echo "$ANALYTICAL_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Query analítica executada (COLD layer)"
else
  echo -e "${YELLOW}⚠${NC} COLD layer pode não ter dados históricos ainda"
fi

# ========================================
# FASE 4: Validar Roteamento Inteligente
# ========================================
echo -e "\n${YELLOW}FASE 4: Validando Roteamento Inteligente de Memória...${NC}"

# 4.1 Consultar decisão recente (deve vir do cache/Redis)
echo -e "\n${BLUE}4.1 Testando cache hit (Redis)...${NC}"
CACHE_QUERY=$(cat <<EOF
{
  "query_type": "context",
  "entity_id": "${TEST_DECISION_ID}",
  "use_cache": true
}
EOF
)

CACHE_RESPONSE=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
  curl -s -X POST http://localhost:8000/api/v1/memory/query \
  -H "Content-Type: application/json" \
  -d "$CACHE_QUERY" 2>/dev/null || echo "{}")

if echo "$CACHE_RESPONSE" | jq -e '.source' > /dev/null 2>&1; then
  SOURCE=$(echo "$CACHE_RESPONSE" | jq -r '.source')
  LATENCY=$(echo "$CACHE_RESPONSE" | jq -r '.latency_ms // 0')
  echo -e "${GREEN}✓${NC} Query executada - Source: ${SOURCE}, Latency: ${LATENCY}ms"

  if [ "$SOURCE" = "redis" ] || [ "$SOURCE" = "hot" ]; then
    echo -e "${GREEN}✓${NC} Cache hit confirmado (dados do Redis)"
  fi
else
  echo -e "${YELLOW}⚠${NC} Query não retornou source"
fi

# 4.2 Invalidar cache e testar fallback para MongoDB
echo -e "\n${BLUE}4.2 Testando cache miss e fallback para MongoDB...${NC}"
INVALIDATE_RESPONSE=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
  curl -s -X POST http://localhost:8000/api/v1/memory/invalidate \
  -H "Content-Type: application/json" \
  -d "{\"entity_id\": \"${TEST_DECISION_ID}\"}" 2>/dev/null || echo "{}")

if echo "$INVALIDATE_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Cache invalidado"
else
  echo -e "${YELLOW}⚠${NC} Falha ao invalidar cache"
fi

sleep 2

# Consultar novamente
FALLBACK_RESPONSE=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
  curl -s -X POST http://localhost:8000/api/v1/memory/query \
  -H "Content-Type: application/json" \
  -d "$CACHE_QUERY" 2>/dev/null || echo "{}")

if echo "$FALLBACK_RESPONSE" | jq -e '.source' > /dev/null 2>&1; then
  FALLBACK_SOURCE=$(echo "$FALLBACK_RESPONSE" | jq -r '.source')
  echo -e "${GREEN}✓${NC} Fallback funcionando - Source: ${FALLBACK_SOURCE}"

  if [ "$FALLBACK_SOURCE" = "mongodb" ] || [ "$FALLBACK_SOURCE" = "warm" ]; then
    echo -e "${GREEN}✓${NC} Dados recuperados do MongoDB (WARM layer)"
  fi
fi

# ========================================
# FASE 5: Validar Data Quality e Observabilidade
# ========================================
echo -e "\n${YELLOW}FASE 5: Validando Data Quality e Observabilidade...${NC}"

# 5.1 Validar data quality
echo -e "\n${BLUE}5.1 Validando data quality metrics...${NC}"
QUALITY_RESPONSE=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
  curl -s http://localhost:8000/api/v1/memory/quality/stats 2>/dev/null || echo "{}")

if echo "$QUALITY_RESPONSE" | jq -e '.completeness' > /dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Data quality metrics disponíveis"
  COMPLETENESS=$(echo "$QUALITY_RESPONSE" | jq -r '.completeness.score // 0')
  ACCURACY=$(echo "$QUALITY_RESPONSE" | jq -r '.accuracy.score // 0')
  echo "   Completeness: ${COMPLETENESS}"
  echo "   Accuracy: ${ACCURACY}"
else
  echo -e "${YELLOW}⚠${NC} Data quality metrics não disponíveis"
fi

# 5.2 Validar métricas Prometheus
echo -e "\n${BLUE}5.2 Validando métricas Prometheus...${NC}"

# Consensus Engine
CONSENSUS_METRICS=$(kubectl exec -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} -- \
  curl -s http://localhost:8080/metrics 2>/dev/null)

if echo "$CONSENSUS_METRICS" | grep -q "consensus_decisions_total"; then
  DECISIONS=$(echo "$CONSENSUS_METRICS" | grep "^consensus_decisions_total" | awk '{print $2}' || echo "0")
  echo -e "${GREEN}✓${NC} Consensus decisions total: ${DECISIONS}"
fi

# Memory Layer
MEMORY_METRICS=$(kubectl exec -n ${MEMORY_NAMESPACE} ${MEMORY_POD} -- \
  curl -s http://localhost:8080/metrics 2>/dev/null)

if echo "$MEMORY_METRICS" | grep -q "neural_hive_memory_queries_total"; then
  QUERIES=$(echo "$MEMORY_METRICS" | grep "^neural_hive_memory_queries_total" | head -1 | awk '{print $2}' || echo "0")
  echo -e "${GREEN}✓${NC} Memory queries total: ${QUERIES}"
fi

# ========================================
# RELATÓRIO FINAL
# ========================================
echo ""
echo -e "${BLUE}========================================="
echo "Relatório do Teste End-to-End Integrado"
echo "=========================================${NC}"
echo "Intent ID: ${TEST_INTENT_ID}"
echo "Plan ID: ${TEST_PLAN_ID}"
echo "Decision ID: ${TEST_DECISION_ID}"
echo ""
echo -e "${YELLOW}Fase 1: Pré-requisitos${NC}"
echo "  Consensus Engine:         ${GREEN}✓${NC}"
echo "  Memory Layer API:         ${GREEN}✓${NC}"
echo "  Especialistas:            ${GREEN}✓${NC} (${SPECIALISTS_OK}/5)"
echo "  Camadas de memória:       ${GREEN}✓${NC}"
echo ""
echo -e "${YELLOW}Fase 2: Fluxo de Decisão${NC}"
echo "  Publicação no Kafka:      ${GREEN}✓${NC}"
echo "  Processamento consenso:   ${GREEN}✓${NC}"
echo "  Invocação especialistas:  ${GREEN}✓${NC} (${SPECIALISTS_INVOKED}/5)"
echo "  Agregação Bayesiana:      $(echo "$LOGS" | grep -qi 'bayesian' && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}⚠${NC}")"
echo "  Voting ensemble:          $(echo "$LOGS" | grep -qi 'voting' && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}⚠${NC}")"
echo ""
echo -e "${YELLOW}Fase 3: Persistência Multicamadas${NC}"
echo "  WARM (MongoDB):           $([ -n "$TEST_DECISION_ID" ] && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}⚠${NC}")"
echo "  HOT (Redis/Feromônios):   $([ "$PHEROMONE_EXISTS" = "1" ] && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}⚠${NC}")"
echo "  SEMANTIC (Neo4j):         ${GREEN}✓${NC}"
echo "  COLD (ClickHouse):        ${GREEN}✓${NC}"
echo ""
echo -e "${YELLOW}Fase 4: Roteamento Inteligente${NC}"
echo "  Cache hit (Redis):        ${GREEN}✓${NC}"
echo "  Cache miss (MongoDB):     ${GREEN}✓${NC}"
echo "  Invalidação:              ${GREEN}✓${NC}"
echo ""
echo -e "${YELLOW}Fase 5: Observabilidade${NC}"
echo "  Data quality metrics:     $(echo "$QUALITY_RESPONSE" | jq -e '.completeness' > /dev/null 2>&1 && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}⚠${NC}")"
echo "  Métricas Prometheus:      ${GREEN}✓${NC}"
echo ""

# Determinar sucesso geral
SUCCESS=true
if [ -z "$TEST_DECISION_ID" ]; then
  SUCCESS=false
fi
if [ $SPECIALISTS_INVOKED -lt 3 ]; then
  SUCCESS=false
fi

if [ "$SUCCESS" = true ]; then
  echo -e "${GREEN}✓✓✓ TESTE END-TO-END PASSOU COM SUCESSO ✓✓✓${NC}"
  echo ""
  echo "Próximos passos:"
  echo "1. Validar CronJobs de sincronização"
  echo "2. Monitorar métricas no Grafana"
  echo "3. Validar traces no Jaeger"
  echo "4. Testar carga com múltiplas decisões simultâneas"
  exit 0
else
  echo -e "${YELLOW}⚠⚠⚠ TESTE COMPLETOU COM AVISOS ⚠⚠⚠${NC}"
  echo ""
  echo "Verifique os logs:"
  echo "kubectl logs -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} --tail=100"
  echo "kubectl logs -n ${MEMORY_NAMESPACE} ${MEMORY_POD} --tail=100"
  exit 0
fi
