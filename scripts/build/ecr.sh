#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/docker.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../lib/aws.sh"

push_to_ecr() {
    local version="$1"
    local parallel_jobs="$2"
    shift 2
    local services=("$@")
    local env="${ENV:-dev}"
    local region="${AWS_REGION:-us-east-1}"

    log_section "PUSH TO ECR - Versão ${version}"

    local account_id
    account_id=$(aws_get_account_id)
    local registry="${account_id}.dkr.ecr.${region}.amazonaws.com"

    aws_ecr_login "$region" "$account_id"

    local pids=()
    for service in "${services[@]}"; do
        acquire_slot "$parallel_jobs"
        (
            push_service_to_ecr "$service" "$version" "$registry" "$env"
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

push_service_to_ecr() {
    local service="$1"
    local version="$2"
    local registry="$3"
    local env="$4"

    local local_image="neural-hive-mind/${service}:${version}"
    local ecr_repo="neural-hive-${env}/${service}"
    local ecr_image="${registry}/${ecr_repo}:${version}"

    if ! docker_check_image_exists "$local_image"; then
        log_error "Imagem local não encontrada: ${local_image}"
        return 1
    fi

    aws_ecr_create_repository "$ecr_repo"

    docker_tag "$local_image" "$ecr_image"
    docker_push "${ecr_repo}" "$version" "$registry" 3
}

docker_check_image_exists() {
    local image="$1"
    docker image inspect "$image" >/dev/null 2>&1
}

acquire_slot() {
    local max_jobs="$1"
    while [[ $(jobs -r | wc -l) -ge $max_jobs ]]; do
        sleep 0.5
    done
}
