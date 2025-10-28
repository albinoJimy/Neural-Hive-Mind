#!/bin/bash

set -e

NAMESPACE="neural-hive"
SERVICE_NAME="queen-agent"

echo "🔍 Validating Queen Agent deployment..."
echo ""

# Verificar pods
echo "1️⃣ Checking pods status..."
PODS=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME -o json)
READY_PODS=$(echo $PODS | jq -r '.items[] | select(.status.phase=="Running") | .metadata.name' | wc -l)
TOTAL_PODS=$(echo $PODS | jq -r '.items | length')

echo "   Ready pods: $READY_PODS/$TOTAL_PODS"

if [ $READY_PODS -eq 0 ]; then
    echo "   ❌ No pods are ready"
    kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME
    exit 1
fi

kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME
echo ""

# Verificar service
echo "2️⃣ Checking service..."
if kubectl get service $SERVICE_NAME -n $NAMESPACE &> /dev/null; then
    echo "   ✅ Service exists"
    kubectl get service $SERVICE_NAME -n $NAMESPACE
else
    echo "   ❌ Service not found"
    exit 1
fi
echo ""

# Verificar endpoints
echo "3️⃣ Checking service endpoints..."
ENDPOINTS=$(kubectl get endpoints $SERVICE_NAME -n $NAMESPACE -o json | jq -r '.subsets[0].addresses | length')
if [ "$ENDPOINTS" -gt 0 ]; then
    echo "   ✅ Service has $ENDPOINTS endpoint(s)"
else
    echo "   ❌ Service has no endpoints"
    exit 1
fi
echo ""

# Verificar health check
echo "4️⃣ Checking health endpoint..."
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

if kubectl exec -n $NAMESPACE $POD_NAME -- curl -sf http://localhost:8000/health &> /dev/null; then
    echo "   ✅ Health endpoint responding"
else
    echo "   ⚠️  Health endpoint not responding yet (pod may still be starting)"
fi
echo ""

# Verificar readiness
echo "5️⃣ Checking readiness endpoint..."
if kubectl exec -n $NAMESPACE $POD_NAME -- curl -sf http://localhost:8000/ready &> /dev/null; then
    echo "   ✅ Readiness endpoint responding"
else
    echo "   ⚠️  Readiness endpoint not ready yet"
fi
echo ""

# Verificar métricas
echo "6️⃣ Checking metrics endpoint..."
if kubectl exec -n $NAMESPACE $POD_NAME -- curl -sf http://localhost:9090/metrics &> /dev/null; then
    echo "   ✅ Metrics endpoint responding"
    METRICS_COUNT=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s http://localhost:9090/metrics | grep -c "^queen_agent_" || true)
    echo "   📊 Found $METRICS_COUNT Queen Agent metrics"
else
    echo "   ⚠️  Metrics endpoint not responding yet"
fi
echo ""

# Verificar logs para erros
echo "7️⃣ Checking logs for errors..."
ERROR_COUNT=$(kubectl logs -n $NAMESPACE $POD_NAME --tail=100 | grep -i "error" | wc -l || true)
if [ $ERROR_COUNT -eq 0 ]; then
    echo "   ✅ No errors in recent logs"
else
    echo "   ⚠️  Found $ERROR_COUNT error(s) in recent logs:"
    kubectl logs -n $NAMESPACE $POD_NAME --tail=100 | grep -i "error" | head -5
fi
echo ""

# Verificar conexões com dependências
echo "8️⃣ Checking dependency connections..."
STARTUP_LOGS=$(kubectl logs -n $NAMESPACE $POD_NAME --tail=200)

if echo "$STARTUP_LOGS" | grep -q "MongoDB client initialized"; then
    echo "   ✅ MongoDB connection established"
else
    echo "   ⚠️  MongoDB connection not confirmed"
fi

if echo "$STARTUP_LOGS" | grep -q "Redis client initialized"; then
    echo "   ✅ Redis connection established"
else
    echo "   ⚠️  Redis connection not confirmed"
fi

if echo "$STARTUP_LOGS" | grep -q "Neo4j client initialized"; then
    echo "   ✅ Neo4j connection established"
else
    echo "   ⚠️  Neo4j connection not confirmed"
fi

if echo "$STARTUP_LOGS" | grep -q "Kafka consumer started"; then
    echo "   ✅ Kafka consumers started"
else
    echo "   ⚠️  Kafka consumers not started yet"
fi
echo ""

# Verificar HPA (se habilitado)
echo "9️⃣ Checking HorizontalPodAutoscaler..."
if kubectl get hpa $SERVICE_NAME -n $NAMESPACE &> /dev/null; then
    echo "   ✅ HPA configured"
    kubectl get hpa $SERVICE_NAME -n $NAMESPACE
else
    echo "   ℹ️  HPA not configured"
fi
echo ""

# Verificar ServiceMonitor (se habilitado)
echo "🔟 Checking ServiceMonitor..."
if kubectl get servicemonitor $SERVICE_NAME -n $NAMESPACE &> /dev/null; then
    echo "   ✅ ServiceMonitor configured"
else
    echo "   ℹ️  ServiceMonitor not configured"
fi
echo ""

echo "✅ Validation complete!"
echo ""
echo "📋 Summary:"
echo "  - Pods: $READY_PODS/$TOTAL_PODS ready"
echo "  - Service: Available with $ENDPOINTS endpoint(s)"
echo "  - Errors in logs: $ERROR_COUNT"
echo ""
