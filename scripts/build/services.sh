#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"

build_services_parallel() {
    local version="$1"
    local parallel_jobs="$2"
    shift 2

    local args=("$@")
    local last_index=$((${#args[@]}-1))
    local no_cache="${args[$last_index]}"
    unset 'args[$last_index]'
    local services=("${args[@]}")

    local semaphore_dir="/tmp/build-semaphore-$$"
    mkdir -p "$semaphore_dir"

    for service in "${services[@]}"; do
        acquire_slot "$parallel_jobs"
        (
            if build_service "$service" "$version" "$no_cache"; then
                echo "SUCCESS:${service}" > "${semaphore_dir}/${service}.status"
            else
                echo "FAILED:${service}" > "${semaphore_dir}/${service}.status"
            fi
        ) &
    done

    wait

    local failed=0
    for status_file in "${semaphore_dir}"/*.status; do
        [[ -e "$status_file" ]] || continue
        if grep -q "FAILED" "$status_file"; then
            log_error "$(cat "$status_file")"
            failed=1
        else
            log_success "$(cat "$status_file")"
        fi
    done

    rm -rf "$semaphore_dir"

    return $failed
}

acquire_slot() {
    local max_jobs="$1"
    while [[ $(jobs -r | wc -l) -ge $max_jobs ]]; do
        sleep 0.5
    done
}

build_service() {
    local service="$1"
    local version="$2"
    local no_cache="$3"

    local dockerfile="services/${service}/Dockerfile"
    if [[ ! -f "$dockerfile" ]]; then
        log_warn "Dockerfile não encontrado para ${service}, pulando"
        return 0
    fi

    local context_dir="services/${service}"
    log_info "Building service ${service}:${version}"

    docker_build "neural-hive-mind/${service}" "$version" "$dockerfile" "$context_dir" \
        "VERSION=${version}" "BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
        ${no_cache:+--no-cache}
}
