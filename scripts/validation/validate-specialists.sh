#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -euo pipefail

SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

echo "Validating Neural Specialists..."

# 1. Verificar pods
echo "1. Checking pods..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  POD_COUNT=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=specialist-${specialist} --field-selector=status.phase=Running -o json | jq '.items | length')

  if [ "$POD_COUNT" -lt 1 ]; then
    echo "ERROR: No running pods for ${specialist}"
    exit 1
  fi
  echo "✓ ${specialist}: $POD_COUNT pods running"
done

# 2. Verificar health endpoints
echo "2. Checking health endpoints..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=specialist-${specialist} -o jsonpath='{.items[0].metadata.name}')

  kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/health
  echo "✓ ${specialist}: Health endpoint OK"
done

# 3. Verificar readiness endpoints
echo "3. Checking readiness endpoints..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=specialist-${specialist} -o jsonpath='{.items[0].metadata.name}')

  kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/ready
  echo "✓ ${specialist}: Readiness endpoint OK"
done

# 4. Verificar métricas Prometheus
echo "4. Checking Prometheus metrics..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=specialist-${specialist} -o jsonpath='{.items[0].metadata.name}')

  METRICS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8080/metrics)
  if echo "$METRICS" | grep -q "neural_hive_service_info"; then
    echo "✓ ${specialist}: Metrics endpoint OK"
  else
    echo "ERROR: Metrics not found for ${specialist}"
    exit 1
  fi
done

# 5. Verificar ServiceMonitors
echo "5. Checking ServiceMonitors..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  kubectl get servicemonitor -n ${NAMESPACE} specialist-${specialist} > /dev/null 2>&1
  echo "✓ ${specialist}: ServiceMonitor exists"
done

# 6. Verificar NetworkPolicies
echo "6. Checking NetworkPolicies..."
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  kubectl get networkpolicy -n ${NAMESPACE} specialist-${specialist} > /dev/null 2>&1
  echo "✓ ${specialist}: NetworkPolicy exists"
done

echo ""
echo "✅ All validations passed!"
echo ""
echo "Next steps:"
echo "1. Test specialist evaluation with sample Cognitive Plan"
echo "2. Verify opinions are persisted in MongoDB ledger"
echo "3. Check Grafana dashboard: http://grafana/d/specialists-cognitive-layer"
echo "4. Check Jaeger traces for correlation"
echo "5. Verify MLflow experiments are being tracked"
