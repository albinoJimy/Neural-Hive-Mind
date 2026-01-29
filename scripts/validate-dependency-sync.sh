#!/bin/bash
# Valida sincronização entre pyproject.toml e requirements.txt

set -e

ERRORS=0

echo "🔍 Validando sincronização de dependências..."

# Função para extrair versão de requirements.txt
get_req_version() {
    local service=$1
    local package=$2
    grep -E "^${package}[=>]" "services/${service}/requirements.txt" 2>/dev/null || echo ""
}

# Função para extrair versão de pyproject.toml
get_toml_version() {
    local service=$1
    local package=$2
    grep -E "^${package} = " "services/${service}/pyproject.toml" 2>/dev/null || echo ""
}

# Serviços a validar
SERVICES=(
    "specialist-behavior"
    "specialist-business"
    "specialist-architecture"
    "specialist-technical"
    "specialist-evolution"
    "consensus-engine"
)

# Pacotes críticos a verificar
CRITICAL_PACKAGES=(
    "fastapi"
    "pydantic"
    "grpcio"
    "structlog"
)

for service in "${SERVICES[@]}"; do
    if [[ ! -f "services/${service}/pyproject.toml" ]]; then
        continue
    fi
    
    echo "  Verificando ${service}..."
    
    for package in "${CRITICAL_PACKAGES[@]}"; do
        req_ver=$(get_req_version "$service" "$package")
        toml_ver=$(get_toml_version "$service" "$package")
        
        if [[ -n "$req_ver" && -n "$toml_ver" ]]; then
            # Extrair apenas a versão (remover operadores)
            req_clean=$(echo "$req_ver" | sed 's/.*==\|>=\|<=\|>\|<//')
            toml_clean=$(echo "$toml_ver" | sed 's/.*"\(.*\)".*/\1/' | sed 's/>=\|==\|<=\|>\|<//')
            
            if [[ "$req_clean" != "$toml_clean"* ]]; then
                echo "    ⚠️  ${package}: requirements.txt=${req_clean} vs pyproject.toml=${toml_clean}"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    done
done

if [[ $ERRORS -eq 0 ]]; then
    echo "✅ Todas as dependências estão sincronizadas!"
    exit 0
else
    echo "❌ Encontradas ${ERRORS} inconsistências. Consulte docs/DEPENDENCY_MANAGEMENT.md"
    exit 1
fi
