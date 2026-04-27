#!/bin/bash
# FASE 0 - Pre-Deploy Validation Script
# Valida todos os componentes localmente antes do deploy

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

echo "======================================"
echo "FASE 0 - Pre-Deploy Validation"
echo "======================================"
echo ""

# 1. Validar arquivos de código
echo "1. Validando arquivos de código..."

FILES_TO_CHECK=(
    "ml_pipelines/inference/feature_adapter.py"
    "ml_pipelines/inference/approval_predictor.py"
    "ml_pipelines/deployment/model_promotion.py"
    "services/orchestrator-dynamic/src/consumers/decision_consumer.py"
    "libraries/python/neural_hive_llm/neural_hive_llm/client.py"
)

for file in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$file" ]; then
        log_info "$file existe"
    else
        log_error "$file NÃO encontrado"
        exit 1
    fi
done
echo ""

# 2. Validar arquivos K8s
echo "2. Validando arquivos Kubernetes..."

K8S_FILES=(
    "k8s/approval-service-deployment.yaml"
    "k8s/orchestrator-dynamic-deployment.yaml"
)

for file in "${K8S_FILES[@]}"; do
    if [ -f "$file" ]; then
        # Verificar feature flags
        if grep -q "USE_PROFESSIONAL_FEATURES" "$file"; then
            log_info "$file tem USE_PROFESSIONAL_FEATURES"
        else
            log_error "$file NÃO tem USE_PROFESSIONAL_FEATURES"
        fi
        if grep -q "ML_AUTO_RETRAIN_ENABLED" "$file"; then
            log_info "$file tem ML_AUTO_RETRAIN_ENABLED"
        fi
    else
        log_error "$file NÃO encontrado"
    fi
done
echo ""

# 3. Validar dashboards Grafana
echo "3. Validando dashboards Grafana..."

DASHBOARDS=(
    "monitoring/grafana/dashboards/ml_model_health.json"
    "monitoring/grafana/dashboards/ml_data_drift.json"
    "monitoring/grafana/dashboards/ml_training_pipeline.json"
)

for dashboard in "${DASHBOARDS[@]}"; do
    if [ -f "$dashboard" ]; then
        panels=$(jq '.panels | length' "$dashboard" 2>/dev/null || echo "0")
        log_info "$dashboard ($panels panels)"
    else
        log_error "$dashboard NÃO encontrado"
    fi
done
echo ""

# 4. Validar alertas Prometheus
echo "4. Validando alertas Prometheus..."

ALERTS_FILE="prometheus-rules/ml-drift-alerts.yaml"
if [ -f "$ALERTS_FILE" ]; then
    alerts=$(grep -c "alert:" "$ALERTS_FILE" || echo "0")
    log_info "$ALERTS_FILE ($alerts alertas)"
else
    log_error "$ALERTS_FILE NÃO encontrado"
fi
echo ""

# 5. Rodar testes críticos
echo "5. Rodando testes críticos..."

echo "   Testando neural_hive_llm..."
cd libraries/python/neural_hive_llm
if python3 -m pytest tests/ -q --tb=no 2>&1 | grep -q "passed"; then
    log_info "neural_hive_llm tests passando"
else
    log_error "neural_hive_llm tests FALHANDO"
fi
cd - > /dev/null

echo "   Testando ML Feedback Loop E2E..."
cd services/orchestrator-dynamic
if python3 -m pytest tests/integration/e2e/test_ml_feedback_loop.py -q --tb=no 2>&1 | grep -q "6 passed"; then
    log_info "ML Feedback Loop E2E passando"
else
    log_error "ML Feedback Loop E2E FALHANDO"
fi
cd - > /dev/null

echo "   Testando Drift Detection Integration..."
if python3 -m pytest services/orchestrator-dynamic/tests/integration/test_decision_consumer_drift_integration.py -q --tb=no 2>&1 | grep -q "19 passed"; then
    log_info "Drift Detection Integration passando"
else
    log_error "Drift Detection Integration FALHANDO"
fi
echo ""

# 6. Validar compatibilidade Python 3.10
echo "6. Validando compatibilidade Python 3.10..."

UTC_IMPORTS=$(find services ml_pipelines -name "*.py" -type f -exec grep -l "from datetime import.*UTC" {} \; 2>/dev/null | wc -l)
if [ "$UTC_IMPORTS" -eq 0 ]; then
    log_info "Nenhum import UTC encontrado (Python 3.10 compatível)"
else
    log_error "$UTC_IMPORTS arquivos ainda com import UTC (Python 3.11+)"
fi
echo ""

# 7. Validar configurações de feature flags
echo "7. Validando configurações de feature flags..."

if grep -q 'USE_PROFESSIONAL_FEATURES: "false"' k8s/approval-service-deployment.yaml; then
    log_info "USE_PROFESSIONAL_FEATURES=false (baseline)"
else
    log_warn "USE_PROFESSIONAL_FEATURES não está em false"
fi

if grep -q 'ML_AUTO_RETRAIN_ENABLED: "false"' k8s/approval-service-deployment.yaml; then
    log_info "ML_AUTO_RETRAIN_ENABLED=false (baseline)"
fi

if grep -q 'MODEL_PROMOTION_ENABLED: "true"' k8s/approval-service-deployment.yaml; then
    log_info "MODEL_PROMOTION_ENABLED=true"
fi
echo ""

# Resumo
echo "======================================"
echo "VALIDATION COMPLETE"
echo "======================================"
log_info "Tudo pronto para deploy staging!"
echo ""
echo "Próximos passos:"
echo "  1. ./deploy-staging.sh           # Deploy baseline"
echo "  2. Aguardar 24h                  # Coletar baseline"
echo "  3. ./deploy-staging.sh --activate-features"
echo "  4. Monitorar por 48h"
echo "  5. Comparar métricas"
echo ""
