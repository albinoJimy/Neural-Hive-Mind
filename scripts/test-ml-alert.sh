#!/bin/bash
# ==========================================================================
# Test ML Alert
# ==========================================================================
# Este script envia um alerta de teste para validar a configuracao de alerting ML.
#
# Uso:
#   ./scripts/test-ml-alert.sh                    # Envia alerta critico de teste
#   ./scripts/test-ml-alert.sh warning            # Envia alerta warning de teste
#   ./scripts/test-ml-alert.sh resolve            # Envia alerta resolvido
#
# Pre-requisitos:
#   - kubectl configurado e conectado ao cluster
#   - Alertmanager acessivel via port-forward ou service
# ==========================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Namespace
NAMESPACE_MONITORING="monitoring"

# Tipo de alerta (critical, warning, resolve)
ALERT_TYPE="${1:-critical}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Test ML Alert - $ALERT_TYPE${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Verificar se kubectl esta disponivel
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Erro: kubectl nao encontrado${NC}"
    exit 1
fi

# Obter URL do Alertmanager
echo -e "${YELLOW}Obtendo acesso ao Alertmanager...${NC}"

# Tentar port-forward em background
ALERTMANAGER_URL="http://localhost:9093"
PORT_FORWARD_PID=""

# Verificar se ja existe port-forward
if ! curl -s "${ALERTMANAGER_URL}/api/v1/status" &> /dev/null; then
    echo -e "${YELLOW}Iniciando port-forward para Alertmanager...${NC}"
    kubectl port-forward -n "$NAMESPACE_MONITORING" svc/alertmanager 9093:9093 &
    PORT_FORWARD_PID=$!
    sleep 3

    # Verificar se port-forward funcionou
    if ! curl -s "${ALERTMANAGER_URL}/api/v1/status" &> /dev/null; then
        echo -e "${RED}Erro: Nao foi possivel conectar ao Alertmanager${NC}"
        kill $PORT_FORWARD_PID 2>/dev/null || true
        exit 1
    fi
fi

# Funcao para cleanup
cleanup() {
    if [ -n "$PORT_FORWARD_PID" ]; then
        echo -e "${YELLOW}Encerrando port-forward...${NC}"
        kill $PORT_FORWARD_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Timestamp atual
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Construir payload baseado no tipo de alerta
case "$ALERT_TYPE" in
    critical)
        echo -e "${RED}Enviando alerta CRITICO de teste...${NC}"
        PAYLOAD='[{
            "labels": {
                "alertname": "MLDriftCritical",
                "severity": "critical",
                "neural_hive_component": "ml-models",
                "neural_hive_layer": "cognicao",
                "specialist_type": "technical"
            },
            "annotations": {
                "summary": "TESTE: Drift critico detectado",
                "description": "Este e um alerta de teste para validar a configuracao de alerting ML. NAO REQUER ACAO.",
                "current_value": "0.35",
                "threshold": "0.25",
                "runbook_url": "https://docs.neural-hive.local/runbooks/ml-drift-critical",
                "dashboard_url": "https://grafana.neural-hive.local/d/ml-slos-dashboard/ml-slos",
                "impact": "TESTE - Este alerta nao representa um problema real"
            },
            "startsAt": "'$TIMESTAMP'",
            "generatorURL": "http://prometheus.monitoring:9090/test"
        }]'
        ;;
    warning)
        echo -e "${YELLOW}Enviando alerta WARNING de teste...${NC}"
        PAYLOAD='[{
            "labels": {
                "alertname": "MLModelDegraded",
                "severity": "warning",
                "neural_hive_component": "ml-models",
                "neural_hive_layer": "cognicao",
                "specialist_type": "technical"
            },
            "annotations": {
                "summary": "TESTE: Modelo degradado",
                "description": "Este e um alerta de teste para validar a configuracao de alerting ML. NAO REQUER ACAO.",
                "current_value": "0.68",
                "threshold": "0.72",
                "runbook_url": "https://docs.neural-hive.local/runbooks/model-degraded",
                "dashboard_url": "https://grafana.neural-hive.local/d/ml-slos-dashboard/ml-slos"
            },
            "startsAt": "'$TIMESTAMP'",
            "generatorURL": "http://prometheus.monitoring:9090/test"
        }]'
        ;;
    resolve)
        echo -e "${GREEN}Enviando alerta RESOLVED de teste...${NC}"
        END_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        PAYLOAD='[{
            "labels": {
                "alertname": "MLDriftCritical",
                "severity": "critical",
                "neural_hive_component": "ml-models",
                "neural_hive_layer": "cognicao",
                "specialist_type": "technical"
            },
            "annotations": {
                "summary": "TESTE: Drift critico detectado",
                "description": "Este e um alerta de teste para validar a configuracao de alerting ML.",
                "resolution_summary": "Alerta de teste resolvido automaticamente"
            },
            "startsAt": "'$TIMESTAMP'",
            "endsAt": "'$END_TIMESTAMP'",
            "generatorURL": "http://prometheus.monitoring:9090/test"
        }]'
        ;;
    *)
        echo -e "${RED}Erro: Tipo de alerta invalido. Use: critical, warning, ou resolve${NC}"
        exit 1
        ;;
esac

# Enviar alerta
echo -e "${YELLOW}Enviando alerta para Alertmanager...${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${ALERTMANAGER_URL}/api/v1/alerts" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}Alerta enviado com sucesso!${NC}"
    echo ""
    echo -e "${BLUE}Detalhes:${NC}"
    echo "  Tipo: $ALERT_TYPE"
    echo "  Alertname: $(echo "$PAYLOAD" | grep -o '"alertname"[^,]*' | head -1 | cut -d'"' -f4)"
    echo "  Specialist: technical"
    echo "  Timestamp: $TIMESTAMP"
    echo ""
    echo -e "${BLUE}Verifique:${NC}"
    echo "  - Canal Slack #ml-alerts"
    echo "  - Alertmanager UI: http://localhost:9093"
    echo ""
    echo -e "${YELLOW}Para resolver o alerta de teste, execute:${NC}"
    echo "  ./scripts/test-ml-alert.sh resolve"
else
    echo -e "${RED}Erro ao enviar alerta. HTTP Code: $HTTP_CODE${NC}"
    echo "$BODY"
    exit 1
fi

# Listar alertas ativos
echo ""
echo -e "${BLUE}Alertas ativos no Alertmanager:${NC}"
curl -s "${ALERTMANAGER_URL}/api/v2/alerts" | \
    python3 -c "import sys, json; alerts=json.load(sys.stdin); print('\n'.join([f\"  - {a['labels'].get('alertname', 'N/A')} ({a['labels'].get('severity', 'N/A')}) - {a['status'].get('state', 'N/A')}\" for a in alerts[:5]]))" 2>/dev/null || \
    echo "  (Nao foi possivel listar alertas)"
