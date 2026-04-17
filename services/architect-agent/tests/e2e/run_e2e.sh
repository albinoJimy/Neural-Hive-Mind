#!/bin/bash
# Script para executar testes E2E do Fluxo G Fase 1

set -e

echo "======================================"
echo "Fluxo G Fase 1 - Testes E2E"
echo "======================================"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para log
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Verificar se docker-compose está rodando
if ! docker ps | grep -q "architect-agent-e2e"; then
    log_error "Serviços E2E não estão rodando!"
    echo "Execute primeiro: docker-compose -f docker-compose.e2e.yml up -d"
    exit 1
fi

log_info "Serviços E2E detectados"

# Esperar que serviços estejam saudáveis
log_info "Aguardando serviços ficarem saudáveis..."

max_wait=60
waited=0
while [ $waited -lt $max_wait ]; do
    if curl -sf http://localhost:8008/health/live > /dev/null 2>&1; then
        log_info "Serviço saudável!"
        break
    fi
    sleep 2
    waited=$((waited + 2))
    echo -n "."
done

echo ""

if [ $waited -ge $max_wait ]; then
    log_error "Timeout aguardando serviço saudável"
    exit 1
fi

# Executar testes
log_info "Executando testes E2E..."

cd "$(dirname "$0")/../.."

# Testes que não requerem LLM real
log_info "Testes E2E (sem LLM real)..."
pytest tests/e2e/test_fluxo_g_fase1_e2e.py::TestFluxoGFase1Integration -v --tb=short -m e2e

# Verificar se OPENAI_API_KEY está definida para testes com LLM real
if [ -n "$OPENAI_API_KEY" ] && [ "$OPENAI_API_KEY" != "sk-test-key-for-e2e" ]; then
    log_info "Executando testes E2E com LLM real..."
    pytest tests/e2e/test_fluxo_g_fase1_e2e.py::TestFluxoGWithRealLLM -v --tb=short -m e2e
else
    log_warn "OPENAI_API_KEY não definida ou é chave de teste"
    log_warn "Saltando testes que requerem LLM real"
fi

log_info "Testes E2E completados!"

# Mostrar resumo
echo ""
echo "======================================"
echo "Resumo dos Testes E2E"
echo "======================================"
echo "Para ver relatório completo: pytest tests/e2e/ --html=e2e-report.html"
echo ""
