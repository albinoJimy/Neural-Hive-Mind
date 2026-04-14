#!/usr/bin/env bash
# HA-001: Health Endpoints Validation Script
# Valida que todos os serviços retornam os 3 endpoints de saúde corretos

set -euo pipefail

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Serviços e suas portas
declare -A SERVICES=(
    ["consensus-engine"]="8002"
    ["semantic-translation-engine"]="8001"
    ["worker-agents"]="8005"
    ["scout-agents"]="8100"
    ["queen-agent"]="8006"
    ["self-healing-engine"]="8106"
    ["analyst-agents"]="8107"
    ["execution-ticket-service"]="8108"
    ["specialist-architecture"]="8101"
    ["specialist-business"]="8102"
    ["specialist-technical"]="8103"
    ["specialist-behavior"]="8104"
    ["specialist-evolution"]="8105"
    ["approval-service"]="8080"
    ["gateway-intencoes"]="8000"
)

# Timeout em segundos
TIMEOUT=5

# URL base padrão
URL_BASE="${1:-http://localhost}"

# Função para validar endpoint
validate_endpoint() {
    local service="$1"
    local port="$2"
    local endpoint="$3"
    local url="$URL_BASE:$port$endpoint"

    echo -e "\n${NC}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${NC}Validating: ${YELLOW}$service${NC} - $endpoint ($url)"

    local response=$(curl -sI --max-time "$TIMEOUT" "$url" 2>/dev/null || echo "")
    local status_code=$(echo "$response" | grep "^HTTP" | cut -d' ' -f2)

    if [ -n "$status_code" ]; then
        if [ "$status_code" = "200" ]; then
            # Verificar campos obrigatórios no body
            local body=$(curl -s --max-time "$TIMEOUT" "$url" 2>/dev/null || echo "{}")

            case "$endpoint" in
                /health)
                    if echo "$body" | grep -q '"status"' && echo "$body" | grep -q '"service"'; then
                        echo -e "  ${GREEN}✓${NC} /health: $status_code - Valid fields"
                    else
                        echo -e "  ${YELLOW}⚠${NC} /health: Missing required fields"
                    fi
                    ;;
                /health/startup)
                    if echo "$body" | grep -q '"status"' && echo "$body" | grep -q '"started_at"'; then
                        echo -e "  ${GREEN}✓${NC} /health/startup: $status_code - Valid fields"
                    else
                        echo -e "  ${YELLOW}⚠${NC} /health/startup: Missing required fields"
                    fi
                    ;;
                /ready)
                    if echo "$body" | grep -q '"ready"' || echo "$body" | grep -q '"checks"'; then
                        echo -e "  ${GREEN}✓${NC} /ready: $status_code - Valid fields"
                    else
                        echo -e "  ${YELLOW}⚠${NC} /ready: Missing required fields"
                    fi
                    ;;
            esac
            return 0
        else
            echo -e "  ${RED}✗${NC} $endpoint: HTTP $status_code"
            return 1
        fi
    else
        echo -e "  ${RED}✗${NC} $endpoint: NO RESPONSE"
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
                services_to_check+=("$1")
                shift
                ;;
        esac
    done

    # Header
    echo -e "${NC}╔══════════════════════════════════════════════════════════════════╗"
    echo -e "${NC}║     HA-001: Health Endpoints Validation                             ║"
    echo -e "${NC}╚══════════════════════════════════════════════════════════════════╝"
    echo -e "URL Base: ${YELLOW}$URL_BASE${NC}"

    # Se nenhum serviço especificado, validar todos
    if [ ${#services_to_check[@]} -eq 0 ]; then
        echo -e "\nValidating all services..."
        for service in "${!SERVICES[@]}"; do
            port="${SERVICES[$service]}"
            validate_endpoint "$service" "$port" "/health" || all_passed=false
            validate_endpoint "$service" "$port" "/health/startup" || all_passed=false
            validate_endpoint "$service" "$port" "/ready" || all_passed=false
        done
    else
        echo -e "\nValidating specified services..."
        for service in "${services_to_check[@]}"; do
            if [ -n "${SERVICES[$service]+x}" ]; then
                port="${SERVICES[$service]}"
                validate_endpoint "$service" "$port" "/health" || all_passed=false
                validate_endpoint "$service" "$port" "/health/startup" || all_passed=false
                validate_endpoint "$service" "$port" "/ready" || all_passed=false
            else
                echo -e "${RED}Unknown service: $service${NC}"
            fi
        done
    fi

    # Resumo final
    echo -e "\n${NC}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ "$all_passed" = true ]; then
        echo -e "${GREEN}✓ ALL CHECKS PASSED${NC}"
        return 0
    else
        echo -e "${RED}✗ SOME CHECKS FAILED${NC}"
        return 1
    fi
}

# Executar validação
main "$@"
