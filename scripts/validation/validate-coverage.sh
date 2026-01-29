#!/bin/bash
set -e

echo "🧪 Executando testes e validando coverage..."

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Limpar coverage anterior
rm -rf htmlcov/ coverage.xml .coverage

# Executar testes unitários
echo -e "${YELLOW}📦 Testes unitários...${NC}"
pytest libraries/python/neural_hive_specialists/tests/ \
    -m "unit" \
    --cov=neural_hive_specialists \
    --cov-report=xml \
    --cov-report=term-missing \
    -v

# Executar testes de integração
echo -e "${YELLOW}🔗 Testes de integração...${NC}"
pytest tests/integration/ \
    -m "integration" \
    --cov=services \
    --cov-append \
    --cov-report=xml \
    --cov-report=term-missing \
    -v

# Validar threshold
echo -e "${YELLOW}📊 Validando coverage threshold...${NC}"
python - <<'PY'
import sys
import xml.etree.ElementTree as ET

try:
    import coverage  # noqa: F401
except ImportError:
    print("coverage não está instalado. Instale com 'pip install coverage'.")
    sys.exit(2)

tree = ET.parse("coverage.xml")
root = tree.getroot()
percent = float(root.attrib.get("line-rate", 0)) * 100
threshold = 85.0
print(f"Coverage: {percent:.2f}% (threshold: {threshold}%)")
if percent < threshold:
    sys.exit(1)
PY

if [[ $? -ne 0 ]]; then
    echo -e "${RED}❌ Coverage abaixo do threshold ou dependência ausente${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Coverage OK${NC}"

# Gerar relatório HTML
python -m coverage html
echo -e "${GREEN}📄 Relatório HTML gerado em htmlcov/index.html${NC}"
