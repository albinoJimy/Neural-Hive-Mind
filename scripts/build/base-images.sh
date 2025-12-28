#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"

build_base_image() {
    local image="$1"
    local version="$2"
    local no_cache="$3"

    local dockerfile="base-images/${image}/Dockerfile"
    [[ ! -f "$dockerfile" ]] && {
        log_warn "Dockerfile not found for ${image}, skipping"
        return 0
    }

    log_info "Building base image ${image}:${version}"
    docker_build "neural-hive-mind/${image}" "$version" "$dockerfile" "." \
        "VERSION=${version}" "BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
        ${no_cache:+--no-cache}
}

build_base_images_parallel() {
    local version="$1"
    local no_cache="$2"

    log_section "Building base images in parallel groups"

    # Group 1: Independent bases (parallel)
    log_info "Group 1: Building python-ml-base and python-observability-base in parallel"
    build_base_image "python-ml-base" "$version" "$no_cache" &
    local pid_ml=$!
    build_base_image "python-observability-base" "$version" "$no_cache" &
    local pid_obs=$!

    wait $pid_ml || { log_error "python-ml-base failed"; return 1; }
    wait $pid_obs || { log_error "python-observability-base failed"; return 1; }
    log_success "Group 1 completed"

    # Group 2: Depends on python-ml-base
    log_info "Group 2: Building python-grpc-base"
    build_base_image "python-grpc-base" "$version" "$no_cache" || return 1
    log_success "Group 2 completed"

    # Group 3: Depends on python-grpc-base (parallel)
    log_info "Group 3: Building python-mlops-base and python-nlp-base in parallel"
    build_base_image "python-mlops-base" "$version" "$no_cache" &
    local pid_mlops=$!
    build_base_image "python-nlp-base" "$version" "$no_cache" &
    local pid_nlp=$!

    wait $pid_mlops || { log_error "python-mlops-base failed"; return 1; }
    wait $pid_nlp || { log_error "python-nlp-base failed"; return 1; }
    log_success "Group 3 completed"

    # Group 4: Depends on python-nlp-base
    log_info "Group 4: Building python-specialist-base"
    build_base_image "python-specialist-base" "$version" "$no_cache" || return 1
    log_success "Group 4 completed"
}

build_base_images() {
    local version="$1"
    local no_cache="$2"
    local skip="${3:-false}"

    [[ "$skip" == "true" ]] && {
        log_info "Skipping base images build"
        return 0
    }

    build_base_images_parallel "$version" "$no_cache"
}
