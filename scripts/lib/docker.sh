#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

docker_build() {
    local image_name="$1"
    local version="$2"
    local dockerfile_path="$3"
    local context="${4:-.}"
    shift 4

    local no_cache="false"
    local build_args=()
    for arg in "$@"; do
        if [[ "$arg" == "--no-cache" ]]; then
            no_cache="true"
        else
            build_args+=("$arg")
        fi
    done

    local tags=("-t" "${image_name}:${version}" "-t" "${image_name}:latest")
    local cache_flag=()
    [[ "${no_cache}" == "true" ]] && cache_flag+=(--no-cache)

    local build_args_flags=()
    for build_arg in "${build_args[@]}"; do
        build_args_flags+=(--build-arg "${build_arg}")
    done

    local log_file="${DOCKER_BUILD_LOG_FILE:-docker_build_${image_name//\//_}_${version}.log}"

    log_info "Iniciando build da imagem ${image_name}:${version} usando ${dockerfile_path} (contexto: ${context})"
    if [[ "${DOCKER_BUILD_SILENT:-false}" == "true" ]]; then
        DOCKER_BUILDKIT=1 docker build "${cache_flag[@]}" "${tags[@]}" -f "${dockerfile_path}" "${build_args_flags[@]}" "${context}" > "${log_file}" 2>&1
    else
        DOCKER_BUILDKIT=1 docker build "${cache_flag[@]}" "${tags[@]}" -f "${dockerfile_path}" "${build_args_flags[@]}" "${context}" | tee "${log_file}"
    fi
    local status=$?
    if [[ "${status}" -ne 0 ]]; then
        log_error "Build falhou: ${image_name}:${version} (ver ${log_file})"
        return "${status}"
    fi
    log_success "Build concluído: ${image_name}:${version} (logs em ${log_file})"
}

docker_build_base_image() {
    local image_name="$1"
    local dockerfile_path="$2"
    local context="${3:-.}"

    check_command_exists docker || return 1
    docker_build "${image_name}" "base" "${dockerfile_path}" "${context}"
}

docker_check_image_exists() {
    local image="$1"
    if docker image inspect "${image}" >/dev/null 2>&1; then
        log_debug "Imagem encontrada: ${image}"
        return 0
    fi
    return 1
}

docker_get_image_size() {
    local image="$1"
    docker image inspect "${image}" --format='{{.Size}}'
}

docker_get_image_id() {
    local image="$1"
    docker images --no-trunc -q "${image}" | head -n 1
}

docker_push() {
    local image_name="$1"
    local tag="$2"
    local registry="$3"
    local max_retries="${4:-3}"

    local full_image="${registry}/${image_name}:${tag}"

    log_info "Realizando push da imagem ${full_image}"
    retry "${max_retries}" 2 docker push "${full_image}"
    local digest
    digest=$(docker inspect --format='{{index .RepoDigests 0}}' "${full_image}" || true)
    log_success "Push concluído: ${full_image} ${digest}"
}

docker_tag() {
    local source_image="$1"
    local target_image="$2"
    docker tag "${source_image}" "${target_image}"
    log_success "Tag criada: ${source_image} -> ${target_image}"
}

docker_push_parallel() {
    local registry="$1"
    shift
    local pids=()

    for image_tag in "$@"; do
        docker_push "${image_tag%%:*}" "${image_tag##*:}" "${registry}" &
        pids+=($!)
    done

    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait "${pid}"; then
            failed=1
        fi
    done

    if [[ "${failed}" -ne 0 ]]; then
        log_error "Push paralelo falhou para uma ou mais imagens"
        return 1
    fi
    log_success "Push paralelo concluído"
}

docker_login_ecr() {
    local region="$1"
    local account_id="$2"
    local registry_url="${account_id}.dkr.ecr.${region}.amazonaws.com"

    log_info "Realizando login no ECR ${registry_url}"
    retry 3 2 aws ecr get-login-password --region "${region}" | docker login --username AWS --password-stdin "${registry_url}"
    log_success "Login no ECR concluído"
}

docker_login_registry() {
    local registry="$1"
    local username="$2"
    local password="$3"

    echo "${password}" | docker login "${registry}" --username "${username}" --password-stdin
    log_success "Login no registry ${registry} concluído"
}

docker_cleanup_dangling() {
    log_info "Removendo imagens dangling"
    docker image prune -f
}

docker_cleanup_old_images() {
    local days_old="${1:-30}"
    log_info "Removendo imagens com mais de ${days_old} dias"
    docker image prune -a --filter "until=${days_old}d" -f
}

docker_system_prune() {
    log_warning "Executando docker system prune -a"
    docker system prune -a -f
}

docker_get_disk_usage() {
    docker system df
}

export -f docker_build docker_build_base_image docker_check_image_exists docker_get_image_size docker_get_image_id
export -f docker_push docker_tag docker_push_parallel
export -f docker_login_ecr docker_login_registry
export -f docker_cleanup_dangling docker_cleanup_old_images docker_system_prune docker_get_disk_usage
