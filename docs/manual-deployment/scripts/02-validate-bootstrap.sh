#!/bin/bash
# Script de validação do bootstrap do Kubernetes
# Uso: ./02-validate-bootstrap.sh

set -euo pipefail

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

check() {
  local description="$1"
  local command="$2"
  TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
  
  echo -e "${BLUE}[CHECK ${TOTAL_CHECKS}]${NC} ${description}"
  if eval "$command" &> /dev/null; then
    echo -e "${GREEN}✓ PASS${NC}"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
  else
    echo -e "${RED}✗ FAIL${NC}"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
  echo ""
}

echo "======================================="
echo "  Bootstrap Validation - Neural Hive  "
echo "======================================="
echo ""

# 1. Validar Namespaces
echo -e "${YELLOW}=== 1. NAMESPACES ===${NC}"
check "Namespace neural-hive-system existe" "kubectl get namespace neural-hive-system"
check "Namespace neural-hive-cognition existe" "kubectl get namespace neural-hive-cognition"
check "Namespace neural-hive-orchestration existe" "kubectl get namespace neural-hive-orchestration"
check "Namespace neural-hive-execution existe" "kubectl get namespace neural-hive-execution"
check "Namespace neural-hive-observability existe" "kubectl get namespace neural-hive-observability"
check "Namespace cosign-system existe" "kubectl get namespace cosign-system"
check "Namespace gatekeeper-system existe" "kubectl get namespace gatekeeper-system"
check "Namespace cert-manager existe" "kubectl get namespace cert-manager"
check "Namespace auth existe" "kubectl get namespace auth"

# 2. Validar CRDs
echo -e "${YELLOW}=== 2. CUSTOM RESOURCE DEFINITIONS ===${NC}"
check "CRD apiassets.catalog.neural-hive.io existe" "kubectl get crd apiassets.catalog.neural-hive.io"
check "CRD dataassets.catalog.neural-hive.io existe" "kubectl get crd dataassets.catalog.neural-hive.io"
check "CRD servicecontracts.catalog.neural-hive.io existe" "kubectl get crd servicecontracts.catalog.neural-hive.io"
check "CRD datalineages.catalog.neural-hive.io existe" "kubectl get crd datalineages.catalog.neural-hive.io"

# 3. Validar ResourceQuotas
echo -e "${YELLOW}=== 3. RESOURCE QUOTAS ===${NC}"
check "ResourceQuota em neural-hive-cognition" "kubectl get resourcequota -n neural-hive-cognition"
check "ResourceQuota em neural-hive-orchestration" "kubectl get resourcequota -n neural-hive-orchestration"
check "ResourceQuota em neural-hive-execution" "kubectl get resourcequota -n neural-hive-execution"
check "ResourceQuota em neural-hive-observability" "kubectl get resourcequota -n neural-hive-observability"

# 4. Validar LimitRanges
echo -e "${YELLOW}=== 4. LIMIT RANGES ===${NC}"
check "LimitRange em neural-hive-cognition" "kubectl get limitrange -n neural-hive-cognition"
check "LimitRange em neural-hive-orchestration" "kubectl get limitrange -n neural-hive-orchestration"
check "LimitRange em neural-hive-execution" "kubectl get limitrange -n neural-hive-execution"
check "LimitRange em neural-hive-observability" "kubectl get limitrange -n neural-hive-observability"

# 5. Validar RBAC
echo -e "${YELLOW}=== 5. RBAC ===${NC}"
check "ServiceAccount cognitive-processor" "kubectl get serviceaccount cognitive-processor -n neural-hive-cognition"
check "ServiceAccount orchestration-engine" "kubectl get serviceaccount orchestration-engine -n neural-hive-orchestration"
check "ServiceAccount execution-agent" "kubectl get serviceaccount execution-agent -n neural-hive-execution"
check "ClusterRole neural-hive-config-reader" "kubectl get clusterrole neural-hive-config-reader"
check "ClusterRole neural-hive-workload-manager" "kubectl get clusterrole neural-hive-workload-manager"
check "RoleBinding cognitive-processor-binding" "kubectl get rolebinding cognitive-processor-binding -n neural-hive-cognition"
check "ClusterRoleBinding neural-hive-config-readers" "kubectl get clusterrolebinding neural-hive-config-readers"

# 6. Validar Network Policies
echo -e "${YELLOW}=== 6. NETWORK POLICIES ===${NC}"
check "NetworkPolicy default-deny-ingress em cognition" "kubectl get networkpolicy default-deny-ingress -n neural-hive-cognition"
check "NetworkPolicy allow-from-orchestration em cognition" "kubectl get networkpolicy allow-from-orchestration -n neural-hive-cognition"
check "NetworkPolicy allow-dns-access em cognition" "kubectl get networkpolicy allow-dns-access -n neural-hive-cognition"
check "NetworkPolicy default-deny-ingress em orchestration" "kubectl get networkpolicy default-deny-ingress -n neural-hive-orchestration"
check "NetworkPolicy default-deny-ingress em execution" "kubectl get networkpolicy default-deny-ingress -n neural-hive-execution"

# 7. Validar Pod Security Standards
echo -e "${YELLOW}=== 7. POD SECURITY STANDARDS ===${NC}"
check "ConfigMap pod-security-config" "kubectl get configmap pod-security-config -n kube-system"
check "ConfigMap security-context-templates" "kubectl get configmap security-context-templates -n kube-system"
check "ValidatingWebhookConfiguration neural-hive-pod-security-validator" "kubectl get validatingwebhookconfiguration neural-hive-pod-security-validator"
check "ConfigMap runtime-security-config" "kubectl get configmap runtime-security-config -n neural-hive-system"
check "PodDisruptionBudget cognition" "kubectl get poddisruptionbudget neural-hive-cognition-pdb -n neural-hive-cognition"
check "PodDisruptionBudget orchestration" "kubectl get poddisruptionbudget neural-hive-orchestration-pdb -n neural-hive-orchestration"
check "PodDisruptionBudget execution" "kubectl get poddisruptionbudget neural-hive-execution-pdb -n neural-hive-execution"

# Resumo
echo "======================================="
echo -e "${BLUE}RESUMO DA VALIDAÇÃO${NC}"
echo "======================================="
echo -e "Total de checks: ${TOTAL_CHECKS}"
echo -e "${GREEN}Passed: ${PASSED_CHECKS}${NC}"
echo -e "${RED}Failed: ${FAILED_CHECKS}${NC}"
echo ""

if [[ $FAILED_CHECKS -eq 0 ]]; then
  echo -e "${GREEN}✓ Bootstrap validado com sucesso!${NC}"
  exit 0
else
  echo -e "${RED}✗ Bootstrap possui falhas. Revise os checks acima.${NC}"
  exit 1
fi
