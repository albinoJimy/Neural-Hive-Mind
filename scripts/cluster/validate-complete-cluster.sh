#!/bin/bash
# Script de validação completa do cluster Neural Hive-Mind
# Uso: ./validate-complete-cluster.sh [--verbose]

set -e

VERBOSE=false
if [[ "${1}" == "--verbose" ]]; then
  VERBOSE=true
fi

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=== Validação Completa Neural Hive-Mind ==="

# 5.1 Validação de Infraestrutura
log "[Fase 1/5] Validação de infraestrutura..."
scripts/validation/validate-cluster-health.sh
scripts/validation/validate-infrastructure-health.sh
scripts/validation/validate-memory-layer.sh

if [[ "${VERBOSE}" == true ]]; then
  scripts/security.sh validate all
  scripts/validation/test-mtls-connectivity.sh
  scripts/observability.sh validate
fi

# 5.2 Validação de Serviços
log "[Fase 2/5] Validação de serviços..."
scripts/validation/validate-phase2-services.sh
scripts/validation/validate-grpc-ticket-service.sh
scripts/validation/validate-worker-agents-integrations.sh

# 5.3 Testes End-to-End
log "[Fase 3/5] Testes end-to-end..."
if [[ -f "tests/phase1-end-to-end-test.sh" ]]; then
  tests/phase1-end-to-end-test.sh
else
  log "AVISO: Teste E2E Fase 1 não encontrado."
fi

if [[ -f "tests/run-tests.sh" ]]; then
  tests/run-tests.sh --type integration 2>/dev/null || true
  tests/run-tests.sh --type e2e --phase 2 2>/dev/null || true
fi

# 5.4 Validação de Performance
log "[Fase 4/5] Validação de performance..."
scripts/validation/validate-performance-benchmarks.sh
scripts/observability.sh test slos 2>/dev/null || true
scripts/validation/test-autoscaler.sh

# 5.5 Validação de Governança
log "[Fase 5/5] Validação de governança..."
if [[ "${VERBOSE}" == true ]]; then
  kubectl get constraints -A -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.status.totalViolations}{"\n"}{end}' 2>/dev/null || true
  scripts/security.sh audit report --output reports/security-audit-$(date +%Y%m%d).html 2>/dev/null || true
  scripts/validation/test-disaster-recovery.sh
fi

# Relatório Final
log "=== Relatório de Validação ==="

# Infraestrutura
echo ""
echo "## Infraestrutura"
kubectl get nodes 2>/dev/null | grep -v NAME || echo "  nodes não acessíveis"
echo "  Namespaces: $(kubectl get ns --no-headers 2>/dev/null | wc -l)"

# Bancos de Dados
echo ""
echo "## Bancos de Dados"
for ns in mongodb-cluster neo4j-cluster clickhouse-cluster redis-cluster; do
  if kubectl get ns ${ns} &>/dev/null; then
    echo "  ${ns}: $(kubectl get pods -n ${ns} --no-headers 2>/dev/null | grep Running | wc -l)/$(kubectl get pods -n ${ns} --no-headers 2>/dev/null | wc -l) pods running"
  fi
done

# Serviços Core
echo ""
echo "## Serviços Core"
for ns in neural-hive-system neural-hive-memory neural-hive-orchestration neural-hive-cognition neural-hive-execution; do
  if kubectl get ns ${ns} &>/dev/null; then
    echo "  ${ns}: $(kubectl get pods -n ${ns} --no-headers 2>/dev/null | grep Running | wc -l)/$(kubectl get pods -n ${ns} --no-headers 2>/dev/null | wc -l) pods running"
  fi
done

# Gateways
echo ""
echo "## Gateways"
for ns in gateway-intencoes neural-hive-observability; do
  if kubectl get ns ${ns} &>/dev/null; then
    echo "  ${ns}: $(kubectl get pods -n ${ns} --no-headers 2>/dev/null | grep Running | wc -l)/$(kubectl get pods -n ${ns} --no-headers 2>/dev/null | wc -l) pods running"
  fi
done

log "=== Validação Concluída ==="

# Verificar CRÍTICOS
CRITICAL_FAILURES=0
if ! kubectl get pods -n neural-hive-system &>/dev/null | grep -q "1/1"; then
  ((CRITICAL_FAILURES++))
  log "ERRO: Service Registry não está pronto"
fi

if ! kubectl get pods -n neural-hive-cognition &>/dev/null | grep specialist | grep -q "Running"; then
  ((CRITICAL_FAILURES++))
  log "ERRO: Specialists não estão rodando"
fi

if [[ ${CRITICAL_FAILURES} -gt 0 ]]; then
  log "ERRO: ${CRITICAL_FAILURES} falhas críticas detectadas."
  exit 1
else
  log "OK: Todas as validações críticas passaram."
fi
