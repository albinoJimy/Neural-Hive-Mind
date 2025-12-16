#!/usr/bin/env bash
# Script para preparar valores customizados de Prometheus, Grafana e Jaeger
# Uso: ./04-prepare-observability-values.sh [prometheus|grafana|jaeger|all]

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CHARTS_DIR="${PROJECT_ROOT}/helm-charts"
ENV_DIR="${PROJECT_ROOT}/environments/local"
CONFIG_FILE="${OBSERVABILITY_CONFIG:-${ENV_DIR}/observability-config.yaml}"
OUTPUT_DIR="${PROJECT_ROOT}/.tmp/observability-values"
COMPONENTS=(prometheus grafana jaeger)

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Validation parameters (loaded from config)
WAIT_TIMEOUT=600
RETRY_ATTEMPTS=3
HEALTH_CHECK_INTERVAL=10

trap 'log_error "Execução interrompida (linha ${LINENO})."' ERR

usage() {
  cat <<'USO'
Uso: 04-prepare-observability-values.sh [componentes...]

Componentes suportados: prometheus, grafana, jaeger, all
Se nenhum componente for informado, todos serão processados.
USO
}

config_get() {
  local path="$1"
  local default="${2:-}"
  local value
  value=$(yq -r "(${path}) // empty" "$CONFIG_FILE" 2>/dev/null || true)
  if [[ -z "$value" || "$value" == "null" ]]; then
    echo "$default"
  else
    echo "$value"
  fi
}

config_list() {
  local path="$1"
  yq -r "(${path}) // [] | .[]" "$CONFIG_FILE" 2>/dev/null || true
}

load_validation_params() {
  local component="${1:-}"
  local global_timeout global_attempts global_interval

  # Load global validation params
  global_timeout=$(config_get '.validation.wait_timeout' '')
  global_attempts=$(config_get '.validation.retry_attempts' '')
  global_interval=$(config_get '.validation.health_check_interval' '')

  # Load component-specific params with fallback to global
  if [[ -n "$component" ]]; then
    WAIT_TIMEOUT=$(config_get ".${component}.validation.wait_timeout" "${global_timeout:-600}")
    RETRY_ATTEMPTS=$(config_get ".${component}.validation.retry_attempts" "${global_attempts:-3}")
    HEALTH_CHECK_INTERVAL=$(config_get ".${component}.validation.health_check_interval" "${global_interval:-10}")
  else
    WAIT_TIMEOUT="${global_timeout:-600}"
    RETRY_ATTEMPTS="${global_attempts:-3}"
    HEALTH_CHECK_INTERVAL="${global_interval:-10}"
  fi

  # Validate params are positive integers within reasonable bounds
  if ! [[ "$WAIT_TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$WAIT_TIMEOUT" -lt 60 ]]; then
    log_warn "Invalid wait_timeout ($WAIT_TIMEOUT), using default: 600"
    WAIT_TIMEOUT=600
  fi

  if ! [[ "$RETRY_ATTEMPTS" =~ ^[0-9]+$ ]] || [[ "$RETRY_ATTEMPTS" -lt 1 ]]; then
    log_warn "Invalid retry_attempts ($RETRY_ATTEMPTS), using default: 3"
    RETRY_ATTEMPTS=3
  fi

  if ! [[ "$HEALTH_CHECK_INTERVAL" =~ ^[0-9]+$ ]] || [[ "$HEALTH_CHECK_INTERVAL" -lt 1 ]]; then
    log_warn "Invalid health_check_interval ($HEALTH_CHECK_INTERVAL), using default: 10"
    HEALTH_CHECK_INTERVAL=10
  fi
}

retry_with_timeout() {
  local cmd="$1"
  local description="${2:-command}"
  local attempt=1
  local start_time end_time elapsed

  start_time=$(date +%s)

  while [[ $attempt -le $RETRY_ATTEMPTS ]]; do
    end_time=$(date +%s)
    elapsed=$((end_time - start_time))

    if [[ $elapsed -ge $WAIT_TIMEOUT ]]; then
      log_error "Timeout (${WAIT_TIMEOUT}s) exceeded for: $description"
      return 1
    fi

    if [[ $attempt -gt 1 ]]; then
      log "Retry attempt $attempt/$RETRY_ATTEMPTS for: $description"
    fi

    if timeout $((WAIT_TIMEOUT - elapsed)) bash -c "$cmd" 2>/dev/null; then
      return 0
    fi

    if [[ $attempt -lt $RETRY_ATTEMPTS ]]; then
      log_warn "Attempt $attempt failed, waiting ${HEALTH_CHECK_INTERVAL}s before retry..."
      sleep "$HEALTH_CHECK_INTERVAL"
    fi

    ((attempt++))
  done

  log_error "Failed after $RETRY_ATTEMPTS attempts: $description"
  return 1
}

require_commands() {
  for cmd in kubectl helm yq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Comando obrigatório não encontrado: $cmd"
      exit 1
    fi
  done
  log_success "kubectl, helm e yq encontrados."
}

validate_cluster() {
  log "Validating cluster connectivity (timeout=${WAIT_TIMEOUT}s, retries=${RETRY_ATTEMPTS})..."
  if ! retry_with_timeout "kubectl cluster-info" "cluster connectivity check"; then
    log_error "Não foi possível conectar ao cluster Kubernetes após ${RETRY_ATTEMPTS} tentativas."
    exit 1
  fi
  log_success "Cluster acessível: $(kubectl config current-context)"
}

STORAGE_CLASS=""

detect_storage_class() {
  local from_config from_cluster
  from_config=$(config_get '.storage.class' '')
  if [[ -n "$from_config" ]]; then
    STORAGE_CLASS="$from_config"
    log "Using storage class from config: ${STORAGE_CLASS}"
    return
  fi

  log "Detecting default storage class from cluster (timeout=${WAIT_TIMEOUT}s, retries=${RETRY_ATTEMPTS})..."
  if retry_with_timeout "kubectl get sc -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class==\"true\")].metadata.name}' >/dev/null 2>&1" "storage class detection"; then
    from_cluster=$(kubectl get sc -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}' 2>/dev/null || true)
    if [[ -n "$from_cluster" ]]; then
      STORAGE_CLASS="$from_cluster"
      log_success "Detected default storage class: ${STORAGE_CLASS}"
      return
    fi
  fi

  STORAGE_CLASS="local-path"
  log_warn "No default storage class found, using fallback: ${STORAGE_CLASS}"
}

ensure_output_dir() {
  mkdir -p "$OUTPUT_DIR"
}

apply_profile() {
  local file="$1"
  local path="$2"
  local profile="$3"
  local cpu_req mem_req cpu_lim mem_lim
  cpu_req=$(config_get ".resources.${profile}.requests.cpu" '')
  mem_req=$(config_get ".resources.${profile}.requests.memory" '')
  cpu_lim=$(config_get ".resources.${profile}.limits.cpu" '')
  mem_lim=$(config_get ".resources.${profile}.limits.memory" '')
  if [[ -z "$cpu_req" || -z "$mem_req" || -z "$cpu_lim" || -z "$mem_lim" ]]; then
    log_warn "Perfil ${profile} inválido para ${path}."
    return
  fi

  # Apply with retry for transient failures (e.g., file locks)
  retry_with_timeout "yq -i \"${path}.requests.cpu = \\\"${cpu_req}\\\"\" \"$file\"" "applying cpu request to ${path}" || {
    log_error "Failed to apply cpu request for ${profile} at ${path}"
    return 1
  }
  retry_with_timeout "yq -i \"${path}.requests.memory = \\\"${mem_req}\\\"\" \"$file\"" "applying memory request to ${path}" || {
    log_error "Failed to apply memory request for ${profile} at ${path}"
    return 1
  }
  retry_with_timeout "yq -i \"${path}.limits.cpu = \\\"${cpu_lim}\\\"\" \"$file\"" "applying cpu limit to ${path}" || {
    log_error "Failed to apply cpu limit for ${profile} at ${path}"
    return 1
  }
  retry_with_timeout "yq -i \"${path}.limits.memory = \\\"${mem_lim}\\\"\" \"$file\"" "applying memory limit to ${path}" || {
    log_error "Failed to apply memory limit for ${profile} at ${path}"
    return 1
  }
}

write_additional_scrape_configs() {
  local file="$1"
  local namespaces="$2"
  local interval="$3"
  local tmp_file ns_block=""
  tmp_file=$(mktemp)
  while IFS= read -r ns; do
    [[ -z "$ns" ]] && continue
    ns_block+="          - ${ns}"$'\n'
  done <<< "$namespaces"
  cat <<EOF_PROM >"${tmp_file}"
- job_name: neural-hive-services
  scrape_interval: ${interval}
  honor_labels: true
  kubernetes_sd_configs:
    - role: endpoints
      namespaces:
        names:
${ns_block%%$'\n'}
  relabel_configs:
    - source_labels: [__meta_kubernetes_service_label_neural\.hive/metrics]
      regex: enabled
      action: keep
    - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
      regex: true
      action: keep
    - source_labels: [__meta_kubernetes_endpoint_port_name]
      target_label: port_name
    - source_labels: [__meta_kubernetes_namespace]
      target_label: namespace
    - source_labels: [__meta_kubernetes_service_name]
      target_label: service
    - source_labels: [__meta_kubernetes_pod_name]
      target_label: pod
EOF_PROM
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.additionalScrapeConfigs = load(\"${tmp_file}\")" "$file"
  rm -f "$tmp_file"
}

random_password() {
  python3 - <<'PY'
import secrets
alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
print("".join(secrets.choice(alphabet) for _ in range(20)))
PY
}

process_prometheus() {
  local base="${CHARTS_DIR}/prometheus-stack/values-local.yaml"
  local output="${OUTPUT_DIR}/prometheus-values-local.yaml"
  cp "$base" "$output"

  local prometheus_profile alert_profile operator_profile ksm_profile ne_profile
  prometheus_profile=$(config_get '.prometheus.resources' 'medium')
  alert_profile=$(config_get '.prometheus.alertmanager_resources' 'small')
  operator_profile=$(config_get '.prometheus.operator_resources' 'small')
  ksm_profile=$(config_get '.prometheus.kube_state_metrics_resources' 'small')
  ne_profile=$(config_get '.prometheus.node_exporter_resources' 'small')

  yq -i '.global.domain = "neural-hive.local"' "$output"
  yq -i '.global.environment = "local"' "$output"
  yq -i '.global.cluster = "kubeadm-local"' "$output"

  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.replicas = $(config_get '.prometheus.replicas' 1)" "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.retention = \"$(config_get '.prometheus.retention' '7d')\"" "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.retentionSize = \"$(config_get '.prometheus.retention_size' '10Gi')\"" "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName = \"${STORAGE_CLASS}\"" "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage = \"$(config_get '.prometheus.storage_size' '20Gi')\"" "$output"
  yq -i '.kube-prometheus-stack.prometheus.prometheusSpec.resources = {}' "$output"
  apply_profile "$output" '.kube-prometheus-stack.prometheus.prometheusSpec.resources' "$prometheus_profile"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.serviceMonitorSelector.matchLabels = {\"neural.hive/metrics\": \"enabled\"}" "$output"
  yq -i '.kube-prometheus-stack.prometheus.prometheusSpec.serviceMonitorNamespaceSelector = {}' "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.remoteWrite = []" "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.exemplars.maxSize = $(config_get '.prometheus.exemplars.max_size' 10000)" "$output"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.enableAdminAPI = true" "$output"

  apply_profile "$output" '.kube-prometheus-stack.prometheusOperator.resources' "$operator_profile"
  apply_profile "$output" '.kube-prometheus-stack.nodeExporter.resources' "$ne_profile"
  apply_profile "$output" '.kube-prometheus-stack.kubeStateMetrics.resources' "$ksm_profile"

  yq -i ".kube-prometheus-stack.alertmanager.alertmanagerSpec.replicas = $(config_get '.prometheus.alertmanager_replicas' 1)" "$output"
  yq -i '.kube-prometheus-stack.alertmanager.alertmanagerSpec.resources = {}' "$output"
  apply_profile "$output" '.kube-prometheus-stack.alertmanager.alertmanagerSpec.resources' "$alert_profile"
  yq -i ".kube-prometheus-stack.alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.storageClassName = \"${STORAGE_CLASS}\"" "$output"
  yq -i ".kube-prometheus-stack.alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.resources.requests.storage = \"$(config_get '.prometheus.alertmanager_storage' '5Gi')\"" "$output"
  yq -i '.kube-prometheus-stack.alertmanager.config.route.receiver = "default"' "$output"
  yq -i '.kube-prometheus-stack.alertmanager.config.receivers = [{"name":"default"}]' "$output"
  yq -i '.kube-prometheus-stack.alertmanager.config.route.group_by = ["alertname","cluster","service"]' "$output"

  local namespaces
  mapfile -t namespaces < <(config_list '.prometheus.service_monitor_namespaces')
  local namespace_string
  if [[ ${#namespaces[@]} -eq 0 ]]; then
    namespace_string=$'gateway\ngateway-intencoes\nsemantic-translation-engine\nconsensus-engine\norchestrator-dynamic\nspecialist-business\nspecialist-technical\nspecialist-behavior\nspecialist-evolution\nspecialist-architecture\nmemory-layer-api\nexecution-ticket-service'
  else
    namespace_string=$(printf '%s\n' "${namespaces[@]}")
  fi
  local scrape_interval
  scrape_interval=$(config_get '.prometheus.scrape_interval' '30s')
  write_additional_scrape_configs "$output" "$namespace_string" "$scrape_interval"
  yq -i ".kube-prometheus-stack.prometheus.prometheusSpec.scrapeInterval = \"${scrape_interval}\"" "$output"

  log_success "Valores do Prometheus escritos em ${output}"
}

GRAFANA_ADMIN_PASSWORD=""

process_grafana() {
  local base="${CHARTS_DIR}/grafana/values-local.yaml"
  local output="${OUTPUT_DIR}/grafana-values-local.yaml"
  cp "$base" "$output"

  yq -i '.global.domain = "neural-hive.local"' "$output"
  yq -i '.global.environment = "local"' "$output"

  yq -i ".grafana.replicas = $(config_get '.grafana.replicas' 1)" "$output"
  local admin_user admin_password auto_password
  admin_user=$(config_get '.grafana.admin_user' 'admin')
  admin_password=$(config_get '.grafana.admin_password' 'admin')
  auto_password=$(config_get '.grafana.generate_passwords' 'true')
  if [[ "$auto_password" == "true" ]]; then
    admin_password=$(random_password)
    log_warn "Senha admin do Grafana gerada automaticamente."
  fi
  GRAFANA_ADMIN_PASSWORD="$admin_password"
  yq -i ".grafana.adminUser = \"${admin_user}\"" "$output"
  yq -i ".grafana.adminPassword = \"${admin_password}\"" "$output"

  yq -i '.grafana.persistence.enabled = true' "$output"
  yq -i '.grafana.persistence.type = "pvc"' "$output"
  yq -i '.grafana.persistence.accessModes = ["ReadWriteOnce"]' "$output"
  yq -i ".grafana.persistence.storageClassName = \"${STORAGE_CLASS}\"" "$output"
  yq -i ".grafana.persistence.size = \"$(config_get '.grafana.storage_size' '5Gi')\"" "$output"

  local grafana_profile
  grafana_profile=$(config_get '.grafana.resources' 'small')
  apply_profile "$output" '.grafana.resources' "$grafana_profile"

  yq -i '.grafana.database.type = "sqlite3"' "$output"
  yq -i '.grafana.ingress.enabled = false' "$output"
  yq -i '.grafana.sidecar.datasources.enabled = false' "$output"
  yq -i '.grafana.sidecar.dashboards.enabled = false' "$output"

  local prom_url="http://neural-hive-prometheus-kube-prometheus-prometheus.observability.svc.cluster.local:9090"
  local jaeger_url="http://neural-hive-jaeger.observability.svc.cluster.local:16686"
  local ds_tmp
  ds_tmp=$(mktemp)
  cat <<EOF_DS >"${ds_tmp}"
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: ${prom_url}
    isDefault: true
    jsonData:
      timeInterval: 30s
      exemplarTraceIdDestinations:
        - name: trace_id
          datasourceUid: jaeger
          urlDisplayLabel: "View Trace"
  - name: Jaeger
    type: jaeger
    access: proxy
    url: ${jaeger_url}
    uid: jaeger
EOF_DS
  yq -i ".grafana.datasources.datasources.yaml = load(\"${ds_tmp}\")" "$output"
  rm -f "$ds_tmp"

  local plugins_list
  mapfile -t plugins_list < <(config_list '.grafana.plugins')
  if [[ ${#plugins_list[@]} -eq 0 ]]; then
    plugins_list=(grafana-piechart-panel grafana-clock-panel)
  fi
  yq -i '.grafana.plugins = []' "$output"
  for plugin in "${plugins_list[@]}"; do
    yq -i '.grafana.plugins += ["'"${plugin}"'"]' "$output"
  done

  yq -i '.grafana["grafana.ini"].server.domain = "neural-hive.local"' "$output"
  yq -i '.grafana["grafana.ini"].server.root_url = "http://localhost:3000"' "$output"
  yq -i '.grafana["grafana.ini"].analytics.reporting_enabled = false' "$output"
  yq -i '.grafana["grafana.ini"].log.level = "info"' "$output"
  yq -i '.grafana["grafana.ini"].unified_alerting.enabled = true' "$output"

  local toggles
  mapfile -t toggles < <(config_list '.grafana.feature_toggles')
  if [[ ${#toggles[@]} -eq 0 ]]; then
    toggles=(traceqlEditor correlations)
  fi
  local toggle_string="$(IFS=,; echo "${toggles[*]}")"
  yq -i '.grafana.env.GF_FEATURE_TOGGLES_ENABLE = "'"${toggle_string}"'"' "$output"
  yq -i '.grafana.env.GF_EXPLORE_ENABLED = "true"' "$output"
  yq -i '.grafana.env.GF_LOG_LEVEL = "info"' "$output"

  log_success "Valores do Grafana escritos em ${output}"
}

process_jaeger() {
  local base="${CHARTS_DIR}/jaeger/values-local.yaml"
  local output="${OUTPUT_DIR}/jaeger-values-local.yaml"
  cp "$base" "$output"

  yq -i '.global.domain = "neural-hive.local"' "$output"
  yq -i '.global.environment = "local"' "$output"

  yq -i '.allInOne.enabled = true' "$output"
  yq -i '.collector.enabled = false' "$output"
  yq -i '.query.enabled = false' "$output"
  yq -i '.agent.enabled = false' "$output"
  yq -i '.allInOne.replicaCount = 1' "$output"

  local jaeger_profile
  jaeger_profile=$(config_get '.jaeger.resources' 'medium')
  apply_profile "$output" '.allInOne.resources' "$jaeger_profile"

  yq -i '.storage.type = "memory"' "$output"

  yq -i '.allInOne.extraEnv = []' "$output"
  yq -i '.allInOne.extraEnv += [{"name":"COLLECTOR_OTLP_ENABLED","value":"true"}]' "$output"
  yq -i '.allInOne.extraEnv += [{"name":"METRICS_STORAGE_TYPE","value":"prometheus"}]' "$output"

  yq -i '.allInOne.args = ["--memory.max-traces=10000","--collector.otlp.grpc.host-port=0.0.0.0:4317","--collector.otlp.http.host-port=0.0.0.0:4318","--query.base-path=/"]' "$output"

  yq -i '.allInOne.service.type = "ClusterIP"' "$output"
  yq -i '.allInOne.service.ports = []' "$output"
  yq -i '.allInOne.service.ports += [{"name":"grpc","port":14250,"targetPort":14250}]' "$output"
  yq -i '.allInOne.service.ports += [{"name":"http","port":14268,"targetPort":14268}]' "$output"
  yq -i '.allInOne.service.ports += [{"name":"admin","port":14269,"targetPort":14269}]' "$output"
  yq -i '.allInOne.service.ports += [{"name":"otlp-grpc","port":4317,"targetPort":4317}]' "$output"
  yq -i '.allInOne.service.ports += [{"name":"otlp-http","port":4318,"targetPort":4318}]' "$output"
  yq -i '.allInOne.service.ports += [{"name":"ui","port":16686,"targetPort":16686}]' "$output"

  yq -i '.sampling.strategies = ""' "$output"
  cat <<'EOF_SAMPLING' >"${OUTPUT_DIR}/jaeger-sampling.json"
{
  "default_strategy": {"type": "probabilistic", "param": 1.0},
  "service_strategies": [
    {"service": "gateway-intencoes", "type": "probabilistic", "param": 1.0},
    {"service": "semantic-translation-engine", "type": "probabilistic", "param": 1.0},
    {"service": "consensus-engine", "type": "probabilistic", "param": 1.0},
    {"service": "orchestrator-dynamic", "type": "probabilistic", "param": 1.0},
    {"service": "specialist-business", "type": "probabilistic", "param": 1.0},
    {"service": "specialist-technical", "type": "probabilistic", "param": 1.0},
    {"service": "specialist-behavior", "type": "probabilistic", "param": 1.0},
    {"service": "specialist-evolution", "type": "probabilistic", "param": 1.0},
    {"service": "specialist-architecture", "type": "probabilistic", "param": 1.0}
  ],
  "max_traces_per_second": 1000
}
EOF_SAMPLING
  yq -i '.sampling.strategies = load_str("'"${OUTPUT_DIR}/jaeger-sampling.json"'")' "$output"
  rm -f "${OUTPUT_DIR}/jaeger-sampling.json"

  yq -i '.serviceMonitor.enabled = true' "$output"
  yq -i '.serviceMonitor.interval = "30s"' "$output"
  yq -i '.serviceMonitor.additionalLabels = {"neural.hive/component":"distributed-tracing","neural.hive/metrics":"enabled"}' "$output"

  yq -i '.ingress.enabled = false' "$output"

  log_success "Valores do Jaeger escritos em ${output}"
}

process_component() {
  case "$1" in
    prometheus) process_prometheus ;;
    grafana) process_grafana ;;
    jaeger) process_jaeger ;;
    all) process_prometheus; process_grafana; process_jaeger ;;
    *) log_error "Componente desconhecido: $1"; usage; exit 1 ;;
  esac
}

main() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
    exit 1
  fi

  if [[ $# -eq 0 ]]; then
    set -- "${COMPONENTS[@]}"
  fi

  local targets=()
  for arg in "$@"; do
    if [[ "$arg" == "all" ]]; then
      targets=("${COMPONENTS[@]}")
      break
    else
      targets+=("$arg")
    fi
  done

  # Load global validation parameters before any operations
  log "Loading validation parameters from config..."
  load_validation_params
  log_success "Validation params: timeout=${WAIT_TIMEOUT}s, retries=${RETRY_ATTEMPTS}, interval=${HEALTH_CHECK_INTERVAL}s"

  require_commands
  validate_cluster
  detect_storage_class
  ensure_output_dir

  log "Usando StorageClass: ${STORAGE_CLASS}"

  for component in "${targets[@]}"; do
    process_component "$component"
  done

  log_success "Arquivos gerados em ${OUTPUT_DIR}."
  if [[ -n "$GRAFANA_ADMIN_PASSWORD" ]]; then
    log_warn "Senha admin Grafana: ${GRAFANA_ADMIN_PASSWORD}"
  fi
}

main "$@"
