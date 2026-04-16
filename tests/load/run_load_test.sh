#!/bin/bash
#
# Script executável para rodar testes de carga Locust
# para Doc Ingestion (8018) e Data Migration (8019)
#

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações padrão
DOC_INGESTION_HOST="${DOC_INGESTION_HOST:-http://localhost:8018}"
DATA_MIGRATION_HOST="${DATA_MIGRATION_HOST:-http://localhost:8019}"
USERS="${USERS:-10}"
SPAWN_RATE="${SPAWN_RATE:-1}"
RUN_TIME="${RUN_TIME:-5m}"
LOCUSTFILE="${LOCUSTFILE:-doc_ingestion_migration_locustfile.py}"
HEADLESS="${HEADLESS:-true}"
HOST="${HOST:-http://localhost:8018}"

# Funções de helper
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verifica se Locust está instalado
check_locust() {
    if ! command -v locust &> /dev/null; then
        log_error "Locust não está instalado"
        echo "Instale com: pip install locust>=2.15.0 httpx>=0.25.0"
        exit 1
    fi
    log_info "Locust encontrado: $(locust --version | head -1)"
}

# Verifica se os serviços estão rodando
check_services() {
    log_info "Verificando se os serviços estão rodando..."

    # Check Doc Ingestion
    if curl -s -f "${DOC_INGESTION_HOST}/health" > /dev/null 2>&1; then
        log_info "Doc Ingestion está rodando em ${DOC_INGESTION_HOST}"
    else
        log_warn "Doc Ingestion não está respondendo em ${DOC_INGESTION_HOST}"
    fi

    # Check Data Migration
    if curl -s -f "${DATA_MIGRATION_HOST}/health" > /dev/null 2>&1; then
        log_info "Data Migration está rodando em ${DATA_MIGRATION_HOST}"
    else
        log_warn "Data Migration não está respondendo em ${DATA_MIGRATION_HOST}"
    fi
}

# Mostra ajuda
show_help() {
    cat << EOF
Uso: $0 [OPÇÕES]

Executa testes de carga Locust para Doc Ingestion e Data Migration.

OPÇÕES:
    -u, --users N              Número de usuários simultâneos (default: 10)
    -r, --spawn-rate N         Taxa de criação de usuários por segundo (default: 1)
    -t, --run-time DURAÇÃO     Duração do teste (ex: 1m, 5m, 1h) (default: 5m)
    -f, --locustfile ARQUIVO   Arquivo locustfile (default: doc_ingestion_migration_locustfile.py)
    -H, --host HOST            Host principal (default: http://localhost:8018)
    --web                      Modo web (interface gráfica)
    --headless                 Modo headless (default)
    --doc-host HOST            Host do Doc Ingestion (default: http://localhost:8018)
    --migration-host HOST      Host do Data Migration (default: http://localhost:8019)
    -h, --help                 Mostra esta ajuda

AMBIENTE:
    DOC_INGESTION_HOST         Host do Doc Ingestion
    DATA_MIGRATION_HOST        Host do Data Migration
    USERS                      Número de usuários
    SPAWN_RATE                 Taxa de criação de usuários
    RUN_TIME                   Duração do teste

EXEMPLOS:
    # Teste rápido com 5 usuários
    $0 --users 5 --run-time 1m

    # Teste longo com interface web
    $0 --users 20 --run-time 30m --web

    # Teste de pico (3x carga normal)
    $0 --users 30 --spawn-rate 5 --run-time 10m

EOF
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--users)
            USERS="$2"
            shift 2
            ;;
        -r|--spawn-rate)
            SPAWN_RATE="$2"
            shift 2
            ;;
        -t|--run-time)
            RUN_TIME="$2"
            shift 2
            ;;
        -f|--locustfile)
            LOCUSTFILE="$2"
            shift 2
            ;;
        -H|--host)
            HOST="$2"
            shift 2
            ;;
        --doc-host)
            DOC_INGESTION_HOST="$2"
            shift 2
            ;;
        --migration-host)
            DATA_MIGRATION_HOST="$2"
            shift 2
            ;;
        --web)
            HEADLESS="false"
            shift
            ;;
        --headless)
            HEADLESS="true"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            show_help
            exit 1
            ;;
    esac
done

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Verifica se o locustfile existe
if [ ! -f "$LOCUSTFILE" ]; then
    log_error "Locustfile não encontrado: $LOCUSTFILE"
    exit 1
fi

# Main
log_info "=========================================="
log_info "Load Test - Doc Ingestion & Data Migration"
log_info "=========================================="
log_info "Locustfile: $LOCUSTFILE"
log_info "Users: $USERS"
log_info "Spawn Rate: $SPAWN_RATE"
log_info "Run Time: $RUN_TIME"
log_info "Mode: $([ "$HEADLESS" = "true" ] && echo "Headless" || echo "Web")"
log_info "=========================================="

check_locust
check_services

# Exporta hosts para o Locust
export DOC_INGESTION_HOST
export DATA_MIGRATION_HOST

# Constrói comando
LOCUST_CMD="locust -f $LOCUSTFILE --host $HOST"

if [ "$HEADLESS" = "true" ]; then
    LOCUST_CMD="$LOCUST_CMD --headless -u $USERS -r $SPAWN_RATE -t $RUN_TIME"
    log_info "Iniciando teste em modo headless..."
    echo ""
else
    LOCUST_CMD="$LOCUST_CMD --ui -u $USERS -r $SPAWN_RATE -t $RUN_TIME"
    log_info "Iniciando teste em modo web..."
    log_info "Acesse: http://localhost:8089"
    echo ""
fi

# Executa Locust
eval $LOCUST_CMD

exit_code=$?

if [ $exit_code -eq 0 ]; then
    log_info "Teste concluído com sucesso"
else
    log_error "Teste falhou com código de saída: $exit_code"
fi

exit $exit_code
