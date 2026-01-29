#!/bin/bash
# run-tests.sh - Script para executar testes do Code Forge
#
# Uso:
#   ./run-tests.sh           # Executa todos os testes
#   ./run-tests.sh unit      # Apenas testes unitarios
#   ./run-tests.sh integration  # Apenas testes de integracao
#   ./run-tests.sh coverage  # Testes com relatorio de cobertura detalhado

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Code Forge Test Runner ===${NC}"

# Criar diretorio de resultados se nao existir
mkdir -p test-results
mkdir -p htmlcov

# Funcao para executar testes
run_tests() {
    local test_type=$1
    local extra_args="${@:2}"

    echo -e "${YELLOW}Executando testes: ${test_type:-todos}${NC}"

    case $test_type in
        unit)
            python -m pytest tests/unit -v $extra_args
            ;;
        integration)
            python -m pytest tests/integration -v $extra_args
            ;;
        coverage)
            python -m pytest tests/ \
                --cov=src \
                --cov-report=term-missing \
                --cov-report=html:htmlcov \
                --cov-report=xml:test-results/coverage.xml \
                --junit-xml=test-results/junit.xml \
                -v $extra_args
            echo -e "${GREEN}Relatorio HTML disponivel em: htmlcov/index.html${NC}"
            ;;
        *)
            python -m pytest tests/ -v $extra_args
            ;;
    esac
}

# Verificar se pytest esta instalado
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}pytest nao encontrado. Instalando dependencias...${NC}"
    pip install -r requirements.txt
fi

# Executar testes baseado no argumento
if [ $# -eq 0 ]; then
    run_tests
else
    run_tests "$@"
fi

echo -e "${GREEN}=== Testes finalizados ===${NC}"
