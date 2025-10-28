#!/bin/bash
# Script para transição automática de políticas OPA de modo 'warn' para 'enforce'
# Verifica idade das políticas e histórico de violações antes da transição

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="/tmp/opa-policies-backup-$(date +%Y%m%d-%H%M%S)"
MAX_VIOLATION_THRESHOLD=10  # Máximo de violações para permitir transição
MIN_DAYS_IN_WARN=3          # Mínimo de dias em modo warn antes da transição
DRY_RUN="${DRY_RUN:-false}" # Modo dry-run por padrão

# Funções auxiliares
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_dry_run() {
    echo -e "${YELLOW}[DRY-RUN]${NC} $1"
}

# Função para verificar se kubectl está disponível
check_prerequisites() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi

    log_success "Pré-requisitos verificados"
}

# Criar backup das configurações atuais
create_backup() {
    log_info "Criando backup das políticas atuais..."

    mkdir -p "$BACKUP_DIR"

    # Backup de constraints
    for constraint_type in neuralhivemtlsrequired neuralhiveimagesignature; do
        if kubectl get "$constraint_type" &>/dev/null; then
            kubectl get "$constraint_type" -o yaml > "$BACKUP_DIR/${constraint_type}-constraints.yaml"
            log_info "✓ Backup criado: ${constraint_type}-constraints.yaml"
        fi
    done

    # Backup de constraint templates
    if kubectl get constrainttemplates &>/dev/null; then
        kubectl get constrainttemplates -o yaml > "$BACKUP_DIR/constraint-templates.yaml"
        log_info "✓ Backup criado: constraint-templates.yaml"
    fi

    log_success "Backup criado em: $BACKUP_DIR"
}

# Verificar idade da política baseada em annotation
check_policy_age() {
    local constraint_name="$1"
    local constraint_type="$2"

    local creation_date=$(kubectl get "$constraint_type" "$constraint_name" -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null)
    if [[ -z "$creation_date" ]]; then
        log_warning "Não foi possível obter data de criação para $constraint_name"
        return 1
    fi

    # Converter data de criação para timestamp
    local creation_timestamp=$(date -d "$creation_date" +%s)
    local current_timestamp=$(date +%s)
    local age_days=$(( (current_timestamp - creation_timestamp) / 86400 ))

    log_info "Política $constraint_name tem $age_days dias de idade"

    if [[ $age_days -lt $MIN_DAYS_IN_WARN ]]; then
        log_warning "Política $constraint_name muito recente ($age_days dias < $MIN_DAYS_IN_WARN dias)"
        return 1
    fi

    return 0
}

# Verificar histórico de violações
check_violation_history() {
    local constraint_name="$1"
    local constraint_type="$2"

    local total_violations=$(kubectl get "$constraint_type" "$constraint_name" -o jsonpath='{.status.totalViolations}' 2>/dev/null || echo "0")

    log_info "Política $constraint_name tem $total_violations violações totais"

    if [[ "$total_violations" -gt $MAX_VIOLATION_THRESHOLD ]]; then
        log_warning "Muitas violações para $constraint_name ($total_violations > $MAX_VIOLATION_THRESHOLD)"
        log_warning "Recomenda-se resolver violações antes de ativar enforce mode"
        return 1
    fi

    # Verificar violações recentes via eventos
    local recent_violations=$(kubectl get events -A --field-selector reason=ConstraintViolation | grep "$constraint_name" | wc -l)
    log_info "Violações recentes (eventos): $recent_violations"

    if [[ "$recent_violations" -gt 5 ]]; then
        log_warning "Muitas violações recentes para $constraint_name"
        return 1
    fi

    return 0
}

# Transicionar política específica para enforce
transition_policy_to_enforce() {
    local constraint_name="$1"
    local constraint_type="$2"

    log_info "Processando transição: $constraint_name ($constraint_type)"

    # Verificar se está em modo warn
    local current_action=$(kubectl get "$constraint_type" "$constraint_name" -o jsonpath='{.spec.enforcementAction}' 2>/dev/null)
    if [[ "$current_action" != "warn" ]]; then
        log_info "Política $constraint_name já está em modo: $current_action"
        return 0
    fi

    # Verificar idade da política
    if ! check_policy_age "$constraint_name" "$constraint_type"; then
        log_warning "Política $constraint_name não é elegível para transição (muito recente)"
        return 1
    fi

    # Verificar histórico de violações
    if ! check_violation_history "$constraint_name" "$constraint_type"; then
        log_warning "Política $constraint_name não é elegível para transição (muitas violações)"
        return 1
    fi

    # Fazer a transição
    log_info "Política $constraint_name é elegível para transição warn → enforce"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "Transicionaria $constraint_name de 'warn' para 'enforce'"
        return 0
    fi

    # Aplicar patch para mudar enforcementAction
    local patch='{"spec":{"enforcementAction":"enforce"}}'
    if kubectl patch "$constraint_type" "$constraint_name" --type='merge' -p "$patch"; then
        log_success "✓ $constraint_name transicionado para enforce mode"

        # Adicionar annotation com data da transição
        local transition_annotation='{"metadata":{"annotations":{"gatekeeper.sh/policy-transition-date":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}}}'
        kubectl patch "$constraint_type" "$constraint_name" --type='merge' -p "$transition_annotation" || log_warning "Falha ao adicionar annotation de transição"

        return 0
    else
        log_error "Falha ao transicionar $constraint_name"
        return 1
    fi
}

# Processar todas as políticas elegíveis
process_all_policies() {
    log_info "Processando todas as políticas para transição..."

    local total_processed=0
    local total_transitioned=0
    local total_skipped=0

    # Processar constraints mTLS
    if kubectl get neuralhivemtlsrequired &>/dev/null; then
        for constraint in $(kubectl get neuralhivemtlsrequired -o jsonpath='{.items[*].metadata.name}'); do
            total_processed=$((total_processed + 1))
            if transition_policy_to_enforce "$constraint" "neuralhivemtlsrequired"; then
                total_transitioned=$((total_transitioned + 1))
            else
                total_skipped=$((total_skipped + 1))
            fi
        done
    else
        log_warning "Nenhum constraint mTLS encontrado"
    fi

    # Processar constraints de assinatura de imagem
    if kubectl get neuralhiveimagesignature &>/dev/null; then
        for constraint in $(kubectl get neuralhiveimagesignature -o jsonpath='{.items[*].metadata.name}'); do
            total_processed=$((total_processed + 1))
            if transition_policy_to_enforce "$constraint" "neuralhiveimagesignature"; then
                total_transitioned=$((total_transitioned + 1))
            else
                total_skipped=$((total_skipped + 1))
            fi
        done
    else
        log_warning "Nenhum constraint de assinatura de imagem encontrado"
    fi

    # Relatório final
    log_info "=========================================="
    log_info "RESUMO DA TRANSIÇÃO:"
    log_info "Políticas processadas: $total_processed"
    log_info "Políticas transicionadas: $total_transitioned"
    log_info "Políticas puladas: $total_skipped"
    log_info "=========================================="

    return 0
}

# Validar que transição foi bem-sucedida
validate_transition() {
    log_info "Validando transições realizadas..."

    local validation_errors=0

    # Verificar constraints mTLS
    if kubectl get neuralhivemtlsrequired &>/dev/null; then
        for constraint in $(kubectl get neuralhivemtlsrequired -o jsonpath='{.items[*].metadata.name}'); do
            local action=$(kubectl get neuralhivemtlsrequired "$constraint" -o jsonpath='{.spec.enforcementAction}')
            local transition_date=$(kubectl get neuralhivemtlsrequired "$constraint" -o jsonpath='{.metadata.annotations.gatekeeper\.sh/policy-transition-date}' 2>/dev/null || echo "")

            log_info "$constraint: $action $(if [[ -n "$transition_date" ]]; then echo "(transicionado em: $transition_date)"; fi)"

            if [[ "$action" == "enforce" && -z "$transition_date" ]]; then
                log_warning "$constraint está em enforce mas sem annotation de transição"
            fi
        done
    fi

    # Verificar constraints de imagem
    if kubectl get neuralhiveimagesignature &>/dev/null; then
        for constraint in $(kubectl get neuralhiveimagesignature -o jsonpath='{.items[*].metadata.name}'); do
            local action=$(kubectl get neuralhiveimagesignature "$constraint" -o jsonpath='{.spec.enforcementAction}')
            local transition_date=$(kubectl get neuralhiveimagesignature "$constraint" -o jsonpath='{.metadata.annotations.gatekeeper\.sh/policy-transition-date}' 2>/dev/null || echo "")

            log_info "$constraint: $action $(if [[ -n "$transition_date" ]]; then echo "(transicionado em: $transition_date)"; fi)"

            if [[ "$action" == "enforce" && -z "$transition_date" ]]; then
                log_warning "$constraint está em enforce mas sem annotation de transição"
            fi
        done
    fi

    # Verificar se há novas violações após transição
    sleep 10
    log_info "Verificando novas violações após transição..."

    local new_violations=$(kubectl get events -A --field-selector reason=ConstraintViolation --sort-by='.lastTimestamp' | tail -5 | wc -l)
    if [[ "$new_violations" -gt 0 ]]; then
        log_warning "$new_violations nova(s) violação(ões) detectada(s) após transição"
        log_info "Últimas violações:"
        kubectl get events -A --field-selector reason=ConstraintViolation --sort-by='.lastTimestamp' | tail -3
    else
        log_success "Nenhuma nova violação detectada"
    fi

    if [[ $validation_errors -eq 0 ]]; then
        log_success "Validação concluída com sucesso"
        return 0
    else
        log_error "$validation_errors erro(s) encontrado(s) na validação"
        return 1
    fi
}

# Função de rollback em caso de problemas
rollback_changes() {
    log_error "Iniciando rollback das mudanças..."

    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Diretório de backup não encontrado: $BACKUP_DIR"
        return 1
    fi

    # Restaurar constraints
    for backup_file in "$BACKUP_DIR"/*.yaml; do
        if [[ -f "$backup_file" ]]; then
            log_info "Restaurando: $(basename "$backup_file")"
            kubectl apply -f "$backup_file" || log_error "Falha ao restaurar $(basename "$backup_file")"
        fi
    done

    log_warning "Rollback concluído. Verifique o estado das políticas."
}

# Gerar relatório de notificação
send_notification() {
    local status="$1"
    local message="$2"

    # Log local
    echo "$(date): $status - $message" >> /var/log/opa-policy-transitions.log 2>/dev/null || true

    # Webhook de notificação (se configurado)
    if [[ -n "${NOTIFICATION_WEBHOOK:-}" ]]; then
        curl -X POST "$NOTIFICATION_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"status\":\"$status\",\"message\":\"$message\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
            &>/dev/null || log_warning "Falha ao enviar notificação webhook"
    fi

    # Slack notification (se configurado)
    if [[ -n "${SLACK_WEBHOOK:-}" ]]; then
        curl -X POST "$SLACK_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"OPA Policy Transition: $status - $message\"}" \
            &>/dev/null || log_warning "Falha ao enviar notificação Slack"
    fi
}

# Função principal
main() {
    log_info "=============================================="
    log_info "TRANSIÇÃO DE POLÍTICAS OPA: WARN → ENFORCE"
    log_info "=============================================="

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warning "EXECUTANDO EM MODO DRY-RUN - Nenhuma mudança será aplicada"
    fi

    local exit_code=0

    # Verificar pré-requisitos
    check_prerequisites

    # Criar backup
    create_backup

    # Processar todas as políticas
    if ! process_all_policies; then
        exit_code=1
    fi

    # Validar transições (apenas se não for dry-run)
    if [[ "$DRY_RUN" != "true" ]]; then
        if ! validate_transition; then
            log_error "Falha na validação - considerando rollback"
            if [[ "${AUTO_ROLLBACK:-false}" == "true" ]]; then
                rollback_changes
            fi
            exit_code=1
        fi
    fi

    # Notificação final
    if [[ $exit_code -eq 0 ]]; then
        local success_msg="Transição de políticas concluída com sucesso"
        log_success "$success_msg"
        send_notification "SUCCESS" "$success_msg"
    else
        local error_msg="Falha na transição de políticas"
        log_error "$error_msg"
        send_notification "ERROR" "$error_msg"
    fi

    log_info "Backup das políticas mantido em: $BACKUP_DIR"

    return $exit_code
}

# Mostrar ajuda
show_help() {
    cat << EOF
USO: $0 [OPÇÕES]

OPÇÕES:
    -d, --dry-run                    Executar em modo dry-run (sem aplicar mudanças)
    -t, --threshold NUM              Definir threshold máximo de violações (padrão: $MAX_VIOLATION_THRESHOLD)
    -m, --min-days NUM               Mínimo de dias em modo warn (padrão: $MIN_DAYS_IN_WARN)
    -r, --auto-rollback              Ativar rollback automático em caso de falha
    -h, --help                       Mostrar esta ajuda

VARIÁVEIS DE AMBIENTE:
    DRY_RUN=true                     Ativar modo dry-run
    NOTIFICATION_WEBHOOK=url         URL para notificações webhook
    SLACK_WEBHOOK=url                URL para notificações Slack
    AUTO_ROLLBACK=true               Ativar rollback automático

EXEMPLOS:
    $0                               Executar transição normal
    $0 --dry-run                     Verificar quais políticas seriam transicionadas
    $0 --threshold 5 --min-days 7    Usar threshold personalizado
    DRY_RUN=true $0                  Executar via variável de ambiente

EOF
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -t|--threshold)
            MAX_VIOLATION_THRESHOLD="$2"
            shift 2
            ;;
        -m|--min-days)
            MIN_DAYS_IN_WARN="$2"
            shift 2
            ;;
        -r|--auto-rollback)
            AUTO_ROLLBACK=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            show_help
            exit 1
            ;;
    esac
done

# Executar
main "$@"