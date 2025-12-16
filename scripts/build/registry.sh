#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"

push_to_registry() {
    local version="$1"
    local parallel_jobs="$2"
    shift 2
    local services=("$@")
    local registry="${REGISTRY_URL:-37.60.241.150:30500}"

    log_section "PUSH TO REGISTRY - ${registry}"

    if ! check_registry_available "$registry"; then
        log_error "Registry indisponível: ${registry}"
        return 1
    fi

    local pids=()
    for service in "${services[@]}"; do
        acquire_slot "$parallel_jobs"
        (
            push_service_to_registry "$service" "$version" "$registry"
        ) &
        pids+=($!)
    done

    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait "$pid"; then
            failed=1
        fi
    done

    return $failed
}

check_registry_available() {
    local registry="$1"
    curl -sf "http://${registry}/v2/" >/dev/null
}

push_service_to_registry() {
    local service="$1"
    local version="$2"
    local registry="$3"

    local local_image="neural-hive-mind/${service}:${version}"
    local registry_image="${registry}/${service}:${version}"

    if ! docker image inspect "$local_image" >/dev/null 2>&1; then
        log_error "Imagem local não encontrada: ${local_image}"
        return 1
    fi

    docker_tag "$local_image" "$registry_image"
    retry 3 2 docker push "$registry_image"
}

acquire_slot() {
    local max_jobs="$1"
    while [[ $(jobs -r | wc -l) -ge $max_jobs ]]; do
        sleep 0.5
    done
}
