#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

aws_check_credentials() {
    aws sts get-caller-identity >/dev/null 2>&1
}

aws_get_account_id() {
    aws sts get-caller-identity --query "Account" --output text
}

aws_get_caller_identity() {
    aws sts get-caller-identity --query "Arn" --output text
}

aws_get_region() {
    aws configure get region
}

aws_ecr_login() {
    local region="$1"
    local account_id="$2"
    local registry_url
    registry_url="${account_id}.dkr.ecr.${region}.amazonaws.com"

    log_info "Realizando login no ECR ${registry_url}"
    retry 3 2 aws ecr get-login-password --region "${region}" | docker login --username AWS --password-stdin "${registry_url}"
    log_success "Login no ECR concluído"
}

aws_ecr_repository_exists() {
    local repository="$1"
    aws ecr describe-repositories --repository-names "${repository}" >/dev/null 2>&1
}

aws_ecr_create_repository() {
    local repository="$1"
    log_info "Criando repositório ECR ${repository} se não existir"
    aws_ecr_repository_exists "${repository}" || aws ecr create-repository --repository-name "${repository}" >/dev/null
}

aws_ecr_get_registry_url() {
    local account_id="$1"
    local region="$2"
    echo "${account_id}.dkr.ecr.${region}.amazonaws.com"
}

aws_ecr_describe_images() {
    local repository="$1"
    aws ecr describe-images --repository-name "${repository}"
}

aws_ecr_get_image_digest() {
    local repository="$1"
    local tag="$2"
    aws ecr describe-images --repository-name "${repository}" --image-ids imageTag="${tag}" --query "imageDetails[0].imageDigest" --output text
}

aws_s3_bucket_exists() {
    local bucket="$1"
    aws s3api head-bucket --bucket "${bucket}" >/dev/null 2>&1
}

aws_s3_create_bucket() {
    local bucket="$1"
    local region="${2:-$(aws_get_region)}"

    log_info "Criando bucket S3 ${bucket} na região ${region}"
    if [[ "${region}" == "us-east-1" ]]; then
        aws s3api create-bucket --bucket "${bucket}" >/dev/null
    else
        aws s3api create-bucket --bucket "${bucket}" --create-bucket-configuration LocationConstraint="${region}" >/dev/null
    fi
}

aws_s3_upload_file() {
    local file_path="$1"
    local bucket="$2"
    local key="$3"
    aws s3 cp "${file_path}" "s3://${bucket}/${key}"
}

aws_s3_download_file() {
    local bucket="$1"
    local key="$2"
    local destination="$3"
    aws s3 cp "s3://${bucket}/${key}" "${destination}"
}

aws_s3_list_objects() {
    local bucket="$1"
    local prefix="${2:-}"
    aws s3 ls "s3://${bucket}/${prefix}"
}

aws_iam_user_exists() {
    local user="$1"
    aws iam get-user --user-name "${user}" >/dev/null 2>&1
}

aws_iam_role_exists() {
    local role="$1"
    aws iam get-role --role-name "${role}" >/dev/null 2>&1
}

aws_iam_get_user_policies() {
    local user="$1"
    aws iam list-attached-user-policies --user-name "${user}"
}

export -f aws_check_credentials aws_get_account_id aws_get_caller_identity aws_get_region
export -f aws_ecr_login aws_ecr_repository_exists aws_ecr_create_repository aws_ecr_get_registry_url aws_ecr_describe_images aws_ecr_get_image_digest
export -f aws_s3_bucket_exists aws_s3_create_bucket aws_s3_upload_file aws_s3_download_file aws_s3_list_objects
export -f aws_iam_user_exists aws_iam_role_exists aws_iam_get_user_policies
