#!/bin/bash
# validate-test-coverage.sh - Script para validar cobertura de testes
#
# Uso:
#   ./scripts/validate-test-coverage.sh           # Valida todos os servicos
#   ./scripts/validate-test-coverage.sh code-forge  # Valida servico especifico
#   ./scripts/validate-test-coverage.sh --report  # Gera relatorio detalhado

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Threshold minimo de cobertura
MIN_COVERAGE=${MIN_COVERAGE:-80}

# Lista de servicos para validar
SERVICES=(
    "code-forge"
    "mcp-tool-catalog"
    "worker-agents"
    "guard-agents"
    "optimizer-agents"
    "analyst-agents"
    "consensus-engine"
    "queen-agent"
)

echo -e "${BLUE}=== Neural Hive Mind - Test Coverage Validator ===${NC}"
echo -e "${BLUE}Minimum coverage threshold: ${MIN_COVERAGE}%${NC}"
echo ""

# Funcao para validar cobertura de um servico
validate_service() {
    local service=$1
    local service_dir="$PROJECT_ROOT/services/$service"

    if [ ! -d "$service_dir" ]; then
        echo -e "${YELLOW}[SKIP] $service - diretorio nao encontrado${NC}"
        return 0
    fi

    if [ ! -f "$service_dir/pytest.ini" ] && [ ! -f "$service_dir/pyproject.toml" ]; then
        echo -e "${YELLOW}[SKIP] $service - configuracao pytest nao encontrada${NC}"
        return 0
    fi

    if [ ! -d "$service_dir/tests" ]; then
        echo -e "${YELLOW}[SKIP] $service - diretorio de testes nao encontrado${NC}"
        return 0
    fi

    echo -e "${BLUE}[TEST] $service${NC}"

    cd "$service_dir"

    # Executar testes com cobertura
    if python -m pytest tests/ \
        --cov=src \
        --cov-report=term-missing \
        --cov-report=xml:coverage.xml \
        --cov-fail-under=$MIN_COVERAGE \
        -q \
        --tb=no \
        2>/dev/null; then
        echo -e "${GREEN}[PASS] $service - cobertura >= ${MIN_COVERAGE}%${NC}"
        return 0
    else
        echo -e "${RED}[FAIL] $service - cobertura abaixo de ${MIN_COVERAGE}%${NC}"
        return 1
    fi
}

# Funcao para gerar relatorio
generate_report() {
    echo -e "${BLUE}=== Generating Coverage Report ===${NC}"

    local report_file="$PROJECT_ROOT/coverage-report.md"

    cat > "$report_file" << 'EOF'
# Test Coverage Report

| Service | Coverage | Status |
|---------|----------|--------|
EOF

    for service in "${SERVICES[@]}"; do
        local service_dir="$PROJECT_ROOT/services/$service"
        local coverage_file="$service_dir/coverage.xml"

        if [ -f "$coverage_file" ]; then
            local coverage=$(python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('$coverage_file')
root = tree.getroot()
print(f'{float(root.attrib.get(\"line-rate\", 0)) * 100:.1f}')
" 2>/dev/null || echo "N/A")

            local status="✅"
            if [ "$coverage" != "N/A" ]; then
                if (( $(echo "$coverage < $MIN_COVERAGE" | bc -l) )); then
                    status="❌"
                fi
            else
                status="⚠️"
            fi

            echo "| $service | ${coverage}% | $status |" >> "$report_file"
        else
            echo "| $service | N/A | ⚠️ |" >> "$report_file"
        fi
    done

    cat >> "$report_file" << EOF

## Legend
- ✅ Coverage meets threshold (>= ${MIN_COVERAGE}%)
- ❌ Coverage below threshold
- ⚠️ No coverage data available

Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
EOF

    echo -e "${GREEN}Report generated: $report_file${NC}"
}

# Processar argumentos
GENERATE_REPORT=false
SPECIFIC_SERVICE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --report)
            GENERATE_REPORT=true
            shift
            ;;
        --min-coverage)
            MIN_COVERAGE=$2
            shift 2
            ;;
        *)
            SPECIFIC_SERVICE=$1
            shift
            ;;
    esac
done

# Executar validacao
failed_count=0

if [ -n "$SPECIFIC_SERVICE" ]; then
    # Validar servico especifico
    if ! validate_service "$SPECIFIC_SERVICE"; then
        failed_count=$((failed_count + 1))
    fi
else
    # Validar todos os servicos
    for service in "${SERVICES[@]}"; do
        if ! validate_service "$service"; then
            failed_count=$((failed_count + 1))
        fi
    done
fi

# Gerar relatorio se solicitado
if [ "$GENERATE_REPORT" = true ]; then
    generate_report
fi

# Resumo final
echo ""
echo -e "${BLUE}=== Summary ===${NC}"

if [ $failed_count -eq 0 ]; then
    echo -e "${GREEN}All services passed coverage threshold!${NC}"
    exit 0
else
    echo -e "${RED}$failed_count service(s) failed coverage threshold${NC}"
    exit 1
fi
