#!/bin/bash
# Script para executar testes de integracao dos executors
#
# Uso:
#   ./run_executor_integration_tests.sh           # Executa todos os testes
#   ./run_executor_integration_tests.sh deploy    # Apenas deploy executor
#   ./run_executor_integration_tests.sh test      # Apenas test executor
#   ./run_executor_integration_tests.sh validate  # Apenas validate executor
#   ./run_executor_integration_tests.sh execute   # Apenas execute executor
#   ./run_executor_integration_tests.sh -v        # Verbose mode
#   ./run_executor_integration_tests.sh --cov     # Com coverage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TESTS_DIR="$SCRIPT_DIR"
RESULTS_DIR="$PROJECT_ROOT/tests/results"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Criar diretorio de resultados se nao existir
mkdir -p "$RESULTS_DIR"

echo -e "${YELLOW}🧪 Executando testes de integracao de executors...${NC}"
echo ""

# Parsear argumentos
VERBOSE=""
COVERAGE=""
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        deploy)
            SPECIFIC_TEST="$TESTS_DIR/test_deploy_executor_integration.py"
            shift
            ;;
        test)
            SPECIFIC_TEST="$TESTS_DIR/test_test_executor_integration.py"
            shift
            ;;
        validate)
            SPECIFIC_TEST="$TESTS_DIR/test_validate_executor_integration.py"
            shift
            ;;
        execute)
            SPECIFIC_TEST="$TESTS_DIR/test_execute_executor_integration.py"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-vv"
            shift
            ;;
        --cov|--coverage)
            COVERAGE="--cov=src/executors --cov-report=html:$RESULTS_DIR/executor-integration-coverage --cov-report=term-missing"
            shift
            ;;
        -h|--help)
            echo "Uso: $0 [deploy|test|validate|execute] [-v] [--cov]"
            echo ""
            echo "Opcoes:"
            echo "  deploy     Executa apenas testes do DeployExecutor"
            echo "  test       Executa apenas testes do TestExecutor"
            echo "  validate   Executa apenas testes do ValidateExecutor"
            echo "  execute    Executa apenas testes do ExecuteExecutor"
            echo "  -v         Modo verbose"
            echo "  --cov      Gera relatorio de coverage"
            echo "  -h         Mostra esta ajuda"
            exit 0
            ;;
        *)
            echo -e "${RED}Argumento desconhecido: $1${NC}"
            exit 1
            ;;
    esac
done

# Se nenhum teste especifico, executar todos
if [ -z "$SPECIFIC_TEST" ]; then
    TEST_FILES="$TESTS_DIR/test_deploy_executor_integration.py \
                $TESTS_DIR/test_test_executor_integration.py \
                $TESTS_DIR/test_validate_executor_integration.py \
                $TESTS_DIR/test_execute_executor_integration.py"
else
    TEST_FILES="$SPECIFIC_TEST"
fi

# Mudar para diretorio do projeto
cd "$PROJECT_ROOT"

# Verificar se pytest esta instalado
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}pytest nao encontrado. Instale com: pip install pytest${NC}"
    exit 1
fi

# Executar testes
echo -e "${YELLOW}Executando:${NC}"
echo "$TEST_FILES" | tr ' ' '\n' | grep -v '^$' | while read -r f; do
    echo "  - $(basename "$f")"
done
echo ""

# Comando pytest
PYTEST_CMD="pytest $TEST_FILES \
    $VERBOSE \
    --tb=short \
    --junit-xml=$RESULTS_DIR/executor-integration-junit.xml \
    -m 'executor_integration or integration' \
    $COVERAGE"

echo -e "${YELLOW}Comando: ${NC}$PYTEST_CMD"
echo ""

# Executar
if eval $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}✅ Testes de integracao concluidos com sucesso!${NC}"
    echo ""
    echo "Resultados em: $RESULTS_DIR/executor-integration-junit.xml"
    if [ -n "$COVERAGE" ]; then
        echo "Coverage em: $RESULTS_DIR/executor-integration-coverage/index.html"
    fi
else
    echo ""
    echo -e "${RED}❌ Alguns testes falharam${NC}"
    exit 1
fi
