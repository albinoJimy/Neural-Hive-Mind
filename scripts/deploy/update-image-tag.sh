#!/bin/bash
# =============================================================================
# Script: update-image-tag.sh
# Descrição: Atualiza a tag de imagem nos arquivos Helm values
# Uso: ./update-image-tag.sh --service <nome> --tag <tag> [opções]
# =============================================================================

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações padrão
REGISTRY="ghcr.io/albinojimy/neural-hive-mind"
ENVIRONMENT=""
DRY_RUN=false
BACKUP=true
VERBOSE=false

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HELM_CHARTS_DIR="${PROJECT_ROOT}/helm-charts"
ENVIRONMENTS_DIR="${PROJECT_ROOT}/environments"

# =============================================================================
# Funções de utilidade
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

show_help() {
    cat << EOF
Uso: $(basename "$0") [opções]

Atualiza a tag de imagem Docker nos arquivos Helm values.

Opções obrigatórias:
  --service <nome>      Nome do serviço (ex: gateway-intencoes)
  --tag <tag>           Nova tag da imagem (ex: 1.2.0, latest, abc1234)

Opções opcionais:
  --environment <env>   Ambiente específico (prod, staging, dev)
                        Se não especificado, atualiza apenas values.yaml base
  --registry <url>      URL do registry (padrão: ${REGISTRY})
  --dry-run             Simula as alterações sem aplicá-las
  --no-backup           Não cria backup dos arquivos
  --verbose             Mostra informações detalhadas
  --help                Mostra esta ajuda

Exemplos:
  # Atualizar tag no values.yaml base
  $(basename "$0") --service gateway-intencoes --tag 1.2.0

  # Atualizar tag para ambiente de produção
  $(basename "$0") --service gateway-intencoes --tag 1.2.0 --environment prod

  # Simular atualização (dry-run)
  $(basename "$0") --service gateway-intencoes --tag 1.2.0 --dry-run

  # Atualizar com registry customizado
  $(basename "$0") --service gateway-intencoes --tag 1.2.0 --registry ghcr.io/myorg/myrepo

EOF
}

# =============================================================================
# Validações
# =============================================================================

check_yq() {
    if command -v yq &> /dev/null; then
        YQ_VERSION=$(yq --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        YQ_MAJOR=$(echo "$YQ_VERSION" | cut -d. -f1)
        if [[ "$YQ_MAJOR" -ge 4 ]]; then
            log_debug "yq v${YQ_VERSION} detectado"
            return 0
        else
            log_warn "yq v${YQ_VERSION} detectado, mas v4+ é recomendado"
            return 1
        fi
    else
        log_warn "yq não encontrado, usando sed como fallback"
        return 1
    fi
}

validate_service() {
    local service="$1"
    local service_dir="${HELM_CHARTS_DIR}/${service}"

    if [[ ! -d "$service_dir" ]]; then
        log_error "Serviço '${service}' não encontrado em ${HELM_CHARTS_DIR}"
        log_info "Serviços disponíveis:"
        ls -1 "${HELM_CHARTS_DIR}" | grep -v '^_' | sed 's/^/  - /'
        return 1
    fi

    if [[ ! -f "${service_dir}/values.yaml" ]]; then
        log_error "values.yaml não encontrado para o serviço '${service}'"
        return 1
    fi

    return 0
}

validate_tag() {
    local tag="$1"

    if [[ -z "$tag" ]]; then
        log_error "Tag não pode ser vazia"
        return 1
    fi

    # Validar formato (semver, sha, ou latest)
    if [[ "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?$ ]]; then
        log_debug "Tag semver válida: ${tag}"
    elif [[ "$tag" =~ ^[a-f0-9]{7,40}$ ]]; then
        log_debug "Tag SHA válida: ${tag}"
    elif [[ "$tag" == "latest" || "$tag" =~ ^(main|develop|staging)$ ]]; then
        log_warn "Tag mutável detectada: ${tag} - considere usar tag fixa em produção"
    else
        log_warn "Formato de tag não reconhecido: ${tag}"
    fi

    return 0
}

validate_environment() {
    local env="$1"

    case "$env" in
        prod|production)
            ENVIRONMENT="prod"
            ;;
        staging)
            ENVIRONMENT="staging"
            ;;
        dev|development)
            ENVIRONMENT="dev"
            ;;
        "")
            ENVIRONMENT=""
            ;;
        *)
            log_error "Ambiente inválido: ${env}"
            log_info "Ambientes válidos: prod, staging, dev"
            return 1
            ;;
    esac

    return 0
}

# =============================================================================
# Funções de atualização
# =============================================================================

create_backup() {
    local file="$1"
    local backup_file="${file}.backup.$(date +%Y%m%d_%H%M%S)"

    if [[ "$BACKUP" == "true" && "$DRY_RUN" == "false" ]]; then
        cp "$file" "$backup_file"
        log_debug "Backup criado: ${backup_file}"
    fi
}

update_with_yq() {
    local file="$1"
    local tag="$2"
    local registry="$3"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Atualizaria ${file}:"
        echo "  image.tag: ${tag}"
        if [[ -n "$registry" ]]; then
            echo "  image.repository: ${registry}"
        fi
        return 0
    fi

    create_backup "$file"

    # Atualizar tag
    yq -i ".image.tag = \"${tag}\"" "$file"

    # Atualizar repository se especificado
    if [[ -n "$registry" ]]; then
        local service_name
        service_name=$(basename "$(dirname "$file")")
        yq -i ".image.repository = \"${registry}/${service_name}\"" "$file"
    fi

    log_success "Atualizado: ${file}"
}

update_with_sed() {
    local file="$1"
    local tag="$2"
    local registry="$3"

    # Ler tag atual
    local old_tag
    old_tag=$(grep -E '^\s*tag:' "$file" | head -1 | awk '{print $2}' | tr -d '"' || echo "N/A")

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Atualizaria ${file}:"
        echo "  Tag antiga: ${old_tag}"
        echo "  Tag nova: ${tag}"
        return 0
    fi

    create_backup "$file"

    # Atualizar tag usando sed
    sed -i "s|^\(\s*tag:\s*\).*|\1\"${tag}\"|" "$file"

    # Atualizar repository se especificado
    if [[ -n "$registry" ]]; then
        local service_name
        service_name=$(basename "$(dirname "$file")")
        sed -i "s|^\(\s*repository:\s*\).*|\1${registry}/${service_name}|" "$file"
    fi

    log_success "Atualizado: ${file} (${old_tag} -> ${tag})"
}

update_file() {
    local file="$1"
    local tag="$2"
    local registry="$3"

    if [[ ! -f "$file" ]]; then
        log_warn "Arquivo não encontrado: ${file}"
        return 1
    fi

    if check_yq; then
        update_with_yq "$file" "$tag" "$registry"
    else
        update_with_sed "$file" "$tag" "$registry"
    fi
}

# =============================================================================
# Função principal
# =============================================================================

main() {
    local SERVICE=""
    local TAG=""
    local REGISTRY_OVERRIDE=""

    # Parse argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --service)
                SERVICE="$2"
                shift 2
                ;;
            --tag)
                TAG="$2"
                shift 2
                ;;
            --environment)
                validate_environment "$2" || exit 1
                shift 2
                ;;
            --registry)
                REGISTRY_OVERRIDE="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --no-backup)
                BACKUP=false
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help|-h)
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

    # Validar parâmetros obrigatórios
    if [[ -z "$SERVICE" ]]; then
        log_error "Parâmetro --service é obrigatório"
        show_help
        exit 1
    fi

    if [[ -z "$TAG" ]]; then
        log_error "Parâmetro --tag é obrigatório"
        show_help
        exit 1
    fi

    # Validações
    validate_service "$SERVICE" || exit 1
    validate_tag "$TAG" || exit 1

    # Usar registry override ou padrão
    local FINAL_REGISTRY="${REGISTRY_OVERRIDE:-$REGISTRY}"

    # Banner
    echo ""
    echo "=========================================="
    echo "  Atualização de Tag de Imagem"
    echo "=========================================="
    echo "  Serviço:    ${SERVICE}"
    echo "  Tag:        ${TAG}"
    echo "  Registry:   ${FINAL_REGISTRY}"
    echo "  Ambiente:   ${ENVIRONMENT:-'base (todos)'}"
    echo "  Dry Run:    ${DRY_RUN}"
    echo "=========================================="
    echo ""

    local FILES_UPDATED=0

    # Atualizar values.yaml base
    local BASE_VALUES="${HELM_CHARTS_DIR}/${SERVICE}/values.yaml"
    if [[ -z "$ENVIRONMENT" || "$ENVIRONMENT" == "base" ]]; then
        log_info "Atualizando values.yaml base..."
        update_file "$BASE_VALUES" "$TAG" "$FINAL_REGISTRY"
        FILES_UPDATED=$((FILES_UPDATED + 1))
    fi

    # Atualizar values-k8s.yaml se existir
    local K8S_VALUES="${HELM_CHARTS_DIR}/${SERVICE}/values-k8s.yaml"
    if [[ -f "$K8S_VALUES" && ( -z "$ENVIRONMENT" || "$ENVIRONMENT" == "base" ) ]]; then
        log_info "Atualizando values-k8s.yaml..."
        update_file "$K8S_VALUES" "$TAG" "$FINAL_REGISTRY"
        FILES_UPDATED=$((FILES_UPDATED + 1))
    fi

    # Atualizar arquivo específico do ambiente
    if [[ -n "$ENVIRONMENT" ]]; then
        local ENV_DIR=""
        case "$ENVIRONMENT" in
            prod)
                ENV_DIR="${ENVIRONMENTS_DIR}/prod/helm-values"
                ;;
            staging)
                ENV_DIR="${ENVIRONMENTS_DIR}/staging/helm-values"
                ;;
            dev)
                ENV_DIR="${ENVIRONMENTS_DIR}/dev/helm-values"
                ;;
        esac

        if [[ -n "$ENV_DIR" ]]; then
            local ENV_VALUES="${ENV_DIR}/${SERVICE}-values.yaml"
            if [[ -f "$ENV_VALUES" ]]; then
                log_info "Atualizando arquivo de ambiente ${ENVIRONMENT}..."
                update_file "$ENV_VALUES" "$TAG" "$FINAL_REGISTRY"
                FILES_UPDATED=$((FILES_UPDATED + 1))
            else
                log_warn "Arquivo de ambiente não encontrado: ${ENV_VALUES}"
            fi
        fi
    fi

    # Resumo
    echo ""
    echo "=========================================="
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Simulação concluída. ${FILES_UPDATED} arquivo(s) seriam atualizados."
    else
        log_success "Atualização concluída. ${FILES_UPDATED} arquivo(s) atualizado(s)."
    fi
    echo "=========================================="
    echo ""

    # Sugestão de próximos passos
    if [[ "$DRY_RUN" == "false" ]]; then
        log_info "Próximos passos:"
        echo "  1. Verificar alterações: git diff"
        echo "  2. Commit: git add -A && git commit -m 'chore: update ${SERVICE} image tag to ${TAG}'"
        echo "  3. Deploy: helm upgrade ${SERVICE} helm-charts/${SERVICE} -n <namespace>"
    fi
}

# Executar
main "$@"
