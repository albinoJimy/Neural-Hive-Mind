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

NAMESPACE="fluxo-a"
RELEASE_NAME="gateway-intencoes"
FULLNAME_OVERRIDE=""
TIMEOUT=300
SKIP_CONNECTIVITY=0
VERBOSE=0
OUTPUT_FILE=""
FULLNAME=""

usage() {
  cat <<USAGE
Uso: $0 [opções]
  --namespace <ns>    Namespace do deployment (padrão: fluxo-a)
  --release <name>    Nome do release Helm (padrão: gateway-intencoes)
  --fullname <name>   Override manual do prefixo fullname (ConfigMap/Secret)
  --skip-connectivity Pula verificações de conectividade (DNS/TCP)
  --verbose           Mostra saída completa de cada check
  --output <file>     Salva relatório em JSON
  -h, --help          Exibe esta ajuda
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    --release)
      RELEASE_NAME="${2:-}"
      shift 2
      ;;
    --fullname)
      FULLNAME_OVERRIDE="${2:-}"
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
    --output)
      OUTPUT_FILE="${2:-}"
      shift 2
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
require_command helm
require_command curl
require_command jq

# Pré-validações para evitar avalanche de erros
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  log_error "Namespace '$NAMESPACE' não encontrado. Crie-o antes de executar este script (ex.: kubectl create namespace $NAMESPACE)."
  exit 1
fi

TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
CHECK_RESULTS=()
FAILED_DETAILS=()
POD_NAME=""
PF_PID=""
PORT_FORWARD_LOG=""

cleanup() {
  if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" >/dev/null 2>&1; then
    kill "$PF_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$PORT_FORWARD_LOG" && -f "$PORT_FORWARD_LOG" ]]; then
    rm -f "$PORT_FORWARD_LOG"
  fi
}

trap cleanup EXIT

escape_json() {
  printf '%s' "$1" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g'
}

record_result() {
  local status="$1"
  local name="$2"
  local error_msg="${3:-}"
  local escaped_name=$(escape_json "$name")
  if [[ "$status" == "PASS" ]]; then
    CHECK_RESULTS+=("{\"id\":$TOTAL_CHECKS,\"name\":\"$escaped_name\",\"status\":\"PASS\"}")
  elif [[ "$status" == "SKIPPED" ]]; then
    CHECK_RESULTS+=("{\"id\":$TOTAL_CHECKS,\"name\":\"$escaped_name\",\"status\":\"SKIPPED\"}")
  else
    local escaped_error=$(escape_json "$error_msg")
    CHECK_RESULTS+=("{\"id\":$TOTAL_CHECKS,\"name\":\"$escaped_name\",\"status\":\"FAIL\"}")
    FAILED_DETAILS+=("{\"id\":$TOTAL_CHECKS,\"name\":\"$escaped_name\",\"error\":\"$escaped_error\"}")
  fi
}

run_check() {
  local name="$1"
  local cmd="$2"
  TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
  log_info "[$TOTAL_CHECKS] $name"
  local tmp_out
  tmp_out=$(mktemp)
  if eval "$cmd" >"$tmp_out" 2>&1; then
    log_success "  ✓ PASS"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    if [[ $VERBOSE -eq 1 ]]; then
      sed 's/^/    /' "$tmp_out"
    fi
    record_result "PASS" "$name"
  else
    log_error "  ✗ FAIL"
    sed 's/^/    /' "$tmp_out"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    local err
    err=$(cat "$tmp_out")
    record_result "FAIL" "$name" "$err"
  fi
  rm -f "$tmp_out"
}

set_pod_name() {
  POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name="$RELEASE_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
}

start_port_forward() {
  if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" >/dev/null 2>&1; then
    return
  fi
  PORT_FORWARD_LOG=$(mktemp)
  kubectl port-forward -n "$NAMESPACE" svc/"$RELEASE_NAME" 8080:80 >"$PORT_FORWARD_LOG" 2>&1 &
  PF_PID=$!
  sleep 3
}

detect_fullname() {
  if [[ -n "$FULLNAME_OVERRIDE" ]]; then
    FULLNAME="$FULLNAME_OVERRIDE"
    return
  fi

  local tmp override
  tmp=$(mktemp)
  if helm get values "$RELEASE_NAME" -n "$NAMESPACE" -o json >"$tmp" 2>/dev/null; then
    override=$(jq -r '.fullnameOverride // empty' "$tmp")
    if [[ -n "$override" && "$override" != "null" ]]; then
      FULLNAME="${override}-${RELEASE_NAME}"
    else
      FULLNAME="$RELEASE_NAME"
    fi
  else
    FULLNAME="$RELEASE_NAME"
  fi
  rm -f "$tmp"
}

# Section 1
run_check "Namespace $NAMESPACE existe" "kubectl get namespace $NAMESPACE"
run_check "Release Helm $RELEASE_NAME instalado" "helm list -n $NAMESPACE | grep -q $RELEASE_NAME"
run_check "Release $RELEASE_NAME com status deployed" "helm status $RELEASE_NAME -n $NAMESPACE | grep -q 'STATUS: deployed'"

detect_fullname
log_info "Usando prefixo '$FULLNAME' para validar ConfigMap e Secret."

# Section 2
run_check "Deployment $RELEASE_NAME existe" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE"
run_check "Deployment com replicas desejadas = 1" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.spec.replicas}' | grep -q '^1$'"
run_check "Deployment com replicas disponíveis = 1" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.status.availableReplicas}' | grep -q '^1$'"
run_check "Service $RELEASE_NAME existe" "kubectl get svc $RELEASE_NAME -n $NAMESPACE"
run_check "Service $RELEASE_NAME possui endpoints" "kubectl get endpoints $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.subsets[0].addresses[0].ip}'"
run_check "ConfigMap do gateway existe" "kubectl get configmap ${FULLNAME}-config -n $NAMESPACE"
run_check "Secret do gateway existe" "kubectl get secret ${FULLNAME}-secret -n $NAMESPACE"
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
log_info "[$TOTAL_CHECKS] ServiceMonitor (opcional)"
if kubectl get servicemonitor -n "$NAMESPACE" "$RELEASE_NAME" >/dev/null 2>&1; then
  log_success "  ✓ PASS"
  PASSED_CHECKS=$((PASSED_CHECKS + 1))
  record_result "PASS" "ServiceMonitor (opcional)"
else
  log_warning "ServiceMonitor não encontrado (ok se observability desabilitado)"
  PASSED_CHECKS=$((PASSED_CHECKS + 1))
  record_result "SKIPPED" "ServiceMonitor (opcional)"
fi

# Section 3: Pod checks
set_pod_name
run_check "Pod do gateway existe" "[[ -n \"$POD_NAME\" ]]"
set_pod_name
run_check "Pod em status Running" "kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.phase}' | grep -q Running"
run_check "Pod Ready 1/1" "kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].ready}' | grep -q true"
run_check "Pod com menos de 5 restarts" "kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].restartCount}' | awk '{exit !(\$1 < 5)}'"
run_check "Pod age superior a 60s" "kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.startTime}' | xargs -I{} bash -c '[[ $(( $(date +%s) - $(date -d {} +%s) )) -gt 60 ]]'"
run_check "Quantidade de containers = 1" "kubectl get pod $POD_NAME -n $NAMESPACE -o json | jq '.spec.containers | length == 1' -e"

# Section 4: Logs
run_check "Logs contêm Application startup complete" "kubectl logs $POD_NAME -n $NAMESPACE | grep -q 'Application startup complete'"
run_check "Logs contêm Uvicorn running" "kubectl logs $POD_NAME -n $NAMESPACE | grep -q 'Uvicorn running on'"
run_check "Logs sem CRITICAL/FATAL" "! kubectl logs $POD_NAME -n $NAMESPACE | grep -E 'CRITICAL|FATAL'"
run_check "Logs contêm Kafka producer initialized" "kubectl logs $POD_NAME -n $NAMESPACE | grep -q 'Kafka producer initialized'"
run_check "Logs contêm Redis client initialized" "kubectl logs $POD_NAME -n $NAMESPACE | grep -q 'Redis client initialized'"

# Section 5: HTTP endpoints
start_port_forward
run_check "Health endpoint retorna 200" "curl -sf http://localhost:8080/health > /dev/null"
run_check "Health status = healthy" "curl -s http://localhost:8080/health | jq -e '.status==\"healthy\"' > /dev/null"
run_check "Status indica kafka_producer_ready" "curl -s http://localhost:8080/status | jq -e '.kafka_producer_ready==true' > /dev/null"
run_check "Status indica nlu_pipeline_ready" "curl -s http://localhost:8080/status | jq -e '.nlu_pipeline_ready==true' > /dev/null"

# Section 6: Connectivity
if [[ $SKIP_CONNECTIVITY -eq 1 ]]; then
  log_warning "Checks de conectividade pulados por solicitação"
else
  run_check "Pod resolve DNS do Kafka" "kubectl exec -n $NAMESPACE $POD_NAME -- nslookup neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local"
  run_check "Pod conecta ao Kafka (porta 9092)" "kubectl exec -n $NAMESPACE $POD_NAME -- timeout 5 bash -c 'cat < /dev/null > /dev/tcp/neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local/9092'"
  run_check "Pod conecta ao Redis (porta 6379)" "kubectl exec -n $NAMESPACE $POD_NAME -- timeout 5 bash -c 'cat < /dev/null > /dev/tcp/neural-hive-cache.redis-cluster.svc.cluster.local/6379'"
fi

# Section 7: Configuração
run_check "ConfigMap contém KAFKA_BOOTSTRAP_SERVERS" "kubectl get configmap ${FULLNAME}-config -n $NAMESPACE -o jsonpath='{.data.KAFKA_BOOTSTRAP_SERVERS}' | grep -q 'kafka'"
run_check "ConfigMap contém REDIS_CLUSTER_NODES" "kubectl get configmap ${FULLNAME}-config -n $NAMESPACE -o jsonpath='{.data.REDIS_CLUSTER_NODES}' | grep -q 'redis'"
run_check "Secret contém jwtSecretKey" "kubectl get secret ${FULLNAME}-secret -n $NAMESPACE -o jsonpath='{.data.jwt-secret-key}' | grep -q '.'"
run_check "Image pull policy = Never" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].imagePullPolicy}' | grep -q Never"

# Section 8: Recursos
run_check "CPU requests configurado" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' | grep -q 'm'"
run_check "Memory requests configurado" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' | grep -q 'Gi'"
run_check "CPU limits configurado" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' | grep -q 'm'"
run_check "Memory limits configurado" "kubectl get deployment $RELEASE_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' | grep -q 'Gi'"

PERCENT=0
if [[ $TOTAL_CHECKS -gt 0 ]]; then
  PERCENT=$(( PASSED_CHECKS * 100 / TOTAL_CHECKS ))
fi

echo ""
echo "========================================"
echo "  GATEWAY DEPLOYMENT VALIDATION REPORT"
echo "========================================"
echo ""
echo "Total checks: $TOTAL_CHECKS"
echo "Passed: $PASSED_CHECKS (${PERCENT}%)"
echo "Failed: $FAILED_CHECKS"
echo ""

if [[ $FAILED_CHECKS -eq 0 ]]; then
  log_success "All checks passed! Gateway is ready."
else
  log_error "$FAILED_CHECKS checks failed. Revise os detalhes acima."
fi

if [[ -n "$OUTPUT_FILE" ]]; then
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  join_by() {
    local IFS="$1"; shift; echo "$*"
  }
  CHECKS_JSON=$(join_by , "${CHECK_RESULTS[@]}")
  FAILED_JSON=$(join_by , "${FAILED_DETAILS[@]}")
  cat <<JSON > "$OUTPUT_FILE"
{
  "timestamp": "$TS",
  "namespace": "$NAMESPACE",
  "release": "$RELEASE_NAME",
  "total_checks": $TOTAL_CHECKS,
  "passed": $PASSED_CHECKS,
  "failed": $FAILED_CHECKS,
  "checks": [${CHECKS_JSON}],
  "failed_checks": [${FAILED_JSON}]
}
JSON
  log_info "Relatório salvo em $OUTPUT_FILE"
fi

if [[ $FAILED_CHECKS -ne 0 ]]; then
  exit 1
fi
