#!/bin/bash
#
# run_smoke_tests.sh
#
# Script para executar smoke tests E2E do Neural Hive-Mind.
#
# Uso:
#   ./run_smoke_tests.sh [opções]
#
# Opções:
#   -v, --verbose    Saída verbosa
#   -k, --keep-going Continua mesmo com falhas
#   -s, --service    Executa apenas para um serviço específico
#   -h, --help       Mostra ajuda
#
# Variáveis de Ambiente:
#   GATEWAY_URL      URL do Gateway (default: detecta K8s ou localhost:8000)
#   STE_URL          URL do STE (default: detecta K8s ou localhost:8001)
#   CONSENSUS_URL    URL do Consensus (default: detecta K8s ou localhost:8002)
#   TIMEOUT          Timeout em minutos (default: 10)
#

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Variáveis padrão
VERBOSE=false
KEEP_GOING=false
SPECIFIC_SERVICE=""
TIMEOUT_MINUTES=10
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Detecta ambiente Kubernetes ou local
detect_environment() {
    if kubectl cluster-info &>/dev/null; then
        log_info "Ambiente Kubernetes detectado"
        export K8S_ENV=true

        # Detecta namespace atual
        CURRENT_NS=$(kubectl config view --minify --output 'jsonpath={..namespace}')
        log_info "Namespace atual: ${CURRENT_NS:-default}"

        # Configura URLs baseadas em services K8s
        : "${GATEWAY_URL:=http://gateway-intencoes.neural-hive-gateway.svc.cluster.local:8000}"
        : "${STE_URL:=http://semantic-translation-engine.neural-hive-semantic.svc.cluster.local:8001}"
        : "${CONSENSUS_URL:=http://consensus-engine.neural-hive-consensus.svc.cluster.local:8002}"
        : "${ORCHESTRATOR_URL:=http://orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local:8003}"
        : "${APPROVAL_URL:=http://approval-service.neural-hive-approval.svc.cluster.local:8004}"
        : "${WORKER_URL:=http://worker-agents.neural-hive-execution.svc.cluster.local:8005}"
        : "${QUEEN_URL:=http://queen-agent.neural-hive-agents.svc.cluster.local:8006}"
    else
        log_info "Ambiente local detectado"
        export K8S_ENV=false

        # Configura URLs locais
        : "${GATEWAY_URL:=http://localhost:8000}"
        : "${STE_URL:=http://localhost:8001}"
        : "${CONSENSUS_URL:=http://localhost:8002}"
        : "${ORCHESTRATOR_URL:=http://localhost:8003}"
        : "${APPROVAL_URL:=http://localhost:8004}"
        : "${WORKER_URL:=http://localhost:8005}"
        : "${QUEEN_URL:=http://localhost:8006}"
    fi
}

# Parse argumentos
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -k|--keep-going)
                KEEP_GOING=true
                shift
                ;;
            -s|--service)
                SPECIFIC_SERVICE="$2"
                shift 2
                ;;
            -t|--timeout)
                TIMEOUT_MINUTES="$2"
                shift 2
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
}

show_help() {
    cat << EOF
Uso: $(basename "$0") [opções]

Smoke Tests E2E - Neural Hive-Mind

Opções:
  -v, --verbose       Saída verbosa do pytest
  -k, --keep-going    Continua mesmo com falhas
  -s, --service SVC   Executa apenas para o serviço especificado
                      (gateway, ste, consensus, orchestrator, approval, worker, queen)
  -t, --timeout MIN   Timeout em minutos (default: 10)
  -h, --help          Mostra esta ajuda

Variáveis de Ambiente:
  GATEWAY_URL         URL do Gateway de Intenções
  STE_URL             URL do Semantic Translation Engine
  CONSENSUS_URL       URL do Consensus Engine
  TIMEOUT             Timeout em minutos (default: 10)

Exemplos:
  # Executa todos os smoke tests
  $(basename "$0")

  # Executa apenas para Gateway
  $(basename "$0") -s gateway

  # Executa com saída verbosa
  $(basename "$0") -v

  # Executa continuando mesmo com falhas
  $(basename "$0") -k

EOF
}

# Pré-checks
pre_checks() {
    log_info "Executando pré-checks..."

    # Verifica Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 não encontrado"
        exit 1
    fi

    # Verifica pytest
    if ! command -v pytest &> /dev/null; then
        log_error "pytest não encontrado. Execute: pip install pytest pytest-asyncio httpx"
        exit 1
    fi

    # Verifica dependências Python
    log_info "Verificando dependências..."
    python3 -c "import httpx, pytest" 2>/dev/null || {
        log_error "Dependências Python faltando. Execute:"
        log_error "  pip install httpx pytest pytest-asyncio"
        exit 1
    }

    log_success "Pré-checks concluídos"
}

# Executa os testes
run_tests() {
    cd "$PROJECT_ROOT"

    local pytest_args=(
        "-m" "smoke"
        "-v" if [ "$VERBOSE" = true ] else "-q"
        "--tb=short"
        "--timeout=${TIMEOUT_MINUTES}m"
        "$SCRIPT_DIR"
    )

    # Adiciona -x para parar na primeira falha se keep-going não está ativo
    if [ "$KEEP_GOING" = false ]; then
        pytest_args+=("-x")
    fi

    # Filtra por serviço específico se especificado
    if [ -n "$SPECIFIC_SERVICE" ]; then
        case "$SPECIFIC_SERVICE" in
            gateway)
                pytest_args+=("$SCRIPT_DIR/test_smoke_gateway.py")
                ;;
            ste|semantic)
                pytest_args+=("$SCRIPT_DIR/test_smoke_ste.py")
                ;;
            consensus)
                pytest_args+=("$SCRIPT_DIR/test_smoke_consensus.py")
                ;;
            orchestrator)
                pytest_args+=("$SCRIPT_DIR/test_smoke_orchestrator.py")
                ;;
            approval)
                pytest_args+=("$SCRIPT_DIR/test_smoke_approval.py")
                ;;
            worker)
                pytest_args+=("$SCRIPT_DIR/test_smoke_workers.py")
                ;;
            queen)
                pytest_args+=("$SCRIPT_DIR/test_smoke_queen.py")
                ;;
            *)
                log_error "Serviço desconhecido: $SPECIFIC_SERVICE"
                log_info "Serviços disponíveis: gateway, ste, consensus, orchestrator, approval, worker, queen"
                exit 1
                ;;
        esac
        log_info "Executando smoke tests para: $SPECIFIC_SERVICE"
    else
        log_info "Executando smoke tests para todos os serviços"
    fi

    # Exporta URLs como variáveis de ambiente
    export GATEWAY_URL STE_URL CONSENSUS_URL ORCHESTRATOR_URL APPROVAL_URL WORKER_URL QUEEN_URL

    log_info "Timeout configurado: ${TIMEOUT_MINUTES} minutos"
    log_info "URLs configuradas:"
    log_info "  Gateway: $GATEWAY_URL"
    log_info "  STE: $STE_URL"
    log_info "  Consensus: $CONSENSUS_URL"

    echo ""
    log_info "Iniciando execução dos testes..."
    echo "=================================="

    # Executa pytest
    if pytest "${pytest_args[@]}"; then
        echo ""
        log_success "=================================="
        log_success "Smoke tests finalizados com sucesso!"
        return 0
    else
        local exit_code=$?
        echo ""
        log_error "=================================="
        log_error "Smoke tests finalizados com erros (exit code: $exit_code)"
        return $exit_code
    fi
}

# Relatório final
print_summary() {
    local exit_code=$1

    echo ""
    echo "=================================="
    echo "RESUMO DOS SMOKE TESTS"
    echo "=================================="
    echo "Ambiente: $([ "$K8S_ENV" = true ] && echo "Kubernetes" || echo "Local")"
    echo "Timeout: ${TIMEOUT_MINUTES} minutos"
    echo "Serviço: ${SPECIFIC_SERVICE:-Todos}"

    if [ $exit_code -eq 0 ]; then
        log_success "Status: SUCESSO"
        echo ""
        echo "Todos os smoke tests passaram!"
    else
        log_error "Status: FALHA"
        echo ""
        echo "Alguns smoke tests falharam."
        echo "Verifique o output acima para detalhes."
    fi

    echo "=================================="

    return $exit_code
}

# Main
main() {
    echo "=================================="
    echo "SMOKE TESTS E2E - NEURAL HIVE-MIND"
    echo "=================================="
    echo ""

    parse_args "$@"
    detect_environment
    pre_checks

    local start_time=$(date +%s)

    if run_tests; then
        local exit_code=0
    else
        local exit_code=$?
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    log_info "Duração total: ${duration} segundos"

    print_summary $exit_code
    exit $exit_code
}

# Executa main
main "$@"
