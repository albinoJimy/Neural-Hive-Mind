#!/bin/bash
# Neural-Hive-Mind - Development Tools Setup
# Instala e configura ferramentas de desenvolvimento padrão

set -e

echo "🚀 Neural-Hive-Mind - Development Tools Setup"
echo "=============================================="
echo ""

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detectar Python
PYTHON_CMD=${PYTHON_CMD:-python3.12}
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD=python3
fi

echo "📦 Python detectado: $($PYTHON_CMD --version)"
echo ""

# Criar venv se não existir
if [ ! -d "venv" ]; then
    echo "🔧 Criando ambiente virtual..."
    $PYTHON_CMD -m venv venv
    source venv/bin/activate
else
    echo "✅ Ambiente virtual já existe"
    source venv/bin/activate
fi

echo ""
echo "📥 Instalando ferramentas de desenvolvimento..."

# Instalar ferramentas base
pip install --upgrade pip
pip install --upgrade \
    black==24.10.0 \
    ruff==0.8.0 \
    mypy==1.13.0 \
    pre-commit==3.8.0 \
    pytest==8.3.0 \
    pytest-asyncio==0.24.0 \
    pytest-cov==6.0.0 \
    pytest-mock==3.14.0

echo ""
echo "🔧 Configurando pre-commit hooks..."
pre-commit install

echo ""
echo "✅ Setup completo! Ferramentas disponíveis:"
echo ""
echo "  • black   - Formatação de código"
echo "  • ruff    - Linting e organização de imports"
echo "  • mypy    - Type checking"
echo "  • pytest  - Execução de testes"
echo ""
echo "${GREEN}Comandos úteis:${NC}"
echo ""
echo "  # Formatar código"
echo "  black services/ libraries/"
echo ""
echo "  # Verificar linting"
echo "  ruff check services/ libraries/"
echo ""
echo "  # Auto-corrigir problemas"
echo "  ruff check services/ libraries/ --fix"
echo ""
echo "  # Type checking"
echo "  mypy services/"
echo ""
echo "  # Executar testes"
echo "  pytest services/"
echo ""
echo "  # Executar pre-commit em todos os arquivos"
echo "  pre-commit run --all-files"
echo ""
echo "${YELLOW}Nota:${NC} Pre-commit hooks executam automaticamente antes de cada commit."
echo "Para pular (não recomendado), use: git commit --no-verify"
echo ""
