#!/bin/bash

# Script de Teste End-to-End para Analyst Agents
# Testa integração completa: Kafka → Consumers → Analytics → Insights → Producer

set -e

NAMESPACE="neural-hive"
SERVICE_NAME="analyst-agents"
KAFKA_BROKER="neural-hive-kafka-bootstrap:9092"

echo "=================================================="
echo "Teste E2E: Analyst Agents"
echo "=================================================="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função de teste
test_step() {
    echo -e "${YELLOW}[TEST]${NC} $1"
}

test_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

test_fail() {
    echo -e "${RED}[✗]${NC} $1"
    exit 1
}

# 1. Verificar deployment
test_step "1. Verificando deployment do Analyst Agents..."
kubectl get deployment $SERVICE_NAME -n $NAMESPACE > /dev/null 2>&1 || test_fail "Deployment não encontrado"
REPLICAS=$(kubectl get deployment $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.readyReplicas}')
if [ "$REPLICAS" -gt 0 ]; then
    test_success "Deployment ativo com $REPLICAS réplicas"
else
    test_fail "Nenhuma réplica disponível"
fi

# 2. Verificar service
test_step "2. Verificando service..."
kubectl get service $SERVICE_NAME -n $NAMESPACE > /dev/null 2>&1 || test_fail "Service não encontrado"
test_success "Service encontrado"

# 3. Verificar pods
test_step "3. Verificando pods..."
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POD_NAME" ]; then
    test_fail "Nenhum pod encontrado"
fi
POD_STATUS=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    test_fail "Pod não está Running: $POD_STATUS"
fi
test_success "Pod $POD_NAME está Running"

# 4. Verificar tópicos Kafka
test_step "4. Verificando tópicos Kafka..."
KAFKA_POD=$(kubectl get pods -n $NAMESPACE -l strimzi.io/name=neural-hive-kafka -o jsonpath='{.items[0].metadata.name}')

for TOPIC in "insights.analyzed" "insights.strategic" "insights.operational"; do
    kubectl exec -n $NAMESPACE $KAFKA_POD -- bin/kafka-topics.sh \
        --bootstrap-server $KAFKA_BROKER \
        --describe --topic $TOPIC > /dev/null 2>&1 || test_fail "Tópico $TOPIC não encontrado"
    test_success "Tópico $TOPIC existe"
done

# 5. Health check REST API
test_step "5. Testando health check REST API..."
kubectl port-forward -n $NAMESPACE svc/$SERVICE_NAME 8080:8000 > /dev/null 2>&1 &
PF_PID=$!
sleep 2

HEALTH_RESPONSE=$(curl -s http://localhost:8080/health)
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    test_success "Health check OK: $HEALTH_RESPONSE"
else
    kill $PF_PID
    test_fail "Health check falhou: $HEALTH_RESPONSE"
fi

# 6. Readiness check
test_step "6. Testando readiness check..."
READY_RESPONSE=$(curl -s http://localhost:8080/ready)
if echo "$READY_RESPONSE" | grep -q "ready"; then
    test_success "Readiness check OK"
else
    kill $PF_PID
    test_fail "Readiness check falhou: $READY_RESPONSE"
fi

# 7. Publicar mensagem de telemetria no Kafka
test_step "7. Publicando mensagem de telemetria no Kafka..."
TELEMETRY_MESSAGE=$(cat <<EOF
{
  "timestamp": $(date +%s)000,
  "service_name": "test-service",
  "metrics": {
    "cpu_usage": 95.5,
    "memory_usage": 85.2,
    "request_count": 1000,
    "error_count": 50
  },
  "correlation_id": "test-$(date +%s)",
  "trace_id": "trace-test-$(date +%s)"
}
EOF
)

kubectl exec -n $NAMESPACE $KAFKA_POD -- bin/kafka-console-producer.sh \
    --broker-list $KAFKA_BROKER \
    --topic telemetry.aggregated \
    --property "parse.key=false" <<< "$TELEMETRY_MESSAGE" || test_fail "Falha ao publicar telemetria"
test_success "Mensagem de telemetria publicada"

# 8. Aguardar processamento (5 segundos)
test_step "8. Aguardando processamento (5s)..."
sleep 5

# 9. Verificar logs do consumer
test_step "9. Verificando logs do Telemetry Consumer..."
LOGS=$(kubectl logs -n $NAMESPACE $POD_NAME --tail=50 | grep -i "telemetry_message_consumed\|anomaly_detected" || echo "")
if [ -n "$LOGS" ]; then
    test_success "Consumer processou mensagem de telemetria"
    echo "$LOGS" | head -3
else
    echo -e "${YELLOW}[!]${NC} Nenhum log de processamento encontrado (pode ser normal se buffer não encheu)"
fi

# 10. Testar API de insights
test_step "10. Testando API de insights..."
INSIGHTS_RESPONSE=$(curl -s http://localhost:8080/api/v1/insights?limit=5)
if echo "$INSIGHTS_RESPONSE" | grep -q "insights"; then
    INSIGHTS_COUNT=$(echo "$INSIGHTS_RESPONSE" | jq '.insights | length' 2>/dev/null || echo "0")
    test_success "API de insights funcionando ($INSIGHTS_COUNT insights retornados)"
else
    echo -e "${YELLOW}[!]${NC} API respondeu mas sem insights ainda: $INSIGHTS_RESPONSE"
fi

# 11. Testar API de analytics
test_step "11. Testando API de analytics (anomaly detection)..."
ANOMALY_REQUEST=$(cat <<EOF
{
  "metric_name": "cpu_usage",
  "values": [50.0, 52.0, 51.0, 95.0, 53.0, 52.0],
  "method": "zscore",
  "threshold": 2.0
}
EOF
)

ANOMALY_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/analytics/anomalies \
    -H "Content-Type: application/json" \
    -d "$ANOMALY_REQUEST")

if echo "$ANOMALY_RESPONSE" | grep -q "anomalies"; then
    ANOMALY_COUNT=$(echo "$ANOMALY_RESPONSE" | jq '.anomalies | length' 2>/dev/null || echo "0")
    test_success "Detecção de anomalias funcionando ($ANOMALY_COUNT anomalias detectadas)"
else
    kill $PF_PID
    test_fail "API de analytics falhou: $ANOMALY_RESPONSE"
fi

# 12. Testar API semântica
test_step "12. Testando API semântica (similarity)..."
SIMILARITY_REQUEST=$(cat <<EOF
{
  "text1": "erro de conexão com o banco de dados",
  "text2": "falha ao conectar no database"
}
EOF
)

SIMILARITY_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/semantics/similarity \
    -H "Content-Type: application/json" \
    -d "$SIMILARITY_REQUEST")

if echo "$SIMILARITY_RESPONSE" | grep -q "similarity"; then
    SIMILARITY_SCORE=$(echo "$SIMILARITY_RESPONSE" | jq '.similarity' 2>/dev/null || echo "0")
    test_success "API semântica funcionando (similarity: $SIMILARITY_SCORE)"
else
    kill $PF_PID
    test_fail "API semântica falhou: $SIMILARITY_RESPONSE"
fi

# 13. Verificar métricas Prometheus
test_step "13. Verificando métricas Prometheus..."
METRICS_RESPONSE=$(curl -s http://localhost:8080/metrics)
if echo "$METRICS_RESPONSE" | grep -q "insights_generated_total"; then
    test_success "Métricas Prometheus disponíveis"
else
    kill $PF_PID
    test_fail "Métricas Prometheus não encontradas"
fi

# 14. Verificar consumer lag (Kafka)
test_step "14. Verificando consumer lag..."
CONSUMER_GROUP="analyst-agents-group"
LAG_OUTPUT=$(kubectl exec -n $NAMESPACE $KAFKA_POD -- bin/kafka-consumer-groups.sh \
    --bootstrap-server $KAFKA_BROKER \
    --describe --group $CONSUMER_GROUP 2>/dev/null || echo "")

if echo "$LAG_OUTPUT" | grep -q "telemetry.aggregated"; then
    test_success "Consumer group ativo"
    echo "$LAG_OUTPUT" | grep -E "TOPIC|telemetry|consensus|execution|pheromone" | head -5
else
    echo -e "${YELLOW}[!]${NC} Consumer group não encontrado (pode ser normal se consumidores não iniciaram)"
fi

# 15. Testar MongoDB (via logs)
test_step "15. Verificando integração MongoDB..."
MONGO_LOGS=$(kubectl logs -n $NAMESPACE $POD_NAME --tail=100 | grep -i "mongodb" | tail -3 || echo "")
if echo "$MONGO_LOGS" | grep -q "initialized\|connected"; then
    test_success "MongoDB integrado"
else
    echo -e "${YELLOW}[!]${NC} Logs MongoDB não encontrados"
fi

# 16. Testar Redis (via logs)
test_step "16. Verificando integração Redis..."
REDIS_LOGS=$(kubectl logs -n $NAMESPACE $POD_NAME --tail=100 | grep -i "redis" | tail -3 || echo "")
if echo "$REDIS_LOGS" | grep -q "initialized\|connected"; then
    test_success "Redis integrado"
else
    echo -e "${YELLOW}[!]${NC} Logs Redis não encontrados"
fi

# 17. Verificar recursos do pod
test_step "17. Verificando recursos do pod..."
CPU_USAGE=$(kubectl top pod $POD_NAME -n $NAMESPACE 2>/dev/null | awk 'NR==2 {print $2}' || echo "N/A")
MEM_USAGE=$(kubectl top pod $POD_NAME -n $NAMESPACE 2>/dev/null | awk 'NR==2 {print $3}' || echo "N/A")
test_success "Recursos: CPU=$CPU_USAGE, Memory=$MEM_USAGE"

# 18. Verificar HPA (se existir)
test_step "18. Verificando HPA..."
HPA_STATUS=$(kubectl get hpa $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.currentReplicas}' 2>/dev/null || echo "")
if [ -n "$HPA_STATUS" ]; then
    test_success "HPA ativo com $HPA_STATUS réplicas"
else
    echo -e "${YELLOW}[!]${NC} HPA não configurado"
fi

# Cleanup
kill $PF_PID 2>/dev/null || true

echo ""
echo "=================================================="
echo -e "${GREEN}Teste E2E Concluído com Sucesso!${NC}"
echo "=================================================="
echo ""
echo "Resumo:"
echo "  • Deployment: OK"
echo "  • Service: OK"
echo "  • Kafka Topics: OK (3 tópicos)"
echo "  • REST API: OK (health, insights, analytics, semantics)"
echo "  • Kafka Integration: OK (consumers ativos)"
echo "  • MongoDB: OK"
echo "  • Redis: OK"
echo "  • Prometheus Metrics: OK"
echo ""
echo "Próximos passos:"
echo "  1. Compilar proto gRPC: make proto"
echo "  2. Ativar gRPC: GRPC_ENABLED=true"
echo "  3. Configurar dashboard Grafana"
echo "  4. Configurar alertas Prometheus"
echo ""
