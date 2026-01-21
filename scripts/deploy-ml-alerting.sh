#!/bin/bash
# ==========================================================================
# Deploy ML Alerting Configuration
# ==========================================================================
# Este script faz o deployment da configuracao de alerting ML no Kubernetes.
#
# Uso:
#   ./scripts/deploy-ml-alerting.sh
#
# Pre-requisitos:
#   - kubectl configurado e conectado ao cluster
#   - Namespace 'monitoring' existente
#   - Alertmanager e Prometheus ja deployados
# ==========================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Namespaces
NAMESPACE_MONITORING="monitoring"

# Diretorio base do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Deploy ML Alerting Configuration${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Verificar se kubectl esta disponivel
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Erro: kubectl nao encontrado${NC}"
    exit 1
fi

# Verificar se namespace monitoring existe
if ! kubectl get namespace "$NAMESPACE_MONITORING" &> /dev/null; then
    echo -e "${RED}Erro: Namespace '$NAMESPACE_MONITORING' nao existe${NC}"
    exit 1
fi

# 1. Criar ConfigMap com templates Slack
echo -e "${YELLOW}[1/6] Criando ConfigMap com templates Slack...${NC}"
if [ -f "$PROJECT_ROOT/monitoring/alertmanager/ml-message-template.tmpl" ]; then
    kubectl create configmap alertmanager-ml-templates \
        --from-file=ml-message-template.tmpl="$PROJECT_ROOT/monitoring/alertmanager/ml-message-template.tmpl" \
        -n "$NAMESPACE_MONITORING" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo -e "${GREEN}  ConfigMap alertmanager-ml-templates criado/atualizado${NC}"
else
    echo -e "${RED}  Arquivo ml-message-template.tmpl nao encontrado${NC}"
    exit 1
fi

# 2. Aplicar configuracao Alertmanager ML
echo -e "${YELLOW}[2/6] Aplicando configuracao Alertmanager ML...${NC}"
if [ -f "$PROJECT_ROOT/monitoring/alertmanager/ml-slack-config.yaml" ]; then
    kubectl apply -f "$PROJECT_ROOT/monitoring/alertmanager/ml-slack-config.yaml"
    echo -e "${GREEN}  Configuracao Alertmanager ML aplicada${NC}"
else
    echo -e "${RED}  Arquivo ml-slack-config.yaml nao encontrado${NC}"
    exit 1
fi

# 3. Verificar se Alertmanager esta rodando
echo -e "${YELLOW}[3/6] Verificando Alertmanager...${NC}"
if kubectl get pod -n "$NAMESPACE_MONITORING" -l app.kubernetes.io/name=alertmanager -o name &> /dev/null; then
    ALERTMANAGER_POD=$(kubectl get pod -n "$NAMESPACE_MONITORING" -l app.kubernetes.io/name=alertmanager -o name | head -1)
    if [ -n "$ALERTMANAGER_POD" ]; then
        echo -e "${GREEN}  Alertmanager encontrado: $ALERTMANAGER_POD${NC}"

        # Tentar recarregar configuracao
        echo -e "${YELLOW}[4/6] Recarregando configuracao do Alertmanager...${NC}"
        kubectl exec -n "$NAMESPACE_MONITORING" "${ALERTMANAGER_POD}" -- kill -HUP 1 2>/dev/null || \
            echo -e "${YELLOW}  Aviso: Nao foi possivel enviar SIGHUP. Pode ser necessario reiniciar o pod.${NC}"
        echo -e "${GREEN}  Sinal de reload enviado${NC}"
    fi
else
    echo -e "${YELLOW}  Alertmanager nao encontrado. Pulando reload.${NC}"
fi

# 5. Aplicar regras Prometheus ML
echo -e "${YELLOW}[5/6] Aplicando regras Prometheus ML...${NC}"
if [ -f "$PROJECT_ROOT/prometheus-rules/ml-drift-alerts.yaml" ]; then
    kubectl apply -f "$PROJECT_ROOT/prometheus-rules/ml-drift-alerts.yaml"
    echo -e "${GREEN}  Regras de drift aplicadas${NC}"
fi
if [ -f "$PROJECT_ROOT/prometheus-rules/ml-slo-alerts.yaml" ]; then
    kubectl apply -f "$PROJECT_ROOT/prometheus-rules/ml-slo-alerts.yaml"
    echo -e "${GREEN}  Regras de SLO aplicadas${NC}"
fi

# 6. Verificar configuracao
echo -e "${YELLOW}[6/6] Verificando configuracao...${NC}"
echo ""

# Verificar ConfigMaps
echo -e "${BLUE}ConfigMaps criados:${NC}"
kubectl get configmap -n "$NAMESPACE_MONITORING" | grep -E "alertmanager-ml|ml-templates" || echo "  Nenhum ConfigMap ML encontrado"
echo ""

# Verificar PrometheusRules
echo -e "${BLUE}PrometheusRules ML:${NC}"
kubectl get prometheusrule -n "$NAMESPACE_MONITORING" | grep -E "ml-drift|ml-slo" || echo "  Nenhuma rule ML encontrada"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment concluido com sucesso!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Proximos passos:${NC}"
echo "  1. Configure Slack webhook URL no Secret:"
echo "     kubectl edit secret alertmanager-secrets -n monitoring"
echo ""
echo "  2. Teste um alerta:"
echo "     ./scripts/test-ml-alert.sh"
echo ""
echo "  3. Consulte a documentacao:"
echo "     docs/operations/alert-management.md"
echo ""
