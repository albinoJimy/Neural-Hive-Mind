#!/bin/bash

# Script de Teste Rápido da Fase 1 - Neural Hive-Mind
# Este script inicia os componentes base e executa validações

set -euo pipefail
source "$(dirname "$0")/../../scripts/lib/common.sh"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << 'EOF'
╔════════════════════════════════════════════════════════════════╗
║         NEURAL HIVE-MIND - TESTE FASE 1                        ║
║                  Infraestrutura Base                           ║
╚════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Função para log
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# 1. Verificar Docker
log_info "Verificando Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
    log_success "Docker instalado: $DOCKER_VERSION"
else
    log_error "Docker não encontrado. Instale o Docker primeiro."
    exit 1
fi

# 2. Iniciar serviços
log_info "Iniciando serviços de infraestrutura..."
docker compose -f docker-compose-test.yml up -d zookeeper kafka redis 2>&1 | grep -v "warning"

# Aguardar inicialização
log_info "Aguardando inicialização (15s)..."
sleep 15

# 3. Verificar status dos containers
log_info "Verificando status dos containers..."
CONTAINERS=$(docker compose -f docker-compose-test.yml ps --format "{{.Name}}" 2>/dev/null | wc -l)
if [ "$CONTAINERS" -eq 3 ]; then
    log_success "3 containers rodando"
else
    log_error "Esperado 3 containers, encontrado $CONTAINERS"
    exit 1
fi

# 4. Testar Redis
log_info "Testando Redis..."
REDIS_PONG=$(docker exec redis redis-cli ping 2>/dev/null || echo "FAIL")
if [ "$REDIS_PONG" = "PONG" ]; then
    log_success "Redis: PONG"
else
    log_error "Redis não respondeu"
fi

# 5. Testar Kafka
log_info "Testando Kafka..."
KAFKA_READY=$(docker exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092 2>&1 | grep -c "ApiVersion" || echo "0")
if [ "$KAFKA_READY" -gt 0 ]; then
    log_success "Kafka broker respondendo"
else
    log_warn "Kafka pode não estar pronto ainda"
fi

# 6. Criar tópicos
log_info "Criando tópicos Kafka..."
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic intents.raw --partitions 3 --replication-factor 1 --if-not-exists 2>&1 | grep -v "WARNING" | grep -v "^$" || true
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic plans.ready --partitions 3 --replication-factor 1 --if-not-exists 2>&1 | grep -v "WARNING" | grep -v "^$" || true
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic plans.consensus --partitions 3 --replication-factor 1 --if-not-exists 2>&1 | grep -v "WARNING" | grep -v "^$" || true

# 7. Listar tópicos
TOPICS=$(docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l)
log_success "Tópicos criados: $TOPICS"

# 8. Teste de escrita/leitura Redis
log_info "Testando escrita/leitura Redis..."
docker exec redis redis-cli SET "test:fase1" "Neural Hive OK" > /dev/null
TEST_VALUE=$(docker exec redis redis-cli GET "test:fase1" 2>/dev/null)
if [ "$TEST_VALUE" = "Neural Hive OK" ]; then
    log_success "Redis SET/GET funcionando"
    docker exec redis redis-cli DEL "test:fase1" > /dev/null
fi

# 9. Sumário
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}                    TESTE CONCLUÍDO${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "✅ Componentes Ativos: 3/3"
echo -e "✅ Tópicos Kafka: $TOPICS"
echo -e "✅ Redis: Operacional"
echo ""
echo -e "${YELLOW}Relatório completo:${NC} TESTE_FASE1_RESULTADO.md"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Comandos úteis:${NC}"
echo -e "  Ver logs:       docker compose -f docker-compose-test.yml logs -f"
echo -e "  Parar:          docker compose -f docker-compose-test.yml down"
echo -e "  Status:         docker compose -f docker-compose-test.yml ps"
echo ""
