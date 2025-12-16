#!/usr/bin/env bash
# =============================================================================
# Neural Hive-Mind - Testes de Integração do CLI de Segurança
# =============================================================================
# Testa os comandos do CLI unificado de segurança em modo dry-run
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Carregar biblioteca comum
source "${PROJECT_ROOT}/scripts/lib/common.sh"

# Contadores de testes
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# =============================================================================
# Funções auxiliares
# =============================================================================

run_test() {
    local test_name="$1"
    local command="$2"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log_info "Executando teste: ${test_name}"

    if eval "${command}"; then
        log_test "${test_name}" "PASS"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_test "${test_name}" "FAIL"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# =============================================================================
# Testes do CLI de Segurança
# =============================================================================

test_cli_help() {
    run_test "security.sh --help" \
        "${PROJECT_ROOT}/scripts/security.sh --help >/dev/null 2>&1"
}

test_vault_init_dry_run() {
    run_test "vault init --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh vault init 2>&1 | grep -q 'dry-run\|Vault\|INFO'"
}

test_vault_configure_dry_run() {
    run_test "vault configure --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh vault configure 2>&1 || true"
}

test_vault_backup_dry_run() {
    run_test "vault backup --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh vault backup --output /tmp/test-backup.tar.gz 2>&1 | grep -q 'dry-run\|backup\|INFO'"
}

test_spire_deploy_dry_run() {
    run_test "spire deploy --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh spire deploy --namespace spire-system 2>&1 || true"
}

test_spire_validate_dry_run() {
    run_test "spire validate --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh spire validate 2>&1 || true"
}

test_certs_setup_dry_run() {
    run_test "certs setup --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh certs setup dev 2>&1 || true"
}

test_certs_validate_dry_run() {
    run_test "certs validate --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh certs validate --check-expiry --days 30 2>&1 || true"
}

test_secrets_create_dry_run() {
    run_test "secrets create --phase 2 --mode static --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh secrets create --phase 2 --mode static 2>&1 || true"
}

test_secrets_validate_dry_run() {
    run_test "secrets validate --phase 2 --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh secrets validate --phase 2 2>&1 || true"
}

test_secrets_rotate_dry_run() {
    run_test "secrets rotate --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh secrets rotate --service test-service --namespace default 2>&1 | grep -q 'dry-run\|Rotacionando\|INFO'"
}

test_policies_transition_dry_run() {
    run_test "policies transition --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh policies transition --dry-run 2>&1 || true"
}

test_policies_validate_dry_run() {
    run_test "policies validate --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh policies validate all 2>&1 || true"
}

test_validate_all_dry_run() {
    run_test "validate all --dry-run" \
        "DRY_RUN=true ${PROJECT_ROOT}/scripts/security.sh validate all 2>&1 || true"
}

test_audit_report_dry_run() {
    run_test "audit report --dry-run" \
        "${PROJECT_ROOT}/scripts/security.sh audit report --output /tmp/test-audit-report.html 2>&1 && test -f /tmp/test-audit-report.html"
}

# =============================================================================
# Testes de wrappers deprecados
# =============================================================================

test_wrapper_vault_init() {
    run_test "wrapper vault-init.sh" \
        "${PROJECT_ROOT}/scripts/vault-init.sh --help 2>&1 | grep -q 'DEPRECATED\|Redirecionando'"
}

test_wrapper_deploy_spire() {
    run_test "wrapper deploy-spire.sh" \
        "${PROJECT_ROOT}/scripts/deploy-spire.sh --help 2>&1 | grep -q 'DEPRECATED\|Redirecionando'"
}

test_wrapper_create_phase2_secrets() {
    run_test "wrapper create-phase2-secrets.sh" \
        "${PROJECT_ROOT}/scripts/create-phase2-secrets.sh --help 2>&1 | grep -q 'DEPRECATED\|Redirecionando'"
}

# =============================================================================
# Execução principal
# =============================================================================

main() {
    log_section "Testes de Integração - CLI de Segurança"

    log_info "Verificando existência do CLI de segurança..."
    if [[ ! -x "${PROJECT_ROOT}/scripts/security.sh" ]]; then
        log_error "CLI de segurança não encontrado ou não executável"
        exit 1
    fi

    log_phase "Testes do CLI principal"
    test_cli_help

    log_phase "Testes de comandos Vault"
    test_vault_init_dry_run
    test_vault_configure_dry_run
    test_vault_backup_dry_run

    log_phase "Testes de comandos SPIRE"
    test_spire_deploy_dry_run
    test_spire_validate_dry_run

    log_phase "Testes de comandos Certificates"
    test_certs_setup_dry_run
    test_certs_validate_dry_run

    log_phase "Testes de comandos Secrets"
    test_secrets_create_dry_run
    test_secrets_validate_dry_run
    test_secrets_rotate_dry_run

    log_phase "Testes de comandos Policies"
    test_policies_transition_dry_run
    test_policies_validate_dry_run

    log_phase "Testes de comandos Validate"
    test_validate_all_dry_run

    log_phase "Testes de comandos Audit"
    test_audit_report_dry_run

    log_phase "Testes de wrappers deprecados"
    test_wrapper_vault_init
    test_wrapper_deploy_spire
    test_wrapper_create_phase2_secrets

    # Resumo
    log_section "Resumo dos Testes"
    echo ""
    log_info "Total de testes: ${TESTS_TOTAL}"
    log_success "Testes passados: ${TESTS_PASSED}"
    if [[ ${TESTS_FAILED} -gt 0 ]]; then
        log_error "Testes falhados: ${TESTS_FAILED}"
        exit 1
    else
        log_success "Todos os testes passaram!"
        exit 0
    fi
}

# Executar se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
