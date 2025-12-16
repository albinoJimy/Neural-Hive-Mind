#!/usr/bin/env bash
# Prepara o ambiente de build manual das imagens dos serviços Neural Hive-Mind
# Uso: ./05-prepare-services-build.sh [--version <v>] [--parallel <n>] [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ENV_DIR="${PROJECT_ROOT}/environments/local"
CONFIG_FILE="${SERVICES_BUILD_CONFIG:-${ENV_DIR}/services-build-config.yaml}"
TMP_DIR="${PROJECT_ROOT}/.tmp/services-build"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/prepare-services-build.log"

mkdir -p "$LOG_DIR"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

VERSION_OVERRIDE=""
PARALLEL_OVERRIDE=""
PARSED_ARGS=()

VERSION=""
REGISTRY=""
BUILD_CONTEXT=""
PARALLEL_JOBS=""
NO_CACHE="false"
TEMP_TAR_DIR=""
SERVICES_JSON=""
BASE_IMAGES_JSON=""

trap 'log_error "Execução interrompida (linha ${LINENO}). Consulte ${LOG_FILE} para detalhes."' ERR

usage() {
  cat <<'USO'
Uso: 05-prepare-services-build.sh [opções]

Opções:
  --version <v>   Override da versão definida no arquivo de configuração
  --parallel <n>  Número de jobs paralelos para builds
  --help          Exibe esta ajuda
USO
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version)
        VERSION_OVERRIDE="${2:-}"
        shift 2
        ;;
      --parallel)
        PARALLEL_OVERRIDE="${2:-}"
        shift 2
        ;;
      --help)
        usage
        exit 0
        ;;
      *)
        PARSED_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

check_prerequisites() {
  log_info "Verificando pré-requisitos básicos..."
  for cmd in docker yq jq kubectl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Comando obrigatório não encontrado: $cmd"
      exit 1
    fi
  done
  log_success "Ferramentas docker, yq, jq e kubectl encontradas."

  if ! docker info >/dev/null 2>&1; then
    log_error "Docker daemon não está em execução ou o usuário não tem permissão."
    exit 1
  fi

  local docker_path="/var/lib/docker"
  if [[ ! -d "$docker_path" ]]; then
    docker_path="/"
  fi
  local free_gb
  free_gb=$(df -BG "$docker_path" | awk 'NR==2 {gsub("G","",$4); print $4}')
  if [[ -z "$free_gb" ]]; then
    log_warn "Não foi possível calcular espaço em disco livre."
  elif (( free_gb < 20 )); then
    log_warn "Espaço livre menor que 20GB (${free_gb}GB). Limpe imagens antes de prosseguir."
  else
    log_success "Espaço livre suficiente (${free_gb}GB)."
  fi

  if ! kubectl cluster-info >/dev/null 2>&1; then
    log_warn "kubectl não conseguiu conectar ao cluster. Continue apenas se o build ocorrer offline."
  else
    log_success "kubectl conectado ao cluster: $(kubectl config current-context 2>/dev/null || echo 'desconhecido')."
  fi

  if ! sudo ctr version >/dev/null 2>&1; then
    log_warn "Não foi possível executar 'sudo ctr version'. Verifique permissões antes da importação."
  else
    log_success "ctr acessível via sudo."
  fi
}

load_config() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
    exit 1
  fi

  VERSION=$(yq -r '.build.version // "1.0.0"' "$CONFIG_FILE")
  REGISTRY=$(yq -r '.build.registry // "neural-hive-mind"' "$CONFIG_FILE")
  BUILD_CONTEXT=$(yq -r '.build.context // "."' "$CONFIG_FILE")
  PARALLEL_JOBS=$(yq -r '.build.parallel_jobs // 2' "$CONFIG_FILE")
  NO_CACHE=$(yq -r '.build.no_cache // false' "$CONFIG_FILE")
  TEMP_TAR_DIR=$(yq -r '.containerd.temp_dir // "/tmp/neural-hive-images"' "$CONFIG_FILE")

  [[ -n "$VERSION_OVERRIDE" ]] && VERSION="$VERSION_OVERRIDE"
  if [[ -n "$PARALLEL_OVERRIDE" ]]; then
    if [[ ! "$PARALLEL_OVERRIDE" =~ ^[0-9]+$ ]]; then
      log_error "Valor inválido para --parallel: $PARALLEL_OVERRIDE"
      exit 1
    fi
    PARALLEL_JOBS="$PARALLEL_OVERRIDE"
  fi

  SERVICES_JSON="$(yq -o=json '.services' "$CONFIG_FILE")"
  BASE_IMAGES_JSON="$(yq -o=json '.base_images' "$CONFIG_FILE")"

  export VERSION REGISTRY BUILD_CONTEXT PARALLEL_JOBS NO_CACHE
  log_success "Configuração carregada (versão=${VERSION}, parallel_jobs=${PARALLEL_JOBS})."
}

prepare_build_environment() {
  log_info "Preparando diretórios auxiliares..."
  mkdir -p "$TMP_DIR"
  mkdir -p "$TEMP_TAR_DIR"
  mkdir -p "${PROJECT_ROOT}/logs"
  mkdir -p "${PROJECT_ROOT}/.tmp"
  find "$TMP_DIR" -type f -delete || true
  log_success "Diretórios prontos (${TMP_DIR} / ${TEMP_TAR_DIR})."
}

generate_build_order() {
  local order_file="${TMP_DIR}/build-order.txt"
  log_info "Gerando ordem de build em ${order_file}..."
  cat >"$order_file" <<'EOF'
# Ordem recomendada de build - Neural Hive-Mind

Fase 1 - Imagens Base
EOF

  printf "%s\n" "python-ml-base" "python-grpc-base" "python-nlp-base" >>"$order_file"
  cat >>"$order_file" <<'EOF'

Fase 2 - Serviços sem dependências diretas entre si
EOF
  printf "%s\n" "gateway-intencoes" "semantic-translation-engine" "orchestrator-dynamic" >>"$order_file"

  cat >>"$order_file" <<'EOF'

Fase 3 - Specialists (podem rodar em paralelo)
EOF
  printf "%s\n" "specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture" >>"$order_file"

  cat >>"$order_file" <<'EOF'

Fase 4 - Serviços dependentes gRPC
EOF
  printf "%s\n" "consensus-engine" >>"$order_file"

  log_success "Arquivo de ordem criado."
}

export_build_vars() {
  local env_file="${TMP_DIR}/build-env.sh"
  log_info "Exportando variáveis de ambiente para ${env_file}..."
  cat >"$env_file" <<EOF
export VERSION="${VERSION}"
export BUILD_DATE="\$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
export REGISTRY="${REGISTRY}"
export DOCKER_BUILDKIT=1
export DOCKER_DEFAULT_PLATFORM="linux/amd64"
export PARALLEL_JOBS="${PARALLEL_JOBS}"
export BUILD_CONTEXT="${BUILD_CONTEXT}"
export NO_CACHE="${NO_CACHE}"
EOF
  chmod +x "$env_file"
  log_success "Arquivo ${env_file} pronto. Use 'source ${env_file}' antes dos builds."
}

validate_dockerfiles() {
  log_info "Validando Dockerfiles declarados na configuração..."
  local missing=0
  local entry name path

  # Base images
  while IFS='|' read -r name path; do
    [[ -z "$name" ]] && continue
    if [[ ! -f "${PROJECT_ROOT}/${path}" ]]; then
      log_error "Dockerfile não encontrado: ${path}"
      ((missing++))
      continue
    fi
    if ! grep -q '^FROM ' "${PROJECT_ROOT}/${path}"; then
      log_warn "Dockerfile ${path} sem instrução FROM clara."
    fi
  done < <(yq -r '.base_images | to_entries[] | "\(.value.name)|\(.value.dockerfile)"' "$CONFIG_FILE")

  # Services
  while IFS='|' read -r name path; do
    [[ -z "$name" ]] && continue
    if [[ ! -f "${PROJECT_ROOT}/${path}" ]]; then
      log_error "Dockerfile não encontrado: ${path}"
      ((missing++))
      continue
    fi
    for kw in FROM COPY CMD; do
      if ! grep -q "$kw" "${PROJECT_ROOT}/${path}"; then
        log_warn "Dockerfile ${path} não contém '${kw}'."
      fi
    done
  done < <(yq -r '.services[] | "\(.name)|\(.dockerfile)"' "$CONFIG_FILE")

  if (( missing > 0 )); then
    log_error "Existem ${missing} Dockerfiles ausentes. Corrija antes de continuar."
    exit 1
  fi
  log_success "Todos os Dockerfiles foram encontrados e passaram pela validação básica."
}

size_to_mb() {
  python3 - "$1" <<'PY'
import sys
value = sys.argv[1]
digits = ''.join(ch for ch in value if ch.isdigit() or ch == '.')
unit = ''.join(ch for ch in value if ch.isalpha()).upper() or 'MB'
if not digits:
    print("0")
    sys.exit()
num = float(digits)
if unit == 'GB':
    num *= 1024
elif unit == 'KB':
    num /= 1024
print(int(num))
PY
}

print_summary() {
  log_info "Calculando resumo e requisitos de build..."
  local base_count service_count total_images total_mb=0 size entry total_gb

  base_count=$(yq -r '.base_images | length' "$CONFIG_FILE")
  service_count=$(yq -r '.services | length' "$CONFIG_FILE")
  total_images=$((base_count + service_count))

  while read -r size; do
    [[ -z "$size" || "$size" == "null" ]] && continue
    total_mb=$(( total_mb + $(size_to_mb "$size") ))
  done < <(yq -r '.base_images | to_entries[].value.size_estimate' "$CONFIG_FILE")

  while read -r size; do
    [[ -z "$size" || "$size" == "null" ]] && continue
    total_mb=$(( total_mb + $(size_to_mb "$size") ))
  done < <(yq -r '.services[].size_estimate' "$CONFIG_FILE")

  total_gb=$(awk -v val="$total_mb" 'BEGIN {printf "%.2f", val/1024}')

  log_info "==================== RESUMO ===================="
  log_info "Imagens a construir : ${total_images} (bases=${base_count}, serviços=${service_count})"
  log_info "Espaço estimado     : ~${total_mb} MB (~${total_gb} GB)"
  log_info "Paralelismo sugerido: ${PARALLEL_JOBS} jobs"
  log_info "Arquivo com ordem   : ${TMP_DIR}/build-order.txt"
  log_info "Variáveis exportar  : source ${TMP_DIR}/build-env.sh"
  log_info "Tempo estimado      : ~3 minutos por serviço (total ~45min)"
  log_info "================================================="
}

main() {
  parse_args "$@"
  check_prerequisites
  load_config
  prepare_build_environment
  generate_build_order
  export_build_vars
  validate_dockerfiles
  print_summary
  log_success "Preparação concluída. Siga o guia manual 04-services-build-manual-guide.md para iniciar os builds."
  log_info "Próximos passos: executar docker builds conforme ordem definida e registrar progresso no SERVICES_BUILD_CHECKLIST.md."
}

main "$@"
