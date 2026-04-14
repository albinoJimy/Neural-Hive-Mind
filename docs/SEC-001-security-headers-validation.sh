#!/usr/bin/env bash3
"""
Script de validação de Security Headers (SEC-001).

Valida que todos os serviços FastAPI do Neural Hive-Mind estão
retornando os headers de segurança corretos.

Uso:
    ./validate_security_headers.sh [--url-base URL_BASE]

Exemplo:
    # Para serviços rodando localmente
    ./validate_security_headers.sh --url-base http://localhost

    # Para serviços em cluster
    ./validate_security_headers.sh --url-base https://nhm.example.com
"""

set -euo pipefail

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Headers obrigatórios e seus valores esperados
declare -A REQUIRED_HEADERS=(
    ["X-Content-Type-Options"]="nosniff"
    ["X-Frame-Options"]="DENY"
    ["Strict-Transport-Security"]="max-age=31536000"
    ["X-XSS-Protection"]="1; mode=block"
    ["Referrer-Policy"]="strict-origin-when-cross-origin"
    ["Cross-Origin-Opener-Policy"]="same-origin"
    ["Cross-Origin-Resource-Policy"]="same-site"
    ["X-Permitted-Cross-Domain-Policies"]="none"
)

# Headers que devem conter certos valores (verificação parcial)
declare -A PARTIAL_HEADERS=(
    ["Content-Security-Policy"]="default-src 'self'"
    ["Permissions-Policy"]="geolocation=()"
)

# Serviços e suas portas padrão
declare -A SERVICES=(
    ["orchestrator-dynamic"]="8003"
    ["consensus-engine"]="8002"
    ["gateway-intencoes"]="8000"
    ["approval-service"]="8004"
    ["queen-agent"]="8006"
    ["worker-agents"]="8005"
    ["semantic-translation-engine"]="8001"
    ["specialist-architecture"]="8101"
    ["specialist-business"]="8102"
    ["specialist-technical"]="8103"
    ["specialist-behavior"]="8104"
    ["specialist-evolution"]="8105"
)

# Timeout em segundos
TIMEOUT=5

# URL base padrão
URL_BASE="${1:-http://localhost}"

# Função para extrair header do curl
get_header() {
    local url="$1"
    local header="$2"
    curl -sI --max-time "$TIMEOUT" "$url" 2>/dev/null | grep "^$header:" | cut -d':' -f2- | xargs
}

# Função para validar serviço
validate_service() {
    local service="$1"
    local port="$2"
    local url="$URL_BASE:$port/health"

    echo -e "\n${NC}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${NC}Validating: ${YELLOW}$service${NC} ($url)"

    local passed=0
    local total=0

    # Headers obrigatórios
    for header in "${!REQUIRED_HEADERS[@]}"; do
        expected="${REQUIRED_HEADERS[$header]}"
        actual=$(get_header "$url" "$header")
        total=$((total + 1))

        if [ -n "$actual" ]; then
            if [[ "$actual" == *"$expected"* ]]; then
                echo -e "  ${GREEN}✓${NC} $header: $actual"
                passed=$((passed + 1))
            else
                echo -e "  ${RED}✗${NC} $header: $actual (expected: $expected)"
            fi
        else
            echo -e "  ${RED}✗${NC} $header: MISSING"
        fi
    done

    # Headers parciais
    for header in "${!PARTIAL_HEADERS[@]}"; do
        expected="${PARTIAL_HEADERS[$header]}"
        actual=$(get_header "$url" "$header")
        total=$((total + 1))

        if [ -n "$actual" ]; then
            if [[ "$actual" == *"$expected"* ]]; then
                echo -e "  ${GREEN}✓${NC} $header: Found '$expected'"
                passed=$((passed + 1))
            else
                echo -e "  ${YELLOW}⚠${NC} $header: Missing '$expected'"
            fi
        else
            echo -e "  ${RED}✗${NC} $header: MISSING"
        fi
    done

    # Resumo do serviço
    if [ $passed -eq $total ]; then
        echo -e "  ${GREEN}✓ PASS${NC} ($passed/$total)"
        return 0
    else
        echo -e "  ${RED}✗ FAIL${NC} ($passed/$total)"
        return 1
    fi
}

# Função principal
main() {
    local services_to_check=()
    local all_passed=true

    # Parse argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --url-base)
                URL_BASE="$2"
                shift 2
                ;;
            *)
                # Se não é opção, é um serviço específico
                services_to_check+=("$1")
                shift
                ;;
        esac
    done

    # Header
    echo -e "${NC}╔══════════════════════════════════════════════════════════════════╗"
    echo -e "${NC}║     SEC-001: Security Headers Validation                             ║"
    echo -e "${NC}╚══════════════════════════════════════════════════════════════════╝"
    echo -e "URL Base: ${YELLOW}$URL_BASE${NC}"

    # Se nenhum serviço especificado, validar todos
    if [ ${#services_to_check[@]} -eq 0 ]; then
        echo -e "\nValidating all services..."
        for service in "${!SERVICES[@]}"; do
            validate_service "$service" "${SERVICES[$service]}" || all_passed=false
        done
    else
        echo -e "\nValidating specified services..."
        for service in "${services_to_check[@]}"; do
            if [ -n "${SERVICES[$service]+x}" ]; then
                validate_service "$service" "${SERVICES[$service]}" || all_passed=false
            else
                echo -e "${RED}Unknown service: $service${NC}"
            fi
        done
    fi

    # Resumo final
    echo -e "\n${NC}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ "$all_passed" = true ]; then
        echo -e "${GREEN}✓ ALL SERVICES PASSED${NC}"
        return 0
    else
        echo -e "${RED}✗ SOME SERVICES FAILED${NC}"
        return 1
    fi
}

# Executar validação
main "$@"
