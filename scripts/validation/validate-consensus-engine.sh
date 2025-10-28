#!/bin/bash
set -euo pipefail

# Validation script for Consensus Engine
# Valida integração completa do motor de consenso

NAMESPACE="consensus-engine"

echo "========================================="
echo "Validando Consensus Engine..."
echo "========================================="

# 1. Verificar pods
echo ""
echo "1. Verificando pods..."
kubectl get pods -n ${NAMESPACE}

POD_COUNT=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine --field-selector=status.phase=Running -o json | jq '.items | length')
if [ "$POD_COUNT" -lt 1 ]; then
  echo "❌ ERRO: Nenhum pod em execução encontrado"
  exit 1
fi
echo "✅ Pods em execução: $POD_COUNT"

# 2. Verificar health endpoint
echo ""
echo "2. Verificando health endpoint..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
if kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/health 2>/dev/null; then
  echo "✅ Health endpoint OK"
else
  echo "❌ Health endpoint falhou"
  exit 1
fi

# 3. Verificar readiness endpoint
echo ""
echo "3. Verificando readiness endpoint..."
READINESS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8000/ready 2>/dev/null)
if echo "$READINESS" | jq -e '.ready == true' > /dev/null 2>&1; then
  echo "✅ Readiness endpoint OK"
  echo "   Checks:"
  echo "$READINESS" | jq '.checks'
else
  echo "⚠ Serviço não está pronto:"
  echo "$READINESS" | jq . || echo "$READINESS"
fi

# Função auxiliar para testar conectividade TCP
# Tenta primeiro com nc dentro do pod, depois com busybox temporário
test_tcp_connectivity() {
  local host=$1
  local port=$2
  local pod_name=$3
  local namespace=$4

  # Tentar nc dentro do pod
  if kubectl exec -n ${namespace} ${pod_name} -- which nc >/dev/null 2>&1; then
    if kubectl exec -n ${namespace} ${pod_name} -- nc -z -w 5 ${host} ${port} 2>/dev/null; then
      return 0
    fi
  fi

  # Fallback: usar busybox temporário para teste de rede
  if kubectl run tmp-netcheck-$$ --rm -i --image=busybox --restart=Never -- nc -z -w 5 ${host} ${port} >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

# 4. Verificar conectividade com especialistas via gRPC
echo ""
echo "4. Verificando conectividade com especialistas neurais..."
for specialist in business technical behavior evolution architecture; do
  SPECIALIST_HOST="specialist-${specialist}.specialist-${specialist}.svc.cluster.local"
  if test_tcp_connectivity ${SPECIALIST_HOST} 50051 ${POD_NAME} ${NAMESPACE}; then
    echo "✅ ${specialist} specialist alcançável"
  else
    echo "⚠ ${specialist} specialist não alcançável (pode precisar de tempo para iniciar)"
  fi
done

# 5. Verificar conectividade com MongoDB
echo ""
echo "5. Verificando conectividade com MongoDB..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 2>/dev/null | grep -qi "mongodb.*connected\|cognitive ledger.*initialized"; then
  echo "✅ MongoDB conectado"
else
  echo "⚠ Conexão MongoDB não confirmada nos logs"
fi

# 6. Verificar conectividade com Redis (feromônios)
echo ""
echo "6. Verificando conectividade com Redis..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 2>/dev/null | grep -qi "redis.*connected\|pheromone.*initialized"; then
  echo "✅ Redis conectado"
else
  echo "⚠ Conexão Redis não confirmada nos logs"
fi

# 7. Verificar conectividade com Kafka
echo ""
echo "7. Verificando conectividade com Kafka..."
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=100 2>/dev/null | grep -qi "kafka.*connected\|consumer.*started\|subscribed.*plans.ready"; then
  echo "✅ Kafka conectado"
else
  echo "⚠ Conexão Kafka não confirmada nos logs"
fi

# 8. Verificar APIs REST
echo ""
echo "8. Verificando APIs REST..."

# GET /health
echo "  - Testando GET /health..."
HTTP_CODE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
  echo "    ✅ Health endpoint OK (200)"
else
  echo "    ❌ Health endpoint failed (HTTP ${HTTP_CODE})"
fi

# GET /ready
echo "  - Testando GET /ready..."
HTTP_CODE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ready 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
  echo "    ✅ Ready endpoint OK (200)"
else
  echo "    ⚠ Ready endpoint not ready (HTTP ${HTTP_CODE})"
fi

# GET /api/v1/decisions/{decision_id}
echo "  - Testando GET /api/v1/decisions/test-id..."
HTTP_CODE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/decisions/test-id 2>/dev/null)
if [ "$HTTP_CODE" = "404" ]; then
  echo "    ✅ Decision API respondendo (404 esperado para ID inexistente)"
elif [ "$HTTP_CODE" = "200" ]; then
  echo "    ✅ Decision API respondendo (200)"
elif [[ "$HTTP_CODE" =~ ^5 ]]; then
  echo "    ❌ Decision API erro 5xx (HTTP ${HTTP_CODE})"
  RESPONSE=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8000/api/v1/decisions/test-id 2>/dev/null)
  echo "    Response: ${RESPONSE}"
else
  echo "    ⚠ Decision API resposta inesperada (HTTP ${HTTP_CODE})"
fi

# GET /api/v1/pheromones/stats
echo "  - Testando GET /api/v1/pheromones/stats..."
if kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -f http://localhost:8000/api/v1/pheromones/stats 2>/dev/null > /dev/null; then
  echo "    ✅ Pheromones API respondendo"
else
  echo "    ⚠ Pheromones API não responde"
fi

# 9. Verificar métricas Prometheus
echo ""
echo "9. Verificando métricas Prometheus..."
METRICS=$(kubectl exec -n ${NAMESPACE} ${POD_NAME} -- curl -s http://localhost:8080/metrics 2>/dev/null)
if echo "$METRICS" | grep -q "consensus_decisions_total\|bayesian_aggregation_duration_seconds\|process_cpu_seconds_total"; then
  echo "✅ Métricas Prometheus OK"

  # Contar métricas específicas
  DECISIONS_COUNT=$(echo "$METRICS" | grep -c "consensus_decisions_total" || echo "0")
  BAYESIAN_COUNT=$(echo "$METRICS" | grep -c "bayesian_aggregation_duration_seconds" || echo "0")
  VOTING_COUNT=$(echo "$METRICS" | grep -c "voting_ensemble_duration_seconds" || echo "0")

  echo "   - consensus_decisions_total: $DECISIONS_COUNT"
  echo "   - bayesian_aggregation_duration_seconds: $BAYESIAN_COUNT"
  echo "   - voting_ensemble_duration_seconds: $VOTING_COUNT"
else
  echo "❌ Métricas não encontradas"
  exit 1
fi

# 10. Verificar logs estruturados
echo ""
echo "10. Verificando logs estruturados..."
RECENT_LOGS=$(kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=10 2>/dev/null || echo "{}")
if echo "$RECENT_LOGS" | jq empty 2>/dev/null; then
  echo "✅ Logs em formato JSON estruturado"
else
  echo "⚠ Logs não estão em formato JSON (verificar configuração de logging)"
fi

# 11. Verificar ServiceMonitor
echo ""
echo "11. Verificando ServiceMonitor..."
if kubectl get servicemonitor -n ${NAMESPACE} consensus-engine &> /dev/null 2>&1; then
  echo "✅ ServiceMonitor existe"
else
  echo "⚠ ServiceMonitor não encontrado (pode não ter sido criado ainda)"
fi

# 12. Verificar Service
echo ""
echo "12. Verificando Service..."
if kubectl get svc -n ${NAMESPACE} consensus-engine &> /dev/null; then
  echo "✅ Service existe"
  kubectl get svc -n ${NAMESPACE} consensus-engine
else
  echo "❌ Service não encontrado"
  exit 1
fi

echo ""
echo "========================================="
echo "✅ Todas as validações críticas passaram!"
echo "========================================="
echo ""
echo "Próximos passos:"
echo "1. Executar teste de integração: ./tests/consensus-engine-integration-test.sh"
echo "2. Testar sistema de feromônios: ./tests/pheromone-system-test.sh"
echo "3. Publicar Cognitive Plan no Kafka e validar processamento"
echo "4. Verificar decisões no MongoDB"
echo "5. Verificar feromônios no Redis"
echo "6. Validar métricas no Grafana (se disponível)"
echo ""
echo "Comandos úteis:"
echo "  - Port-forward API: kubectl port-forward -n ${NAMESPACE} svc/consensus-engine 8000:8000"
echo "  - Ver logs: kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -f"
echo "  - Ver métricas: kubectl port-forward -n ${NAMESPACE} svc/consensus-engine 8080:8080 && curl http://localhost:8080/metrics"
echo ""
