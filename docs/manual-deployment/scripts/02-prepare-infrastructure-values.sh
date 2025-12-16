#!/bin/bash
# Script para preparar valores Helm customizados para infraestrutura local
# Uso: ./02-prepare-infrastructure-values.sh [redis|mongodb|neo4j|clickhouse|all]

set -euo pipefail
shopt -s nullglob

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CHARTS_DIR="${PROJECT_ROOT}/helm-charts"
ENV_DIR="${PROJECT_ROOT}/environments/local"
CONFIG_FILE="${ENV_DIR}/infrastructure-config.yaml"
TEMP_DIR="${PROJECT_ROOT}/.tmp/infrastructure-values"
STORAGE_CLASS=""

declare -A SUMMARY_STORAGE_CLASS
declare -A SUMMARY_STORAGE_SIZE
declare -A SUMMARY_SCALE

COMPONENTS=("redis" "mongodb" "neo4j" "clickhouse")

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

error_trap() {
  local exit_code=$?
  log_error "Execução interrompida (código ${exit_code}, linha ${BASH_LINENO[0]})."
  exit $exit_code
}
trap error_trap ERR

usage() {
  cat <<'EOF'
Uso: 02-prepare-infrastructure-values.sh [componentes...]

Componentes suportados:
  redis, mongodb, neo4j, clickhouse

Se nenhum componente for informado, todos serão processados.
EOF
}

ensure_commands() {
  for cmd in kubectl helm yq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Comando obrigatório não encontrado: $cmd"
      exit 1
    fi
  done
  log_success "Dependências verificadas (kubectl, helm, yq)."
}

validate_cluster() {
  if ! kubectl cluster-info >/dev/null 2>&1; then
    log_error "Não foi possível conectar ao cluster Kubernetes."
    exit 1
  fi
  log_success "Conectado ao cluster: $(kubectl config current-context)"
}

config_value() {
  local path="$1"
  local default="${2:-}"
  local raw
  raw=$(yq -r "${path}" "$CONFIG_FILE" 2>/dev/null || echo "null")
  if [[ -z "$raw" || "$raw" == "null" ]]; then
    echo "$default"
  else
    echo "$raw"
  fi
}

apply_profile() {
  local file="$1"
  local target_path="$2"
  local profile="$3"
  local cpu_req mem_req cpu_lim mem_lim
  profile="${profile:-medium}"
  cpu_req=$(config_value ".resources.${profile}.requests.cpu" "")
  mem_req=$(config_value ".resources.${profile}.requests.memory" "")
  cpu_lim=$(config_value ".resources.${profile}.limits.cpu" "")
  mem_lim=$(config_value ".resources.${profile}.limits.memory" "")
  if [[ -z "$cpu_req" || -z "$mem_req" || -z "$cpu_lim" || -z "$mem_lim" ]]; then
    log_warning "Perfil de recursos '${profile}' inválido. Mantendo valores originais em ${target_path}."
    return
  fi
  yq -i "${target_path}.requests.cpu = \"${cpu_req}\"" "$file"
  yq -i "${target_path}.requests.memory = \"${mem_req}\"" "$file"
  yq -i "${target_path}.limits.cpu = \"${cpu_lim}\"" "$file"
  yq -i "${target_path}.limits.memory = \"${mem_lim}\"" "$file"
}

detect_storage_class() {
  local configured default_sc
  configured=$(config_value '.storage.class' '')
  if [[ -n "$configured" ]]; then
    STORAGE_CLASS="$configured"
    return
  fi
  for candidate in local-path hostpath standard; do
    if kubectl get storageclass "$candidate" >/dev/null 2>&1; then
      STORAGE_CLASS="$candidate"
      return
    fi
  done
  default_sc=$(kubectl get storageclass -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [[ -n "$default_sc" ]]; then
    STORAGE_CLASS="$default_sc"
  else
    log_error "Nenhuma StorageClass encontrada. Crie uma antes de continuar."
    exit 1
  fi
}

prepare_base_file() {
  local component="$1"
  local chart_values="$2"
  local override_file="$3"
  local work_file="$4"

  if [[ ! -f "$chart_values" ]]; then
    log_error "Arquivo de valores base não encontrado para ${component}: $chart_values"
    exit 1
  fi

  if [[ -f "$override_file" ]]; then
    yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
      "$chart_values" "$override_file" > "$work_file"
  else
    cp "$chart_values" "$work_file"
  fi
}

summarize_change() {
  local component="$1"
  local storage_path="$2"
  local size_path="$3"
  local scale_desc="$4"
  local file="$5"
  local before_file="$6"

  local orig_sc new_sc orig_size new_size orig_scale new_scale
  orig_sc=$(yq -r "$storage_path" "$before_file" 2>/dev/null || echo "-")
  new_sc=$(yq -r "$storage_path" "$file" 2>/dev/null || echo "-")
  orig_size=$(yq -r "$size_path" "$before_file" 2>/dev/null || echo "-")
  new_size=$(yq -r "$size_path" "$file" 2>/dev/null || echo "-")
  orig_scale=$(yq -r "$scale_desc" "$before_file" 2>/dev/null || echo "-")
  new_scale=$(yq -r "$scale_desc" "$file" 2>/dev/null || echo "-")

  SUMMARY_STORAGE_CLASS["$component"]="${orig_sc} -> ${new_sc}"
  SUMMARY_STORAGE_SIZE["$component"]="${orig_size} -> ${new_size}"
  SUMMARY_SCALE["$component"]="${orig_scale} -> ${new_scale}"
}

process_redis() {
  local base="${CHARTS_DIR}/redis-cluster/values.yaml"
  local override="${ENV_DIR}/redis-values.yaml"
  local work="${TEMP_DIR}/redis.work.yaml"
  local final="${TEMP_DIR}/redis-values-local.yaml"

  prepare_base_file "redis" "$base" "$override" "$work"
  cp "$work" "${work}.orig"

  yq -i ".cluster.name = \"$(config_value '.redis.cluster_name' 'neural-hive-cache')\"" "$work"
  yq -i ".cluster.namespace = \"$(config_value '.redis.namespace' 'redis-cluster')\"" "$work"
  yq -i ".cluster.clusterSize = $(config_value '.redis.cluster_size' 3)" "$work"
  yq -i ".cluster.storage.size = \"$(config_value '.redis.storage_size' '5Gi')\"" "$work"
  yq -i ".cluster.storage.storageClass = \"${STORAGE_CLASS}\"" "$work"
  apply_profile "$work" ".cluster.resources" "$(config_value '.redis.resources' 'medium')"
  yq -i ".security.tls.enabled = $(config_value '.redis.tls_enabled' 'false')" "$work"
  yq -i ".backup.enabled = $(config_value '.redis.backup_enabled' 'false')" "$work"
  yq -i ".backup.storage.storageClass = \"${STORAGE_CLASS}\"" "$work"
  local redis_storage_size
  redis_storage_size=$(yq -r ".cluster.storage.size" "$work")
  yq -i ".backup.storage.size = \"${redis_storage_size}\"" "$work"

  summarize_change "redis" ".cluster.storage.storageClass" ".cluster.storage.size" ".cluster.clusterSize" "$work" "${work}.orig"

  mv "$work" "$final"
  rm -f "${work}.orig"
  log_success "Valores do Redis gerados em ${final}"
}

process_mongodb() {
  local base="${CHARTS_DIR}/mongodb/values.yaml"
  local override="${ENV_DIR}/mongodb-values.yaml"
  local work="${TEMP_DIR}/mongodb.work.yaml"
  local final="${TEMP_DIR}/mongodb-values-local.yaml"

  prepare_base_file "mongodb" "$base" "$override" "$work"
  cp "$work" "${work}.orig"

  yq -i ".cluster.name = \"$(config_value '.mongodb.cluster_name' 'neural-hive-mongodb')\"" "$work"
  yq -i ".cluster.namespace = \"$(config_value '.mongodb.namespace' 'mongodb-cluster')\"" "$work"
  yq -i ".cluster.members = $(config_value '.mongodb.members' 3)" "$work"
  yq -i ".storage.size = \"$(config_value '.mongodb.storage_size' '20Gi')\"" "$work"
  yq -i ".storage.storageClass = \"${STORAGE_CLASS}\"" "$work"
  apply_profile "$work" ".resources" "$(config_value '.mongodb.resources' 'large')"
  yq -i ".security.tls.enabled = $(config_value '.mongodb.tls_enabled' 'false')" "$work"
  yq -i ".backup.enabled = $(config_value '.mongodb.backup_enabled' 'false')" "$work"
  yq -i ".backup.storage.storageClass = \"${STORAGE_CLASS}\"" "$work"
  yq -i ".backup.storage.size = \"$(config_value '.mongodb.storage_size' '20Gi')\"" "$work"

  summarize_change "mongodb" ".storage.storageClass" ".storage.size" ".cluster.members" "$work" "${work}.orig"

  mv "$work" "$final"
  rm -f "${work}.orig"
  log_success "Valores do MongoDB gerados em ${final}"
}

process_neo4j() {
  local base="${CHARTS_DIR}/neo4j/values.yaml"
  local override="${ENV_DIR}/neo4j-values.yaml"
  local work="${TEMP_DIR}/neo4j.work.yaml"
  local final="${TEMP_DIR}/neo4j-values-local.yaml"

  prepare_base_file "neo4j" "$base" "$override" "$work"
  cp "$work" "${work}.orig"

  yq -i ".neo4j.name = \"$(config_value '.neo4j.cluster_name' 'neural-hive-neo4j')\"" "$work"
  yq -i ".neo4j.namespace = \"$(config_value '.neo4j.namespace' 'neo4j-cluster')\"" "$work"
  yq -i ".cluster.coreServers = $(config_value '.neo4j.core_servers' 1)" "$work"
  yq -i ".cluster.readReplicas = $(config_value '.neo4j.read_replicas' 1)" "$work"
  yq -i ".storage.core.size = \"$(config_value '.neo4j.storage.core_size' '20Gi')\"" "$work"
  yq -i ".storage.core.storageClass = \"${STORAGE_CLASS}\"" "$work"
  yq -i ".storage.replica.size = \"$(config_value '.neo4j.storage.replica_size' '10Gi')\"" "$work"
  yq -i ".storage.replica.storageClass = \"${STORAGE_CLASS}\"" "$work"
  apply_profile "$work" ".resources.core" "$(config_value '.neo4j.resources.core' 'large')"
  apply_profile "$work" ".resources.replica" "$(config_value '.neo4j.resources.replica' 'medium')"
  yq -i ".security.ssl.bolt.enabled = $(config_value '.neo4j.ssl_enabled' 'false')" "$work"
  yq -i ".security.ssl.https.enabled = $(config_value '.neo4j.ssl_enabled' 'false')" "$work"
  yq -i ".backup.enabled = $(config_value '.neo4j.backup_enabled' 'false')" "$work"
  yq -i ".plugins.apoc = $(config_value '.neo4j.plugins.apoc' 'true')" "$work"
  yq -i ".plugins.graphDataScience = $(config_value '.neo4j.plugins.graph_data_science' 'false')" "$work"
  yq -i ".plugins.neosemantics = $(config_value '.neo4j.plugins.neosemantics' 'true')" "$work"

  summarize_change "neo4j" ".storage.core.storageClass" ".storage.core.size" \
    '.cluster.coreServers as $c | .cluster.readReplicas as $r | ($c | tostring) + " core / " + ($r | tostring) + " replica(s)"' \
    "$work" "${work}.orig"

  mv "$work" "$final"
  rm -f "${work}.orig"
  log_success "Valores do Neo4j gerados em ${final}"
}

process_clickhouse() {
  local base="${CHARTS_DIR}/clickhouse/values.yaml"
  local override="${ENV_DIR}/clickhouse-values.yaml"
  local work="${TEMP_DIR}/clickhouse.work.yaml"
  local final="${TEMP_DIR}/clickhouse-values-local.yaml"

  prepare_base_file "clickhouse" "$base" "$override" "$work"
  cp "$work" "${work}.orig"

  yq -i ".cluster.name = \"$(config_value '.clickhouse.cluster_name' 'neural-hive-clickhouse')\"" "$work"
  yq -i ".cluster.namespace = \"$(config_value '.clickhouse.namespace' 'clickhouse-cluster')\"" "$work"
  yq -i ".cluster.shards = $(config_value '.clickhouse.shards' 1)" "$work"
  yq -i ".cluster.replicas = $(config_value '.clickhouse.replicas' 1)" "$work"
  yq -i ".storage.size = \"$(config_value '.clickhouse.storage_size' '30Gi')\"" "$work"
  yq -i ".storage.storageClass = \"${STORAGE_CLASS}\"" "$work"
  apply_profile "$work" ".resources" "$(config_value '.clickhouse.resources' 'large')"
  yq -i ".zookeeper.nodes = $(config_value '.clickhouse.zookeeper.nodes' 1)" "$work"
  yq -i ".zookeeper.storage.size = \"$(config_value '.clickhouse.zookeeper.storage_size' '5Gi')\"" "$work"
  yq -i ".zookeeper.storage.storageClass = \"${STORAGE_CLASS}\"" "$work"
  apply_profile "$work" ".zookeeperResources" "$(config_value '.clickhouse.zookeeper.resources' 'small')"
  yq -i ".security.tls.enabled = $(config_value '.clickhouse.tls_enabled' 'false')" "$work"
  yq -i ".backup.enabled = $(config_value '.clickhouse.backup_enabled' 'false')" "$work"

  summarize_change "clickhouse" ".storage.storageClass" ".storage.size" \
    '.cluster.shards as $s | .cluster.replicas as $r | ($s | tostring) + "x" + ($r | tostring)' \
    "$work" "${work}.orig"

  mv "$work" "$final"
  rm -f "${work}.orig"
  log_success "Valores do ClickHouse gerados em ${final}"
}

validate_outputs() {
  for file in "${TEMP_DIR}"/*-values-local.yaml; do
    [[ -e "$file" ]] || continue
    yq eval '.' "$file" >/dev/null
    log_success "Validação YAML OK: ${file}"
  done
}

print_summary() {
  printf "\n=== Resumo das Alterações Aplicadas ===\n"
  printf "%-12s | %-25s | %-20s | %-20s\n" "Componente" "StorageClass" "Capacidade" "Escala"
  printf "%-12s-+-%-25s-+-%-20s-+-%-20s\n" "------------" "-------------------------" "--------------------" "--------------------"
  for component in "${COMPONENTS[@]}"; do
    [[ -n "${SUMMARY_STORAGE_CLASS[$component]:-}" ]] || continue
    printf "%-12s | %-25s | %-20s | %-20s\n" \
      "$component" \
      "${SUMMARY_STORAGE_CLASS[$component]}" \
      "${SUMMARY_STORAGE_SIZE[$component]}" \
      "${SUMMARY_SCALE[$component]}"
  done
  printf "Arquivos disponíveis em %s\n\n" "$TEMP_DIR"
}

main() {
  local requested_components=()
  if [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  if [[ $# -gt 0 ]]; then
    if [[ "$1" == "all" ]]; then
      requested_components=("${COMPONENTS[@]}")
    else
      for arg in "$@"; do
        if [[ ! " ${COMPONENTS[*]} " =~ " ${arg} " ]]; then
          log_error "Componente inválido: ${arg}"
          usage
          exit 1
        fi
        requested_components+=("$arg")
      done
    fi
  else
    requested_components=("${COMPONENTS[@]}")
  fi

  ensure_commands

  if [[ ! -f "$CONFIG_FILE" ]]; then
    log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
    exit 1
  fi

  validate_cluster
  detect_storage_class
  log "Usando StorageClass: ${STORAGE_CLASS}"

  mkdir -p "$TEMP_DIR"

  for component in "${requested_components[@]}"; do
    case "$component" in
      redis) process_redis ;;
      mongodb) process_mongodb ;;
      neo4j) process_neo4j ;;
      clickhouse) process_clickhouse ;;
    esac
  done

  validate_outputs
  print_summary
}

main "$@"
