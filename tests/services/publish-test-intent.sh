#!/usr/bin/env bash

# Script para publicar envelopes de intenção de teste no Kafka para testes manuais

set -euo pipefail

# Configuração
KAFKA_NAMESPACE="kafka"
KAFKA_BOOTSTRAP="neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
DEFAULT_TOPIC="intentions.business"

# Valores padrão
TOPIC="$DEFAULT_TOPIC"
DOMAIN="BUSINESS"
TEXT=""
PRIORITY="NORMAL"

# Função de ajuda
show_help() {
  cat <<EOF
Uso: $0 [OPTIONS]

Opções:
  --topic TOPIC       Tópico Kafka (padrão: intentions.business)
  --domain DOMAIN     Domínio da intenção (padrão: BUSINESS)
                      Valores: BUSINESS, TECHNICAL, INFRASTRUCTURE, SECURITY
  --text TEXT         Texto da intenção (obrigatório)
  --priority PRIORITY Prioridade (padrão: NORMAL)
                      Valores: LOW, NORMAL, HIGH, CRITICAL
  --help              Mostra esta mensagem de ajuda

Exemplos:
  # Intenção de negócio
  $0 --domain business --text "Criar fluxo de aprovação"

  # Intenção técnica
  $0 --domain technical --text "Implantar microsserviço" --topic intentions.technical

  # Alta prioridade
  $0 --domain business --text "Correção crítica de bug" --priority high

EOF
  exit 0
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
  case $1 in
    --topic)
      TOPIC="$2"
      shift 2
      ;;
    --domain)
      DOMAIN=$(echo "$2" | tr '[:lower:]' '[:upper:]')
      shift 2
      ;;
    --text)
      TEXT="$2"
      shift 2
      ;;
    --priority)
      PRIORITY=$(echo "$2" | tr '[:lower:]' '[:upper:]')
      shift 2
      ;;
    --help)
      show_help
      ;;
    *)
      echo "Argumento desconhecido: $1"
      show_help
      ;;
  esac
done

# Validação
if [ -z "$TEXT" ]; then
  echo "Erro: --text é obrigatório"
  show_help
fi

# Verificar conectividade kubectl
if ! kubectl cluster-info > /dev/null 2>&1; then
  echo "Erro: kubectl não pode conectar ao cluster"
  exit 1
fi

# Verificar namespace Kafka
if ! kubectl get namespace $KAFKA_NAMESPACE > /dev/null 2>&1; then
  echo "Erro: Namespace $KAFKA_NAMESPACE não encontrado"
  exit 1
fi

# Gerar envelope de intenção
INTENT_ID="test-intent-$(date +%s)-$RANDOM"
TIMESTAMP=$(date +%s%3N)
SESSION_ID="test-session-$(date +%s)"

INTENT_ENVELOPE=$(cat <<EOF
{
  "id": "$INTENT_ID",
  "version": "1.0.0",
  "timestamp": $TIMESTAMP,
  "actor": {
    "type": "HUMAN",
    "id": "test-user",
    "name": "Test User"
  },
  "intent": {
    "text": "$TEXT",
    "domain": "$DOMAIN",
    "classification": "test"
  },
  "confidence": 0.95,
  "context": {
    "sessionId": "$SESSION_ID",
    "userId": "test-user",
    "tenantId": "test-tenant",
    "channel": "API"
  },
  "constraints": {
    "priority": "$PRIORITY",
    "securityLevel": "INTERNAL"
  },
  "qos": {
    "deliveryMode": "EXACTLY_ONCE",
    "durability": "PERSISTENT"
  }
}
EOF
)

echo "=========================================="
echo "Envelope de Intenção de Teste"
echo "=========================================="
echo "$INTENT_ENVELOPE" | jq '.' 2>/dev/null || echo "$INTENT_ENVELOPE"
echo "=========================================="
echo ""

# Publicar no Kafka
PRODUCER_POD="kafka-producer-manual-$RANDOM"
echo "Criando pod produtor Kafka: $PRODUCER_POD"

kubectl run $PRODUCER_POD --restart=Never \
  --image=docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace=$KAFKA_NAMESPACE \
  --command -- sh -c "sleep 3600" > /dev/null 2>&1 || {
  echo "Erro: Falha ao criar pod produtor"
  exit 1
}

# Aguardar pod ficar pronto
echo "Aguardando pod ficar pronto..."
kubectl wait --for=condition=ready pod/$PRODUCER_POD -n $KAFKA_NAMESPACE --timeout=60s > /dev/null 2>&1 || {
  echo "Erro: Pod não ficou pronto"
  kubectl delete pod $PRODUCER_POD -n $KAFKA_NAMESPACE --force --grace-period=0 > /dev/null 2>&1 || true
  exit 1
}

# Publicar mensagem
echo "Publicando intenção no tópico: $TOPIC"
kubectl exec $PRODUCER_POD -n $KAFKA_NAMESPACE -- sh -c "echo '$INTENT_ENVELOPE' | kafka-console-producer.sh --bootstrap-server $KAFKA_BOOTSTRAP --topic $TOPIC" 2>&1 | grep -v "WARN" || {
  echo "Erro: Falha ao publicar mensagem"
  kubectl delete pod $PRODUCER_POD -n $KAFKA_NAMESPACE --force --grace-period=0 > /dev/null 2>&1 || true
  exit 1
}

# Limpar pod
echo "Limpando pod produtor..."
kubectl delete pod $PRODUCER_POD -n $KAFKA_NAMESPACE --force --grace-period=0 > /dev/null 2>&1 || true

echo ""
echo "=========================================="
echo "Intenção publicada com sucesso!"
echo "=========================================="
echo "ID da Intenção: $INTENT_ID"
echo "Tópico: $TOPIC"
echo ""
echo "Comandos de verificação:"
echo ""
echo "# Verificar logs do gateway"
echo "kubectl logs -n neural-hive-gateway -l app.kubernetes.io/name=gateway-intencoes | grep $INTENT_ID"
echo ""
echo "# Verificar logs do semantic-translation-engine"
echo "kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine | grep $INTENT_ID"
echo ""
echo "# Consumir do tópico Kafka para verificar mensagem"
echo "kubectl run kafka-consumer-test --restart=Never --image=docker.io/bitnami/kafka:4.0.0-debian-12-r10 --namespace=kafka --command -- kafka-console-consumer.sh --bootstrap-server $KAFKA_BOOTSTRAP --topic $TOPIC --from-beginning --max-messages 1"
echo "kubectl logs kafka-consumer-test -n kafka"
echo "kubectl delete pod kafka-consumer-test -n kafka --force --grace-period=0"
echo ""

exit 0
