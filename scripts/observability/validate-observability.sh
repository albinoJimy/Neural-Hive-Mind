#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Script de validação da stack de observabilidade

set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive-observability}"

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
warning() { echo -e "${YELLOW}[!]${NC} $1"; }

PASSED=0
FAILED=0

check() {
    local description="$1"
    local command="$2"

    if eval "$command" &> /dev/null; then
        success "$description"
        ((PASSED++))
        return 0
    else
        error "$description"
        ((FAILED++))
        return 1
    fi
}

log "Validando Stack de Observabilidade no namespace: $NAMESPACE"
echo ""

# 1. Verificar namespace
log "[1/10] Verificando namespace..."
check "Namespace $NAMESPACE existe" "kubectl get namespace $NAMESPACE"

# 2. Verificar Prometheus
log "[2/10] Verificando Prometheus..."
check "Prometheus StatefulSet existe" "kubectl get statefulset -n $NAMESPACE -l app.kubernetes.io/name=prometheus"
check "Prometheus pods Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].status.phase}' | grep -q Running"
check "Prometheus Service existe" "kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=prometheus"

# 3. Verificar Grafana
log "[3/10] Verificando Grafana..."
check "Grafana Deployment existe" "kubectl get deployment -n $NAMESPACE -l app.kubernetes.io/name=grafana"
check "Grafana pod Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.phase}' | grep -q Running"
check "Grafana Service existe" "kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=grafana"

# 4. Verificar Jaeger
log "[4/10] Verificando Jaeger..."
check "Jaeger Deployment existe" "kubectl get deployment -n $NAMESPACE -l app.kubernetes.io/name=jaeger"
check "Jaeger pod Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=jaeger -o jsonpath='{.items[0].status.phase}' | grep -q Running"
check "Jaeger Service existe" "kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=jaeger"

# 5. Verificar AlertManager
log "[5/10] Verificando AlertManager..."
check "AlertManager StatefulSet existe" "kubectl get statefulset -n $NAMESPACE -l app.kubernetes.io/name=alertmanager"
check "AlertManager pod Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=alertmanager -o jsonpath='{.items[0].status.phase}' | grep -q Running"

# 6. Verificar ServiceMonitors
log "[6/10] Verificando ServiceMonitors..."
SM_COUNT=$(kubectl get servicemonitor -A -l neural.hive/metrics=enabled --no-headers 2>/dev/null | wc -l)
if [ "$SM_COUNT" -ge 9 ]; then
    success "ServiceMonitors encontrados: $SM_COUNT (mínimo 9 esperado)"
    ((PASSED++))
else
    warning "ServiceMonitors encontrados: $SM_COUNT (esperado >= 9)"
    ((FAILED++))
fi

# 7. Verificar PrometheusRules (opcional em ambiente local)
log "[7/10] Verificando PrometheusRules..."
PR_COUNT=$(kubectl get prometheusrule -n $NAMESPACE --no-headers 2>/dev/null | wc -l)
if [ "$PR_COUNT" -ge 1 ]; then
    success "PrometheusRules encontradas: $PR_COUNT"
    ((PASSED++))
else
    warning "PrometheusRules não encontradas (opcional em ambiente local)"
    # Não falha em ambiente local
    ((PASSED++))
fi

# 8. Verificar PVCs
log "[8/10] Verificando PersistentVolumeClaims..."
check "Prometheus PVC Bound" "kubectl get pvc -n $NAMESPACE -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].status.phase}' | grep -q Bound"
check "Grafana PVC Bound" "kubectl get pvc -n $NAMESPACE -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.phase}' | grep -q Bound"

# 9. Testar conectividade (se port-forward estiver ativo)
log "[9/10] Testando conectividade (opcional)..."
if curl -s --connect-timeout 2 http://localhost:9090/-/healthy &> /dev/null; then
    success "Prometheus acessível via port-forward"
    ((PASSED++))
else
    warning "Prometheus não acessível (port-forward não ativo)"
fi

if curl -s --connect-timeout 2 http://localhost:3000/api/health &> /dev/null; then
    success "Grafana acessível via port-forward"
    ((PASSED++))
else
    warning "Grafana não acessível (port-forward não ativo)"
fi

if curl -s --connect-timeout 2 http://localhost:16686/ &> /dev/null; then
    success "Jaeger acessível via port-forward"
    ((PASSED++))
else
    warning "Jaeger não acessível (port-forward não ativo)"
fi

# 10. Verificar logs por erros
log "[10/10] Verificando logs por erros críticos..."
PROM_ERRORS=$(kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=prometheus --tail=100 2>/dev/null | grep -i "error\|fatal" | wc -l)
if [ "$PROM_ERRORS" -eq 0 ]; then
    success "Prometheus sem erros críticos nos logs"
    ((PASSED++))
else
    warning "Prometheus tem $PROM_ERRORS linhas com erros nos logs"
fi

GRAFANA_ERRORS=$(kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=grafana --tail=100 2>/dev/null | grep -i "error\|fatal" | wc -l)
if [ "$GRAFANA_ERRORS" -eq 0 ]; then
    success "Grafana sem erros críticos nos logs"
    ((PASSED++))
else
    warning "Grafana tem $GRAFANA_ERRORS linhas com erros nos logs"
fi

# Resumo
echo ""
log "========================================"
log "Resumo da Validação"
log "========================================"
log "Testes Passados: $PASSED"
log "Testes Falhados: $FAILED"
log "Taxa de Sucesso: $(( PASSED * 100 / (PASSED + FAILED) ))%"
echo ""

if [ $FAILED -eq 0 ]; then
    success "Todas as validações passaram!"
    exit 0
else
    warning "Algumas validações falharam"
    exit 1
fi
