#!/bin/bash
# FASE 0 - Deploy Staging Script
# Uso: ./deploy-staging.sh [--activate-features]

set -e

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configurações
NAMESPACE_APPROVAL="approval"
NAMESPACE_ORCHESTRATOR="neural-hive-orchestration"
DEPLOYMENT_APPROVAL="approval-service"
DEPLOYMENT_ORCHESTRATOR="orchestrator-dynamic"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Fase 1: Verificar pré-requisitos
check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não conectado ao cluster Kubernetes"
        exit 1
    fi

    log_info "Pré-requisitos OK"
}

# Fase 2: Deploy com features OFF
deploy_baseline() {
    log_info "=== FASE 1: Deploy Baseline (Features OFF) ==="

    log_info "Aplicando approval-service deployment..."
    kubectl apply -f k8s/approval-service-deployment.yaml

    log_info "Aplicando orchestrator-dynamic deployment..."
    kubectl apply -f k8s/orchestrator-dynamic-deployment.yaml

    log_info "Aguardando rollout..."
    kubectl rollout status deployment/$DEPLOYMENT_APPROVAL -n $NAMESPACE_APPROVAL --timeout=5m
    kubectl rollout status deployment/$DEPLOYMENT_ORCHESTRATOR -n $NAMESPACE_ORCHESTRATOR --timeout=5m

    log_info "Verificando pods..."
    kubectl get pods -n $NAMESPACE_APPROVAL -l app=$DEPLOYMENT_APPROVAL
    kubectl get pods -n $NAMESPACE_ORCHESTRATOR -l app=$DEPLOYMENT_ORCHESTRATOR

    log_info "=== BASELINE DEPLOYED ==="
    log_warn "Aguardar 24h para coletar baseline de métricas"
}

# Fase 3: Coletar baseline
collect_baseline() {
    log_info "=== Coletando Baseline ==="

    log_info "Métricas atuais:"
    echo "Taxa de aprovação:"
    kubectl exec -n $NAMESPACE_APPROVAL -c approval-service -- \
        curl -s localhost:8004/metrics | grep approval_service_approvals_total || echo "N/A"

    echo "Latência:"
    kubectl exec -n $NAMESPACE_APPROVAL -c approval-service -- \
        curl -s localhost:8004/metrics | grep prediction_duration_seconds || echo "N/A"

    echo "Drift score:"
    kubectl exec -n $NAMESPACE_ORCHESTRATOR -c orchestrator-dynamic -- \
        curl -s localhost:8003/metrics | grep drift_score || echo "N/A"

    log_info "Dashboard Grafana:"
    echo "  ML Model Health: http://grafana.neural-hive.local/d/ml_model_health"
    echo "  Data Drift: http://grafana.neural-hive.local/d/ml_data_drift"
}

# Fase 4: Ativar features profissionais
activate_features() {
    log_info "=== FASE 2: Ativando Features Profissionais ==="

    log_info "Ativando USE_PROFESSIONAL_FEATURES..."
    kubectl patch configmap approval-service-config -n $NAMESPACE_APPROVAL --type=json \
      -p='[{"op": "replace", "path": "/data/USE_PROFESSIONAL_FEATURES", "value": "true"}]'

    log_info "Ativando ML_AUTO_RETRAIN_ENABLED (opcional)..."
    kubectl patch configmap orchestrator-dynamic-config -n $NAMESPACE_ORCHESTRATOR --type=json \
      -p='[{"op": "replace", "path": "/data/ML_AUTO_RETRAIN_ENABLED", "value": "true"}]' || true

    log_info "Restartando pods..."
    kubectl rollout restart deployment/$DEPLOYMENT_APPROVAL -n $NAMESPACE_APPROVAL
    kubectl rollout restart deployment/$DEPLOYMENT_ORCHESTRATOR -n $NAMESPACE_ORCHESTRATOR

    log_info "Aguardando rollout..."
    kubectl rollout status deployment/$DEPLOYMENT_APPROVAL -n $NAMESPACE_APPROVAL --timeout=5m
    kubectl rollout status deployment/$DEPLOYMENT_ORCHESTRATOR -n $NAMESPACE_ORCHESTRATOR --timeout=5m

    log_info "Verificando logs..."
    kubectl logs -n $NAMESPACE_APPROVAL -l app=$DEPLOYMENT_APPROVAL --tail=20 | grep -i "professional.*features\|nlp.*features" || true
    kubectl logs -n $NAMESPACE_ORCHESTRATOR -l app=$DEPLOYMENT_ORCHESTRATOR --tail=20 | grep -i "auto.*retrain\|drift" || true

    log_info "=== FEATURES ATIVADAS ==="
    log_warn "Monitorar por 24-48h"
}

# Fase 5: Monitoramento
monitor_metrics() {
    log_info "=== Monitoramento ==="

    log_info "Métricas pós-ativação:"
    echo "Taxa de aprovação:"
    kubectl exec -n $NAMESPACE_APPROVAL -c approval-service -- \
        curl -s localhost:8004/metrics | grep approval_service_approvals_total || echo "N/A"

    echo "Latência:"
    kubectl exec -n $NAMESPACE_APPROVAL -c approval-service -- \
        curl -s localhost:8004/metrics | grep prediction_duration_seconds || echo "N/A"
}

# Fase 6: Rollback (se necessário)
rollback_features() {
    log_info "=== ROLLBACK ==="

    log_info "Desativando USE_PROFESSIONAL_FEATURES..."
    kubectl patch configmap approval-service-config -n $NAMESPACE_APPROVAL --type=json \
      -p='[{"op": "replace", "path": "/data/USE_PROFESSIONAL_FEATURES", "value": "false"}]'

    log_info "Desativando ML_AUTO_RETRAIN_ENABLED..."
    kubectl patch configmap orchestrator-dynamic-config -n $NAMESPACE_ORCHESTRATOR --type=json \
      -p='[{"op": "replace", "path": "/data/ML_AUTO_RETRAIN_ENABLED", "value": "false"}]' || true

    log_info "Restartando pods..."
    kubectl rollout restart deployment/$DEPLOYMENT_APPROVAL -n $NAMESPACE_APPROVAL
    kubectl rollout restart deployment/$DEPLOYMENT_ORCHESTRATOR -n $NAMESPACE_ORCHESTRATOR

    log_info "=== ROLLBACK COMPLETO ==="
}

# Main
main() {
    case "${1:-}" in
        --activate-features)
            check_prerequisites
            activate_features
            monitor_metrics
            ;;
        --rollback)
            check_prerequisites
            rollback_features
            ;;
        --collect-baseline)
            check_prerequisites
            collect_baseline
            ;;
        --monitor)
            check_prerequisites
            monitor_metrics
            ;;
        *)
            check_prerequisites
            deploy_baseline
            collect_baseline
            log_warn "Próximo passo: ./deploy-staging.sh --activate-features (após 24h)"
            ;;
    esac
}

main "$@"
