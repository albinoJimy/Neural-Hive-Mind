#!/bin/bash
# Script para build e publicação da biblioteca neural_hive_integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building neural_hive_integration library ==="

# Limpar builds anteriores
echo "Limpando builds anteriores..."
rm -rf build/ dist/ *.egg-info/

# Instalar dependências de build
echo "Instalando dependências de build..."
pip install --upgrade pip setuptools wheel build twine

# Build da biblioteca
echo "Building wheel e source distribution..."
python -m build

echo ""
echo "=== Build completo! ==="
echo "Arquivos gerados em dist/:"
ls -lh dist/

echo ""
echo "Para publicar em registry privado:"
echo "  twine upload --repository-url https://your-registry.com/pypi dist/*"
echo ""
echo "Para instalar localmente:"
echo "  pip install dist/neural_hive_integration-1.0.0-py3-none-any.whl"
echo ""
echo "Para desenvolvimento (editable install):"
echo "  pip install -e ."
