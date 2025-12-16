#!/usr/bin/env bash
# Exporta e importa as imagens Neural Hive-Mind para o containerd (k8s.io)
# Uso: ./07-export-images-to-containerd.sh [--remote] [--nodes n1,n2] [--skip-export] [--skip-cleanup] [--dry-run] [--parallel]

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ENV_DIR="${PROJECT_ROOT}/environments/local"
CONFIG_FILE="${SERVICES_BUILD_CONFIG:-${ENV_DIR}/services-build-config.yaml}"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/export-images-to-containerd.log"

mkdir -p "$LOG_DIR"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

run_with_keepalive() {
  local description="$1"
  shift
  "$@" &
  local pid=$!
  local interval=5
  while kill -0 "$pid" >/dev/null 2>&1; do
    echo -e "${BLUE}[INFO]${NC} ${description} (pid=${pid}) ainda em execução..."
    sleep "$interval"
  done
  wait "$pid"
}

REMOTE_MODE=false
NODE_OVERRIDE=""
SKIP_EXPORT=false
SKIP_CLEANUP=false
DRY_RUN=false
PARALLEL_MODE=false

REGISTRY=""
VERSION=""
TEMP_DIR=""
CONTAINERD_NAMESPACE="k8s.io"
SSH_USER="root"
declare -a IMAGE_NAMES=()
TOTAL_IMAGES=0
TOTAL_SIZE_BYTES=0
EXPORT_SUCCESS=0
IMPORT_SUCCESS=0
IMPORT_FAILURES=0
NODES=()
SCRIPT_START=$SECONDS

usage() {
  cat <<'USO'
Uso: 07-export-images-to-containerd.sh [opções]

Opções:
  --remote            Copia as imagens para nós remotos via SSH/SCP antes da importação
  --nodes <lista>     Lista de nós (ex: master01,worker01) para override
  --skip-export       Pula o docker save (assume arquivos .tar já presentes)
  --skip-cleanup      Não remove os arquivos .tar ao final
  --dry-run           Apenas simula, sem executar comandos destrutivos
  --parallel          Processa nós remotos em paralelo (experimental)
  --help              Exibe esta ajuda
USO
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --remote) REMOTE_MODE=true; shift ;;
      --nodes) NODE_OVERRIDE="${2:-}"; shift 2 ;;
      --skip-export) SKIP_EXPORT=true; shift ;;
      --skip-cleanup) SKIP_CLEANUP=true; shift ;;
      --dry-run) DRY_RUN=true; shift ;;
      --parallel) PARALLEL_MODE=true; shift ;;
      --help) usage; exit 0 ;;
      *) log_error "Opção desconhecida: $1"; usage; exit 1 ;;
    esac
  done
}

require_tools() {
  for cmd in docker yq jq sha256sum; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Comando obrigatório não encontrado: $cmd"
      exit 1
    fi
  done
  if [[ "$REMOTE_MODE" == true ]]; then
    for cmd in ssh scp; do
      if ! command -v "$cmd" >/dev/null 2>&1; then
        log_error "Comando obrigatório não encontrado (modo remoto): $cmd"
        exit 1
      fi
    done
  fi
}

load_config() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
    exit 1
  fi
  REGISTRY=$(yq -r '.build.registry // "neural-hive-mind"' "$CONFIG_FILE")
  VERSION=$(yq -r '.build.version // "1.0.0"' "$CONFIG_FILE")
  TEMP_DIR=$(yq -r '.containerd.temp_dir // "/tmp/neural-hive-images"' "$CONFIG_FILE")
  CONTAINERD_NAMESPACE=$(yq -r '.containerd.namespace // "k8s.io"' "$CONFIG_FILE")
  SSH_USER=$(yq -r '.containerd.ssh_user // "root"' "$CONFIG_FILE")

  mapfile -t IMAGE_NAMES < <(
    {
      yq -r '.base_images | to_entries[] | .value.name' "$CONFIG_FILE"
      yq -r '.services[].name' "$CONFIG_FILE"
    } | sed '/^null$/d'
  )
  TOTAL_IMAGES=${#IMAGE_NAMES[@]}

  if [[ -n "$NODE_OVERRIDE" ]]; then
    IFS=',' read -r -a NODES <<<"$NODE_OVERRIDE"
  else
    mapfile -t NODES < <(yq -r '.containerd.nodes[]?' "$CONFIG_FILE" | sed '/^null$/d')
  fi

  if [[ "$REMOTE_MODE" == true && ${#NODES[@]} -eq 0 ]]; then
    log_error "Modo remoto habilitado, mas nenhum nó foi especificado."
    exit 1
  fi

  mkdir -p "$TEMP_DIR"
  log_success "Config carregada (versão=${VERSION}, temp_dir=${TEMP_DIR})."
}

docker_inspect_image() {
  local image="$1"
  docker image inspect "$image" >/dev/null 2>&1
}

save_image() {
  local name="$1"
  local ref="${REGISTRY}/${name}:${VERSION}"
  local tar_file="${TEMP_DIR}/${name}.tar"
  log_info "Exportando ${ref} -> ${tar_file}"
  if [[ "$DRY_RUN" == true || "$SKIP_EXPORT" == true ]]; then
    if [[ "$SKIP_EXPORT" == true && ! -f "$tar_file" ]]; then
      log_error "Arquivo ${tar_file} inexistente e --skip-export foi usado."
      return 1
    fi
    log_info "[SKIPPED] docker save ${ref}"
    return 0
  fi
  if ! docker_inspect_image "$ref"; then
    log_error "Imagem não encontrada: ${ref}"
    return 1
  fi
  run_with_keepalive "docker save ${ref}" docker save "$ref" -o "$tar_file"
  ((EXPORT_SUCCESS++))
  local size_bytes
  size_bytes=$(stat -c%s "$tar_file")
  TOTAL_SIZE_BYTES=$((TOTAL_SIZE_BYTES + size_bytes))
  sha256sum "$tar_file" > "${tar_file}.sha256"
  log_success "Imagem salva (${ref}) - $(du -h "$tar_file" | awk '{print $1}')"
}

export_images_to_tar() {
  [[ "$SKIP_EXPORT" == true ]] && log_warn "Exportação pulada por flag --skip-export"
  for name in "${IMAGE_NAMES[@]}"; do
    save_image "$name"
  done
}

run_ssh() {
  local node="$1"
  shift
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN][${node}] $*"
    return 0
  fi
  ssh -o StrictHostKeyChecking=no "${SSH_USER}@${node}" "$@"
}

run_scp() {
  local target="${@: -1}"
  local sources=("${@:1:$#-1}")
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN][scp] ${sources[*]} -> ${target}"
    return 0
  fi
  scp -q "${sources[@]}" "$target"
}

copy_node_payload() {
  local node="$1"
  log_info "Copiando arquivos para ${node}..."
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Arquivos seriam copiados para ${node}"
    return 0
  fi
  local tar_files=("${TEMP_DIR}"/*.tar)
  if [[ ${#tar_files[@]} -eq 0 ]]; then
    log_error "Nenhum arquivo .tar encontrado em ${TEMP_DIR}."
    return 1
  fi
  local checksum_files=("${TEMP_DIR}"/*.tar.sha256)
  run_ssh "$node" "mkdir -p ${TEMP_DIR}"
  run_scp "${tar_files[@]}" "${SSH_USER}@${node}:${TEMP_DIR}/"
  if [[ ${#checksum_files[@]} -gt 0 ]]; then
    run_scp "${checksum_files[@]}" "${SSH_USER}@${node}:${TEMP_DIR}/"
    run_ssh "$node" "cd ${TEMP_DIR} && sha256sum -c *.sha256"
  else
    log_warn "Nenhum arquivo .sha256 encontrado para validação."
  fi
  log_success "Transferência concluída em ${node}"
}

run_for_nodes() {
  local func="$1"
  shift
  local nodes=("$@")
  local status=0
  if [[ "$PARALLEL_MODE" == true ]]; then
    log_info "Executando ${func} em paralelo (${#nodes[@]} nós)..."
    local pids=()
    for node in "${nodes[@]}"; do
      ("$func" "$node") &
      pids+=($!)
    done
    for pid in "${pids[@]}"; do
      if ! wait "$pid"; then
        status=1
      fi
    done
  else
    for node in "${nodes[@]}"; do
      "$func" "$node"
    done
  fi
  return $status
}

copy_to_nodes() {
  [[ "$REMOTE_MODE" == true ]] || return
  log_info "Iniciando cópia para nós remotos (${NODES[*]})."
  run_for_nodes copy_node_payload "${NODES[@]}"
}

import_local_images() {
  log_info "Importando imagens localmente para containerd (${CONTAINERD_NAMESPACE})..."
  for name in "${IMAGE_NAMES[@]}"; do
    local tar_file="${TEMP_DIR}/${name}.tar"
    if [[ ! -f "$tar_file" ]]; then
      log_error "Arquivo ${tar_file} não encontrado."
      continue
    fi
    if [[ "$DRY_RUN" == true ]]; then
      log_info "[DRY-RUN] sudo ctr -n ${CONTAINERD_NAMESPACE} images import ${tar_file}"
      ((IMPORT_SUCCESS++))
      continue
    fi
    if run_with_keepalive "ctr import ${name}" sudo ctr -n "${CONTAINERD_NAMESPACE}" images import "$tar_file" >/dev/null; then
      ((IMPORT_SUCCESS++))
      log_success "Importado: ${name}"
    else
      log_error "Falha ao importar ${name}"
    fi
  done
}

import_remote_node() {
  local node="$1"
  log_info "Importando imagens em ${node}..."
  for name in "${IMAGE_NAMES[@]}"; do
    local remote_tar="${TEMP_DIR}/${name}.tar"
    if [[ "$DRY_RUN" == true ]]; then
      log_info "[DRY-RUN][${node}] sudo ctr -n ${CONTAINERD_NAMESPACE} images import ${remote_tar}"
      continue
    fi
    if run_with_keepalive "[${node}] ctr import ${name}" run_ssh "$node" "sudo ctr -n ${CONTAINERD_NAMESPACE} images import ${remote_tar} >/dev/null"; then
      log_success "[${node}] Importado ${name}"
      ((IMPORT_SUCCESS++))
    else
      log_error "[${node}] Falha ao importar ${name}"
    fi
  done
}

import_to_containerd() {
  if [[ "$REMOTE_MODE" == true ]]; then
    run_for_nodes import_remote_node "${NODES[@]}"
  else
    import_local_images
  fi
}

validate_import_local() {
  local output
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Validação local de ctr"
    return
  fi
  output=$(sudo ctr -n "${CONTAINERD_NAMESPACE}" images ls --quiet)
  local missing=0
  for name in "${IMAGE_NAMES[@]}"; do
    local ref="${REGISTRY}/${name}:${VERSION}"
    if ! grep -q "$ref" <<<"$output"; then
      log_warn "Imagem ausente após importação: ${ref}"
      missing=$((missing + 1))
    fi
  done
  IMPORT_FAILURES=$missing
  if (( missing == 0 )); then
    log_success "Todas as imagens estão disponíveis localmente no containerd."
  else
    log_warn "${missing} imagens não foram encontradas localmente."
  fi
}

validate_import_remote_node() {
  local node="$1"
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN][${node}] validação via ctr"
    return
  fi
  local output node_missing=0
  output=$(run_ssh "$node" "sudo ctr -n ${CONTAINERD_NAMESPACE} images ls --quiet")
  for name in "${IMAGE_NAMES[@]}"; do
    local ref="${REGISTRY}/${name}:${VERSION}"
    if ! grep -q "$ref" <<<"$output"; then
      log_warn "[${node}] Imagem ausente: ${ref}"
      node_missing=$((node_missing + 1))
    fi
  done
  if (( node_missing == 0 )); then
    log_success "[${node}] Todas as imagens disponíveis."
  elif (( node_missing > IMPORT_FAILURES )); then
    IMPORT_FAILURES=$node_missing
  fi
}

validate_import() {
  if [[ "$REMOTE_MODE" == true ]]; then
    for node in "${NODES[@]}"; do
      validate_import_remote_node "$node"
    done
  else
    validate_import_local
  fi
}

cleanup_local() {
  [[ "$SKIP_CLEANUP" == true ]] && return
  log_info "Limpando arquivos locais (${TEMP_DIR})..."
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] rm -f ${TEMP_DIR}/*.tar"
    return
  fi
  rm -f "${TEMP_DIR}"/*.tar
}

cleanup_remote_node() {
  local node="$1"
  [[ "$SKIP_CLEANUP" == true ]] && return
  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN][cleanup] ${node}"
    return
  fi
  run_ssh "$node" "rm -f ${TEMP_DIR}/*.tar"
}

cleanup_all() {
  cleanup_local
  if [[ "$REMOTE_MODE" == true && "$SKIP_CLEANUP" == false ]]; then
    run_for_nodes cleanup_remote_node "${NODES[@]}"
  fi
}

trap cleanup_all EXIT
trap 'log_error "Falha inesperada (linha ${LINENO}): ${BASH_COMMAND}"; exit 1' ERR

print_summary() {
  local duration=$((SECONDS - SCRIPT_START))
  local minutes=$((duration / 60))
  local seconds=$((duration % 60))
  local total_gb
  total_gb=$(awk -v bytes="$TOTAL_SIZE_BYTES" 'BEGIN {printf "%.2f", bytes/1024/1024/1024}')

  echo "========================================"
  echo "IMPORTAÇÃO NO CONTAINERD - RESUMO"
  echo "========================================"
  local imported=$((TOTAL_IMAGES - IMPORT_FAILURES))
  ((imported < 0)) && imported=0
  echo "Imagens exportadas: ${EXPORT_SUCCESS}/${TOTAL_IMAGES}"
  echo "Imagens importadas: ${imported}/${TOTAL_IMAGES}"
  if [[ "$REMOTE_MODE" == true ]]; then
    echo "Nós processados: ${#NODES[@]} (modo remoto)"
  else
    echo "Nós processados: 1 (modo local)"
  fi
  echo "Espaço processado: ~${total_gb} GB"
  printf "Tempo total: %dm %02ds\n" "$minutes" "$seconds"
  echo "========================================"
  if (( IMPORT_FAILURES > 0 )); then
    echo "STATUS: WARNING (verifique imagens faltantes)"
  else
    echo "STATUS: SUCCESS"
  fi
  echo "========================================"
  log_info "Atualize os itens correspondentes no docs/manual-deployment/SERVICES_BUILD_CHECKLIST.md."
}

main() {
  parse_args "$@"
  require_tools
  load_config
  export_images_to_tar
  copy_to_nodes
  import_to_containerd
  validate_import
  print_summary
}

main "$@"
