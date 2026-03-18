#!/bin/bash
set -e

NAMESPACE="neural-hive-orchestration"
SERVICE="optimizer-agents"

echo "=== Validando Deployment do Optimizer Agents ==="

# 1. Verificar se pod está rodando
echo "[1/8] Verificando status do pod..."
kubectl get pods -n $NAMESPACE -l app=$SERVICE
kubectl wait --for=condition=ready pod -l app=$SERVICE -n $NAMESPACE --timeout=120s

# 2. Verificar logs de inicialização
echo "[2/8] Verificando logs de inicialização..."
POD=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n $NAMESPACE $POD --tail=50 | grep "optimizer_agents_started"

# 3. Testar health check HTTP
echo "[3/8] Testando health check HTTP..."
kubectl exec -n $NAMESPACE $POD -- curl -f http://localhost:8000/health || exit 1

# 4. Testar health check gRPC
echo "[4/8] Testando health check gRPC..."
kubectl exec -n $NAMESPACE $POD -- grpcurl -plaintext localhost:50051 optimizer_agent.OptimizerAgent/HealthCheck

# 5. Verificar conexões com dependências
echo "[5/8] Verificando conexões..."
kubectl logs -n $NAMESPACE $POD | grep -E "(mongodb_client_initialized|redis_client_initialized|kafka.*initialized)"

# 6. Verificar métricas Prometheus
echo "[6/8] Verificando métricas Prometheus..."
kubectl exec -n $NAMESPACE $POD -- curl -s http://localhost:9090/metrics | grep "optimizer_"

# 7. Verificar ServiceMonitor
echo "[7/8] Verificando ServiceMonitor..."
kubectl get servicemonitor -n $NAMESPACE $SERVICE

# 8. Verificar registro no Service Registry
echo "[8/8] Verificando registro no Service Registry..."
kubectl logs -n $NAMESPACE $POD | grep "agent_registered"

echo "✅ Validação completa! Optimizer Agents está operacional."
