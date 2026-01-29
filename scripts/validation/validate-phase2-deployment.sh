#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Validate Phase 2 Deployment
# Verifica health/readiness de todos os 13 servicos

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

validate_service() {
  local service=$1
  local namespace=$2

  echo -n "Validando ${service}... "

  # Check deployment exists
  if ! kubectl get deployment ${service} -n ${namespace} >/dev/null 2>&1; then
    echo -e "${RED}FAIL${NC} (deployment nao encontrado)"
    return 1
  fi

  # Check pods running
  local ready=$(kubectl get deployment ${service} -n ${namespace} -o jsonpath='{.status.readyReplicas}')
  local desired=$(kubectl get deployment ${service} -n ${namespace} -o jsonpath='{.spec.replicas}')

  if [ "${ready:-0}" != "${desired}" ]; then
    echo -e "${RED}FAIL${NC} (${ready:-0}/${desired} pods ready)"
    return 1
  fi

  echo -e "${GREEN}OK${NC} (${ready}/${desired} pods ready)"
  return 0
}

echo "===== Validacao Phase 2 Deployment ====="
echo ""

FAILED=0

validate_service "service-registry" "neural-hive-registry" || FAILED=$((FAILED+1))
validate_service "execution-ticket-service" "neural-hive-orchestration" || FAILED=$((FAILED+1))
validate_service "orchestrator-dynamic" "neural-hive-orchestration" || FAILED=$((FAILED+1))
validate_service "queen-agent" "neural-hive-queen" || FAILED=$((FAILED+1))
validate_service "worker-agents" "neural-hive-workers" || FAILED=$((FAILED+1))
validate_service "code-forge" "neural-hive-code-forge" || FAILED=$((FAILED+1))
validate_service "scout-agents" "neural-hive-scouts" || FAILED=$((FAILED+1))
validate_service "analyst-agents" "neural-hive-analysts" || FAILED=$((FAILED+1))
validate_service "optimizer-agents" "neural-hive-optimizers" || FAILED=$((FAILED+1))
validate_service "guard-agents" "neural-hive-guards" || FAILED=$((FAILED+1))
validate_service "sla-management-system" "neural-hive-sla" || FAILED=$((FAILED+1))
validate_service "mcp-tool-catalog" "neural-hive-mcp" || FAILED=$((FAILED+1))
validate_service "self-healing-engine" "neural-hive-healing" || FAILED=$((FAILED+1))

echo ""
if [ ${FAILED} -eq 0 ]; then
  echo -e "${GREEN} Todos os 13 servicos estao healthy${NC}"
  exit 0
else
  echo -e "${RED} ${FAILED} servico(s) com problemas${NC}"
  exit 1
fi
