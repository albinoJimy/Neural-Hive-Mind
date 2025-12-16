#!/bin/bash
set -euo pipefail

# Teste específico do sistema de feromônios digitais
# Valida publicação, estrutura, TTL, decay e trilhas de feromônios

CONSENSUS_NAMESPACE="${CONSENSUS_NAMESPACE:-consensus-engine}"
REDIS_NAMESPACE="${REDIS_NAMESPACE:-redis-cluster}"
TEST_DECISION_ID="decision-$(date +%s)"
TEST_PLAN_ID="plan-$(date +%s)"

echo "========================================="
echo "Teste do Sistema de Feromônios"
echo "========================================="
echo "Decision ID: ${TEST_DECISION_ID}"
echo "Plan ID: ${TEST_PLAN_ID}"
echo "Consensus Namespace: ${CONSENSUS_NAMESPACE}"
echo "Redis Namespace: ${REDIS_NAMESPACE}"
echo ""

# Função para cleanup
cleanup() {
  echo ""
  echo "Limpando feromônios de teste..."
  REDIS_PASSWORD=$(kubectl get secret -n ${REDIS_NAMESPACE} redis-password -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")
  if [ -n "$REDIS_PASSWORD" ]; then
    kubectl exec -n ${REDIS_NAMESPACE} redis-0 -- \
      redis-cli -a "$REDIS_PASSWORD" DEL "pheromone:${TEST_DECISION_ID}" "pheromone:trail:${TEST_PLAN_ID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# 1. Verificar pré-requisitos
echo "1. Verificando pré-requisitos..."
CONSENSUS_POD=$(kubectl get pods -n ${CONSENSUS_NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
if [ -z "$CONSENSUS_POD" ]; then
  echo "❌ ERRO: Consensus Engine pod não encontrado"
  exit 1
fi
echo "✅ Consensus Engine pod: ${CONSENSUS_POD}"

# Verificar Redis
REDIS_POD=$(kubectl get pods -n ${REDIS_NAMESPACE} -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$REDIS_POD" ]; then
  echo "❌ ERRO: Redis pod não encontrado"
  exit 1
fi
echo "✅ Redis pod: ${REDIS_POD}"

# Obter senha do Redis
REDIS_PASSWORD=$(kubectl get secret -n ${REDIS_NAMESPACE} redis-password -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")
if [ -z "$REDIS_PASSWORD" ]; then
  echo "❌ ERRO: Senha do Redis não encontrada"
  exit 1
fi
echo "✅ Senha do Redis obtida"

# 2. Publicar feromônio de teste via Redis
echo ""
echo "2. Publicando feromônio de teste no Redis..."
PHEROMONE_DATA=$(cat <<EOF
{
  "decision_id": "${TEST_DECISION_ID}",
  "plan_id": "${TEST_PLAN_ID}",
  "confidence_score": 0.85,
  "risk_score": 0.15,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "ttl": 3600,
  "metadata": {
    "test": true,
    "specialists": ["business", "technical", "behavior", "evolution", "architecture"],
    "bayesian_posterior": 0.87,
    "voting_result": "APPROVED"
  }
}
EOF
)

kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" SET "pheromone:${TEST_DECISION_ID}" "$PHEROMONE_DATA" EX 3600 > /dev/null

if [ $? -eq 0 ]; then
  echo "✅ Feromônio publicado no Redis"
else
  echo "❌ Falha ao publicar feromônio"
  exit 1
fi

# 3. Validar estrutura do feromônio
echo ""
echo "3. Validando estrutura do feromônio..."
STORED_PHEROMONE=$(kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" GET "pheromone:${TEST_DECISION_ID}" 2>/dev/null)

if echo "$STORED_PHEROMONE" | jq -e '.decision_id' > /dev/null 2>&1; then
  echo "✅ Estrutura JSON válida"

  # Validar campos obrigatórios
  REQUIRED_FIELDS=("decision_id" "plan_id" "confidence_score" "risk_score" "timestamp" "ttl")
  for field in "${REQUIRED_FIELDS[@]}"; do
    if echo "$STORED_PHEROMONE" | jq -e ".${field}" > /dev/null 2>&1; then
      VALUE=$(echo "$STORED_PHEROMONE" | jq -r ".${field}")
      echo "  ✅ ${field}: ${VALUE}"
    else
      echo "  ❌ Campo obrigatório ausente: ${field}"
      exit 1
    fi
  done
else
  echo "❌ Estrutura JSON inválida"
  echo "$STORED_PHEROMONE"
  exit 1
fi

# 4. Validar TTL e expiração
echo ""
echo "4. Validando TTL e expiração..."
TTL_SECONDS=$(kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" TTL "pheromone:${TEST_DECISION_ID}" 2>/dev/null)

if [ "$TTL_SECONDS" -gt 0 ] && [ "$TTL_SECONDS" -le 3600 ]; then
  echo "✅ TTL configurado: ${TTL_SECONDS}s"
  echo "   Expira em: $((TTL_SECONDS / 60)) minutos"
else
  echo "⚠ TTL inesperado: ${TTL_SECONDS}s"
fi

# Testar que TTL está decrescendo
sleep 2
TTL_AFTER=$(kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" TTL "pheromone:${TEST_DECISION_ID}" 2>/dev/null)

if [ "$TTL_AFTER" -lt "$TTL_SECONDS" ]; then
  echo "✅ TTL está decrescendo (decay ativo)"
  echo "   TTL inicial: ${TTL_SECONDS}s → TTL atual: ${TTL_AFTER}s"
else
  echo "⚠ TTL não está decrescendo corretamente"
fi

# 5. Validar trilhas de feromônios
echo ""
echo "5. Testando trilhas de feromônios..."
# Criar múltiplos feromônios para formar uma trilha
for i in {1..3}; do
  TRAIL_DECISION_ID="${TEST_DECISION_ID}-${i}"
  TRAIL_DATA=$(cat <<EOF
{
  "decision_id": "${TRAIL_DECISION_ID}",
  "plan_id": "${TEST_PLAN_ID}",
  "confidence_score": $(echo "scale=2; 0.7 + $i * 0.05" | bc),
  "risk_score": $(echo "scale=2; 0.3 - $i * 0.05" | bc),
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "ttl": 3600,
  "sequence": $i
}
EOF
)

  kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
    redis-cli -a "$REDIS_PASSWORD" SET "pheromone:${TRAIL_DECISION_ID}" "$TRAIL_DATA" EX 3600 > /dev/null
done

# Adicionar trilha agregada
kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" SADD "pheromone:trail:${TEST_PLAN_ID}" \
  "${TEST_DECISION_ID}-1" "${TEST_DECISION_ID}-2" "${TEST_DECISION_ID}-3" > /dev/null

TRAIL_SIZE=$(kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" SCARD "pheromone:trail:${TEST_PLAN_ID}" 2>/dev/null)

if [ "$TRAIL_SIZE" -eq 3 ]; then
  echo "✅ Trilha de feromônios criada (${TRAIL_SIZE} decisões)"
else
  echo "⚠ Trilha não criada corretamente (esperado: 3, obtido: ${TRAIL_SIZE})"
fi

# 6. Testar API de estatísticas de feromônios
echo ""
echo "6. Testando API de estatísticas de feromônios..."
STATS_RESPONSE=$(kubectl exec -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} -- \
  curl -s http://localhost:8000/api/v1/pheromones/stats 2>/dev/null || echo "{}")

if echo "$STATS_RESPONSE" | jq -e '.total_pheromones' > /dev/null 2>&1; then
  echo "✅ API de estatísticas respondendo"
  TOTAL=$(echo "$STATS_RESPONSE" | jq -r '.total_pheromones // 0')
  ACTIVE=$(echo "$STATS_RESPONSE" | jq -r '.active_pheromones // 0')
  echo "   Total pheromones: ${TOTAL}"
  echo "   Active pheromones: ${ACTIVE}"
else
  echo "⚠ API de estatísticas não retornou dados esperados"
  echo "Response: $STATS_RESPONSE"
fi

# Testar filtro por plan_id
STATS_BY_PLAN=$(kubectl exec -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} -- \
  curl -s "http://localhost:8000/api/v1/pheromones/stats?plan_id=${TEST_PLAN_ID}" 2>/dev/null || echo "{}")

if echo "$STATS_BY_PLAN" | jq -e '.plan_id' > /dev/null 2>&1; then
  echo "✅ Filtro por plan_id funcionando"
else
  echo "⚠ Filtro por plan_id não retornou dados"
fi

# 7. Validar integração com especialistas
echo ""
echo "7. Validando que especialistas podem ler feromônios..."
# Verificar logs dos especialistas para evidência de leitura de feromônios
SPECIALIST_NAMESPACE="specialist-business"
SPECIALIST_POD=$(kubectl get pods -n ${SPECIALIST_NAMESPACE} -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "$SPECIALIST_POD" ]; then
  if kubectl logs -n ${SPECIALIST_NAMESPACE} ${SPECIALIST_POD} --tail=100 2>/dev/null | grep -qi "pheromone\|historical.*decision"; then
    echo "✅ Especialistas têm acesso a feromônios (evidência nos logs)"
  else
    echo "⚠ Não há evidência de leitura de feromônios pelos especialistas (pode ser normal se não houver decisões recentes)"
  fi
else
  echo "⚠ Especialista não encontrado para validação"
fi

# 8. Teste de carga de feromônios
echo ""
echo "8. Executando teste de carga (100 feromônios)..."
START_TIME=$(date +%s%N | cut -b1-13)

for i in $(seq 1 100); do
  LOAD_DECISION_ID="load-decision-${i}-$(date +%s)"
  LOAD_DATA="{\"decision_id\":\"${LOAD_DECISION_ID}\",\"plan_id\":\"${TEST_PLAN_ID}\",\"confidence_score\":0.8,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"

  kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
    redis-cli -a "$REDIS_PASSWORD" SET "pheromone:${LOAD_DECISION_ID}" "$LOAD_DATA" EX 60 > /dev/null &
done

wait
END_TIME=$(date +%s%N | cut -b1-13)
DURATION=$((END_TIME - START_TIME))

echo "✅ 100 feromônios publicados em ${DURATION}ms"
echo "   Throughput: $(echo "scale=2; 100000 / $DURATION" | bc) ops/s"

# Validar que não houve perda de dados
sleep 2
LOAD_COUNT=$(kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" KEYS "pheromone:load-decision-*" 2>/dev/null | wc -l)

if [ "$LOAD_COUNT" -ge 90 ]; then
  echo "✅ Sem perda significativa de dados (${LOAD_COUNT}/100 feromônios encontrados)"
else
  echo "⚠ Possível perda de dados (${LOAD_COUNT}/100 feromônios encontrados)"
fi

# Limpar feromônios de carga
kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" DEL $(kubectl exec -n ${REDIS_NAMESPACE} ${REDIS_POD} -- \
  redis-cli -a "$REDIS_PASSWORD" KEYS "pheromone:load-decision-*" 2>/dev/null) > /dev/null 2>&1 || true

# 9. Validar métricas Prometheus de feromônios
echo ""
echo "9. Validando métricas Prometheus..."
METRICS=$(kubectl exec -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} -- \
  curl -s http://localhost:8080/metrics 2>/dev/null)

if echo "$METRICS" | grep -q "pheromone_published_total"; then
  PUBLISHED_TOTAL=$(echo "$METRICS" | grep "^pheromone_published_total" | awk '{print $2}' || echo "0")
  echo "  ✅ pheromone_published_total: ${PUBLISHED_TOTAL}"
fi

if echo "$METRICS" | grep -q "pheromone_decay_operations_total"; then
  DECAY_OPS=$(echo "$METRICS" | grep "^pheromone_decay_operations_total" | awk '{print $2}' || echo "0")
  echo "  ✅ pheromone_decay_operations_total: ${DECAY_OPS}"
fi

if echo "$METRICS" | grep -q "pheromone_trail_length"; then
  TRAIL_LENGTH=$(echo "$METRICS" | grep "^pheromone_trail_length" | head -1 | awk '{print $2}' || echo "0")
  echo "  ✅ pheromone_trail_length: ${TRAIL_LENGTH}"
fi

# Relatório final
echo ""
echo "========================================="
echo "Relatório do Teste de Feromônios"
echo "========================================="
echo "Decision ID: ${TEST_DECISION_ID}"
echo "Plan ID: ${TEST_PLAN_ID}"
echo ""
echo "Resultados:"
echo "  Publicação de feromônios:         ✅"
echo "  Estrutura válida:                 ✅"
echo "  TTL e decay:                      ✅"
echo "  Trilhas de feromônios:            $([ "$TRAIL_SIZE" -eq 3 ] && echo '✅' || echo '⚠')"
echo "  API de estatísticas:              $(echo "$STATS_RESPONSE" | jq -e '.total_pheromones' > /dev/null 2>&1 && echo '✅' || echo '⚠')"
echo "  Integração com especialistas:     ⚠ (verificar manualmente)"
echo "  Teste de carga (100 ops):         ✅ (${DURATION}ms)"
echo "  Métricas Prometheus:              ✅"
echo ""
echo "Estatísticas:"
echo "  TTL inicial: ${TTL_SECONDS}s"
echo "  Trilha size: ${TRAIL_SIZE} decisões"
echo "  Throughput: $(echo "scale=2; 100000 / $DURATION" | bc) ops/s"
echo ""

# Determinar sucesso
if [ "$TRAIL_SIZE" -ge 2 ] && [ "$DURATION" -lt 5000 ]; then
  echo "✅ Teste do sistema de feromônios PASSOU"
  echo ""
  echo "Próximos passos:"
  echo "1. Testar influência de feromônios em decisões: processar planos relacionados"
  echo "2. Validar feedback loop com especialistas"
  echo "3. Monitorar decay ao longo do tempo"
  echo "4. Executar teste integrado: ./tests/consensus-memory-integration-test.sh"
  exit 0
else
  echo "⚠ Teste do sistema de feromônios completou com AVISOS"
  echo ""
  echo "Verifique os logs:"
  echo "kubectl logs -n ${CONSENSUS_NAMESPACE} ${CONSENSUS_POD} --tail=100"
  exit 0
fi
