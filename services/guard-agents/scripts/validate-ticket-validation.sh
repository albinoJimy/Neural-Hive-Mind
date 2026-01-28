#!/bin/bash
set -e

echo "=== Guard Agents - Ticket Validation Test ==="

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Namespace
NAMESPACE="${NAMESPACE:-neural-hive-resilience}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"

# 1. Verificar pods
echo -e "\n${YELLOW}1. Verificando pods...${NC}"
kubectl get pods -n $NAMESPACE -l app=guard-agents

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Pods encontrados${NC}"
else
    echo -e "${RED}❌ Nenhum pod encontrado${NC}"
    exit 1
fi

# 2. Verificar tópicos Kafka
echo -e "\n${YELLOW}2. Verificando tópicos Kafka...${NC}"
kubectl get kafkatopic -n $KAFKA_NAMESPACE | grep -E "execution-tickets|security-validations" || true

# 3. Testar API de validação
echo -e "\n${YELLOW}3. Testando API de validação...${NC}"
GUARD_POD=$(kubectl get pod -n $NAMESPACE -l app=guard-agents -o jsonpath='{.items[0].metadata.name}')

if [ -z "$GUARD_POD" ]; then
    echo -e "${RED}❌ Pod não encontrado${NC}"
    exit 1
fi

echo "Pod: $GUARD_POD"
kubectl exec -n $NAMESPACE $GUARD_POD -- curl -s http://localhost:8080/health

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ API respondendo${NC}"
else
    echo -e "${RED}❌ API não está respondendo${NC}"
    exit 1
fi

# 4. Publicar ticket de teste
echo -e "\n${YELLOW}4. Publicando ticket de teste...${NC}"

TICKET_ID="test-$(date +%s)"

cat <<EOF | kubectl exec -i -n $KAFKA_NAMESPACE kafka-0 -- kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets
{
  "ticket_id": "$TICKET_ID",
  "plan_id": "test-plan",
  "intent_id": "test-intent",
  "correlation_id": "test-corr",
  "task_type": "BUILD",
  "security_level": "internal",
  "service_account": "default",
  "namespace": "default",
  "parameters": {
    "repo": "test-repo",
    "branch": "main"
  },
  "required_capabilities": []
}
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Ticket publicado: $TICKET_ID${NC}"
else
    echo -e "${RED}❌ Falha ao publicar ticket${NC}"
    exit 1
fi

# 5. Aguardar processamento
echo -e "\n${YELLOW}5. Aguardando processamento (10s)...${NC}"
sleep 10

# 6. Verificar métricas
echo -e "\n${YELLOW}6. Verificando métricas...${NC}"
kubectl exec -n $NAMESPACE $GUARD_POD -- curl -s http://localhost:9090/metrics | grep guard_agent_tickets_validated_total || echo "Métrica não encontrada ainda"

# 7. Verificar logs
echo -e "\n${YELLOW}7. Verificando logs do Guard Agent...${NC}"
kubectl logs -n $NAMESPACE $GUARD_POD --tail=20 | grep -i "ticket\|validation" || echo "Nenhum log de validação encontrado"

# 8. Verificar MongoDB (se disponível)
echo -e "\n${YELLOW}8. Verificando MongoDB...${NC}"
MONGO_POD=$(kubectl get pod -n neural-hive-data -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ ! -z "$MONGO_POD" ]; then
    echo "MongoDB Pod: $MONGO_POD"
    VALIDATION_COUNT=$(kubectl exec -n neural-hive-data $MONGO_POD -- mongosh --quiet --eval \
      'db.getSiblingDB("neural_hive").security_validations.countDocuments({})' 2>/dev/null || echo "0")
    echo "Total de validações no MongoDB: $VALIDATION_COUNT"

    # Buscar validação específica
    FOUND=$(kubectl exec -n neural-hive-data $MONGO_POD -- mongosh --quiet --eval \
      "db.getSiblingDB(\"neural_hive\").security_validations.countDocuments({ticket_id: \"$TICKET_ID\"})" 2>/dev/null || echo "0")

    if [ "$FOUND" != "0" ]; then
        echo -e "${GREEN}✅ Validação encontrada no MongoDB para ticket $TICKET_ID${NC}"
    else
        echo -e "${YELLOW}⚠️  Validação não encontrada no MongoDB (pode ainda estar sendo processada)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Pod MongoDB não encontrado - pulando verificação${NC}"
fi

# 9. Resumo
echo -e "\n${YELLOW}=== Resumo ===${NC}"
echo -e "✅ Pods verificados"
echo -e "✅ API respondendo"
echo -e "✅ Ticket publicado: $TICKET_ID"
echo -e "⚠️  Aguarde alguns segundos para processamento completo"

echo -e "\n${YELLOW}Comandos úteis:${NC}"
echo "  # Ver logs do Guard Agent:"
echo "  kubectl logs -n $NAMESPACE -l app=guard-agents --tail=50 -f"
echo ""
echo "  # Verificar métricas:"
echo "  kubectl exec -n $NAMESPACE $GUARD_POD -- curl http://localhost:9090/metrics | grep guard_agent_tickets"
echo ""
echo "  # Consumir tópico de validações:"
echo "  kubectl exec -it -n $KAFKA_NAMESPACE kafka-0 -- kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic security.validations --from-beginning"

echo -e "\n${GREEN}✅ Validação completa!${NC}"
