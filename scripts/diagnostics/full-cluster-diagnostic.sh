#!/bin/bash
###############################################################################
# Neural Hive-Mind - Diagnostico Completo do Cluster
# Execute este script no servidor com acesso ao kubectl
# Uso: bash full-cluster-diagnostic.sh [--output relatorio.txt]
###############################################################################
set -euo pipefail

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

OUTPUT_FILE="${1:-/tmp/neural-hive-diagnostic-$(date +%Y%m%d-%H%M%S).txt}"
if [[ "$1" == "--output" ]] && [[ -n "${2:-}" ]]; then
  OUTPUT_FILE="$2"
fi

log() { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$OUTPUT_FILE"; }
ok()  { echo -e "${GREEN}[OK]${NC} $1" | tee -a "$OUTPUT_FILE"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$OUTPUT_FILE"; }
fail(){ echo -e "${RED}[FAIL]${NC} $1" | tee -a "$OUTPUT_FILE"; }
section() { echo -e "\n${BLUE}========== $1 ==========${NC}" | tee -a "$OUTPUT_FILE"; }

exec_cmd() {
  local desc="$1"
  shift
  echo -e "\n--- $desc ---" >> "$OUTPUT_FILE"
  if output=$("$@" 2>&1); then
    echo "$output" >> "$OUTPUT_FILE"
    echo "$output"
  else
    echo "ERRO: $output" >> "$OUTPUT_FILE"
    echo "$output"
    return 1
  fi
}

echo "Neural Hive-Mind - Diagnostico Completo" | tee "$OUTPUT_FILE"
echo "Data: $(date)" | tee -a "$OUTPUT_FILE"
echo "Host: $(hostname)" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

###############################################################################
section "1. NODES E RECURSOS DO CLUSTER"
###############################################################################

log "1.1 - Nodes do cluster"
exec_cmd "kubectl get nodes" kubectl get nodes -o wide

log "1.2 - Recursos dos nodes"
exec_cmd "kubectl top nodes" kubectl top nodes 2>/dev/null || warn "metrics-server nao disponivel"

log "1.3 - Descricao dos nodes"
for node in $(kubectl get nodes -o name); do
  exec_cmd "Describe $node" kubectl describe "$node" | head -60
done

###############################################################################
section "2. NAMESPACES"
###############################################################################

log "2.1 - Namespaces"
exec_cmd "kubectl get namespaces" kubectl get namespaces

###############################################################################
section "3. PODS - TODOS OS NAMESPACES"
###############################################################################

log "3.1 - Todos os pods"
exec_cmd "kubectl get pods -A" kubectl get pods -A -o wide

log "3.2 - Pods NAO Running"
exec_cmd "Pods com problemas" kubectl get pods -A --field-selector 'status.phase!=Running,status.phase!=Succeeded' 2>/dev/null || ok "Todos os pods estao Running"

log "3.3 - Pods com restart > 0"
exec_cmd "Pods com restarts" kubectl get pods -A -o json | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'{'NAMESPACE':<30} {'POD':<50} {'CONTAINER':<30} {'RESTARTS':<10} {'STATE'}')
print('-' * 150)
for pod in data.get('items', []):
  ns = pod['metadata']['namespace']
  name = pod['metadata']['name']
  for cs in pod.get('status', {}).get('containerStatuses', []):
    restarts = cs.get('restartCount', 0)
    if restarts > 0:
      state = list(cs.get('state', {}).keys())[0] if cs.get('state') else 'unknown'
      print(f'{ns:<30} {name:<50} {cs[\"name\"]:<30} {restarts:<10} {state}')
" 2>/dev/null || warn "Falha ao processar JSON de pods"

###############################################################################
section "4. SERVICOS NEURAL HIVE-MIND"
###############################################################################

NEURAL_NS="default"
# Tenta detectar namespace principal
for ns in neural-hive neural-hive-mind default production; do
  if kubectl get namespace "$ns" &>/dev/null; then
    pod_count=$(kubectl get pods -n "$ns" --no-headers 2>/dev/null | wc -l)
    if [[ $pod_count -gt 5 ]]; then
      NEURAL_NS="$ns"
      break
    fi
  fi
done
log "Namespace principal detectado: $NEURAL_NS"

SERVICES=(
  "gateway-intencoes"
  "semantic-translation-engine"
  "consensus-engine"
  "specialist-architecture"
  "specialist-technical"
  "specialist-business"
  "specialist-behavior"
  "specialist-evolution"
  "orchestrator-dynamic"
  "worker-agents"
  "scout-agents"
  "guard-agents"
  "analyst-agents"
  "optimizer-agents"
  "queen-agent"
  "code-forge"
  "memory-layer-api"
  "service-registry"
  "execution-ticket-service"
  "approval-service"
  "explainability-api"
  "self-healing-engine"
  "sla-management-system"
  "mcp-tool-catalog"
)

log "4.1 - Status dos servicos Neural Hive-Mind"
echo "" >> "$OUTPUT_FILE"
printf "%-40s %-10s %-10s %-15s %-20s\n" "SERVICO" "READY" "RESTARTS" "STATUS" "AGE" | tee -a "$OUTPUT_FILE"
printf "%s\n" "$(printf '=%.0s' {1..100})" | tee -a "$OUTPUT_FILE"

for svc in "${SERVICES[@]}"; do
  pod_info=$(kubectl get pods -n "$NEURAL_NS" -l "app.kubernetes.io/name=$svc" -o json 2>/dev/null || \
             kubectl get pods -n "$NEURAL_NS" -l "app=$svc" -o json 2>/dev/null || \
             kubectl get pods -n "$NEURAL_NS" 2>/dev/null | grep "$svc" || echo "")

  if echo "$pod_info" | grep -q "$svc"; then
    pod_line=$(kubectl get pods -n "$NEURAL_NS" 2>/dev/null | grep "$svc" | head -1)
    if [[ -n "$pod_line" ]]; then
      name=$(echo "$pod_line" | awk '{print $1}')
      ready=$(echo "$pod_line" | awk '{print $2}')
      status=$(echo "$pod_line" | awk '{print $3}')
      restarts=$(echo "$pod_line" | awk '{print $4}')
      age=$(echo "$pod_line" | awk '{print $5}')

      if [[ "$status" == "Running" ]]; then
        printf "${GREEN}%-40s %-10s %-10s %-15s %-20s${NC}\n" "$svc" "$ready" "$restarts" "$status" "$age" | tee -a "$OUTPUT_FILE"
      else
        printf "${RED}%-40s %-10s %-10s %-15s %-20s${NC}\n" "$svc" "$ready" "$restarts" "$status" "$age" | tee -a "$OUTPUT_FILE"
      fi
    fi
  else
    printf "${RED}%-40s %-10s %-10s %-15s %-20s${NC}\n" "$svc" "-" "-" "NOT FOUND" "-" | tee -a "$OUTPUT_FILE"
  fi
done

###############################################################################
section "5. INFRAESTRUTURA (Kafka, Redis, MongoDB, etc)"
###############################################################################

INFRA_SERVICES=(
  "kafka"
  "zookeeper"
  "redis"
  "mongodb"
  "neo4j"
  "clickhouse"
  "temporal"
  "vault"
  "keycloak"
  "schema-registry"
)

log "5.1 - Status da infraestrutura"
for infra in "${INFRA_SERVICES[@]}"; do
  pods=$(kubectl get pods -A 2>/dev/null | grep -i "$infra" || echo "")
  if [[ -n "$pods" ]]; then
    ok "$infra encontrado:"
    echo "$pods" | tee -a "$OUTPUT_FILE"
  else
    warn "$infra NAO encontrado no cluster"
  fi
  echo "" >> "$OUTPUT_FILE"
done

###############################################################################
section "6. SERVICES E ENDPOINTS"
###############################################################################

log "6.1 - Services no namespace $NEURAL_NS"
exec_cmd "kubectl get svc" kubectl get svc -n "$NEURAL_NS" -o wide

log "6.2 - Endpoints no namespace $NEURAL_NS"
exec_cmd "kubectl get endpoints" kubectl get endpoints -n "$NEURAL_NS"

log "6.3 - Ingress"
exec_cmd "kubectl get ingress" kubectl get ingress -A 2>/dev/null || warn "Nenhum ingress encontrado"

###############################################################################
section "7. KAFKA TOPICS E CONECTIVIDADE"
###############################################################################

log "7.1 - Verificando Kafka"
KAFKA_POD=$(kubectl get pods -A -l app=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get pods -A -l strimzi.io/name -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get pods -A 2>/dev/null | grep -i kafka | grep -v zookeeper | head -1 | awk '{print $2}')
KAFKA_NS=$(kubectl get pods -A 2>/dev/null | grep "$KAFKA_POD" | head -1 | awk '{print $1}')

if [[ -n "$KAFKA_POD" ]] && [[ -n "$KAFKA_NS" ]]; then
  ok "Kafka pod encontrado: $KAFKA_POD (ns: $KAFKA_NS)"

  log "7.2 - Topics Kafka"
  kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
    kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | tee -a "$OUTPUT_FILE" || \
  kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
    /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | tee -a "$OUTPUT_FILE" || \
    warn "Nao foi possivel listar topics"

  log "7.3 - Consumer Groups"
  kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
    kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null | tee -a "$OUTPUT_FILE" || \
    warn "Nao foi possivel listar consumer groups"
else
  warn "Kafka pod nao encontrado"
fi

###############################################################################
section "8. MONGODB STATUS"
###############################################################################

MONGO_POD=$(kubectl get pods -A -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get pods -A 2>/dev/null | grep -i mongo | head -1 | awk '{print $2}')
MONGO_NS=$(kubectl get pods -A 2>/dev/null | grep "$MONGO_POD" | head -1 | awk '{print $1}')

if [[ -n "$MONGO_POD" ]] && [[ -n "$MONGO_NS" ]]; then
  ok "MongoDB pod encontrado: $MONGO_POD (ns: $MONGO_NS)"

  log "8.1 - MongoDB databases"
  kubectl exec -n "$MONGO_NS" "$MONGO_POD" -- \
    mongosh --quiet --eval "db.adminCommand('listDatabases').databases.forEach(d => print(d.name + ' - ' + d.sizeOnDisk + ' bytes'))" 2>/dev/null | tee -a "$OUTPUT_FILE" || \
    warn "Nao foi possivel listar databases"
else
  warn "MongoDB pod nao encontrado"
fi

###############################################################################
section "9. REDIS STATUS"
###############################################################################

REDIS_POD=$(kubectl get pods -A -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get pods -A 2>/dev/null | grep -i redis | head -1 | awk '{print $2}')
REDIS_NS=$(kubectl get pods -A 2>/dev/null | grep "$REDIS_POD" | head -1 | awk '{print $1}')

if [[ -n "$REDIS_POD" ]] && [[ -n "$REDIS_NS" ]]; then
  ok "Redis pod encontrado: $REDIS_POD (ns: $REDIS_NS)"

  log "9.1 - Redis info"
  kubectl exec -n "$REDIS_NS" "$REDIS_POD" -- redis-cli INFO server 2>/dev/null | head -20 | tee -a "$OUTPUT_FILE" || \
    warn "Nao foi possivel acessar Redis"

  log "9.2 - Redis key count"
  kubectl exec -n "$REDIS_NS" "$REDIS_POD" -- redis-cli DBSIZE 2>/dev/null | tee -a "$OUTPUT_FILE" || true
else
  warn "Redis pod nao encontrado"
fi

###############################################################################
section "10. HEALTH CHECKS DOS SERVICOS"
###############################################################################

log "10.1 - Testando health endpoints"
for svc in "${SERVICES[@]}"; do
  pod=$(kubectl get pods -n "$NEURAL_NS" 2>/dev/null | grep "$svc" | grep Running | head -1 | awk '{print $1}')
  if [[ -n "$pod" ]]; then
    # Tenta porta 8000 e 8080
    for port in 8000 8080; do
      health=$(kubectl exec -n "$NEURAL_NS" "$pod" -- curl -sf "http://localhost:$port/health" --max-time 5 2>/dev/null || echo "")
      if [[ -n "$health" ]]; then
        ok "$svc (:$port/health) - $health"
        break
      fi
    done
    if [[ -z "$health" ]]; then
      warn "$svc - health check falhou em ambas as portas"
    fi
  fi
done

###############################################################################
section "11. LOGS DE ERROS RECENTES"
###############################################################################

log "11.1 - Ultimos erros nos pods Neural Hive-Mind"
for svc in "${SERVICES[@]}"; do
  pod=$(kubectl get pods -n "$NEURAL_NS" 2>/dev/null | grep "$svc" | head -1 | awk '{print $1}')
  if [[ -n "$pod" ]]; then
    errors=$(kubectl logs -n "$NEURAL_NS" "$pod" --tail=100 2>/dev/null | grep -iE "(error|exception|traceback|critical|fatal)" | tail -5)
    if [[ -n "$errors" ]]; then
      warn "Erros em $svc:"
      echo "$errors" | tee -a "$OUTPUT_FILE"
    fi
  fi
done

###############################################################################
section "12. PERSISTENT VOLUMES"
###############################################################################

log "12.1 - PVCs"
exec_cmd "kubectl get pvc -A" kubectl get pvc -A

log "12.2 - PVs"
exec_cmd "kubectl get pv" kubectl get pv 2>/dev/null || warn "Nenhum PV encontrado"

###############################################################################
section "13. CONFIGMAPS E SECRETS"
###############################################################################

log "13.1 - ConfigMaps no namespace $NEURAL_NS"
exec_cmd "kubectl get configmaps" kubectl get configmaps -n "$NEURAL_NS"

log "13.2 - Secrets no namespace $NEURAL_NS (nomes apenas)"
exec_cmd "kubectl get secrets" kubectl get secrets -n "$NEURAL_NS" -o name

###############################################################################
section "14. HELM RELEASES"
###############################################################################

log "14.1 - Helm releases"
exec_cmd "helm list -A" helm list -A 2>/dev/null || warn "Helm nao disponivel"

###############################################################################
section "15. RESOURCE QUOTAS E LIMITS"
###############################################################################

log "15.1 - Resource Quotas"
exec_cmd "kubectl get resourcequotas" kubectl get resourcequotas -A 2>/dev/null || ok "Nenhum resource quota"

log "15.2 - Limit Ranges"
exec_cmd "kubectl get limitranges" kubectl get limitranges -A 2>/dev/null || ok "Nenhum limit range"

###############################################################################
section "16. NETWORK POLICIES"
###############################################################################

log "16.1 - Network Policies"
exec_cmd "kubectl get networkpolicies" kubectl get networkpolicies -A 2>/dev/null || ok "Nenhuma network policy"

###############################################################################
section "17. EVENTOS RECENTES"
###############################################################################

log "17.1 - Eventos Warning recentes"
exec_cmd "kubectl get events (Warning)" kubectl get events -A --field-selector type=Warning --sort-by='.metadata.creationTimestamp' 2>/dev/null | tail -30

###############################################################################
section "18. RESUMO"
###############################################################################

total_pods=$(kubectl get pods -A --no-headers 2>/dev/null | wc -l)
running_pods=$(kubectl get pods -A --no-headers --field-selector status.phase=Running 2>/dev/null | wc -l)
failed_pods=$(kubectl get pods -A --no-headers --field-selector 'status.phase=Failed' 2>/dev/null | wc -l)
pending_pods=$(kubectl get pods -A --no-headers --field-selector 'status.phase=Pending' 2>/dev/null | wc -l)

echo "" | tee -a "$OUTPUT_FILE"
echo "============================================" | tee -a "$OUTPUT_FILE"
echo "        RESUMO DO DIAGNOSTICO" | tee -a "$OUTPUT_FILE"
echo "============================================" | tee -a "$OUTPUT_FILE"
echo "Total de Pods:    $total_pods" | tee -a "$OUTPUT_FILE"
echo "Running:          $running_pods" | tee -a "$OUTPUT_FILE"
echo "Pending:          $pending_pods" | tee -a "$OUTPUT_FILE"
echo "Failed:           $failed_pods" | tee -a "$OUTPUT_FILE"
echo "Namespace Neural: $NEURAL_NS" | tee -a "$OUTPUT_FILE"
echo "============================================" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"
echo "Relatorio salvo em: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "Para compartilhar: cat $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
