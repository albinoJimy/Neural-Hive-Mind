#!/bin/bash
# Script de Teste - Validação Fix Cognitive Plan Aninhado
# Data: 2026-02-25
# Uso: ./test_fix_validation.sh

set -e

echo "========================================="
echo "Teste Validação Fix Cognitive Plan Aninhado"
echo "========================================="
echo ""

NAMESPACE="neural-hive"
GATEWAY_POD=$(kubectl get pods -n $NAMESPACE -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}')
ORCHESTRATOR_POD=$(kubectl get pods -n $NAMESPACE -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')
APPROVAL_POD=$(kubectl get pods -n $NAMESPACE -l app=approval-service -o jsonpath='{.items[0].metadata.name}')

echo "1. Verificando status dos pods..."
echo "   Gateway: $GATEWAY_POD"
echo "   Orchestrator: $ORCHESTRATOR_POD"
echo "   Approval: $APPROVAL_POD"

# Check if pods are ready
GATEWAY_READY=$(kubectl get pod $GATEWAY_POD -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].ready}')
ORCHESTRATOR_READY=$(kubectl get pod $ORCHESTRATOR_POD -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].ready}')
APPROVAL_READY=$(kubectl get pod $APPROVAL_POD -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].ready}')

if [[ "$GATEWAY_READY" != "true" ]] || [[ "$ORCHESTRATOR_READY" != "true" ]] || [[ "$APPROVAL_READY" != "true" ]]; then
    echo "   ❌ Um ou mais pods não estão prontos"
    exit 1
fi
echo "   ✅ Todos os pods estão prontos"
echo ""

echo "2. Verificando fix no Orchestrator..."
FIX_IN_ORCHESTRATOR=$(kubectl exec $ORCHESTRATOR_POD -n $NAMESPACE -- \
    grep -c "FIX: Lidar com estrutura aninhada" /app/src/activities/ticket_generation.py 2>/dev/null || echo "0")

if [[ "$FIX_IN_ORCHESTRATOR" -gt "0" ]]; then
    echo "   ✅ Fix encontrado no Orchestrator"
else
    echo "   ❌ Fix NÃO encontrado no Orchestrator"
    exit 1
fi
echo ""

echo "3. Verificando fix no Approval Service..."
FIX_IN_APPROVAL=$(kubectl exec $APPROVAL_POD -n $NAMESPACE -- \
    grep -c "FIX: Extrair plano completo da estrutura aninhada" /app/src/services/approval_service.py 2>/dev/null || echo "0")

if [[ "$FIX_IN_APPROVAL" -gt "0" ]]; then
    echo "   ✅ Fix encontrado no Approval Service"
else
    echo "   ❌ Fix NÃO encontrado no Approval Service"
    exit 1
fi
echo ""

echo "4. Enviando intenção de teste..."
INTENTION_RESPONSE=$(kubectl exec $ORCHESTRATOR_POD -n $NAMESPACE -- \
    curl -s -X POST http://gateway-intencoes.$NAMESPACE.svc.cluster.local:8000/intentions \
    -H "Content-Type: application/json" \
    -d '{
        "text": "deploy microservico teste validacao fix cognitive plan aninhado",
        "user_id": "test-fix-validation-2026-02-25"
    }')

INTENT_ID=$(echo $INTENTION_RESPONSE | grep -o '"intent_id":"[^"]*' | cut -d'"' -f4)

if [[ -z "$INTENT_ID" ]]; then
    echo "   ❌ Falha ao enviar intenção"
    echo "   Response: $INTENTION_RESPONSE"
    exit 1
fi

echo "   ✅ Intenção enviada"
echo "   Intent ID: $INTENT_ID"
echo ""

echo "5. Aguardando geração do plano (10s)..."
sleep 10

echo "6. Buscando Plan ID dos logs..."
kubectl logs $ORCHESTRATOR_POD -n $NAMESPACE --tail=100 | grep "$INTENT_ID" | grep "plan_id" > /tmp/plan_search.txt

PLAN_ID=$(grep -o '"plan_id":"[^"]*' /tmp/plan_search.txt | head -1 | cut -d'"' -f4)

if [[ -z "$PLAN_ID" ]]; then
    echo "   ⚠️  Plan ID não encontrado nos logs (pode ainda estar processando)"
    echo "   Para verificar manualmente:"
    echo "   kubectl logs $ORCHESTRATOR_POD -n $NAMESPACE | grep $INTENT_ID"
else
    echo "   ✅ Plan ID encontrado: $PLAN_ID"
fi
echo ""

echo "7. Verificando decisão do Consensus Engine..."
DECISION=$(kubectl logs $ORCHESTRATOR_POD -n $NAMESPACE --tail=200 | grep -A 5 "$INTENT_ID" | grep "final_decision" | head -1)
echo "   $DECISION"
echo ""

echo "========================================="
echo "Resumo do Teste"
echo "========================================="
echo ""
echo "✅ Deploy validado:"
echo "   - Orchestrator: Fix presente"
echo "   - Approval Service: Fix presente"
echo "   - Todos os pods: Running"
echo ""
echo "📋 IDs de Rastreamento:"
echo "   - Intent ID: $INTENT_ID"
if [[ -n "$PLAN_ID" ]]; then
    echo "   - Plan ID: $PLAN_ID"
fi
echo ""
echo "⏳ Próximos Passos:"
echo "   1. Verificar se o plano foi aprovado automaticamente"
echo "   2. Se 'review_required', aprovar manualmente via API"
echo "   3. Verificar se o workflow foi iniciado"
echo "   4. Verificar se tickets foram gerados"
echo ""
echo "Comandos úteis:"
echo "   # Verificar logs do orchestrator"
echo "   kubectl logs $ORCHESTRATOR_POD -n $NAMESPACE | grep $INTENT_ID"
echo ""
echo "   # Verificar logs do approval"
echo "   kubectl logs $APPROVAL_POD -n $NAMESPACE | grep $PLAN_ID"
echo ""
echo "   # Verificar tickets gerados"
echo "   kubectl logs $ORCHESTRATOR_POD -n $NAMESPACE | grep 'Gerando execution tickets'"
echo ""
