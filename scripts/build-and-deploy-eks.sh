#!/bin/bash

################################################################################
# Script Orquestrador: Build e Deploy para EKS
################################################################################
# Este script orquestra o fluxo completo de build local, push para ECR e
# atualização de manifestos Kubernetes/Helm para deployment no EKS.
#
# Integra os seguintes scripts:
# 1. build-local-parallel.sh - Build paralelo de imagens Docker
# 2. push-to-ecr.sh - Push paralelo para Amazon ECR
# 3. update-manifests-ecr.sh - Atualização de manifestos com novas tags
#
# Autor: Neural Hive Mind Team
# Data: 2025-11-14
################################################################################

set -euo pipefail

# Cores para logging
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m' # No Color

# Variáveis de configuração padrão
VERSION="${VERSION:-1.0.7}"
MAX_PARALLEL_JOBS="${MAX_PARALLEL_JOBS:-4}"
ENV="${ENV:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_PUSH="${SKIP_PUSH:-false}"
SKIP_UPDATE="${SKIP_UPDATE:-false}"
NO_CACHE="${NO_CACHE:-false}"
DRY_RUN="${DRY_RUN:-false}"
SERVICES_FILTER="${SERVICES_FILTER:-}"

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Variáveis globais para rastreamento de resultados
BUILD_EXIT_CODE=0
PUSH_EXIT_CODE=0
UPDATE_EXIT_CODE=0
BUILD_DURATION=0
PUSH_DURATION=0
UPDATE_DURATION=0
TOTAL_START=0
AWS_ACCOUNT_ID=""
ECR_REGISTRY=""
BUILT_IMAGES_COUNT=0
PUSHED_IMAGES_COUNT=0
UPDATED_MANIFESTS_COUNT=0

################################################################################
# Funções de Logging
################################################################################

log_info() {
    echo -e "${BLUE}ℹ️  $*${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $*${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $*${NC}"
}

log_error() {
    echo -e "${RED}❌ $*${NC}"
}

log_phase() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $*${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

log_phase_result() {
    local phase="$1"
    local exit_code="$2"
    local duration="$3"

    if [[ ${exit_code} -eq 0 ]]; then
        log_success "${phase} concluída com sucesso (${duration}s)"
    else
        log_error "${phase} falhou com código de saída ${exit_code} (${duration}s)"
    fi
}

################################################################################
# Função de Pré-requisitos
################################################################################

check_prerequisites() {
    log_phase "VERIFICAÇÃO DE PRÉ-REQUISITOS"

    local has_error=false

    # Docker
    log_info "Verificando Docker..."
    if ! command -v docker &> /dev/null; then
        log_error "Docker não encontrado. Instale Docker primeiro."
        has_error=true
    else
        if ! docker info &> /dev/null; then
            log_error "Docker daemon não está rodando. Inicie o Docker primeiro."
            has_error=true
        else
            log_success "Docker: OK"

            # Verificar espaço em disco
            local available_space=$(df -BG "${PROJECT_ROOT}" | awk 'NR==2 {print $4}' | sed 's/G//')
            if [[ ${available_space} -lt 10 ]]; then
                log_warning "Espaço em disco baixo: ${available_space}GB disponível (recomendado: ≥10GB)"
            else
                log_success "Espaço em disco: ${available_space}GB disponível"
            fi
        fi
    fi

    # AWS CLI
    log_info "Verificando AWS CLI..."

    # Determinar se AWS CLI é obrigatória
    local aws_required=true
    if [[ "${SKIP_PUSH}" == "true" && "${DRY_RUN}" == "true" ]]; then
        aws_required=false
    elif [[ "${SKIP_PUSH}" == "true" && "${SKIP_UPDATE}" == "false" ]]; then
        aws_required=true
    elif [[ "${SKIP_PUSH}" == "false" ]]; then
        aws_required=true
    fi

    if ! command -v aws &> /dev/null; then
        if [[ "${aws_required}" == "true" ]]; then
            log_error "AWS CLI não encontrado. Instale AWS CLI primeiro."
            has_error=true
        else
            log_warning "AWS CLI não encontrado (OK para preview/dry-run sem push)"
        fi
    else
        if ! aws sts get-caller-identity &> /dev/null; then
            if [[ "${aws_required}" == "true" ]]; then
                log_error "Credenciais AWS não configuradas ou inválidas."
                log_info "Configure com: aws configure"
                has_error=true
            else
                log_warning "Credenciais AWS não configuradas (OK para preview/dry-run sem push)"
            fi
        else
            AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
            ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
            log_success "AWS CLI: OK (Account: ${AWS_ACCOUNT_ID})"
            log_success "ECR Registry: ${ECR_REGISTRY}"
        fi
    fi

    # kubectl (apenas se não skip update)
    if [[ "${SKIP_UPDATE}" == "false" ]]; then
        log_info "Verificando kubectl..."

        # kubectl é obrigatório apenas se update for real (não dry-run)
        local kubectl_required=true
        if [[ "${DRY_RUN}" == "true" ]]; then
            kubectl_required=false
        fi

        if ! command -v kubectl &> /dev/null; then
            if [[ "${kubectl_required}" == "true" ]]; then
                log_error "kubectl não encontrado. Instale kubectl primeiro."
                has_error=true
            else
                log_warning "kubectl não encontrado (OK para preview/dry-run)"
            fi
        else
            # Verificar cluster-info com timeout condicional (compatível com macOS)
            local cluster_check_result=0
            if command -v timeout &> /dev/null; then
                timeout 5s kubectl cluster-info &> /dev/null
                cluster_check_result=$?
            else
                kubectl cluster-info &> /dev/null
                cluster_check_result=$?
            fi

            if [[ ${cluster_check_result} -eq 0 ]]; then
                local current_context=$(kubectl config current-context 2>/dev/null || echo "nenhum")
                log_success "kubectl: OK (Context: ${current_context})"
            else
                if [[ "${kubectl_required}" == "true" ]]; then
                    log_warning "kubectl encontrado mas cluster não acessível (pode causar falhas em update real)"
                else
                    log_warning "Cluster não acessível (OK para preview/dry-run)"
                fi
            fi
        fi
    fi

    # Carregar ~/.neural-hive-env se existir
    if [[ -f "${HOME}/.neural-hive-env" ]]; then
        log_info "Carregando configurações de ${HOME}/.neural-hive-env..."
        source "${HOME}/.neural-hive-env"
        log_success "Configurações carregadas"
    fi

    # Verificar variáveis de ambiente
    log_info "Validando variáveis de ambiente..."
    if [[ -z "${ENV}" ]]; then
        log_error "ENV não definido"
        has_error=true
    else
        log_success "ENV: ${ENV}"
    fi

    if [[ -z "${AWS_REGION}" ]]; then
        log_error "AWS_REGION não definido"
        has_error=true
    else
        log_success "AWS_REGION: ${AWS_REGION}"
    fi

    # yq (opcional)
    if command -v yq &> /dev/null; then
        log_success "yq: OK (recomendado para update de manifestos)"
    else
        log_warning "yq não encontrado (fallback para sed será usado)"
    fi

    # Resumo
    echo ""
    log_info "═══════════════════════════════════════════════════════════════"
    log_info "CONFIGURAÇÃO DETECTADA:"
    log_info "  Versão: ${VERSION}"
    log_info "  Ambiente: ${ENV}"
    log_info "  Região AWS: ${AWS_REGION}"
    log_info "  Paralelismo: ${MAX_PARALLEL_JOBS}"
    if [[ -n "${SERVICES_FILTER}" ]]; then
        log_info "  Serviços filtrados: ${SERVICES_FILTER}"
    fi
    log_info "═══════════════════════════════════════════════════════════════"
    echo ""

    if [[ "${has_error}" == "true" ]]; then
        log_error "Pré-requisitos não atendidos. Corrija os erros acima e tente novamente."
        exit 1
    fi

    log_success "Todos os pré-requisitos verificados ✓"
}

################################################################################
# Função de Build
################################################################################

execute_build_phase() {
    if [[ "${SKIP_BUILD}" == "true" ]]; then
        log_info "⏭️  Pulando fase de build (--skip-build ativado)"
        return 0
    fi

    log_phase "FASE 1: BUILD LOCAL DAS IMAGENS"

    # Construir comando
    local cmd="${SCRIPT_DIR}/build-local-parallel.sh"
    cmd+=" --version ${VERSION}"
    cmd+=" --parallel ${MAX_PARALLEL_JOBS}"

    if [[ -n "${SERVICES_FILTER}" ]]; then
        cmd+=" --services ${SERVICES_FILTER}"
    fi

    if [[ "${NO_CACHE}" == "true" ]]; then
        cmd+=" --no-cache"
    fi

    log_info "Executando: ${cmd}"
    echo ""

    # Executar com captura de exit code
    local start_time=$(date +%s)
    set +e
    ${cmd}
    BUILD_EXIT_CODE=$?
    set -e
    local end_time=$(date +%s)
    BUILD_DURATION=$((end_time - start_time))

    # Extrair contagem de imagens buildadas dos logs
    if [[ -f "${PROJECT_ROOT}/logs/build-summary.log" ]]; then
        BUILT_IMAGES_COUNT=$(grep -c "Successfully built" "${PROJECT_ROOT}/logs/build-summary.log" 2>/dev/null || echo "0")
    elif [[ -d "${PROJECT_ROOT}/logs" ]]; then
        local latest_build_log=$(ls -t "${PROJECT_ROOT}"/logs/build-*.log 2>/dev/null | head -1)
        if [[ -n "${latest_build_log}" ]]; then
            BUILT_IMAGES_COUNT=$(grep -c "Successfully built\|Successfully tagged" "${latest_build_log}" 2>/dev/null | awk '{print int($1/2)}' || echo "0")
        fi
    fi

    echo ""
    log_phase_result "Fase de Build" "${BUILD_EXIT_CODE}" "${BUILD_DURATION}"

    return ${BUILD_EXIT_CODE}
}

################################################################################
# Função de Push
################################################################################

execute_push_phase() {
    if [[ "${SKIP_PUSH}" == "true" ]]; then
        log_info "⏭️  Pulando fase de push (--skip-push ativado)"
        return 0
    fi

    log_phase "FASE 2: PUSH PARA ECR"

    # Construir comando
    local cmd="${SCRIPT_DIR}/push-to-ecr.sh"
    cmd+=" --version ${VERSION}"
    cmd+=" --parallel ${MAX_PARALLEL_JOBS}"
    cmd+=" --env ${ENV}"
    cmd+=" --region ${AWS_REGION}"

    if [[ -n "${SERVICES_FILTER}" ]]; then
        cmd+=" --services ${SERVICES_FILTER}"
    fi

    log_info "Executando: ${cmd}"
    echo ""

    # Executar com captura de exit code
    local start_time=$(date +%s)
    set +e
    ${cmd}
    PUSH_EXIT_CODE=$?
    set -e
    local end_time=$(date +%s)
    PUSH_DURATION=$((end_time - start_time))

    # Extrair contagem de imagens enviadas dos logs
    if [[ -f "${PROJECT_ROOT}/logs/push-summary.log" ]]; then
        PUSHED_IMAGES_COUNT=$(grep -c "Successfully pushed\|digest:" "${PROJECT_ROOT}/logs/push-summary.log" 2>/dev/null || echo "0")
    elif [[ -d "${PROJECT_ROOT}/logs" ]]; then
        local latest_push_log=$(ls -t "${PROJECT_ROOT}"/logs/push-*.log 2>/dev/null | head -1)
        if [[ -n "${latest_push_log}" ]]; then
            PUSHED_IMAGES_COUNT=$(grep -c "Pushed\|digest:" "${latest_push_log}" 2>/dev/null || echo "0")
        fi
    fi

    echo ""
    log_phase_result "Fase de Push" "${PUSH_EXIT_CODE}" "${PUSH_DURATION}"

    return ${PUSH_EXIT_CODE}
}

################################################################################
# Função de Update de Manifestos
################################################################################

execute_update_phase() {
    if [[ "${SKIP_UPDATE}" == "true" ]]; then
        log_info "⏭️  Pulando fase de atualização de manifestos (--skip-update ativado)"
        return 0
    fi

    log_phase "FASE 3: ATUALIZAÇÃO DE MANIFESTOS"

    # Construir comando
    local cmd="${SCRIPT_DIR}/update-manifests-ecr.sh"
    cmd+=" --version ${VERSION}"
    cmd+=" --env ${ENV}"
    cmd+=" --region ${AWS_REGION}"

    if [[ -n "${SERVICES_FILTER}" ]]; then
        cmd+=" --services ${SERVICES_FILTER}"
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        cmd+=" --dry-run"
    fi

    log_info "Executando: ${cmd}"
    echo ""

    # Executar com captura de exit code
    local start_time=$(date +%s)
    set +e
    ${cmd}
    UPDATE_EXIT_CODE=$?
    set -e
    local end_time=$(date +%s)
    UPDATE_DURATION=$((end_time - start_time))

    # Extrair contagem de manifestos atualizados dos logs
    if [[ -f "${PROJECT_ROOT}/logs/update-summary.log" ]]; then
        UPDATED_MANIFESTS_COUNT=$(grep -c "Updated\|Atualizado" "${PROJECT_ROOT}/logs/update-summary.log" 2>/dev/null || echo "0")
    elif [[ -d "${PROJECT_ROOT}/logs" ]]; then
        local latest_update_log=$(ls -t "${PROJECT_ROOT}"/logs/update-*.log 2>/dev/null | head -1)
        if [[ -n "${latest_update_log}" ]]; then
            UPDATED_MANIFESTS_COUNT=$(grep -c "Updated\|modified\|Atualizado" "${latest_update_log}" 2>/dev/null || echo "0")
        fi
    fi

    echo ""
    log_phase_result "Fase de Update" "${UPDATE_EXIT_CODE}" "${UPDATE_DURATION}"

    return ${UPDATE_EXIT_CODE}
}

################################################################################
# Função de Resumo Final
################################################################################

print_final_summary() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}           RESUMO FINAL DO DEPLOYMENT${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Seção 1: Status das Fases
    echo -e "${BLUE}📊 STATUS DAS FASES:${NC}"
    echo ""

    if [[ "${SKIP_BUILD}" == "true" ]]; then
        echo -e "   ⏭️  Build Local: ${YELLOW}Pulada${NC}"
    elif [[ ${BUILD_EXIT_CODE} -eq 0 ]]; then
        echo -e "   ✅ Build Local: ${GREEN}Sucesso${NC} (${BUILD_DURATION}s)"
    else
        echo -e "   ❌ Build Local: ${RED}Falha${NC} (código ${BUILD_EXIT_CODE}, ${BUILD_DURATION}s)"
    fi

    if [[ "${SKIP_PUSH}" == "true" ]]; then
        echo -e "   ⏭️  Push para ECR: ${YELLOW}Pulada${NC}"
    elif [[ ${PUSH_EXIT_CODE} -eq 0 ]]; then
        echo -e "   ✅ Push para ECR: ${GREEN}Sucesso${NC} (${PUSH_DURATION}s)"
    else
        echo -e "   ❌ Push para ECR: ${RED}Falha${NC} (código ${PUSH_EXIT_CODE}, ${PUSH_DURATION}s)"
    fi

    if [[ "${SKIP_UPDATE}" == "true" ]]; then
        echo -e "   ⏭️  Update Manifestos: ${YELLOW}Pulada${NC}"
    elif [[ ${UPDATE_EXIT_CODE} -eq 0 ]]; then
        echo -e "   ✅ Update Manifestos: ${GREEN}Sucesso${NC} (${UPDATE_DURATION}s)"
    else
        echo -e "   ❌ Update Manifestos: ${RED}Falha${NC} (código ${UPDATE_EXIT_CODE}, ${UPDATE_DURATION}s)"
    fi

    echo ""

    # Seção 2: Estatísticas Agregadas
    echo -e "${BLUE}📈 ESTATÍSTICAS:${NC}"
    echo ""
    echo -e "   Versão deployada: ${GREEN}${VERSION}${NC}"
    echo -e "   Ambiente: ${GREEN}${ENV}${NC}"
    echo -e "   Região AWS: ${GREEN}${AWS_REGION}${NC}"
    if [[ -n "${ECR_REGISTRY}" ]]; then
        echo -e "   Registry ECR: ${GREEN}${ECR_REGISTRY}${NC}"
    fi

    # Estatísticas de processamento
    if [[ "${SKIP_BUILD}" == "false" && ${BUILT_IMAGES_COUNT} -gt 0 ]]; then
        echo -e "   Imagens buildadas: ${GREEN}${BUILT_IMAGES_COUNT}${NC}"
    fi
    if [[ "${SKIP_PUSH}" == "false" && ${PUSHED_IMAGES_COUNT} -gt 0 ]]; then
        echo -e "   Imagens enviadas ao ECR: ${GREEN}${PUSHED_IMAGES_COUNT}${NC}"
    fi
    if [[ "${SKIP_UPDATE}" == "false" && ${UPDATED_MANIFESTS_COUNT} -gt 0 ]]; then
        echo -e "   Manifestos/Helm charts atualizados: ${GREEN}${UPDATED_MANIFESTS_COUNT}${NC}"
    fi
    echo ""

    # Seção 3: Tempo Total
    local total_time=$((BUILD_DURATION + PUSH_DURATION + UPDATE_DURATION))
    local total_minutes=$((total_time / 60))
    local total_seconds=$((total_time % 60))

    echo -e "${BLUE}⏱️  TEMPO TOTAL:${NC}"
    echo ""
    echo -e "   ${total_minutes}m ${total_seconds}s"
    echo ""

    # Seção 4: Próximos Passos (se sucesso)
    local all_success=true
    if [[ "${SKIP_BUILD}" == "false" && ${BUILD_EXIT_CODE} -ne 0 ]]; then
        all_success=false
    fi
    if [[ "${SKIP_PUSH}" == "false" && ${PUSH_EXIT_CODE} -ne 0 ]]; then
        all_success=false
    fi
    if [[ "${SKIP_UPDATE}" == "false" && ${UPDATE_EXIT_CODE} -ne 0 ]]; then
        all_success=false
    fi

    if [[ "${all_success}" == "true" ]]; then
        echo -e "${GREEN}🎉 DEPLOYMENT PREPARADO COM SUCESSO!${NC}"
        echo ""
        echo -e "${BLUE}📋 PRÓXIMOS PASSOS:${NC}"
        echo ""

        if [[ "${SKIP_PUSH}" == "false" ]]; then
            echo "   1. Verificar imagens no ECR:"
            echo "      aws ecr describe-images --repository-name neural-hive-mind/gateway-intencoes --region ${AWS_REGION}"
            echo ""
        fi

        if [[ "${SKIP_UPDATE}" == "false" && "${DRY_RUN}" == "false" ]]; then
            echo "   2. Revisar mudanças nos manifestos:"
            echo "      git diff"
            echo ""
            echo "   3. Aplicar no cluster EKS (Helm):"
            echo "      helm upgrade neural-hive-mind ./helm/neural-hive-mind -n neural-hive-mind"
            echo ""
            echo "   4. Verificar pods:"
            echo "      kubectl get pods -n neural-hive-mind -w"
            echo ""
        elif [[ "${DRY_RUN}" == "true" ]]; then
            echo "   2. Revisar mudanças propostas acima"
            echo ""
            echo "   3. Executar sem --dry-run para aplicar:"
            echo "      ./scripts/build-and-deploy-eks.sh --skip-build --skip-push"
            echo ""
        fi
    else
        echo -e "${RED}⚠️  DEPLOYMENT COMPLETADO COM ERROS${NC}"
        echo ""
        echo -e "${BLUE}📋 LOGS DISPONÍVEIS:${NC}"
        echo ""

        if [[ "${SKIP_BUILD}" == "false" && ${BUILD_EXIT_CODE} -ne 0 ]]; then
            echo "   Build logs: ${PROJECT_ROOT}/logs/build-*.log"
        fi

        if [[ "${SKIP_PUSH}" == "false" && ${PUSH_EXIT_CODE} -ne 0 ]]; then
            echo "   Push logs: ${PROJECT_ROOT}/logs/push-*.log"
        fi

        echo ""
        echo "   Execute novamente com flags --skip-* para pular fases bem-sucedidas."
        echo ""
    fi

    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

################################################################################
# Função de Help
################################################################################

print_help() {
    cat << EOF
${BLUE}═══════════════════════════════════════════════════════════════${NC}
${BLUE}  Script Orquestrador: Build e Deploy para EKS${NC}
${BLUE}═══════════════════════════════════════════════════════════════${NC}

${GREEN}DESCRIÇÃO:${NC}
  Orquestra o fluxo completo de build local, push para ECR e atualização
  de manifestos Kubernetes/Helm para deployment no Amazon EKS.

  Executa em sequência:
    1. Build paralelo de imagens Docker (build-local-parallel.sh)
    2. Push paralelo para Amazon ECR (push-to-ecr.sh)
    3. Atualização de manifestos K8s/Helm (update-manifests-ecr.sh)

${GREEN}USO:${NC}
  $0 [OPÇÕES]

${GREEN}OPÇÕES DE CONTROLE DE FLUXO:${NC}
  --skip-build         Pular fase de build (usar imagens já buildadas)
  --skip-push          Pular fase de push para ECR
  --skip-update        Pular atualização de manifestos
  --dry-run            Preview de mudanças sem aplicar (apenas update)

${GREEN}OPÇÕES DE CONFIGURAÇÃO:${NC}
  --version VERSION    Versão das imagens (default: 1.0.7)
  --parallel N         Jobs paralelos para build/push (default: 4)
  --services LISTA     Filtrar serviços (ex: "gateway,consensus")
  --env ENV            Ambiente de deployment (default: dev)
  --region REGIÃO      Região AWS (default: us-east-1)
  --no-cache           Build sem cache Docker

${GREEN}OPÇÕES DE AJUDA:${NC}
  --help               Mostrar esta mensagem de ajuda

${GREEN}EXEMPLOS:${NC}
  # Fluxo completo (build + push + update)
  $0

  # Apenas build e push (sem atualizar manifestos)
  $0 --skip-update

  # Apenas push (imagens já buildadas)
  $0 --skip-build

  # Preview de mudanças nos manifestos
  $0 --skip-build --skip-push --dry-run

  # Versão customizada com mais paralelismo
  $0 --version 1.0.8 --parallel 8

  # Serviços específicos
  $0 --services "gateway-intencoes,consensus-engine"

  # Ambiente staging
  $0 --env staging --region us-west-2

${GREEN}PRÉ-REQUISITOS:${NC}
  - Docker (daemon rodando)
  - AWS CLI (obrigatória para push; opcional para preview/dry-run com --skip-push)
  - kubectl (se não usar --skip-update)
  - 10GB+ de espaço em disco
  - yq (recomendado, fallback para sed)

${GREEN}WORKFLOW TÍPICO:${NC}
  1. Desenvolvimento local:
     $0 --skip-update

  2. Testar mudanças nos manifestos:
     $0 --skip-build --skip-push --dry-run

  3. Deploy completo:
     $0

  4. Rollback/redeploy:
     $0 --skip-build --version 1.0.6

${BLUE}═══════════════════════════════════════════════════════════════${NC}
EOF
}

################################################################################
# Função de Parse de Argumentos
################################################################################

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --version)
                if [[ $# -lt 2 ]]; then
                    log_error "A opção '$1' requer um argumento (ex: --version 1.0.8)."
                    echo ""
                    print_help
                    exit 1
                fi
                VERSION="$2"
                shift 2
                ;;
            --parallel)
                if [[ $# -lt 2 ]]; then
                    log_error "A opção '$1' requer um argumento (ex: --parallel 4)."
                    echo ""
                    print_help
                    exit 1
                fi
                if ! [[ "$2" =~ ^[0-9]+$ ]] || [[ "$2" -le 0 ]]; then
                    log_error "--parallel deve ser um número > 0 (fornecido: $2)."
                    echo ""
                    print_help
                    exit 1
                fi
                MAX_PARALLEL_JOBS="$2"
                shift 2
                ;;
            --services)
                if [[ $# -lt 2 ]]; then
                    log_error "A opção '$1' requer um argumento (ex: --services 'gateway-intencoes,consensus-engine')."
                    echo ""
                    print_help
                    exit 1
                fi
                SERVICES_FILTER="$2"
                shift 2
                ;;
            --env)
                if [[ $# -lt 2 ]]; then
                    log_error "A opção '$1' requer um argumento (ex: --env dev)."
                    echo ""
                    print_help
                    exit 1
                fi
                ENV="$2"
                shift 2
                ;;
            --region)
                if [[ $# -lt 2 ]]; then
                    log_error "A opção '$1' requer um argumento (ex: --region us-east-1)."
                    echo ""
                    print_help
                    exit 1
                fi
                AWS_REGION="$2"
                shift 2
                ;;
            --skip-build)
                SKIP_BUILD="true"
                shift
                ;;
            --skip-push)
                SKIP_PUSH="true"
                shift
                ;;
            --skip-update)
                SKIP_UPDATE="true"
                shift
                ;;
            --no-cache)
                NO_CACHE="true"
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --help)
                print_help
                exit 0
                ;;
            *)
                log_error "Flag desconhecida: $1"
                echo ""
                print_help
                exit 1
                ;;
        esac
    done
}

################################################################################
# Função de Cleanup
################################################################################

cleanup() {
    # Garantir que processos filhos sejam terminados em caso de interrupção
    local jobs_running=$(jobs -p)
    if [[ -n "${jobs_running}" ]]; then
        log_warning "Terminando processos filhos..."
        kill ${jobs_running} 2>/dev/null || true
    fi
}

################################################################################
# Função Principal
################################################################################

main() {
    # Banner inicial
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}     🚀 NEURAL HIVE MIND - BUILD E DEPLOY PARA EKS${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Exibir configuração
    log_info "Configuração:"
    log_info "  Versão: ${VERSION}"
    log_info "  Ambiente: ${ENV}"
    log_info "  Região AWS: ${AWS_REGION}"
    log_info "  Paralelismo: ${MAX_PARALLEL_JOBS}"
    echo ""
    log_info "Flags ativas:"
    [[ "${SKIP_BUILD}" == "true" ]] && log_info "  - Skip build"
    [[ "${SKIP_PUSH}" == "true" ]] && log_info "  - Skip push"
    [[ "${SKIP_UPDATE}" == "true" ]] && log_info "  - Skip update"
    [[ "${NO_CACHE}" == "true" ]] && log_info "  - No cache"
    [[ "${DRY_RUN}" == "true" ]] && log_info "  - Dry run"
    [[ -n "${SERVICES_FILTER}" ]] && log_info "  - Serviços filtrados: ${SERVICES_FILTER}"
    echo ""

    # Verificar pré-requisitos
    check_prerequisites

    # Registrar início
    TOTAL_START=$(date +%s)

    # Executar fases
    local continue_execution=true

    # Fase 1: Build
    if [[ "${SKIP_BUILD}" == "false" ]]; then
        if ! execute_build_phase; then
            if [[ -t 0 ]]; then
                echo ""
                read -p "$(echo -e ${YELLOW}Build falhou. Continuar com push/update? [y/N]: ${NC})" -n 1 -r
                echo ""
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    continue_execution=false
                fi
            else
                log_warning "Build falhou. Continuando (modo não-interativo)..."
            fi
        fi
    fi

    # Fase 2: Push
    if [[ "${continue_execution}" == "true" && "${SKIP_PUSH}" == "false" ]]; then
        if ! execute_push_phase; then
            if [[ -t 0 ]]; then
                echo ""
                read -p "$(echo -e ${YELLOW}Push falhou. Continuar com update? [y/N]: ${NC})" -n 1 -r
                echo ""
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    continue_execution=false
                fi
            else
                log_warning "Push falhou. Continuando (modo não-interativo)..."
            fi
        fi
    fi

    # Fase 3: Update
    if [[ "${continue_execution}" == "true" && "${SKIP_UPDATE}" == "false" ]]; then
        execute_update_phase || true
    fi

    # Resumo final
    print_final_summary

    # Exit code final
    local final_exit_code=0
    if [[ "${SKIP_BUILD}" == "false" && ${BUILD_EXIT_CODE} -ne 0 ]]; then
        final_exit_code=1
    fi
    if [[ "${SKIP_PUSH}" == "false" && ${PUSH_EXIT_CODE} -ne 0 ]]; then
        final_exit_code=1
    fi
    if [[ "${SKIP_UPDATE}" == "false" && ${UPDATE_EXIT_CODE} -ne 0 ]]; then
        final_exit_code=1
    fi

    exit ${final_exit_code}
}

################################################################################
# Entry Point
################################################################################

# Registrar handler de cleanup
trap cleanup EXIT INT TERM

# Parse argumentos e executar
parse_arguments "$@"
main
