#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECURITY_ROOT="${SECURITY_ROOT:-${SCRIPT_DIR}/security}"
SECURITY_MODULES_DIR="${SECURITY_MODULES_DIR:-${SECURITY_ROOT}/modules}"
export SECURITY_ROOT SECURITY_MODULES_DIR

source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/k8s.sh"
source "${SECURITY_ROOT}/lib/security-functions.sh"
source "${SECURITY_MODULES_DIR}/vault.sh"
source "${SECURITY_MODULES_DIR}/spire.sh"
source "${SECURITY_MODULES_DIR}/certificates.sh"
source "${SECURITY_MODULES_DIR}/secrets.sh"
source "${SECURITY_MODULES_DIR}/policies.sh"
source "${SECURITY_MODULES_DIR}/validation.sh"

show_help() {
    cat << 'EOF_HELP'
Neural Hive-Mind Security CLI

USAGE:
    ./scripts/security.sh <COMMAND> <SUBCOMMAND> [OPTIONS]

COMMANDS:
    vault       Operações HashiCorp Vault
    spire       Operações SPIRE (SPIFFE)
    certs       Operações certificados (cert-manager)
    secrets     Operações secrets management
    policies    Operações políticas OPA/Gatekeeper
    validate    Validações de segurança
    audit       Auditoria de segurança

VAULT SUBCOMMANDS:
    init        Inicializar Vault (auth, engines, policies, roles)
    configure   Configurar policies e roles específicos
    populate    Popular secrets
    pki         Configurar PKI engine
    deploy-ha   Deploy Vault HA
    backup      Backup Vault data
    restore     Restore Vault data
    audit       Audit logs Vault

SPIRE SUBCOMMANDS:
    deploy      Deploy SPIRE com Terraform + Helm
    register    Registrar workload entries
    validate    Validar SPIRE health e entries
    rotate      Rotacionar certificados SPIRE

CERTS SUBCOMMANDS:
    setup       Setup cert-manager
    generate    Gerar certificados
    rotate      Rotacionar certificados
    validate    Validar certificados (expiry, chain)

SECRETS SUBCOMMANDS:
    create      Criar secrets (Phase 1, Phase 2, custom)
    validate    Validar secrets existem e são válidos
    rotate      Rotacionar secrets
    backup      Backup secrets
    restore     Restore secrets

POLICIES SUBCOMMANDS:
    transition  Transicionar políticas warn → enforce
    validate    Validar enforcement de políticas
    audit       Auditar violações de políticas

VALIDATE SUBCOMMANDS:
    all         Validar todos componentes segurança
    vault       Validar Vault + SPIRE connectivity
    mtls        Validar mTLS connectivity
    oauth2      Validar OAuth2 flow
    policies    Validar policy enforcement
    namespace   Validar namespace isolation

AUDIT SUBCOMMANDS:
    vault       Audit logs Vault
    spire       Audit logs SPIRE
    policies    Audit violações políticas
    secrets     Audit acessos secrets
    report      Gerar relatório auditoria

EXAMPLES:
    # Vault
    ./scripts/security.sh vault init
    ./scripts/security.sh vault populate --mode static --environment dev
    ./scripts/security.sh vault backup --output /backup/vault.tar.gz

    # SPIRE
    ./scripts/security.sh spire deploy --namespace spire-system
    ./scripts/security.sh spire register --service orchestrator-dynamic

    # Certificates
    ./scripts/security.sh certs setup --environment production
    ./scripts/security.sh certs validate --check-expiry --days 30

    # Secrets
    ./scripts/security.sh secrets create --phase 2 --mode static
    ./scripts/security.sh secrets rotate --service orchestrator-dynamic

    # Policies
    ./scripts/security.sh policies transition --dry-run
    ./scripts/security.sh policies validate --type mtls

    # Validation
    ./scripts/security.sh validate all
    ./scripts/security.sh validate vault --dry-run

    # Audit
    ./scripts/security.sh audit vault --since 24h
    ./scripts/security.sh audit report --output /reports/security-audit.html

FLAGS:
    --dry-run           Executar em modo dry-run (sem aplicar mudanças)
    --namespace <ns>    Namespace Kubernetes
    --environment <env> Ambiente (dev, staging, production)
    --help, -h          Mostrar esta ajuda

DEPRECATED SCRIPTS:
    Os seguintes scripts foram consolidados neste CLI:
    - vault-init.sh → security.sh vault init
    - vault-configure-policies.sh → security.sh vault configure
    - vault-populate-secrets.sh → security.sh vault populate
    - deploy-spire.sh → security.sh spire deploy
    - spire-create-entries.sh → security.sh spire register
    - setup-cert-manager.sh → security.sh certs setup
    - create-phase2-secrets.sh → security.sh secrets create
    - transition-policies-to-enforce.sh → security.sh policies transition
EOF_HELP
}

GLOBAL_DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            GLOBAL_DRY_RUN="true"; shift ;;
        -h|--help)
            show_help; exit 0 ;;
        *)
            break ;;
    esac
done

DRY_RUN="${GLOBAL_DRY_RUN}"

COMMAND="${1:-}"; shift || true
if [[ -z "${COMMAND}" ]]; then
    show_help
    exit 1
fi

case "${COMMAND}" in
    vault)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            init)
                vault_init "$@" ;;
            configure)
                vault_configure "$@" ;;
            populate)
                local_mode="static"; local_env="dev"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --mode) local_mode="$2"; shift 2 ;;
                        --environment|--env) local_env="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                vault_populate "${local_mode}" "${local_env}" ;;
            pki)
                vault_pki "$@" ;;
            deploy-ha)
                vault_deploy_ha "$@" ;;
            backup)
                local_output="/tmp/vault-backup-$(date +%Y%m%d).tar.gz"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --output) local_output="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                vault_backup "${local_output}" ;;
            restore)
                local_input="${1:-}"
                if [[ -z "${local_input}" ]]; then
                    log_error "Informe --input <file>"
                    exit 1
                fi
                vault_restore "${local_input}" ;;
            audit)
                vault_audit "$@" ;;
            *)
                show_help ;;
        esac
        ;;
    spire)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            deploy)
                ns="${SPIRE_NAMESPACE}"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --namespace) ns="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                spire_deploy "${ns}" ;;
            register)
                service="${1:-all}"; shift || true
                spire_register "${service}" "$@" ;;
            validate)
                spire_validate "$@" ;;
            rotate)
                spire_rotate "$@" ;;
            *)
                show_help ;;
        esac
        ;;
    certs)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            setup)
                env="${1:-dev}"; shift || true
                certs_setup "${env}" "$@" ;;
            generate)
                type="${1:-self-signed}"; cn="${2:-neural-hive.local}"; shift 2 || true
                certs_generate "${type}" "${cn}" "$@" ;;
            rotate)
                service="${1:-}"; shift || true
                certs_rotate "${service}" "$@" ;;
            validate)
                check_expiry="true"; days="30"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --check-expiry) check_expiry="true"; shift ;;
                        --days) days="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                certs_validate "${check_expiry}" "${days}" ;;
            *) show_help ;;
        esac
        ;;
    secrets)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            create)
                phase="2"; mode="static"; env="dev"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --phase) phase="$2"; shift 2 ;;
                        --mode) mode="$2"; shift 2 ;;
                        --environment|--env) env="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                secrets_create "${phase}" "${mode}" "${env}" ;;
            validate)
                phase="2"; while [[ $# -gt 0 ]]; do case "$1" in --phase) phase="$2"; shift 2 ;; *) shift ;; esac; done
                secrets_validate "${phase}" ;;
            rotate)
                service=""; secret_name=""; namespace="default"; env="dev"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --service) service="$2"; shift 2 ;;
                        --secret-name) secret_name="$2"; shift 2 ;;
                        --namespace|-n) namespace="$2"; shift 2 ;;
                        --environment|--env) env="$2"; shift 2 ;;
                        *)
                            # Argumento posicional (retrocompatibilidade)
                            if [[ -z "${service}" ]]; then
                                service="$1"
                            elif [[ -z "${secret_name}" ]]; then
                                secret_name="$1"
                            fi
                            shift ;;
                    esac
                done
                if [[ -z "${service}" ]]; then
                    log_error "Erro: --service é obrigatório"
                    log_info "Uso: secrets rotate --service <nome> [--secret-name <nome>] [--namespace <ns>] [--environment <env>]"
                    exit 1
                fi
                [[ -z "${secret_name}" ]] && secret_name="${service}-secret"
                secrets_rotate "${service}" "${secret_name}" "${namespace}" "${env}" ;;
            backup)
                output="/tmp/secrets-backup-$(date +%Y%m%d).yaml"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --output) output="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                secrets_backup "${output}" ;;
            restore)
                input="${1:-}"; shift || true
                secrets_restore "${input}" ;;
            *) show_help ;;
        esac
        ;;
    policies)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            transition)
                dry="false"; threshold="10"; min_days="3"
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --dry-run) dry="true"; shift ;;
                        --threshold) threshold="$2"; shift 2 ;;
                        --min-days) min_days="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                policies_transition "${dry}" "${threshold}" "${min_days}" ;;
            validate)
                type="${1:-all}"; shift || true
                policies_validate "${type}" ;;
            audit)
                since="${1:-24h}"; shift || true
                policies_audit "${since}" ;;
            *) show_help ;;
        esac
        ;;
    validate)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            all) validation_all "$@" ;;
            vault) validation_vault "$@" ;;
            mtls) validation_mtls "$@" ;;
            oauth2) validation_oauth2 "$@" ;;
            policies) validation_policies "$@" ;;
            namespace) validation_namespace "$@" ;;
            *) show_help ;;
        esac
        ;;
    audit)
        SUBCOMMAND="${1:-}"; shift || true
        case "${SUBCOMMAND}" in
            vault) vault_audit "$@" ;;
            spire) spire_validate "$@" ;;
            policies) policies_audit "$@" ;;
            secrets)
                log_info "Auditando acessos a secrets"
                kubectl get events --all-namespaces | grep -i secret || true ;;
            report)
                output="${1:-/tmp/security-audit-$(date +%Y%m%d).html}"; shift || true
                mkdir -p "$(dirname "${output}")"
                cat > "${output}" <<'HTML'
<html><head><title>Security Audit Report</title></head><body>
<h1>Security Audit Report</h1>
<p>Generated by scripts/security.sh</p>
</body></html>
HTML
                log_success "Relatório gerado em ${output}" ;;
            *) show_help ;;
        esac
        ;;
    *)
        show_help ;;
 esac
