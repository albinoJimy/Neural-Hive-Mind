#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Validar instrumentação de observabilidade

set -euo pipefail

SERVICES=("queen-agent" "execution-ticket-service" "guard-agents" "service-registry")

for service in "${SERVICES[@]}"; do
  echo "Validando $service..."

  # Verificar pod está rodando
  kubectl get pods -l app=$service -n neural-hive-orchestration

  # Verificar logs de inicialização
  kubectl logs -l app=$service -n neural-hive-orchestration --tail=50 | grep "Observabilidade inicializada"

  # Verificar métricas Prometheus
  POD=$(kubectl get pods -l app=$service -n neural-hive-orchestration -o jsonpath='{.items[0].metadata.name}')
  kubectl exec "$POD" -n neural-hive-orchestration -- curl -s localhost:9090/metrics | grep neural_hive_service_startup_total
done

echo "Validação completa!"
