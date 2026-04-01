#!/bin/bash
# Health Check Script for Neural Hive-Mind Services
#
# Este script executa health checks em todos os serviços críticos
# e retorna status consolidado para automação de failover.
#
# Uso:
#   ./health-check.sh [--namespace <ns>] [--timeout <seconds>]

set -euo pipefail

# Configurações
NAMESPACE="${NAMESPACE:-neural-hive}"
TIMEOUT="${TIMEOUT:-30}"
SERVICES=(
  "gateway-intencoes"
  "consensus-engine"
  "orchestrator-dynamic"
  "worker-agents"
  "specialist-business"
  "specialist-technical"
  "queen-agent"
)

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Status tracking
declare -A SERVICE_STATUS
declare -A SERVICE_REPLICAS
TOTAL_SERVICES=${#SERVICES[@]}
HEALTHY_SERVICES=0
UNHEALTHY_SERVICES=0

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     Health Check - Neural Hive-Mind Services                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Namespace: $NAMESPACE"
echo "Timeout: ${TIMEOUT}s"
echo ""

# Função para check de deployment
check_deployment() {
  local service=$1
  local namespace=$2

  # Verificar se deployment existe
  if ! kubectl get deployment "$service" -n "$namespace" &>/dev/null; then
    echo -e "${YELLOW}⚠${NC}  $service: Deployment não encontrado"
    SERVICE_STATUS[$service]="not_found"
    return 1
  fi

  # Obter status do deployment
  local replicas
  local ready
  local updated
  local available

  replicas=$(kubectl get deployment "$service" -n "$namespace" \
    -o jsonpath='{.spec.replicas}')

  ready=$(kubectl get deployment "$service" -n "$namespace" \
    -o jsonpath='{.status.readyReplicas}')

  updated=$(kubectl get deployment "$service" -n "$namespace" \
    -o jsonpath='{.status.updatedReplicas}')

  available=$(kubectl get deployment "$service" -n "$namespace" \
    -o jsonpath='{.status.availableReplicas}')

  # Armazenar info de replicas
  SERVICE_REPLICAS[$service]="${ready:-0}/${replicas}"

  # Verificar condições de saúde
  if [[ "$ready" == "$replicas" ]] && \
     [[ "$updated" == "$replicas" ]] && \
     [[ "$available" == "$replicas" ]]; then
    echo -e "${GREEN}✓${NC}  $service: Ready (${ready}/${replicas})"
    SERVICE_STATUS[$service]="healthy"
    return 0
  else
    echo -e "${RED}✗${NC}  $service: Not Ready (${ready:-0}/${replicas})"
    SERVICE_STATUS[$service]="unhealthy"
    return 1
  fi
}

# Função para check de pods
check_pods() {
  local service=$1
  local namespace=$2

  local pods
  local running=0
  local pending=0
  local failed=0

  pods=$(kubectl get pods -n "$namespace" -l "app=$service" -o jsonpath='{.items[*].metadata.name}')

  for pod in $pods; do
    local phase
    phase=$(kubectl get pod "$pod" -n "$namespace" -o jsonpath='{.status.phase}')

    case "$phase" in
      Running)
        ((running++))
        ;;
      Pending)
        ((pending++))
        ;;
      Failed|Error|CrashLoopBackOff)
        ((failed++))
        ;;
    esac
  done

  if [[ $failed -gt 0 ]]; then
    echo "    Pods: $running running, $pending pending, ${RED}$failed failed${NC}"
    return 1
  elif [[ $pending -gt 0 ]]; then
    echo "    Pods: $running running, ${YELLOW}$pending pending${NC}, 0 failed"
    return 2
  else
    echo "    Pods: $running running, 0 pending, 0 failed"
    return 0
  fi
}

# Função para check de endpoint HTTP
check_http_endpoint() {
  local service=$1
  local namespace=$2
  local port=${3:-8000}
  local path=${4:-/health}

  # Obter nome de um pod
  local pod
  pod=$(kubectl get pods -n "$namespace" -l "app=$service" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -z "$pod" ]]; then
    return 1
  fi

  # Executar curl no pod
  local response
  response=$(kubectl exec "$pod" -n "$namespace" -c "$service" \
    -- curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:${port}${path}" 2>/dev/null || echo "000")

  if [[ "$response" == "200" ]]; then
    return 0
  else
    return 1
  fi
}

# Executar checks
echo "Verificando serviços..."
echo ""

for service in "${SERVICES[@]}"; do
  if check_deployment "$service" "$NAMESPACE"; then
    ((HEALTHY_SERVICES++))
    check_pods "$service" "$NAMESPACE" || true

    # Check HTTP endpoint se disponível
    case "$service" in
      gateway-intencoes)
        if check_http_endpoint "$service" "$NAMESPACE" 8000 /health; then
          echo "    HTTP: ✓ /health"
        else
          echo "    HTTP: ✗ /health (endpoint não responde)"
        fi
        ;;
      worker-agents)
        if check_http_endpoint "$service" "$NAMESPACE" 8005 /health; then
          echo "    HTTP: ✓ /health"
        else
          echo "    HTTP: ✗ /health (endpoint não responde)"
        fi
        ;;
    esac
  else
    ((UNHEALTHY_SERVICES++))
    check_pods "$service" "$NAMESPACE" || true
  fi
  echo ""
done

# Resumo
echo "═══════════════════════════════════════════════════════════════"
echo "RESUMO"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Total de serviços: $TOTAL_SERVICES"
echo -e "Saudáveis: ${GREEN}${HEALTHY_SERVICES}${NC}"
echo -e "Não saudáveis: ${RED}${UNHEALTHY_SERVICES}${NC}"
echo ""

# Calcular percentual de saúde
HEALTH_PERCENT=$(( HEALTHY_SERVICES * 100 / TOTAL_SERVICES ))

echo "Saúde do cluster: ${HEALTH_PERCENT}%"
echo ""

# Exit code baseado na saúde
if [[ $HEALTHY_SERVICES -eq $TOTAL_SERVICES ]]; then
  echo -e "${GREEN}✓ Todos os serviços saudáveis${NC}"
  exit 0
elif [[ $HEALTH_PERCENT -ge 70 ]]; then
  echo -e "${YELLOW}⚠ Cluster parcialmente degradado${NC}"
  exit 1
else
  echo -e "${RED}✗ Cluster severamente degradado - FAILOVER RECOMENDADO${NC}"
  exit 2
fi
