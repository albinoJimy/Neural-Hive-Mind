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

docker_push_with_fallback() {
    local source_image="$1"
    local image_name="$2"
    local tag="$3"
    local max_retries="${4:-3}"

    # Registry chain: Primary DNS → Secondary IP → ECR fallback
    local registries=(
        "${REGISTRY_PRIMARY:-registry.neural-hive.local:5000}"
        "${REGISTRY_SECONDARY:-37.60.241.150:30500}"
    )

    local pushed=false

    # Verify source image exists
    if ! docker image inspect "${source_image}" >/dev/null 2>&1; then
        log_error "Imagem fonte não encontrada: ${source_image}"
        return 1
    fi

    for registry in "${registries[@]}"; do
        local full_image="${registry}/${image_name}:${tag}"

        log_info "Tentando push para ${registry}..."

        # Check registry availability
        if ! curl -sf "http://${registry}/v2/" >/dev/null 2>&1; then
            log_warning "Registry ${registry} indisponível, tentando próximo..."
            continue
        fi

        # Tag from source image to registry target
        docker_tag "${source_image}" "${full_image}"

        # Try push with retry
        if retry "${max_retries}" 2 docker push "${full_image}"; then
            log_success "Push concluído para ${registry}"
            pushed=true
            break
        else
            log_warning "Push falhou para ${registry}, tentando próximo..."
        fi
    done

    # Fallback to ECR if all registries failed
    if [[ "${pushed}" == "false" ]] && [[ -n "${AWS_REGION:-}" ]]; then
        log_warning "Todos os registries falharam, tentando ECR como fallback..."

        local account_id
        account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")

        if [[ -n "${account_id}" ]]; then
            docker_login_ecr "${AWS_REGION}" "${account_id}"
            local ecr_image="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${image_name}:${tag}"
            docker_tag "${source_image}" "${ecr_image}"

            if retry "${max_retries}" 2 docker push "${ecr_image}"; then
                log_success "Push concluído para ECR (fallback)"
                pushed=true
            fi
        fi
    fi

    if [[ "${pushed}" == "false" ]]; then
        log_error "Push falhou em todos os registries disponíveis"
        return 1
    fi

    return 0
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
export -f docker_push docker_push_with_fallback docker_tag docker_push_parallel
export -f docker_login_ecr docker_login_registry
export -f docker_cleanup_dangling docker_cleanup_old_images docker_system_prune docker_get_disk_usage
