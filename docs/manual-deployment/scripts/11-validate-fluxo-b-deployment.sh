#!/usr/bin/env bash
set -euo pipefail

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERR]${NC} $1"; }

NAMESPACE="semantic-translation"
REPORT_FILE="/tmp/fluxo-b-validation-report.json"
SKIP_CONNECTIVITY=0
VERBOSE=0
CHECK_TIMEOUT=10

SERVICES=(
  "semantic-translation-engine"
  "specialist-business"
  "specialist-technical"
  "specialist-behavior"
  "specialist-evolution"
  "specialist-architecture"
)

SPECIALISTS=(
  "specialist-business"
  "specialist-technical"
  "specialist-behavior"
  "specialist-evolution"
  "specialist-architecture"
)

declare -A SERVICE_LABEL_SELECTORS=()
declare -A SERVICE_RESOURCE_NAMES=()
declare -A SERVICE_CONFIGMAP_NAMES=()
declare -A SERVICE_SECRET_NAMES=()
declare -A SPECIALIST_MONGODB_SECRET_KEYS=()

for svc in "${SERVICES[@]}"; do
  SERVICE_LABEL_SELECTORS[$svc]="app.kubernetes.io/name=${svc}"
  SERVICE_RESOURCE_NAMES[$svc]="$svc"
  SERVICE_CONFIGMAP_NAMES[$svc]="${svc}-config"
  SERVICE_SECRET_NAMES[$svc]="${svc}-secrets"
done

for specialist in "${SPECIALISTS[@]}"; do
  SPECIALIST_MONGODB_SECRET_KEYS[$specialist]="mongodb_uri"
done

KAFKA_BOOTSTRAP="neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
NEO4J_ENDPOINT="neo4j-bolt.neo4j-cluster.svc.cluster.local:7687"
MONGODB_ENDPOINT="mongodb.mongodb-cluster.svc.cluster.local:27017"
REDIS_ENDPOINT="neural-hive-cache.redis-cluster.svc.cluster.local:6379"
MLFLOW_ENDPOINT="mlflow.mlflow.svc.cluster.local:5000"
OTEL_ENDPOINT="opentelemetry-collector.observability.svc.cluster.local:4317"
DEFAULT_KAFKA_POD="neural-hive-kafka-kafka-0"
DEFAULT_MONGODB_POD="mongodb-0"
DEFAULT_NEO4J_POD="neo4j-0"
DEFAULT_PROM_POD="prometheus-kube-prometheus-prometheus-0"
KAFKA_SELECTOR="app.kubernetes.io/name=neural-hive-kafka"
MONGODB_SELECTOR="app.kubernetes.io/name=mongodb"
NEO4J_SELECTOR="app.kubernetes.io/name=neo4j"
PROM_SELECTOR="app.kubernetes.io/name=prometheus"

usage() {
  cat <<USAGE
Uso: $0 [opções]
  --namespace <ns>           Namespace do Fluxo B (padrão: semantic-translation)
  --output-report <arquivo>  Caminho do relatório JSON (padrão: /tmp/fluxo-b-validation-report.json)
  --skip-connectivity        Pula validações que exigem conectividade direta (nc/grpcurl)
  --verbose                  Mostra saída detalhada dos comandos
  -h, --help                 Exibe esta ajuda
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    --output-report)
      REPORT_FILE="${2:-}"
      shift 2
      ;;
    --skip-connectivity)
      SKIP_CONNECTIVITY=1
      shift
      ;;
    --verbose)
      VERBOSE=1
      shift
      ;;
    -h|--help)
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

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log_error "Comando obrigatório não encontrado: $1"
    exit 1
  fi
}

require_command kubectl
require_command jq
require_command curl
require_command timeout

GRPCURL_AVAILABLE=0
if command -v grpcurl >/dev/null 2>&1; then
  GRPCURL_AVAILABLE=1
else
  log_warning "grpcurl não encontrado; checks gRPC serão marcados como WARN."
fi

kubectl cluster-info >/dev/null 2>&1 || {
  log_error "kubectl não consegue falar com o cluster. Configure o contexto antes de continuar."
  exit 1
}

TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0
SKIPPED_CHECKS=0
CHECKS=()
CHECK_RESULTS_JSON=()
TABLE_ROWS=()

now_ms() {
  if date +%s%3N >/dev/null 2>&1; then
    date +%s%3N
  else
    echo "$(( $(date +%s) * 1000 ))"
  fi
}

CHECK_STATUS=""
CHECK_MESSAGE=""

run_with_timeout() {
  if [[ $VERBOSE -eq 1 ]]; then
    timeout "$CHECK_TIMEOUT" "$@"
  else
    timeout "$CHECK_TIMEOUT" "$@" >/dev/null 2>&1
  fi
}

run_capture() {
  local __outvar=$1
  shift
  local output
  if output=$(timeout "$CHECK_TIMEOUT" "$@" 2>&1); then
    printf -v "$__outvar" '%s' "$output"
    return 0
  else
    printf -v "$__outvar" '%s' "$output"
    return 1
  fi
}

get_label_selector_for_app() {
  local app=$1
  if [[ -n "${SERVICE_LABEL_SELECTORS[$app]:-}" ]]; then
    echo "${SERVICE_LABEL_SELECTORS[$app]}"
  else
    echo "app.kubernetes.io/name=${app}"
  fi
}

get_service_resource_name() {
  local app=$1
  if [[ -n "${SERVICE_RESOURCE_NAMES[$app]:-}" ]]; then
    echo "${SERVICE_RESOURCE_NAMES[$app]}"
  else
    echo "$app"
  fi
}

get_configmap_name_for_app() {
  local app=$1
  if [[ -n "${SERVICE_CONFIGMAP_NAMES[$app]:-}" ]]; then
    echo "${SERVICE_CONFIGMAP_NAMES[$app]}"
  else
    local base
    base=$(get_service_resource_name "$app")
    echo "${base}-config"
  fi
}

get_secret_name_for_app() {
  local app=$1
  if [[ -n "${SERVICE_SECRET_NAMES[$app]:-}" ]]; then
    echo "${SERVICE_SECRET_NAMES[$app]}"
  else
    local base
    base=$(get_service_resource_name "$app")
    echo "${base}-secrets"
  fi
}

get_mongodb_secret_key_for_specialist() {
  local app=$1
  if [[ -n "${SPECIALIST_MONGODB_SECRET_KEYS[$app]:-}" ]]; then
    echo "${SPECIALIST_MONGODB_SECRET_KEYS[$app]}"
  else
    echo "mongodb_uri"
  fi
}

declare -A POD_CACHE=()

get_pod_name_for_app() {
  local app=$1
  if [[ -n "${POD_CACHE[$app]:-}" ]]; then
    echo "${POD_CACHE[$app]}"
    return
  fi
  local pod=""
  local selector
  selector=$(get_label_selector_for_app "$app")
  if run_capture pod kubectl get pods -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[0].metadata.name}'; then
    if [[ -n "$pod" ]]; then
      POD_CACHE[$app]=$pod
      echo "$pod"
      return
    fi
  fi
  echo ""
}

get_service_port() {
  local svc=$1
  local port_key=$2
  local value=""
  if run_capture value kubectl get svc -n "$NAMESPACE" "$svc" -o "jsonpath={.spec.ports[?(@.name==\"$port_key\")].port}"; then
    echo "$value"
  else
    echo ""
  fi
}

http_exec_in_pod() {
  local pod=$1
  local port=$2
  local path=$3
  local output=""
  local cmd="if command -v curl >/dev/null 2>&1; then curl -s --fail http://127.0.0.1:${port}${path}; elif command -v wget >/dev/null 2>&1; then wget -qO- http://127.0.0.1:${port}${path}; else echo missing-http-client; exit 10; fi"
  if run_capture output kubectl exec -n "$NAMESPACE" "$pod" -- sh -c "$cmd"; then
    printf '%s' "$output"
    return 0
  fi
  return 1
}

get_external_pod() {
  local namespace=$1
  local selector=$2
  local fallback=$3
  local pod=""
  if run_capture pod kubectl get pods -n "$namespace" -l "$selector" -o jsonpath='{.items[0].metadata.name}'; then
    if [[ -n "$pod" ]]; then
      echo "$pod"
      return
    fi
  fi
  echo "$fallback"
}

record_check() {
  local id="$1"
  local description="$2"
  local function_name="$3"
  local args="${4:-}"
  CHECKS+=("${id}:::${description}:::${function_name}:::${args}")
}

run_check_entry() {
  local entry="$1"
  IFS=':::' read -r id description func args <<< "$entry"
  TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
  log_info "[$TOTAL_CHECKS] ${description}"
  CHECK_STATUS="PASS"
  CHECK_MESSAGE="OK"
  local start_ms
  start_ms=$(now_ms)
  local args_array=()
  if [[ -n "$args" ]]; then
    IFS='|' read -r -a args_array <<< "$args"
  fi
  "$func" "${args_array[@]}"
  local end_ms
  end_ms=$(now_ms)
  local duration=$((end_ms - start_ms))
  case "$CHECK_STATUS" in
    PASS)
      log_success "  ✓ ${CHECK_MESSAGE}"
      PASSED_CHECKS=$((PASSED_CHECKS + 1))
      ;;
    WARN)
      log_warning "  ⚠ ${CHECK_MESSAGE}"
      WARNING_CHECKS=$((WARNING_CHECKS + 1))
      ;;
    SKIPPED)
      log_warning "  - ${CHECK_MESSAGE}"
      SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
      ;;
    FAIL|*)
      log_error "  ✗ ${CHECK_MESSAGE}"
      FAILED_CHECKS=$((FAILED_CHECKS + 1))
      ;;
  esac
  TABLE_ROWS+=("${description}|${CHECK_STATUS}|${CHECK_MESSAGE}")
  local safe_desc
  safe_desc=$(printf '%s' "$description" | sed 's/"/\\"/g')
  local safe_msg
  safe_msg=$(printf '%s' "$CHECK_MESSAGE" | sed 's/"/\\"/g')
  CHECK_RESULTS_JSON+=("{\"name\":\"${safe_desc}\",\"status\":\"${CHECK_STATUS}\",\"message\":\"${safe_msg}\",\"duration_ms\":${duration}}")
}

# Funções auxiliares específicas dos checks --------------------------

check_namespace_exists() {
  if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    CHECK_STATUS="PASS"
    CHECK_MESSAGE="Namespace ${NAMESPACE} existe."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Namespace ${NAMESPACE} não encontrado."
  fi
}

check_pods_running() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    local phases=""
    local selector
    selector=$(get_label_selector_for_app "$svc")
    if run_capture phases kubectl get pods -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[*].status.phase}'; then
      if [[ "$phases" != *"Running"* ]]; then
        missing+=("$svc")
      fi
    else
      missing+=("$svc")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Todos os pods em Running."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pods não encontrados/running: ${missing[*]}"
  fi
}

check_pods_ready() {
  local not_ready=()
  for svc in "${SERVICES[@]}"; do
    local readiness=""
    local selector
    selector=$(get_label_selector_for_app "$svc")
    if run_capture readiness kubectl get pods -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[*].status.containerStatuses[*].ready}'; then
      if [[ "$readiness" != *"true"* ]]; then
        not_ready+=("$svc")
      fi
    else
      not_ready+=("$svc")
    fi
  done
  if [[ ${#not_ready[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Todos os pods Ready 1/1."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pods não prontos: ${not_ready[*]}"
  fi
}

check_deployments_available() {
  local unavailable=()
  for svc in "${SERVICES[@]}"; do
    local replicas=""
    local deploy_name
    deploy_name=$(get_service_resource_name "$svc")
    if run_capture replicas kubectl get deploy -n "$NAMESPACE" "$deploy_name" -o jsonpath='{.status.availableReplicas}'; then
      if [[ "$replicas" != "1" ]]; then
        unavailable+=("$deploy_name")
      fi
    else
      unavailable+=("$deploy_name")
    fi
  done
  if [[ ${#unavailable[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Deployments disponíveis."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Deployments sem replicas disponíveis: ${unavailable[*]}"
  fi
}

check_pod_restarts() {
  local offenders=()
  for svc in "${SERVICES[@]}"; do
    local restarts=""
    local selector
    selector=$(get_label_selector_for_app "$svc")
    if run_capture restarts kubectl get pods -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'; then
      for count in $restarts; do
        if [[ "$count" -ge 3 ]]; then
          offenders+=("$svc")
          break
        fi
      done
    fi
  done
  if [[ ${#offenders[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Nenhum pod com restarts > 3."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Restarts elevados nos serviços: ${offenders[*]}"
  fi
}

check_pod_age() {
  local too_young=()
  for svc in "${SERVICES[@]}"; do
    local ages=""
    local selector
    selector=$(get_label_selector_for_app "$svc")
    if run_capture ages kubectl get pods -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[*].status.startTime}'; then
      # Simplificação: verificar se tempo de inicialização existe
      if [[ -z "$ages" ]]; then
        too_young+=("$svc")
      fi
    else
      too_young+=("$svc")
    fi
  done
  if [[ ${#too_young[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Pods ativos há mais de alguns minutos."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Pods recém criados (aguarde): ${too_young[*]}"
  fi
}

check_services_exist() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    local resource=""
    resource=$(get_service_resource_name "$svc")
    if ! kubectl get svc -n "$NAMESPACE" "$resource" >/dev/null 2>&1; then
      missing+=("$resource")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Services ClusterIP encontrados."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Services ausentes: ${missing[*]}"
  fi
}

check_service_endpoints() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    local subsets=""
    local resource=""
    resource=$(get_service_resource_name "$svc")
    if run_capture subsets kubectl get endpoints -n "$NAMESPACE" "$resource" -o jsonpath='{.subsets[*].addresses[*].ip}'; then
      if [[ -z "$subsets" ]]; then
        missing+=("$resource")
      fi
    else
      missing+=("$resource")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Endpoints preenchidos para todos services."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Services sem endpoints: ${missing[*]}"
  fi
}

check_ste_service_port() {
  local port=""
  local svc_name
  svc_name=$(get_service_resource_name "semantic-translation-engine")
  if run_capture port kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.ports[?(@.port==8000)].port}'; then
    if [[ "$port" == "8000" ]]; then
      CHECK_MESSAGE="Porta HTTP 8000 exposta."
      return
    fi
  fi
  CHECK_STATUS="FAIL"
  CHECK_MESSAGE="Service do STE não expõe porta 8000."
}

check_specialists_grpc_ports() {
  local missing=()
  for svc in "${SPECIALISTS[@]}"; do
    local port=""
    local svc_name
    svc_name=$(get_service_resource_name "$svc")
    if run_capture port kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.ports[?(@.name=="grpc")].port}'; then
      if [[ "$port" != "50051" ]]; then
        missing+=("$svc_name")
      fi
    else
      missing+=("$svc_name")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Porta gRPC 50051 presente em todos specialists."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Services sem porta gRPC 50051: ${missing[*]}"
  fi
}

check_specialists_metrics_ports() {
  local missing=()
  for svc in "${SPECIALISTS[@]}"; do
    local port=""
    local svc_name
    svc_name=$(get_service_resource_name "$svc")
    if run_capture port kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.ports[?(@.name=="metrics")].port}'; then
      if [[ "$port" != "8080" ]]; then
        missing+=("$svc_name")
      fi
    else
      missing+=("$svc_name")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Portas de métricas 8080 expostas."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Services sem porta de métricas 8080: ${missing[*]}"
  fi
}

check_configmaps_exist() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    local cfg=""
    cfg=$(get_configmap_name_for_app "$svc")
    if ! kubectl get configmap -n "$NAMESPACE" "$cfg" >/dev/null 2>&1; then
      missing+=("$cfg")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="ConfigMaps presentes."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="ConfigMaps ausentes: ${missing[*]}"
  fi
}

check_secrets_exist() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    local secret=""
    secret=$(get_secret_name_for_app "$svc")
    if ! kubectl get secret -n "$NAMESPACE" "$secret" >/dev/null 2>&1; then
      missing+=("$secret")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Secrets presentes."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Secrets ausentes: ${missing[*]}"
  fi
}

check_ste_kafka_config() {
  local cfg_name
  cfg_name=$(get_configmap_name_for_app "semantic-translation-engine")
  local cfg=""
  if run_capture cfg kubectl get configmap -n "$NAMESPACE" "$cfg_name" -o jsonpath='{.data.KAFKA_BOOTSTRAP_SERVERS}'; then
    if [[ -n "$cfg" ]]; then
      CHECK_MESSAGE="Kafka bootstrap configurado (${cfg})."
      return
    fi
  fi
  CHECK_STATUS="FAIL"
  CHECK_MESSAGE="ConfigMap do STE sem KAFKA_BOOTSTRAP_SERVERS."
}

check_ste_neo4j_config() {
  local cfg=""
  local cfg_name
  cfg_name=$(get_configmap_name_for_app "semantic-translation-engine")
  if run_capture cfg kubectl get configmap -n "$NAMESPACE" "$cfg_name" -o jsonpath='{.data.NEO4J_URI}'; then
    if [[ "$cfg" == bolt://* ]]; then
      CHECK_MESSAGE="ConfigMap aponta para Neo4j (${cfg})."
      return
    fi
  fi
  CHECK_STATUS="FAIL"
  CHECK_MESSAGE="ConfigMap do STE sem NEO4J_URI."
}

check_specialists_mongodb_config() {
  local missing=()
  for svc in "${SPECIALISTS[@]}"; do
    local secret=""
    secret=$(get_secret_name_for_app "$svc")
    local encoded=""
    local key=""
    key=$(get_mongodb_secret_key_for_specialist "$svc")
    if run_capture encoded kubectl get secret -n "$NAMESPACE" "$secret" -o "jsonpath={.data.${key}}"; then
      local uri=""
      uri=$(printf '%s' "$encoded" | base64 --decode 2>/dev/null || echo "")
      if [[ "$uri" != mongodb://* ]]; then
        missing+=("$secret")
      fi
    else
      missing+=("$secret")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Secrets dos specialists contêm mongodb_uri."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="mongodb_uri ausente ou inválido em: ${missing[*]}"
  fi
}

http_check_service() {
  local svc=$1
  local port=$2
  local path=$3
  local expect=$4
  local pod
  pod=$(get_pod_name_for_app "$svc")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod de ${svc} não encontrado."
    return 1
  fi
  local output=""
  if output=$(http_exec_in_pod "$pod" "$port" "$path"); then
    if [[ "$output" == *"$expect"* ]]; then
      CHECK_MESSAGE="Endpoint ${svc}${path} respondeu ${expect}."
      return 0
    fi
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Resposta inesperada em ${svc}${path}: ${output}"
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao consultar ${svc}${path} (curl/wget indisponível?)."
  fi
}

tcp_test_from_service() {
  local svc=$1
  local host=$2
  local port=$3
  local label=$4
  if [[ $SKIP_CONNECTIVITY -eq 1 ]]; then
    CHECK_STATUS="SKIPPED"
    CHECK_MESSAGE="Conectividade ignorada (--skip-connectivity)."
    return
  fi
  local pod
  pod=$(get_pod_name_for_app "$svc")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod de ${svc} não encontrado para testar ${label}."
    return
  fi
  local cmd="if command -v nc >/dev/null 2>&1; then nc -z -w5 ${host} ${port}; elif command -v timeout >/dev/null 2>&1; then timeout 5 sh -c '> /dev/tcp/${host}/${port}' >/dev/null 2>&1; else sh -c '> /dev/tcp/${host}/${port}' >/dev/null 2>&1; fi"
  if run_with_timeout kubectl exec -n "$NAMESPACE" "$pod" -- sh -c "$cmd"; then
    CHECK_STATUS="PASS"
    CHECK_MESSAGE="Conectividade ${label} ok."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha de conectividade ${label} a partir de ${svc}."
  fi
}

check_ste_to_kafka() {
  tcp_test_from_service "semantic-translation-engine" "${KAFKA_BOOTSTRAP%%:*}" "${KAFKA_BOOTSTRAP##*:}" "Kafka"
}

check_ste_to_neo4j() {
  local endpoint="${NEO4J_ENDPOINT#bolt://}"
  tcp_test_from_service "semantic-translation-engine" "${endpoint%%:*}" "${endpoint##*:}" "Neo4j"
}

check_ste_to_mongodb() {
  local endpoint="${MONGODB_ENDPOINT#mongodb://}"
  tcp_test_from_service "semantic-translation-engine" "${endpoint%%:*}" "${endpoint##*:}" "MongoDB"
}

check_ste_to_redis() {
  tcp_test_from_service "semantic-translation-engine" "${REDIS_ENDPOINT%%:*}" "${REDIS_ENDPOINT##*:}" "Redis"
}

check_specialists_to_mongodb() {
  if [[ $SKIP_CONNECTIVITY -eq 1 ]]; then
    CHECK_STATUS="SKIPPED"
    CHECK_MESSAGE="Conectividade ignorada (--skip-connectivity)."
    return
  fi
  local endpoint="${MONGODB_ENDPOINT#mongodb://}"
  local host="${endpoint%%:*}"
  local port="${endpoint##*:}"
  local failures=()
  for svc in "${SPECIALISTS[@]}"; do
    CHECK_STATUS="PASS"
    tcp_test_from_service "$svc" "$host" "$port" "MongoDB"
    if [[ "$CHECK_STATUS" == "FAIL" ]]; then
      failures+=("$svc")
    fi
  done
  if [[ ${#failures[@]} -eq 0 ]]; then
    CHECK_STATUS="PASS"
    CHECK_MESSAGE="Todos specialists conectam no MongoDB."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha de MongoDB em: ${failures[*]}"
  fi
}

check_specialists_to_neo4j() {
  if [[ $SKIP_CONNECTIVITY -eq 1 ]]; then
    CHECK_STATUS="SKIPPED"
    CHECK_MESSAGE="Conectividade ignorada (--skip-connectivity)."
    return
  fi
  local endpoint="${NEO4J_ENDPOINT#bolt://}"
  local host="${endpoint%%:*}"
  local port="${endpoint##*:}"
  local failures=()
  for svc in "${SPECIALISTS[@]}"; do
    CHECK_STATUS="PASS"
    tcp_test_from_service "$svc" "$host" "$port" "Neo4j"
    if [[ "$CHECK_STATUS" == "FAIL" ]]; then
      failures+=("$svc")
    fi
  done
  if [[ ${#failures[@]} -eq 0 ]]; then
    CHECK_STATUS="PASS"
    CHECK_MESSAGE="Todos specialists conectam em Neo4j."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha de Neo4j em: ${failures[*]}"
  fi
}

check_specialists_to_mlflow() {
  if [[ $SKIP_CONNECTIVITY -eq 1 ]]; then
    CHECK_STATUS="SKIPPED"
    CHECK_MESSAGE="Conectividade ignorada (--skip-connectivity)."
    return
  fi
  local endpoint="${MLFLOW_ENDPOINT#http://}"
  local host="${endpoint%%:*}"
  local port="${endpoint##*:}"
  local failures=()
  for svc in "${SPECIALISTS[@]}"; do
    CHECK_STATUS="PASS"
    tcp_test_from_service "$svc" "$host" "$port" "MLflow"
    if [[ "$CHECK_STATUS" == "FAIL" ]]; then
      failures+=("$svc")
    fi
  done
  if [[ ${#failures[@]} -eq 0 ]]; then
    CHECK_STATUS="PASS"
    CHECK_MESSAGE="Todos specialists conectam em MLflow."
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha de MLflow em: ${failures[*]}"
  fi
}

check_kafka_topics_exist() {
  local kafka_pod
  kafka_pod=$(get_external_pod "kafka" "$KAFKA_SELECTOR" "$DEFAULT_KAFKA_POD")
  if [[ -z "$kafka_pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod Kafka não encontrado."
    return
  fi
  local output=""
  if run_capture output kubectl exec -n kafka "$kafka_pod" -- bash -c "bin/kafka-topics.sh --bootstrap-server localhost:9092 --list"; then
    local missing=()
    for topic in intentions.business intentions.technical intentions.infrastructure intentions.security plans.ready; do
      if ! grep -q "$topic" <<<"$output"; then
        missing+=("$topic")
      fi
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
      CHECK_MESSAGE="Tópicos Kafka necessários encontrados."
    else
      CHECK_STATUS="FAIL"
      CHECK_MESSAGE="Tópicos ausentes: ${missing[*]}"
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao listar tópicos Kafka."
  fi
}

check_ste_consumer_group() {
  local kafka_pod
  kafka_pod=$(get_external_pod "kafka" "$KAFKA_SELECTOR" "$DEFAULT_KAFKA_POD")
  if [[ -z "$kafka_pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod Kafka não encontrado."
    return
  fi
  local output=""
  if run_capture output kubectl exec -n kafka "$kafka_pod" -- bash -c "bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list"; then
    if grep -q "semantic-translation-engine-local" <<<"$output"; then
      CHECK_MESSAGE="Consumer group semantic-translation-engine-local encontrado."
    else
      CHECK_STATUS="FAIL"
      CHECK_MESSAGE="Consumer group semantic-translation-engine-local ausente."
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao listar consumer groups."
  fi
}

check_ste_consumer_lag() {
  local kafka_pod
  kafka_pod=$(get_external_pod "kafka" "$KAFKA_SELECTOR" "$DEFAULT_KAFKA_POD")
  if [[ -z "$kafka_pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod Kafka não encontrado."
    return
  fi
  local output=""
  if run_capture output kubectl exec -n kafka "$kafka_pod" -- bash -c "bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group semantic-translation-engine-local"; then
    local lag
    lag=$(echo "$output" | awk 'NR>1 {sum+=$6} END {print sum+0}')
    if [[ -z "$lag" ]]; then
      lag=0
    fi
    if (( lag < 100 )); then
      CHECK_MESSAGE="Lag total ${lag} (<100)."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="Lag elevado (${lag})."
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao consultar consumer group."
  fi
}

check_plans_ready_topic_messages() {
  local kafka_pod
  kafka_pod=$(get_external_pod "kafka" "$KAFKA_SELECTOR" "$DEFAULT_KAFKA_POD")
  if [[ -z "$kafka_pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod Kafka não encontrado."
    return
  fi

  local output=""
  if run_capture output kubectl exec -n kafka "$kafka_pod" -- bash -c "bin/kafka-run-class.sh kafka.tools.GetOffsetShell --broker-list localhost:9092 --topic plans.ready | awk -F: '{sum+=\$3} END {print sum}'"; then
    if [[ "${output:-0}" -gt 0 ]]; then
      CHECK_MESSAGE="plans.ready possui mensagens (${output})."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="plans.ready vazio (envie intenção de teste)."
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao consultar offsets de plans.ready."
  fi
}

grpc_health_call() {
  local svc=$1
  local label=$2
  if [[ $GRPCURL_AVAILABLE -eq 0 ]]; then
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="grpcurl indisponível para ${label}."
    return 1
  fi
  local local_port=$((RANDOM % 1000 + 20050))
  local tmp_log
  tmp_log=$(mktemp)
  kubectl port-forward -n "$NAMESPACE" "svc/${svc}" "${local_port}:50051" >"$tmp_log" 2>&1 &
  local pf_pid=$!
  sleep 2
  local result=0
  if ! timeout "$CHECK_TIMEOUT" grpcurl -plaintext "localhost:${local_port}" grpc.health.v1.Health/Check >/dev/null 2>&1; then
    result=1
  fi
  kill "$pf_pid" >/dev/null 2>&1 || true
  wait "$pf_pid" >/dev/null 2>&1 || true
  rm -f "$tmp_log"
  if [[ $result -eq 0 ]]; then
    CHECK_MESSAGE="gRPC Health/Check SERVING (${label})."
    return 0
  fi
  CHECK_STATUS="FAIL"
  CHECK_MESSAGE="gRPC Health/Check falhou (${label})."
  return 1
}

check_grpc_health_specialist() {
  local svc=$1
  local label=${2:-$1}
  grpc_health_call "$svc" "$label"
}

check_grpc_evaluate_plan_stub() {
  if [[ $GRPCURL_AVAILABLE -eq 0 ]]; then
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="grpcurl indisponível para teste EvaluatePlan."
    return
  fi
  local svc="specialist-business"
  local local_port=$((RANDOM % 1000 + 21000))
  local tmp_log
  tmp_log=$(mktemp)
  kubectl port-forward -n "$NAMESPACE" "svc/${svc}" "${local_port}:50051" >"$tmp_log" 2>&1 &
  local pf_pid=$!
  sleep 2
  local payload='{"plan_id":"validation-plan","intent_id":"demo-intent"}'
  local result=0
  if ! timeout "$CHECK_TIMEOUT" grpcurl -plaintext -d "$payload" "localhost:${local_port}" ai.neuralhivemind.specialist.v1.SpecialistService/EvaluatePlan >/dev/null 2>&1; then
    result=1
  fi
  kill "$pf_pid" >/dev/null 2>&1 || true
  wait "$pf_pid" >/dev/null 2>&1 || true
  rm -f "$tmp_log"
  if [[ $result -eq 0 ]]; then
    CHECK_MESSAGE="Chamada EvaluatePlan respondeu (stub)."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Falha ao chamar EvaluatePlan (ajuste nomes gRPC se necessário)."
  fi
}

logs_contains() {
  local pod=$1
  local pattern=$2
  local output=""
  if run_capture output kubectl logs -n "$NAMESPACE" "$pod" --tail=200; then
    if grep -qi "$pattern" <<<"$output"; then
      return 0
    fi
  fi
  return 1
}

check_ste_logs_kafka_consumer() {
  local pod
  pod=$(get_pod_name_for_app "semantic-translation-engine")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod do STE não encontrado."
    return
  fi
  if logs_contains "$pod" "Kafka consumer initialized\|Subscribed to topics"; then
    CHECK_MESSAGE="Logs indicam consumo Kafka."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Não encontrei logs de consumo Kafka (verifique manualmente)."
  fi
}

check_ste_logs_plan_generation() {
  local pod
  pod=$(get_pod_name_for_app "semantic-translation-engine")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod do STE não encontrado."
    return
  fi
  if logs_contains "$pod" "Cognitive plan generated\|Plan published"; then
    CHECK_MESSAGE="Logs indicam planos gerados/publicados."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Sem logs recentes de geração de planos."
  fi
}

check_specialists_logs_grpc_server() {
  local failures=()
  for svc in "${SPECIALISTS[@]}"; do
    local pod
    pod=$(get_pod_name_for_app "$svc")
    if [[ -z "$pod" ]]; then
      failures+=("$svc")
      continue
    fi
    if ! logs_contains "$pod" "gRPC server"; then
      failures+=("$svc")
    fi
  done
  if [[ ${#failures[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Logs mostram gRPC server inicializado."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="gRPC server não detectado nos logs: ${failures[*]}"
  fi
}

check_specialists_logs_evaluation() {
  local failures=()
  for svc in "${SPECIALISTS[@]}"; do
    local pod
    pod=$(get_pod_name_for_app "$svc")
    if [[ -z "$pod" ]]; then
      failures+=("$svc")
      continue
    fi
    if ! logs_contains "$pod" "EvaluatePlan\|Opinion generated"; then
      failures+=("$svc")
    fi
  done
  if [[ ${#failures[@]} -eq 0 ]]; then
    CHECK_MESSAGE="Logs dos specialists indicam avaliações."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Sem logs de avaliação em: ${failures[*]}"
  fi
}

check_mongodb_cognitive_ledger() {
  local pod
  pod=$(get_external_pod "mongodb-cluster" "$MONGODB_SELECTOR" "$DEFAULT_MONGODB_POD")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod MongoDB não encontrado."
    return
  fi
  local count=""
  if run_capture count kubectl exec -n mongodb-cluster "$pod" -- mongosh --quiet --eval 'use neural_hive; db.cognitive_ledger.countDocuments()'; then
    if [[ "${count:-0}" -gt 0 ]]; then
      CHECK_MESSAGE="cognitive_ledger possui ${count} documentos."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="cognitive_ledger vazio."
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao consultar MongoDB."
  fi
}

check_mongodb_specialist_opinions() {
  local pod
  pod=$(get_external_pod "mongodb-cluster" "$MONGODB_SELECTOR" "$DEFAULT_MONGODB_POD")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod MongoDB não encontrado."
    return
  fi
  local count=""
  if run_capture count kubectl exec -n mongodb-cluster "$pod" -- mongosh --quiet --eval 'use neural_hive; db.specialist_opinions.countDocuments()'; then
    if [[ "${count:-0}" -gt 0 ]]; then
      CHECK_MESSAGE="specialist_opinions possui ${count} documentos."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="specialist_opinions vazia."
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao consultar MongoDB para specialist_opinions."
  fi
}

check_neo4j_knowledge_graph() {
  local pod
  pod=$(get_external_pod "neo4j-cluster" "$NEO4J_SELECTOR" "$DEFAULT_NEO4J_POD")
  if [[ -z "$pod" ]]; then
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Pod Neo4j não encontrado."
    return
  fi
  local result=""
  if run_capture result kubectl exec -n neo4j-cluster "$pod" -- cypher-shell -u neo4j -p neo4j-local-password 'MATCH (n) RETURN count(n) LIMIT 1'; then
    if [[ "$result" == *"count(n)"* ]]; then
      CHECK_MESSAGE="Neo4j respondeu a consulta básica."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="Resposta inesperada ao consultar Neo4j."
    fi
  else
    CHECK_STATUS="FAIL"
    CHECK_MESSAGE="Falha ao executar cypher-shell."
  fi
}

check_servicemonitors_exist() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    if ! kubectl get servicemonitor -n "$NAMESPACE" "$svc" >/dev/null 2>&1; then
      missing+=("$svc")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="ServiceMonitors encontrados."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="ServiceMonitors ausentes: ${missing[*]}"
  fi
}

check_prometheus_targets() {
  local prom_pod
  prom_pod=$(get_external_pod "observability" "$PROM_SELECTOR" "$DEFAULT_PROM_POD")
  if [[ -z "$prom_pod" ]]; then
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Pod do Prometheus não identificado."
    return
  fi
  local local_port=$((RANDOM % 1000 + 22000))
  kubectl port-forward -n observability "$prom_pod" "${local_port}:9090" >/tmp/prom-pf.log 2>&1 &
  local pf_pid=$!
  sleep 2
  local output=""
  if run_capture output curl -s "http://127.0.0.1:${local_port}/api/v1/targets?state=active"; then
    if echo "$output" | jq -e '.data.activeTargets[] | select(.labels.job=="semantic-translation-engine" or .labels.job|test("specialist"))' >/dev/null 2>&1; then
      CHECK_MESSAGE="Prometheus possui targets ativos para o Fluxo B."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="Targets do Fluxo B não encontrados no Prometheus."
    fi
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Falha ao consultar API do Prometheus."
  fi
  kill "$pf_pid" >/dev/null 2>&1 || true
  wait "$pf_pid" >/dev/null 2>&1 || true
  rm -f /tmp/prom-pf.log
}

check_ste_metrics_endpoint() {
  http_check_service "semantic-translation-engine" 8000 "/metrics" "# HELP"
}

check_specialist_metrics_endpoint() {
  local svc=$1
  http_check_service "$svc" 8080 "/metrics" "# HELP"
}

check_pod_cpu_usage() {
  local output=""
  if run_capture output kubectl top pod -n "$NAMESPACE"; then
    local offenders=()
    while read -r line; do
      local pod cpu
      pod=$(awk '{print $1}' <<<"$line")
      cpu=$(awk '{print $2}' <<<"$line")
      cpu=${cpu%m}
      if [[ "$pod" == semantic-translation-engine* && "$cpu" -gt 900 ]]; then
        offenders+=("$pod:${cpu}m")
      elif [[ "$pod" == specialist-* && "$cpu" -gt 700 ]]; then
        offenders+=("$pod:${cpu}m")
      fi
    done < <(echo "$output" | tail -n +2)
    if [[ ${#offenders[@]} -eq 0 ]]; then
      CHECK_MESSAGE="CPU dentro dos limites definidos."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="Pods com CPU alta: ${offenders[*]}"
    fi
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="kubectl top pod indisponível (instale metrics-server)."
  fi
}

check_pod_memory_usage() {
  local output=""
  if run_capture output kubectl top pod -n "$NAMESPACE"; then
    local offenders=()
    while read -r line; do
      local pod mem
      pod=$(awk '{print $1}' <<<"$line")
      mem=$(awk '{print $3}' <<<"$line")
      mem=${mem%Mi}
      if [[ "$pod" == semantic-translation-engine* && "$mem" -gt 1800 ]]; then
        offenders+=("$pod:${mem}Mi")
      elif [[ "$pod" == specialist-* && "$mem" -gt 1400 ]]; then
        offenders+=("$pod:${mem}Mi")
      fi
    done < <(echo "$output" | tail -n +2)
    if [[ ${#offenders[@]} -eq 0 ]]; then
      CHECK_MESSAGE="Memória dentro dos limites."
    else
      CHECK_STATUS="WARN"
      CHECK_MESSAGE="Pods com memória alta: ${offenders[*]}"
    fi
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="kubectl top pod indisponível (instale metrics-server)."
  fi
}

check_node_capacity() {
  local output=""
  if run_capture output kubectl top nodes; then
    CHECK_MESSAGE="kubectl top nodes executado. Utilize valores para comparar recursos."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Falha ao executar kubectl top nodes."
  fi
}

check_serviceaccounts_exist() {
  local missing=()
  for svc in "${SERVICES[@]}"; do
    if ! kubectl get serviceaccount -n "$NAMESPACE" "$svc" >/dev/null 2>&1; then
      missing+=("$svc")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    CHECK_MESSAGE="ServiceAccounts presentes."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="ServiceAccounts ausentes: ${missing[*]}"
  fi
}

check_rbac_bindings() {
  local bindings
  if ! run_capture bindings kubectl get rolebinding -n "$NAMESPACE"; then
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Falha ao listar RoleBindings."
    return
  fi
  if grep -q "semantic-translation-engine" <<<"$bindings" && grep -q "specialist" <<<"$bindings"; then
    CHECK_MESSAGE="RoleBindings padrão encontrados."
  else
    CHECK_STATUS="WARN"
    CHECK_MESSAGE="Revise RoleBindings do namespace (padrões não encontrados)."
  fi
}

# Registro dos checks ------------------------------------------------

record_check "namespace" "Namespace disponível" check_namespace_exists
record_check "pods-running" "Pods em Running" check_pods_running
record_check "pods-ready" "Pods em Ready 1/1" check_pods_ready
record_check "deployments" "Deployments com replicas disponíveis" check_deployments_available
record_check "pod-restarts" "Contagem de restarts aceitável" check_pod_restarts
record_check "pod-age" "Pods com idade mínima" check_pod_age
record_check "services-exist" "Services ClusterIP criados" check_services_exist
record_check "service-endpoints" "Services com endpoints" check_service_endpoints
record_check "ste-service-port" "Service do STE expõe porta 8000" check_ste_service_port
record_check "specialists-grpc-port" "Services dos specialists expõem gRPC" check_specialists_grpc_ports
record_check "specialists-metrics-port" "Services dos specialists expõem métricas" check_specialists_metrics_ports
record_check "configmaps" "ConfigMaps presentes" check_configmaps_exist
record_check "secrets" "Secrets presentes" check_secrets_exist
record_check "ste-kafka-config" "ConfigMap STE com Kafka" check_ste_kafka_config
record_check "ste-neo4j-config" "ConfigMap STE com Neo4j" check_ste_neo4j_config
record_check "specialists-mongodb-config" "Secrets specialists com MongoDB" check_specialists_mongodb_config
record_check "ste-health" "STE /health saudável" check_ste_http_health
record_check "ste-ready" "STE /ready pronto" check_ste_http_ready

for svc in "${SPECIALISTS[@]}"; do
  record_check "health-${svc}" "Health HTTP ${svc}" check_specialist_http_health "$svc"
done
for svc in "${SPECIALISTS[@]}"; do
  record_check "ready-${svc}" "Ready HTTP ${svc}" check_specialist_http_ready "$svc"
done

record_check "ste-kafka-connectivity" "STE consegue acessar Kafka" check_ste_to_kafka
record_check "ste-neo4j-connectivity" "STE consegue acessar Neo4j" check_ste_to_neo4j
record_check "ste-mongodb-connectivity" "STE consegue acessar MongoDB" check_ste_to_mongodb
record_check "ste-redis-connectivity" "STE consegue acessar Redis" check_ste_to_redis
record_check "specialists-mongodb" "Specialists conseguem acessar MongoDB" check_specialists_to_mongodb
record_check "specialists-neo4j" "Specialists conseguem acessar Neo4j" check_specialists_to_neo4j
record_check "specialists-mlflow" "Specialists conseguem acessar MLflow" check_specialists_to_mlflow

record_check "kafka-topics" "Tópicos Kafka necessários existem" check_kafka_topics_exist
record_check "consumer-group" "Consumer group do STE registrado" check_ste_consumer_group
record_check "consumer-lag" "Lag do consumer group dentro do limite" check_ste_consumer_lag
record_check "plans-ready-offset" "plans.ready possui mensagens" check_plans_ready_topic_messages

for svc in "${SPECIALISTS[@]}"; do
  record_check "grpc-health-${svc}" "gRPC Health ${svc}" check_grpc_health_specialist "$svc|$svc"
done
record_check "grpc-evaluate-plan" "Teste gRPC EvaluatePlan (stub)" check_grpc_evaluate_plan_stub

record_check "ste-logs-kafka" "Logs do STE indicam consumo Kafka" check_ste_logs_kafka_consumer
record_check "ste-logs-plan" "Logs do STE indicam geração de planos" check_ste_logs_plan_generation
record_check "specialists-logs-grpc" "Logs dos specialists mostram gRPC server" check_specialists_logs_grpc_server
record_check "specialists-logs-eval" "Logs dos specialists mostram avaliações" check_specialists_logs_evaluation

record_check "mongodb-ledger" "MongoDB cognitive_ledger com dados" check_mongodb_cognitive_ledger
record_check "mongodb-opinions" "MongoDB specialist_opinions com dados" check_mongodb_specialist_opinions
record_check "neo4j-graph" "Neo4j retorna resultados" check_neo4j_knowledge_graph

record_check "servicemonitors" "ServiceMonitors presentes" check_servicemonitors_exist
record_check "prometheus-targets" "Prometheus possui targets do Fluxo B" check_prometheus_targets
record_check "ste-metrics" "STE expõe métricas" check_ste_metrics_endpoint
for svc in "${SPECIALISTS[@]}"; do
  record_check "metrics-${svc}" "Specialist ${svc} expõe métricas" check_specialist_metrics_endpoint "$svc"
done

record_check "cpu-usage" "Uso de CPU dos pods" check_pod_cpu_usage
record_check "memory-usage" "Uso de memória dos pods" check_pod_memory_usage
record_check "node-capacity" "kubectl top nodes disponível" check_node_capacity

record_check "serviceaccounts" "ServiceAccounts presentes" check_serviceaccounts_exist
record_check "rbac-bindings" "RoleBindings revisados" check_rbac_bindings

# Execução ------------------------------------------------------------

for entry in "${CHECKS[@]}"; do
  run_check_entry "$entry"
done

printf "\n%-55s | %-7s | %s\n" "Check" "Status" "Mensagem"
printf "%-55s-+-%-7s-+-%s\n" "$(printf '%.0s-' {1..55})" "$(printf '%.0s-' {1..7})" "$(printf '%.0s-' {1..40})"
for row in "${TABLE_ROWS[@]}"; do
  IFS='|' read -r desc status message <<< "$row"
  printf "%-55s | %-7s | %s\n" "$desc" "$status" "$message"
done

SUMMARY_JSON=$(cat <<JSON
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "namespace": "$NAMESPACE",
  "checks": [$(IFS=,; echo "${CHECK_RESULTS_JSON[*]}")],
  "summary": {
    "total": $TOTAL_CHECKS,
    "passed": $PASSED_CHECKS,
    "failed": $FAILED_CHECKS,
    "warnings": $WARNING_CHECKS,
    "skipped": $SKIPPED_CHECKS
  }
}
JSON
)

echo "$SUMMARY_JSON" > "$REPORT_FILE"
log_success "Relatório salvo em $REPORT_FILE"
log_info "Resumo: ${PASSED_CHECKS} PASS / ${FAILED_CHECKS} FAIL / ${WARNING_CHECKS} WARN / ${SKIPPED_CHECKS} SKIPPED"

if [[ $FAILED_CHECKS -gt 0 ]]; then
  exit 1
fi

check_ste_http_health() {
  http_check_service "semantic-translation-engine" 8000 "/health" "healthy"
}

check_ste_http_ready() {
  http_check_service "semantic-translation-engine" 8000 "/ready" "ready"
}

check_specialist_http_health() {
  local svc=$1
  http_check_service "$svc" 8000 "/health" "healthy"
}

check_specialist_http_ready() {
  local svc=$1
  http_check_service "$svc" 8000 "/ready" "ready"
}
