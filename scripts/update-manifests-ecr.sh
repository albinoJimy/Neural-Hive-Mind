#!/bin/bash
set -euo pipefail

# =============================================================================
# Script: update-manifests-ecr.sh
# Descrição: Atualiza manifestos Kubernetes (Helm charts e standalone) com URLs ECR
# Versão: 1.0.0
# =============================================================================

# Cores para logging
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m' # No Color

# Configuração padrão
VERSION="${VERSION:-1.0.7}"
DRY_RUN=false
CREATE_BACKUP=true
ENV="${ENV:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=""
ECR_REGISTRY=""
BACKUP_DIR=""

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HELM_CHARTS_DIR="${PROJECT_ROOT}/helm-charts"
K8S_DIR="${PROJECT_ROOT}/k8s"

# Array de serviços Phase 1
SERVICES=(
    "gateway-intencoes"
    "semantic-translation-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
    "consensus-engine"
    "memory-layer-api"
)

# Contadores
HELM_CHARTS_UPDATED=0
HELM_CHARTS_FAILED=0
MANIFESTS_UPDATED=0
MANIFESTS_FAILED=0

# Tool preference
USE_YQ=false

# =============================================================================
# Funções de Logging
# =============================================================================

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

log_change() {
    local old_value="$1"
    local new_value="$2"
    echo -e "  ${RED}OLD:${NC} ${old_value}"
    echo -e "  ${GREEN}NEW:${NC} ${new_value}"
}

# =============================================================================
# Funções Auxiliares
# =============================================================================

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar yq
    if command -v yq &> /dev/null; then
        local yq_version=$(yq --version 2>&1 | head -n1)
        if [[ $yq_version == *"version 4"* ]] || [[ $yq_version == *"v4"* ]]; then
            log_success "yq v4.x encontrado: ${yq_version}"
            USE_YQ=true
        else
            log_warning "yq encontrado mas não é v4.x: ${yq_version}"
            log_warning "Usando sed como fallback"
        fi
    else
        log_warning "yq não encontrado. Usando sed como fallback"
    fi

    # Verificar sed (sempre presente em sistemas Unix)
    if ! command -v sed &> /dev/null; then
        log_error "sed não encontrado. Impossível continuar."
        exit 1
    fi

    # Validar diretórios
    if [[ ! -d "${HELM_CHARTS_DIR}" ]]; then
        log_error "Diretório de Helm charts não encontrado: ${HELM_CHARTS_DIR}"
        exit 1
    fi

    if [[ ! -d "${K8S_DIR}" ]]; then
        log_error "Diretório de manifestos K8s não encontrado: ${K8S_DIR}"
        exit 1
    fi
}

check_aws_prerequisites() {
    log_info "Verificando pré-requisitos AWS..."

    # Verificar AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI não encontrado. Instale com: curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip' && unzip awscliv2.zip && sudo ./aws/install"
        exit 1
    fi

    # Verificar credenciais AWS
    log_info "Validando credenciais AWS..."
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "Credenciais AWS inválidas. Execute 'aws configure' ou exporte AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY"
        exit 1
    fi

    # Carregar variáveis de ambiente se arquivo existir
    if [[ -f ~/.neural-hive-env ]]; then
        log_info "Carregando variáveis de ~/.neural-hive-env"
        source ~/.neural-hive-env
        ENV="${ENV:-dev}"
        AWS_REGION="${AWS_REGION:-us-east-1}"
    fi

    # Derivar AWS Account ID
    log_info "Obtendo AWS Account ID..."
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
        log_error "Não foi possível obter AWS Account ID"
        exit 1
    fi

    # Construir ECR Registry URL
    ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

    # Exibir configuração
    log_success "Pré-requisitos AWS validados!"
    echo ""
    echo -e "${BLUE}Configuração detectada:${NC}"
    echo -e "  Ambiente:       ${GREEN}${ENV}${NC}"
    echo -e "  Região AWS:     ${GREEN}${AWS_REGION}${NC}"
    echo -e "  Account ID:     ${GREEN}${AWS_ACCOUNT_ID}${NC}"
    echo -e "  ECR Registry:   ${GREEN}${ECR_REGISTRY}${NC}"
    echo -e "  Versão:         ${GREEN}${VERSION}${NC}"
    echo -e "  Ferramenta:     ${GREEN}$(${USE_YQ} && echo 'yq' || echo 'sed')${NC}"
    echo ""
}

create_backup() {
    local timestamp=$(date +%Y%m%d-%H%M%S)
    BACKUP_DIR="${PROJECT_ROOT}/backups/manifests-${timestamp}"

    log_info "Criando backup em: ${BACKUP_DIR}"
    mkdir -p "${BACKUP_DIR}/helm-charts"
    mkdir -p "${BACKUP_DIR}/k8s"

    # Backup de values.yaml dos Helm charts
    for service in "${SERVICES[@]}"; do
        local values_file="${HELM_CHARTS_DIR}/${service}/values.yaml"
        if [[ -f "${values_file}" ]]; then
            cp "${values_file}" "${BACKUP_DIR}/helm-charts/${service}-values.yaml"
        fi
    done

    # Backup de manifests standalone
    if [[ -d "${K8S_DIR}" ]]; then
        cp "${K8S_DIR}"/*.yaml "${BACKUP_DIR}/k8s/" 2>/dev/null || true
    fi

    log_success "Backup criado: ${BACKUP_DIR}"
    echo ""
}

update_helm_chart_values() {
    local service_name="$1"
    local ecr_registry="$2"
    local env="$3"
    local version="$4"

    local values_file="${HELM_CHARTS_DIR}/${service_name}/values.yaml"

    if [[ ! -f "${values_file}" ]]; then
        log_warning "Arquivo values.yaml não encontrado para ${service_name}"
        return 1
    fi

    local new_repo="${ecr_registry}/neural-hive-${env}/${service_name}"

    log_info "Atualizando Helm chart: ${service_name}"

    if [[ "${DRY_RUN}" == true ]]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} Mudanças que seriam aplicadas em ${values_file}:"
        # Extrair repository e tag apenas do bloco image:
        local current_repo=$(awk '/^image:/,/^[^ ]/ { if (/^[[:space:]]+repository:/) print }' "${values_file}" | sed 's/.*repository:\s*//' | tr -d '"' || echo "N/A")
        local current_tag=$(awk '/^image:/,/^[^ ]/ { if (/^[[:space:]]+tag:/) print }' "${values_file}" | sed 's/.*tag:\s*//' | tr -d '"' || echo "N/A")
        log_change "repository: ${current_repo}" "repository: ${new_repo}"
        log_change "tag: ${current_tag}" "tag: ${version}"
        echo ""
        return 0
    fi

    if [[ "${USE_YQ}" == true ]]; then
        # Usar yq para atualização segura
        yq eval ".image.repository = \"${new_repo}\"" -i "${values_file}"
        yq eval ".image.tag = \"${version}\"" -i "${values_file}"
    else
        # Fallback para sed com contexto para afetar apenas o bloco image:
        # Usar awk para processar apenas o bloco image:
        awk -v repo="${new_repo}" -v tag="${version}" '
        BEGIN { in_image_block = 0 }
        /^image:/ { in_image_block = 1; print; next }
        in_image_block && /^[^ ]/ { in_image_block = 0 }
        in_image_block && /^[[:space:]]+repository:/ {
            print "  repository: " repo
            next
        }
        in_image_block && /^[[:space:]]+tag:/ {
            print "  tag: \"" tag "\""
            next
        }
        { print }
        ' "${values_file}" > "${values_file}.tmp" && mv "${values_file}.tmp" "${values_file}"
    fi

    log_success "Helm chart atualizado: ${service_name}"
    echo "  Repository: ${new_repo}"
    echo "  Tag: ${version}"
    echo ""

    return 0
}

update_standalone_manifest() {
    local manifest_file="$1"
    local service_name="$2"
    local ecr_registry="$3"
    local env="$4"
    local version="$5"

    if [[ ! -f "${manifest_file}" ]]; then
        log_warning "Manifest não encontrado: ${manifest_file}"
        return 1
    fi

    local new_image="${ecr_registry}/neural-hive-${env}/${service_name}:${version}"

    log_info "Atualizando manifest standalone: $(basename ${manifest_file})"

    if [[ "${DRY_RUN}" == true ]]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} Mudanças que seriam aplicadas em ${manifest_file}:"

        if [[ "${USE_YQ}" == true ]]; then
            # Usar yq para listar todas as imagens no manifest
            local current_images=$(yq eval '.spec.template.spec.containers[].image' "${manifest_file}" 2>/dev/null || echo "N/A")
            if [[ "${current_images}" == "N/A" ]] || [[ -z "${current_images}" ]]; then
                log_change "image: N/A" "image: ${new_image}"
            else
                # Mostrar todas as imagens encontradas
                while IFS= read -r img; do
                    if [[ -n "${img}" ]]; then
                        log_change "image: ${img}" "image: ${new_image}"
                    fi
                done <<< "${current_images}"
            fi
        else
            # Fallback: usar grep simples para encontrar linhas com image:
            local current_images=$(grep -E '^[[:space:]]*image:' "${manifest_file}" | sed 's/.*image:[[:space:]]*//' | tr -d '"' || echo "N/A")
            if [[ "${current_images}" == "N/A" ]] || [[ -z "${current_images}" ]]; then
                log_change "image: N/A" "image: ${new_image}"
            else
                # Mostrar primeira imagem encontrada (normalmente há apenas uma por deployment)
                local first_image=$(echo "${current_images}" | head -n1)
                log_change "image: ${first_image}" "image: ${new_image}"

                # Se houver múltiplas imagens, avisar
                local image_count=$(echo "${current_images}" | wc -l)
                if [[ ${image_count} -gt 1 ]]; then
                    log_warning "Múltiplas imagens encontradas (${image_count}). Apenas a primeira será atualizada."
                fi
            fi
        fi

        echo ""
        return 0
    fi

    if [[ "${USE_YQ}" == true ]]; then
        # Usar yq para atualização segura
        yq eval "(.spec.template.spec.containers[].image) |= \"${new_image}\"" -i "${manifest_file}"
    else
        # Fallback para sed
        sed -i.bak "s|image:.*${service_name}.*|image: ${new_image}|" "${manifest_file}"
        rm -f "${manifest_file}.bak"
    fi

    log_success "Manifest atualizado: $(basename ${manifest_file})"
    echo "  Image: ${new_image}"
    echo ""

    return 0
}

print_help() {
    cat << EOF
${GREEN}update-manifests-ecr.sh${NC} - Atualiza manifestos Kubernetes com URLs ECR

${BLUE}USO:${NC}
    ./scripts/update-manifests-ecr.sh [OPTIONS]

${BLUE}OPÇÕES:${NC}
    --version <ver>       Versão das imagens (padrão: ${VERSION})
    --env <env>           Ambiente (dev, staging, prod) (padrão: ${ENV})
    --region <region>     Região AWS (padrão: ${AWS_REGION})
    --services <list>     Lista de serviços separados por vírgula
    --dry-run             Preview das mudanças sem aplicar
    --no-backup           Não criar backup antes de modificar
    --help                Exibir esta ajuda

${BLUE}EXEMPLOS:${NC}
    # Atualização padrão
    ./scripts/update-manifests-ecr.sh

    # Preview das mudanças (dry-run)
    ./scripts/update-manifests-ecr.sh --dry-run

    # Atualizar com versão específica
    ./scripts/update-manifests-ecr.sh --version 1.0.8

    # Serviços específicos
    ./scripts/update-manifests-ecr.sh --services "gateway-intencoes,consensus-engine"

    # Ambiente staging
    ./scripts/update-manifests-ecr.sh --env staging --region us-west-2

    # Sem backup (não recomendado)
    ./scripts/update-manifests-ecr.sh --no-backup

${BLUE}PRÉ-REQUISITOS:${NC}
    - yq v4.x (recomendado) ou sed/awk como fallback (sempre necessário)
    - AWS CLI configurado (apenas se não usar --dry-run)
    - Credenciais AWS válidas (apenas se não usar --dry-run)
    - Nota: --dry-run pode usar valores placeholder para preview sem AWS

${BLUE}O QUE O SCRIPT FAZ:${NC}
    1. Valida pré-requisitos (yq/sed sempre; AWS CLI/credenciais apenas se não --dry-run)
    2. Cria backup timestamped dos manifestos (opcional, exceto em dry-run)
    3. Atualiza image.repository e image.tag em Helm charts (apenas bloco image:)
    4. Atualiza imagens hardcoded em manifests standalone (*-deployment.yaml)
    5. Exibe resumo de mudanças aplicadas

${BLUE}ARQUIVOS ATUALIZADOS:${NC}
    - helm-charts/*/values.yaml (9 serviços Phase 1)
    - k8s/*-deployment.yaml (manifests standalone que correspondem aos serviços Phase 1)

${BLUE}BACKUP:${NC}
    Backups são salvos em: backups/manifests-YYYYMMDD-HHMMSS/
    Para restaurar: cp -r backups/manifests-YYYYMMDD-HHMMSS/* .

${BLUE}VERIFICAR MUDANÇAS:${NC}
    git diff helm-charts/*/values.yaml
    helm template gateway-intencoes helm-charts/gateway-intencoes/ | grep image:

EOF
}

# =============================================================================
# Parsing de Argumentos
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --env)
            ENV="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --services)
            IFS=',' read -ra SERVICES <<< "$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-backup)
            CREATE_BACKUP=false
            shift
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            echo ""
            print_help
            exit 1
            ;;
    esac
done

# =============================================================================
# Função Principal
# =============================================================================

main() {
    local start_time=$(date +%s)

    # Banner
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}  ${BLUE}Update Kubernetes Manifests for ECR${NC}                       ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Pré-requisitos básicos (sempre necessários)
    check_prerequisites

    # Pré-requisitos AWS (apenas se não for dry-run)
    if [[ "${DRY_RUN}" == false ]]; then
        check_aws_prerequisites
    else
        # Em modo dry-run, construir ECR_REGISTRY a partir de variáveis de ambiente ou valores padrão
        log_warning "Modo DRY-RUN ativado - pré-requisitos AWS não são necessários"

        # Carregar variáveis de ambiente se arquivo existir
        if [[ -f ~/.neural-hive-env ]]; then
            log_info "Carregando variáveis de ~/.neural-hive-env"
            source ~/.neural-hive-env
            ENV="${ENV:-dev}"
            AWS_REGION="${AWS_REGION:-us-east-1}"
        fi

        # Usar AWS_ACCOUNT_ID do ambiente ou valor placeholder
        if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
            AWS_ACCOUNT_ID="123456789012"
            log_info "AWS_ACCOUNT_ID não definido, usando placeholder: ${AWS_ACCOUNT_ID}"
        fi

        # Construir ECR Registry URL
        ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

        echo ""
        echo -e "${BLUE}Configuração para dry-run:${NC}"
        echo -e "  Ambiente:       ${GREEN}${ENV}${NC}"
        echo -e "  Região AWS:     ${GREEN}${AWS_REGION}${NC}"
        echo -e "  Account ID:     ${GREEN}${AWS_ACCOUNT_ID}${NC} ${YELLOW}(pode ser placeholder)${NC}"
        echo -e "  ECR Registry:   ${GREEN}${ECR_REGISTRY}${NC}"
        echo -e "  Versão:         ${GREEN}${VERSION}${NC}"
        echo -e "  Ferramenta:     ${GREEN}$(${USE_YQ} && echo 'yq' || echo 'sed')${NC}"
        echo ""
    fi

    # Backup
    if [[ "${CREATE_BACKUP}" == true ]] && [[ "${DRY_RUN}" == false ]]; then
        create_backup
    fi

    if [[ "${DRY_RUN}" == true ]]; then
        log_warning "Preview de mudanças - nenhuma alteração será aplicada"
        echo ""
    fi

    # Atualizar Helm Charts
    log_info "Atualizando Helm charts..."
    echo ""

    for service in "${SERVICES[@]}"; do
        set +e
        update_helm_chart_values "${service}" "${ECR_REGISTRY}" "${ENV}" "${VERSION}"
        if [[ $? -eq 0 ]]; then
            ((HELM_CHARTS_UPDATED++))
        else
            ((HELM_CHARTS_FAILED++))
        fi
        set -e
    done

    # Atualizar Manifests Standalone
    log_info "Atualizando manifests standalone..."
    echo ""

    # Processar todos os manifests em k8s/*.yaml
    for manifest_file in "${K8S_DIR}"/*-deployment.yaml; do
        if [[ ! -f "${manifest_file}" ]]; then
            continue
        fi

        # Derivar service_name do nome do arquivo (ex: gateway-intencoes-deployment.yaml -> gateway-intencoes)
        local filename=$(basename "${manifest_file}")
        local service_name="${filename%-deployment.yaml}"

        # Verificar se o serviço está na lista de serviços conhecidos
        local is_known_service=false
        for known_service in "${SERVICES[@]}"; do
            if [[ "${service_name}" == "${known_service}" ]]; then
                is_known_service=true
                break
            fi
        done

        if [[ "${is_known_service}" == false ]]; then
            log_warning "Serviço ${service_name} não está na lista de serviços Phase 1. Pulando..."
            continue
        fi

        set +e
        update_standalone_manifest "${manifest_file}" "${service_name}" "${ECR_REGISTRY}" "${ENV}" "${VERSION}"
        if [[ $? -eq 0 ]]; then
            ((MANIFESTS_UPDATED++))
        else
            ((MANIFESTS_FAILED++))
        fi
        set -e
    done

    # Calcular duração
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Exibir resumo
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}  ${BLUE}Resumo${NC}                                                     ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if [[ "${DRY_RUN}" == true ]]; then
        echo -e "${YELLOW}⚠️  DRY-RUN: Nenhuma mudança foi aplicada${NC}"
        echo ""
    fi

    echo -e "${BLUE}Helm Charts:${NC}"
    echo -e "  ✅ Atualizados: ${GREEN}${HELM_CHARTS_UPDATED}${NC}/${#SERVICES[@]}"
    if [[ ${HELM_CHARTS_FAILED} -gt 0 ]]; then
        echo -e "  ❌ Falhas:      ${RED}${HELM_CHARTS_FAILED}${NC}"
    fi
    echo ""

    echo -e "${BLUE}Manifests Standalone:${NC}"
    echo -e "  ✅ Atualizados: ${GREEN}${MANIFESTS_UPDATED}${NC}"
    if [[ ${MANIFESTS_FAILED} -gt 0 ]]; then
        echo -e "  ❌ Falhas:      ${RED}${MANIFESTS_FAILED}${NC}"
    fi
    echo ""

    echo -e "${BLUE}Estatísticas:${NC}"
    echo -e "  ⏱️  Tempo total: ${duration}s"
    if [[ "${CREATE_BACKUP}" == true ]] && [[ "${DRY_RUN}" == false ]]; then
        echo -e "  📁 Backup:      ${BACKUP_DIR}"
    fi
    echo ""

    if [[ "${DRY_RUN}" == false ]]; then
        echo -e "${BLUE}Próximos passos:${NC}"
        echo -e "  1. Verificar mudanças:"
        echo -e "     ${GREEN}git diff helm-charts/*/values.yaml k8s/*.yaml${NC}"
        echo ""
        echo -e "  2. Verificar templates Helm:"
        echo -e "     ${GREEN}helm template gateway-intencoes helm-charts/gateway-intencoes/ | grep image:${NC}"
        echo ""
        echo -e "  3. Deploy no cluster:"
        echo -e "     ${GREEN}helm upgrade --install gateway-intencoes helm-charts/gateway-intencoes/ -n gateway${NC}"
        echo ""

        if [[ "${CREATE_BACKUP}" == true ]]; then
            echo -e "  4. Para restaurar backup:"
            echo -e "     ${GREEN}cp -r ${BACKUP_DIR}/* .${NC}"
            echo ""
        fi
    else
        echo -e "${BLUE}Para aplicar as mudanças:${NC}"
        echo -e "  ${GREEN}./scripts/update-manifests-ecr.sh --version ${VERSION} --env ${ENV}${NC}"
        echo ""
    fi

    # Exit code
    if [[ ${HELM_CHARTS_FAILED} -gt 0 ]] || [[ ${MANIFESTS_FAILED} -gt 0 ]]; then
        log_warning "Algumas atualizações falharam. Verifique os logs acima."
        exit 1
    fi

    log_success "Atualização concluída com sucesso!"
}

# Executar função principal
main
