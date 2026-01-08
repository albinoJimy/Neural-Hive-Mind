#!/bin/bash
# Validacao de SLA Monitoring do Orchestrator Dynamic
# Verifica deployment completo do sistema de monitoramento SLA

set -e

echo "=== Validacao de SLA Monitoring ==="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

check_warn() {
    echo -e "${YELLOW}!${NC} $1"
}

# 1. Verificar servicos necessarios
echo "1. Verificando servicos..."

if kubectl get svc -n neural-hive-orchestration orchestrator-dynamic &>/dev/null; then
    check_pass "Orchestrator Dynamic disponivel"
else
    check_warn "Orchestrator Dynamic nao encontrado (verificar namespace)"
fi

if kubectl get svc -n neural-hive-sla sla-management-system &>/dev/null; then
    check_pass "SLA Management System disponivel"
else
    check_warn "SLA Management System nao encontrado"
fi

# 2. Verificar alertas configurados
echo ""
echo "2. Verificando alertas Prometheus..."

if kubectl get prometheusrule -n monitoring orchestrator-sla-alerts &>/dev/null; then
    check_pass "PrometheusRule orchestrator-sla-alerts configurado"
else
    check_warn "PrometheusRule orchestrator-sla-alerts nao encontrado"
fi

# 3. Verificar dashboard Grafana
echo ""
echo "3. Verificando dashboard Grafana..."

if kubectl get configmap -n monitoring orchestrator-sla-compliance-dashboard &>/dev/null; then
    check_pass "Dashboard ConfigMap configurado"
else
    check_warn "Dashboard ConfigMap nao encontrado (usar 'make deploy-sla-dashboard')"
fi

# 4. Executar testes unitarios
echo ""
echo "4. Executando testes unitarios..."

cd "$(dirname "$0")/../services/orchestrator-dynamic"

if [ -f "tests/unit/test_sla_monitor.py" ] && [ -f "tests/unit/test_alert_manager.py" ]; then
    if pytest tests/unit/test_sla_monitor.py tests/unit/test_alert_manager.py -v --tb=short 2>/dev/null; then
        check_pass "Testes unitarios SLA passaram"
    else
        check_fail "Testes unitarios SLA falharam"
    fi
else
    check_warn "Arquivos de teste unitario nao encontrados"
fi

# 5. Executar testes de integracao (mocked)
echo ""
echo "5. Executando testes de integracao..."

if [ -f "tests/integration/test_sla_integration.py" ]; then
    if pytest tests/integration/test_sla_integration.py -v --tb=short -m "not real_integration" 2>/dev/null; then
        check_pass "Testes de integracao passaram"
    else
        check_fail "Testes de integracao falharam"
    fi
else
    check_warn "Arquivo de teste de integracao nao encontrado"
fi

cd - >/dev/null

# 6. Verificar metricas Prometheus (se acessivel)
echo ""
echo "6. Verificando metricas Prometheus..."

PROM_URL="${PROMETHEUS_URL:-http://prometheus.monitoring.svc.cluster.local:9090}"

if command -v curl &>/dev/null; then
    METRIC_COUNT=$(curl -s "${PROM_URL}/api/v1/query?query=orchestration_sla_check_duration_seconds_count" 2>/dev/null | grep -c "result" || echo "0")
    if [ "$METRIC_COUNT" -gt "0" ]; then
        check_pass "Metricas SLA disponiveis no Prometheus"
    else
        check_warn "Metricas SLA nao encontradas (Prometheus pode estar inacessivel)"
    fi
else
    check_warn "curl nao disponivel para verificar metricas"
fi

# 7. Resumo
echo ""
echo "=== Validacao Concluida ==="
echo ""
echo "Para executar testes de integracao real:"
echo "  pytest -m real_integration services/orchestrator-dynamic/tests/integration/test_sla_real_integration.py -v"
echo ""
echo "Para deploy do dashboard Grafana:"
echo "  make deploy-sla-dashboard"
echo ""
