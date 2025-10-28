#!/bin/bash

# Script de Deploy - Gateway de Intenções Neural Hive-Mind
# Deploy completo do Gateway de Intenções incluindo dependências

set -euo pipefail

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
NAMESPACE="gateway-intencoes"
CHART_PATH="$PROJECT_ROOT/helm-charts/gateway-intencoes"
VALUES_FILE="$CHART_PATH/values.yaml"

# Configurações de ambiente
ENVIRONMENT="${ENVIRONMENT:-prod}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_DEPS="${SKIP_DEPS:-false}"
TIMEOUT="${TIMEOUT:-600s}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Mostrar ajuda
show_help() {
    cat << EOF
Script de Deploy - Gateway de Intenções Neural Hive-Mind

Uso: $0 [OPÇÕES]

OPÇÕES:
    -e, --environment ENV     Ambiente (dev|staging|prod) [padrão: prod]
    -n, --namespace NS       Namespace para deploy [padrão: gateway-intencoes]
    -d, --dry-run            Executar dry-run (não aplica mudanças)
    -s, --skip-deps          Pular verificação de dependências
    -t, --timeout TIMEOUT   Timeout para operações [padrão: 600s]
    --image-tag TAG         Tag da imagem Docker [padrão: baseada no ambiente]
    -h, --help              Mostrar esta ajuda

VARIÁVEIS DE AMBIENTE:
    ENVIRONMENT             Ambiente de deploy (dev|staging|prod)
    DRY_RUN                Executar dry-run (true|false)
    SKIP_DEPS              Pular dependências (true|false)
    TIMEOUT                Timeout para operações

EXEMPLOS:
    # Deploy em produção
    $0 --environment prod

    # Dry-run em staging
    $0 --environment staging --dry-run

    # Deploy em dev pulando dependências
    $0 --environment dev --skip-deps

EOF
}

# Parse de argumentos
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -n|--namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --image-tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            -s|--skip-deps)
                SKIP_DEPS="true"
                shift
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -h|--help)
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

    # Validar ambiente
    if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
        log_error "Ambiente inválido: $ENVIRONMENT. Use: dev, staging ou prod"
        exit 1
    fi
}

# Verificar dependências
check_dependencies() {
    if [[ "$SKIP_DEPS" == "true" ]]; then
        log_info "Pulando verificação de dependências"
        return 0
    fi

    log_info "Verificando dependências..."

    # Verificar ferramentas
    local missing_tools=()

    command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl")
    command -v helm >/dev/null 2>&1 || missing_tools+=("helm")
    command -v docker >/dev/null 2>&1 || missing_tools+=("docker")

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Ferramentas não encontradas: ${missing_tools[*]}"
        exit 1
    fi

    # Verificar conectividade com cluster
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Não é possível conectar ao cluster Kubernetes"
        exit 1
    fi

    # Verificar se Helm chart existe
    if [[ ! -d "$CHART_PATH" ]]; then
        log_error "Helm chart não encontrado em: $CHART_PATH"
        exit 1
    fi

    log_success "Todas as dependências verificadas"
}

# Verificar dependências do cluster
check_cluster_dependencies() {
    log_info "Verificando dependências do cluster..."

    # Verificar namespaces necessários
    local required_namespaces=("redis-cluster" "neural-hive-kafka" "monitoring")

    for ns in "${required_namespaces[@]}"; do
        if ! kubectl get namespace "$ns" >/dev/null 2>&1; then
            log_warning "Namespace $ns não encontrado - pode causar problemas de conectividade"
        else
            log_info "✓ Namespace $ns encontrado"
        fi
    done

    # Verificar se Redis Cluster está rodando
    if kubectl get statefulset -n redis-cluster >/dev/null 2>&1; then
        local redis_ready=$(kubectl get statefulset -n redis-cluster -o jsonpath='{.items[0].status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$redis_ready" -gt 0 ]]; then
            log_success "✓ Redis Cluster está operacional ($redis_ready réplicas)"
        else
            log_warning "Redis Cluster pode não estar pronto"
        fi
    else
        log_warning "Redis Cluster não encontrado"
    fi

    # Verificar se Kafka está rodando
    if kubectl get deployment -n neural-hive-kafka >/dev/null 2>&1; then
        log_success "✓ Kafka namespace encontrado"
    else
        log_warning "Kafka pode não estar disponível"
    fi
}

# Criar namespace se não existir
create_namespace() {
    log_info "Verificando namespace $NAMESPACE..."

    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_info "Namespace $NAMESPACE já existe"
    else
        log_info "Criando namespace $NAMESPACE..."

        if [[ "$DRY_RUN" == "true" ]]; then
            echo "kubectl create namespace $NAMESPACE"
        else
            kubectl create namespace "$NAMESPACE"

            # Adicionar labels ao namespace
            kubectl label namespace "$NAMESPACE" \
                neural-hive-mind.org/component=gateway \
                neural-hive-mind.org/environment="$ENVIRONMENT" \
                --overwrite
        fi

        log_success "Namespace $NAMESPACE criado"
    fi
}

# Build da imagem Docker
build_docker_image() {
    log_info "Verificando imagem Docker..."

    local image_tag="neural-hive-mind/gateway-intencoes:1.0.0"
    local dockerfile_path="$PROJECT_ROOT/services/gateway-intencoes/Dockerfile"

    if [[ ! -f "$dockerfile_path" ]]; then
        log_error "Dockerfile não encontrado em: $dockerfile_path"
        exit 1
    fi

    # Verificar se imagem já existe
    if docker images | grep -q "neural-hive-mind/gateway-intencoes.*1.0.0"; then
        log_info "Imagem Docker já existe localmente"
        return 0
    fi

    log_info "Building imagem Docker: $image_tag..."

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "docker build -t $image_tag -f $PROJECT_ROOT/services/gateway-intencoes/Dockerfile $PROJECT_ROOT"
    else
        docker build -t "$image_tag" -f "$dockerfile_path" "$PROJECT_ROOT"
        log_success "Imagem Docker construída: $image_tag"
    fi
}

# Preparar values para o ambiente
prepare_values() {
    log_info "Preparando configurações para ambiente: $ENVIRONMENT..."

    local temp_values="/tmp/gateway-values-$ENVIRONMENT.yaml"

    # Copiar values base
    cp "$VALUES_FILE" "$temp_values"

    # Aplicar overrides específicos do ambiente
    case "$ENVIRONMENT" in
        dev)
            # Configurações para desenvolvimento
            yq eval '.replicaCount = 1' -i "$temp_values"
            yq eval '.config.logLevel = "DEBUG"' -i "$temp_values"
            yq eval '.config.debug = true' -i "$temp_values"
            yq eval '.resources.limits.cpu = "1000m"' -i "$temp_values"
            yq eval '.resources.limits.memory = "2Gi"' -i "$temp_values"
            yq eval '.resources.requests.cpu = "500m"' -i "$temp_values"
            yq eval '.resources.requests.memory = "1Gi"' -i "$temp_values"
            yq eval '.autoscaling.enabled = false' -i "$temp_values"
            ;;
        staging)
            # Configurações para staging
            yq eval '.replicaCount = 2' -i "$temp_values"
            yq eval '.config.logLevel = "INFO"' -i "$temp_values"
            yq eval '.config.debug = false' -i "$temp_values"
            ;;
        prod)
            # Configurações para produção (usar valores padrão)
            yq eval '.config.logLevel = "WARNING"' -i "$temp_values"
            yq eval '.config.debug = false' -i "$temp_values"
            ;;
    esac

    echo "$temp_values"
}

# Deploy com Helm
deploy_helm_chart() {
    log_info "Iniciando deploy do Gateway de Intenções..."

    local values_file
    values_file=$(prepare_values)

    local helm_args=(
        "upgrade" "--install"
        "gateway-intencoes"
        "$CHART_PATH"
        "--namespace" "$NAMESPACE"
        "--values" "$values_file"
        "--timeout" "$TIMEOUT"
        "--wait"
        "--create-namespace"
    )

    if [[ "$DRY_RUN" == "true" ]]; then
        helm_args+=("--dry-run")
        log_info "Executando Helm dry-run..."
    fi

    log_info "Executando: helm ${helm_args[*]}"

    if helm "${helm_args[@]}"; then
        log_success "Deploy do Helm completado com sucesso"
    else
        log_error "Falha no deploy do Helm"
        return 1
    fi

    # Limpar arquivo temporário
    rm -f "$values_file"
}

# Verificar status do deployment
check_deployment_status() {
    log_info "Verificando status do deployment..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Pulando verificação de status (dry-run)"
        return 0
    fi

    # Aguardar deployment ficar pronto
    log_info "Aguardando deployment ficar pronto..."

    if kubectl rollout status deployment/gateway-intencoes -n "$NAMESPACE" --timeout="$TIMEOUT"; then
        log_success "Deployment está pronto"
    else
        log_error "Timeout aguardando deployment ficar pronto"
        return 1
    fi

    # Verificar pods
    local ready_pods=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes --field-selector=status.phase=Running --no-headers | wc -l)
    local total_pods=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes --no-headers | wc -l)

    log_info "Status dos pods: $ready_pods/$total_pods prontos"

    if [[ "$ready_pods" -eq "$total_pods" && "$ready_pods" -gt 0 ]]; then
        log_success "Todos os pods estão prontos"
    else
        log_warning "Nem todos os pods estão prontos"

        # Mostrar logs dos pods com problema
        log_info "Logs dos pods com problema:"
        kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes --field-selector=status.phase!=Running --no-headers | while read -r pod_name _; do
            log_info "Logs do pod $pod_name:"
            kubectl logs -n "$NAMESPACE" "$pod_name" --tail=20 || true
        done
    fi
}

# Executar testes de conectividade
run_connectivity_tests() {
    log_info "Executando testes de conectividade..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Pulando testes de conectividade (dry-run)"
        return 0
    fi

    # Executar script de validação se disponível
    local validation_script="$PROJECT_ROOT/scripts/validation/validate-gateway-integration.sh"

    if [[ -f "$validation_script" ]]; then
        log_info "Executando validação de integração..."
        if bash "$validation_script"; then
            log_success "Validação de integração passou"
        else
            log_warning "Validação de integração falhou - verificar manualmente"
        fi
    else
        log_warning "Script de validação não encontrado: $validation_script"
    fi
}

# Mostrar informações do deployment
show_deployment_info() {
    log_info "Informações do deployment:"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Deploy seria realizado em: $NAMESPACE"
        log_info "Ambiente: $ENVIRONMENT"
        return 0
    fi

    echo
    echo "============================================"
    echo "        INFORMAÇÕES DO DEPLOYMENT"
    echo "============================================"
    echo "Namespace: $NAMESPACE"
    echo "Ambiente: $ENVIRONMENT"
    echo "Chart: $CHART_PATH"
    echo

    # Mostrar status dos recursos
    echo "Deployment:"
    kubectl get deployment -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes -o wide

    echo
    echo "Pods:"
    kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes -o wide

    echo
    echo "Services:"
    kubectl get services -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes

    echo
    echo "Para acessar os logs:"
    echo "kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=gateway-intencoes -f"

    echo
    echo "Para fazer port-forward:"
    echo "kubectl port-forward -n $NAMESPACE svc/gateway-intencoes 8080:80"
    echo
}

# Função principal
main() {
    echo "=================================================="
    echo "     Deploy - Gateway de Intenções Neural Hive-Mind"
    echo "=================================================="
    echo

    # Parse argumentos
    parse_args "$@"

    log_info "Iniciando deploy do Gateway de Intenções"
    log_info "Ambiente: $ENVIRONMENT"
    log_info "Dry-run: $DRY_RUN"
    log_info "Namespace: $NAMESPACE"
    echo

    # Executar verificações e deploy
    check_dependencies
    echo

    check_cluster_dependencies
    echo

    create_namespace
    echo

    build_docker_image
    echo

    deploy_helm_chart
    echo

    check_deployment_status
    echo

    run_connectivity_tests
    echo

    show_deployment_info

    # Status final
    if [[ "$DRY_RUN" == "true" ]]; then
        log_success "✅ Dry-run completado com sucesso!"
        log_info "Execute sem --dry-run para aplicar as mudanças"
    else
        log_success "✅ Deploy do Gateway de Intenções completado com sucesso!"
        log_info "Gateway está disponível no namespace $NAMESPACE"
    fi
}

# Executar apenas se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi