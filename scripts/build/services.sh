#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"

# Carregar métricas se disponível
METRICS_ENABLED="${PUSH_METRICS:-false}"
if [[ "$METRICS_ENABLED" == "true" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/../lib/metrics.sh" ]]; then
    source "$(dirname "${BASH_SOURCE[0]}")/../lib/metrics.sh"
fi

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

    # Use project root as context - Dockerfiles expect 'COPY services/SERVICE/...'
    local context_dir="."
    log_info "Building service ${service}:${version}"

    # Iniciar timer para métricas
    local start_time
    start_time=$(date +%s)

    # Configurar log file para métricas de cache
    export DOCKER_BUILD_LOG_FILE="/tmp/docker-build-${service}.log"

    local build_result=0
    docker_build "neural-hive-mind/${service}" "$version" "$dockerfile" "$context_dir" \
        "VERSION=${version}" "BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
        ${no_cache:+--no-cache} || build_result=$?

    # Coletar métricas se habilitado
    if [[ "$METRICS_ENABLED" == "true" ]]; then
        local end_time
        end_time=$(date +%s)
        local duration=$((end_time - start_time))

        # Salvar métrica de duração
        local metrics_file="${METRICS_DIR:-/tmp}/build-metrics-${service}.json"
        mkdir -p "$(dirname "$metrics_file")"
        printf '{"name":"build_duration_seconds","value":"%s","labels":"service=%s,success=%s","timestamp":"%s"}\n' \
            "$duration" "$service" "$([[ $build_result -eq 0 ]] && echo "true" || echo "false")" "$(date +%s)" >> "$metrics_file"

        # Coletar tamanho da imagem se build bem-sucedido
        if [[ $build_result -eq 0 ]]; then
            local size
            size=$(docker image inspect "neural-hive-mind/${service}:${version}" --format='{{.Size}}' 2>/dev/null || echo "0")
            printf '{"name":"build_image_size_bytes","value":"%s","labels":"service=%s,version=%s","timestamp":"%s"}\n' \
                "$size" "$service" "$version" "$(date +%s)" >> "$metrics_file"
        fi
    fi

    return $build_result
}
