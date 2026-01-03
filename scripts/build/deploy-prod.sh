#!/usr/bin/env bash
# Deploy Production Script for Neural Hive-Mind
# Build local com compressão gzip e push para registry remoto via contexto neural-hive-prod
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${SCRIPT_DIR}/../lib/common.sh"
source "${SCRIPT_DIR}/../lib/docker.sh"

# ===========================
# Configuração
# ===========================
VERSION="${VERSION:-1.0.10}"
NAMESPACE="${NAMESPACE:-neural-hive}"
K8S_CONTEXT="${K8S_CONTEXT:-neural-hive-prod}"
DOCKER_PREFIX="neural-hive-mind"
REGISTRY_URL="${REGISTRY_URL:-37.60.241.150:30500}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-6}"  # gzip level 1-9
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="${PROJECT_ROOT}/logs"
BUILD_CACHE_DIR="${PROJECT_ROOT}/.build-cache"

# Componentes disponíveis
declare -A COMPONENTS=(
    # Base images
    ["python-base"]="base-images/python-base"
    ["python-grpc-base"]="base-images/python-grpc-base"
    ["python-observability-base"]="base-images/python-observability-base"
    ["python-specialist-base"]="base-images/python-specialist-base"
    # Services
    ["gateway-intencoes"]="services/gateway-intencoes"
    ["consensus-engine"]="services/consensus-engine"
    ["specialist-business"]="services/specialist-business"
    ["specialist-technical"]="services/specialist-technical"
    ["specialist-behavior"]="services/specialist-behavior"
    ["specialist-evolution"]="services/specialist-evolution"
    ["specialist-architecture"]="services/specialist-architecture"
    ["orchestrator-dynamic"]="services/orchestrator-dynamic"
    ["worker-agents"]="services/worker-agents"
    ["guard-agents"]="services/guard-agents"
    ["scout-agents"]="services/scout-agents"
    ["mcp-tool-catalog"]="services/mcp-tool-catalog"
    ["memory-layer-api"]="services/memory-layer-api"
    ["service-registry"]="services/service-registry"
    ["self-healing-engine"]="services/self-healing-engine"
    ["semantic-translation-engine"]="services/semantic-translation-engine"
    ["sla-management-system"]="services/sla-management-system"
    ["code-forge"]="services/code-forge"
    ["execution-ticket-service"]="services/execution-ticket-service"
)

# Grupos de componentes
declare -a GROUP_SPECIALISTS=(
    "specialist-business" "specialist-technical" "specialist-behavior"
    "specialist-evolution" "specialist-architecture"
)
declare -a GROUP_CORE=(
    "gateway-intencoes" "consensus-engine" "orchestrator-dynamic"
)
declare -a GROUP_AGENTS=(
    "worker-agents" "guard-agents" "scout-agents"
)
declare -a GROUP_ALL=()

# Flags
SKIP_BUILD=false
SKIP_PUSH=false
SKIP_DEPLOY=false
DRY_RUN=false
USE_CACHE=true
COMPRESS_EXPORT=false
EXPORT_ONLY=false
SELECTED_COMPONENTS=()

# Contadores
BUILD_SUCCESS=0
BUILD_FAILED=0
PUSH_SUCCESS=0
PUSH_FAILED=0
DEPLOY_SUCCESS=0
DEPLOY_FAILED=0

# ===========================
# Funções de Build
# ===========================

build_with_compression() {
    local component="$1"
    local component_path="${COMPONENTS[$component]}"
    local dockerfile="${PROJECT_ROOT}/${component_path}/Dockerfile"
    local image_name="${DOCKER_PREFIX}/${component}"
    local full_tag="${image_name}:${VERSION}"
    local start_time=$(date +%s)

    if [[ ! -f "${dockerfile}" ]]; then
        log_error "Dockerfile não encontrado: ${dockerfile}"
        return 1
    fi

    log_info "Building ${component}:${VERSION}..."

    local log_file="${LOG_DIR}/build-${component}-${TIMESTAMP}.log"
    mkdir -p "${LOG_DIR}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_warning "[DRY-RUN] docker build ${full_tag}"
        return 0
    fi

    # Build com BuildKit (compressão automática de layers)
    local build_result=0
    DOCKER_BUILDKIT=1 docker build \
        -t "${full_tag}" \
        -t "${image_name}:latest" \
        -f "${dockerfile}" \
        --build-arg "BUILDKIT_INLINE_CACHE=1" \
        --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --build-arg "VERSION=${VERSION}" \
        --compress \
        "${PROJECT_ROOT}" > "${log_file}" 2>&1 || build_result=$?

    if [[ ${build_result} -eq 0 ]]; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        local image_size=$(docker image inspect "${full_tag}" --format='{{.Size}}' 2>/dev/null | numfmt --to=iec || echo "N/A")

        log_success "${component}: Build OK (${duration}s, ${image_size})"
        ((BUILD_SUCCESS++))
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_error "${component}: Build FALHOU após ${duration}s (ver ${log_file})"
        ((BUILD_FAILED++))
        return 1
    fi
}

export_image_compressed() {
    local component="$1"
    local image_name="${DOCKER_PREFIX}/${component}:${VERSION}"
    local output_file="${BUILD_CACHE_DIR}/exports/${component}-${VERSION}.tar.gz"

    mkdir -p "${BUILD_CACHE_DIR}/exports"

    log_info "Exportando ${component} com compressão gzip..."

    if docker save "${image_name}" | gzip -${COMPRESSION_LEVEL} > "${output_file}"; then
        local size=$(du -h "${output_file}" | cut -f1)
        log_success "${component}: Exportado (${size})"
        return 0
    else
        log_error "${component}: Falha na exportação"
        return 1
    fi
}

import_image_compressed() {
    local archive="$1"

    log_info "Importando imagem de ${archive}..."

    if gunzip -c "${archive}" | docker load; then
        log_success "Imagem importada com sucesso"
        return 0
    else
        log_error "Falha ao importar imagem"
        return 1
    fi
}

# ===========================
# Funções de Push
# ===========================

push_to_remote_registry() {
    local component="$1"
    local source_image="${DOCKER_PREFIX}/${component}:${VERSION}"
    local remote_image="${REGISTRY_URL}/${component}:${VERSION}"
    local start_time=$(date +%s)

    log_info "Pushing ${component} -> ${REGISTRY_URL}..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_warning "[DRY-RUN] docker push ${remote_image}"
        return 0
    fi

    # Tag para registry remoto
    if ! docker tag "${source_image}" "${remote_image}"; then
        log_error "${component}: Falha ao criar tag"
        ((PUSH_FAILED++))
        return 1
    fi

    # Push com retry
    if retry 3 5 docker push "${remote_image}"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_success "${component}: Push OK (${duration}s)"

        # Tag latest também
        docker tag "${source_image}" "${REGISTRY_URL}/${component}:latest"
        docker push "${REGISTRY_URL}/${component}:latest" 2>/dev/null || true

        ((PUSH_SUCCESS++))
        return 0
    else
        log_error "${component}: Push FALHOU"
        ((PUSH_FAILED++))
        return 1
    fi
}

check_registry_connection() {
    log_info "Verificando conexão com registry ${REGISTRY_URL}..."

    if curl -sf "http://${REGISTRY_URL}/v2/" >/dev/null 2>&1; then
        log_success "Registry acessível"
        return 0
    else
        log_error "Registry ${REGISTRY_URL} inacessível"
        return 1
    fi
}

# ===========================
# Funções de Deploy
# ===========================

switch_k8s_context() {
    log_info "Switching para contexto ${K8S_CONTEXT}..."

    if ! kubectl config use-context "${K8S_CONTEXT}" 2>/dev/null; then
        log_error "Contexto ${K8S_CONTEXT} não encontrado"
        log_info "Contextos disponíveis:"
        kubectl config get-contexts --output=name
        return 1
    fi

    log_success "Usando contexto: ${K8S_CONTEXT}"

    # Verificar conexão
    if kubectl cluster-info &>/dev/null; then
        log_success "Cluster conectado"
        return 0
    else
        log_error "Falha ao conectar ao cluster"
        return 1
    fi
}

deploy_component() {
    local component="$1"
    local helm_chart="${PROJECT_ROOT}/helm-charts/${component}"
    local values_file=""

    # Determinar arquivo de values
    if [[ -f "${helm_chart}/values-prod.yaml" ]]; then
        values_file="${helm_chart}/values-prod.yaml"
    elif [[ -f "${helm_chart}/values-local.yaml" ]]; then
        values_file="${helm_chart}/values-local.yaml"
    elif [[ -f "${helm_chart}/values.yaml" ]]; then
        values_file="${helm_chart}/values.yaml"
    else
        log_warning "${component}: Helm chart não encontrado, pulando deploy"
        return 0
    fi

    log_info "Deploying ${component} via Helm..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_warning "[DRY-RUN] helm upgrade --install ${component}"
        return 0
    fi

    if helm upgrade --install "${component}" "${helm_chart}" \
        --namespace "${NAMESPACE}" \
        --create-namespace \
        --values "${values_file}" \
        --set image.repository="${REGISTRY_URL}/${component}" \
        --set image.tag="${VERSION}" \
        --wait \
        --timeout 5m 2>&1; then

        log_success "${component}: Deploy OK"
        ((DEPLOY_SUCCESS++))
        return 0
    else
        log_error "${component}: Deploy FALHOU"
        ((DEPLOY_FAILED++))
        return 1
    fi
}

# ===========================
# Funções de Controle
# ===========================

process_components_parallel() {
    local action="$1"
    shift
    local components=("$@")
    local pids=()
    local failed=0

    for component in "${components[@]}"; do
        # Controle de slots paralelos
        while [[ $(jobs -r | wc -l) -ge ${PARALLEL_JOBS} ]]; do
            sleep 0.5
        done

        (
            case "${action}" in
                build) build_with_compression "${component}" ;;
                push) push_to_remote_registry "${component}" ;;
                export) export_image_compressed "${component}" ;;
                deploy) deploy_component "${component}" ;;
            esac
        ) &
        pids+=($!)
    done

    # Aguardar todos os jobs
    for pid in "${pids[@]}"; do
        if ! wait "${pid}"; then
            failed=1
        fi
    done

    return ${failed}
}

process_components_sequential() {
    local action="$1"
    shift
    local components=("$@")
    local failed=0

    for component in "${components[@]}"; do
        case "${action}" in
            build) build_with_compression "${component}" || failed=1 ;;
            push) push_to_remote_registry "${component}" || failed=1 ;;
            export) export_image_compressed "${component}" || failed=1 ;;
            deploy) deploy_component "${component}" || failed=1 ;;
        esac
    done

    return ${failed}
}

# ===========================
# Help e Parsing
# ===========================

show_usage() {
    cat << EOF
Neural Hive-Mind - Deploy Production Script

USAGE:
    $0 [OPTIONS] [COMPONENTS...]

OPTIONS:
    --version, -v VERSION    Versão das imagens (default: ${VERSION})
    --context, -c CONTEXT    Contexto Kubernetes (default: ${K8S_CONTEXT})
    --registry, -r URL       URL do registry (default: ${REGISTRY_URL})
    --namespace, -n NS       Namespace Kubernetes (default: ${NAMESPACE})

    --skip-build             Pular fase de build
    --skip-push              Pular fase de push
    --skip-deploy            Pular fase de deploy
    --no-cache               Desabilitar cache de build
    --compress-export        Exportar imagens como .tar.gz
    --export-only            Apenas exportar (sem push/deploy)

    --parallel, -p JOBS      Jobs paralelos (default: ${PARALLEL_JOBS})
    --compression LEVEL      Nível de compressão gzip 1-9 (default: ${COMPRESSION_LEVEL})
    --dry-run                Simular sem executar

    --group GROUP            Build grupo: specialists, core, agents, all

    -h, --help               Mostrar esta ajuda

COMPONENTES DISPONÍVEIS:
    $(printf '%s\n' "${!COMPONENTS[@]}" | sort | tr '\n' ' ')

GROUPS:
    specialists: ${GROUP_SPECIALISTS[*]}
    core:        ${GROUP_CORE[*]}
    agents:      ${GROUP_AGENTS[*]}
    all:         Todos os serviços

EXEMPLOS:
    # Build e deploy de todos os specialists para produção
    $0 --group specialists

    # Build local com compressão, push e deploy
    $0 -v 1.0.10 gateway-intencoes consensus-engine

    # Apenas build local com export comprimido
    $0 --skip-push --skip-deploy --compress-export specialist-business

    # Deploy para cluster prod com imagens já no registry
    $0 --skip-build --skip-push --group all

    # Dry-run completo
    $0 --dry-run --group specialists

EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version|-v) VERSION="$2"; shift 2 ;;
            --context|-c) K8S_CONTEXT="$2"; shift 2 ;;
            --registry|-r) REGISTRY_URL="$2"; shift 2 ;;
            --namespace|-n) NAMESPACE="$2"; shift 2 ;;
            --parallel|-p) PARALLEL_JOBS="$2"; shift 2 ;;
            --compression) COMPRESSION_LEVEL="$2"; shift 2 ;;
            --skip-build) SKIP_BUILD=true; shift ;;
            --skip-push) SKIP_PUSH=true; shift ;;
            --skip-deploy) SKIP_DEPLOY=true; shift ;;
            --no-cache) USE_CACHE=false; shift ;;
            --compress-export) COMPRESS_EXPORT=true; shift ;;
            --export-only) EXPORT_ONLY=true; SKIP_PUSH=true; SKIP_DEPLOY=true; shift ;;
            --dry-run) DRY_RUN=true; shift ;;
            --group)
                case "$2" in
                    specialists) SELECTED_COMPONENTS+=("${GROUP_SPECIALISTS[@]}") ;;
                    core) SELECTED_COMPONENTS+=("${GROUP_CORE[@]}") ;;
                    agents) SELECTED_COMPONENTS+=("${GROUP_AGENTS[@]}") ;;
                    all)
                        for key in "${!COMPONENTS[@]}"; do
                            [[ "${COMPONENTS[$key]}" == services/* ]] && SELECTED_COMPONENTS+=("$key")
                        done
                        ;;
                    *) log_error "Grupo desconhecido: $2"; exit 1 ;;
                esac
                shift 2
                ;;
            -h|--help) show_usage; exit 0 ;;
            -*)
                log_error "Opção desconhecida: $1"
                show_usage
                exit 1
                ;;
            *)
                if [[ -n "${COMPONENTS[$1]:-}" ]]; then
                    SELECTED_COMPONENTS+=("$1")
                else
                    log_error "Componente desconhecido: $1"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Default: todos os services se nenhum especificado
    if [[ ${#SELECTED_COMPONENTS[@]} -eq 0 ]]; then
        log_warning "Nenhum componente especificado. Use --help para ver opções."
        exit 1
    fi
}

# ===========================
# Sumário
# ===========================

print_summary() {
    log_section "SUMÁRIO DA EXECUÇÃO"

    cat << EOF

┌─────────────────────────────────────────────────────────────┐
│           Neural Hive-Mind Deploy v${VERSION}                    │
└─────────────────────────────────────────────────────────────┘

Configuração:
  • Contexto K8s:    ${K8S_CONTEXT}
  • Registry:        ${REGISTRY_URL}
  • Namespace:       ${NAMESPACE}
  • Compressão:      gzip level ${COMPRESSION_LEVEL}
  • Jobs paralelos:  ${PARALLEL_JOBS}

Resultados:
  • Builds:   ${BUILD_SUCCESS} sucesso, ${BUILD_FAILED} falhas
  • Pushes:   ${PUSH_SUCCESS} sucesso, ${PUSH_FAILED} falhas
  • Deploys:  ${DEPLOY_SUCCESS} sucesso, ${DEPLOY_FAILED} falhas

Logs: ${LOG_DIR}/

EOF

    if [[ ${BUILD_FAILED} -eq 0 ]] && [[ ${PUSH_FAILED} -eq 0 ]] && [[ ${DEPLOY_FAILED} -eq 0 ]]; then
        log_success "Deploy concluído com sucesso!"
        return 0
    else
        log_error "Deploy concluído com erros"
        return 1
    fi
}

# ===========================
# Main
# ===========================

main() {
    parse_arguments "$@"

    log_section "NEURAL HIVE-MIND DEPLOY"
    log_info "Versão: ${VERSION}"
    log_info "Componentes: ${SELECTED_COMPONENTS[*]}"
    log_info "Contexto: ${K8S_CONTEXT}"

    mkdir -p "${LOG_DIR}"

    # Verificar pré-requisitos
    check_docker_running || exit 1

    # === FASE 1: BUILD ===
    if [[ "${SKIP_BUILD}" != "true" ]]; then
        log_section "FASE 1: BUILD LOCAL"

        # Verificar se buildx está disponível
        if ! docker buildx version &>/dev/null; then
            log_warning "docker buildx não disponível, usando build padrão"
        fi

        process_components_parallel "build" "${SELECTED_COMPONENTS[@]}" || true
        log_info "Build: ${BUILD_SUCCESS} sucesso, ${BUILD_FAILED} falhas"

        # Export comprimido se solicitado
        if [[ "${COMPRESS_EXPORT}" == "true" ]]; then
            log_section "EXPORTANDO IMAGENS COMPRIMIDAS"
            process_components_parallel "export" "${SELECTED_COMPONENTS[@]}" || true
        fi
    fi

    # === FASE 2: PUSH ===
    if [[ "${SKIP_PUSH}" != "true" ]]; then
        log_section "FASE 2: PUSH PARA REGISTRY"

        if ! check_registry_connection; then
            log_error "Abortando push: registry inacessível"
        else
            process_components_parallel "push" "${SELECTED_COMPONENTS[@]}" || true
            log_info "Push: ${PUSH_SUCCESS} sucesso, ${PUSH_FAILED} falhas"
        fi
    fi

    # === FASE 3: DEPLOY ===
    if [[ "${SKIP_DEPLOY}" != "true" ]]; then
        log_section "FASE 3: DEPLOY VIA HELM"

        if ! switch_k8s_context; then
            log_error "Abortando deploy: falha no contexto K8s"
        else
            # Deploy sequencial para respeitar dependências
            process_components_sequential "deploy" "${SELECTED_COMPONENTS[@]}" || true
            log_info "Deploy: ${DEPLOY_SUCCESS} sucesso, ${DEPLOY_FAILED} falhas"
        fi
    fi

    print_summary
}

main "$@"
