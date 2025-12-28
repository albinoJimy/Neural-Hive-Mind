#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/base-images.sh"
source "$(dirname "${BASH_SOURCE[0]}")/services.sh"
source "$(dirname "${BASH_SOURCE[0]}")/changed-services.sh"

# Carregar smart-build se habilitado
if [[ "${SMART_BUILD:-false}" == "true" ]]; then
    source "$(dirname "${BASH_SOURCE[0]}")/smart-build.sh"
fi

# Global variable to store actually built services
BUILT_SERVICES=()

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

    # Detecção de mudanças
    if [[ "${BUILD_CHANGED_ONLY:-false}" == "true" ]]; then
        log_info "Modo incremental: detectando mudanças..."
        local changed_services
        changed_services=$(get_services_to_build "HEAD~1" "${services[@]}")

        if [[ -z "$changed_services" ]]; then
            log_success "Nenhum serviço modificado - nada a buildar"
            BUILT_SERVICES=()
            return 0
        fi

        # Atualiza lista de serviços
        readarray -t services <<< "$changed_services"
        log_info "Serviços a buildar (${#services[@]}): ${services[*]}"
    fi

    check_disk_space
    build_base_images "$version" "$no_cache" "$skip_base"

    # Usar smart build se habilitado
    if [[ "${SMART_BUILD:-false}" == "true" ]]; then
        log_info "Modo Smart Build habilitado (retry + fallback)"
        build_services_parallel_smart "$version" "$parallel_jobs" "${services[@]}" "$no_cache"
    else
        build_services_parallel "$version" "$parallel_jobs" "${services[@]}" "$no_cache"
    fi

    # Export list of actually built services
    BUILT_SERVICES=("${services[@]}")

    log_info "Serviços buildados: ${services[*]}"
    log_success "Build local concluído"
}

# Returns the list of services that were actually built
get_built_services() {
    printf '%s\n' "${BUILT_SERVICES[@]}"
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
