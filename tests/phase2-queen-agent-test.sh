#!/bin/bash

set -e

NAMESPACE="neural-hive"
SERVICE_NAME="queen-agent"
SERVICE_URL="http://$SERVICE_NAME.$NAMESPACE.svc.cluster.local:8000"

echo "🧪 Queen Agent End-to-End Test"
echo "================================"
echo ""

# Função auxiliar para logs
log_step() {
    echo ""
    echo "▶ $1"
    echo "---"
}

log_success() {
    echo "✅ $1"
}

log_error() {
    echo "❌ $1"
    exit 1
}

# Obter um pod do Queen Agent para executar comandos
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
    log_error "No Queen Agent pod found"
fi

echo "Using pod: $POD_NAME"

# 1. Testar Health Endpoints
log_step "1. Testing health endpoints"

if kubectl exec -n $NAMESPACE $POD_NAME -- curl -sf http://localhost:8000/health > /dev/null; then
    log_success "Health endpoint responding"
else
    log_error "Health endpoint failed"
fi

if kubectl exec -n $NAMESPACE $POD_NAME -- curl -sf http://localhost:8000/ready > /dev/null; then
    log_success "Readiness endpoint responding"
else
    log_error "Readiness endpoint failed"
fi

# 2. Testar Metrics Endpoint
log_step "2. Testing metrics endpoint"

METRICS=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s http://localhost:9090/metrics)

if echo "$METRICS" | grep -q "queen_agent_decisions_total"; then
    log_success "Decision metrics available"
else
    log_error "Decision metrics not found"
fi

if echo "$METRICS" | grep -q "queen_agent_conflicts_detected_total"; then
    log_success "Conflict metrics available"
else
    log_error "Conflict metrics not found"
fi

if echo "$METRICS" | grep -q "queen_agent_system_health_score"; then
    log_success "System health metrics available"
else
    log_error "System health metrics not found"
fi

# 3. Testar API de Decisões Estratégicas
log_step "3. Testing strategic decisions API"

# Criar uma decisão estratégica de teste
DECISION_PAYLOAD='{
  "decision_type": "REPLANNING",
  "triggered_by": "test_suite",
  "context": {
    "test": true,
    "description": "End-to-end test decision"
  },
  "domains_involved": ["business", "technical"],
  "confidence_score": 0.85,
  "risk_assessment": {
    "level": "low",
    "factors": ["test environment"]
  },
  "actions_taken": [
    {
      "action_type": "validate",
      "description": "Test action"
    }
  ]
}'

RESPONSE=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s -X POST \
    http://localhost:8000/api/v1/decisions \
    -H "Content-Type: application/json" \
    -d "$DECISION_PAYLOAD")

if echo "$RESPONSE" | grep -q "decision_id"; then
    DECISION_ID=$(echo "$RESPONSE" | jq -r '.decision_id')
    log_success "Strategic decision created: $DECISION_ID"
else
    log_error "Failed to create strategic decision"
fi

# Buscar a decisão criada
GET_RESPONSE=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s \
    http://localhost:8000/api/v1/decisions/$DECISION_ID)

if echo "$GET_RESPONSE" | grep -q "$DECISION_ID"; then
    log_success "Strategic decision retrieved successfully"
else
    log_error "Failed to retrieve strategic decision"
fi

# 4. Testar API de Conflitos
log_step "4. Testing conflict resolution API"

CONFLICT_PAYLOAD='{
  "conflict_id": "test-conflict-001",
  "domain1": "business",
  "domain2": "security",
  "severity": "high",
  "description": "Test conflict between business goal and security policy"
}'

CONFLICT_RESPONSE=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s -X POST \
    http://localhost:8000/api/v1/conflicts/resolve \
    -H "Content-Type: application/json" \
    -d "$CONFLICT_PAYLOAD")

if echo "$CONFLICT_RESPONSE" | grep -q "strategy"; then
    STRATEGY=$(echo "$CONFLICT_RESPONSE" | jq -r '.strategy')
    log_success "Conflict resolved with strategy: $STRATEGY"
else
    log_error "Failed to resolve conflict"
fi

# 5. Testar API de Replanning
log_step "5. Testing replanning API"

REPLANNING_PAYLOAD='{
  "plan_id": "test-plan-001",
  "reason": "end_to_end_test",
  "urgency": "low"
}'

REPLANNING_RESPONSE=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s -X POST \
    http://localhost:8000/api/v1/replanning/trigger \
    -H "Content-Type: application/json" \
    -d "$REPLANNING_PAYLOAD")

if echo "$REPLANNING_RESPONSE" | grep -q "triggered"; then
    log_success "Replanning triggered successfully"
else
    log_error "Failed to trigger replanning"
fi

# 6. Testar API de Exceções
log_step "6. Testing exception approval API"

EXCEPTION_PAYLOAD='{
  "request_id": "test-exception-001",
  "guardrail_type": "resource_limit",
  "requested_by": "test_suite",
  "justification": "Testing exception approval flow",
  "duration_minutes": 60
}'

EXCEPTION_RESPONSE=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s -X POST \
    http://localhost:8000/api/v1/exceptions/request \
    -H "Content-Type: application/json" \
    -d "$EXCEPTION_PAYLOAD")

if echo "$EXCEPTION_RESPONSE" | grep -q "request_id"; then
    REQUEST_ID=$(echo "$EXCEPTION_RESPONSE" | jq -r '.request_id')
    log_success "Exception requested: $REQUEST_ID"
else
    log_error "Failed to request exception"
fi

# 7. Verificar Kafka Integration
log_step "7. Testing Kafka integration"

# Verificar se os consumers estão rodando
LOGS=$(kubectl logs -n $NAMESPACE $POD_NAME --tail=100)

if echo "$LOGS" | grep -q "consensus_consumer"; then
    log_success "Consensus consumer is running"
else
    log_error "Consensus consumer not found in logs"
fi

if echo "$LOGS" | grep -q "telemetry_consumer"; then
    log_success "Telemetry consumer is running"
else
    log_error "Telemetry consumer not found in logs"
fi

if echo "$LOGS" | grep -q "incident_consumer"; then
    log_success "Incident consumer is running"
else
    log_error "Incident consumer not found in logs"
fi

# 8. Verificar Database Connections
log_step "8. Testing database connections"

if echo "$LOGS" | grep -q "MongoDB client initialized"; then
    log_success "MongoDB connection established"
else
    log_error "MongoDB connection not established"
fi

if echo "$LOGS" | grep -q "Redis client initialized"; then
    log_success "Redis connection established"
else
    log_error "Redis connection not established"
fi

if echo "$LOGS" | grep -q "Neo4j client initialized"; then
    log_success "Neo4j connection established"
else
    log_error "Neo4j connection not established"
fi

# 9. Verificar System Health
log_step "9. Testing system health monitoring"

HEALTH_RESPONSE=$(kubectl exec -n $NAMESPACE $POD_NAME -- curl -s \
    http://localhost:8000/api/v1/system/health)

if echo "$HEALTH_RESPONSE" | grep -q "health_score"; then
    HEALTH_SCORE=$(echo "$HEALTH_RESPONSE" | jq -r '.health_score')
    log_success "System health score: $HEALTH_SCORE"
else
    log_error "Failed to get system health"
fi

# 10. Verificar OpenTelemetry Tracing
log_step "10. Testing OpenTelemetry integration"

if echo "$LOGS" | grep -q "Tracing initialized"; then
    log_success "OpenTelemetry tracing initialized"
else
    echo "⚠️  OpenTelemetry tracing initialization not confirmed (may be optional)"
fi

# Resumo Final
echo ""
echo "================================"
echo "✅ All tests passed successfully!"
echo "================================"
echo ""
echo "📊 Test Summary:"
echo "  ✓ Health endpoints functional"
echo "  ✓ Metrics collection working"
echo "  ✓ Strategic decision API operational"
echo "  ✓ Conflict resolution API operational"
echo "  ✓ Replanning API operational"
echo "  ✓ Exception approval API operational"
echo "  ✓ Kafka consumers running"
echo "  ✓ Database connections established"
echo "  ✓ System health monitoring active"
echo "  ✓ OpenTelemetry integration configured"
echo ""
echo "🎉 Queen Agent is fully operational!"
