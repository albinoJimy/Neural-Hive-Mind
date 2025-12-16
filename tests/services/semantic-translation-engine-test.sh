#!/bin/bash
# Script de teste end-to-end do Semantic Translation Engine em ambiente local
set -euo pipefail

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Contadores de testes
TESTS_PASSED=0
TESTS_FAILED=0

# Função para log
log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[✓]${NC} $1"
  TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_error() {
  echo -e "${RED}[✗]${NC} $1"
  TESTS_FAILED=$((TESTS_FAILED + 1))
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_section() {
  echo ""
  echo -e "${BLUE}========================================${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}========================================${NC}"
}

# Variáveis
NAMESPACE="semantic-translation-engine"
KAFKA_NAMESPACE="neural-hive-kafka"
KAFKA_BOOTSTRAP="neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092"
NEO4J_NAMESPACE="neo4j"
MONGODB_NAMESPACE="mongodb-cluster"
REDIS_NAMESPACE="redis-cluster"
INTENT_ID="test-intent-$(date +%s)"
TIMESTAMP_MS=$(date +%s)000

log_section "TESTES DO SEMANTIC TRANSLATION ENGINE"
log_info "Intent ID de teste: ${INTENT_ID}"
log_info "Timestamp: ${TIMESTAMP_MS}"

# 1. Validação de Infraestrutura
log_section "1. VALIDAÇÃO DE INFRAESTRUTURA"

# Kafka
log_info "Verificando Kafka..."
if kubectl get pods -n ${KAFKA_NAMESPACE} -l app.kubernetes.io/name=kafka | grep -q Running; then
  log_success "Kafka está rodando"
else
  log_error "Kafka não está rodando"
fi

# Neo4j
log_info "Verificando Neo4j..."
if kubectl get pods -n ${NEO4J_NAMESPACE} | grep -q Running; then
  log_success "Neo4j está rodando"
else
  log_warning "Neo4j pode não estar rodando"
fi

# MongoDB
log_info "Verificando MongoDB..."
if kubectl get pods -n ${MONGODB_NAMESPACE} | grep -q Running; then
  log_success "MongoDB está rodando"
else
  log_warning "MongoDB pode não estar rodando"
fi

# Redis
log_info "Verificando Redis..."
if kubectl get pods -n ${REDIS_NAMESPACE} | grep -q Running; then
  log_success "Redis está rodando"
else
  log_warning "Redis pode não estar rodando"
fi

# Verificar topics Kafka
log_info "Verificando topics Kafka..."
TOPICS=$(kubectl exec -n ${KAFKA_NAMESPACE} neural-hive-kafka-0 -- \
  /opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list 2>/dev/null)

if echo "${TOPICS}" | grep -q "intentions.business"; then
  log_success "Topic intentions.business existe"
else
  log_error "Topic intentions.business não encontrado"
fi

if echo "${TOPICS}" | grep -q "plans.ready"; then
  log_success "Topic plans.ready existe"
else
  log_error "Topic plans.ready não encontrado"
fi

# 2. Validação do Deployment
log_section "2. VALIDAÇÃO DO DEPLOYMENT"

# Verificar pod
log_info "Verificando pod do semantic-translation-engine..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "${POD_NAME}" ]; then
  log_error "Pod não encontrado"
  exit 1
fi

POD_STATUS=$(kubectl get pod -n ${NAMESPACE} ${POD_NAME} -o jsonpath='{.status.phase}')
if [ "${POD_STATUS}" == "Running" ]; then
  log_success "Pod ${POD_NAME} está Running"
else
  log_error "Pod ${POD_NAME} não está Running (status: ${POD_STATUS})"
fi

# Verificar logs não contêm erros críticos
log_info "Verificando logs para erros críticos..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=50 | grep -i "error\|exception\|failed" | grep -v "ERROR_METRICS\|error_type" > /dev/null 2>&1; then
  log_warning "Logs contêm possíveis erros - revisar manualmente"
else
  log_success "Nenhum erro crítico encontrado nos logs"
fi

# Testar endpoint /health
log_info "Testando endpoint /health..."
HEALTH_RESPONSE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -fsSL http://localhost:8000/health 2>/dev/null || echo "")

if echo "${HEALTH_RESPONSE}" | grep -q "healthy"; then
  log_success "Endpoint /health retornou 200 OK"
else
  log_error "Endpoint /health não está respondendo corretamente"
fi

# Testar endpoint /ready
log_info "Testando endpoint /ready..."
READY_RESPONSE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -fsSL http://localhost:8000/ready 2>/dev/null || echo "")

if echo "${READY_RESPONSE}" | grep -q "ready"; then
  log_success "Endpoint /ready retornou resposta"

  # Verificar detalhes das dependências
  if echo "${READY_RESPONSE}" | grep -q "kafka_consumer"; then
    log_success "Status do Kafka consumer disponível"
  fi

  if echo "${READY_RESPONSE}" | grep -q "neo4j"; then
    log_success "Status do Neo4j disponível"
  fi
else
  log_error "Endpoint /ready não está respondendo corretamente"
fi

# Testar endpoint /metrics
log_info "Testando endpoint /metrics..."
METRICS_RESPONSE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -fsSL http://localhost:8000/metrics 2>/dev/null || echo "")

if echo "${METRICS_RESPONSE}" | grep -q "neural_hive"; then
  log_success "Endpoint /metrics está disponível com métricas customizadas"
else
  log_error "Endpoint /metrics não está respondendo corretamente"
fi

# 3. Teste de Conectividade
log_section "3. TESTE DE CONECTIVIDADE"

# Verificar conexão Kafka nos logs
log_info "Verificando conexão com Kafka nos logs..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -i "kafka\|consumer\|connected" | grep -v "disconnected" > /dev/null 2>&1; then
  log_success "Logs indicam conexão com Kafka"
else
  log_warning "Não foi possível confirmar conexão com Kafka pelos logs"
fi

# Verificar conexão Neo4j nos logs
log_info "Verificando conexão com Neo4j nos logs..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -i "neo4j" | grep -i "connect\|initialized" > /dev/null 2>&1; then
  log_success "Logs indicam conexão com Neo4j"
else
  log_warning "Não foi possível confirmar conexão com Neo4j pelos logs"
fi

# Verificar conexão MongoDB nos logs
log_info "Verificando conexão com MongoDB nos logs..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -i "mongodb\|mongo" | grep -i "connect\|initialized" > /dev/null 2>&1; then
  log_success "Logs indicam conexão com MongoDB"
else
  log_warning "Não foi possível confirmar conexão com MongoDB pelos logs"
fi

# Verificar conexão Redis nos logs
log_info "Verificando conexão com Redis nos logs..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -i "redis" | grep -i "connect\|initialized" > /dev/null 2>&1; then
  log_success "Logs indicam conexão com Redis"
else
  log_warning "Não foi possível confirmar conexão com Redis pelos logs"
fi

# 4. Teste End-to-End
log_section "4. TESTE END-TO-END (FLUXO COMPLETO)"

# Criar Intent Envelope de teste
log_info "Criando Intent Envelope de teste..."
INTENT_ENVELOPE=$(cat <<EOF
{
  "id": "${INTENT_ID}",
  "actor": {
    "type": "human",
    "id": "test-user-123",
    "name": "Test User"
  },
  "intent": {
    "text": "Criar API REST para gerenciar produtos com operações CRUD completas",
    "domain": "business",
    "classification": "api-creation",
    "entities": [
      {"type": "resource", "value": "produtos"},
      {"type": "operation", "value": "CRUD"}
    ],
    "keywords": ["API", "REST", "produtos", "CRUD", "gerenciar"]
  },
  "confidence": 0.95,
  "context": {
    "session_id": "test-session-${TIMESTAMP_MS}",
    "user_id": "test-user-123",
    "tenant_id": "test-tenant",
    "channel": "test"
  },
  "constraints": {
    "priority": "high",
    "security_level": "internal"
  },
  "timestamp": ${TIMESTAMP_MS}
}
EOF
)

log_info "Intent Envelope criado: ${INTENT_ID}"

# Publicar Intent Envelope no Kafka
log_info "Publicando Intent Envelope no Kafka (topic: intentions.business)..."

kubectl run kafka-producer-test-${TIMESTAMP_MS} --restart='Never' \
  --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace ${KAFKA_NAMESPACE} \
  --command -- sh -c "echo '${INTENT_ENVELOPE}' | \
    /opt/bitnami/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server ${KAFKA_BOOTSTRAP} \
    --topic intentions.business" > /dev/null 2>&1

sleep 3

# Limpar pod temporário
kubectl delete pod kafka-producer-test-${TIMESTAMP_MS} -n ${KAFKA_NAMESPACE} --force --grace-period=0 &> /dev/null || true

log_success "Intent Envelope publicado"

# Aguardar processamento
log_info "Aguardando processamento (15 segundos)..."
sleep 15

# Verificar consumo nos logs
log_info "Verificando consumo da mensagem nos logs..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -q "${INTENT_ID}"; then
  log_success "Intent Envelope foi consumido (ID encontrado nos logs)"
else
  log_error "Intent Envelope não foi consumido (ID não encontrado nos logs)"
fi

# Verificar geração do plano nos logs
log_info "Verificando geração do plano cognitivo..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -i "plan\|cognitive\|generated" | grep -v "planning" > /dev/null 2>&1; then
  log_success "Logs indicam geração de plano cognitivo"

  # Tentar extrair plan_id dos logs
  PLAN_ID=$(kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 | grep -oP 'plan[_-]?id["\s:=]+[a-zA-Z0-9-]+' | head -1 || echo "")
  if [ -n "${PLAN_ID}" ]; then
    log_info "Plan ID extraído: ${PLAN_ID}"
  fi
else
  log_warning "Não foi possível confirmar geração do plano pelos logs"
fi

# Verificar publicação no topic plans.ready
log_info "Verificando publicação no topic plans.ready..."

# Consumir última mensagem do topic
PLAN_MESSAGE=$(kubectl run kafka-consumer-test-${TIMESTAMP_MS} --restart='Never' \
  --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace ${KAFKA_NAMESPACE} \
  --command -- sh -c "/opt/bitnami/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server ${KAFKA_BOOTSTRAP} \
    --topic plans.ready \
    --from-beginning \
    --max-messages 1 \
    --timeout-ms 5000" 2>/dev/null || echo "")

sleep 5

# Obter logs do consumer
CONSUMER_OUTPUT=$(kubectl logs kafka-consumer-test-${TIMESTAMP_MS} -n ${KAFKA_NAMESPACE} 2>/dev/null || echo "")

# Limpar pod temporário
kubectl delete pod kafka-consumer-test-${TIMESTAMP_MS} -n ${KAFKA_NAMESPACE} --force --grace-period=0 &> /dev/null || true

if echo "${CONSUMER_OUTPUT}" | grep -q "${INTENT_ID}\|plan_id\|cognitive"; then
  log_success "Plano cognitivo publicado no topic plans.ready"

  # Validar estrutura JSON (básico)
  if echo "${CONSUMER_OUTPUT}" | grep -q "\"plan_id\""; then
    log_success "Plano contém campo plan_id"
  fi

  if echo "${CONSUMER_OUTPUT}" | grep -q "\"intent_id\""; then
    log_success "Plano contém campo intent_id"
  fi

  if echo "${CONSUMER_OUTPUT}" | grep -q "\"steps\""; then
    log_success "Plano contém campo steps"
  fi
else
  log_warning "Não foi possível confirmar publicação do plano"
fi

# 5. Teste de Métricas
log_section "5. VALIDAÇÃO DE MÉTRICAS"

log_info "Consultando métricas Prometheus..."
METRICS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -fsSL http://localhost:8000/metrics 2>/dev/null || echo "")

# Verificar métricas esperadas
if echo "${METRICS}" | grep -q "neural_hive_plans_generated_total"; then
  log_success "Métrica neural_hive_plans_generated_total disponível"
fi

if echo "${METRICS}" | grep -q "neural_hive_kafka_messages_consumed_total"; then
  log_success "Métrica neural_hive_kafka_messages_consumed_total disponível"
fi

if echo "${METRICS}" | grep -q "neural_hive_plan_generation_duration_seconds"; then
  log_success "Métrica neural_hive_plan_generation_duration_seconds disponível"
fi

# Verificar se métricas têm valores > 0 (indicando atividade)
if echo "${METRICS}" | grep "neural_hive_plans_generated_total" | grep -v " 0$\| 0.0$" > /dev/null 2>&1; then
  log_success "Planos foram gerados (contador > 0)"
fi

# 6. Resumo Final
log_section "RESUMO DOS TESTES"

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
SUCCESS_RATE=$((TESTS_PASSED * 100 / TOTAL_TESTS))

echo ""
log_info "Total de testes executados: ${TOTAL_TESTS}"
log_success "Testes passaram: ${TESTS_PASSED}"
if [ ${TESTS_FAILED} -gt 0 ]; then
  log_error "Testes falharam: ${TESTS_FAILED}"
fi
log_info "Taxa de sucesso: ${SUCCESS_RATE}%"
echo ""

if [ ${TESTS_FAILED} -eq 0 ]; then
  log_section "✅ TODOS OS TESTES PASSARAM!"
  echo ""
  log_info "O Semantic Translation Engine está funcionando corretamente."
  log_info "Próximos passos:"
  echo "  1. Verificar traces no Jaeger (se disponível)"
  echo "  2. Explorar métricas no Grafana (se disponível)"
  echo "  3. Prosseguir com deploy dos Especialistas Neurais"
  echo ""
  exit 0
else
  log_section "⚠️  ALGUNS TESTES FALHARAM"
  echo ""
  log_info "Comandos para troubleshooting:"
  echo ""
  echo "  # Ver logs completos:"
  echo "  kubectl logs -n ${NAMESPACE} ${POD_NAME} -f"
  echo ""
  echo "  # Verificar eventos do pod:"
  echo "  kubectl describe pod -n ${NAMESPACE} ${POD_NAME}"
  echo ""
  echo "  # Verificar configuração:"
  echo "  kubectl get configmap -n ${NAMESPACE} semantic-translation-engine -o yaml"
  echo ""
  echo "  # Reiniciar pod:"
  echo "  kubectl delete pod -n ${NAMESPACE} ${POD_NAME}"
  echo ""
  exit 1
fi
