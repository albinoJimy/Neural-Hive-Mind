#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/base-images.sh"
source "$(dirname "${BASH_SOURCE[0]}")/services.sh"

build_local() {
    local version="$1"
    local parallel_jobs="$2"
    shift 2
    local args=("$@")
    local last_index=$((${#args[@]}-1))
    local skip_base="${args[$last_index]}"
    local no_cache_index=$((last_index-1))
    local no_cache="${args[$no_cache_index]}"
    local services=("${args[@]:0:$no_cache_index}")

    log_section "BUILD LOCAL - Versão ${version}"

    check_disk_space
    build_base_images "$version" "$no_cache" "$skip_base"
    build_services_parallel "$version" "$parallel_jobs" "${services[@]}" "$no_cache"

    log_info "Serviços buildados: ${services[*]}"
    log_success "Build local concluído"
}

check_disk_space() {
    local threshold_mb="${MIN_DISK_MB:-2048}"
    local available_mb
    available_mb=$(df -Pm . | awk 'NR==2 {print $4}')

    if (( available_mb < threshold_mb )); then
        log_error "Espaço em disco insuficiente: ${available_mb}MB disponíveis, requerido >= ${threshold_mb}MB"
        exit 1
    fi

    log_info "Espaço em disco disponível: ${available_mb}MB"
}
