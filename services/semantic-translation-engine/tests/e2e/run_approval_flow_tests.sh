#!/bin/bash
# =============================================================================
# Script para execução de testes E2E do fluxo de aprovação
#
# Uso:
#   ./run_approval_flow_tests.sh [opções]
#
# Opções:
#   --all           Executa todos os testes E2E
#   --quick         Executa apenas testes rápidos (sem marcador slow)
#   --destructive   Executa apenas testes de operações destrutivas
#   --metrics       Executa apenas testes de métricas
#   --failures      Executa apenas testes de cenários de falha
#   --verbose       Modo verbose com logs detalhados
#   --help          Mostra esta ajuda
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Variáveis de configuração
PYTEST_ARGS="-v --tb=short"
MARKER_FILTER="e2e and approval_flow"
VERBOSE=false

# Função de ajuda
show_help() {
    echo -e "${BLUE}Script para execução de testes E2E do fluxo de aprovação${NC}"
    echo ""
    echo "Uso: $0 [opções]"
    echo ""
    echo "Opções:"
    echo "  --all           Executa todos os testes E2E"
    echo "  --quick         Executa apenas testes rápidos (sem marcador slow)"
    echo "  --destructive   Executa apenas testes de operações destrutivas"
    echo "  --metrics       Executa apenas testes de métricas"
    echo "  --failures      Executa apenas testes de cenários de falha"
    echo "  --verbose       Modo verbose com logs detalhados"
    echo "  --help          Mostra esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  $0 --quick              # Executa testes rápidos"
    echo "  $0 --destructive        # Executa testes destrutivos"
    echo "  $0 --all --verbose      # Executa todos com logs detalhados"
}

# Função para verificar pré-requisitos
check_prerequisites() {
    echo -e "${BLUE}Verificando pré-requisitos...${NC}"

    # Verificar Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Erro: Python 3 não encontrado${NC}"
        exit 1
    fi

    # Verificar pytest
    if ! python3 -c "import pytest" &> /dev/null; then
        echo -e "${RED}Erro: pytest não instalado${NC}"
        echo "Execute: pip install pytest pytest-asyncio"
        exit 1
    fi

    echo -e "${GREEN}✓ Pré-requisitos verificados${NC}"
}

# Função para verificar infraestrutura (opcional)
check_infrastructure() {
    echo -e "${BLUE}Verificando infraestrutura (opcional)...${NC}"

    # Verificar se estamos em ambiente Kubernetes
    if command -v kubectl &> /dev/null; then
        # Verificar Kafka
        if kubectl get pods -n neural-hive-kafka 2>/dev/null | grep -q kafka; then
            echo -e "${GREEN}✓ Kafka disponível${NC}"
        else
            echo -e "${YELLOW}⚠ Kafka não encontrado - testes usarão mocks${NC}"
        fi

        # Verificar MongoDB
        if kubectl get pods -n mongodb-cluster 2>/dev/null | grep -q mongodb; then
            echo -e "${GREEN}✓ MongoDB disponível${NC}"
        else
            echo -e "${YELLOW}⚠ MongoDB não encontrado - testes usarão mocks${NC}"
        fi

        # Verificar Approval Service
        if kubectl get pods -n neural-hive-orchestration 2>/dev/null | grep -q approval-service; then
            echo -e "${GREEN}✓ Approval Service disponível${NC}"
        else
            echo -e "${YELLOW}⚠ Approval Service não encontrado - testes usarão mocks${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ kubectl não disponível - testes usarão mocks${NC}"
    fi
}

# Função principal de execução de testes
run_tests() {
    local marker="$1"
    local description="$2"

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Executando: ${description}${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    cd "${PROJECT_ROOT}"

    # Construir comando pytest
    local cmd="python3 -m pytest tests/e2e/test_approval_flow.py ${PYTEST_ARGS}"

    if [ -n "$marker" ]; then
        cmd="${cmd} -m \"${marker}\""
    fi

    if [ "$VERBOSE" = true ]; then
        cmd="${cmd} --log-cli-level=DEBUG"
    fi

    echo -e "${YELLOW}Comando: ${cmd}${NC}"
    echo ""

    # Executar testes
    eval $cmd

    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ ${description} - PASSOU${NC}"
    else
        echo ""
        echo -e "${RED}✗ ${description} - FALHOU${NC}"
    fi

    return $exit_code
}

# Processar argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            MARKER_FILTER="e2e"
            shift
            ;;
        --quick)
            MARKER_FILTER="e2e and approval_flow and not slow"
            shift
            ;;
        --destructive)
            MARKER_FILTER="e2e and destructive"
            shift
            ;;
        --metrics)
            MARKER_FILTER="e2e and metrics"
            shift
            ;;
        --failures)
            MARKER_FILTER="e2e and failure_scenarios"
            shift
            ;;
        --verbose)
            VERBOSE=true
            PYTEST_ARGS="${PYTEST_ARGS} -vv"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Opção desconhecida: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Execução principal
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Testes E2E - Fluxo de Aprovação do Neural Hive Mind       ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

check_prerequisites
check_infrastructure

# Executar testes
run_tests "$MARKER_FILTER" "Testes E2E de Fluxo de Aprovação"
exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✓ Todos os testes E2E passaram com sucesso!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
else
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  ✗ Alguns testes E2E falharam${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
fi

exit $exit_code
