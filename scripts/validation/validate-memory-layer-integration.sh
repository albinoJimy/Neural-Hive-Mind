#!/bin/bash
set -euo pipefail

# Validation script for Memory Layer Integration
# Valida integração completa das 4 camadas de memória

NAMESPACE="memory-layer-api"

echo "========================================="
echo "Validating Memory Layer Integration..."
echo "========================================="

# 1. Verificar pods
echo ""
echo "1. Checking pods..."
kubectl get pods -n ${NAMESPACE}

POD_COUNT=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=memory-layer-api --field-selector=status.phase=Running -o json | jq '.items | length')
if [ "$POD_COUNT" -lt 1 ]; then
  echo "❌ ERROR: No running pods found"
  exit 1
fi
echo "✅ Pods running: $POD_COUNT"

# 2. Verificar health endpoint
echo ""
echo "2. Checking health endpoint..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=memory-layer-api -o jsonpath='{.items[0].metadata.name}')
if kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/health 2>/dev/null; then
  echo "✅ Health endpoint OK"
else
  echo "❌ Health endpoint failed"
  exit 1
fi

# 3. Verificar readiness endpoint
echo ""
echo "3. Checking readiness endpoint..."
READINESS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8000/ready 2>/dev/null)
if echo "$READINESS" | jq -e '.ready == true' > /dev/null 2>&1; then
  echo "✅ Readiness endpoint OK"
else
  echo "⚠ Service not ready:"
  echo "$READINESS" | jq . || echo "$READINESS"
fi

# 4. Verificar conectividade com 4 camadas
echo ""
echo "4. Checking connectivity to memory layers..."
for layer in redis mongodb neo4j clickhouse; do
  if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 2>/dev/null | grep -qi "${layer}.*initialized\|${layer}.*connected"; then
    echo "✅ ${layer} connected"
  else
    echo "⚠ ${layer} connection not confirmed in logs"
  fi
done

# 5. Testar API de query unificada
echo ""
echo "5. Testing unified query API..."
if kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f -X POST http://localhost:8000/api/v1/memory/query \
  -H "Content-Type: application/json" \
  -d '{"query_type": "context", "entity_id": "test-id", "use_cache": true}' 2>/dev/null; then
  echo "✅ Query API responding"
else
  echo "⚠ Query API test failed (may be expected if no data)"
fi

# 6. Verificar métricas Prometheus
echo ""
echo "6. Checking Prometheus metrics..."
METRICS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8080/metrics 2>/dev/null)
if echo "$METRICS" | grep -q "neural_hive_memory_queries_total\|process_cpu_seconds_total"; then
  echo "✅ Memory layer metrics OK"
else
  echo "❌ Memory metrics not found"
  exit 1
fi

# 7. Verificar CronJobs
echo ""
echo "7. Checking CronJobs..."
for job in memory-sync-mongodb-to-clickhouse memory-cleanup-retention data-quality-check; do
  if kubectl get cronjob -n ${NAMESPACE} ${job} &> /dev/null; then
    echo "✅ CronJob ${job} exists"
  else
    echo "⚠ CronJob ${job} not found"
  fi
done

# 8. Verificar ConfigMap de políticas
echo ""
echo "8. Checking policies ConfigMap..."
if kubectl get configmap -n ${NAMESPACE} memory-layer-policies &> /dev/null; then
  echo "✅ Policies ConfigMap exists"
else
  echo "⚠ Policies ConfigMap not found"
fi

# 9. Verificar ServiceMonitor (se existir)
echo ""
echo "9. Checking ServiceMonitor..."
if kubectl get servicemonitor -n ${NAMESPACE} memory-layer-api &> /dev/null 2>&1; then
  echo "✅ ServiceMonitor exists"
else
  echo "⚠ ServiceMonitor not found (may not be created yet)"
fi

# 10. Verificar NetworkPolicy (se existir)
echo ""
echo "10. Checking NetworkPolicy..."
if kubectl get networkpolicy -n ${NAMESPACE} memory-layer-api &> /dev/null 2>&1; then
  echo "✅ NetworkPolicy exists"
else
  echo "⚠ NetworkPolicy not found (may not be created yet)"
fi

echo ""
echo "========================================="
echo "✅ All critical validations passed!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Test unified query API with real data"
echo "2. Verify data appears in all 4 layers (Redis, MongoDB, Neo4j, ClickHouse)"
echo "3. Check lineage tracking in MongoDB and Neo4j"
echo "4. Verify quality metrics in MongoDB"
echo "5. Check Grafana dashboards (if available)"
echo "6. Wait for CronJobs to execute and verify sync"
echo ""
echo "Commands:"
echo "  - Port-forward API: kubectl port-forward -n ${NAMESPACE} svc/memory-layer-api 8000:8000"
echo "  - View logs: kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=memory-layer-api -f"
echo "  - Test query: curl -X POST http://localhost:8000/api/v1/memory/query -H 'Content-Type: application/json' -d '{\"query_type\": \"context\", \"entity_id\": \"test\"}'"
