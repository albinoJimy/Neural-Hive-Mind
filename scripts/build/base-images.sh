#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"

build_base_images() {
    local version="$1"
    local no_cache="$2"
    local skip="${3:-false}"

    [[ "$skip" == "true" ]] && {
        log_info "Skipping base images build"
        return 0
    }

    local base_images=(
        "python-ml-base"
        "python-grpc-base"
        "python-mlops-base"
        "python-nlp-base"
        "python-specialist-base"
    )

    for image in "${base_images[@]}"; do
        local dockerfile="base-images/${image}/Dockerfile"
        [[ ! -f "$dockerfile" ]] && {
            log_warn "Dockerfile not found for ${image}, skipping"
            continue
        }

        log_info "Building base image ${image}:${version}"
        docker_build "neural-hive-mind/${image}" "$version" "$dockerfile" "." \
            "VERSION=${version}" "BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
            ${no_cache:+--no-cache}
    done
}
