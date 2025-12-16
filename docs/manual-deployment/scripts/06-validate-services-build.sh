#!/usr/bin/env bash
# Valida as imagens construídas dos serviços Neural Hive-Mind
# Uso: ./06-validate-services-build.sh [--check-containerd] [--skip-health-checks] [--verbose] [--report-only]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ENV_DIR="${PROJECT_ROOT}/environments/local"
CONFIG_FILE="${SERVICES_BUILD_CONFIG:-${ENV_DIR}/services-build-config.yaml}"
LOG_DIR="${PROJECT_ROOT}/logs"
REPORT_FILE="${LOG_DIR}/services-build-validation-report.txt"

mkdir -p "$LOG_DIR"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

CHECK_CONTAINERD=false
SKIP_HEALTH_CHECKS=false
VERBOSE=false
REPORT_ONLY=false

BASE_IMAGE_NAMES=()
declare -A BASE_IMAGE_SIZE
SERVICE_NAMES=()
declare -A SERVICE_SIZE
declare -A SERVICE_PORT
declare -A SERVICE_HEALTH
declare -A SERVICE_DEPENDS

declare -A BASE_STATUS
declare -A SERVICE_STATUS
declare -A SERVICE_HEALTH_STATUS
declare -A SERVICE_HEALTH_ENABLED
declare -a REPORT_LINES

WARNINGS=0
ERRORS=0
PASSED=0
FAILED=0
TOTAL_STEPS=0
CURRENT_STEP=0

REGISTRY=""
VERSION=""
HEALTH_TIMEOUT=30
CONTAINERD_NAMESPACE="k8s.io"
CONTAINERD_MISSING=0
LAYER_WARN_THRESHOLD=45

usage() {
  cat <<'USO'
Uso: 06-validate-services-build.sh [opções]

Opções:
  --check-containerd     Valida importação no containerd (namespace k8s.io)
  --skip-health-checks   Pula execução de containers e verificações HTTP
  --verbose              Exibe saídas completas das validações
  --report-only          Apenas gera o relatório sem executar testes
  --help                 Exibe esta ajuda
USO
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --check-containerd) CHECK_CONTAINERD=true; shift ;;
      --skip-health-checks) SKIP_HEALTH_CHECKS=true; shift ;;
      --verbose) VERBOSE=true; shift ;;
      --report-only) REPORT_ONLY=true; shift ;;
      --help) usage; exit 0 ;;
      *) log_error "Opção desconhecida: $1"; usage; exit 1 ;;
    esac
  done
}

ensure_tools() {
  for cmd in docker yq jq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Comando obrigatório não encontrado: $cmd"
      exit 1
    fi
  done
  if [[ "$SKIP_HEALTH_CHECKS" = false ]]; then
    command -v curl >/dev/null 2>&1 || {
      log_error "curl é obrigatório para executar health checks."
      exit 1
    }
  fi
}

load_config() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    log_error "Arquivo de configuração não encontrado: $CONFIG_FILE"
    exit 1
  fi

  REGISTRY=$(yq -r '.build.registry // "neural-hive-mind"' "$CONFIG_FILE")
  VERSION=$(yq -r '.build.version // "1.0.0"' "$CONFIG_FILE")
  HEALTH_TIMEOUT=$(yq -r '.validation.health_check_timeout // 30' "$CONFIG_FILE")
  CONTAINERD_NAMESPACE=$(yq -r '.containerd.namespace // "k8s.io"' "$CONFIG_FILE")

  while IFS='|' read -r name size; do
    [[ -z "$name" || "$name" == "null" ]] && continue
    BASE_IMAGE_NAMES+=("$name")
    BASE_IMAGE_SIZE["$name"]="$size"
  done < <(yq -r '.base_images | to_entries[] | "\(.value.name)|\(.value.size_estimate)"' "$CONFIG_FILE")

  while IFS='|' read -r name size ports health depends health_enabled; do
    [[ -z "$name" || "$name" == "null" ]] && continue
    SERVICE_NAMES+=("$name")
    SERVICE_SIZE["$name"]="$size"
    SERVICE_HEALTH["$name"]="$health"
    SERVICE_DEPENDS["$name"]="$depends"
    SERVICE_HEALTH_ENABLED["$name"]="${health_enabled:-true}"
    local first_port
    first_port=$(echo "$ports" | jq -r '.[0] // empty')
    SERVICE_PORT["$name"]="${first_port}"
  done < <(yq -o=json '.services' "$CONFIG_FILE" | jq -r '.[] | "\(.name)|\(.size_estimate)|\(.ports)|\(.health_endpoint // "/health")|\(.depends_on // [])|\(.health_check_enabled // true)"')

  TOTAL_STEPS=$(( ${#BASE_IMAGE_NAMES[@]} + ${#SERVICE_NAMES[@]} + 4 ))
  if [[ "$CHECK_CONTAINERD" == true ]]; then
    TOTAL_STEPS=$((TOTAL_STEPS + 1))
  fi
}

progress() {
  local desc="$1"
  CURRENT_STEP=$((CURRENT_STEP + 1))
  local percent=$((CURRENT_STEP * 100 / TOTAL_STEPS))
  local filled=$((percent / 5))
  local empty=$((20 - filled))
  local filled_bar empty_bar
  filled_bar=$(printf "%${filled}s" "" | tr ' ' '#')
  empty_bar=$(printf "%${empty}s" "" | tr ' ' '-')
  echo -e "${BLUE}[${filled_bar}${empty_bar}]${NC} (${CURRENT_STEP}/${TOTAL_STEPS}) ${desc}"
}

size_to_mb() {
  python3 - "$1" <<'PY'
import sys
value = sys.argv[1] or ""
digits = ''.join(ch for ch in value if ch.isdigit() or ch == '.')
unit = ''.join(ch for ch in value if ch.isalpha()).upper()
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

record_result() {
  local label="$1"
  local status="$2"
  local message="$3"
  REPORT_LINES+=("[$status] ${label} - ${message}")
  case "$status" in
    PASS) PASSED=$((PASSED + 1)) ;;
    WARN) WARNINGS=$((WARNINGS + 1)) ;;
    FAIL) ERRORS=$((ERRORS + 1)); FAILED=$((FAILED + 1)) ;;
  esac
}

check_version_label() {
  local labels_json="$1"
  local entity="$2"
  local record_key="$3"
  local actual=""
  local label_name=""
  for key in "org.opencontainers.image.version" "version"; do
    actual=$(echo "$labels_json" | jq -r --arg k "$key" '.[$k] // empty' 2>/dev/null || echo "")
    if [[ -n "$actual" && "$actual" != "null" ]]; then
      label_name="$key"
      break
    fi
  done
  if [[ -z "$actual" || "$actual" == "null" ]]; then
    [[ "$VERBOSE" == true ]] && log_info "${entity} sem label de versão padronizada."
    return
  fi
  if [[ "$actual" != "$VERSION" ]]; then
    log_warn "Label ${label_name}=${actual} divergente em ${entity} (esperado ${VERSION})."
    record_result "$record_key" "WARN" "Label ${label_name}=${actual} (esperado ${VERSION})"
  fi
}

image_exists() {
  local ref="$1"
  docker image inspect "$ref" >/dev/null 2>&1
}

validate_base_images() {
  log_info "Validando imagens base..."
  for base in "${BASE_IMAGE_NAMES[@]}"; do
    progress "Base image ${base}"
    local image="${REGISTRY}/${base}:${VERSION}"
    if ! image_exists "$image"; then
      BASE_STATUS["$base"]="FAIL"
      log_error "Imagem não encontrada: ${image}"
      record_result "base:${base}" "FAIL" "Imagem ${image} ausente"
      continue
    fi
    if ! image_exists "${REGISTRY}/${base}:latest"; then
      log_warn "Tag latest ausente para ${base}"
      record_result "base:${base}" "WARN" "Tag latest não encontrada"
    fi
    local labels
    labels=$(docker inspect --format='{{json .Config.Labels}}' "$image" 2>/dev/null || echo "{}")
    check_version_label "$labels" "base ${base}" "base:${base}"

    local test_cmd status_msg
    case "$base" in
      python-ml-base)
        test_cmd=(python -c "import pip; print(pip.__version__)")
        ;;
      python-grpc-base)
        test_cmd=(python -c "import grpc; print(grpc.__version__)")
        ;;
      python-nlp-base)
        test_cmd=(python -c "import spacy; import pt_core_news_sm; import en_core_web_sm; print('OK')")
        ;;
      *)
        test_cmd=(python -c "print('noop')")
        ;;
    esac

    set +e
    docker run --rm "$image" "${test_cmd[@]}" >/dev/null 2>&1
    local exit_code=$?
    set -e
    if [[ $exit_code -ne 0 ]]; then
      BASE_STATUS["$base"]="FAIL"
      log_error "Teste funcional falhou para ${base}"
      record_result "base:${base}" "FAIL" "Teste funcional falhou"
    else
      BASE_STATUS["$base"]="PASS"
      log_success "Base ${base} validada."
      record_result "base:${base}" "PASS" "Imagem válida"
    fi
  done
}

run_health_check() {
  local name="$1"
  local image="$2"
  local port="$3"
  local endpoint="$4"
  local container_id host_port

  set +e
  container_id=$(docker run -d --rm -p 0:"${port}" "$image" 2>/dev/null)
  local run_status=$?
  set -e
  if [[ $run_status -ne 0 || -z "$container_id" ]]; then
    return 1
  fi
  sleep 5
  set +e
  host_port=$(docker inspect --format="{{(index .NetworkSettings.Ports \"${port}/tcp\" 0).HostPort}}" "$container_id" 2>/dev/null)
  local inspect_status=$?
  set -e
  if [[ $inspect_status -ne 0 || -z "$host_port" ]]; then
    docker stop "$container_id" >/dev/null 2>&1 || true
    return 1
  fi
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  local success=false
  while [[ $SECONDS -lt $deadline ]]; do
    if curl -fsS "http://127.0.0.1:${host_port}${endpoint}" >/dev/null 2>&1; then
      success=true
      break
    fi
    sleep 2
  done
  docker stop "$container_id" >/dev/null 2>&1 || true
  $success && return 0 || return 1
}

validate_service_images() {
  log_info "Validando imagens dos serviços..."
  for svc in "${SERVICE_NAMES[@]}"; do
    progress "Service image ${svc}"
    local svc_failed=false
    local image="${REGISTRY}/${svc}:${VERSION}"
    if ! image_exists "$image"; then
      SERVICE_STATUS["$svc"]="FAIL"
      log_error "Imagem não encontrada: ${image}"
      record_result "svc:${svc}" "FAIL" "Imagem ausente"
      continue
    fi
    if ! image_exists "${REGISTRY}/${svc}:latest"; then
      log_warn "Tag latest não encontrada para ${svc}"
      record_result "svc:${svc}" "WARN" "Tag latest ausente"
    fi

    local labels
    labels=$(docker inspect --format='{{json .Config.Labels}}' "$image" 2>/dev/null || echo "{}")
    check_version_label "$labels" "serviço ${svc}" "svc:${svc}"

    local entry
    entry=$(docker inspect --format='{{json .Config.Entrypoint}}' "$image")
    [[ "$VERBOSE" == true ]] && log_info "${svc} entrypoint: ${entry}"

    local actual_bytes actual_mb estimate_mb limit_mb
    actual_bytes=$(docker image inspect --format='{{.Size}}' "$image")
    actual_mb=$(awk -v bytes="$actual_bytes" 'BEGIN {printf "%.0f", bytes/1024/1024}')
    estimate_mb=$(size_to_mb "${SERVICE_SIZE[$svc]}")
    limit_mb=$((estimate_mb * 2))
    if (( actual_mb > limit_mb )); then
      log_warn "Imagem ${svc} excede limite (${actual_mb}MB > ${limit_mb}MB)."
      record_result "svc:${svc}" "WARN" "Tamanho acima do esperado (${actual_mb}MB)"
    fi

    local layer_count
    layer_count=$(docker image inspect --format='{{len .RootFS.Layers}}' "$image")
    REPORT_LINES+=("[INFO] layers:${svc} - ${layer_count} camadas")
    if (( layer_count > LAYER_WARN_THRESHOLD )); then
      log_warn "${svc} possui ${layer_count} camadas (>${LAYER_WARN_THRESHOLD})."
      record_result "svc:${svc}" "WARN" "Camadas excessivas (${layer_count})"
    fi

    local health_enabled="${SERVICE_HEALTH_ENABLED[$svc]:-true}"
    if [[ "$health_enabled" != "true" ]]; then
      SERVICE_HEALTH_STATUS["$svc"]="SKIPPED-CONFIG"
      record_result "health:${svc}" "PASS" "Health check desabilitado na configuração"
    elif [[ "$SKIP_HEALTH_CHECKS" == false && -n "${SERVICE_PORT[$svc]}" ]]; then
      if run_health_check "$svc" "$image" "${SERVICE_PORT[$svc]}" "${SERVICE_HEALTH[$svc]:-/health}"; then
        SERVICE_HEALTH_STATUS["$svc"]="PASS"
        record_result "health:${svc}" "PASS" "Health check OK"
      else
        SERVICE_HEALTH_STATUS["$svc"]="FAIL"
        svc_failed=true
        log_error "Health check falhou para ${svc}"
        record_result "health:${svc}" "FAIL" "Health check falhou"
      fi
    elif [[ "$SKIP_HEALTH_CHECKS" == true ]]; then
      SERVICE_HEALTH_STATUS["$svc"]="SKIPPED"
    else
      SERVICE_HEALTH_STATUS["$svc"]="NO-PORT"
    fi

    if [[ "$svc_failed" == true ]]; then
      SERVICE_STATUS["$svc"]="FAIL"
      record_result "svc:${svc}" "FAIL" "Falha em validações críticas"
    else
      SERVICE_STATUS["$svc"]="PASS"
      record_result "svc:${svc}" "PASS" "Imagem validada"
      log_success "${svc} validado."
    fi
  done
}

validate_disk_space() {
  progress "Validação de espaço em disco"
  local docker_df free_space path="/var/lib/docker" free_gb status="PASS"
  [[ -d "$path" ]] || path="/"

  docker_df=$(docker system df 2>/dev/null || true)
  free_space=$(df -h "$path" | awk 'NR==2 {print $4}')
  free_gb=$(df -BG "$path" | awk 'NR==2 {gsub("G","",$4); print $4}')
  log_info "Uso atual docker:\n${docker_df}"
  log_info "Espaço livre em /var/lib/docker: ${free_space}"
  if [[ -n "$free_gb" && "$free_gb" -lt 5 ]]; then
    log_warn "Apenas ${free_gb}GB livres em ${path}."
    status="WARN"
  fi
  record_result "disk-space" "$status" "Espaço livre ${free_space}"
}

validate_dependencies() {
  progress "Verificando dependências declaradas"
  for svc in "${SERVICE_NAMES[@]}"; do
    local deps="${SERVICE_DEPENDS[$svc]}"
    [[ -z "$deps" || "$deps" == "null" ]] && continue
    for dep in $(echo "$deps" | tr -d '[]" ' | tr ',' ' '); do
      [[ -z "$dep" ]] && continue
      if ! image_exists "${REGISTRY}/${dep}:${VERSION}"; then
        log_error "Dependência ${dep} ausente para ${svc}"
        record_result "deps:${svc}" "FAIL" "Dependência ${dep} não encontrada"
      fi
    done
  done
}

validate_containerd_import() {
  [[ "$CHECK_CONTAINERD" == true ]] || return
  progress "Validando imagens no containerd (${CONTAINERD_NAMESPACE})"
  local ctr_output
  if ! ctr_output=$(sudo ctr -n "${CONTAINERD_NAMESPACE}" images ls --quiet 2>/dev/null); then
    log_error "Falha ao listar imagens no containerd."
    record_result "containerd" "FAIL" "Não foi possível listar imagens via ctr"
    return
  fi
  local expected=("${BASE_IMAGE_NAMES[@]}" "${SERVICE_NAMES[@]}")
  local missing=0
  for name in "${expected[@]}"; do
    local ref="${REGISTRY}/${name}:${VERSION}"
    if ! grep -q "$ref" <<<"$ctr_output"; then
      log_warn "Imagem ausente no containerd: ${ref}"
      record_result "containerd:${name}" "WARN" "Imagem não encontrada no namespace ${CONTAINERD_NAMESPACE}"
      missing=$((missing + 1))
    fi
  done
  CONTAINERD_MISSING=$missing
  if (( missing == 0 )); then
    log_success "Todas as imagens encontradas no containerd."
    record_result "containerd" "PASS" "12 imagens presentes no namespace ${CONTAINERD_NAMESPACE}"
  fi
}

check_helm_values_compatibility() {
  progress "Validando valores dos Helm charts"
  for svc in "${SERVICE_NAMES[@]}"; do
    local values_file="${PROJECT_ROOT}/helm-charts/${svc}/values-local.yaml"
    if [[ ! -f "$values_file" ]]; then
      log_warn "Arquivo values-local.yaml não encontrado para ${svc}"
      record_result "helm:${svc}" "WARN" "values-local.yaml ausente"
      continue
    fi
    local repo tag pull_policy helm_ok=true
    repo=$(yq -r '.image.repository' "$values_file")
    tag=$(yq -r '.image.tag' "$values_file")
    pull_policy=$(yq -r '.image.pullPolicy' "$values_file")
    if [[ "$repo" != "${REGISTRY}/${svc}" ]]; then
      log_warn "Repository incorreto em ${values_file} (${repo})"
      record_result "helm:${svc}" "WARN" "Repository esperado ${REGISTRY}/${svc}"
      helm_ok=false
    fi
    if [[ "$tag" != "${VERSION}" ]]; then
      log_warn "Tag incorreta em ${values_file}: ${tag}"
      record_result "helm:${svc}" "WARN" "Tag esperada ${VERSION}"
      helm_ok=false
    fi
    if [[ "${pull_policy,,}" != "never" ]]; then
      log_warn "imagePullPolicy deve ser Never (${values_file})"
      record_result "helm:${svc}" "WARN" "imagePullPolicy != Never"
      helm_ok=false
    fi
    if [[ "$helm_ok" == true ]]; then
      record_result "helm:${svc}" "PASS" "values-local alinhado"
    fi
  done
}

generate_validation_report() {
  {
    echo "========================================"
    echo "RELATÓRIO DE VALIDAÇÃO - $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "Version: ${VERSION}   Registry: ${REGISTRY}"
    echo "========================================"
    for line in "${REPORT_LINES[@]}"; do
      echo "$line"
    done
    echo "========================================"
    echo "Total PASS: ${PASSED}"
    echo "Total WARN: ${WARNINGS}"
    echo "Total FAIL: ${ERRORS}"
  } >"$REPORT_FILE"
  log_success "Relatório salvo em ${REPORT_FILE}"
}

report_only_mode() {
  log_info "Modo report-only habilitado. Nenhum teste será executado."
  REPORT_LINES=("Report only mode: testes não executados.")
  generate_validation_report
  exit 0
}

final_summary() {
  local base_pass=0 svc_pass=0 health_pass=0
  for base in "${BASE_IMAGE_NAMES[@]}"; do
    [[ "${BASE_STATUS[$base]}" == "PASS" ]] && base_pass=$((base_pass + 1))
  done
  for svc in "${SERVICE_NAMES[@]}"; do
    [[ "${SERVICE_STATUS[$svc]}" == "PASS" ]] && svc_pass=$((svc_pass + 1))
    [[ "${SERVICE_HEALTH_STATUS[$svc]}" == "PASS" ]] && health_pass=$((health_pass + 1))
  done

  echo "========================================"
  echo "VALIDAÇÃO DE IMAGENS - RESUMO"
  echo "========================================"
  echo "✓ Base Images: ${base_pass}/${#BASE_IMAGE_NAMES[@]}"
  echo "✓ Service Images: ${svc_pass}/${#SERVICE_NAMES[@]}"
  if [[ "$SKIP_HEALTH_CHECKS" == true ]]; then
    echo "• Health Checks: SKIPPED (flag --skip-health-checks)"
  else
    echo "✓ Health Checks: ${health_pass}/${#SERVICE_NAMES[@]}"
  fi
  if [[ "$CHECK_CONTAINERD" == true ]]; then
    if (( CONTAINERD_MISSING > 0 )); then
      echo "⚠ Containerd Import: faltam ${CONTAINERD_MISSING} imagens"
    else
      echo "✓ Containerd Import: OK"
    fi
  fi
  echo "Warnings: ${WARNINGS}"
  echo "Failures: ${ERRORS}"
  if (( ERRORS == 0 )); then
    if (( WARNINGS == 0 )); then
      echo "========================================"
      echo "STATUS: PASS"
      echo "========================================"
    else
      echo "========================================"
      echo "STATUS: PASS (com warnings)"
      echo "========================================"
    fi
  else
    echo "========================================"
    echo "STATUS: FAIL"
    echo "========================================"
  fi
}

main() {
  parse_args "$@"
  ensure_tools
  load_config
  [[ "$REPORT_ONLY" == true ]] && report_only_mode
  validate_base_images
  validate_service_images
  validate_disk_space
  validate_dependencies
  check_helm_values_compatibility
  validate_containerd_import
  generate_validation_report
  final_summary

  if (( ERRORS > 0 )); then
    exit 1
  elif (( WARNINGS > 0 )); then
    exit 2
  else
    exit 0
  fi
}

main "$@"
