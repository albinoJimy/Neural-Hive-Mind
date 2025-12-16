# Bibliotecas Compartilhadas do Neural Hive-Mind

Bibliotecas compartilhadas para consolidar código duplicado em 20+ scripts.

## Visão Geral

- `common.sh`: Logging, cores, validações básicas e utilidades.
- `docker.sh`: Builds, push/tag, login e limpeza Docker.
- `k8s.sh`: Wrappers para kubectl, waits, port-forward e health checks.
- `aws.sh`: Operações STS, ECR, S3 e IAM.

## Uso Básico

```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/docker.sh"

log_info "Iniciando build..."
docker_build "my-image" "1.0.0" "Dockerfile" "."
log_success "Build concluído"
```

## `common.sh`

- `log_info/log_success/log_error/log_warning/log_debug/log_test/log_section/log_phase`: logging padronizado.  
  ```bash
  log_info "Mensagem"; log_success "Ok"; DEBUG=true log_debug "Detalhe"; log_test "Unit 1" "PASS" "Todos ok"
  ```
- `check_command_exists <cmd>`: verifica se o comando existe.  
  ```bash
  check_command_exists kubectl || exit 1
  ```
- `check_prerequisites`: valida docker, kubectl, aws, jq, curl, espaço em disco e conexões.  
  ```bash
  check_prerequisites
  ```
- `check_docker_running`, `check_kubectl_connection`, `check_disk_space`: verificações individuais.  
  ```bash
  check_disk_space
  ```
- `wait_for_condition "<cmd>" [timeout] [interval]`: espera comando ter sucesso.  
  ```bash
  wait_for_condition "kubectl get ns default" 60 5
  ```
- `retry <tentativas> <delay> <cmd...>`: retry exponencial.  
  ```bash
  retry 3 2 kubectl get pods
  ```
- `timeout_command <duracao> <cmd...>`: executa com timeout.  
  ```bash
  timeout_command 30s curl -I https://example.com
  ```
- `generate_random_string [len]`: string aleatória.  
  ```bash
  tmp="tmp-$(generate_random_string 6)"
  ```
- `timestamp`, `duration <inicio> <fim>`, `measure_execution_time <cmd...>`: utilidades de tempo.  
  ```bash
  start=$(date +%s); sleep 1; duration "$start" "$(date +%s)"
  ```

## `docker.sh`

- `docker_build <image> <versao> <dockerfile> <contexto> [build_args...] [--no-cache]`: build com BuildKit.  
  ```bash
  docker_build "repo/app" "1.2.3" "Dockerfile" "." "VERSION=1.2.3" --no-cache
  ```
- `docker_build_base_image <image> <dockerfile> [contexto]`: build base.  
  ```bash
  docker_build_base_image "repo/base" "Dockerfile.base"
  ```
- `docker_check_image_exists <image>` / `docker_get_image_size <image>` / `docker_get_image_id <image>`: inspeções.  
  ```bash
  docker_check_image_exists "alpine:latest"
  docker_get_image_size "alpine:latest"
  docker_get_image_id "alpine:latest"
  ```
- `docker_push <image> <tag> <registry> [retries]`: push com retry.  
  ```bash
  docker_push "repo/app" "1.2.3" "123.dkr.ecr.us-east-1.amazonaws.com" 3
  ```
- `docker_tag <src> <dst>`: cria tag.  
  ```bash
  docker_tag "repo/app:1.2.3" "repo/app:latest"
  ```
- `docker_push_parallel <registry> <image:tag...>`: push paralelo.  
  ```bash
  docker_push_parallel "123.dkr.ecr.us-east-1.amazonaws.com" "repo/app:1.2.3" "repo/base:1.2.3"
  ```
- `docker_login_ecr <region> <account_id>` / `docker_login_registry <registry> <user> <pass>`: login.  
  ```bash
  docker_login_ecr "us-east-1" "123456789012"
  ```
- `docker_cleanup_dangling`, `docker_cleanup_old_images [dias]`, `docker_system_prune`, `docker_get_disk_usage`: limpeza/uso.  
  ```bash
  docker_cleanup_dangling
  ```

## `k8s.sh`

- `k8s_namespace_exists/create/delete/label/detect_namespace`: gestão de namespaces.  
  ```bash
  k8s_create_namespace "neural-gateway"
  ```
- `k8s_get_pod_name/logs/wait_for_pod_ready/exec_in_pod/get_pod_status/get_pods_by_label`: operações de pods.  
  ```bash
  pod=$(k8s_get_pod_name default "app=gateway"); k8s_wait_for_pod_ready default "app=gateway" 120
  ```
- `k8s_resource_exists/apply_manifest/delete_resource/wait_for_resource/get_resource_status`: recursos genéricos.  
  ```bash
  k8s_apply_manifest "deploy.yaml"
  ```
- `k8s_port_forward <ns> <resource> <local> <remote> [retries]`: port-forward com PID retornado; `k8s_cleanup_port_forwards`, `k8s_check_port_forward_active <pid>`.  
  ```bash
  pf_pid=$(k8s_port_forward default svc/gateway 8080 80); k8s_cleanup_port_forwards
  ```
- `k8s_create_secret/k8s_secret_exists/k8s_delete_secret`: gestão de secrets.  
  ```bash
  k8s_create_secret default api-secret --from-literal=token=123
  ```
- `k8s_test_service_connectivity <ns> <url>` / `k8s_test_dns_resolution <ns> <host>`: checagens de conectividade.  
  ```bash
  k8s_test_service_connectivity default "http://gateway.default.svc.cluster.local/health"
  ```

## `aws.sh`

- `aws_check_credentials`: valida credenciais; `aws_get_account_id`, `aws_get_caller_identity`, `aws_get_region`: consultas STS/config.  
  ```bash
  aws_check_credentials && log_success "Credenciais ok"
  ```
- `aws_ecr_login <region> <account>` / `aws_ecr_repository_exists/create/get_registry_url/describe_images/get_image_digest`: operações ECR.  
  ```bash
  registry=$(aws_ecr_get_registry_url "$(aws_get_account_id)" "us-east-1")
  aws_ecr_repository_exists "repo-app" || aws_ecr_create_repository "repo-app"
  aws_ecr_describe_images "repo-app"
  aws_ecr_get_image_digest "repo-app" "latest"
  ```
- `aws_s3_bucket_exists/create_bucket/upload_file/download_file/list_objects`: utilidades S3.  
  ```bash
  aws_s3_create_bucket "neural-backups" "us-east-1"
  aws_s3_bucket_exists "neural-backups"
  aws_s3_upload_file "./artifact.tgz" "neural-backups" "artifacts/artifact.tgz"
  aws_s3_download_file "neural-backups" "artifacts/artifact.tgz" "/tmp/artifact.tgz"
  aws_s3_list_objects "neural-backups" "artifacts/"
  ```
- `aws_iam_user_exists <user>`, `aws_iam_role_exists <role>`, `aws_iam_get_user_policies <user>`: verificações IAM.  
  ```bash
  aws_iam_role_exists "neural-admin-role"
  aws_iam_get_user_policies "ci-user"
  ```
