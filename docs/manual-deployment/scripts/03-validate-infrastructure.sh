#!/bin/bash
# Script de validação da infraestrutura Neural Hive-Mind
# Uso: ./03-validate-infrastructure.sh [--verbose] [--fix]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
REPORT_DIR="${PROJECT_ROOT}/.tmp"
REPORT_FILE="${REPORT_DIR}/infrastructure-validation-report.txt"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
VERBOSE=false
FIX_MODE=false
NETWORK_POD=""

# Pod selectors - Dependem das labels definidas nos charts Helm
# Atualize estas variáveis se os charts mudarem suas labels
KAFKA_POD_SELECTOR="strimzi.io/name=neural-hive-kafka-kafka"          # De: helm-charts/kafka-topics (Strimzi)
KAFKA_CLUSTER_SELECTOR="strimzi.io/cluster=neural-hive-kafka"         # De: helm-charts/kafka-topics (Strimzi)
REDIS_POD_SELECTOR="app=redis-cluster"                                # De: helm-charts/redis-cluster/values.yaml
MONGODB_POD_SELECTOR="app.kubernetes.io/name=mongodb"                 # De: helm-charts/mongodb/values.yaml
NEO4J_POD_SELECTOR="app.kubernetes.io/name=neo4j"                     # De: helm-charts/neo4j/values.yaml
CLICKHOUSE_POD_SELECTOR="app=clickhouse"                              # De: helm-charts/clickhouse/values.yaml

declare -A COMPONENT_STATUS=(
  [Kafka]="PASS"
  [Redis]="PASS"
  [MongoDB]="PASS"
  [Neo4j]="PASS"
  [ClickHouse]="PASS"
  [Connectivity]="PASS"
)
REPORT_LINES=()

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
  cat <<'EOF'
Uso: 03-validate-infrastructure.sh [opções]

Opções:
  --verbose    Mostra saídas detalhadas de cada verificação.
  --fix        Tenta correções automáticas básicas (restart de operators/pods).
  --help       Exibe esta ajuda.
EOF
}

cleanup_network_pod() {
  if [[ -n "${NETWORK_POD}" ]]; then
    kubectl delete pod "${NETWORK_POD}" -n kafka --ignore-not-found >/dev/null 2>&1 || true
    NETWORK_POD=""
  fi
}

trap cleanup_network_pod EXIT

ensure_tools() {
  for cmd in kubectl yq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Comando obrigatório não encontrado: $cmd"
      exit 1
    fi
  done
}

ensure_cluster() {
  if ! kubectl cluster-info >/dev/null 2>&1; then
    log_error "Não foi possível conectar ao cluster Kubernetes."
    exit 1
  fi
  log_success "Contexto atual: $(kubectl config current-context)"
}

safe_exec() {
  local cmd="$1"
  set +e
  bash -lc "$cmd" >/dev/null 2>&1
  set -e
}

attempt_fix() {
  local component="$1"
  local description="$2"
  [[ "$FIX_MODE" == true ]] || return
  log_warn "Tentando correção automática (${component} - ${description})..."
  case "$component" in
    Kafka)
      safe_exec "kubectl rollout restart deployment strimzi-cluster-operator -n kafka"
      ;;
    Redis)
      safe_exec "kubectl rollout restart deployment redis-operator -n redis-operator"
      ;;
    MongoDB)
      safe_exec "kubectl rollout restart deployment mongodb-kubernetes-operator -n mongodb-operator"
      ;;
    Neo4j)
      safe_exec "kubectl rollout restart statefulset neo4j -n neo4j-cluster"
      ;;
    ClickHouse)
      safe_exec "kubectl rollout restart deployment clickhouse-operator -n clickhouse-operator"
      ;;
    Connectivity)
      cleanup_network_pod
      ;;
  esac
}

run_check() {
  local description="$1"
  local component="$2"
  local command="$3"

  TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
  local output=""
  local exit_code=0
  local exec_type
  exec_type=$(type -t "$command" 2>/dev/null || true)

  if [[ "$exec_type" == "function" ]]; then
    set +e
    output=$($command 2>&1)
    exit_code=$?
    set -e
  else
    set +e
    output=$(bash -lc "$command" 2>&1)
    exit_code=$?
    set -e
  fi

  if [[ $exit_code -eq 0 ]]; then
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    log_success "[${component}] ${description}"
    if [[ "$VERBOSE" == true && -n "$output" ]]; then
      echo "$output"
    fi
    REPORT_LINES+=("[✓] ${component} - ${description}")
  else
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    COMPONENT_STATUS["$component"]="FAIL"
    log_error "[${component}] ${description}"
    if [[ -n "$output" ]]; then
      echo "$output"
    fi
    REPORT_LINES+=("[✗] ${component} - ${description}: ${output}")
    attempt_fix "$component" "$description"
  fi
}

get_pod() {
  local namespace="$1"
  local selector="$2"
  kubectl get pods -n "$namespace" -l "$selector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

check_pods_ready() {
  local namespace="$1"
  local selector="$2"
  local minimum="$3"
  mapfile -t phases < <(kubectl get pods -n "$namespace" -l "$selector" -o jsonpath='{range .items[*]}{.status.phase}{"\n"}{end}')
  local total=${#phases[@]}
  if [[ $total -lt $minimum ]]; then
    echo "Apenas ${total}/${minimum} pods encontrados."
    return 1
  fi
  for phase in "${phases[@]}"; do
    if [[ "$phase" != "Running" ]]; then
      echo "Pod em estado ${phase}"
      return 1
    fi
  done
  return 0
}

check_pvcs() {
  local namespace="$1"
  local data
  data=$(kubectl get pvc -n "$namespace" --no-headers 2>/dev/null || true)
  [[ -z "$data" ]] && return 0
  local pending
  pending=$(echo "$data" | awk '{if ($2 != "Bound") c++} END {print c+0}')
  if [[ "$pending" -gt 0 ]]; then
    echo "${pending} PVC(s) não estão Bound"
    return 1
  fi
  return 0
}

kafka_topic_list_check() {
  local pod
  pod=$(get_pod "kafka" "${KAFKA_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod Kafka encontrado."
    return 1
  fi
  kubectl exec -n kafka "$pod" -- /bin/sh -c "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/tmp/topics && cat /tmp/topics >/dev/null"
}

kafka_produce_consume_check() {
  local pod topic message consumed
  pod=$(get_pod "kafka" "${KAFKA_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod Kafka encontrado."
    return 1
  fi
  topic="neural-hive-health-check-$(date +%s)"
  message="health-check-$(date +%s)"
  kubectl exec -n kafka "$pod" -- bash -c "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic ${topic} --replication-factor 1 --partitions 1" >/dev/null 2>&1 || true
  kubectl exec -n kafka "$pod" -- bash -c "echo '${message}' | /opt/kafka/bin/kafka-console-producer.sh --broker-list localhost:9092 --topic ${topic} --producer-property acks=all" >/dev/null
  if ! consumed=$(kubectl exec -n kafka "$pod" -- bash -c "/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic ${topic} --from-beginning --timeout-ms 5000 --max-messages 1 --consumer-property group.id=nh-health-check-$(date +%s)"); then
    kubectl exec -n kafka "$pod" -- bash -c "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic ${topic}" >/dev/null 2>&1 || true
    return 1
  fi
  kubectl exec -n kafka "$pod" -- bash -c "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic ${topic}" >/dev/null 2>&1 || true
  echo "$consumed" | grep -q "${message}"
}

redis_ping_check() {
  local pod password
  pod=$(get_pod "redis-cluster" "${REDIS_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod Redis encontrado."
    return 1
  fi
  password=$(kubectl get secret -n redis-cluster redis-cluster-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)
  kubectl exec -n redis-cluster "$pod" -- redis-cli -a "$password" ping | grep -q "PONG"
}

redis_cluster_info_check() {
  local pod password
  pod=$(get_pod "redis-cluster" "${REDIS_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod Redis encontrado."
    return 1
  fi
  password=$(kubectl get secret -n redis-cluster redis-cluster-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)
  kubectl exec -n redis-cluster "$pod" -- redis-cli -a "$password" cluster info | grep -q "cluster_state:ok"
}

mongodb_ping_check() {
  local pod username password
  pod=$(get_pod "mongodb-cluster" "${MONGODB_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod MongoDB encontrado."
    return 1
  fi
  username=$(kubectl get secret -n mongodb-cluster neural-hive-mongodb-auth -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "root")
  password=$(kubectl get secret -n mongodb-cluster neural-hive-mongodb-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)
  kubectl exec -n mongodb-cluster "$pod" -- /bin/sh -c "mongosh --quiet -u '${username}' -p '${password}' --authenticationDatabase admin --eval \"db.adminCommand('ping')\" | grep -qi 'ok'"
}

mongodb_rs_status_check() {
  local pod username password
  pod=$(get_pod "mongodb-cluster" "${MONGODB_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod MongoDB encontrado."
    return 1
  fi
  username=$(kubectl get secret -n mongodb-cluster neural-hive-mongodb-auth -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "root")
  password=$(kubectl get secret -n mongodb-cluster neural-hive-mongodb-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)
  kubectl exec -n mongodb-cluster "$pod" -- /bin/sh -c "mongosh --quiet -u '${username}' -p '${password}' --authenticationDatabase admin --eval \"const status = rs.status(); if (status.ok !== 1) { quit(1); }\""
}

neo4j_cypher_check() {
  local pod password
  pod=$(get_pod "neo4j-cluster" "${NEO4J_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod Neo4j encontrado."
    return 1
  fi
  password=$(kubectl get secret -n neo4j-cluster neo4j-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)
  kubectl exec -n neo4j-cluster "$pod" -- /bin/bash -c "cypher-shell -u neo4j -p '${password}' 'RETURN 1' | grep -q 1"
}

neo4j_cluster_overview_check() {
  local pod password
  pod=$(get_pod "neo4j-cluster" "${NEO4J_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod Neo4j encontrado."
    return 1
  fi
  password=$(kubectl get secret -n neo4j-cluster neo4j-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)
  kubectl exec -n neo4j-cluster "$pod" -- bash -c "cypher-shell -u neo4j -p '${password}' --format plain \"CALL dbms.cluster.overview() YIELD id RETURN count(id)\" | grep -qE '[0-9]'"
}

clickhouse_query_check() {
  local pod
  pod=$(get_pod "clickhouse-cluster" "${CLICKHOUSE_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod ClickHouse encontrado."
    return 1
  fi
  kubectl exec -n clickhouse-cluster "$pod" -- clickhouse-client --query "SELECT version()"
}

clickhouse_system_cluster_check() {
  local pod
  pod=$(get_pod "clickhouse-cluster" "${CLICKHOUSE_POD_SELECTOR}")
  if [[ -z "$pod" ]]; then
    echo "Nenhum pod ClickHouse encontrado."
    return 1
  fi
  kubectl exec -n clickhouse-cluster "$pod" -- clickhouse-client --query "SELECT count() FROM system.clusters"
}

connectivity_probe() {
  local services=(
    "redis-cluster.redis-cluster.svc.cluster.local:6379"
    "mongodb.mongodb-cluster.svc.cluster.local:27017"
    "neo4j.neo4j-cluster.svc.cluster.local:7687"
    "clickhouse.clickhouse-cluster.svc.cluster.local:9000"
  )
  NETWORK_POD="infra-net-check-$(date +%s)"
  kubectl run "${NETWORK_POD}" -n kafka --image=busybox:1.36 --restart=Never --command -- sh -c "sleep 120" >/dev/null
  kubectl wait --for=condition=Ready pod "${NETWORK_POD}" -n kafka --timeout=60s >/dev/null
  local entry host port
  for entry in "${services[@]}"; do
    host="${entry%%:*}"
    port="${entry##*:}"
    kubectl exec -n kafka "${NETWORK_POD}" -- sh -c "nc -vz -w 3 ${host} ${port}" >/dev/null
  done
  cleanup_network_pod
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --verbose)
        VERBOSE=true
        shift
        ;;
      --fix)
        FIX_MODE=true
        shift
        ;;
      --help)
        usage
        exit 0
        ;;
      *)
        log_error "Opção desconhecida: $1"
        usage
        exit 1
        ;;
    esac
  done
}

validate_kafka() {
  log_info "Validando Kafka..."
  run_check "Operator Strimzi pronto" "Kafka" "kubectl wait --for=condition=Ready pod -l name=strimzi-cluster-operator -n kafka --timeout=300s"
  run_check "Kafka CR em estado Ready" "Kafka" "kubectl get kafka neural-hive-kafka -n kafka -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}' 2>/dev/null | grep -q True"
  run_check "Pods Kafka Running" "Kafka" "check_pods_ready kafka ${KAFKA_CLUSTER_SELECTOR} 1"
  run_check "Tópicos Kafka (>=10)" "Kafka" "test \$(kubectl get kafkatopic -n kafka --no-headers 2>/dev/null | wc -l | tr -d ' ') -ge 10"
  run_check "Serviços Kafka disponíveis" "Kafka" "kubectl get svc -n kafka"
  run_check "Listagem de tópicos por broker" "Kafka" kafka_topic_list_check
  run_check "Produção/consumo funcional" "Kafka" kafka_produce_consume_check
}

validate_redis() {
  log_info "Validando Redis..."
  run_check "Operator Redis pronto" "Redis" "kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=redis-operator -n redis-operator --timeout=300s"
  run_check "CR RedisCluster presente" "Redis" "kubectl get rediscluster -n redis-cluster"
  run_check "Pods Redis Running (>=3)" "Redis" "check_pods_ready redis-cluster ${REDIS_POD_SELECTOR} 3"
  run_check "PVCs Redis Bound" "Redis" "check_pvcs redis-cluster"
  run_check "Serviços Redis disponíveis" "Redis" "kubectl get svc -n redis-cluster"
  run_check "redis-cli ping" "Redis" redis_ping_check
  run_check "redis-cli cluster info" "Redis" redis_cluster_info_check
}

validate_mongodb() {
  log_info "Validando MongoDB..."
  run_check "Operator MongoDB pronto" "MongoDB" "kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=mongodb-kubernetes-operator -n mongodb-operator --timeout=300s"
  run_check "CR MongoDBCommunity presente" "MongoDB" "kubectl get mongodbcommunity -n mongodb-cluster"
  run_check "Pods MongoDB Running (>=3)" "MongoDB" "check_pods_ready mongodb-cluster ${MONGODB_POD_SELECTOR} 3"
  run_check "PVCs MongoDB Bound" "MongoDB" "check_pvcs mongodb-cluster"
  run_check "Serviços MongoDB disponíveis" "MongoDB" "kubectl get svc -n mongodb-cluster"
  run_check "mongosh ping" "MongoDB" mongodb_ping_check
  run_check "ReplicaSet rs.status()" "MongoDB" mongodb_rs_status_check
}

validate_neo4j() {
  log_info "Validando Neo4j..."
  run_check "Pods Neo4j Running" "Neo4j" "check_pods_ready neo4j-cluster ${NEO4J_POD_SELECTOR} 1"
  run_check "PVCs Neo4j Bound" "Neo4j" "check_pvcs neo4j-cluster"
  run_check "Serviços Neo4j (bolt/http/https)" "Neo4j" "kubectl get svc -n neo4j-cluster"
  run_check "Cypher ping" "Neo4j" neo4j_cypher_check
  run_check "Cluster overview" "Neo4j" neo4j_cluster_overview_check
}

validate_clickhouse() {
  log_info "Validando ClickHouse..."
  run_check "Operator ClickHouse pronto" "ClickHouse" "kubectl wait --for=condition=Ready pod -l app=clickhouse-operator -n clickhouse-operator --timeout=300s"
  run_check "CR ClickHouseInstallation presente" "ClickHouse" "kubectl get clickhouseinstallation -n clickhouse-cluster"
  run_check "Pods ClickHouse Running" "ClickHouse" "check_pods_ready clickhouse-cluster ${CLICKHOUSE_POD_SELECTOR} 1"
  run_check "PVCs ClickHouse Bound" "ClickHouse" "check_pvcs clickhouse-cluster"
  run_check "Serviços ClickHouse" "ClickHouse" "kubectl get svc -n clickhouse-cluster"
  run_check "Query SELECT 1" "ClickHouse" clickhouse_query_check
  run_check "system.clusters pronto" "ClickHouse" clickhouse_system_cluster_check
}

validate_connectivity() {
  log_info "Validando conectividade entre namespaces..."
  run_check "Prova de DNS/TCP cruzada" "Connectivity" connectivity_probe
}

validate_servicemonitors() {
  # NOTA: ServiceMonitors pertencem à fase de observabilidade, não infraestrutura básica.
  # Não usamos run_check para evitar que falhas afetem COMPONENT_STATUS ou FAILED_CHECKS.
  if kubectl api-resources | grep -q ServiceMonitor; then
    local sm_output
    sm_output=$(kubectl get servicemonitor -A 2>/dev/null | grep -E 'kafka|redis|mongodb|neo4j|clickhouse' || true)
    if [[ -n "$sm_output" ]]; then
      log_info "ServiceMonitors detectados (fase observabilidade):"
      echo "$sm_output"
    else
      log_warn "ServiceMonitors para infraestrutura não encontrados (fase observabilidade será tratada posteriormente)."
    fi
  else
    log_warn "ServiceMonitor CRD não encontrado; pulando validação de métricas."
  fi
}

generate_report() {
  mkdir -p "$REPORT_DIR"
  {
    echo "=== Validação da Infraestrutura Neural Hive-Mind ==="
    for component in Kafka Redis MongoDB Neo4j ClickHouse Connectivity; do
      local status="${COMPONENT_STATUS[$component]}"
      [[ -z "$status" ]] && status="PASS"
      local symbol="✓"
      [[ "$status" == "FAIL" ]] && symbol="✗"
      echo "[${symbol}] ${component}: ${status}"
    done
    echo ""
    echo "Total: ${TOTAL_CHECKS} checks (PASS=${PASSED_CHECKS}, FAIL=${FAILED_CHECKS})"
    echo ""
    echo "Detalhes:"
    for line in "${REPORT_LINES[@]}"; do
      echo " - ${line}"
    done
  } | tee "$REPORT_FILE"
  log_info "Relatório salvo em ${REPORT_FILE}"
}

main() {
  parse_args "$@"
  ensure_tools
  ensure_cluster

  validate_kafka
  validate_redis
  validate_mongodb
  validate_neo4j
  validate_clickhouse
  validate_connectivity
  validate_servicemonitors

  generate_report

  if [[ $FAILED_CHECKS -eq 0 ]]; then
    log_success "✓ ALL CHECKS PASSED"
  else
    log_error "✗ Falhas encontradas. Consulte o relatório."
    exit 1
  fi
}

main "$@"
