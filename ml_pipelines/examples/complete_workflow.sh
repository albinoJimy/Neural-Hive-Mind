#!/bin/bash
# complete_workflow.sh - Exemplo de workflow completo de ML
#
# Este script demonstra um ciclo completo de operacoes ML usando o CLI unificado.
#
# Uso: ./complete_workflow.sh
#
# Passos:
#   1. Gerar datasets para todos os specialists
#   2. Treinar todos os modelos
#   3. Validar modelos treinados
#   4. Verificar status
#   5. Promover modelos que atingiram thresholds

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ML_CLI="${SCRIPT_DIR}/../ml.sh"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}PASSO $1: $2${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Verificar se CLI existe
if [[ ! -f "$ML_CLI" ]]; then
    echo -e "${RED}Erro: CLI nao encontrado em $ML_CLI${NC}"
    exit 1
fi

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Neural Hive Mind - Workflow Completo de ML${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Este script executara o seguinte workflow:"
echo "  1. Gerar datasets para todos os 5 specialists"
echo "  2. Treinar modelos com hyperparameter tuning"
echo "  3. Validar modelos treinados"
echo "  4. Verificar status de todos os modelos"
echo "  5. Promover modelos que atingiram thresholds"
echo ""
echo -e "${YELLOW}Pressione ENTER para continuar ou CTRL+C para cancelar...${NC}"
read -r

# Passo 1: Gerar datasets
log_step "1" "Gerar Datasets"
echo "Gerando datasets para todos os 5 specialists..."
echo "Comando: ml.sh generate-dataset --all --num-samples 500"
echo ""

if "$ML_CLI" generate-dataset --all --num-samples 500; then
    echo -e "${GREEN}Datasets gerados com sucesso!${NC}"
else
    echo -e "${RED}Falha ao gerar datasets${NC}"
    exit 1
fi

# Passo 2: Treinar modelos
log_step "2" "Treinar Modelos"
echo "Treinando modelos para todos os 5 specialists..."
echo "Comando: ml.sh train --all --hyperparameter-tuning"
echo ""

if "$ML_CLI" train --all --hyperparameter-tuning; then
    echo -e "${GREEN}Modelos treinados com sucesso!${NC}"
else
    echo -e "${RED}Falha ao treinar modelos${NC}"
    exit 1
fi

# Passo 3: Validar modelos
log_step "3" "Validar Modelos"
echo "Validando modelos carregados..."
echo "Comando: ml.sh validate --all"
echo ""

if "$ML_CLI" validate --all; then
    echo -e "${GREEN}Modelos validados com sucesso!${NC}"
else
    echo -e "${YELLOW}Alguns modelos requerem atencao${NC}"
fi

# Passo 4: Verificar status
log_step "4" "Verificar Status"
echo "Verificando status de todos os modelos..."
echo "Comando: ml.sh status --all --verbose"
echo ""

"$ML_CLI" status --all --verbose || true

# Passo 5: Promover modelos
log_step "5" "Promover Modelos"
echo "Verificando modelos para promocao..."
echo ""

SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

for specialist in "${SPECIALISTS[@]}"; do
    model_name="${specialist}-evaluator"
    echo -e "${BLUE}Verificando $model_name...${NC}"

    # Tentar obter versao mais recente
    # Este e um exemplo simplificado - em producao, usaria mlflow_utils.sh
    echo "  Comando: ml.sh promote --model $model_name --version latest --skip-validation"
    # Descomentar para executar: "$ML_CLI" promote --model "$model_name" --version latest --skip-validation
    echo ""
done

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Workflow Completo Finalizado!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Proximos passos:"
echo "  1. Revisar modelos em Staging: ml.sh status --all --verbose"
echo "  2. Promover modelos manualmente se necessario"
echo "  3. Reiniciar pods de specialists para carregar novos modelos"
echo ""
echo "Comandos uteis:"
echo "  ml.sh status --all --format json    # Status em JSON"
echo "  ml.sh validate --all --check-pods   # Validar pods K8s"
echo "  ml.sh rollback --specialist TYPE    # Rollback se necessario"
echo ""
