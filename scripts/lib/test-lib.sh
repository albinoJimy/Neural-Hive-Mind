#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "${SCRIPT_DIR}/common.sh"

echo "=== Testando common.sh ==="
log_info "Teste de log_info"
log_success "Teste de log_success"
log_warning "Teste de log_warning"
log_error "Teste de log_error"
DEBUG=true log_debug "Teste de log_debug (DEBUG=true)"

check_command_exists docker && log_success "Docker encontrado" || log_error "Docker não encontrado"
check_command_exists kubectl && log_success "kubectl encontrado" || log_error "kubectl não encontrado"

source "${SCRIPT_DIR}/docker.sh"

echo "=== Testando docker.sh ==="
docker_check_image_exists "alpine:latest" && log_success "Imagem alpine existe" || log_warning "Imagem alpine não existe"

source "${SCRIPT_DIR}/k8s.sh"

echo "=== Testando k8s.sh ==="
k8s_namespace_exists "default" && log_success "Namespace default existe" || log_error "Namespace default não existe"

source "${SCRIPT_DIR}/aws.sh"

echo "=== Testando aws.sh ==="
if aws_check_credentials; then
    log_success "Credenciais AWS válidas"
    log_info "Account ID: $(aws_get_account_id)"
else
    log_warning "Credenciais AWS não configuradas"
fi
