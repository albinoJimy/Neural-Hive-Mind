#!/bin/bash
# Script de teste para notificações Slack do FluxCD
# Uso: ./test-slack-notifications.sh [dev|staging|prod]

set -e

ENV=${1:-dev}
NAMESPACE="flux-system"

echo "================================================"
echo "Teste de Notificações Slack - Ambiente: $ENV"
echo "================================================"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para verificar recurso
check_resource() {
  local resource_type=$1
  local resource_name=$2
  local expected_condition=$3

  echo -n "Checking $resource_type/$resource_name... "
  if kubectl get $resource_type $resource_name -n $NAMESPACE &>/dev/null; then
    echo -e "${GREEN}OK${NC}"
    return 0
  else
    echo -e "${RED}NOT FOUND${NC}"
    return 1
  fi
}

# Função para verificar secret do Slack
check_slack_secret() {
  echo -n "Checking slack-webhook secret... "
  if kubectl get secret slack-webhook -n $NAMESPACE &>/dev/null; then
    WEBHOOK_URL=$(kubectl get secret slack-webhook -n $NAMESPACE -o jsonpath='{.data.webhookUrl}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
    if [[ $WEBHOOK_URL == https://hooks.slack.com/services/* ]]; then
      echo -e "${GREEN}OK${NC}"
      echo "  Webhook URL: ${WEBHOOK_URL:0:30}..."
      return 0
    else
      echo -e "${YELLOW}MISSING WEBHOOK URL${NC}"
      echo "  Execute: kubectl create secret generic slack-webhook -n $NAMESPACE \\"
      echo "    --from-literal=webhookUrl='YOUR_WEBHOOK_URL'"
      return 1
    fi
  else
    echo -e "${RED}NOT FOUND${NC}"
    return 1
  fi
}

# Função para listar todos os alerts
list_alerts() {
  echo ""
  echo "Alerts configured:"
  echo "-------------------"
  kubectl get alert -n $NAMESPACE -o custom-columns="NAME:.metadata.name","PROVIDER:.spec.providerRef.name","SEVERITY:.eventSeverity" 2>/dev/null || echo "No alerts found"
}

# Função para mostrar eventos recentes
show_recent_events() {
  echo ""
  echo "Recent events (last 10):"
  echo "------------------------"
  kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' --field-selector type!=Normal 2>/dev/null | tail -10 || echo "No events found"
}

# Função para testar webhook manualmente
test_webhook_manual() {
  echo ""
  read -p "Testar webhook manualmente no Slack? (y/N) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    WEBHOOK_URL=$(kubectl get secret slack-webhook -n $NAMESPACE -o jsonpath='{.data.webhookUrl}' 2>/dev/null | base64 -d 2>/dev/null || "")
    if [[ -n $WEBHOOK_URL ]]; then
      echo "Enviando mensagem de teste para $ENV..."
      curl -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{
          \"text\": \"🧪 Teste de notificação FluxCD - Ambiente: $ENV\",
          \"username\": \"FluxCD Test\",
          \"icon_emoji\": \":bee:\"
        }" 2>/dev/null && echo -e "${GREEN}Mensagem enviada!${NC}" || echo -e "${RED}Falha ao enviar${NC}"
    else
      echo -e "${RED}Webhook URL não encontrada${NC}"
    fi
  fi
}

# Main execution
echo "Checking FluxCD Notification Components..."
echo ""

case $ENV in
  dev)
    PROVIDER_NAME="slack-dev"
    ;;
  staging)
    PROVIDER_NAME="slack-staging"
    ;;
  prod)
    PROVIDER_NAME="slack-prod"
    ;;
  *)
    echo -e "${RED}Ambiente inválido: $ENV${NC}"
    echo "Uso: $0 [dev|staging|prod]"
    exit 1
    ;;
esac

# Verificar componentes
RESULT=0
check_resource "provider" "$PROVIDER_NAME" || RESULT=1
check_slack_secret || RESULT=1

# Listar alerts
list_alerts

# Mostrar eventos recentes
show_recent_events

# Teste manual opcional
test_webhook_manual

# Resumo
echo ""
echo "================================================"
if [ $RESULT -eq 0 ]; then
  echo -e "${GREEN}✓ Componentes de notificação verificados${NC}"
  echo "Para troubleshoot, verifique:"
  echo "  - kubectl get provider -n $NAMESPACE"
  echo "  - kubectl get alert -n $NAMESPACE"
  echo "  - kubectl get events -n $NAMESPACE"
else
  echo -e "${RED}✗ Problemas encontrados - verifique acima${NC}"
  exit 1
fi
echo "================================================"
