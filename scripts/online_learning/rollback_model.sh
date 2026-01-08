#!/bin/bash
# Script para executar rollback de modelo online
# Uso: ./rollback_model.sh <specialist-type> <reason> [--version <version>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Verificar argumentos obrigatórios
if [[ $# -lt 2 ]]; then
    echo -e "${RED}Uso: $0 <specialist-type> <reason> [--version <version>]${NC}"
    echo ""
    echo "Exemplos:"
    echo "  $0 feasibility 'Degradação de performance detectada'"
    echo "  $0 risk 'Rollback manual solicitado' --version v1.2.3"
    exit 1
fi

SPECIALIST_TYPE="$1"
REASON="$2"
VERSION=""
NAMESPACE="${NAMESPACE:-mlflow}"
KUBECTL="${KUBECTL:-kubectl}"

# Processar argumentos opcionais
shift 2
while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
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

echo -e "${YELLOW}=== Neural Hive - Online Learning Rollback ===${NC}"
echo ""
echo "Configurações:"
echo "  Specialist Type: $SPECIALIST_TYPE"
echo "  Motivo: $REASON"
echo "  Versão alvo: ${VERSION:-última estável}"
echo "  Namespace: $NAMESPACE"
echo ""

# Confirmação
read -p "Confirma o rollback? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Rollback cancelado.${NC}"
    exit 0
fi

# Executar rollback
VERSION_ARG=""
if [[ -n "$VERSION" ]]; then
    VERSION_ARG="--version $VERSION"
fi

if ! command -v "$KUBECTL" &> /dev/null; then
    echo -e "${YELLOW}kubectl não encontrado. Executando localmente...${NC}"

    cd "$PROJECT_ROOT"
    python -m ml_pipelines.online_learning.cli rollback \
        --specialist-type "$SPECIALIST_TYPE" \
        --reason "$REASON" \
        $VERSION_ARG \
        --verbose
    exit $?
fi

# Criar Job para rollback
JOB_NAME="online-rollback-$(date +%s)"

echo -e "${YELLOW}Criando job de rollback: $JOB_NAME${NC}"

$KUBECTL run "$JOB_NAME" \
    --namespace="$NAMESPACE" \
    --image="077878370245.dkr.ecr.us-east-1.amazonaws.com/neural-hive-mind/pipelines:1.0.7" \
    --restart=Never \
    --rm \
    -i \
    -- python -m ml_pipelines.online_learning.cli rollback \
       --specialist-type "$SPECIALIST_TYPE" \
       --reason "$REASON" \
       $VERSION_ARG \
       --verbose

echo -e "${GREEN}Rollback concluído!${NC}"
