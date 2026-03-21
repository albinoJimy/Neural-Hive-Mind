#!/bin/bash
###############################################################################
# Neural Hive-Mind - Teste E2E dos Fluxos (A, B, C)
# Execute este script no servidor com acesso ao kubectl
# Uso: bash e2e-flow-test.sh [namespace]
###############################################################################
set -euo pipefail

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

NS="${1:-default}"
OUTPUT="/tmp/neural-hive-e2e-$(date +%Y%m%d-%H%M%S).txt"
INTENT_ID="test-e2e-$(date +%s)"
CORRELATION_ID="corr-$INTENT_ID"

log()  { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$OUTPUT"; }
ok()   { echo -e "${GREEN}[PASS]${NC} $1" | tee -a "$OUTPUT"; }
fail() { echo -e "${RED}[FAIL]${NC} $1" | tee -a "$OUTPUT"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$OUTPUT"; }
section() { echo -e "\n${CYAN}======== $1 ========${NC}" | tee -a "$OUTPUT"; }

# Funcao para executar dentro de um pod
exec_in_pod() {
  local svc="$1"
  shift
  local pod=$(kubectl get pods -n "$NS" 2>/dev/null | grep "$svc" | grep Running | head -1 | awk '{print $1}')
  if [[ -n "$pod" ]]; then
    kubectl exec -n "$NS" "$pod" -- "$@" 2>/dev/null
  else
    echo "POD_NOT_FOUND"
    return 1
  fi
}

echo "Neural Hive-Mind - Teste E2E" | tee "$OUTPUT"
echo "Data: $(date)" | tee -a "$OUTPUT"
echo "Namespace: $NS" | tee -a "$OUTPUT"
echo "Intent ID: $INTENT_ID" | tee -a "$OUTPUT"
echo "" | tee -a "$OUTPUT"

###############################################################################
section "PRE-VALIDACAO: Servicos Criticos"
###############################################################################

CRITICAL_SERVICES=(
  "gateway-intencoes"
  "semantic-translation-engine"
  "consensus-engine"
  "orchestrator-dynamic"
  "specialist-architecture"
  "specialist-technical"
  "specialist-business"
  "specialist-behavior"
  "specialist-evolution"
)

all_running=true
for svc in "${CRITICAL_SERVICES[@]}"; do
  pod=$(kubectl get pods -n "$NS" 2>/dev/null | grep "$svc" | grep Running | head -1 | awk '{print $1}')
  if [[ -n "$pod" ]]; then
    ok "$svc -> Running ($pod)"
  else
    fail "$svc -> NAO encontrado ou NAO Running"
    all_running=false
  fi
done

if [[ "$all_running" != "true" ]]; then
  warn "Nem todos os servicos criticos estao rodando. O teste E2E pode falhar."
  echo "Continuar mesmo assim? (s/N)"
  read -r resp
  if [[ "$resp" != "s" ]] && [[ "$resp" != "S" ]]; then
    echo "Abortado pelo usuario"
    exit 1
  fi
fi

###############################################################################
section "PRE-VALIDACAO: Infraestrutura"
###############################################################################

# Kafka
KAFKA_POD=$(kubectl get pods -A 2>/dev/null | grep -i kafka | grep -v zookeeper | grep Running | head -1 | awk '{print $2}')
KAFKA_NS=$(kubectl get pods -A 2>/dev/null | grep "$KAFKA_POD" | head -1 | awk '{print $1}')

if [[ -n "$KAFKA_POD" ]]; then
  ok "Kafka: $KAFKA_POD (ns: $KAFKA_NS)"
else
  fail "Kafka nao encontrado"
fi

# Redis
REDIS_POD=$(kubectl get pods -A 2>/dev/null | grep -i redis | grep Running | head -1 | awk '{print $2}')
REDIS_NS=$(kubectl get pods -A 2>/dev/null | grep "$REDIS_POD" | head -1 | awk '{print $1}')
if [[ -n "$REDIS_POD" ]]; then
  ok "Redis: $REDIS_POD (ns: $REDIS_NS)"
else
  fail "Redis nao encontrado"
fi

# MongoDB
MONGO_POD=$(kubectl get pods -A 2>/dev/null | grep -i mongo | grep Running | head -1 | awk '{print $2}')
MONGO_NS=$(kubectl get pods -A 2>/dev/null | grep "$MONGO_POD" | head -1 | awk '{print $1}')
if [[ -n "$MONGO_POD" ]]; then
  ok "MongoDB: $MONGO_POD (ns: $MONGO_NS)"
else
  fail "MongoDB nao encontrado"
fi

###############################################################################
section "FLUXO A: Gateway de Intencoes -> Kafka"
###############################################################################

log "A.1 - Health check do Gateway"
GW_POD=$(kubectl get pods -n "$NS" 2>/dev/null | grep gateway-intencoes | grep Running | head -1 | awk '{print $1}')
if [[ -n "$GW_POD" ]]; then
  GW_HEALTH=$(exec_in_pod "gateway-intencoes" curl -sf http://localhost:8000/health --max-time 10 || echo "FAIL")
  if [[ "$GW_HEALTH" != "FAIL" ]] && [[ "$GW_HEALTH" != "POD_NOT_FOUND" ]]; then
    ok "Gateway health: $GW_HEALTH"
  else
    fail "Gateway health check falhou"
  fi

  log "A.2 - Enviando intencao de teste via Gateway"
  INTENT_PAYLOAD='{
    "text": "Criar um microservico de autenticacao com OAuth2 e JWT",
    "source": "e2e-test",
    "language": "pt",
    "metadata": {
      "correlation_id": "'"$CORRELATION_ID"'",
      "intent_id": "'"$INTENT_ID"'",
      "test_run": true
    }
  }'

  RESPONSE=$(exec_in_pod "gateway-intencoes" curl -sf \
    -X POST http://localhost:8000/api/v1/intents \
    -H "Content-Type: application/json" \
    -d "$INTENT_PAYLOAD" \
    --max-time 30 || echo "FAIL")

  if [[ "$RESPONSE" != "FAIL" ]] && [[ "$RESPONSE" != "POD_NOT_FOUND" ]]; then
    ok "Intencao enviada com sucesso"
    echo "Resposta: $RESPONSE" | tee -a "$OUTPUT"

    # Extrair intent_id da resposta se disponivel
    RETURNED_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('intent_id', d.get('id', '')))" 2>/dev/null || echo "")
    if [[ -n "$RETURNED_ID" ]]; then
      INTENT_ID="$RETURNED_ID"
      log "Intent ID retornado: $INTENT_ID"
    fi
  else
    fail "Falha ao enviar intencao"
    warn "Tentando endpoint alternativo /api/v1/intent/process"

    RESPONSE=$(exec_in_pod "gateway-intencoes" curl -sf \
      -X POST http://localhost:8000/api/v1/intent/process \
      -H "Content-Type: application/json" \
      -d "$INTENT_PAYLOAD" \
      --max-time 30 || echo "FAIL")

    if [[ "$RESPONSE" != "FAIL" ]]; then
      ok "Intencao enviada via endpoint alternativo"
      echo "Resposta: $RESPONSE" | tee -a "$OUTPUT"
    else
      fail "Ambos os endpoints falharam"
    fi
  fi

  log "A.3 - Verificando mensagem no Kafka"
  sleep 5
  if [[ -n "$KAFKA_POD" ]]; then
    # Tentar verificar se a mensagem chegou ao topico
    for topic in "intentions.business" "intentions.technical" "intents"; do
      MSGS=$(kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
        kafka-console-consumer.sh --bootstrap-server localhost:9092 \
        --topic "$topic" --from-beginning --timeout-ms 10000 --max-messages 5 2>/dev/null | \
        grep -c "$INTENT_ID" || echo "0")

      if [[ "$MSGS" -gt 0 ]]; then
        ok "Mensagem encontrada no topic $topic"
        break
      fi
    done
  fi
else
  fail "Gateway pod nao encontrado, pulando Fluxo A"
fi

###############################################################################
section "FLUXO B: STE -> Plano Cognitivo"
###############################################################################

log "B.1 - Health check do STE"
STE_HEALTH=$(exec_in_pod "semantic-translation-engine" curl -sf http://localhost:8000/health --max-time 10 || echo "FAIL")
if [[ "$STE_HEALTH" != "FAIL" ]] && [[ "$STE_HEALTH" != "POD_NOT_FOUND" ]]; then
  ok "STE health: $STE_HEALTH"
else
  fail "STE health check falhou"
fi

log "B.2 - Aguardando processamento do STE (30s)"
sleep 30

log "B.3 - Verificando plano cognitivo no Kafka"
if [[ -n "$KAFKA_POD" ]]; then
  for topic in "cognitive-plans" "plans.ready"; do
    PLAN_MSGS=$(kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
      kafka-console-consumer.sh --bootstrap-server localhost:9092 \
      --topic "$topic" --from-beginning --timeout-ms 10000 --max-messages 3 2>/dev/null || echo "")

    if [[ -n "$PLAN_MSGS" ]]; then
      ok "Mensagens encontradas no topic $topic"
      echo "$PLAN_MSGS" | head -5 | tee -a "$OUTPUT"
      break
    fi
  done
fi

log "B.4 - Verificando plano no MongoDB"
if [[ -n "$MONGO_POD" ]]; then
  PLAN_COUNT=$(kubectl exec -n "$MONGO_NS" "$MONGO_POD" -- \
    mongosh --quiet --eval "db.getSiblingDB('neural_hive').cognitive_plans.countDocuments()" 2>/dev/null || echo "ERRO")
  log "Total de planos cognitivos no MongoDB: $PLAN_COUNT"
fi

###############################################################################
section "FLUXO B.2: Consensus Engine -> Specialists"
###############################################################################

log "B2.1 - Health check do Consensus Engine"
CE_HEALTH=$(exec_in_pod "consensus-engine" curl -sf http://localhost:8000/health --max-time 10 || echo "FAIL")
if [[ "$CE_HEALTH" != "FAIL" ]] && [[ "$CE_HEALTH" != "POD_NOT_FOUND" ]]; then
  ok "Consensus Engine health: $CE_HEALTH"
else
  fail "Consensus Engine health check falhou"
fi

log "B2.2 - Verificando conectividade gRPC com Specialists"
SPECIALISTS=("specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")

for spec in "${SPECIALISTS[@]}"; do
  spec_pod=$(kubectl get pods -n "$NS" 2>/dev/null | grep "$spec" | grep Running | head -1 | awk '{print $1}')
  if [[ -n "$spec_pod" ]]; then
    # Testar health HTTP
    spec_health=$(kubectl exec -n "$NS" "$spec_pod" -- curl -sf http://localhost:8000/health --max-time 5 2>/dev/null || echo "FAIL")
    if [[ "$spec_health" != "FAIL" ]]; then
      ok "$spec: HTTP health OK"
    else
      # Tentar porta 8080
      spec_health=$(kubectl exec -n "$NS" "$spec_pod" -- curl -sf http://localhost:8080/health --max-time 5 2>/dev/null || echo "FAIL")
      if [[ "$spec_health" != "FAIL" ]]; then
        ok "$spec: HTTP health OK (porta 8080)"
      else
        warn "$spec: HTTP health NAO respondeu"
      fi
    fi

    # Verificar se gRPC esta listening na porta 50051
    grpc_check=$(kubectl exec -n "$NS" "$spec_pod" -- sh -c "ss -tlnp | grep 50051 || netstat -tlnp | grep 50051" 2>/dev/null || echo "")
    if echo "$grpc_check" | grep -q "50051"; then
      ok "$spec: gRPC porta 50051 listening"
    else
      warn "$spec: gRPC porta 50051 NAO detectado (pode estar em outra porta)"
    fi
  else
    fail "$spec: Pod NAO encontrado"
  fi
done

log "B2.3 - Verificando decisoes de consenso no Kafka"
if [[ -n "$KAFKA_POD" ]]; then
  CONSENSUS_MSGS=$(kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
    kafka-console-consumer.sh --bootstrap-server localhost:9092 \
    --topic "plans.consensus" --from-beginning --timeout-ms 10000 --max-messages 3 2>/dev/null || echo "")
  if [[ -n "$CONSENSUS_MSGS" ]]; then
    ok "Decisoes de consenso encontradas no Kafka"
    echo "$CONSENSUS_MSGS" | head -3 | tee -a "$OUTPUT"
  else
    warn "Nenhuma decisao de consenso encontrada (pode nao ter processado ainda)"
  fi
fi

log "B2.4 - Verificando consenso no MongoDB"
if [[ -n "$MONGO_POD" ]]; then
  DECISION_COUNT=$(kubectl exec -n "$MONGO_NS" "$MONGO_POD" -- \
    mongosh --quiet --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments()" 2>/dev/null || echo "ERRO")
  log "Total de decisoes de consenso no MongoDB: $DECISION_COUNT"
fi

###############################################################################
section "FLUXO C: Orchestrator -> Temporal -> Workers"
###############################################################################

log "C.1 - Health check do Orchestrator"
ORCH_HEALTH=$(exec_in_pod "orchestrator-dynamic" curl -sf http://localhost:8000/health --max-time 10 || echo "FAIL")
if [[ "$ORCH_HEALTH" != "FAIL" ]] && [[ "$ORCH_HEALTH" != "POD_NOT_FOUND" ]]; then
  ok "Orchestrator health: $ORCH_HEALTH"
  echo "Detalhes: $ORCH_HEALTH" | tee -a "$OUTPUT"
else
  fail "Orchestrator health check falhou"
fi

log "C.2 - Verificando Temporal"
TEMPORAL_POD=$(kubectl get pods -A 2>/dev/null | grep temporal | grep -i frontend | grep Running | head -1 | awk '{print $2}')
TEMPORAL_NS=$(kubectl get pods -A 2>/dev/null | grep "$TEMPORAL_POD" | head -1 | awk '{print $1}')
if [[ -n "$TEMPORAL_POD" ]]; then
  ok "Temporal frontend: $TEMPORAL_POD (ns: $TEMPORAL_NS)"

  # Verificar workflows
  WORKFLOWS=$(kubectl exec -n "$TEMPORAL_NS" "$TEMPORAL_POD" -- \
    tctl --ns neural-hive workflow list --status open 2>/dev/null | head -10 || echo "")
  if [[ -n "$WORKFLOWS" ]]; then
    log "Workflows abertos:"
    echo "$WORKFLOWS" | tee -a "$OUTPUT"
  else
    log "Nenhum workflow aberto no Temporal (ou tctl nao disponivel)"
  fi
else
  warn "Temporal frontend nao encontrado"
fi

log "C.3 - Verificando execution tickets"
ET_HEALTH=$(exec_in_pod "execution-ticket-service" curl -sf http://localhost:8000/health --max-time 10 || echo "FAIL")
if [[ "$ET_HEALTH" != "FAIL" ]] && [[ "$ET_HEALTH" != "POD_NOT_FOUND" ]]; then
  ok "Execution Ticket Service health: $ET_HEALTH"
else
  warn "Execution Ticket Service health check falhou"
fi

log "C.4 - Verificando Worker Agents"
WA_HEALTH=$(exec_in_pod "worker-agents" curl -sf http://localhost:8080/health --max-time 10 || echo "FAIL")
if [[ "$WA_HEALTH" != "FAIL" ]] && [[ "$WA_HEALTH" != "POD_NOT_FOUND" ]]; then
  ok "Worker Agents health: $WA_HEALTH"
else
  warn "Worker Agents health check falhou"
fi

log "C.5 - Verificando Code Forge"
CF_HEALTH=$(exec_in_pod "code-forge" curl -sf http://localhost:8080/health --max-time 10 || echo "FAIL")
if [[ "$CF_HEALTH" != "FAIL" ]] && [[ "$CF_HEALTH" != "POD_NOT_FOUND" ]]; then
  ok "Code Forge health: $CF_HEALTH"
else
  warn "Code Forge health check falhou"
fi

###############################################################################
section "VERIFICACAO FINAL: MongoDB (Resultados Consolidados)"
###############################################################################

if [[ -n "$MONGO_POD" ]]; then
  log "E.1 - Collections e documentos"
  kubectl exec -n "$MONGO_NS" "$MONGO_POD" -- \
    mongosh --quiet --eval "
      const dbs = ['neural_hive', 'neural_hive_orchestration', 'code_forge', 'memory', 'mcp_tool_catalog'];
      dbs.forEach(dbName => {
        const db = db.getSiblingDB(dbName);
        const colls = db.getCollectionNames();
        if (colls.length > 0) {
          print('\\nDatabase: ' + dbName);
          colls.forEach(c => {
            const count = db.getCollection(c).countDocuments();
            print('  ' + c + ': ' + count + ' docs');
          });
        }
      });
    " 2>/dev/null | tee -a "$OUTPUT" || warn "Falha ao consultar MongoDB"
fi

###############################################################################
section "METRICAS E OBSERVABILIDADE"
###############################################################################

log "F.1 - Verificando OTEL Collector"
OTEL_POD=$(kubectl get pods -A 2>/dev/null | grep otel | grep Running | head -1 | awk '{print $2}')
OTEL_NS=$(kubectl get pods -A 2>/dev/null | grep "$OTEL_POD" | head -1 | awk '{print $1}')
if [[ -n "$OTEL_POD" ]]; then
  ok "OTEL Collector: $OTEL_POD (ns: $OTEL_NS)"
else
  warn "OTEL Collector nao encontrado"
fi

log "F.2 - Verificando Prometheus"
PROM_POD=$(kubectl get pods -A 2>/dev/null | grep prometheus | grep -v pushgateway | grep Running | head -1 | awk '{print $2}')
if [[ -n "$PROM_POD" ]]; then
  ok "Prometheus: $PROM_POD"
else
  warn "Prometheus nao encontrado"
fi

log "F.3 - Metricas dos servicos"
for svc in "${CRITICAL_SERVICES[@]}"; do
  pod=$(kubectl get pods -n "$NS" 2>/dev/null | grep "$svc" | grep Running | head -1 | awk '{print $1}')
  if [[ -n "$pod" ]]; then
    for port in 9090 8080; do
      metrics=$(kubectl exec -n "$NS" "$pod" -- curl -sf "http://localhost:$port/metrics" --max-time 5 2>/dev/null | head -5)
      if [[ -n "$metrics" ]]; then
        ok "$svc: Metricas Prometheus disponiveis na porta $port"
        break
      fi
    done
  fi
done

###############################################################################
section "RESUMO DO TESTE E2E"
###############################################################################

echo "" | tee -a "$OUTPUT"
echo "============================================" | tee -a "$OUTPUT"
echo "        RESUMO DO TESTE E2E" | tee -a "$OUTPUT"
echo "============================================" | tee -a "$OUTPUT"
echo "" | tee -a "$OUTPUT"

PASS_COUNT=$(grep -c "\[PASS\]" "$OUTPUT" || echo "0")
FAIL_COUNT=$(grep -c "\[FAIL\]" "$OUTPUT" || echo "0")
WARN_COUNT=$(grep -c "\[WARN\]" "$OUTPUT" || echo "0")

echo -e "${GREEN}PASS: $PASS_COUNT${NC}" | tee -a "$OUTPUT"
echo -e "${RED}FAIL: $FAIL_COUNT${NC}" | tee -a "$OUTPUT"
echo -e "${YELLOW}WARN: $WARN_COUNT${NC}" | tee -a "$OUTPUT"
echo "" | tee -a "$OUTPUT"

if [[ $FAIL_COUNT -eq 0 ]]; then
  echo -e "${GREEN}RESULTADO: TODOS OS TESTES PASSARAM${NC}" | tee -a "$OUTPUT"
elif [[ $FAIL_COUNT -lt 3 ]]; then
  echo -e "${YELLOW}RESULTADO: PARCIALMENTE OK (verificar falhas)${NC}" | tee -a "$OUTPUT"
else
  echo -e "${RED}RESULTADO: MULTIPLAS FALHAS DETECTADAS${NC}" | tee -a "$OUTPUT"
fi

echo "" | tee -a "$OUTPUT"
echo "Relatorio completo: $OUTPUT" | tee -a "$OUTPUT"
echo "Para compartilhar: cat $OUTPUT" | tee -a "$OUTPUT"
