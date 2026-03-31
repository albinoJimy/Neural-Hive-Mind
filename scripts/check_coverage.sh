#!/usr/bin/env bash
# =============================================================================
# Neural Hive-Mind - Script de Verificação de Cobertura de Testes
# =============================================================================
# Verifica se a cobertura de testes atinge o threshold mínimo de 70%.
# Pode ser executado localmente ou no CI/CD.
#
# Uso:
#   ./scripts/check_coverage.sh                    # Verifica threshold padrão (70%)
#   ./scripts/check_coverage.sh --threshold 80     # Threshold customizado
#   ./scripts/check_coverage.sh --report           # Gera relatórios HTML/XML
#   ./scripts/check_coverage.sh --verbose          # Saída detalhada
#
# GAP-04: Meta de cobertura 70%
# CR-08: Configurar threshold no CI/CD
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configurações
# -----------------------------------------------------------------------------

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Threshold padrão de cobertura (pode ser sobrescrito por argumento)
REQUIRED_COVERAGE=${REQUIRED_COVERAGE:-70}

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RESULTS_DIR="${PROJECT_ROOT}/tests/results/coverage"
HTML_REPORT_DIR="${PROJECT_ROOT}/tests/results/coverage/html"

# Flags
VERBOSE=false
GENERATE_REPORT=false
COVERAGE_FILE="${PROJECT_ROOT}/.coverage"

# -----------------------------------------------------------------------------
# Funções de Utilidade
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}[VERBOSE]${NC} $*" >&2
    fi
}

show_usage() {
    cat << EOF
Uso: $(basename "$0") [OPÇÕES]

Verifica se a cobertura de testes atinge o threshold mínimo.

OPÇÕES:
    -t, --threshold N      Threshold mínimo de cobertura (padrão: 70)
    -r, --report           Gera relatórios HTML e XML
    -v, --verbose          Saída detalhada
    -h, --help             Mostra esta mensagem de ajuda

VARIÁVEIS DE AMBIENTE:
    REQUIRED_COVERAGE      Threshold mínimo (padrão: 70)

EXEMPLOS:
    $(basename "$0")                           # Verifica 70%
    $(basename "$0") --threshold 80            # Verifica 80%
    $(basename "$0") --report                  # Gera relatórios
    REQUIRED_COVERAGE=75 $(basename "$0")      # Usa variável de ambiente

EOF
}

# -----------------------------------------------------------------------------
# Funções de Cobertura
# -----------------------------------------------------------------------------

check_coverage_file() {
    if [[ ! -f "$COVERAGE_FILE" ]]; then
        log_error "Arquivo de cobertura não encontrado: $COVERAGE_FILE"
        log_info "Execute os testes com cobertura primeiro:"
        log_info "  pytest --cov --cov-report=term-missing"
        return 1
    fi
    return 0
}

get_coverage_from_xml() {
    local xml_file="$1"
    local line_rate

    if [[ ! -f "$xml_file" ]]; then
        log_error "Arquivo XML de cobertura não encontrado: $xml_file"
        echo "0"
        return 1
    fi

    # Extrai line-rate do XML usando python
    line_rate=$(python3 -c "
import xml.etree.ElementTree as ET
import sys
try:
    tree = ET.parse('$xml_file')
    root = tree.getroot()
    line_rate = float(root.attrib.get('line-rate', 0))
    print(f'{line_rate * 100:.2f}')
except Exception as e:
    print('0', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null || echo "0")

    echo "$line_rate"
}

get_coverage_from_coverage_file() {
    local coverage_percent

    if ! command -v coverage &> /dev/null; then
        log_warning "coverage.py não instalado, tentando método alternativo..."
        return 1
    fi

    # Usa coverage report para obter a porcentagem
    coverage_percent=$(cd "$PROJECT_ROOT" && coverage report --format=total 2>/dev/null | grep -oP '\d+(?=\%)' | head -1 || echo "0")

    echo "$coverage_percent"
}

generate_coverage_reports() {
    log_info "Gerando relatórios de cobertura..."

    # Cria diretórios
    mkdir -p "$RESULTS_DIR"
    mkdir -p "$HTML_REPORT_DIR"

    # Gera relatório XML
    log_info "Gerando relatório XML: ${RESULTS_DIR}/coverage.xml"
    (cd "$PROJECT_ROOT" && coverage xml -o "${RESULTS_DIR}/coverage.xml" 2>/dev/null) || {
        log_warning "Falha ao gerar relatório XML"
    }

    # Gera relatório HTML
    log_info "Gerando relatório HTML: ${HTML_REPORT_DIR}/index.html"
    (cd "$PROJECT_ROOT" && coverage html -d "$HTML_REPORT_DIR" 2>/dev/null) || {
        log_warning "Falha ao gerar relatório HTML"
    }

    # Gera relatório JSON
    log_info "Gerando relatório JSON: ${RESULTS_DIR}/coverage.json"
    (cd "$PROJECT_ROOT" && coverage json -o "${RESULTS_DIR}/coverage.json" 2>/dev/null) || {
        log_warning "Falha ao gerar relatório JSON"
    }

    log_success "Relatórios gerados em: $RESULTS_DIR"
}

print_coverage_summary() {
    local current_coverage="$1"
    local threshold="$2"

    echo ""
    echo "============================================================================"
    echo "                       COVERAGE SUMMARY"
    echo "============================================================================"
    echo ""
    echo "  Current Coverage:  ${current_coverage}%"
    echo "  Required Coverage: ${threshold}%"
    echo ""

    local difference
    difference=$(echo "$current_coverage - $threshold" | bc -l 2>/dev/null || echo "0")

    if (( $(echo "$current_coverage >= $threshold" | bc -l 2>/dev/null || echo "0") )); then
        local margin
        margin=$(printf "%.2f" "$difference")
        echo -e "  Status: ${GREEN}PASS${NC}"
        echo "  Margin: +${margin}%"
    else
        local gap
        gap=$(printf "%.2f" "$(echo "$difference * -1" | bc -l)")
        echo -e "  Status: ${RED}FAIL${NC}"
        echo "  Gap: -${gap}%"
        echo ""
        log_error "Cobertura abaixo do threshold mínimo!"
        log_info "Execute 'pytest --cov-report=term-missing' para ver linhas não cobertas."
    fi

    echo ""
    echo "============================================================================"
    echo ""
}

check_threshold() {
    local current_coverage="$1"
    local threshold="$2"

    log_verbose "Verificando threshold: ${current_coverage}% >= ${threshold}%"

    # Compara usando bc para lidar com decimais
    if (( $(echo "$current_coverage >= $threshold" | bc -l 2>/dev/null || echo "0") )); then
        return 0
    else
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Parse Argumentos
# -----------------------------------------------------------------------------

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--threshold)
                REQUIRED_COVERAGE="$2"
                shift 2
                ;;
            -r|--report)
                GENERATE_REPORT=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Opção desconhecida: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    parse_args "$@"

    log_info "Neural Hive-Mind - Coverage Check"
    log_verbose "Threshold requerido: ${REQUIRED_COVERAGE}%"

    # Verifica se existe arquivo .coverage
    if ! check_coverage_file; then
        exit 1
    fi

    # Obtém cobertura atual
    log_info "Obtendo cobertura atual..."

    # Tenta obter do arquivo .coverage primeiro
    current_coverage=$(get_coverage_from_coverage_file)

    # Se falhar, tenta de um XML existente
    if [[ -z "$current_coverage" || "$current_coverage" == "0" ]]; then
        existing_xml="${RESULTS_DIR}/coverage.xml"
        if [[ -f "$existing_xml" ]]; then
            current_coverage=$(get_coverage_from_xml "$existing_xml")
        fi
    fi

    # Se ainda falhar, gera XML e tenta de novo
    if [[ -z "$current_coverage" || "$current_coverage" == "0" ]]; then
        log_verbose "Gerando XML para obter cobertura..."
        mkdir -p "$RESULTS_DIR"
        (cd "$PROJECT_ROOT" && coverage xml -o "${RESULTS_DIR}/coverage.xml" 2>/dev/null) || {
            log_error "Não foi possível obter a cobertura. Execute os testes primeiro."
            exit 1
        }
        current_coverage=$(get_coverage_from_xml "${RESULTS_DIR}/coverage.xml")
    fi

    log_verbose "Cobertura atual: ${current_coverage}%"

    # Gera relatórios se solicitado
    if [[ "$GENERATE_REPORT" == "true" ]]; then
        generate_coverage_reports
    fi

    # Imprime resumo
    print_coverage_summary "$current_coverage" "$REQUIRED_COVERAGE"

    # Verifica threshold
    if check_threshold "$current_coverage" "$REQUIRED_COVERAGE"; then
        log_success "Coverage check PASSED!"
        exit 0
    else
        log_error "Coverage check FAILED!"
        exit 1
    fi
}

# Executa main
main "$@"
