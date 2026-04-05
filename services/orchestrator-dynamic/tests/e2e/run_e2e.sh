#!/bin/bash
set -e

# Script para executar testes E2E Vault+SPIFFE
# Uso: ./run_e2e.sh [comando]
#   start - Inicia infraestrutura
#   test - Executa testes
#   stop - Para infraestrutura
#   logs - Mostra logs
#   restart - Reinicia infraestrutura
#   clean - Remove volumes e containers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
E2E_DIR="$PROJECT_ROOT/services/orchestrator-dynamic/tests/e2e"

cd "$E2E_DIR"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar docker-compose
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "docker-compose não encontrado. Instale primeiro."
        exit 1
    fi

    # Usar docker compose se disponível, senão docker-compose
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
}

# Iniciar infraestrutura
cmd_start() {
    log_info "Iniciando infraestrutura E2E..."

    check_docker_compose

    # Criar diretórios necessários
    mkdir -p scripts

    # Executar docker-compose
    $DOCKER_COMPOSE -f docker-compose.e2e up -d

    log_info "Aguardando serviços ficarem prontos..."
    sleep 10

    # Verificar saúde dos serviços
    log_info "Verificando Vault..."
    if curl -s http://localhost:8200/v1/sys/health > /dev/null 2>&1; then
        log_info "✓ Vault está pronto"
    else
        log_warn "Vault ainda não está pronto (pode precisar de mais tempo)"
    fi

    log_info "Infraestrutura iniciada!"
    log_info "Use './run_e2e.sh logs' para acompanhar os logs"
    log_info "Use './run_e2e.sh test' para executar os testes"
}

# Executar testes
cmd_test() {
    log_info "Executando testes E2E..."

    check_docker_compose

    # Verificar se test-runner está rodando
    if ! $DOCKER_COMPOSE -f docker-compose.e2e ps test-runner | grep -q "Up"; then
        log_error "Container test-runner não está rodando. Execute 'start' primeiro."
        exit 1
    fi

    # Executar testes
    $DOCKER_COMPOSE -f docker-compose.e2e exec -e RUN_VAULT_SPIFFE_E2E=true test-runner \
        pytest tests/e2e/test_vault_spiffe_e2e.py -v --tb=short "$@"

    log_info "Testes concluídos!"
}

# Executar testes locais (sem docker)
cmd_test_local() {
    log_info "Executando testes E2E localmente..."

    export RUN_VAULT_SPIFFE_E2E=true
    export VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
    export VAULT_TOKEN="${VAULT_TOKEN:-dev-root-token}"

    cd "$PROJECT_ROOT/services/orchestrator-dynamic"
    pytest tests/e2e/test_vault_spiffe_e2e.py -v --tb=short "$@"
}

# Parar infraestrutura
cmd_stop() {
    log_info "Parando infraestrutura E2E..."

    check_docker_compose

    $DOCKER_COMPOSE -f docker-compose.e2e down

    log_info "Infraestrutura parada!"
}

# Mostrar logs
cmd_logs() {
    check_docker_compose

    service="${1:-}"

    if [ -n "$service" ]; then
        $DOCKER_COMPOSE -f docker-compose.e2e logs -f "$service"
    else
        $DOCKER_COMPOSE -f docker-compose.e2e logs -f
    fi
}

# Reiniciar infraestrutura
cmd_restart() {
    log_info "Reiniciando infraestrutura E2E..."
    cmd_stop
    cmd_start
}

# Limpar tudo
cmd_clean() {
    log_info "Limpando infraestrutura E2E..."

    check_docker_compose

    $DOCKER_COMPOSE -f docker-compose.e2e down -v

    log_info "Limpeza concluída!"
}

# Status dos serviços
cmd_status() {
    check_docker_compose

    log_info "Status dos serviços:"
    $DOCKER_COMPOSE -f docker-compose.e2e ps
}

# Ajuda
cmd_help() {
    cat << EOF
Uso: ./run_e2e.sh [comando] [opções]

Comandos:
    start       Inicia infraestrutura Docker Compose
    test        Executa testes dentro do container
    test-local  Executa testes localmente (requer Vault/SPIRE rodando)
    stop        Para infraestrutura
    restart     Reinicia infraestrutura
    logs        Mostra logs [serviço]
    status      Mostra status dos serviços
    clean       Para e remove volumes
    help        Mostra esta ajuda

Exemplos:
    ./run_e2e.sh start
    ./run_e2e.sh test
    ./run_e2e.sh test -k "test_01"
    ./run_e2e.sh logs vault
    ./run_e2e.sh clean

Variáveis de ambiente:
    VAULT_ADDR          Endereço Vault (default: http://localhost:8200)
    VAULT_TOKEN         Token Vault (default: dev-root-token)
    RUN_VAULT_SPIFFE_E2E Habilita testes reais (default: true)

EOF
}

# Main
case "${1:-help}" in
    start)
        cmd_start
        ;;
    test)
        shift
        cmd_test "$@"
        ;;
    test-local)
        shift
        cmd_test_local "$@"
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        shift
        cmd_logs "$@"
        ;;
    status)
        cmd_status
        ;;
    clean)
        cmd_clean
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        log_error "Comando desconhecido: $1"
        cmd_help
        exit 1
        ;;
esac
