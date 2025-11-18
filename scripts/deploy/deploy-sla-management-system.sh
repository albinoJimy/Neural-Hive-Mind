#!/bin/bash
set -e

# SLA Management System Deployment Script
# Automatiza a instalação completa do SLA Management System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NAMESPACE="neural-hive-monitoring"
HELM_CHART_DIR="$PROJECT_ROOT/helm-charts/sla-management-system"
VALUES_FILE="$HELM_CHART_DIR/values.yaml"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funções auxiliares
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Argumentos
DRY_RUN=false
SKIP_CRDS=false
CUSTOM_VALUES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-crds)
            SKIP_CRDS=true
            shift
            ;;
        --values)
            CUSTOM_VALUES="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --help)
            echo "Uso: $0 [opções]"
            echo ""
            echo "Opções:"
            echo "  --dry-run           Mostra o que seria feito sem aplicar"
            echo "  --skip-crds         Pula instalação de CRDs (se já instalados)"
            echo "  --values <file>     Usa arquivo values customizado"
            echo "  --namespace <ns>    Deploy em namespace específico (default: neural-hive-monitoring)"
            echo "  --help              Mostra esta mensagem"
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            exit 1
            ;;
    esac
done

log_info "========================================"
log_info "SLA Management System - Deploy"
log_info "========================================"

# 1. Verificar pré-requisitos
log_info "Verificando pré-requisitos..."

if ! command -v kubectl &> /dev/null; then
    log_error "kubectl não encontrado. Instale kubectl primeiro."
    exit 1
fi

if ! command -v helm &> /dev/null; then
    log_error "helm não encontrado. Instale helm 3 primeiro."
    exit 1
fi

# Verificar conectividade do cluster
if ! kubectl cluster-info &> /dev/null; then
    log_error "Não foi possível conectar ao cluster Kubernetes."
    exit 1
fi

log_info "✓ kubectl e helm encontrados"
log_info "✓ Cluster Kubernetes acessível"

# 2. Verificar namespaces necessários
log_info "Verificando namespaces necessários..."

REQUIRED_NAMESPACES=("kafka" "monitoring" "neural-hive-data" "redis-cluster")
for ns in "${REQUIRED_NAMESPACES[@]}"; do
    if ! kubectl get namespace "$ns" &> /dev/null; then
        log_warn "Namespace $ns não encontrado. Alguns recursos podem não funcionar."
    else
        log_info "✓ Namespace $ns encontrado"
    fi
done

# 3. Verificar dependências (PostgreSQL, Redis, Kafka, Prometheus)
log_info "Verificando serviços dependentes..."

check_service() {
    local service=$1
    local namespace=$2
    if kubectl get svc "$service" -n "$namespace" &> /dev/null; then
        log_info "✓ $service encontrado em $namespace"
        return 0
    else
        log_warn "$service não encontrado em $namespace"
        return 1
    fi
}

check_service "kafka-bootstrap" "kafka" || log_warn "Kafka pode não estar disponível"
check_service "prometheus-server" "monitoring" || log_warn "Prometheus pode não estar disponível"
check_service "redis-cluster" "redis-cluster" || log_warn "Redis pode não estar disponível"

# 4. Instalar CRDs
if [ "$SKIP_CRDS" = false ]; then
    log_info "Instalando CRDs..."

    CRD_FILES=(
        "$PROJECT_ROOT/k8s/crds/slodefinition-crd.yaml"
        "$PROJECT_ROOT/k8s/crds/slapolicy-crd.yaml"
    )

    for crd_file in "${CRD_FILES[@]}"; do
        if [ ! -f "$crd_file" ]; then
            log_error "CRD file não encontrado: $crd_file"
            exit 1
        fi

        if [ "$DRY_RUN" = true ]; then
            log_info "[DRY-RUN] Aplicaria: $crd_file"
        else
            kubectl apply -f "$crd_file"
            log_info "✓ CRD aplicado: $(basename $crd_file)"
        fi
    done

    if [ "$DRY_RUN" = false ]; then
        log_info "Aguardando CRDs serem estabelecidos..."
        kubectl wait --for condition=established --timeout=60s crd/slodefinitions.neural-hive.io
        kubectl wait --for condition=established --timeout=60s crd/slapolicies.neural-hive.io
        log_info "✓ CRDs estabelecidos"
    fi
else
    log_info "Pulando instalação de CRDs (--skip-crds)"
fi

# 5. Criar tópicos Kafka
log_info "Criando tópicos Kafka..."

KAFKA_TOPICS_FILE="$PROJECT_ROOT/k8s/kafka-topics/sla-topics.yaml"
if [ -f "$KAFKA_TOPICS_FILE" ]; then
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Aplicaria: $KAFKA_TOPICS_FILE"
    else
        kubectl apply -f "$KAFKA_TOPICS_FILE" || log_warn "Falha ao criar tópicos Kafka (pode já existir)"
        log_info "✓ Tópicos Kafka criados/atualizados"
    fi
else
    log_warn "Arquivo de tópicos Kafka não encontrado: $KAFKA_TOPICS_FILE"
fi

# 6. Criar namespace
log_info "Criando namespace $NAMESPACE..."

if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] Criaria namespace: $NAMESPACE"
else
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    log_info "✓ Namespace $NAMESPACE criado/verificado"
fi

# 7. Instalar Helm chart
log_info "Instalando Helm chart..."

HELM_CMD="helm upgrade --install sla-management-system"
HELM_CMD="$HELM_CMD $HELM_CHART_DIR"
HELM_CMD="$HELM_CMD --namespace $NAMESPACE"

if [ -n "$CUSTOM_VALUES" ]; then
    HELM_CMD="$HELM_CMD --values $CUSTOM_VALUES"
else
    HELM_CMD="$HELM_CMD --values $VALUES_FILE"
fi

HELM_CMD="$HELM_CMD --wait --timeout 10m"

if [ "$DRY_RUN" = true ]; then
    HELM_CMD="$HELM_CMD --dry-run --debug"
fi

log_info "Executando: $HELM_CMD"
eval $HELM_CMD

if [ "$DRY_RUN" = false ]; then
    log_info "✓ Helm chart instalado"
fi

# 8. Verificação (apenas se não for dry-run)
if [ "$DRY_RUN" = false ]; then
    log_info "Verificando deployment..."

    # Aguardar deployment estar pronto
    kubectl rollout status deployment/sla-management-system -n "$NAMESPACE" --timeout=5m
    log_info "✓ API Server deployment pronto"

    # Verificar operator (se habilitado)
    if kubectl get deployment sla-management-system-operator -n "$NAMESPACE" &> /dev/null; then
        kubectl rollout status deployment/sla-management-system-operator -n "$NAMESPACE" --timeout=5m
        log_info "✓ Operator deployment pronto"
    fi

    # Verificar pods
    log_info "Pods em execução:"
    kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=sla-management-system

    # Verificar serviço
    log_info "Serviços criados:"
    kubectl get svc -n "$NAMESPACE" sla-management-system

    # Testar health endpoint
    log_info "Testando health endpoint..."
    if kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
        curl -f http://sla-management-system.$NAMESPACE.svc.cluster.local:8000/health &> /dev/null; then
        log_info "✓ Health endpoint respondendo"
    else
        log_warn "Health endpoint não respondeu (pode levar alguns segundos para ficar pronto)"
    fi
fi

# 9. Mostrar próximos passos
log_info ""
log_info "========================================"
log_info "Deployment Completo!"
log_info "========================================"
log_info ""
log_info "Próximos passos:"
log_info ""
log_info "1. Verificar status:"
log_info "   kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=sla-management-system"
log_info ""
log_info "2. Ver logs:"
log_info "   kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=sla-management-system -f"
log_info ""
log_info "3. Acessar API:"
log_info "   kubectl port-forward -n $NAMESPACE svc/sla-management-system 8000:8000"
log_info "   curl http://localhost:8000/health"
log_info ""
log_info "4. Criar SLO exemplo:"
log_info "   kubectl apply -f $PROJECT_ROOT/examples/sla-management-system/example-slo-latency.yaml"
log_info ""
log_info "5. Executar validação:"
log_info "   $PROJECT_ROOT/scripts/validation/validate-sla-management-system.sh"
log_info ""
log_info "Documentação: $PROJECT_ROOT/services/sla-management-system/DEPLOYMENT_GUIDE.md"
log_info ""
