#!/bin/bash

# Guard Agents Validation Script
# Valida deployment completo do Guard Agents

NAMESPACE="${NAMESPACE:-neural-hive-resilience}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

TOTAL_CHECKS=0
PASSED_CHECKS=0

check() {
  local name=$1
  local command=$2
  TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

  if eval "$command" >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} $name"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    return 0
  else
    echo -e "${RED}✗${NC} $name"
    return 1
  fi
}

echo -e "${YELLOW}=== Guard Agents Validation ===${NC}\n"

# 1. Infraestrutura
echo -e "${YELLOW}[Infraestrutura]${NC}"
check "Namespace existe" "kubectl get namespace $NAMESPACE"
check "Kafka topic security-incidents" "kubectl get kafkatopic security-incidents -n kafka"
check "Kafka topic remediation-actions" "kubectl get kafkatopic remediation-actions -n kafka"
check "MongoDB acessível" "kubectl get svc mongodb -n neural-hive-persistence"
check "Redis acessível" "kubectl get svc redis -n neural-hive-persistence"
check "Prometheus acessível" "kubectl get svc prometheus -n observability"
check "Alertmanager acessível" "kubectl get svc alertmanager -n observability"
echo ""

# 2. Deployment
echo -e "${YELLOW}[Deployment]${NC}"
check "Pods Guard Agents running" "kubectl get pods -n $NAMESPACE -l app=guard-agents -o jsonpath='{.items[*].status.phase}' | grep -q Running"
check "Mínimo 2 réplicas" "[ \$(kubectl get pods -n $NAMESPACE -l app=guard-agents --no-headers | wc -l) -ge 2 ]"
check "Service existe" "kubectl get svc guard-agents -n $NAMESPACE"
check "ServiceMonitor existe" "kubectl get servicemonitor guard-agents -n $NAMESPACE"
check "HPA existe" "kubectl get hpa guard-agents -n $NAMESPACE"
check "PDB existe" "kubectl get pdb guard-agents -n $NAMESPACE"
echo ""

# 3. RBAC
echo -e "${YELLOW}[RBAC]${NC}"
check "ServiceAccount existe" "kubectl get sa guard-agents -n $NAMESPACE"
check "ClusterRole existe" "kubectl get clusterrole guard-agents"
check "ClusterRoleBinding existe" "kubectl get clusterrolebinding guard-agents"
echo ""

# 4. Health Checks
echo -e "${YELLOW}[Health Checks]${NC}"
POD=$(kubectl get pods -n $NAMESPACE -l app=guard-agents -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$POD" ]; then
  check "Liveness endpoint" "kubectl exec -n $NAMESPACE $POD -- curl -f -s http://localhost:8080/health/liveness"
  check "Readiness endpoint" "kubectl exec -n $NAMESPACE $POD -- curl -f -s http://localhost:8080/health/readiness"
  check "Metrics endpoint" "kubectl exec -n $NAMESPACE $POD -- curl -f -s http://localhost:9090/metrics"
fi
echo ""

# 5. Alertas
echo -e "${YELLOW}[Alertas]${NC}"
check "PrometheusRule guard-agents" "kubectl get prometheusrule neural-hive-guard-agents-alerts -n observability"
echo ""

# Sumário
echo -e "${YELLOW}=== Sumário ===${NC}"
echo -e "Checks passados: ${PASSED_CHECKS}/${TOTAL_CHECKS}"

if [ $PASSED_CHECKS -eq $TOTAL_CHECKS ]; then
  echo -e "${GREEN}✓ Todos os checks passaram!${NC}"
  exit 0
else
  echo -e "${RED}✗ Alguns checks falharam${NC}"
  exit 1
fi
