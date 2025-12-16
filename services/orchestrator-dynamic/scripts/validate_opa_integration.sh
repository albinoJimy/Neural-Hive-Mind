#!/bin/bash
# Script para validar integração OPA end-to-end

set -e

echo "=== Validação de Integração OPA ==="

# 1. Verificar OPA está rodando
echo "1. Verificando OPA Server..."
curl -s http://localhost:8181/health || {
    echo "❌ OPA Server não está acessível"
    exit 1
}
echo "✅ OPA Server acessível"

# 2. Verificar políticas carregadas
echo "2. Verificando políticas carregadas..."
curl -s http://localhost:8181/v1/policies | jq -r '.result[].id' | grep -q "neuralhive/orchestrator" || {
    echo "❌ Políticas não carregadas"
    exit 1
}
echo "✅ Políticas carregadas"

# 3. Testar política resource_limits
echo "3. Testando política resource_limits..."
curl -s -X POST http://localhost:8181/v1/data/neuralhive/orchestrator/resource_limits \
    -H "Content-Type: application/json" \
    -d '{"input": {"resource": {"ticket_id": "test", "risk_band": "high", "sla": {"timeout_ms": 60000, "max_retries": 3}, "required_capabilities": ["code_generation"]}, "parameters": {"allowed_capabilities": ["code_generation"], "max_concurrent_tickets": 100}, "context": {"total_tickets": 50}}}' \
    | jq -e '.result.allow == true' || {
    echo "❌ Política resource_limits falhou"
    exit 1
}
echo "✅ Política resource_limits OK"

# 4. Testar política sla_enforcement
echo "4. Testando política sla_enforcement..."
CURRENT_TIME=$(date +%s)000
DEADLINE=$((CURRENT_TIME + 3600000))
curl -s -X POST http://localhost:8181/v1/data/neuralhive/orchestrator/sla_enforcement \
    -H "Content-Type: application/json" \
    -d "{\"input\": {\"resource\": {\"ticket_id\": \"test\", \"risk_band\": \"high\", \"sla\": {\"timeout_ms\": 120000, \"deadline\": $DEADLINE}, \"qos\": {\"delivery_mode\": \"EXACTLY_ONCE\", \"consistency\": \"STRONG\"}, \"priority\": \"HIGH\", \"estimated_duration_ms\": 60000}, \"context\": {\"current_time\": $CURRENT_TIME}}}" \
    | jq -e '.result.allow == true' || {
    echo "❌ Política sla_enforcement falhou"
    exit 1
}
echo "✅ Política sla_enforcement OK"

# 5. Testar política feature_flags
echo "5. Testando política feature_flags..."
curl -s -X POST http://localhost:8181/v1/data/neuralhive/orchestrator/feature_flags \
    -H "Content-Type: application/json" \
    -d '{"input": {"resource": {"ticket_id": "test", "risk_band": "critical"}, "flags": {"intelligent_scheduler_enabled": true, "scheduler_namespaces": ["production"]}, "context": {"namespace": "production", "current_load": 0.5, "tenant_id": "test", "queue_depth": 50, "current_time": 1234567890000, "model_accuracy": 0.9}}}' \
    | jq -e '.result.enable_intelligent_scheduler == true' || {
    echo "❌ Política feature_flags falhou"
    exit 1
}
echo "✅ Política feature_flags OK"

# 6. Testar política security_constraints
echo "6. Testando política security_constraints..."
curl -s -X POST http://localhost:8181/v1/data/neuralhive/orchestrator/security_constraints \
    -H "Content-Type: application/json" \
    -d '{"input": {"resource": {"ticket_id": "test", "tenant_id": "allowed-tenant"}, "security": {"allowed_tenants": ["allowed-tenant"], "spiffe_enabled": false}, "context": {"user_id": "test-user", "current_time": 1234567890000}}}' \
    | jq -e '.result.allow == true' || {
    echo "❌ Política security_constraints falhou"
    exit 1
}
echo "✅ Política security_constraints OK"

# 7. Executar testes de integração
echo "7. Executando testes de integração..."
cd /jimy/Neural-Hive-Mind/services/orchestrator-dynamic
pytest tests/integration/test_opa_real_server.py -v || {
    echo "❌ Testes de integração falharam"
    exit 1
}
echo "✅ Testes de integração OK"

echo ""
echo "=== ✅ Validação de Integração OPA Completa ==="
