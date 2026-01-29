#!/bin/bash
# Script para configurar variáveis de ambiente para deployment EKS
# Version: 1.0.0

set -euo pipefail

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Neural Hive-Mind - Setup EKS Deployment${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Função para gerar senha segura
generate_password() {
    openssl rand -base64 24 | tr -d "=+/" | cut -c1-20
}

# Verificar AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI não encontrado${NC}"
    echo "Execute: curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o awscliv2.zip && unzip && sudo ./aws/install"
    exit 1
fi

# Verificar credenciais AWS
echo -e "${BLUE}[1/5] Verificando credenciais AWS...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ Credenciais AWS não configuradas ou inválidas${NC}"
    echo ""
    echo "Configure com: aws configure"
    echo "Você precisará de:"
    echo "  - AWS Access Key ID"
    echo "  - AWS Secret Access Key"
    echo "  - Default region (recomendado: us-east-1)"
    echo "  - Default output format (recomendado: json)"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CURRENT_USER=$(aws sts get-caller-identity --query Arn --output text)
echo -e "${GREEN}✅ Credenciais válidas${NC}"
echo "   Account: ${ACCOUNT_ID}"
echo "   User: ${CURRENT_USER}"
echo ""

# Selecionar ambiente
echo -e "${BLUE}[2/5] Selecionar ambiente${NC}"
echo "Escolha o ambiente para deploy:"
echo "  1) dev     (desenvolvimento - menor custo)"
echo "  2) staging (homologação - custo médio)"
echo "  3) prod    (produção - maior custo)"
read -p "Digite o número [1-3] (padrão: 1): " env_choice
env_choice=${env_choice:-1}

case $env_choice in
    1) ENV="dev" ;;
    2) ENV="staging" ;;
    3) ENV="prod" ;;
    *) echo -e "${RED}Opção inválida, usando 'dev'${NC}"; ENV="dev" ;;
esac
echo -e "${GREEN}✅ Ambiente selecionado: ${ENV}${NC}"
echo ""

# Selecionar região
echo -e "${BLUE}[3/5] Selecionar região AWS${NC}"
read -p "Digite a região AWS (padrão: us-east-1): " aws_region
AWS_REGION=${aws_region:-us-east-1}
echo -e "${GREEN}✅ Região: ${AWS_REGION}${NC}"
echo ""

# Configurar senhas
echo -e "${BLUE}[4/5] Configurar senhas dos bancos de dados${NC}"
echo "Você pode:"
echo "  1) Gerar senhas automáticas (seguras, recomendado)"
echo "  2) Digitar suas próprias senhas"
read -p "Escolha [1-2] (padrão: 1): " pwd_choice
pwd_choice=${pwd_choice:-1}

if [ "$pwd_choice" == "1" ]; then
    echo -e "${YELLOW}Gerando senhas seguras...${NC}"
    MONGODB_PWD=$(generate_password)
    NEO4J_PWD=$(generate_password)
    CLICKHOUSE_ADMIN_PWD=$(generate_password)
    CLICKHOUSE_RO_PWD=$(generate_password)
    CLICKHOUSE_WR_PWD=$(generate_password)
    echo -e "${GREEN}✅ Senhas geradas${NC}"
else
    echo "Digite as senhas (mínimo 16 caracteres):"
    read -sp "MongoDB root password: " MONGODB_PWD
    echo ""
    read -sp "Neo4j password: " NEO4J_PWD
    echo ""
    read -sp "ClickHouse admin password: " CLICKHOUSE_ADMIN_PWD
    echo ""
    read -sp "ClickHouse readonly password: " CLICKHOUSE_RO_PWD
    echo ""
    read -sp "ClickHouse writer password: " CLICKHOUSE_WR_PWD
    echo ""
    echo -e "${GREEN}✅ Senhas configuradas${NC}"
fi
echo ""

# Criar arquivo de configuração
ENV_FILE="$HOME/.neural-hive-${ENV}-env"

echo -e "${BLUE}[5/5] Salvando configuração${NC}"
cat > "$ENV_FILE" <<EOF
# Neural Hive-Mind - Configuração de Deployment EKS
# Ambiente: ${ENV}
# Gerado em: $(date)

export ENV=${ENV}
export AWS_REGION=${AWS_REGION}
export AWS_ACCOUNT_ID=${ACCOUNT_ID}
export CLUSTER_NAME=neural-hive-${ENV}
export ECR_REGISTRY=${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Database passwords
export TF_VAR_mongodb_root_password="${MONGODB_PWD}"
export TF_VAR_neo4j_password="${NEO4J_PWD}"
export TF_VAR_clickhouse_admin_password="${CLICKHOUSE_ADMIN_PWD}"
export TF_VAR_clickhouse_readonly_password="${CLICKHOUSE_RO_PWD}"
export TF_VAR_clickhouse_writer_password="${CLICKHOUSE_WR_PWD}"

# AWS User info
export AWS_USER_ARN="${CURRENT_USER}"
EOF

chmod 600 "$ENV_FILE"
echo -e "${GREEN}✅ Configuração salva em: ${ENV_FILE}${NC}"
echo ""

# Carregar configuração
source "$ENV_FILE"

# Exibir resumo
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Resumo da Configuração${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""
echo "Ambiente: ${ENV}"
echo "Região: ${AWS_REGION}"
echo "Cluster: ${CLUSTER_NAME}"
echo "Account ID: ${ACCOUNT_ID}"
echo "ECR Registry: ${ECR_REGISTRY}"
echo ""
echo "Senhas configuradas:"
echo "  - MongoDB: ${MONGODB_PWD:0:5}***"
echo "  - Neo4j: ${NEO4J_PWD:0:5}***"
echo "  - ClickHouse Admin: ${CLICKHOUSE_ADMIN_PWD:0:5}***"
echo "  - ClickHouse ReadOnly: ${CLICKHOUSE_RO_PWD:0:5}***"
echo "  - ClickHouse Writer: ${CLICKHOUSE_WR_PWD:0:5}***"
echo ""

# Salvar senhas em arquivo separado (backup)
PASSWORDS_FILE="$HOME/.neural-hive-${ENV}-passwords.txt"
cat > "$PASSWORDS_FILE" <<EOF
Neural Hive-Mind - Senhas dos Bancos de Dados
Ambiente: ${ENV}
Gerado em: $(date)

IMPORTANTE: Guarde este arquivo em local seguro!

MongoDB Root Password: ${MONGODB_PWD}
Neo4j Password: ${NEO4J_PWD}
ClickHouse Admin Password: ${CLICKHOUSE_ADMIN_PWD}
ClickHouse ReadOnly Password: ${CLICKHOUSE_RO_PWD}
ClickHouse Writer Password: ${CLICKHOUSE_WR_PWD}
EOF
chmod 600 "$PASSWORDS_FILE"
echo -e "${YELLOW}⚠️  Senhas salvas em: ${PASSWORDS_FILE}${NC}"
echo -e "${YELLOW}⚠️  Guarde este arquivo em local SEGURO!${NC}"
echo ""

# Estimativa de custos
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Estimativa de Custos AWS${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""
case $ENV in
    dev)
        echo "Custo estimado: ~\$267/mês"
        echo "  - EKS Control Plane: \$72"
        echo "  - 3x t3.medium nodes: ~\$75"
        echo "  - NAT Gateways: ~\$100"
        echo "  - Outros: ~\$20"
        ;;
    staging)
        echo "Custo estimado: ~\$600/mês"
        echo "  - EKS Control Plane: \$72"
        echo "  - 6x t3.large nodes: ~\$300"
        echo "  - NAT Gateways: ~\$100"
        echo "  - RDS/ElastiCache: ~\$100"
        echo "  - Outros: ~\$28"
        ;;
    prod)
        echo "Custo estimado: ~\$1,127/mês"
        echo "  - EKS Control Plane: \$72"
        echo "  - 6x m5.large nodes: ~\$450"
        echo "  - NAT Gateways: ~\$100"
        echo "  - RDS/ElastiCache: ~\$350"
        echo "  - ALB/NLB: ~\$50"
        echo "  - Outros: ~\$105"
        ;;
esac
echo ""
echo -e "${YELLOW}💡 Dica: Use Spot Instances para reduzir custos em até 70%${NC}"
echo ""

# Próximos passos
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Próximos Passos${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""
echo "1. Carregar configuração:"
echo "   source ${ENV_FILE}"
echo ""
echo "2. Executar deployment:"
echo "   cd /jimy/Neural-Hive-Mind"
echo "   ./scripts/deploy/deploy-eks-complete.sh"
echo ""
echo "3. Acompanhar progresso (tempo estimado: 20-30 min)"
echo ""
echo "4. Validar deployment:"
echo "   kubectl get pods --all-namespaces"
echo "   ./tests/phase1-end-to-end-test.sh"
echo ""
echo -e "${GREEN}✅ Setup concluído! Execute os comandos acima para iniciar o deployment.${NC}"
echo ""

# Perguntar se deseja iniciar deployment agora
read -p "Deseja iniciar o deployment agora? (y/N): " start_deploy
if [[ $start_deploy =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${BLUE}Iniciando deployment...${NC}"
    cd /jimy/Neural-Hive-Mind
    ./scripts/deploy/deploy-eks-complete.sh
else
    echo ""
    echo -e "${YELLOW}Para iniciar o deployment posteriormente, execute:${NC}"
    echo "  source ${ENV_FILE}"
    echo "  cd /jimy/Neural-Hive-Mind"
    echo "  ./scripts/deploy/deploy-eks-complete.sh"
fi
