#!/bin/bash
# Script para disparar atualização de online learning
# Uso: ./trigger_update.sh [specialist-type] [--force] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configurações padrão
SPECIALIST_TYPE="${1:-all}"
FORCE_FLAG=""
DRY_RUN_FLAG=""
NAMESPACE="${NAMESPACE:-mlflow}"
KUBECTL="${KUBECTL:-kubectl}"

# Processar argumentos
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_FLAG="--force"
            shift
            ;;
        --dry-run)
            DRY_RUN_FLAG="--dry-run"
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Argumento desconhecido: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}=== Neural Hive - Online Learning Update ===${NC}"
echo ""
echo "Configurações:"
echo "  Specialist Type: $SPECIALIST_TYPE"
echo "  Namespace: $NAMESPACE"
echo "  Force: ${FORCE_FLAG:-false}"
echo "  Dry Run: ${DRY_RUN_FLAG:-false}"
echo ""

# Verificar se kubectl está disponível
if ! command -v "$KUBECTL" &> /dev/null; then
    echo -e "${RED}kubectl não encontrado. Tentando execução local...${NC}"

    cd "$PROJECT_ROOT"
    python -m ml_pipelines.online_learning.cli update \
        --specialist-types "$SPECIALIST_TYPE" \
        $FORCE_FLAG $DRY_RUN_FLAG \
        --verbose
    exit $?
fi

# Criar Job temporário para execução
JOB_NAME="online-update-manual-$(date +%s)"

echo -e "${YELLOW}Criando job de atualização: $JOB_NAME${NC}"

$KUBECTL create job "$JOB_NAME" \
    --namespace="$NAMESPACE" \
    --from=cronjob/online-learning-update \
    -- python -m ml_pipelines.online_learning.cli update \
       --specialist-types "$SPECIALIST_TYPE" \
       $FORCE_FLAG $DRY_RUN_FLAG \
       --verbose

echo -e "${GREEN}Job criado com sucesso!${NC}"
echo ""
echo "Para acompanhar o progresso:"
echo "  kubectl logs -f job/$JOB_NAME -n $NAMESPACE"
echo ""
echo "Para verificar status:"
echo "  kubectl get job $JOB_NAME -n $NAMESPACE"
