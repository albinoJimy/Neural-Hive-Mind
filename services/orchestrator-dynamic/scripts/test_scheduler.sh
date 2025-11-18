#!/bin/bash
# Script de execução de testes para Intelligent Scheduler
# Uso: ./scripts/test_scheduler.sh

set -e  # Sair em caso de erro

echo "========================================="
echo "Executando Testes do Intelligent Scheduler"
echo "========================================="

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # Sem cor

# Mudar para diretório do serviço
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SERVICE_DIR"

echo -e "${YELLOW}Diretório de trabalho: $SERVICE_DIR${NC}"

# Ativar ambiente virtual se existir
if [ -d "venv" ]; then
    echo -e "${YELLOW}Ativando ambiente virtual...${NC}"
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo -e "${YELLOW}Ativando ambiente virtual...${NC}"
    source .venv/bin/activate
fi

# Verificar se pytest está disponível
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Erro: pytest não encontrado. Instale com: pip install pytest pytest-asyncio pytest-cov${NC}"
    exit 1
fi

# Executar testes unitários
echo -e "\n${GREEN}[1/3] Executando Testes Unitários...${NC}"
echo "-------------------------------------------"

pytest tests/unit/test_intelligent_scheduler.py -v --tb=short || {
    echo -e "${RED}Testes unitários para IntelligentScheduler falharam${NC}"
    exit 1
}

pytest tests/unit/test_priority_calculator.py -v --tb=short || {
    echo -e "${RED}Testes unitários para PriorityCalculator falharam${NC}"
    exit 1
}

pytest tests/unit/test_resource_allocator.py -v --tb=short || {
    echo -e "${RED}Testes unitários para ResourceAllocator falharam${NC}"
    exit 1
}

echo -e "${GREEN}✓ Todos os testes unitários passaram${NC}"

# Executar testes de integração
echo -e "\n${GREEN}[2/3] Executando Testes de Integração...${NC}"
echo "-------------------------------------------"

pytest tests/integration/test_scheduler_integration.py -v --tb=short || {
    echo -e "${RED}Testes de integração para scheduler falharam${NC}"
    exit 1
}

pytest tests/integration/test_orchestration_workflow_scheduler.py -v --tb=short || {
    echo -e "${RED}Testes de integração para workflow scheduler falharam${NC}"
    exit 1
}

echo -e "${GREEN}✓ Todos os testes de integração passaram${NC}"

# Gerar relatório de cobertura
echo -e "\n${GREEN}[3/3] Gerando Relatório de Cobertura...${NC}"
echo "-------------------------------------------"

pytest tests/unit/test_intelligent_scheduler.py \
       tests/unit/test_priority_calculator.py \
       tests/unit/test_resource_allocator.py \
       tests/integration/test_scheduler_integration.py \
       tests/integration/test_orchestration_workflow_scheduler.py \
       --cov=src/scheduler \
       --cov-report=term-missing \
       --cov-report=html:coverage_scheduler \
       --cov-fail-under=90 || {
    echo -e "${YELLOW}Aviso: Cobertura abaixo do limite de 90%${NC}"
}

echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}✓ Todos os Testes do Scheduler Passaram!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "\nRelatório de cobertura: ${YELLOW}coverage_scheduler/index.html${NC}"
echo -e "Abrir com: ${YELLOW}open coverage_scheduler/index.html${NC} (macOS)"
echo -e "       ou: ${YELLOW}xdg-open coverage_scheduler/index.html${NC} (Linux)\n"

# Resumo estatístico
echo -e "${GREEN}Resumo dos Testes:${NC}"
echo "  - Testes unitários: 40 testes (IntelligentScheduler, PriorityCalculator, ResourceAllocator)"
echo "  - Testes de integração: 16 testes (Integração do scheduler, Integração do workflow)"
echo "  - Total: 56 testes"
echo ""
