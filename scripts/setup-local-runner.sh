#!/bin/bash
# Setup GitHub Actions Runner Local
# Uso: ./scripts/setup-local-runner.sh [RUNNER_NUMBER] [RUNNER_TOKEN]
#
# Exemplos:
#   ./scripts/setup-local-runner.sh 1          # Primeiro runner
#   ./scripts/setup-local-runner.sh 2          # Segundo runner
#   ./scripts/setup-local-runner.sh 2 TOKEN    # Segundo runner com token

set -e

# Número do runner (1, 2, 3, etc.)
RUNNER_NUM="${1:-1}"
RUNNER_TOKEN="${2:-}"

RUNNER_NAME="${RUNNER_NAME:-neural-hive-runner-${RUNNER_NUM}}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,Linux,X64,neural-hive}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-${RUNNER_NUM}}"
REPO_URL="https://github.com/albinoJimy/Neural-Hive-Mind"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== GitHub Actions Runner Setup ===${NC}"
echo ""

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker não encontrado!${NC}"
    echo "Ative o Docker Desktop WSL Integration ou instale o Docker Engine"
    exit 1
fi

if ! docker ps &> /dev/null; then
    echo -e "${RED}Docker não está rodando ou sem permissão${NC}"
    echo "Verifique se Docker Desktop está rodando"
    exit 1
fi

echo -e "${GREEN}Docker OK${NC}"

# Info do runner
echo -e "${GREEN}Runner #${RUNNER_NUM}${NC}"
echo "  Nome: $RUNNER_NAME"
echo "  Diretório: $RUNNER_DIR"
echo "  Labels: $RUNNER_LABELS"
echo ""

# Verificar token
if [ -z "$RUNNER_TOKEN" ]; then
    echo -e "${YELLOW}Token não fornecido como argumento${NC}"
    echo ""
    echo "Para obter o token:"
    echo "1. Acesse: https://github.com/albinoJimy/Neural-Hive-Mind/settings/actions/runners/new"
    echo "2. Copie o token do comando ./config.sh"
    echo ""
    read -p "Cole o RUNNER_TOKEN aqui: " RUNNER_TOKEN
fi

if [ -z "$RUNNER_TOKEN" ]; then
    echo -e "${RED}Token é obrigatório${NC}"
    exit 1
fi

# Criar diretório
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

# Baixar runner (versão mais recente)
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep -oP '"tag_name": "v\K[^"]+')
RUNNER_VERSION="${RUNNER_VERSION:-2.321.0}"

echo -e "${GREEN}Baixando runner v${RUNNER_VERSION}...${NC}"

if [ ! -f "actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" ]; then
    curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz -L \
        https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
fi

# Extrair
echo -e "${GREEN}Extraindo...${NC}"
tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# Instalar dependências
echo -e "${GREEN}Instalando dependências...${NC}"
sudo ./bin/installdependencies.sh || true

# Configurar runner
echo -e "${GREEN}Configurando runner...${NC}"
./config.sh --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$RUNNER_LABELS" \
    --work "_work" \
    --replace \
    --unattended

echo ""
echo -e "${GREEN}=== Runner #${RUNNER_NUM} Configurado! ===${NC}"
echo ""
echo "Para iniciar o runner em foreground:"
echo -e "  ${YELLOW}cd $RUNNER_DIR && ./run.sh${NC}"
echo ""
echo "Para rodar como serviço systemd (recomendado):"
echo -e "  ${YELLOW}cd $RUNNER_DIR${NC}"
echo -e "  ${YELLOW}sudo ./svc.sh install${NC}"
echo -e "  ${YELLOW}sudo ./svc.sh start${NC}"
echo -e "  ${YELLOW}sudo ./svc.sh status${NC}"
echo ""
echo "Para adicionar OUTRO runner, execute:"
echo -e "  ${YELLOW}./scripts/setup-local-runner.sh $((RUNNER_NUM + 1))${NC}"
echo ""
echo -e "${GREEN}Resumo:${NC}"
echo "  Nome: $RUNNER_NAME"
echo "  Labels: $RUNNER_LABELS"
echo "  Diretório: $RUNNER_DIR"
