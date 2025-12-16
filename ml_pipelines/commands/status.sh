#!/bin/bash
# status.sh - Comando para verificar status de modelos
#
# Uso: ml.sh status [OPCOES]
#
# Este comando e um wrapper para o script check_model_status.sh existente,
# mantendo compatibilidade enquanto oferece interface unificada.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"

# Funcao de ajuda
show_help() {
    cat << EOF
status - Verificar status de modelos ML no MLflow Registry

Uso: ml.sh status [OPCOES]

OPCOES:
    --specialist TYPE   Verificar especialista especifico (technical|business|behavior|evolution|architecture)
    --all               Verificar todos os 5 especialistas (padrao)
    --verbose           Mostrar informacoes detalhadas (run_id, timestamps, tags)
    --format FORMAT     Formato de saida: table (padrao) ou json
    -h, --help          Mostrar esta mensagem

EXEMPLOS:
    ml.sh status --all
    ml.sh status --specialist technical --verbose
    ml.sh status --all --format json

INFORMACOES EXIBIDAS:
    - Versao em Production
    - Metricas (Precision, Recall, F1, Accuracy)
    - Ultima atualizacao
    - (Verbose) Run ID, versao em Staging, comparacao

EXIT CODES:
    0  Todos os modelos OK
    1  Algum modelo nao encontrado ou sem versao em Production
    2  MLflow nao acessivel

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
STATUS_SCRIPT="${SCRIPT_DIR}/../scripts/check_model_status.sh"

if [[ ! -f "$STATUS_SCRIPT" ]]; then
    log_error "Script de status nao encontrado: $STATUS_SCRIPT"
    exit 1
fi

# Delegar para script existente (com flag para suprimir aviso de deprecacao)
log_phase "Neural Hive - Model Status"
echo ""

export ML_CLI_WRAPPER=true
exec "$STATUS_SCRIPT" "$@"
