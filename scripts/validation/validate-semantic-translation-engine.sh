#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Validação end-to-end do Motor de Tradução Semântica
set -euo pipefail

NAMESPACE="semantic-translation-engine"

echo "Validando Semantic Translation Engine..."

# 1. Verificar pods
echo "1. Verificando pods..."
kubectl get pods -n ${NAMESPACE}

POD_COUNT=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine --field-selector=status.phase=Running -o json | jq '.items | length')
if [ "$POD_COUNT" -lt 1 ]; then
  echo "❌ ERRO: Nenhum pod em execução"
  exit 1
fi
echo "✓ Pods em execução: $POD_COUNT"

# 2. Verificar health endpoint
echo "2. Verificando health endpoint..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/health
echo "✓ Health endpoint OK"

# 3. Verificar readiness endpoint
echo "3. Verificando readiness endpoint..."
kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/ready
echo "✓ Readiness endpoint OK"

# 4. Verificar métricas Prometheus
echo "4. Verificando métricas Prometheus..."
METRICS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8080/metrics)
if echo "$METRICS" | grep -q "neural_hive"; then
  echo "✓ Métricas Prometheus OK"
else
  echo "❌ ERRO: Métricas não encontradas"
  exit 1
fi

# 5. Verificar conectividade Kafka
echo "5. Verificando conectividade Kafka..."
kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=50 | grep -q "Intent consumer inicializado"
echo "✓ Kafka consumer inicializado"

# 6. Verificar conectividade Neo4j
echo "6. Verificando conectividade Neo4j..."
kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=50 | grep -q "Neo4j client inicializado"
echo "✓ Neo4j client inicializado"

# 7. Verificar conectividade MongoDB
echo "7. Verificando conectividade MongoDB..."
kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=50 | grep -q "MongoDB client inicializado"
echo "✓ MongoDB client inicializado"

# 8. Verificar ServiceMonitor
echo "8. Verificando ServiceMonitor..."
kubectl get servicemonitor -n ${NAMESPACE} semantic-translation-engine
echo "✓ ServiceMonitor existe"

# 9. Verificar NetworkPolicy
echo "9. Verificando NetworkPolicy..."
kubectl get networkpolicy -n ${NAMESPACE} semantic-translation-engine
echo "✓ NetworkPolicy existe"

echo ""
echo "✅ Todas as validações passaram!"
echo ""
echo "Próximos passos:"
echo "1. Enviar Intent Envelope de teste para Kafka"
echo "2. Verificar Cognitive Plan gerado no tópico plans.ready"
echo "3. Acessar dashboard Grafana"
echo "4. Verificar traces no Jaeger"
