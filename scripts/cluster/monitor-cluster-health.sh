#!/bin/bash
# Script de monitoramento contínuo da saúde do cluster
# Uso: ./monitor-cluster-health.sh [--interval N]

set -e

INTERVAL="${2:-5}"

echo "=== Monitoramento Neural Hive-Mind ==="
echo "Intervalo: ${INTERVAL} segundos | Ctrl+C para sair"
echo ""

# Função de exibição de dashboard
show_dashboard() {
  clear
  echo "╔════════════════════════════════════════════════════════════╗"
  echo "║  Neural Hive-Mind - Cluster Health Monitor               ║"
  echo "║  $(date '+%Y-%m-%d %H:%M:%S')                                  ║"
  echo "╚════════════════════════════════════════════════════════════╝"
  echo ""

  # Nodes
  echo "## Nodes"
  kubectl get nodes 2>/dev/null | head -5 || echo "  nodes não acessíveis"
  echo ""

  # Pods por namespace crítico
  echo "## Pods por Namespace"
  for ns in neural-hive-system neural-hive-memory neural-hive-orchestration \
    neural-hive-cognition neural-hive-execution neural-hive-specialists \
    gateway-intencoes neural-hive-observability; do
    if kubectl get ns ${ns} &>/dev/null; then
      TOTAL=$(kubectl get pods -n ${ns} --no-headers 2>/dev/null | wc -l)
      RUNNING=$(kubectl get pods -n ${ns} --no-headers 2>/dev/null | grep -c Running || echo 0)
      PENDING=$((TOTAL - RUNNING))
      STATUS="✓"
      [[ ${PENDING} -gt 0 ]] && STATUS="⚠"
      [[ ${RUNNING} -eq 0 && ${TOTAL} -gt 0 ]] && STATUS="✗"
      printf "  ${STATUS} %-30s %3d/%3d running" "${ns}" ${RUNNING} ${TOTAL}
      [[ ${PENDING} -gt 0 ]] && printf " (%d pending)" ${PENDING}
      echo ""
    fi
  done
  echo ""

  # Recursos do cluster
  echo "## Recursos"
  echo "  Pods totais: $(kubectl get pods --all-namespaces --no-headers 2>/dev/null | wc -l)"
  echo "  Namespaces: $(kubectl get ns --no-headers 2>/dev/null | wc -l)"
  echo ""

  # Recursos por nodo (se top disponível)
  if command -v kubectl-top &>/dev/null || kubectl top nodes &>/dev/null; then
    echo "## Uso de Recursos (Nodes)"
    kubectl top nodes 2>/dev/null | head -5 || echo "  métricas não disponíveis"
    echo ""
  fi

  # Eventos recentes
  echo "## Eventos Recentes (últimos 5)"
  kubectl get events --all-namespaces --sort-by='.lastTimestamp' 2>/dev/null | \
    grep -v "Normal.*Successful" | tail -6 | head -5 || echo "  nenhum evento"
  echo ""

  # Pods não-Running ou com problemas
  echo "## Pods com Problemas"
  PROBLEM_PODS=$(kubectl get pods --all-namespaces --no-headers 2>/dev/null | \
    grep -v "Running\|Completed" | grep -v "Completed" || echo "")
  if [[ -n "${PROBLEM_PODS}" ]]; then
    echo "${PROBLEM_PODS}" | head -5
  else
    echo "  nenhum pod com problemas"
  fi
  echo ""
}

# Trap para sair limpo
trap 'echo ""; echo "Monitoramento encerrado."; exit 0' INT TERM

# Loop principal
while true; do
  show_dashboard
  sleep ${INTERVAL}
done
