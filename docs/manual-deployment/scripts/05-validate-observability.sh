#!/usr/bin/env bash
# Script de validação da stack de observabilidade
# Uso: ./05-validate-observability.sh [--verbose]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
NAMESPACE="observability"
REPORT_FILE="${PROJECT_ROOT}/.tmp/observability-validation-report.txt"
VERBOSE=false
PASSED=0
FAILED=0
WARNINGS=0
CHECK_MESSAGE=""
REPORT_LINES=()

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
  cat <<'USO'
Uso: 05-validate-observability.sh [--verbose]

Executa 25 verificações automatizadas para Prometheus, Grafana e Jaeger.
USO
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --verbose) VERBOSE=true; shift ;;
      -h|--help) usage; exit 0 ;;
      *) log_error "Argumento desconhecido: $1"; usage; exit 1 ;;
    esac
  done
}

check_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log_error "Comando obrigatório ausente: $1"
    exit 1
  fi
}

prepare_environment() {
  mkdir -p "${PROJECT_ROOT}/.tmp"
  : >"${REPORT_FILE}"
}

append_report() {
  REPORT_LINES+=("$1 | $2 | $3")
}

run_check() {
  local name="$1" func="$2"
  CHECK_MESSAGE=""
  $VERBOSE && log "Executando: ${name}"
  if "$func"; then
    ((PASSED++))
    local message="$name"
    [[ -n "$CHECK_MESSAGE" ]] && message+=" - $CHECK_MESSAGE"
    log_success "$message"
    append_report "PASS" "$name" "${CHECK_MESSAGE:-OK}"
  else
    local rc=$?
    if [[ $rc -eq 2 ]]; then
      ((WARNINGS++))
      local warn_message="$name"
      [[ -n "$CHECK_MESSAGE" ]] && warn_message+=" - $CHECK_MESSAGE"
      log_warn "$warn_message"
      append_report "WARN" "$name" "${CHECK_MESSAGE:-Verificar manualmente}"
    else
      ((FAILED++))
      local err_message="$name"
      [[ -n "$CHECK_MESSAGE" ]] && err_message+=" - $CHECK_MESSAGE"
      log_error "$err_message"
      append_report "FAIL" "$name" "${CHECK_MESSAGE:-Falha}" 
    fi
  fi
}

validate_namespace() {
  local labels
  labels=$(kubectl get ns "$NAMESPACE" -o jsonpath='{.metadata.labels}' 2>/dev/null) || { CHECK_MESSAGE="Namespace não encontrado"; return 1; }
  if [[ "$labels" == *"neural-hive.io/phase"* ]]; then
    CHECK_MESSAGE="Labels detectados"
    return 0
  fi
  CHECK_MESSAGE="Labels neural-hive ausentes"
  return 1
}

validate_prometheus_operator() {
  local pods
  pods=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=prometheus-operator --no-headers 2>/dev/null) || true
  if [[ -z "$pods" ]]; then
    CHECK_MESSAGE="Prometheus Operator não encontrado"
    return 1
  fi
  if echo "$pods" | awk '{print $3}' | grep -vq "Running"; then
    CHECK_MESSAGE="Alguns pods não estão Running"
    return 1
  fi
  CHECK_MESSAGE="Operator Running"
  return 0
}

validate_prometheus_server() {
  if ! kubectl get prometheus -n "$NAMESPACE" >/dev/null 2>&1; then
    CHECK_MESSAGE="CR Prometheus não encontrado"
    return 1
  fi
  if ! kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=prometheus -n "$NAMESPACE" --timeout=30s >/dev/null 2>&1; then
    CHECK_MESSAGE="Pods Prometheus não prontos"
    return 1
  fi
  local pvc
  pvc=$(kubectl get pvc -n "$NAMESPACE" | grep prometheus || true)
  if [[ "$pvc" != *Bound* ]]; then
    CHECK_MESSAGE="PVC Prometheus não Bound"
    return 1
  fi
  CHECK_MESSAGE="Prometheus pronto"
  return 0
}

validate_alertmanager() {
  if ! kubectl get alertmanager -n "$NAMESPACE" >/dev/null 2>&1; then
    CHECK_MESSAGE="CR Alertmanager não encontrado"
    return 1
  fi
  if ! kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=alertmanager -n "$NAMESPACE" --timeout=30s >/dev/null 2>&1; then
    CHECK_MESSAGE="Pods Alertmanager não prontos"
    return 1
  fi
  CHECK_MESSAGE="Alertmanager pronto"
  return 0
}

validate_node_exporter() {
  local desired ready
  desired=$(kubectl get daemonset -n "$NAMESPACE" -l app.kubernetes.io/name=node-exporter -o jsonpath='{.items[0].status.desiredNumberScheduled}' 2>/dev/null || echo 0)
  ready=$(kubectl get daemonset -n "$NAMESPACE" -l app.kubernetes.io/name=node-exporter -o jsonpath='{.items[0].status.numberReady}' 2>/dev/null || echo 0)
  if [[ "$desired" == "$ready" && "$desired" != "0" ]]; then
    CHECK_MESSAGE="${ready}/${desired} prontos"
    return 0
  fi
  CHECK_MESSAGE="DaemonSet incompleto (${ready}/${desired})"
  return 1
}

validate_kube_state_metrics() {
  local ready desired
  ready=$(kubectl get deploy -n "$NAMESPACE" -l app.kubernetes.io/name=kube-state-metrics -o jsonpath='{.items[0].status.readyReplicas}' 2>/dev/null || echo 0)
  desired=$(kubectl get deploy -n "$NAMESPACE" -l app.kubernetes.io/name=kube-state-metrics -o jsonpath='{.items[0].status.replicas}' 2>/dev/null || echo 0)
  if [[ "$ready" == "$desired" && "$desired" != "0" ]]; then
    CHECK_MESSAGE="${ready}/${desired} replicas"
    return 0
  fi
  CHECK_MESSAGE="Deployment não pronto"
  return 1
}

validate_grafana() {
  if ! kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=grafana -n "$NAMESPACE" --timeout=30s >/dev/null 2>&1; then
    CHECK_MESSAGE="Pod Grafana não pronto"
    return 1
  fi
  local pvc
  pvc=$(kubectl get pvc -n "$NAMESPACE" | grep grafana || true)
  if [[ "$pvc" != *Bound* ]]; then
    CHECK_MESSAGE="PVC Grafana não Bound"
    return 1
  fi
  if ! kubectl get secret -n "$NAMESPACE" neural-hive-grafana >/dev/null 2>&1; then
    CHECK_MESSAGE="Secret admin ausente"
    return 1
  fi
  CHECK_MESSAGE="Grafana operacional"
  return 0
}

validate_jaeger() {
  if ! kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=jaeger -n "$NAMESPACE" --timeout=30s >/dev/null 2>&1; then
    CHECK_MESSAGE="Pod Jaeger não pronto"
    return 1
  fi
  local svc
  svc=$(kubectl get svc -n "$NAMESPACE" neural-hive-jaeger -o jsonpath='{.spec.ports[*].port}' 2>/dev/null || true)
  if [[ "$svc" != *16686* ]]; then
    CHECK_MESSAGE="Portas Jaeger ausentes"
    return 1
  fi
  CHECK_MESSAGE="Jaeger operacional"
  return 0
}

validate_services() {
  for svc in neural-hive-prometheus-kube-prometheus-prometheus neural-hive-prometheus-kube-prometheus-alertmanager neural-hive-grafana neural-hive-jaeger; do
    if ! kubectl get svc -n "$NAMESPACE" "$svc" >/dev/null 2>&1; then
      CHECK_MESSAGE="Service ${svc} ausente"
      return 1
    fi
  done
  CHECK_MESSAGE="Serviços principais presentes"
  return 0
}

validate_servicemonitors() {
  local list count
  if ! list=$(kubectl get servicemonitor -A -l neural.hive/metrics=enabled --no-headers 2>/dev/null); then
    CHECK_MESSAGE="Falha ao listar ServiceMonitors"
    return 1
  fi
  count=$(printf "%s\n" "$list" | awk 'NF{c++} END{print c+0}')
  if [[ "${count}" -ge 5 ]]; then
    CHECK_MESSAGE="${count} ServiceMonitors detectados"
    return 0
  fi
  CHECK_MESSAGE="Apenas ${count} ServiceMonitors encontrados"
  return 1
}

start_port_forward() {
  local resource="$1" mapping="$2"
  local log_file
  log_file=$(mktemp)
  kubectl port-forward -n "$NAMESPACE" "${resource}" "$mapping" >"${log_file}" 2>&1 &
  local pid=$!
  sleep 5
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    CHECK_MESSAGE="Falha no port-forward (${resource})"
    cat "$log_file" >&2
    rm -f "$log_file"
    return 1
  fi
  echo "$pid $log_file"
}

stop_port_forward() {
  local pid="$1" log_file="$2"
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true
  rm -f "$log_file"
}

validate_prometheus_targets() {
  local pf
  pf=$(start_port_forward svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090) || return 1
  local pid log_file
  pid=$(echo "$pf" | awk '{print $1}')
  log_file=$(echo "$pf" | awk '{print $2}')
  local targets
  targets=$(curl -s http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets | length' 2>/dev/null || echo 0)
  stop_port_forward "$pid" "$log_file"
  if [[ "$targets" -gt 0 ]]; then
    CHECK_MESSAGE="${targets} targets ativos"
    return 0
  fi
  CHECK_MESSAGE="Nenhum target ativo"
  return 1
}

validate_prometheus_metrics() {
  local pf
  pf=$(start_port_forward svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090) || return 1
  local pid log_file
  pid=$(echo "$pf" | awk '{print $1}')
  log_file=$(echo "$pf" | awk '{print $2}')
  local result
  result=$(curl -s 'http://127.0.0.1:9090/api/v1/query?query=up' | jq '.data.result | length' 2>/dev/null || echo 0)
  stop_port_forward "$pid" "$log_file"
  if [[ "$result" -gt 0 ]]; then
    CHECK_MESSAGE="Consulta up retornou ${result} séries"
    return 0
  fi
  CHECK_MESSAGE="Query up vazia"
  return 1
}

get_grafana_password() {
  kubectl get secret -n "$NAMESPACE" neural-hive-grafana -o jsonpath='{.data.admin-password}' | base64 -d
}

validate_grafana_datasources() {
  local password pf pid log_file
  password=$(get_grafana_password 2>/dev/null || true)
  if [[ -z "$password" ]]; then
    CHECK_MESSAGE="Não foi possível recuperar senha"
    return 1
  fi
  pf=$(start_port_forward svc/neural-hive-grafana 3000:80) || return 1
  pid=$(echo "$pf" | awk '{print $1}')
  log_file=$(echo "$pf" | awk '{print $2}')
  local ds
  ds=$(curl -s -u "admin:${password}" http://127.0.0.1:3000/api/datasources | jq -r '.[].name' 2>/dev/null || true)
  stop_port_forward "$pid" "$log_file"
  if [[ "$ds" == *Prometheus* && "$ds" == *Jaeger* ]]; then
    CHECK_MESSAGE="Datasources Prometheus e Jaeger detectados"
    return 0
  fi
  CHECK_MESSAGE="Datasources ausentes"
  return 1
}

validate_grafana_health() {
  local pw pf pid log_file status
  pw=$(get_grafana_password 2>/dev/null || true)
  [[ -z "$pw" ]] && { CHECK_MESSAGE="Senha indisponível"; return 1; }
  pf=$(start_port_forward svc/neural-hive-grafana 4000:80) || return 1
  pid=$(echo "$pf" | awk '{print $1}')
  log_file=$(echo "$pf" | awk '{print $2}')
  status=$(curl -s -o /tmp/grafana-health.txt -w '%{http_code}' -u "admin:${pw}" http://127.0.0.1:4000/api/health || echo 0)
  stop_port_forward "$pid" "$log_file"
  rm -f /tmp/grafana-health.txt
  if [[ "$status" == "200" ]]; then
    CHECK_MESSAGE="API health OK"
    return 0
  fi
  CHECK_MESSAGE="API health retornou ${status}"
  return 1
}

validate_jaeger_health() {
  local pf pid log_file code
  pf=$(start_port_forward svc/neural-hive-jaeger 16686:16686) || return 1
  pid=$(echo "$pf" | awk '{print $1}')
  log_file=$(echo "$pf" | awk '{print $2}')
  code=$(curl -s -o /tmp/jaeger-ui.html -w '%{http_code}' http://127.0.0.1:16686 || echo 0)
  stop_port_forward "$pid" "$log_file"
  rm -f /tmp/jaeger-ui.html
  if [[ "$code" == "200" ]]; then
    CHECK_MESSAGE="UI acessível"
    return 0
  fi
  CHECK_MESSAGE="UI respondeu ${code}"
  return 1
}

validate_jaeger_otlp() {
  local ports
  ports=$(kubectl get svc -n "$NAMESPACE" neural-hive-jaeger -o json | jq '.spec.ports[].port' 2>/dev/null || true)
  if [[ "$ports" == *4317* && "$ports" == *4318* ]]; then
    CHECK_MESSAGE="Portas OTLP expostas"
    return 0
  fi
  CHECK_MESSAGE="Portas OTLP ausentes"
  return 1
}

validate_storage() {
  local pvcs pending
  if ! pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null); then
    CHECK_MESSAGE="Falha ao listar PVCs"
    return 1
  fi
  pending=$(printf "%s\n" "$pvcs" | awk '$2 != "Bound"{c++} END{print c+0}')
  if [[ "$pending" == "0" ]]; then
    CHECK_MESSAGE="Todos os PVCs Bound"
    return 0
  fi
  CHECK_MESSAGE="${pending} PVCs não Bound"
  return 1
}

validate_resources() {
  local oom
  oom=$(kubectl get pods -n "$NAMESPACE" -o json | jq '[.items[] | select(.status.containerStatuses[]?.lastState.terminated.reason=="OOMKilled")] | length' 2>/dev/null || echo 0)
  if [[ "$oom" == "0" ]]; then
    CHECK_MESSAGE="Sem OOMKilled"
    return 0
  fi
  CHECK_MESSAGE="${oom} pods com OOMKilled"
  return 1
}

validate_logs() {
  local errors
  errors=$(kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/name=prometheus --tail=100 2>/dev/null | grep -iE 'error|fatal' || true)
  if [[ -z "$errors" ]]; then
    CHECK_MESSAGE="Sem erros críticos"
    return 0
  fi
  CHECK_MESSAGE="Logs contêm possíveis erros"
  return 2
}

validate_connectivity() {
  local cmd
  cmd="nc -vz neural-hive-prometheus-kube-prometheus-prometheus 9090 && nc -vz neural-hive-grafana 80 && nc -vz neural-hive-jaeger 16686"
  if kubectl run net-debug-obs --rm -i --restart=Never --image=busybox -n "$NAMESPACE" -- /bin/sh -c "$cmd" >/dev/null 2>&1; then
    CHECK_MESSAGE="Netcat para serviços bem-sucedido"
    return 0
  fi
  CHECK_MESSAGE="Falha na conectividade interna"
  return 1
}

validate_rbac() {
  if kubectl get sa,role,rolebinding -n "$NAMESPACE" >/dev/null 2>&1; then
    CHECK_MESSAGE="SA/Role/RoleBinding listados"
    return 0
  fi
  CHECK_MESSAGE="Falha ao listar RBAC"
  return 1
}

validate_network_policies() {
  local count
  count=$(kubectl get networkpolicy -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$count" -eq 0 ]]; then
    CHECK_MESSAGE="Nenhuma NetworkPolicy (warning)"
    return 2
  fi
  CHECK_MESSAGE="${count} NetworkPolicies"
  return 0
}

validate_pod_security() {
  local enforce
  enforce=$(kubectl get ns "$NAMESPACE" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || true)
  if [[ "$enforce" == "baseline" || "$enforce" == "restricted" ]]; then
    CHECK_MESSAGE="PSS ${enforce} aplicado"
    return 0
  fi
  CHECK_MESSAGE="Label PSS ausente"
  return 1
}

validate_exemplars() {
  local size
  size=$(kubectl get prometheus -n "$NAMESPACE" -o jsonpath='{.items[0].spec.exemplars.maxSize}' 2>/dev/null || echo 0)
  if [[ "$size" -gt 0 ]]; then
    CHECK_MESSAGE="exemplars.maxSize=${size}"
    return 0
  fi
  CHECK_MESSAGE="Exemplars não configurados"
  return 1
}

validate_integration() {
  local cfg
  cfg=$(kubectl get configmap -n "$NAMESPACE" -o name | grep grafana-datasources || true)
  if [[ -n "$cfg" ]]; then
    CHECK_MESSAGE="ConfigMap ${cfg} presente"
    return 0
  fi
  CHECK_MESSAGE="ConfigMap grafana-datasources ausente"
  return 1
}

write_report() {
  {
    echo "Observability Validation Report - $(date)"
    echo "Namespace: ${NAMESPACE}"
    echo "Resumo: ${PASSED} passados, ${FAILED} falharam, ${WARNINGS} avisos"
    echo ""
    for line in "${REPORT_LINES[@]}"; do
      echo "- ${line}"
    done
  } >"${REPORT_FILE}"
  log "Relatório disponível em ${REPORT_FILE}"
}

main() {
  parse_args "$@"
  check_command kubectl
  check_command jq
  check_command curl
  prepare_environment

  set +e
  run_check "Namespace observability" validate_namespace
  run_check "Prometheus Operator" validate_prometheus_operator
  run_check "Prometheus Server" validate_prometheus_server
  run_check "Alertmanager" validate_alertmanager
  run_check "Node Exporter" validate_node_exporter
  run_check "Kube State Metrics" validate_kube_state_metrics
  run_check "Grafana" validate_grafana
  run_check "Jaeger" validate_jaeger
  run_check "Serviços principais" validate_services
  run_check "ServiceMonitors" validate_servicemonitors
  run_check "Prometheus targets" validate_prometheus_targets
  run_check "Prometheus query" validate_prometheus_metrics
  run_check "Grafana datasources" validate_grafana_datasources
  run_check "Grafana health" validate_grafana_health
  run_check "Jaeger UI" validate_jaeger_health
  run_check "Jaeger OTLP" validate_jaeger_otlp
  run_check "PVCs" validate_storage
  run_check "Recursos/OOM" validate_resources
  run_check "Logs críticos" validate_logs
  run_check "Conectividade interna" validate_connectivity
  run_check "RBAC" validate_rbac
  run_check "NetworkPolicies" validate_network_policies
  run_check "Pod Security" validate_pod_security
  run_check "Exemplars" validate_exemplars
  run_check "Integração Grafana" validate_integration
  set -e

  write_report

  local exit_code=0
  if [[ $FAILED -gt 0 ]]; then
    exit_code=1
  elif [[ $WARNINGS -gt 0 ]]; then
    exit_code=2
  fi
  exit $exit_code
}

main "$@"
