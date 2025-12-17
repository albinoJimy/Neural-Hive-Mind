#!/bin/bash
# ml.sh - CLI unificado para operacoes de Machine Learning do Neural Hive Mind
#
# Este script consolida todos os scripts ML dispersos em um unico ponto de entrada
# com subcomandos para treinar, validar, promover, re-treinar, rollback e gerar datasets.
#
# Uso: ml.sh COMANDO [OPCOES]
#
# Exemplos:
#   ml.sh train --specialist technical
#   ml.sh validate --all
#   ml.sh promote --model technical-evaluator --version 3
#   ml.sh retrain --specialist business --hyperparameter-tuning
#   ml.sh rollback --specialist evolution --reason "Alta latencia"
#   ml.sh generate-dataset --specialist architecture --num-samples 1000
#   ml.sh status --all --verbose

set -euo pipefail

# Diretorio do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Carregar bibliotecas
source "${SCRIPT_DIR}/lib/ml_common.sh"
source "${SCRIPT_DIR}/lib/mlflow_utils.sh"
source "${SCRIPT_DIR}/lib/dataset_utils.sh"

# Versao do CLI
VERSION="1.0.0"

# Funcao de uso principal
usage() {
    cat << EOF
ml.sh - CLI unificado para operacoes de Machine Learning

Uso: ml.sh COMANDO [OPCOES]

COMANDOS:
    train              Treinar modelos de specialists
    validate           Validar modelos carregados
    promote            Promover modelo entre stages
    retrain            Re-treinar specialist com feedback
    rollback           Fazer rollback de modelo
    generate-dataset   Gerar datasets de treinamento
    status             Verificar status de modelos
    business-metrics   Coletar métricas de negócio
    anomaly-detector   Treinar detector de anomalias
    feedback           Registrar feedback manual
    disaster-recovery  Rotinas de teste de DR
    help               Mostrar esta mensagem
    version            Mostrar versao

Execute 'ml.sh COMANDO --help' para mais informacoes sobre cada comando.

EXEMPLOS:
    ml.sh train --specialist technical
    ml.sh train --all --hyperparameter-tuning
    ml.sh validate --all
    ml.sh promote --model technical-evaluator --version 3 --stage Production
    ml.sh retrain --specialist business --hyperparameter-tuning
    ml.sh rollback --specialist evolution --reason "Alta latencia"
    ml.sh generate-dataset --specialist architecture --num-samples 1000
    ml.sh generate-dataset --all --llm-provider openai
    ml.sh status --all --verbose
    ml.sh status --specialist technical --format json

VARIAVEIS DE AMBIENTE:
    MLFLOW_URI         URI do servidor MLflow (padrao: http://mlflow.mlflow:5000)
    MONGODB_URI        URI do MongoDB para feedbacks
    DATASET_DIR        Diretorio de datasets (padrao: /data/training)
    K8S_NAMESPACE      Namespace Kubernetes (padrao: neural-hive)
    LLM_PROVIDER       Provider LLM para geracao (openai, anthropic, ollama, groq, deepseek)
    LLM_MODEL          Modelo LLM a usar
    LLM_API_KEY        Chave de API do LLM

MAPEAMENTO DE SCRIPTS ANTIGOS:
    train_all_specialists.sh         -> ml.sh train --all
    train_specialist_model.py        -> ml.sh train --specialist TYPE
    retrain_specialist.sh            -> ml.sh retrain --specialist TYPE
    check_model_status.sh            -> ml.sh status
    rollback_model.sh                -> ml.sh rollback --specialist TYPE
    generate_all_datasets.sh         -> ml.sh generate-dataset --all
    validate_models_loaded.sh        -> ml.sh validate --all
    promote_model.py                 -> ml.sh promote --model NAME --version N

EOF
    exit 0
}

# Funcao de versao
show_version() {
    echo "ml.sh versao $VERSION"
    echo "Neural Hive Mind - CLI de Machine Learning"
    exit 0
}

# Parse comando principal
COMMAND="${1:-help}"
shift || true

case "${COMMAND}" in
    train)
        exec "${SCRIPT_DIR}/commands/train.sh" "$@"
        ;;
    validate)
        exec "${SCRIPT_DIR}/commands/validate.sh" "$@"
        ;;
    promote)
        exec "${SCRIPT_DIR}/commands/promote.sh" "$@"
        ;;
    retrain)
        exec "${SCRIPT_DIR}/commands/retrain.sh" "$@"
        ;;
    rollback)
        exec "${SCRIPT_DIR}/commands/rollback.sh" "$@"
        ;;
    generate-dataset|generate_dataset|dataset)
        exec "${SCRIPT_DIR}/commands/generate_dataset.sh" "$@"
        ;;
    status)
        exec "${SCRIPT_DIR}/commands/status.sh" "$@"
        ;;
    business-metrics|business_metrics)
        exec "${SCRIPT_DIR}/commands/business_metrics.sh" "$@"
        ;;
    anomaly-detector|anomaly_detector)
        exec "${SCRIPT_DIR}/commands/anomaly_detector.sh" "$@"
        ;;
    feedback)
        exec "${SCRIPT_DIR}/commands/feedback.sh" "$@"
        ;;
    disaster-recovery|disaster_recovery)
        exec "${SCRIPT_DIR}/commands/disaster_recovery.sh" "$@"
        ;;
    help|--help|-h)
        usage
        ;;
    version|--version|-v)
        show_version
        ;;
    *)
        log_error "Comando desconhecido: ${COMMAND}"
        echo ""
        echo "Use 'ml.sh help' para ver comandos disponiveis."
        exit 1
        ;;
esac
