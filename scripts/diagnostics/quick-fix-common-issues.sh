#!/bin/bash
###############################################################################
# Neural Hive-Mind - Quick Fix para Problemas Comuns
# Execute no servidor com acesso ao kubectl
# Uso: bash quick-fix-common-issues.sh [fix-name]
#
# Fixes disponiveis:
#   restart-crashloop   - Restart pods em CrashLoopBackOff
#   fix-imagepull       - Corrigir ImagePullBackOff
#   fix-pending         - Diagnosticar pods Pending
#   fix-kafka-lag       - Resetar consumer groups com lag
#   fix-mongo-conn      - Testar conectividade MongoDB
#   fix-redis-conn      - Testar conectividade Redis
#   fix-grpc-timeout    - Ajustar timeouts gRPC dos specialists
#   restart-all         - Restart rolling de todos os servicos
#   check-resources     - Verificar uso de recursos vs limits
#   all                 - Executar todos os diagnosticos
###############################################################################
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

FIX="${1:-all}"

# Detectar namespace
NS="default"
for ns in neural-hive neural-hive-mind default production; do
  if kubectl get namespace "$ns" &>/dev/null; then
    count=$(kubectl get pods -n "$ns" --no-headers 2>/dev/null | wc -l)
    if [[ $count -gt 5 ]]; then
      NS="$ns"
      break
    fi
  fi
done
log "Namespace: $NS"

fix_crashloop() {
  log "=== FIX: Restart pods em CrashLoopBackOff ==="
  crashloop_pods=$(kubectl get pods -n "$NS" --no-headers 2>/dev/null | grep CrashLoopBackOff | awk '{print $1}')
  if [[ -z "$crashloop_pods" ]]; then
    ok "Nenhum pod em CrashLoopBackOff"
    return
  fi

  for pod in $crashloop_pods; do
    warn "Pod em CrashLoopBackOff: $pod"
    log "Ultimos logs:"
    kubectl logs -n "$NS" "$pod" --tail=20 2>/dev/null || true
    echo ""

    log "Deletando pod para restart..."
    kubectl delete pod -n "$NS" "$pod" --grace-period=30 2>/dev/null
    ok "Pod $pod deletado (sera recriado pelo deployment)"
  done
}

fix_imagepull() {
  log "=== FIX: ImagePullBackOff ==="
  imagepull_pods=$(kubectl get pods -n "$NS" --no-headers 2>/dev/null | grep -E "ImagePullBackOff|ErrImagePull" | awk '{print $1}')
  if [[ -z "$imagepull_pods" ]]; then
    ok "Nenhum pod com ImagePullBackOff"
    return
  fi

  for pod in $imagepull_pods; do
    warn "Pod com ImagePull error: $pod"
    image=$(kubectl get pod -n "$NS" "$pod" -o jsonpath='{.spec.containers[0].image}' 2>/dev/null)
    log "Imagem: $image"

    # Verificar se o secret de pull existe
    pull_secret=$(kubectl get pod -n "$NS" "$pod" -o jsonpath='{.spec.imagePullSecrets[0].name}' 2>/dev/null || echo "")
    if [[ -n "$pull_secret" ]]; then
      if kubectl get secret -n "$NS" "$pull_secret" &>/dev/null; then
        ok "Pull secret '$pull_secret' existe"
      else
        fail "Pull secret '$pull_secret' NAO existe!"
        log "Crie com: kubectl create secret docker-registry $pull_secret --docker-server=ghcr.io --docker-username=<user> --docker-password=<token> -n $NS"
      fi
    else
      warn "Nenhum imagePullSecret configurado"
    fi
  done
}

fix_pending() {
  log "=== FIX: Pods Pending ==="
  pending_pods=$(kubectl get pods -n "$NS" --no-headers --field-selector status.phase=Pending 2>/dev/null | awk '{print $1}')
  if [[ -z "$pending_pods" ]]; then
    ok "Nenhum pod Pending"
    return
  fi

  for pod in $pending_pods; do
    warn "Pod Pending: $pod"
    events=$(kubectl describe pod -n "$NS" "$pod" 2>/dev/null | grep -A5 "Events:" | tail -5)
    echo "$events"

    # Verificar se e problema de recursos
    if echo "$events" | grep -qi "insufficient"; then
      fail "Recursos insuficientes no cluster"
      log "Verificar: kubectl top nodes"
    fi

    # Verificar se e problema de PVC
    if echo "$events" | grep -qi "pvc\|volume\|storage"; then
      fail "Problema com volume/PVC"
      log "Verificar: kubectl get pvc -n $NS"
    fi
  done
}

fix_kafka_lag() {
  log "=== FIX: Kafka Consumer Group Lag ==="
  KAFKA_POD=$(kubectl get pods -A 2>/dev/null | grep -i kafka | grep -v zookeeper | grep Running | head -1 | awk '{print $2}')
  KAFKA_NS=$(kubectl get pods -A 2>/dev/null | grep "$KAFKA_POD" | head -1 | awk '{print $1}')

  if [[ -z "$KAFKA_POD" ]]; then
    warn "Kafka nao encontrado"
    return
  fi

  log "Consumer groups com lag:"
  kubectl exec -n "$KAFKA_NS" "$KAFKA_POD" -- \
    kafka-consumer-groups.sh --bootstrap-server localhost:9092 --all-groups --describe 2>/dev/null | \
    grep -v "^$" | grep -v "TOPIC" | awk '$6 > 100 {print "  Group:", $1, "Topic:", $2, "Partition:", $3, "Lag:", $6}' || \
    warn "Nao foi possivel verificar lag"
}

fix_mongo_conn() {
  log "=== FIX: Conectividade MongoDB ==="
  MONGO_POD=$(kubectl get pods -A 2>/dev/null | grep -i mongo | grep Running | head -1 | awk '{print $2}')
  MONGO_NS=$(kubectl get pods -A 2>/dev/null | grep "$MONGO_POD" | head -1 | awk '{print $1}')

  if [[ -z "$MONGO_POD" ]]; then
    warn "MongoDB nao encontrado"
    return
  fi

  # Testar conexao do orchestrator ao MongoDB
  ORCH_POD=$(kubectl get pods -n "$NS" 2>/dev/null | grep orchestrator | grep Running | head -1 | awk '{print $1}')
  if [[ -n "$ORCH_POD" ]]; then
    log "Testando conectividade do orchestrator ao MongoDB..."
    result=$(kubectl exec -n "$NS" "$ORCH_POD" -- python3 -c "
from pymongo import MongoClient
import os
uri = os.environ.get('MONGODB_URI', 'mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017')
try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print('OK - MongoDB conectado')
except Exception as e:
    print(f'FAIL - {e}')
" 2>/dev/null || echo "FAIL - Pod nao tem pymongo")
    echo "  Resultado: $result"
  fi
}

fix_redis_conn() {
  log "=== FIX: Conectividade Redis ==="
  REDIS_POD=$(kubectl get pods -A 2>/dev/null | grep -i redis | grep Running | head -1 | awk '{print $2}')
  REDIS_NS=$(kubectl get pods -A 2>/dev/null | grep "$REDIS_POD" | head -1 | awk '{print $1}')

  if [[ -z "$REDIS_POD" ]]; then
    warn "Redis nao encontrado"
    return
  fi

  log "Testando Redis PING..."
  result=$(kubectl exec -n "$REDIS_NS" "$REDIS_POD" -- redis-cli PING 2>/dev/null || echo "FAIL")
  if [[ "$result" == "PONG" ]]; then
    ok "Redis respondeu PONG"
  else
    fail "Redis nao respondeu: $result"
  fi

  log "Redis info memory:"
  kubectl exec -n "$REDIS_NS" "$REDIS_POD" -- redis-cli INFO memory 2>/dev/null | grep -E "used_memory_human|maxmemory_human" || true
}

fix_grpc_timeout() {
  log "=== FIX: Verificar timeouts gRPC dos Specialists ==="
  CE_POD=$(kubectl get pods -n "$NS" 2>/dev/null | grep consensus-engine | grep Running | head -1 | awk '{print $1}')

  if [[ -z "$CE_POD" ]]; then
    warn "Consensus Engine nao encontrado"
    return
  fi

  log "Verificando configuracao de timeout do Consensus Engine..."
  timeout_config=$(kubectl exec -n "$NS" "$CE_POD" -- env 2>/dev/null | grep -iE "timeout|grpc" || echo "")
  if [[ -n "$timeout_config" ]]; then
    echo "$timeout_config"
  else
    warn "Nenhuma variavel de timeout encontrada"
  fi

  log "Recomendacao: Timeout minimo de 120s (120000ms) para specialists com ML inference"
}

restart_all() {
  log "=== Rolling restart de todos os deployments ==="
  echo "ATENCAO: Isso vai reiniciar todos os pods do namespace $NS"
  echo "Continuar? (s/N)"
  read -r resp
  if [[ "$resp" != "s" ]] && [[ "$resp" != "S" ]]; then
    echo "Abortado"
    return
  fi

  for deploy in $(kubectl get deployments -n "$NS" -o name 2>/dev/null); do
    log "Restarting $deploy..."
    kubectl rollout restart -n "$NS" "$deploy" 2>/dev/null || warn "Falha ao reiniciar $deploy"
  done
  ok "Rolling restart iniciado. Aguarde os pods reiniciarem."
  log "Acompanhe com: kubectl get pods -n $NS -w"
}

check_resources() {
  log "=== Verificar uso de recursos vs limits ==="
  log "Pods com alto uso de memoria:"
  kubectl top pods -n "$NS" --sort-by=memory 2>/dev/null | head -15 || warn "metrics-server nao disponivel"

  echo ""
  log "Pods com alto uso de CPU:"
  kubectl top pods -n "$NS" --sort-by=cpu 2>/dev/null | head -15 || true

  echo ""
  log "Nodes:"
  kubectl top nodes 2>/dev/null || true
}

# Executar fix selecionado
case "$FIX" in
  restart-crashloop) fix_crashloop ;;
  fix-imagepull)     fix_imagepull ;;
  fix-pending)       fix_pending ;;
  fix-kafka-lag)     fix_kafka_lag ;;
  fix-mongo-conn)    fix_mongo_conn ;;
  fix-redis-conn)    fix_redis_conn ;;
  fix-grpc-timeout)  fix_grpc_timeout ;;
  restart-all)       restart_all ;;
  check-resources)   check_resources ;;
  all)
    fix_crashloop
    echo ""
    fix_imagepull
    echo ""
    fix_pending
    echo ""
    fix_kafka_lag
    echo ""
    fix_mongo_conn
    echo ""
    fix_redis_conn
    echo ""
    fix_grpc_timeout
    echo ""
    check_resources
    ;;
  *)
    echo "Fix desconhecido: $FIX"
    echo "Opcoes: restart-crashloop, fix-imagepull, fix-pending, fix-kafka-lag, fix-mongo-conn, fix-redis-conn, fix-grpc-timeout, restart-all, check-resources, all"
    exit 1
    ;;
esac

echo ""
ok "Diagnostico concluido."
