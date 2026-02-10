#!/bin/bash
set -e

echo "🔨 Compilando todos os arquivos protobuf do Neural Hive-Mind..."

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Função para compilar proto de um serviço
compile_service_proto() {
    local service_name=$1
    local service_path=$2
    
    echo -e "${YELLOW}📦 Compilando protos de ${service_name}...${NC}"
    
    if [ ! -d "$service_path" ]; then
        echo -e "${RED}❌ Diretório não encontrado: $service_path${NC}"
        return 1
    fi
    
    cd "$service_path"
    
    if [ ! -f "Makefile" ]; then
        echo -e "${RED}❌ Makefile não encontrado em $service_path${NC}"
        return 1
    fi
    
    if ! make proto; then
        echo -e "${RED}❌ Falha ao compilar protos de ${service_name}${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✅ Protos de ${service_name} compilados com sucesso${NC}"
    cd - > /dev/null
}

# Compilar neural_hive_specialists library (base)
echo -e "${YELLOW}📦 Compilando neural_hive_specialists library...${NC}"
make proto-gen
echo -e "${GREEN}✅ neural_hive_specialists library compilada${NC}"

# Compilar protos dos serviços
compile_service_proto "Queen Agent" "services/queen-agent"
compile_service_proto "Analyst Agents" "services/analyst-agents"
compile_service_proto "Optimizer Agents" "services/optimizer-agents"

# Verificar arquivos gerados
echo ""
echo -e "${YELLOW}🔍 Verificando arquivos gerados...${NC}"

check_proto_files() {
    local service=$1
    local proto_dir=$2
    local proto_name=$3
    
    if [ -f "${proto_dir}/${proto_name}_pb2.py" ] && [ -f "${proto_dir}/${proto_name}_pb2_grpc.py" ]; then
        echo -e "${GREEN}✅ ${service}: ${proto_name} OK${NC}"
    else
        echo -e "${RED}❌ ${service}: ${proto_name} FALTANDO${NC}"
    fi
}

check_proto_files "Queen Agent" "services/queen-agent/src/proto" "queen_agent"
check_proto_files "Analyst Agents" "services/analyst-agents/src/proto" "analyst_agent"
check_proto_files "Optimizer Agents" "services/optimizer-agents/src/proto" "optimizer_agent"

echo ""
echo -e "${GREEN}🎉 Compilação de protos concluída!${NC}"

# Fix imports in generated gRPC files
echo ""
echo -e "${YELLOW}🔧 Corrigindo imports em arquivos gRPC gerados...${NC}"
python3 scripts/fix_proto_imports.py
echo -e "${GREEN}✅ Imports corrigidos!${NC}"
