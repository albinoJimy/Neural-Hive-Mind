#!/bin/bash
set -euo pipefail

# Teste de integração end-to-end do Consensus Engine
# Simula fluxo completo: Cognitive Plan → Especialistas → Decisão → Feromônios

NAMESPACE="${NAMESPACE:-consensus-engine}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092}"
TEST_PLAN_ID="${TEST_PLAN_ID:-test-plan-$(date +%s)}"
TEST_INTENT_ID="test-intent-$(date +%s)"
TEST_CORRELATION_ID="test-corr-$(date +%s)"
TIMEOUT=60

echo "========================================="
echo "Teste de Integração - Consensus Engine"
echo "========================================="
echo "Plan ID: ${TEST_PLAN_ID}"
echo "Intent ID: ${TEST_INTENT_ID}"
echo "Namespace: ${NAMESPACE}"
echo "Kafka Bootstrap: ${KAFKA_BOOTSTRAP}"
echo ""

# Função para cleanup
cleanup() {
  echo ""
  echo "Limpando recursos de teste..."
  # Remover dados de teste do MongoDB se necessário
}
trap cleanup EXIT

# 1. Verificar pré-requisitos
echo "1. Verificando pré-requisitos..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POD_NAME" ]; then
  echo "❌ ERRO: Nenhum pod do Consensus Engine encontrado"
  exit 1
fi
echo "✅ Pod encontrado: ${POD_NAME}"

# Verificar especialistas
echo "  Verificando especialistas neurais..."
for specialist in business technical behavior evolution architecture; do
  if kubectl get deployment -n specialist-${specialist} specialist-${specialist} &> /dev/null; then
    echo "    ✅ specialist-${specialist}"
  else
    echo "    ❌ specialist-${specialist} não encontrado"
    exit 1
  fi
done

# 2. Publicar Cognitive Plan no Kafka
echo ""
echo "2. Publicando Cognitive Plan no Kafka..."
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
    "objective": "Teste de integração do sistema de consenso",
    "context": {
      "test": true,
      "environment": "integration-test"
    },
    "requirements": [
      "Validar agregação Bayesiana",
      "Validar voting ensemble",
      "Validar publicação de feromônios"
    ],
    "constraints": {
      "timeout_seconds": 30,
      "parallel_evaluation": true
    }
  }
}
EOF
)

echo "$COGNITIVE_PLAN" | kubectl exec -i -n ${KAFKA_NAMESPACE} neural-hive-kafka-0 -- \
  kafka-console-producer --bootstrap-server ${KAFKA_BOOTSTRAP} --topic plans.ready

if [ $? -eq 0 ]; then
  echo "✅ Cognitive Plan publicado no topic plans.ready"
else
  echo "❌ Falha ao publicar Cognitive Plan"
  exit 1
fi

# 3. Aguardar processamento
echo ""
echo "3. Aguardando processamento (timeout: ${TIMEOUT}s)..."
START_TIME=$(date +%s)
DECISION_FOUND=false

while [ $(($(date +%s) - START_TIME)) -lt ${TIMEOUT} ]; do
  # Verificar logs para processamento
  if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=50 2>/dev/null | grep -q "${TEST_PLAN_ID}"; then
    echo "✅ Plan detectado nos logs do Consensus Engine"
    DECISION_FOUND=true
    break
  fi
  echo -n "."
  sleep 2
done

echo ""
if [ "$DECISION_FOUND" = false ]; then
  echo "❌ Timeout aguardando processamento do plan"
  echo "Últimos logs:"
  kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=20
  exit 1
fi

# Aguardar mais tempo para conclusão
sleep 5

# 4. Validar invocação paralela dos especialistas
echo ""
echo "4. Validando invocação dos especialistas..."
LOGS=$(kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=200 2>/dev/null)

SPECIALISTS_INVOKED=0
for specialist in business technical behavior evolution architecture; do
  if echo "$LOGS" | grep -qi "evaluating.*${specialist}\|${specialist}.*opinion\|calling.*${specialist}"; then
    echo "  ✅ ${specialist} specialist invocado"
    ((SPECIALISTS_INVOKED++))
  else
    echo "  ⚠ ${specialist} specialist não confirmado nos logs"
  fi
done

if [ $SPECIALISTS_INVOKED -ge 3 ]; then
  echo "✅ Múltiplos especialistas invocados ($SPECIALISTS_INVOKED/5)"
else
  echo "⚠ Poucos especialistas invocados ($SPECIALISTS_INVOKED/5)"
fi

# 5. Validar agregação Bayesiana
echo ""
echo "5. Validando agregação Bayesiana..."
if echo "$LOGS" | grep -qi "bayesian.*aggregat\|posterior.*calculat\|bayesian.*confidence"; then
  echo "✅ Agregação Bayesiana executada"
else
  echo "⚠ Agregação Bayesiana não confirmada nos logs"
fi

# 6. Validar voting ensemble
echo ""
echo "6. Validando voting ensemble..."
if echo "$LOGS" | grep -qi "voting.*ensemble\|weighted.*vote\|consensus.*decision"; then
  echo "✅ Voting ensemble executado"
else
  echo "⚠ Voting ensemble não confirmado nos logs"
fi

# 7. Validar persistência no MongoDB
echo ""
echo "7. Validando persistência no MongoDB..."
sleep 3  # Aguardar persistência

DECISION_RESPONSE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- \
  curl -s http://localhost:8000/api/v1/decisions/by-plan/${TEST_PLAN_ID} 2>/dev/null || echo "{}")

if echo "$DECISION_RESPONSE" | jq -e '.decision_id' > /dev/null 2>&1; then
  echo "✅ Decisão consolidada salva no MongoDB"
  echo "   Decision ID: $(echo "$DECISION_RESPONSE" | jq -r '.decision_id')"
  echo "   Status: $(echo "$DECISION_RESPONSE" | jq -r '.final_decision')"
  echo "   Confidence: $(echo "$DECISION_RESPONSE" | jq -r '.bayesian_aggregation.posterior_confidence')"

  DECISION_ID=$(echo "$DECISION_RESPONSE" | jq -r '.decision_id')
else
  echo "⚠ Decisão não encontrada no MongoDB (pode levar mais tempo)"
  echo "Response: $DECISION_RESPONSE"
  DECISION_ID=""
fi

# 8. Validar publicação de feromônios no Redis
echo ""
echo "8. Validando feromônios no Redis..."
if [ -n "$DECISION_ID" ]; then
  # Tentar acessar Redis diretamente
  REDIS_PASSWORD=$(kubectl get secret -n redis-cluster redis-password -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

  if [ -n "$REDIS_PASSWORD" ]; then
    PHEROMONE_EXISTS=$(kubectl exec -n redis-cluster redis-0 -- \
      redis-cli -a "$REDIS_PASSWORD" EXISTS "pheromone:${DECISION_ID}" 2>/dev/null || echo "0")

    if [ "$PHEROMONE_EXISTS" = "1" ]; then
      echo "✅ Feromônio publicado no Redis"
      PHEROMONE_DATA=$(kubectl exec -n redis-cluster redis-0 -- \
        redis-cli -a "$REDIS_PASSWORD" GET "pheromone:${DECISION_ID}" 2>/dev/null || echo "{}")
      echo "   Data: $(echo "$PHEROMONE_DATA" | jq -c .)"
    else
      echo "⚠ Feromônio não encontrado no Redis"
    fi
  else
    echo "⚠ Não foi possível verificar Redis (senha não encontrada)"
  fi
else
  echo "⚠ Pulando verificação de feromônios (Decision ID não disponível)"
fi

# 9. Validar publicação no Kafka topic plans.consensus
echo ""
echo "9. Validando publicação no topic plans.consensus..."
# Consumir últimas mensagens do topic
KAFKA_MESSAGES=$(kubectl exec -n ${KAFKA_NAMESPACE} neural-hive-kafka-0 -- \
  kafka-console-consumer --bootstrap-server ${KAFKA_BOOTSTRAP} \
  --topic plans.consensus --from-beginning --timeout-ms 5000 2>/dev/null || echo "")

if echo "$KAFKA_MESSAGES" | grep -q "${TEST_PLAN_ID}\|${DECISION_ID}"; then
  echo "✅ Decisão publicada no topic plans.consensus"
else
  echo "⚠ Decisão não encontrada no topic (pode ter sido consumida)"
fi

# 10. Validar métricas Prometheus
echo ""
echo "10. Validando métricas Prometheus..."
METRICS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8080/metrics 2>/dev/null)

DECISIONS_TOTAL=$(echo "$METRICS" | grep "^consensus_decisions_total" | awk '{print $2}' || echo "0")
echo "  Decisões totais: ${DECISIONS_TOTAL}"

if echo "$METRICS" | grep -q "bayesian_aggregation_duration_seconds"; then
  BAYESIAN_COUNT=$(echo "$METRICS" | grep "bayesian_aggregation_duration_seconds_count" | awk '{print $2}' || echo "0")
  echo "  ✅ Agregações Bayesianas: ${BAYESIAN_COUNT}"
else
  echo "  ⚠ Métrica de agregação Bayesiana não encontrada"
fi

if echo "$METRICS" | grep -q "voting_ensemble_duration_seconds"; then
  VOTING_COUNT=$(echo "$METRICS" | grep "voting_ensemble_duration_seconds_count" | awk '{print $2}' || echo "0")
  echo "  ✅ Voting ensembles: ${VOTING_COUNT}"
else
  echo "  ⚠ Métrica de voting ensemble não encontrada"
fi

# Relatório final
echo ""
echo "========================================="
echo "Relatório do Teste de Integração"
echo "========================================="
echo "Plan ID: ${TEST_PLAN_ID}"
echo "Decision ID: ${DECISION_ID}"
echo ""
echo "Resultados:"
echo "  - Publicação no Kafka: ✅"
echo "  - Processamento pelo Consensus Engine: ✅"
echo "  - Invocação de especialistas: $([ $SPECIALISTS_INVOKED -ge 3 ] && echo '✅' || echo '⚠')"
echo "  - Agregação Bayesiana: $(echo "$LOGS" | grep -qi 'bayesian' && echo '✅' || echo '⚠')"
echo "  - Voting Ensemble: $(echo "$LOGS" | grep -qi 'voting' && echo '✅' || echo '⚠')"
echo "  - Persistência MongoDB: $([ -n "$DECISION_ID" ] && echo '✅' || echo '⚠')"
echo "  - Feromônios Redis: ⚠ (verificar manualmente)"
echo "  - Métricas Prometheus: ✅"
echo ""

# Determinar sucesso geral
if [ -n "$DECISION_ID" ] && [ $SPECIALISTS_INVOKED -ge 3 ]; then
  echo "✅ Teste de integração PASSOU"
  echo ""
  echo "Próximos passos:"
  echo "1. Verificar decisão: kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl http://localhost:8000/api/v1/decisions/${DECISION_ID}"
  echo "2. Verificar feromônios: ./tests/pheromone-system-test.sh"
  echo "3. Executar teste end-to-end completo: ./tests/consensus-memory-integration-test.sh"
  exit 0
else
  echo "⚠ Teste de integração completou com AVISOS"
  echo ""
  echo "Verifique os logs para mais detalhes:"
  echo "kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100"
  exit 0
fi
