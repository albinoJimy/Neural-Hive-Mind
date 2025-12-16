#!/bin/bash
# rollback.sh - Comando para fazer rollback de modelos
#
# Uso: ml.sh rollback [OPCOES]
#
# Este comando e um wrapper para o script rollback_model.sh existente,
# mantendo compatibilidade enquanto oferece interface unificada.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"

# Funcao de ajuda
show_help() {
    cat << EOF
rollback - Fazer rollback de modelo em Production para versao anterior

Uso: ml.sh rollback [OPCOES]

OPCOES OBRIGATORIAS:
    --specialist TYPE    Tipo do especialista (technical|business|behavior|evolution|architecture)

OPCOES OPCIONAIS:
    --to-version N       Versao especifica para rollback (padrao: versao anterior)
    --from-stage STAGE   Stage de onde pegar versao: Staging, Archived
    --reason TEXT        Motivo do rollback (para auditoria)
    --force              Nao pedir confirmacao
    --dry-run            Simular rollback sem executar
    --all                Rollback de todos os 5 especialistas
    -h, --help           Mostrar esta mensagem

EXEMPLOS:
    ml.sh rollback --specialist technical --reason "Alta latencia em producao"
    ml.sh rollback --specialist business --to-version 3 --reason "Regressao de accuracy"
    ml.sh rollback --specialist behavior --force
    ml.sh rollback --all --reason "Rollback emergencial apos deploy"

EXIT CODES:
    0  Rollback executado com sucesso
    1  Erro de validacao (modelo nao existe, versao nao encontrada)
    2  MLflow nao acessivel
    3  Usuario cancelou operacao

O ROLLBACK INCLUI:
    1. Validacoes pre-rollback
    2. Analise de impacto (comparacao de metricas)
    3. Confirmacao interativa (a menos que --force)
    4. Execucao do rollback
    5. Verificacao pos-rollback
    6. Tags de auditoria no MLflow

EOF
    exit 0
}

# Verificar se help solicitado
for arg in "$@"; do
    if [[ "$arg" == "-h" ]] || [[ "$arg" == "--help" ]]; then
        show_help
    fi
done

# Verificar se script existente esta disponivel
ROLLBACK_SCRIPT="${SCRIPT_DIR}/../scripts/rollback_model.sh"

if [[ ! -f "$ROLLBACK_SCRIPT" ]]; then
    log_error "Script de rollback nao encontrado: $ROLLBACK_SCRIPT"
    exit 1
fi

# Delegar para script existente (com flag para suprimir aviso de deprecacao)
log_phase "Neural Hive - Model Rollback"
log_info "Delegando para script especializado..."
echo ""

export ML_CLI_WRAPPER=true
exec "$ROLLBACK_SCRIPT" "$@"
