#!/bin/bash
# retrain.sh - Comando para re-treinar specialists com feedback
#
# Uso: ml.sh retrain [OPCOES]
#
# Este comando e um wrapper para o script retrain_specialist.sh existente,
# mantendo compatibilidade enquanto oferece interface unificada.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"

# Funcao de ajuda
show_help() {
    cat << EOF
retrain - Re-treinar especialista com opcoes customizadas

Uso: ml.sh retrain [OPCOES]

OPCOES OBRIGATORIAS:
    --specialist TYPE        Tipo do especialista (technical|business|behavior|evolution|architecture)

OPCOES OPCIONAIS:
    --model-type TYPE        Tipo de modelo: random_forest (padrao), gradient_boosting, neural_network
    --hyperparameter-tuning  Habilitar GridSearchCV para otimizacao
    --provider PROVIDER      Provider LLM para geracao de dataset: openai (padrao), anthropic, ollama
    --force-retrain          Forcar re-treino mesmo se modelo atual for bom
    --dry-run                Simular re-treinamento sem executar
    -h, --help               Mostrar esta mensagem

EXEMPLOS:
    ml.sh retrain --specialist technical
    ml.sh retrain --specialist business --hyperparameter-tuning --model-type gradient_boosting
    ml.sh retrain --specialist behavior --force-retrain --provider anthropic
    ml.sh retrain --specialist evolution --dry-run

DIFERENCA ENTRE TRAIN E RETRAIN:
    - train: Treinamento inicial ou regular de modelos
    - retrain: Re-treinamento com analise de necessidade, verificando:
        * Metricas atuais do modelo em Production
        * Idade do modelo
        * Feedbacks humanos disponiveis

O retrain inclui:
    1. Pre-flight checks (MLflow, MongoDB, datasets)
    2. Analise de necessidade de re-treino
    3. Execucao do treinamento
    4. Comparacao pos-treinamento
    5. Sugestoes de proximos passos

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
RETRAIN_SCRIPT="${SCRIPT_DIR}/../scripts/retrain_specialist.sh"

if [[ ! -f "$RETRAIN_SCRIPT" ]]; then
    log_error "Script de re-treinamento nao encontrado: $RETRAIN_SCRIPT"
    exit 1
fi

# Delegar para script existente (com flag para suprimir aviso de deprecacao)
log_phase "Neural Hive - Specialist Retraining"
log_info "Delegando para script especializado..."
echo ""

export ML_CLI_WRAPPER=true
exec "$RETRAIN_SCRIPT" "$@"
