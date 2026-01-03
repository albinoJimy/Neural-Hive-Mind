#!/bin/bash
# Build and Deploy script for Neural Hive-Mind v1.0.9
# Coordena build de imagens Docker e deploy via Helm para 6 componentes

set -euo pipefail

# ===========================
# Configuração e Variáveis
# ===========================

IMAGE_TAG="1.0.9"
NAMESPACE="neural-hive"
DOCKER_REGISTRY="neural-hive-mind"
BUILD_CONTEXT="/jimy/Neural-Hive-Mind"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="${BUILD_CONTEXT}/logs"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Componentes a processar
declare -a SPECIALISTS=(
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
)

# Flags de controle
SKIP_BUILD=false
SKIP_TESTS=false
DRY_RUN=false
COMPONENT_ONLY=""
PARALLEL_BUILD=false
PUSH_IMAGES=false

# Contadores
BUILD_SUCCESS=0
BUILD_FAILED=0
DEPLOY_SUCCESS=0
DEPLOY_FAILED=0
TESTS_PASSED=0
TESTS_FAILED=0

# ===========================
# Funções Auxiliares
# ===========================

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

log_to_file() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "${LOG_DIR}/build-v${IMAGE_TAG}-${TIMESTAMP}.log"
}

show_usage() {
    cat << EOF
Uso: $0 [OPTIONS]

Opções:
    --skip-build          Pular build de imagens (usar imagens existentes)
    --skip-tests          Pular testes pré-deploy (não recomendado)
    --dry-run            Simular deploy sem aplicar mudanças
    --component <name>   Deployar apenas um componente específico
    --parallel-build     Construir imagens em paralelo
    --push               Fazer push das imagens para registry remoto
    -h, --help           Mostrar esta mensagem de ajuda

Exemplos:
    $0                                    # Build e deploy completo
    $0 --skip-build                       # Deploy sem rebuild
    $0 --component consensus-engine       # Deploy apenas consensus-engine
    $0 --parallel-build --push            # Build em paralelo e push para registry
EOF
}

# ===========================
# Parse de Argumentos
# ===========================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --component)
                COMPONENT_ONLY="$2"
                shift 2
                ;;
            --parallel-build)
                PARALLEL_BUILD=true
                shift
                ;;
            --push)
                PUSH_IMAGES=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Argumento desconhecido: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# ===========================
# Validações Pré-Build
# ===========================

validate_environment() {
    print_header "Validando Ambiente"

    # Criar diretório de logs se não existir
    mkdir -p "${LOG_DIR}"

    # Verificar Docker
    if ! docker info &> /dev/null; then
        print_error "Docker não está rodando ou não acessível"
        exit 1
    fi
    print_success "Docker: OK"

    # Verificar kubectl
    if ! kubectl cluster-info &> /dev/null; then
        print_error "kubectl não está conectado ao cluster"
        exit 1
    fi
    print_success "kubectl: OK"

    # Verificar Helm
    if ! helm version &> /dev/null; then
        print_error "Helm não está instalado"
        exit 1
    fi
    print_success "Helm: OK"

    # Verificar namespace
    if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
        print_warning "Namespace ${NAMESPACE} não existe. Criando..."
        kubectl create namespace "${NAMESPACE}"
    fi
    print_success "Namespace ${NAMESPACE}: OK"

    log_to_file "Validação de ambiente concluída com sucesso"
}

# ===========================
# Testes Pré-Build
# ===========================

run_tests() {
    if [[ "${SKIP_TESTS}" == true ]]; then
        print_warning "Testes pré-build pulados (--skip-tests)"
        return 0
    fi

    print_header "Executando Testes Pré-Build"

    local test_failed=false

    # Testes do servidor (specialists library)
    print_info "Executando testes do servidor gRPC..."
    cd "${BUILD_CONTEXT}/libraries/python/neural_hive_specialists"
    if pytest tests/test_grpc_server_timestamp.py -v --tb=short; then
        print_success "Testes do servidor: PASSOU"
        ((TESTS_PASSED++))
    else
        print_error "Testes do servidor: FALHOU"
        ((TESTS_FAILED++))
        test_failed=true
    fi

    # Testes do cliente (consensus-engine)
    print_info "Executando testes do cliente gRPC..."
    cd "${BUILD_CONTEXT}/services/consensus-engine"
    if pytest tests/test_specialists_grpc_client.py -v --tb=short; then
        print_success "Testes do cliente: PASSOU"
        ((TESTS_PASSED++))
    else
        print_error "Testes do cliente: FALHOU"
        ((TESTS_FAILED++))
        test_failed=true
    fi

    cd "${BUILD_CONTEXT}"

    if [[ "${test_failed}" == true ]]; then
        print_error "Testes falharam. Abortando build."
        log_to_file "Testes falharam. Build abortado."
        exit 1
    fi

    print_success "Todos os testes passaram (${TESTS_PASSED}/${TESTS_PASSED})"
    log_to_file "Testes pré-build concluídos: ${TESTS_PASSED} passaram, ${TESTS_FAILED} falharam"
}

# ===========================
# Build de Imagens Docker
# ===========================

build_image() {
    local component=$1
    local start_time=$(date +%s)

    print_info "Building ${component}:${IMAGE_TAG}..."

    local dockerfile_path="${BUILD_CONTEXT}/services/${component}/Dockerfile"
    local image_name="${DOCKER_REGISTRY}/${component}:${IMAGE_TAG}"

    if docker build -t "${image_name}" -f "${dockerfile_path}" "${BUILD_CONTEXT}" >> "${LOG_DIR}/build-v${IMAGE_TAG}-${TIMESTAMP}.log" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_success "${component}: Build completo em ${duration}s"
        ((BUILD_SUCCESS++))
        log_to_file "Build ${component}: SUCESSO (${duration}s)"

        # Push da imagem se flag --push estiver ativada
        if [[ "${PUSH_IMAGES}" == true ]]; then
            print_info "Pushing ${image_name} para registry..."
            if docker push "${image_name}" >> "${LOG_DIR}/build-v${IMAGE_TAG}-${TIMESTAMP}.log" 2>&1; then
                print_success "${component}: Push completo"
                log_to_file "Push ${component}: SUCESSO"
            else
                print_warning "${component}: Push falhou (imagem construída localmente)"
                log_to_file "Push ${component}: FALHA"
            fi
        fi

        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_error "${component}: Build falhou após ${duration}s"
        ((BUILD_FAILED++))
        log_to_file "Build ${component}: FALHA (${duration}s)"
        return 1
    fi
}

build_all_images() {
    if [[ "${SKIP_BUILD}" == true ]]; then
        print_warning "Build de imagens pulado (--skip-build)"
        return 0
    fi

    print_header "Construindo Imagens Docker (v${IMAGE_TAG})"

    local components=("consensus-engine" "${SPECIALISTS[@]}")

    # Filtrar se apenas um componente foi especificado
    if [[ -n "${COMPONENT_ONLY}" ]]; then
        components=("${COMPONENT_ONLY}")
    fi

    if [[ "${PARALLEL_BUILD}" == true ]]; then
        print_info "Construindo imagens em paralelo..."
        for component in "${components[@]}"; do
            build_image "${component}" &
        done
        wait
    else
        for component in "${components[@]}"; do
            build_image "${component}"
        done
    fi

    print_info "Builds concluídos: ${BUILD_SUCCESS} sucesso, ${BUILD_FAILED} falhas"
    log_to_file "Builds concluídos: ${BUILD_SUCCESS} sucesso, ${BUILD_FAILED} falhas"

    if [[ ${BUILD_FAILED} -gt 0 ]]; then
        print_error "Alguns builds falharam. Verifique os logs em ${LOG_DIR}"
        return 1
    fi
}

# ===========================
# Deploy via Helm
# ===========================

deploy_component() {
    local component=$1
    local chart_name=$2

    print_info "Deployando ${component} via Helm..."

    local helm_chart="${BUILD_CONTEXT}/helm-charts/${chart_name}"
    local values_file="${helm_chart}/values-k8s.yaml"

    # Usar values.yaml para consensus-engine
    if [[ "${component}" == "consensus-engine" ]]; then
        values_file="${helm_chart}/values.yaml"
    fi

    if [[ "${DRY_RUN}" == true ]]; then
        print_warning "DRY RUN: helm upgrade --install ${component} ${helm_chart}"
        ((DEPLOY_SUCCESS++))
        return 0
    fi

    if helm upgrade --install "${component}" "${helm_chart}" \
        --namespace "${NAMESPACE}" \
        --values "${values_file}" \
        --set image.repository="${DOCKER_REGISTRY}/${component}" \
        --set image.tag="${IMAGE_TAG}" \
        --wait \
        --timeout 5m \
        >> "${LOG_DIR}/deploy-v${IMAGE_TAG}-${TIMESTAMP}.log" 2>&1; then

        print_success "${component}: Deploy completo"
        ((DEPLOY_SUCCESS++))
        log_to_file "Deploy ${component}: SUCESSO"

        # Aguardar pods ficarem ready
        print_info "Aguardando pod ${component} ficar ready..."
        if kubectl wait --for=condition=ready pod -l app.kubernetes.io/name="${chart_name}" -n "${NAMESPACE}" --timeout=300s &> /dev/null; then
            print_success "${component}: Pod ready"
        else
            print_warning "${component}: Pod demorou a ficar ready (timeout)"
        fi

        return 0
    else
        print_error "${component}: Deploy falhou"
        ((DEPLOY_FAILED++))
        log_to_file "Deploy ${component}: FALHA"
        return 1
    fi
}

deploy_all_components() {
    print_header "Deploy via Helm (Namespace: ${NAMESPACE})"

    local components_map=(
        "specialist-business:specialist-business"
        "specialist-technical:specialist-technical"
        "specialist-behavior:specialist-behavior"
        "specialist-evolution:specialist-evolution"
        "specialist-architecture:specialist-architecture"
        "consensus-engine:consensus-engine"
    )

    # Filtrar se apenas um componente foi especificado
    if [[ -n "${COMPONENT_ONLY}" ]]; then
        deploy_component "${COMPONENT_ONLY}" "${COMPONENT_ONLY}"
    else
        # Deploy specialists primeiro (paralelo), depois consensus-engine
        print_info "Deployando specialists..."
        for mapping in "${components_map[@]}"; do
            IFS=':' read -r component chart <<< "${mapping}"
            if [[ "${component}" != "consensus-engine" ]]; then
                deploy_component "${component}" "${chart}"
            fi
        done

        # Deploy consensus-engine por último
        print_info "Deployando consensus-engine..."
        deploy_component "consensus-engine" "consensus-engine"
    fi

    print_info "Deploys concluídos: ${DEPLOY_SUCCESS} sucesso, ${DEPLOY_FAILED} falhas"
    log_to_file "Deploys concluídos: ${DEPLOY_SUCCESS} sucesso, ${DEPLOY_FAILED} falhas"
}

# ===========================
# Validação Pós-Deploy
# ===========================

validate_deployment() {
    print_header "Validação Pós-Deploy"

    local components=("consensus-engine" "${SPECIALISTS[@]}")

    # Filtrar se apenas um componente foi especificado
    if [[ -n "${COMPONENT_ONLY}" ]]; then
        components=("${COMPONENT_ONLY}")
    fi

    # Verificar versão das imagens
    print_info "Verificando versões das imagens..."
    for component in "${components[@]}"; do
        # Determinar nome do chart (usado em app.kubernetes.io/name)
        local chart_name="${component}"
        local image=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${chart_name}" -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null || echo "N/A")
        if [[ "${image}" == *"${IMAGE_TAG}"* ]]; then
            print_success "${component}: ${image}"
        else
            print_warning "${component}: ${image} (esperado: ${IMAGE_TAG})"
        fi
    done

    # Health checks
    print_info "Executando health checks..."
    for component in "${components[@]}"; do
        # Determinar nome do chart (usado em app.kubernetes.io/name)
        local chart_name="${component}"
        local pod=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${chart_name}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "${pod}" ]]; then
            if kubectl exec -n "${NAMESPACE}" "${pod}" -- curl -f http://localhost:8000/health -s &> /dev/null; then
                print_success "${component}: Health check OK"
            else
                print_warning "${component}: Health check falhou"
            fi
        else
            print_warning "${component}: Pod não encontrado"
        fi
    done

    log_to_file "Validação pós-deploy concluída"
}

# ===========================
# Relatório Final
# ===========================

generate_summary() {
    print_header "Resumo da Sessão"

    local end_time=$(date +%s)
    local start_time_file="${LOG_DIR}/.start_time_${IMAGE_TAG}"
    local total_duration=0

    if [[ -f "${start_time_file}" ]]; then
        local start_time=$(cat "${start_time_file}")
        total_duration=$((end_time - start_time))
        rm -f "${start_time_file}"
    fi

    cat << EOF
┌────────────────────────────────────────────────────────┐
│           Neural Hive-Mind v${IMAGE_TAG} Deploy          │
└────────────────────────────────────────────────────────┘

📊 Métricas da Sessão:
   • Duração Total: ${total_duration}s
   • Testes Executados: ${TESTS_PASSED} passaram, ${TESTS_FAILED} falharam
   • Builds: ${BUILD_SUCCESS} sucesso, ${BUILD_FAILED} falhas
   • Deploys: ${DEPLOY_SUCCESS} sucesso, ${DEPLOY_FAILED} falhas

📁 Artefatos Gerados:
   • Logs de build: ${LOG_DIR}/build-v${IMAGE_TAG}-${TIMESTAMP}.log
   • Logs de deploy: ${LOG_DIR}/deploy-v${IMAGE_TAG}-${TIMESTAMP}.log

EOF

    # Status final
    if [[ ${TESTS_FAILED} -eq 0 ]] && [[ ${BUILD_FAILED} -eq 0 ]] && [[ ${DEPLOY_FAILED} -eq 0 ]]; then
        print_success "✓ Deploy concluído com sucesso!"
        log_to_file "Deploy v${IMAGE_TAG} concluído com SUCESSO"
        return 0
    else
        print_error "✗ Deploy concluído com erros. Verifique os logs."
        log_to_file "Deploy v${IMAGE_TAG} concluído com ERROS"
        return 1
    fi
}

# ===========================
# Main
# ===========================

main() {
    # Registrar tempo de início
    echo "$(date +%s)" > "${LOG_DIR}/.start_time_${IMAGE_TAG}"

    parse_arguments "$@"

    print_header "Neural Hive-Mind v${IMAGE_TAG} - Build & Deploy"
    print_info "Timestamp: ${TIMESTAMP}"
    print_info "Namespace: ${NAMESPACE}"
    print_info "Registry: ${DOCKER_REGISTRY}"

    validate_environment
    run_tests
    build_all_images
    deploy_all_components
    validate_deployment
    generate_summary
}

# Executar script
main "$@"
