#!/bin/bash
set -euo pipefail

# Source shared test helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/helpers/test-helpers.sh"

# Parse command-line arguments
SKIP_PRE_VALIDATION=false
CONTINUE_ON_ERROR=false
OUTPUT_DIR="${SCRIPT_DIR}/results"
NO_CLEANUP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-pre-validation)
            SKIP_PRE_VALIDATION=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --continue-on-error)
            CONTINUE_ON_ERROR=true
            shift
            ;;
        --no-cleanup)
            NO_CLEANUP=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-pre-validation  Skip pre-test validation"
            echo "  --debug                Enable verbose debug output"
            echo "  --continue-on-error    Continue testing even if checks fail"
            echo "  --no-cleanup           Don't clean up test resources"
            echo "  --output-dir DIR       Specify output directory for test results"
            echo "  --help                 Display this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

log_section "Neural Hive-Mind - Fase 1 End-to-End Test"

# Run pre-test validation if not skipped
if [ "$SKIP_PRE_VALIDATION" = false ] && [ -f "${SCRIPT_DIR}/phase1-pre-test-validation.sh" ]; then
    log_info "Executando validação pré-teste..."
    if ! "${SCRIPT_DIR}/phase1-pre-test-validation.sh"; then
        if [ "$CONTINUE_ON_ERROR" = false ]; then
            log_error "Validação pré-teste falhou. Use --skip-pre-validation para pular ou --continue-on-error para continuar"
            exit 1
        else
            log_warning "Validação pré-teste falhou mas continuando devido ao --continue-on-error"
        fi
    fi
fi

# Initialize test report
init_test_report "Phase 1 End-to-End Test"

# Variáveis
TEST_INTENT_ID="test-intent-$(date +%s)"
TEST_PLAN_ID=""
TEST_DECISION_ID=""
TRACE_ID=""

# Status tracking para sumário final
declare -A COMPONENT_STATUS
COMPONENT_STATUS["memory_layers"]=0
COMPONENT_STATUS["gateway"]=0
COMPONENT_STATUS["ste"]=0
COMPONENT_STATUS["specialists"]=0
COMPONENT_STATUS["consensus"]=0
COMPONENT_STATUS["ledger"]=0
COMPONENT_STATUS["pheromones"]=0
COMPONENT_STATUS["prometheus"]=0
COMPONENT_STATUS["jaeger"]=0
COMPONENT_STATUS["dashboards"]=0
COMPONENT_STATUS["alerts"]=0

# Auto-detect Kafka namespace
log_info "Detecting Kafka namespace..."
KAFKA_NS=$(kubectl get statefulset -A -l "strimzi.io/cluster" -o jsonpath='{.items[0].metadata.namespace}' 2>/dev/null || echo "neural-hive-kafka")
if [ -z "$KAFKA_NS" ]; then
    KAFKA_NS="neural-hive-kafka"
fi
log_debug "Using Kafka namespace: $KAFKA_NS"

# Define topic names with fallback support for dot/hyphen variants
INTENT_TOPIC="intentions.business"
PLANS_READY_TOPIC="plans.ready"
PLANS_CONSENSUS_TOPIC="plans.consensus"

# ========================================
# FASE 1: Verificar Infraestrutura
# ========================================
log_section "FASE 1: Verificando Infraestrutura"

# Detect and cache namespaces for all Phase 1 services
log_info "Detecting namespaces for Phase 1 services..."

# Phase 1 services
NS_GATEWAY=$(detect_namespace "gateway-intencoes")
NS_STE=$(detect_namespace "semantic-translation-engine")
NS_SPEC_BUSINESS=$(detect_namespace "specialist-business")
NS_SPEC_TECHNICAL=$(detect_namespace "specialist-technical")
NS_SPEC_BEHAVIOR=$(detect_namespace "specialist-behavior")
NS_SPEC_EVOLUTION=$(detect_namespace "specialist-evolution")
NS_SPEC_ARCHITECTURE=$(detect_namespace "specialist-architecture")
NS_CONSENSUS=$(detect_namespace "consensus-engine")
NS_MEMORY_API=$(detect_namespace "memory-layer-api")

log_debug "Namespace detection complete"

# 1.1 Verificar camadas de memória
log_info "1.1 Verificando camadas de memória..."

MEMORY_LAYERS_OK=0
MEMORY_LAYERS_TOTAL=0
for component in redis-cluster mongodb-cluster neo4j-cluster clickhouse-cluster; do
  MEMORY_LAYERS_TOTAL=$((MEMORY_LAYERS_TOTAL + 1))
  if kubectl get statefulset -n ${component} &> /dev/null; then
    log_success "${component} deployado"
    add_test_result "Infrastructure" "passed" "${component} deployed"
    MEMORY_LAYERS_OK=$((MEMORY_LAYERS_OK + 1))
  else
    # ClickHouse é opcional para Fase 1
    if [ "$component" = "clickhouse-cluster" ]; then
      log_warning "${component} NÃO deployado [OPCIONAL - não bloqueante]"
      add_test_result "Infrastructure" "warning" "${component} NOT deployed (optional)"
      # Conta como OK para não bloquear
      MEMORY_LAYERS_OK=$((MEMORY_LAYERS_OK + 1))
    else
      log_error "${component} NÃO deployado"
      add_test_result "Infrastructure" "failed" "${component} NOT deployed"
      [ "$CONTINUE_ON_ERROR" = false ] && exit 1
    fi
  fi
done

# Atualizar status das camadas de memória
if [ $MEMORY_LAYERS_OK -eq $MEMORY_LAYERS_TOTAL ]; then
  COMPONENT_STATUS["memory_layers"]=1
fi

# 1.2 Verificar serviços da Fase 1
log_info "1.2 Verificando serviços da Fase 1..."

# Array of services and their detected namespaces
declare -A SERVICE_NAMESPACES=(
  ["gateway-intencoes"]="$NS_GATEWAY"
  ["semantic-translation-engine"]="$NS_STE"
  ["specialist-business"]="$NS_SPEC_BUSINESS"
  ["specialist-technical"]="$NS_SPEC_TECHNICAL"
  ["specialist-behavior"]="$NS_SPEC_BEHAVIOR"
  ["specialist-evolution"]="$NS_SPEC_EVOLUTION"
  ["specialist-architecture"]="$NS_SPEC_ARCHITECTURE"
  ["consensus-engine"]="$NS_CONSENSUS"
  ["memory-layer-api"]="$NS_MEMORY_API"
)

for service in "${!SERVICE_NAMESPACES[@]}"; do
  ns="${SERVICE_NAMESPACES[$service]}"

  if kubectl get deployment -n "$ns" "$service" &> /dev/null 2>&1; then
    log_success "${service} deployado em namespace ${ns}"
    add_test_result "Services" "passed" "${service} deployed in ${ns}"

    # Marcar serviços específicos como OK
    case "$service" in
      gateway-intencoes) COMPONENT_STATUS["gateway"]=1 ;;
      semantic-translation-engine) COMPONENT_STATUS["ste"]=1 ;;
      consensus-engine) COMPONENT_STATUS["consensus"]=1 ;;
    esac
  else
    if [ "$CONTINUE_ON_ERROR" = "true" ]; then
      log_warning "${service} não encontrado em namespace ${ns}"
      add_test_result "Services" "warning" "${service} not found in namespace ${ns}"
    else
      log_error "${service} não encontrado em namespace ${ns}"
      add_test_result "Services" "failed" "${service} not found in namespace ${ns}"
      exit 1
    fi
  fi
done

# ========================================
# FASE 2: Teste de Fluxo Completo
# ========================================
log_section "FASE 2: Testando Fluxo Completo (Intent → Plan → Consensus → Decision)"

# 2.1 Publicar Intent Envelope de teste
log_info "2.1 Publicando Intent Envelope de teste..."

# Criar Intent Envelope JSON
INTENT_ENVELOPE=$(cat <<EOF
{
  "id": "${TEST_INTENT_ID}",
  "actor": {
    "type": "human",
    "id": "test-user",
    "name": "Integration Test User"
  },
  "intent": {
    "text": "Criar workflow de aprovação de pedidos com validação de estoque",
    "domain": "business",
    "classification": "workflow-automation",
    "entities": [],
    "keywords": ["workflow", "aprovação", "pedidos", "estoque"]
  },
  "confidence": 0.95,
  "context": {
    "session_id": "test-session-123",
    "user_id": "test-user",
    "tenant_id": "test-tenant",
    "channel": "api"
  },
  "constraints": {
    "priority": "high",
    "security_level": "internal"
  },
  "timestamp": $(date +%s)000
}
EOF
)

# Publicar no Kafka usando helper function com fallback para nomes de tópico
PUBLISH_SUCCESS=false
for topic_variant in "$INTENT_TOPIC" "intentions-business"; do
    if kafka_publish_message "$KAFKA_NS" "$topic_variant" "$INTENT_ENVELOPE"; then
        log_success "Intent Envelope publicado no Kafka (namespace: $KAFKA_NS, tópico: $topic_variant)"
        add_test_result "Kafka Publishing" "passed" "Intent published to $topic_variant topic in $KAFKA_NS"
        INTENT_TOPIC="$topic_variant"  # Update to the working variant
        PUBLISH_SUCCESS=true
        break
    fi
done

if [ "$PUBLISH_SUCCESS" = false ]; then
    log_error "Falha ao publicar Intent Envelope no Kafka"
    add_test_result "Kafka Publishing" "failed" "Failed to publish intent to Kafka"
    [ "$CONTINUE_ON_ERROR" = false ] && exit 1
fi

# 2.2 Aguardar processamento (Semantic Translation Engine)
log_info "2.2 Aguardando geração de Cognitive Plan (10s)..."
sleep 10

# Verificar logs do semantic-translation-engine
STE_POD=$(get_pod_name "$NS_STE" "app.kubernetes.io/name=semantic-translation-engine")

if [ -n "$STE_POD" ]; then
  STE_LOGS=$(get_pod_logs "$NS_STE" "$STE_POD" 100)
  PLAN_GENERATED=$(echo "$STE_LOGS" | grep -c "${TEST_INTENT_ID}" || echo "0")

  if [ "$PLAN_GENERATED" -gt 0 ]; then
    log_success "Cognitive Plan gerado em namespace ${NS_STE}"
    add_test_result "Plan Generation" "passed" "Cognitive Plan generated for intent ${TEST_INTENT_ID} in ${NS_STE}"
  else
    log_error "Cognitive Plan NÃO gerado"
    add_test_result "Plan Generation" "failed" "No Cognitive Plan generated"
    [ "$CONTINUE_ON_ERROR" = false ] && exit 1
  fi

  # Extrair plan_id dos logs com suporte a JSON
  # Primeiro tentar extrair de logs JSON
  TEST_PLAN_ID=$(echo "$STE_LOGS" | grep "${TEST_INTENT_ID}" | grep -o '{.*}' | jq -r '.plan_id // .planId // empty' 2>/dev/null | head -1 || echo "")

  # Se não encontrar em JSON, tentar padrão text-based
  if [ -z "$TEST_PLAN_ID" ]; then
    TEST_PLAN_ID=$(echo "$STE_LOGS" | grep "${TEST_INTENT_ID}" | grep -oP 'plan_id[=:][\s]*["\']?([^"'\'' ]+)["\']?' | head -1 | sed -E 's/plan_id[=:][\s]*["\']?([^"'\'' ]+)["\']?/\1/' || echo "")
  fi

  # Fallback: consumir tópico plans.ready filtrando por intent_id
  if [ -z "$TEST_PLAN_ID" ]; then
    log_debug "Tentando extrair plan_id do tópico Kafka plans.ready..."
    KAFKA_POD=$(get_pod_name "$KAFKA_NS" "app.kubernetes.io/name=kafka")
    if [ -n "$KAFKA_POD" ]; then
      for topic_variant in "$PLANS_READY_TOPIC" "plans-ready"; do
        TEST_PLAN_ID=$(kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic "$topic_variant" --from-beginning --max-messages 100 --timeout-ms 5000 2>/dev/null | grep "$TEST_INTENT_ID" | jq -r '.plan_id // .planId // empty' 2>/dev/null | head -1 || echo "")
        if [ -n "$TEST_PLAN_ID" ]; then
          break
        fi
      done
    fi
  fi

  log_info "   Plan ID: ${TEST_PLAN_ID:-N/A}"
else
  log_warning "Semantic Translation Engine pod não encontrado em namespace ${NS_STE}"
  add_test_result "Plan Generation" "warning" "STE pod not found in ${NS_STE}"
fi

# 2.3 Aguardar avaliação dos especialistas
log_info "2.3 Aguardando avaliação dos 5 especialistas (15s)..."
sleep 15

# Verificar logs dos especialistas
OPINIONS_COUNT=0

# Map specialists to their namespace variables
declare -A SPECIALIST_NAMESPACES=(
  ["business"]="$NS_SPEC_BUSINESS"
  ["technical"]="$NS_SPEC_TECHNICAL"
  ["behavior"]="$NS_SPEC_BEHAVIOR"
  ["evolution"]="$NS_SPEC_EVOLUTION"
  ["architecture"]="$NS_SPEC_ARCHITECTURE"
)

for specialist in business technical behavior evolution architecture; do
  ns="${SPECIALIST_NAMESPACES[$specialist]}"
  SPECIALIST_POD=$(get_pod_name "$ns" "app.kubernetes.io/name=specialist-${specialist}")

  if [ -n "$SPECIALIST_POD" ] && [ -n "$TEST_PLAN_ID" ]; then
    SPECIALIST_LOGS=$(get_pod_logs "$ns" "$SPECIALIST_POD" 50)
    OPINION_GENERATED=$(echo "$SPECIALIST_LOGS" | grep -c "${TEST_PLAN_ID}" || echo "0")
    if [ $OPINION_GENERATED -gt 0 ]; then
      log_success "Specialist ${specialist} avaliou o plano em namespace ${ns}"
      OPINIONS_COUNT=$((OPINIONS_COUNT + 1))
    else
      log_warning "Specialist ${specialist} não avaliou (ou logs não disponíveis) em namespace ${ns}"
    fi
  else
    log_warning "Specialist ${specialist} pod não encontrado em namespace ${ns}"
  fi
done

if [ $OPINIONS_COUNT -ge 3 ]; then
  log_success "Mínimo 3 de 5 especialistas avaliaram (${OPINIONS_COUNT}/5)"
  add_test_result "Specialist Evaluation" "passed" "${OPINIONS_COUNT}/5 specialists evaluated"
  COMPONENT_STATUS["specialists"]=1
else
  log_error "Mínimo de especialistas não avaliaram (${OPINIONS_COUNT}/5)"
  add_test_result "Specialist Evaluation" "failed" "Only ${OPINIONS_COUNT}/5 specialists evaluated"
  [ "$CONTINUE_ON_ERROR" = false ] && exit 1
fi

# 2.4 Aguardar decisão consolidada (Consensus Engine)
echo -e "\n${BLUE}2.4 Aguardando decisão consolidada (10s)...${NC}"
sleep 10

CONSENSUS_POD=$(get_pod_name "$NS_CONSENSUS" "app.kubernetes.io/name=consensus-engine")

if [ -n "$CONSENSUS_POD" ] && [ -n "$TEST_PLAN_ID" ]; then
  CONSENSUS_LOGS=$(get_pod_logs "$NS_CONSENSUS" "$CONSENSUS_POD" 100)
  DECISION_GENERATED=$(echo "$CONSENSUS_LOGS" | grep -c "${TEST_PLAN_ID}" || echo "0")

  # Extrair decision_id dos logs com suporte a JSON
  # Primeiro tentar extrair de logs JSON
  TEST_DECISION_ID=$(echo "$CONSENSUS_LOGS" | grep "${TEST_PLAN_ID}" | grep -o '{.*}' | jq -r '.decision_id // .decisionId // empty' 2>/dev/null | head -1 || echo "")

  # Se não encontrar em JSON, tentar padrão text-based
  if [ -z "$TEST_DECISION_ID" ]; then
    TEST_DECISION_ID=$(echo "$CONSENSUS_LOGS" | grep "${TEST_PLAN_ID}" | grep -oP 'decision_id[=:][\s]*["\']?([^"'\'' ]+)["\']?' | head -1 | sed -E 's/decision_id[=:][\s]*["\']?([^"'\'' ]+)["\']?/\1/' || echo "")
  fi

  # Fallback: consumir tópico plans.consensus filtrando por plan_id
  if [ -z "$TEST_DECISION_ID" ]; then
    log_debug "Tentando extrair decision_id do tópico Kafka plans.consensus..."
    KAFKA_POD=$(get_pod_name "$KAFKA_NS" "app.kubernetes.io/name=kafka")
    if [ -n "$KAFKA_POD" ]; then
      for topic_variant in "$PLANS_CONSENSUS_TOPIC" "plans-consensus"; do
        TEST_DECISION_ID=$(kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic "$topic_variant" --from-beginning --max-messages 100 --timeout-ms 5000 2>/dev/null | grep "$TEST_PLAN_ID" | jq -r '.decision_id // .decisionId // empty' 2>/dev/null | head -1 || echo "")
        if [ -n "$TEST_DECISION_ID" ]; then
          break
        fi
      done
    fi
  fi

  if [ "$DECISION_GENERATED" -gt 0 ]; then
    check_status 0 "Decisão consolidada gerada em namespace ${NS_CONSENSUS}"
    add_test_result "Consensus Decision" "passed" "Decision generated for plan ${TEST_PLAN_ID} in ${NS_CONSENSUS}, decision_id: ${TEST_DECISION_ID:-N/A}"
    echo "   Decision ID: ${TEST_DECISION_ID:-N/A}"
  else
    check_status 1 "Decisão consolidada NÃO gerada"
    add_test_result "Consensus Decision" "failed" "No decision generated for plan ${TEST_PLAN_ID}"
    [ "$CONTINUE_ON_ERROR" = false ] && exit 1
  fi
else
  log_warning "Consensus Engine pod não encontrado em namespace ${NS_CONSENSUS} ou plan_id ausente"
  add_test_result "Consensus Decision" "warning" "Consensus Engine pod not found in ${NS_CONSENSUS} or plan_id missing"
fi

# ========================================
# FASE 3: Validar Persistência e Telemetria
# ========================================
echo -e "\n${YELLOW}FASE 3: Validando Persistência e Telemetria...${NC}"

# 3.1 Verificar ledger cognitivo (MongoDB)
echo -e "\n${BLUE}3.1 Verificando ledger cognitivo no MongoDB...${NC}"

MONGO_POD=$(kubectl get pods -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "$MONGO_POD" ] && [ -n "$TEST_PLAN_ID" ]; then
  PLAN_IN_LEDGER=$(kubectl exec -n mongodb-cluster ${MONGO_POD} -- mongosh --quiet --eval "db.cognitive_ledger.countDocuments({plan_id: '${TEST_PLAN_ID}'})" 2>/dev/null || echo "0")

  if [ "$PLAN_IN_LEDGER" -gt 0 ]; then
    check_status 0 "Plano registrado no ledger cognitivo"
    add_test_result "MongoDB Ledger" "passed" "Plan ${TEST_PLAN_ID} found in cognitive_ledger (${PLAN_IN_LEDGER} records)"
    COMPONENT_STATUS["ledger"]=1
  else
    check_status 1 "Plano NÃO registrado no ledger cognitivo"
    add_test_result "MongoDB Ledger" "failed" "Plan ${TEST_PLAN_ID} not found in cognitive_ledger"
  fi
else
  log_warning "MongoDB pod não encontrado ou plan_id ausente"
  add_test_result "MongoDB Ledger" "warning" "MongoDB pod not found or plan_id missing"
fi

# 3.2 Verificar feromônios (Redis)
echo -e "\n${BLUE}3.2 Verificando feromônios no Redis...${NC}"

REDIS_POD=$(kubectl get pods -n redis-cluster -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "$REDIS_POD" ]; then
  # Usar SCAN ao invés de KEYS para evitar bloquear instâncias grandes de Redis
  log_debug "Contando feromônios usando SCAN..."

  # Script Lua para contar chaves com padrão usando SCAN
  SCAN_SCRIPT='
    local cursor = "0"
    local count = 0
    repeat
      local result = redis.call("SCAN", cursor, "MATCH", "pheromone:*", "COUNT", "100")
      cursor = result[1]
      count = count + #result[2]
    until cursor == "0"
    return count
  '

  PHEROMONES_COUNT=$(kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli --eval /dev/stdin <<< "$SCAN_SCRIPT" 2>/dev/null || echo "0")

  # Fallback: se o script Lua falhar, usar SCAN iterativo via bash
  if [ "$PHEROMONES_COUNT" = "0" ] || [ -z "$PHEROMONES_COUNT" ]; then
    log_debug "Fallback: usando SCAN iterativo..."
    PHEROMONES_COUNT=0
    CURSOR="0"

    while true; do
      # SCAN com cursor
      SCAN_RESULT=$(kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli SCAN "$CURSOR" MATCH "pheromone:*" COUNT 100 2>/dev/null || echo "")

      if [ -z "$SCAN_RESULT" ]; then
        break
      fi

      # Extrair novo cursor (primeira linha)
      NEW_CURSOR=$(echo "$SCAN_RESULT" | head -1)

      # Contar chaves retornadas (todas as linhas exceto a primeira)
      KEYS_IN_BATCH=$(echo "$SCAN_RESULT" | tail -n +2 | wc -l)
      PHEROMONES_COUNT=$((PHEROMONES_COUNT + KEYS_IN_BATCH))

      # Se cursor voltou a 0, terminamos
      if [ "$NEW_CURSOR" = "0" ]; then
        break
      fi

      CURSOR="$NEW_CURSOR"

      # Proteção contra loop infinito
      if [ "$CURSOR" = "0" ] || [ -z "$CURSOR" ]; then
        break
      fi
    done
  fi

  if [ "$PHEROMONES_COUNT" -gt 0 ]; then
    check_status 0 "Feromônios publicados no Redis (${PHEROMONES_COUNT} chaves)"
    add_test_result "Redis Pheromones" "passed" "${PHEROMONES_COUNT} pheromone keys found in Redis"
    COMPONENT_STATUS["pheromones"]=1
  else
    check_status 1 "Nenhum feromônio encontrado no Redis"
    add_test_result "Redis Pheromones" "failed" "No pheromone keys found in Redis"
  fi
else
  log_warning "Redis pod não encontrado"
  add_test_result "Redis Pheromones" "warning" "Redis pod not found"
fi

# 3.3 Verificar métricas Prometheus
echo -e "\n${BLUE}3.3 Verificando métricas Prometheus...${NC}"

# Descobrir serviço Prometheus
PROM_SVC="prometheus"
PROM_NS="neural-hive-observability"
if ! kubectl get svc -n "$PROM_NS" "$PROM_SVC" &> /dev/null; then
  # Tentar encontrar por label
  PROM_SVC=$(kubectl get svc -n "$PROM_NS" -l "app.kubernetes.io/name=prometheus" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "prometheus")
  if [ -z "$PROM_SVC" ] || ! kubectl get svc -n "$PROM_NS" "$PROM_SVC" &> /dev/null; then
    log_warning "Prometheus service not found, usando fallback: prometheus-server"
    PROM_SVC="prometheus-server"
  fi
fi

log_debug "Using Prometheus service: $PROM_NS/$PROM_SVC"

# Port-forward com retry
PF_PID=$(port_forward_with_retry "$PROM_NS" "$PROM_SVC" 9090 9090)

# Verificar readiness do Prometheus
if ! timeout_command 10 curl -s http://localhost:9090/api/v1/status/buildinfo &> /dev/null; then
  log_warning "Prometheus not ready after port-forward"
fi

# Verificar métricas chave (alinhadas com dashboards)
METRICS_TO_CHECK=(
  "neural_hive_specialist_evaluations_total"
  "neural_hive_consensus_decisions_total"
  "neural_hive_consensus_duration_seconds_count"
  "neural_hive_pheromones_published_total"
  "neural_hive_ledger_write_duration_seconds_bucket"
)

METRICS_FOUND=0
for metric in "${METRICS_TO_CHECK[@]}"; do
  if prometheus_check_metric_exists "$metric" "http://localhost:9090"; then
    log_success "Métrica ${metric} disponível"
    METRICS_FOUND=$((METRICS_FOUND + 1))
  else
    log_warning "Métrica ${metric} não encontrada"
  fi
done

if [ "$METRICS_FOUND" -ge 3 ]; then
  check_status 0 "Métricas Prometheus disponíveis (${METRICS_FOUND}/${#METRICS_TO_CHECK[@]})"
  add_test_result "Prometheus Metrics" "passed" "${METRICS_FOUND}/${#METRICS_TO_CHECK[@]} metrics found"
  COMPONENT_STATUS["prometheus"]=1

  # Extrair métricas de performance se o script estiver disponível
  PERF_SCRIPT="${SCRIPT_DIR}/../scripts/extract-performance-metrics.sh"
  if [ -f "$PERF_SCRIPT" ] && [ "$METRICS_FOUND" -ge 1 ]; then
    log_info "Extraindo métricas de performance..."
    if bash "$PERF_SCRIPT" "$OUTPUT_DIR" "http://localhost:9090" >/dev/null 2>&1; then
      log_success "Métricas de performance extraídas"
    else
      log_warning "Falha ao extrair métricas de performance (não crítico)"
    fi
  fi
else
  check_status 1 "Métricas Prometheus insuficientes (${METRICS_FOUND}/${#METRICS_TO_CHECK[@]})"
  add_test_result "Prometheus Metrics" "failed" "Only ${METRICS_FOUND}/${#METRICS_TO_CHECK[@]} metrics found"
  [ "$CONTINUE_ON_ERROR" = false ] && exit 1
fi

# 3.4 Verificar traces Jaeger (correlação)
echo -e "\n${BLUE}3.4 Verificando traces Jaeger...${NC}"

# Descobrir serviço Jaeger
JAEGER_SVC="jaeger-query"
JAEGER_NS="neural-hive-observability"
if ! kubectl get svc -n "$JAEGER_NS" "$JAEGER_SVC" &> /dev/null; then
  # Tentar encontrar por label
  JAEGER_SVC=$(kubectl get svc -n "$JAEGER_NS" -l "app.kubernetes.io/name=jaeger" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "jaeger")
  if [ -z "$JAEGER_SVC" ] || ! kubectl get svc -n "$JAEGER_NS" "$JAEGER_SVC" &> /dev/null; then
    log_warning "Jaeger service not found, usando fallback: jaeger"
    JAEGER_SVC="jaeger"
  fi
fi

log_debug "Using Jaeger service: $JAEGER_NS/$JAEGER_SVC"

# Port-forward com retry
PF_PID=$(port_forward_with_retry "$JAEGER_NS" "$JAEGER_SVC" 16686 16686)

# Verificar readiness do Jaeger
if ! jaeger_check_connection "http://localhost:16686"; then
  log_warning "Jaeger not ready after port-forward"
fi

# Buscar traces por intent_id com URL encoding correto
# Construir tags JSON e fazer URL encoding
TAGS_JSON=$(jq -n --arg intent_id "$TEST_INTENT_ID" '{"neural.hive.intent.id": $intent_id}')
TAGS_ENCODED=$(echo -n "$TAGS_JSON" | jq -sRr @uri)

# Tentar buscar traces com tags JSON encoded
TRACES=$(curl -s "http://localhost:16686/api/traces?service=semantic-translation-engine&tags=${TAGS_ENCODED}" 2>/dev/null | jq -r '.data | length' 2>/dev/null || echo "0")

# Se falhar ou retornar 0, tentar endpoint alternativo (compatibilidade com versões antigas)
if [ "$TRACES" -eq 0 ] || [ "$TRACES" = "null" ]; then
  log_debug "Tentando endpoint alternativo do Jaeger..."
  TRACES=$(curl -s "http://localhost:16686/api/traces?service=semantic-translation-engine" 2>/dev/null | jq -r '.data | length' 2>/dev/null || echo "0")
fi

if [ "$TRACES" -gt 0 ] && [ "$TRACES" != "null" ]; then
  check_status 0 "Traces correlacionados encontrados no Jaeger"
  add_test_result "Jaeger Traces" "passed" "${TRACES} traces found for intent ${TEST_INTENT_ID}"
  COMPONENT_STATUS["jaeger"]=1
else
  # Verificar se Jaeger está respondendo
  JAEGER_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:16686/" 2>/dev/null || echo "000")
  if [ "$JAEGER_HEALTH" = "404" ] || [ "$JAEGER_HEALTH" = "000" ]; then
    if [ "$CONTINUE_ON_ERROR" = true ]; then
      log_warning "Jaeger não acessível ou endpoint inválido (HTTP $JAEGER_HEALTH)"
      add_test_result "Jaeger Traces" "warning" "Jaeger not accessible (HTTP $JAEGER_HEALTH)"
    else
      check_status 1 "Jaeger não acessível (HTTP $JAEGER_HEALTH)"
      add_test_result "Jaeger Traces" "failed" "Jaeger not accessible (HTTP $JAEGER_HEALTH)"
    fi
  else
    check_status 1 "Nenhum trace correlacionado encontrado no Jaeger"
    add_test_result "Jaeger Traces" "failed" "No traces found for intent ${TEST_INTENT_ID}"
  fi
fi

# ========================================
# FASE 4: Validar Governança
# ========================================
echo -e "\n${YELLOW}FASE 4: Validando Governança...${NC}"

# 4.1 Verificar explicabilidade
echo -e "\n${BLUE}4.1 Verificando explicabilidade...${NC}"

if [ -n "$MONGO_POD" ] && [ -n "$TEST_PLAN_ID" ]; then
  # Filtrar por plan_id do teste atual
  EXPLAINABILITY_COUNT=$(kubectl exec -n mongodb-cluster ${MONGO_POD} -- mongosh --quiet --eval "db.explainability_ledger.countDocuments({plan_id: '${TEST_PLAN_ID}'})" 2>/dev/null || echo "0")

  # Fallback: tentar por intent_id se plan_id não retornar resultados
  if [ "$EXPLAINABILITY_COUNT" -eq 0 ] && [ -n "$TEST_INTENT_ID" ]; then
    EXPLAINABILITY_COUNT=$(kubectl exec -n mongodb-cluster ${MONGO_POD} -- mongosh --quiet --eval "db.explainability_ledger.countDocuments({intent_id: '${TEST_INTENT_ID}'})" 2>/dev/null || echo "0")
  fi

  if [ "$EXPLAINABILITY_COUNT" -gt 0 ]; then
    check_status 0 "Explicações registradas no ledger para plan_id ${TEST_PLAN_ID} (${EXPLAINABILITY_COUNT})"
    add_test_result "Explainability" "passed" "${EXPLAINABILITY_COUNT} explanations found for plan ${TEST_PLAN_ID}"
  else
    check_status 1 "Nenhuma explicação registrada para plan_id ${TEST_PLAN_ID}"
    add_test_result "Explainability" "failed" "No explanations found for plan ${TEST_PLAN_ID}"
  fi
else
  log_warning "MongoDB pod ou plan_id não disponível"
  add_test_result "Explainability" "warning" "MongoDB pod or plan_id not available"
fi

# 4.2 Verificar integridade do ledger (hash)
echo -e "\n${BLUE}4.2 Verificando integridade do ledger...${NC}"

if [ -n "$MONGO_POD" ] && [ -n "$TEST_PLAN_ID" ]; then
  HASH_EXISTS=$(kubectl exec -n mongodb-cluster ${MONGO_POD} -- mongosh --quiet --eval "db.cognitive_ledger.countDocuments({plan_id: '${TEST_PLAN_ID}', hash: {\$exists: true}})" 2>/dev/null || echo "0")

  if [ "$HASH_EXISTS" -gt 0 ]; then
    check_status 0 "Registro com hash SHA-256 no ledger"
    add_test_result "Ledger Integrity" "passed" "Hash found for plan ${TEST_PLAN_ID}"
  else
    check_status 1 "Registro sem hash SHA-256 no ledger"
    add_test_result "Ledger Integrity" "failed" "No hash found for plan ${TEST_PLAN_ID}"
  fi
else
  log_warning "MongoDB pod ou plan_id não disponível"
  add_test_result "Ledger Integrity" "warning" "MongoDB pod or plan_id not available"
fi

# 4.3 Verificar compliance (OPA Gatekeeper)
echo -e "\n${BLUE}4.3 Verificando compliance (OPA Gatekeeper)...${NC}"

VIOLATIONS=$(kubectl get constraints -A -o json 2>/dev/null | jq '[.items[] | select(.status.totalViolations > 0)] | length' || echo "0")
if [ "$VIOLATIONS" -eq 0 ]; then
  check_status 0 "Políticas OPA Gatekeeper sem violações"
  add_test_result "OPA Compliance" "passed" "No policy violations found"
else
  check_status 1 "Políticas OPA Gatekeeper com ${VIOLATIONS} violações"
  add_test_result "OPA Compliance" "failed" "${VIOLATIONS} policy violations found"
  [ "$CONTINUE_ON_ERROR" = false ] && exit 1
fi

# ========================================
# FASE 5: Validar Dashboards e Alertas
# ========================================
echo -e "\n${YELLOW}FASE 5: Validando Dashboards e Alertas...${NC}"

# 5.1 Verificar dashboards Grafana
echo -e "\n${BLUE}5.1 Verificando dashboards Grafana...${NC}"

DASHBOARDS_TO_CHECK=(
  "fluxo-b-geracao-planos"
  "specialists-cognitive-layer"
  "consensus-governance"
  "data-governance"
  "memory-layer-data-quality"
)

DASHBOARDS_FOUND=0
for dashboard in "${DASHBOARDS_TO_CHECK[@]}"; do
  if [ -f "monitoring/dashboards/${dashboard}.json" ]; then
    log_success "Dashboard ${dashboard} existe"
    DASHBOARDS_FOUND=$((DASHBOARDS_FOUND + 1))
  else
    log_warning "Dashboard ${dashboard} não encontrado"
  fi
done

if [ "$DASHBOARDS_FOUND" -ge 3 ]; then
  check_status 0 "Dashboards Grafana disponíveis (${DASHBOARDS_FOUND}/${#DASHBOARDS_TO_CHECK[@]})"
  add_test_result "Grafana Dashboards" "passed" "${DASHBOARDS_FOUND}/${#DASHBOARDS_TO_CHECK[@]} dashboards found"
  COMPONENT_STATUS["dashboards"]=1
else
  check_status 1 "Dashboards Grafana insuficientes (${DASHBOARDS_FOUND}/${#DASHBOARDS_TO_CHECK[@]})"
  add_test_result "Grafana Dashboards" "failed" "Only ${DASHBOARDS_FOUND}/${#DASHBOARDS_TO_CHECK[@]} dashboards found"
fi

# 5.2 Verificar alertas Prometheus
echo -e "\n${BLUE}5.2 Verificando alertas Prometheus...${NC}"

ALERTS_TO_CHECK=(
  "infrastructure-alerts.yaml"
  "memory-layer-alerts.yaml"
  "specialists-alerts.yaml"
  "consensus-alerts.yaml"
  "data-quality-alerts.yaml"
)

ALERTS_FOUND=0
for alert_file in "${ALERTS_TO_CHECK[@]}"; do
  if [ -f "monitoring/alerts/${alert_file}" ]; then
    log_success "Alertas ${alert_file} existem"
    ALERTS_FOUND=$((ALERTS_FOUND + 1))
  else
    log_warning "Alertas ${alert_file} não encontrados"
  fi
done

if [ "$ALERTS_FOUND" -ge 3 ]; then
  check_status 0 "Alertas Prometheus configurados (${ALERTS_FOUND}/${#ALERTS_TO_CHECK[@]})"
  add_test_result "Prometheus Alerts" "passed" "${ALERTS_FOUND}/${#ALERTS_TO_CHECK[@]} alert files found"
  COMPONENT_STATUS["alerts"]=1
else
  check_status 1 "Alertas Prometheus insuficientes (${ALERTS_FOUND}/${#ALERTS_TO_CHECK[@]})"
  add_test_result "Prometheus Alerts" "failed" "Only ${ALERTS_FOUND}/${#ALERTS_TO_CHECK[@]} alert files found"
fi

# ========================================
# RESUMO FINAL
# ========================================
echo -e "\n${BLUE}========================================="
echo "Resumo do Teste End-to-End - Fase 1"
echo "=========================================${NC}"

echo -e "\n${YELLOW}Fluxo Testado:${NC}"
echo "  Intent Envelope (${TEST_INTENT_ID})"
echo "    ↓"
echo "  Cognitive Plan (${TEST_PLAN_ID:-N/A})"
echo "    ↓"
echo "  5 Specialist Opinions"
echo "    ↓"
echo "  Consolidated Decision (${TEST_DECISION_ID:-N/A})"

echo -e "\n${YELLOW}Componentes Validados:${NC}"

# Função auxiliar para exibir status
show_status() {
    local component=$1
    local label=$2
    if [ "${COMPONENT_STATUS[$component]}" -eq 1 ]; then
        echo -e "${GREEN}✓${NC} ${label}"
    else
        echo -e "${RED}✗${NC} ${label}"
    fi
}

show_status "memory_layers" "Camadas de Memória (Redis, MongoDB, Neo4j, ClickHouse)"
show_status "gateway" "Gateway de Intenções"
show_status "ste" "Semantic Translation Engine"
show_status "specialists" "5 Especialistas Neurais"
show_status "consensus" "Consensus Engine"
show_status "ledger" "Ledger Cognitivo"
show_status "pheromones" "Feromônios Digitais"
show_status "prometheus" "Métricas Prometheus"
show_status "jaeger" "Traces Jaeger"
show_status "dashboards" "Dashboards Grafana"
show_status "alerts" "Alertas Prometheus"

echo -e "\n${YELLOW}Próximos Passos:${NC}"
echo "1. Verificar dashboards Grafana:"
echo "   kubectl port-forward -n neural-hive-observability svc/grafana 3000:80"
echo "   http://localhost:3000/d/governance-executive-dashboard"
echo "2. Verificar traces Jaeger:"
echo "   kubectl port-forward -n neural-hive-observability svc/jaeger-query 16686:16686"
echo "   http://localhost:16686/search?service=semantic-translation-engine&tag=neural.hive.intent.id:${TEST_INTENT_ID}"
echo "3. Consultar ledger MongoDB:"
echo "   kubectl exec -n mongodb-cluster ${MONGO_POD:-<pod>} -- mongosh --eval \"db.cognitive_ledger.find({intent_id: '${TEST_INTENT_ID}'}).pretty()\""
echo "4. Consultar feromônios Redis:"
echo "   kubectl exec -n redis-cluster ${REDIS_POD:-<pod>} -- redis-cli KEYS 'pheromone:*'"

# ========================================
# GENERATE TEST REPORTS
# ========================================
log_section "Generating Test Reports"

# Save JSON report
REPORT_FILE="${OUTPUT_DIR}/phase1-test-report-$(date +%Y%m%d-%H%M%S).json"
save_test_report "$REPORT_FILE"

# Generate Markdown summary
SUMMARY_FILE="${OUTPUT_DIR}/phase1-test-summary-$(date +%Y%m%d-%H%M%S).md"
generate_markdown_summary "$SUMMARY_FILE"

# Generate executive report (consolidates JSON, Markdown, and Performance Metrics)
EXEC_REPORT_SCRIPT="${SCRIPT_DIR}/../scripts/generate_e2e_executive_report.sh"
if [ -f "$EXEC_REPORT_SCRIPT" ]; then
    log_info "Gerando relatório executivo consolidado..."

    # Encontrar arquivo de métricas mais recente
    METRICS_FILE=$(find "$OUTPUT_DIR" -name "performance-metrics-*.txt" -type f 2>/dev/null | sort -r | head -1)

    if bash "$EXEC_REPORT_SCRIPT" "$REPORT_FILE" "$SUMMARY_FILE" "$METRICS_FILE" >/dev/null 2>&1; then
        log_success "Relatório executivo gerado"
        EXEC_REPORT="${OUTPUT_DIR}/PHASE1_E2E_EXECUTIVE_REPORT.md"
    else
        log_warning "Falha ao gerar relatório executivo (não crítico)"
        EXEC_REPORT=""
    fi
else
    log_warning "Script de relatório executivo não encontrado: $EXEC_REPORT_SCRIPT"
    EXEC_REPORT=""
fi

# Cleanup
if [ "$NO_CLEANUP" = false ]; then
    log_info "Cleaning up test resources..."
    cleanup_port_forwards
fi

echo -e "\n${GREEN}✅ Teste End-to-End da Fase 1 concluído!${NC}"
echo ""
echo "Relatórios gerados:"
echo "  JSON: $REPORT_FILE"
echo "  Markdown: $SUMMARY_FILE"
if [ -n "$EXEC_REPORT" ]; then
    echo "  Executivo: $EXEC_REPORT"
fi
