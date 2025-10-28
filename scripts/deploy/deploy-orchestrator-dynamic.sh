#!/bin/bash
set -euo pipefail

# Script de deploy do Orchestrator Dynamic
# Implementa o deploy completo do serviço conforme Fase 2.1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Configurações
NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
HELM_CHART_PATH="${PROJECT_ROOT}/helm-charts/orchestrator-dynamic"
VALUES_FILE="${HELM_CHART_PATH}/values.yaml"
RELEASE_NAME="orchestrator-dynamic"
ENVIRONMENT="${ENVIRONMENT:-development}"
VERSION="${VERSION:-1.0.0}"
REGISTRY="${REGISTRY:-localhost:5000}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando prerequisites..."

    # Verificar ferramentas instaladas
    command -v kubectl >/dev/null 2>&1 || { log_error "kubectl não instalado"; exit 1; }
    command -v helm >/dev/null 2>&1 || { log_error "helm não instalado"; exit 1; }
    command -v docker >/dev/null 2>&1 || { log_error "docker não instalado"; exit 1; }

    # Verificar conexão com cluster
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi

    # Verificar/criar namespace
    if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
        log_info "Criando namespace ${NAMESPACE}..."
        kubectl create namespace "${NAMESPACE}"
    fi

    # Verificar dependências
    log_info "Verificando dependências..."

    # Temporal Server
    if ! kubectl get service -n temporal temporal-frontend >/dev/null 2>&1; then
        log_warn "Temporal Server não encontrado. Por favor, provisione primeiro."
        read -p "Deseja continuar mesmo assim? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Kafka
    if ! kubectl get pods -n kafka | grep -q kafka; then
        log_warn "Kafka não encontrado. Por favor, provisione primeiro."
        exit 1
    fi

    # MongoDB
    if ! kubectl get pods -n mongodb-cluster | grep -q mongodb; then
        log_warn "MongoDB não encontrado. Por favor, provisione primeiro."
    fi

    # Verificar tópicos Kafka
    log_info "Verificando tópicos Kafka..."
    REQUIRED_TOPICS=("plans.consensus" "execution.tickets" "orchestration.incidents" "telemetry.orchestration")
    for topic in "${REQUIRED_TOPICS[@]}"; do
        if ! kubectl get kafkatopic -n kafka "${topic}" >/dev/null 2>&1; then
            log_warn "Tópico ${topic} não encontrado"
        fi
    done

    log_info "Prerequisites OK"
}

build_and_push_image() {
    log_info "Building imagem Docker..."

    cd "${PROJECT_ROOT}/services/orchestrator-dynamic"

    # Build
    docker build -t "${REGISTRY}/orchestrator-dynamic:${VERSION}" \
        --label "git.commit=$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        --label "build.date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        .

    log_info "Imagem construída: ${REGISTRY}/orchestrator-dynamic:${VERSION}"

    # Push
    if [ "${ENVIRONMENT}" != "development" ]; then
        log_info "Pushing imagem para registry..."
        docker push "${REGISTRY}/orchestrator-dynamic:${VERSION}"
        log_info "Imagem pushed com sucesso"

        # Scan vulnerabilidades (se trivy instalado)
        if command -v trivy >/dev/null 2>&1; then
            log_info "Scanning imagem com Trivy..."
            trivy image "${REGISTRY}/orchestrator-dynamic:${VERSION}"
        fi
    else
        log_info "Ambiente development, skip push para registry"
    fi

    cd "${PROJECT_ROOT}"
}

create_secrets() {
    log_info "Criando Kubernetes Secrets..."

    # Verificar se secrets já existem
    if kubectl get secret orchestrator-secrets -n "${NAMESPACE}" >/dev/null 2>&1; then
        log_warn "Secret orchestrator-secrets já existe"
        read -p "Deseja recriar? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kubectl delete secret orchestrator-secrets -n "${NAMESPACE}"
        else
            log_info "Mantendo secret existente"
            return
        fi
    fi

    # Solicitar credenciais
    read -s -p "PostgreSQL password: " POSTGRES_PASSWORD
    echo
    read -s -p "MongoDB URI: " MONGODB_URI
    echo
    read -s -p "Redis password (deixe vazio se não aplicável): " REDIS_PASSWORD
    echo

    # Criar secret
    kubectl create secret generic orchestrator-secrets \
        --from-literal=postgres-user=temporal \
        --from-literal=postgres-password="${POSTGRES_PASSWORD}" \
        --from-literal=mongodb-uri="${MONGODB_URI}" \
        --from-literal=redis-password="${REDIS_PASSWORD}" \
        -n "${NAMESPACE}"

    log_info "Secrets criados com sucesso"
}

deploy_helm_chart() {
    log_info "Deploying Helm chart..."

    cd "${HELM_CHART_PATH}"

    # Lint chart
    log_info "Validando chart..."
    helm lint .

    # Deploy
    helm upgrade --install "${RELEASE_NAME}" . \
        --namespace "${NAMESPACE}" \
        --values "${VALUES_FILE}" \
        --set image.repository="${REGISTRY}/orchestrator-dynamic" \
        --set image.tag="${VERSION}" \
        --set config.environment="${ENVIRONMENT}" \
        --wait \
        --timeout 10m

    log_info "Helm chart deployed com sucesso"

    # Verificar status
    kubectl rollout status deployment/"${RELEASE_NAME}" -n "${NAMESPACE}"

    cd "${PROJECT_ROOT}"
}

run_smoke_tests() {
    log_info "Executando smoke tests..."

    # Aguardar pods estarem ready
    log_info "Aguardando pods ficarem ready..."
    kubectl wait --for=condition=ready pod \
        -l app.kubernetes.io/name=orchestrator-dynamic \
        -n "${NAMESPACE}" \
        --timeout=300s

    # Get pod name
    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')

    # Test health endpoint
    log_info "Testando health endpoint..."
    kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -f http://localhost:8000/health

    # Test readiness endpoint
    log_info "Testando readiness endpoint..."
    kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -f http://localhost:8000/ready

    # Test metrics endpoint
    log_info "Testando metrics endpoint..."
    kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -f http://localhost:9090/metrics | grep -q orchestration_

    # Verificar logs
    log_info "Verificando logs..."
    kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name=orchestrator-dynamic --tail=50

    log_info "Smoke tests concluídos com sucesso"
}

main() {
    log_info "===== Deploy Orchestrator Dynamic ====="
    log_info "Namespace: ${NAMESPACE}"
    log_info "Environment: ${ENVIRONMENT}"
    log_info "Version: ${VERSION}"
    log_info "========================================"

    check_prerequisites
    build_and_push_image
    create_secrets
    deploy_helm_chart
    run_smoke_tests

    log_info ""
    log_info "===== Deploy Concluído com Sucesso! ====="
    log_info ""
    log_info "Próximos passos:"
    log_info "1. Verificar deployment: kubectl get pods -n ${NAMESPACE}"
    log_info "2. Ver logs: kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=orchestrator-dynamic -f"
    log_info "3. Port-forward (dev): kubectl port-forward -n ${NAMESPACE} svc/orchestrator-dynamic 8000:8000"
    log_info "4. Executar validação completa: ./scripts/validation/validate-orchestrator-dynamic.sh"
    log_info "5. Executar teste end-to-end: ./tests/phase2-orchestrator-test.sh"
    log_info ""
}

main "$@"
