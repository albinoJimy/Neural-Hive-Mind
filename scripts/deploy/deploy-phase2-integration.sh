#!/usr/bin/env bash
#
# Deploy Phase 2 Flow C Integration
#
# Este script automatiza o deployment completo da integração Flow C (Fase 2):
# - Valida prerequisites (kubectl, helm, contexto k8s)
# - Aplica recursos Kafka (topics)
# - Constrói e instala a biblioteca neural_hive_integration
# - Deploya serviços: orchestrator-dynamic, service-registry, execution-ticket-service, worker-agents, code-forge
# - Aplica dashboard Grafana e alertas Prometheus
# - Executa smoke checks e validações básicas
#

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variáveis
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SKIP_BUILD=false
DRY_RUN=false
VERBOSE=false
NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Tratamento de sinais para rollback
cleanup() {
    if [ "${FAILED:-false}" = "true" ]; then
        log_error "Deployment falhou. Executando rollback..."
        rollback_deployment
    fi
}

trap cleanup EXIT

# Rollback em caso de falha
rollback_deployment() {
    log_warn "Rollback não implementado completamente. Verifique manualmente os recursos."
    # TODO: Implementar rollback de helm releases e recursos k8s
}

# Parse argumentos
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                set -x
                shift
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            -h|--help)
                cat <<EOF
Uso: $0 [OPTIONS]

Opções:
  --skip-build       Pula etapa de build de imagens Docker
  --dry-run          Executa em modo dry-run (sem aplicar mudanças)
  --verbose          Ativa modo verbose (set -x)
  --namespace NS     Define namespace k8s (default: neural-hive-orchestration)
  -h, --help         Exibe esta mensagem

Exemplos:
  $0                           # Deploy completo
  $0 --skip-build              # Deploy sem rebuild
  $0 --dry-run --verbose       # Dry-run com output verbose
EOF
                exit 0
                ;;
            *)
                log_error "Argumento desconhecido: $1"
                exit 1
                ;;
        esac
    done
}

# Validar prerequisites
validate_prerequisites() {
    log_info "Validando prerequisites..."

    # kubectl
    if ! command -v kubectl &>/dev/null; then
        log_error "kubectl não encontrado. Instale: https://kubernetes.io/docs/tasks/tools/"
        exit 1
    fi
    log_success "kubectl encontrado: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

    # helm
    if ! command -v helm &>/dev/null; then
        log_error "helm não encontrado. Instale: https://helm.sh/docs/intro/install/"
        exit 1
    fi
    log_success "helm encontrado: $(helm version --short)"

    # Contexto k8s
    local context
    context=$(kubectl config current-context 2>/dev/null || echo "")
    if [ -z "$context" ]; then
        log_error "Nenhum contexto k8s configurado. Configure com: kubectl config use-context <context>"
        exit 1
    fi
    log_success "Contexto k8s: $context"

    # Verificar namespace
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        log_warn "Namespace $NAMESPACE não existe. Criando..."
        if [ "$DRY_RUN" = false ]; then
            kubectl create namespace "$NAMESPACE"
        fi
    fi
    log_success "Namespace: $NAMESPACE"

    # Verificar Kafka (Strimzi)
    if ! kubectl get kafka -n "$NAMESPACE" &>/dev/null; then
        log_warn "Kafka CRD (Strimzi) não encontrado. Certifique-se de que Strimzi está instalado."
    else
        log_success "Kafka (Strimzi) disponível"
    fi

    # Verificar MongoDB
    if ! kubectl get pods -n "$NAMESPACE" -l app=mongodb &>/dev/null; then
        log_warn "MongoDB não encontrado no namespace. Certifique-se de que está rodando."
    fi

    # Verificar Redis
    if ! kubectl get pods -n "$NAMESPACE" -l app=redis &>/dev/null; then
        log_warn "Redis não encontrado no namespace. Certifique-se de que está rodando."
    fi

    # Verificar Temporal
    if ! kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=temporal &>/dev/null; then
        log_warn "Temporal não encontrado no namespace. Certifique-se de que está rodando."
    fi

    log_success "Prerequisites validados"
}

# Aplicar Kafka topics
apply_kafka_topics() {
    log_info "Aplicando Kafka topics..."

    local topics=(
        "k8s/kafka-topics/telemetry-flow-c-topic.yaml"
        "k8s/kafka-topics/plans-consensus-topic.yaml"
        "k8s/kafka-topics/execution-tickets-topic.yaml"
    )

    for topic_file in "${topics[@]}"; do
        local full_path="$PROJECT_ROOT/$topic_file"
        if [ -f "$full_path" ]; then
            log_info "Aplicando: $topic_file"
            if [ "$DRY_RUN" = false ]; then
                kubectl apply -f "$full_path" -n "$NAMESPACE"
            else
                kubectl apply -f "$full_path" -n "$NAMESPACE" --dry-run=client
            fi
        else
            log_warn "Arquivo não encontrado: $topic_file (pulando)"
        fi
    done

    log_success "Kafka topics aplicados"
}

# Build e install biblioteca neural_hive_integration
build_integration_library() {
    if [ "$SKIP_BUILD" = true ]; then
        log_info "Pulando build da biblioteca (--skip-build)"
        return
    fi

    log_info "Construindo biblioteca neural_hive_integration..."

    local lib_dir="$PROJECT_ROOT/libraries/neural_hive_integration"
    if [ ! -d "$lib_dir" ]; then
        log_error "Biblioteca não encontrada em: $lib_dir"
        exit 1
    fi

    cd "$lib_dir"

    # Install em modo editable para desenvolvimento (ou wheel para produção)
    if [ "$DRY_RUN" = false ]; then
        log_info "Instalando biblioteca em modo editable..."
        pip install -e . || {
            log_error "Falha ao instalar biblioteca"
            exit 1
        }
    else
        log_info "[DRY-RUN] pip install -e ."
    fi

    cd "$PROJECT_ROOT"
    log_success "Biblioteca neural_hive_integration pronta"
}

# Deploy serviços via Helm ou manifests
deploy_services() {
    log_info "Deployando serviços Flow C..."

    local services=(
        "orchestrator-dynamic"
        "service-registry"
        "execution-ticket-service"
        "worker-agents"
        "code-forge"
    )

    for service in "${services[@]}"; do
        log_info "Deployando: $service"

        # Verificar se existe Helm chart
        local helm_chart="$PROJECT_ROOT/k8s/helm/$service"
        if [ -d "$helm_chart" ]; then
            log_info "Usando Helm chart: $helm_chart"
            if [ "$DRY_RUN" = false ]; then
                helm upgrade --install "$service" "$helm_chart" \
                    --namespace "$NAMESPACE" \
                    --create-namespace \
                    --wait --timeout 5m || {
                    log_error "Falha no deploy de $service via Helm"
                    FAILED=true
                    exit 1
                }
            else
                helm upgrade --install "$service" "$helm_chart" \
                    --namespace "$NAMESPACE" \
                    --dry-run
            fi
        else
            # Fallback para manifests diretos
            local manifest="$PROJECT_ROOT/k8s/$service.yaml"
            if [ -f "$manifest" ]; then
                log_info "Usando manifest: $manifest"
                if [ "$DRY_RUN" = false ]; then
                    kubectl apply -f "$manifest" -n "$NAMESPACE" || {
                        log_error "Falha no deploy de $service via manifest"
                        FAILED=true
                        exit 1
                    }
                else
                    kubectl apply -f "$manifest" -n "$NAMESPACE" --dry-run=client
                fi
            else
                log_warn "Nem Helm chart nem manifest encontrado para $service (pulando)"
            fi
        fi
    done

    log_success "Serviços deployados"
}

# Aplicar Grafana dashboard e alertas Prometheus
apply_monitoring() {
    log_info "Aplicando monitoring (Grafana dashboard + Prometheus alerts)..."

    # Dashboard Grafana
    local dashboard="$PROJECT_ROOT/monitoring/dashboards/fluxo-c-orquestracao.json"
    if [ -f "$dashboard" ]; then
        log_info "Aplicando Grafana dashboard: $dashboard"
        if [ "$DRY_RUN" = false ]; then
            # Criar ConfigMap com dashboard
            kubectl create configmap grafana-dashboard-flow-c \
                --from-file="$dashboard" \
                -n "$NAMESPACE" \
                --dry-run=client -o yaml | kubectl apply -f - -n "$NAMESPACE"
        else
            log_info "[DRY-RUN] kubectl create configmap grafana-dashboard-flow-c"
        fi
    else
        log_warn "Dashboard Grafana não encontrado: $dashboard"
    fi

    # Alertas Prometheus
    local alerts="$PROJECT_ROOT/monitoring/alerts/flow-c-integration-alerts.yaml"
    if [ -f "$alerts" ]; then
        log_info "Aplicando Prometheus alerts: $alerts"
        if [ "$DRY_RUN" = false ]; then
            kubectl apply -f "$alerts" -n "$NAMESPACE" || {
                log_warn "Falha ao aplicar alertas Prometheus (continuando)"
            }
        else
            kubectl apply -f "$alerts" -n "$NAMESPACE" --dry-run=client
        fi
    else
        log_warn "Alertas Prometheus não encontrados: $alerts"
    fi

    log_success "Monitoring configurado"
}

# Smoke checks
smoke_checks() {
    log_info "Executando smoke checks..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Pulando smoke checks"
        return
    fi

    # Aguardar pods ficarem ready
    log_info "Aguardando pods ficarem ready..."
    kubectl wait --for=condition=ready pod \
        -l app.kubernetes.io/part-of=neural-hive-flow-c \
        -n "$NAMESPACE" \
        --timeout=5m || log_warn "Alguns pods não ficaram ready em 5min"

    # Verificar health endpoints
    local services=(
        "orchestrator-dynamic"
        "service-registry"
        "execution-ticket-service"
        "code-forge"
    )

    for service in "${services[@]}"; do
        log_info "Verificando health de $service..."
        local pod
        pod=$(kubectl get pods -n "$NAMESPACE" -l app="$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [ -n "$pod" ]; then
            # Port-forward e curl
            kubectl port-forward -n "$NAMESPACE" "pod/$pod" 8080:8080 &
            local pf_pid=$!
            sleep 2
            if curl -f http://localhost:8080/health &>/dev/null || curl -f http://localhost:8080/healthz &>/dev/null; then
                log_success "$service health OK"
            else
                log_warn "$service health check falhou"
            fi
            kill $pf_pid 2>/dev/null || true
        else
            log_warn "Pod não encontrado para $service"
        fi
    done

    log_success "Smoke checks concluídos"
}

# Main
main() {
    parse_args "$@"

    log_info "=== Deploy Phase 2 Flow C Integration ==="
    log_info "Namespace: $NAMESPACE"
    log_info "Dry-run: $DRY_RUN"
    log_info "Skip build: $SKIP_BUILD"
    echo

    validate_prerequisites
    apply_kafka_topics
    build_integration_library
    deploy_services
    apply_monitoring
    smoke_checks

    log_success "=== Deploy Phase 2 Flow C Integration COMPLETO ==="
    log_info "Execute './scripts/validation/validate-phase2-integration.sh' para validação completa"
}

main "$@"
