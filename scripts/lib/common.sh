#!/usr/bin/env bash
set -euo pipefail

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

export RED GREEN YELLOW BLUE PURPLE CYAN NC

log_timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

log_info() {
    printf "%b[%s] [INFO] %s%b\n" "${BLUE}" "$(log_timestamp)" "$*" "${NC}" >&2
}

log_success() {
    printf "%b[%s] ✅ %s%b\n" "${GREEN}" "$(log_timestamp)" "$*" "${NC}" >&2
}

log_error() {
    printf "%b[%s] ❌ %s%b\n" "${RED}" "$(log_timestamp)" "$*" "${NC}" >&2
}

log_warning() {
    printf "%b[%s] ⚠️  %s%b\n" "${YELLOW}" "$(log_timestamp)" "$*" "${NC}" >&2
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        printf "%b[%s] [DEBUG] %s%b\n" "${PURPLE}" "$(log_timestamp)" "$*" "${NC}" >&2
    fi
}

log_test() {
    local test_name="$1"
    local status="$2"
    local details="${3:-}"

    local status_icon status_color
    case "${status}" in
        PASS) status_icon="✅"; status_color="${GREEN}" ;;
        FAIL) status_icon="❌"; status_color="${RED}" ;;
        *) status_icon="⚠️ "; status_color="${YELLOW}" ;;
    esac

    printf "%b[%s] [TEST] %s %s%b" "${status_color}" "$(log_timestamp)" "${test_name}" "${status_icon}" "${NC}" >&2
    [[ -n "${details}" ]] && printf " - %s" "${details}" >&2
    printf "\n" >&2
}

log_section() {
    printf "\n%b========== %s ==========%b\n" "${CYAN}" "$*" "${NC}" >&2
}

log_phase() {
    printf "\n%b========== %s ==========%b\n" "${BLUE}" "$*" "${NC}" >&2
}

check_command_exists() {
    command -v "$1" >/dev/null 2>&1
}

check_prerequisites() {
    local missing=0
    local commands=(docker kubectl aws jq curl)

    for cmd in "${commands[@]}"; do
        if ! check_command_exists "$cmd"; then
            log_error "Comando obrigatório não encontrado: $cmd"
            missing=1
        else
            log_debug "Comando encontrado: $cmd"
        fi
    done

    check_docker_running || missing=1
    check_kubectl_connection || missing=1
    check_disk_space || missing=1

    if [[ $missing -ne 0 ]]; then
        return 1
    fi

    log_success "Pré-requisitos verificados com sucesso"
}

# Build-focused prerequisites: only Docker (and AWS when pushing to ECR)
check_build_prerequisites() {
    local target="${1:-local}"
    local missing=0
    local commands=(docker)

    if [[ "${target}" == "ecr" || "${target}" == "all" ]]; then
        commands+=(aws)
    fi

    for cmd in "${commands[@]}"; do
        if ! check_command_exists "$cmd"; then
            log_error "Comando obrigatório não encontrado para build: $cmd"
            missing=1
        else
            log_debug "Comando encontrado: $cmd"
        fi
    done

    check_docker_running || missing=1

    if [[ $missing -ne 0 ]]; then
        return 1
    fi

    log_success "Pré-requisitos de build verificados com sucesso"
}

check_docker_running() {
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker não está em execução. Inicie o daemon do Docker."
        return 1
    fi
    log_debug "Docker daemon está em execução"
}

check_kubectl_connection() {
    if ! kubectl version --short >/dev/null 2>&1; then
        log_error "kubectl não consegue se conectar ao cluster."
        return 1
    fi
    log_debug "kubectl conectado ao cluster"
}

check_disk_space() {
    local required_kb=$((10 * 1024 * 1024)) # 10GB
    local available_kb
    available_kb=$(df -Pk . | awk 'NR==2 {print $4}')

    if [[ -z "${available_kb}" || "${available_kb}" -lt "${required_kb}" ]]; then
        log_error "Espaço em disco insuficiente. Necessário pelo menos 10GB livres."
        return 1
    fi
    log_debug "Espaço em disco suficiente: ${available_kb} KB disponíveis"
}

wait_for_condition() {
    local condition="$1"
    local timeout="${2:-60}"
    local interval="${3:-5}"
    local elapsed=0

    until eval "$condition"; do
        if [[ "${elapsed}" -ge "${timeout}" ]]; then
            log_error "Timeout após ${timeout}s aguardando condição: ${condition}"
            return 1
        fi
        sleep "${interval}"
        elapsed=$((elapsed + interval))
    done
    log_success "Condição satisfeita: ${condition}"
}

retry() {
    local max_attempts="${1:-3}"
    local delay="${2:-2}"
    shift 2

    local attempt=1
    until "$@"; do
        if (( attempt >= max_attempts )); then
            log_error "Comando falhou após ${attempt} tentativas: $*"
            return 1
        fi
        log_warning "Tentativa ${attempt} falhou. Retentando em ${delay}s..."
        sleep "${delay}"
        attempt=$((attempt + 1))
        delay=$((delay * 2))
    done
    log_success "Comando executado com sucesso após ${attempt} tentativas"
}

timeout_command() {
    local duration="$1"
    shift

    if command -v timeout >/dev/null 2>&1; then
        timeout "${duration}" "$@"
    else
        log_warning "timeout não disponível; executando comando sem timeout"
        "$@"
    fi
}

generate_random_string() {
    local length="${1:-12}"
    tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c "${length}"
}

timestamp() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

duration() {
    local start="$1"
    local end="$2"
    echo $(( end - start ))
}

measure_execution_time() {
    local start end
    start=$(date +%s)
    "$@"
    end=$(date +%s)
    duration "${start}" "${end}"
}

export -f log_timestamp log_info log_success log_error log_warning log_debug log_test log_section log_phase
export -f check_command_exists check_prerequisites check_docker_running check_kubectl_connection check_disk_space
export -f wait_for_condition retry timeout_command
export -f generate_random_string measure_execution_time timestamp duration
