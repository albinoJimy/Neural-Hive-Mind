#!/bin/bash
#
# test-e2e-grpc-debug.sh
# Script para enviar intent de teste via gateway-intencoes e provocar TypeError gRPC
#
# Uso: ./scripts/test/test-e2e-grpc-debug.sh [--port-forward]
#

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuração
NAMESPACE="neural-hive"
SERVICE_NAME="gateway-intencoes"
SERVICE_PORT="8000"
ENDPOINT_PATH="/intentions"
USE_PORT_FORWARD=false

# Parse argumentos
if [[ "${1:-}" == "--port-forward" ]]; then
  USE_PORT_FORWARD=true
fi

# Banner
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       Test E2E gRPC Debug - Neural Hive Mind                  ║${NC}"
echo -e "${CYAN}║       Envio de Intent para Provocar TypeError                 ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Função para cleanup
cleanup() {
  if [[ -n "${PORT_FORWARD_PID:-}" ]]; then
    echo -e "${YELLOW}[INFO] Encerrando port-forward (PID: $PORT_FORWARD_PID)...${NC}"
    kill "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Verificar kubectl
if ! command -v kubectl &> /dev/null; then
  echo -e "${RED}[ERROR] kubectl não encontrado. Instale kubectl primeiro.${NC}"
  exit 1
fi

# Verificar conectividade com cluster
echo -e "${BLUE}[1/6] Verificando conectividade com cluster Kubernetes...${NC}"
if ! kubectl cluster-info &> /dev/null; then
  echo -e "${RED}[ERROR] Não foi possível conectar ao cluster Kubernetes${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Cluster acessível${NC}"
echo ""

# Verificar namespace
echo -e "${BLUE}[2/6] Verificando namespace '$NAMESPACE'...${NC}"
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
  echo -e "${RED}[ERROR] Namespace '$NAMESPACE' não existe${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Namespace encontrado${NC}"
echo ""

# Verificar serviço gateway-intencoes
echo -e "${BLUE}[3/6] Verificando serviço '$SERVICE_NAME'...${NC}"
if ! kubectl get service "$SERVICE_NAME" -n "$NAMESPACE" &> /dev/null; then
  echo -e "${RED}[ERROR] Serviço '$SERVICE_NAME' não encontrado no namespace '$NAMESPACE'${NC}"
  exit 1
fi

# Verificar pods do gateway usando selector do Service ou fallback de labels
echo -e "${YELLOW}[INFO] Verificando pods do gateway-intencoes...${NC}"

# Try to get pod using primary label
POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

# Fallback to alternative label if not found
if [[ -z "$POD_NAME" ]]; then
  echo -e "${YELLOW}[INFO] Tentando label alternativa app.kubernetes.io/name=gateway-intencoes...${NC}"
  POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
fi

# Validate pod was found and is running
if [[ -z "$POD_NAME" ]]; then
  echo -e "${RED}[ERROR] Nenhum pod encontrado para gateway-intencoes${NC}"
  echo -e "${YELLOW}[INFO] Listando pods no namespace $NAMESPACE:${NC}"
  kubectl get pods -n "$NAMESPACE"
  exit 1
fi

POD_STATUS=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
POD_READY=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

if [[ "$POD_STATUS" != "Running" ]] || [[ "$POD_READY" != "True" ]]; then
  echo -e "${RED}[ERROR] Gateway-intencoes não está pronto (pod: $POD_NAME, status: $POD_STATUS, ready: $POD_READY)${NC}"
  echo -e "${YELLOW}[INFO] Detalhes do pod:${NC}"
  kubectl describe pod "$POD_NAME" -n "$NAMESPACE"
  exit 1
fi
echo -e "${GREEN}✓ Serviço gateway-intencoes ativo (pod: $POD_NAME, status: $POD_STATUS, ready: $POD_READY)${NC}"
echo ""

# Determinar URL do endpoint
echo -e "${BLUE}[4/6] Configurando endpoint de acesso...${NC}"
if [[ "$USE_PORT_FORWARD" == true ]]; then
  echo -e "${YELLOW}[INFO] Usando port-forward para acesso ao gateway${NC}"
  kubectl port-forward -n "$NAMESPACE" "svc/$SERVICE_NAME" "$SERVICE_PORT:$SERVICE_PORT" &> /dev/null &
  PORT_FORWARD_PID=$!
  sleep 3 # Aguardar port-forward inicializar
  GATEWAY_URL="http://localhost:$SERVICE_PORT"
else
  # Usar ClusterIP via kubectl run curl
  CLUSTER_IP=$(kubectl get service "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
  GATEWAY_URL="http://${CLUSTER_IP}:${SERVICE_PORT}"
  echo -e "${YELLOW}[INFO] Usando acesso direto ao ClusterIP: $CLUSTER_IP${NC}"
fi
echo -e "${GREEN}✓ Endpoint configurado: $GATEWAY_URL$ENDPOINT_PATH${NC}"
echo ""

# Gerar payload de teste
echo -e "${BLUE}[5/6] Preparando payload de teste...${NC}"
TIMESTAMP=$(date +%s)
CORRELATION_ID="test-grpc-debug-$TIMESTAMP"
INTENT_TEXT="Implementar autenticação multifator no sistema de acesso com verificação biométrica e tokens temporários"

PAYLOAD=$(cat <<EOF
{
  "text": "$INTENT_TEXT",
  "language": "pt-BR",
  "correlation_id": "$CORRELATION_ID"
}
EOF
)

echo -e "${CYAN}Payload:${NC}"
echo "$PAYLOAD" | jq '.' 2>/dev/null || echo "$PAYLOAD"
echo ""

# Enviar requisição
echo -e "${BLUE}[6/6] Enviando requisição HTTP POST...${NC}"
echo -e "${YELLOW}[INFO] Timestamp: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo ""

if [[ "$USE_PORT_FORWARD" == true ]]; then
  # Usar curl local via port-forward
  RESPONSE=$(curl -X POST "${GATEWAY_URL}${ENDPOINT_PATH}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    -w "\nHTTP_STATUS:%{http_code}" \
    -s 2>&1)
else
  # Usar kubectl run curl dentro do cluster
  RESPONSE=$(kubectl run curl-test-$TIMESTAMP \
    --rm -i --restart=Never \
    --image=curlimages/curl:latest \
    -n "$NAMESPACE" \
    -- curl -X POST "${GATEWAY_URL}${ENDPOINT_PATH}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    -w "\nHTTP_STATUS:%{http_code}" \
    -s 2>&1)
fi

# Extrair HTTP status
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d':' -f2)
RESPONSE_BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}                        RESPOSTA DO GATEWAY                       ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if [[ "$HTTP_STATUS" == "200" ]] || [[ "$HTTP_STATUS" == "201" ]]; then
  echo -e "${GREEN}✓ HTTP Status: $HTTP_STATUS (Sucesso)${NC}"
  echo ""

  # Parse resposta JSON
  echo -e "${CYAN}Response Body:${NC}"
  echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
  echo ""

  # Extrair IDs para correlação
  INTENT_ID=$(echo "$RESPONSE_BODY" | jq -r '.intent_id // empty' 2>/dev/null)
  PLAN_ID=$(echo "$RESPONSE_BODY" | jq -r '.plan_id // empty' 2>/dev/null)
  DOMAIN=$(echo "$RESPONSE_BODY" | jq -r '.domain // empty' 2>/dev/null)
  CONFIDENCE=$(echo "$RESPONSE_BODY" | jq -r '.confidence // empty' 2>/dev/null)

  echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}                  IDs PARA CORRELAÇÃO DE LOGS                    ${NC}"
  echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}Intent ID:       ${INTENT_ID:-N/A}${NC}"
  echo -e "${GREEN}Plan ID:         ${PLAN_ID:-N/A}${NC}"
  echo -e "${GREEN}Correlation ID:  ${CORRELATION_ID}${NC}"
  echo -e "${GREEN}Domain:          ${DOMAIN:-N/A}${NC}"
  echo -e "${GREEN}Confidence:      ${CONFIDENCE:-N/A}${NC}"
  echo ""

  echo -e "${YELLOW}[INFO] Use os IDs acima para filtrar logs capturados${NC}"
  echo -e "${YELLOW}[INFO] Aguarde 10-30 segundos para o fluxo E2E completar${NC}"
  echo ""

  # Sugerir comandos de follow-up
  echo -e "${CYAN}Comandos úteis para análise:${NC}"
  echo -e "${BLUE}# Logs do consensus-engine (onde TypeError ocorre):${NC}"
  if [[ -n "$PLAN_ID" ]]; then
    echo "kubectl logs -n $NAMESPACE -l app=consensus-engine --tail=100 | grep '$PLAN_ID'"
  else
    echo "kubectl logs -n $NAMESPACE -l app=consensus-engine --tail=100 | grep 'TypeError'"
  fi
  echo ""
  echo -e "${BLUE}# Logs dos specialists:${NC}"
  echo "kubectl logs -n $NAMESPACE -l app=specialist-business --tail=50 | grep 'EvaluatePlan'"
  echo ""

else
  echo -e "${RED}✗ HTTP Status: ${HTTP_STATUS:-UNKNOWN} (Erro)${NC}"
  echo ""
  echo -e "${RED}Response Body:${NC}"
  echo "$RESPONSE_BODY"
  echo ""
  echo -e "${YELLOW}[WARNING] Requisição falhou. Verifique:${NC}"
  echo "  - Status do gateway: kubectl get pods -n $NAMESPACE -l app=gateway-intencoes"
  echo "  - Logs do gateway: kubectl logs -n $NAMESPACE -l app=gateway-intencoes --tail=50"
  exit 1
fi

echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    TESTE CONCLUÍDO COM SUCESSO                 ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
