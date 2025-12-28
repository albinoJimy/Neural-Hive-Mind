#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

# Detecta serviços modificados via git diff
get_changed_services() {
    local base_ref="${1:-HEAD~1}"
    local changed_paths

    # Verifica se estamos em um repositório git
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_warn "Não é um repositório git, retornando todos os serviços"
        return 1
    fi

    # Obtém arquivos modificados
    changed_paths=$(git diff --name-only "$base_ref" 2>/dev/null || echo "")

    if [[ -z "$changed_paths" ]]; then
        log_info "Nenhuma mudança detectada desde $base_ref"
        return 0
    fi

    # Extrai serviços únicos de paths como "services/gateway-intencoes/..."
    echo "$changed_paths" \
        | grep "^services/" \
        | cut -d/ -f2 \
        | sort -u
}

# Detecta se imagens base foram modificadas
check_base_images_changed() {
    local base_ref="${1:-HEAD~1}"

    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        return 0  # Assume mudança se não for git repo
    fi

    local changed_paths
    changed_paths=$(git diff --name-only "$base_ref" 2>/dev/null || echo "")

    if echo "$changed_paths" | grep -q "^base-images/"; then
        return 0  # Mudanças detectadas
    fi

    return 1  # Sem mudanças
}

# Detecta mudanças em bibliotecas compartilhadas
get_changed_libraries() {
    local base_ref="${1:-HEAD~1}"

    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        return 1
    fi

    local changed_paths
    changed_paths=$(git diff --name-only "$base_ref" 2>/dev/null || echo "")

    echo "$changed_paths" \
        | grep "^libraries/" \
        | cut -d/ -f1-3 \
        | sort -u
}

# Mapeia bibliotecas para serviços afetados
get_services_affected_by_libraries() {
    local changed_libs=("$@")
    local affected_services=()

    for lib in "${changed_libs[@]}"; do
        case "$lib" in
            "libraries/python/neural_hive_observability")
                # Afeta: gateway, consensus, memory-layer, todos os specialists
                affected_services+=(
                    "gateway-intencoes"
                    "consensus-engine"
                    "memory-layer-api"
                    "specialist-business"
                    "specialist-technical"
                    "specialist-behavior"
                    "specialist-evolution"
                    "specialist-architecture"
                )
                ;;
            "libraries/python/neural_hive_specialists")
                # Afeta: todos os specialists
                affected_services+=(
                    "specialist-business"
                    "specialist-technical"
                    "specialist-behavior"
                    "specialist-evolution"
                    "specialist-architecture"
                )
                ;;
        esac
    done

    # Remove duplicatas
    printf '%s\n' "${affected_services[@]}" | sort -u
}

# Função principal: retorna lista de serviços a buildar
get_services_to_build() {
    local base_ref="${1:-HEAD~1}"
    shift
    local all_services=("$@")

    log_info "Detectando mudanças desde $base_ref"

    # Se imagens base mudaram, builda tudo
    if check_base_images_changed "$base_ref"; then
        log_warning "Imagens base modificadas - build completo necessário"
        printf '%s\n' "${all_services[@]}"
        return 0
    fi

    # Detecta serviços modificados diretamente
    local changed_services
    changed_services=$(get_changed_services "$base_ref")

    # Detecta bibliotecas modificadas
    local changed_libs
    changed_libs=$(get_changed_libraries "$base_ref")

    # Serviços afetados por bibliotecas
    local affected_by_libs
    if [[ -n "$changed_libs" ]]; then
        affected_by_libs=$(get_services_affected_by_libraries $changed_libs)
    fi

    # Combina e remove duplicatas
    {
        echo "$changed_services"
        echo "$affected_by_libs"
    } | grep -v '^$' | sort -u
}

export -f get_changed_services check_base_images_changed get_changed_libraries
export -f get_services_affected_by_libraries get_services_to_build
