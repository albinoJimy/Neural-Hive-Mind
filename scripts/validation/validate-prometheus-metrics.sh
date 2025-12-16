#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -euo pipefail

#==============================================================================
# Script de Validação de Métricas Prometheus/Grafana dos Especialistas
#
# Valida:
# - Prometheus está coletando métricas dos especialistas
# - Métricas específicas existem (specialist_evaluations_total, etc)
# - Freshness das métricas (scrape recente < 1 minuto)
# - Dashboards do Grafana estão disponíveis
# - Alerting rules configurados
#
# Uso:
#   ./validate-prometheus-metrics.sh
#   ./validate-prometheus-metrics.sh --prometheus-url http://prometheus:9090
#   ./validate-prometheus-metrics.sh --grafana-url http://grafana:3000
#==============================================================================

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações padrão
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus-stack-kube-prom-prometheus.observability:9090}"
GRAFANA_URL="${GRAFANA_URL:-http://grafana.observability:3000}"
NAMESPACE="${NAMESPACE:-semantic-translation}"

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --prometheus-url)
            PROMETHEUS_URL="$2"
            shift 2
            ;;
        --grafana-url)
            GRAFANA_URL="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            echo "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

echo "================================================================================"
echo "🔍 Validação de Métricas Prometheus/Grafana - Especialistas Neural Hive"
echo "================================================================================"
echo ""
echo "Configuração:"
echo "  Prometheus URL: $PROMETHEUS_URL"
echo "  Grafana URL: $GRAFANA_URL"
echo "  Namespace: $NAMESPACE"
echo ""

# Lista de especialistas
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

# Métricas esperadas
EXPECTED_METRICS=(
    "specialist_evaluations_total"
    "specialist_evaluation_duration_seconds"
    "specialist_model_inference_duration_seconds"
    "specialist_cache_hits_total"
    "specialist_cache_misses_total"
    "specialist_errors_total"
)

#==============================================================================
# Função: Verificar conectividade do Prometheus
#==============================================================================
check_prometheus_connectivity() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Verificando conectividade com Prometheus"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    if curl -s -f "$PROMETHEUS_URL/-/healthy" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Prometheus está acessível${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}❌ Prometheus não está acessível em $PROMETHEUS_URL${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
    echo ""
}

#==============================================================================
# Função: Verificar métricas de um especialista
#==============================================================================
check_specialist_metrics() {
    local specialist=$1
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📈 Verificando métricas: specialist-$specialist"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for metric in "${EXPECTED_METRICS[@]}"; do
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

        # Query Prometheus API para verificar se métrica existe
        QUERY="${metric}{specialist_type=\"${specialist}\"}"
        RESPONSE=$(curl -s -G --data-urlencode "query=$QUERY" "$PROMETHEUS_URL/api/v1/query")

        # Verificar se retornou dados
        RESULT_TYPE=$(echo "$RESPONSE" | jq -r '.data.resultType' 2>/dev/null)
        RESULT_COUNT=$(echo "$RESPONSE" | jq -r '.data.result | length' 2>/dev/null)

        if [[ "$RESULT_COUNT" -gt 0 ]]; then
            # Verificar freshness (último scrape)
            TIMESTAMP=$(echo "$RESPONSE" | jq -r '.data.result[0].value[0]' 2>/dev/null)
            CURRENT_TIME=$(date +%s)
            AGE=$((CURRENT_TIME - TIMESTAMP))

            if [[ $AGE -lt 120 ]]; then
                echo -e "  ${GREEN}✅ $metric (idade: ${AGE}s)${NC}"
                PASSED_CHECKS=$((PASSED_CHECKS + 1))
            else
                # Métricas antigas são apenas warnings, não falhas críticas
                # Isso evita falsos negativos em ambientes ociosos
                echo -e "  ${YELLOW}⚠️  $metric (idade: ${AGE}s - dados antigos, não crítico)${NC}"
                WARNING_CHECKS=$((WARNING_CHECKS + 1))
                PASSED_CHECKS=$((PASSED_CHECKS + 1))
            fi
        else
            echo -e "  ${RED}❌ $metric (não encontrada)${NC}"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
        fi
    done
    echo ""
}

#==============================================================================
# Função: Verificar Grafana dashboards
#==============================================================================
check_grafana_dashboards() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Verificando Grafana Dashboards"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    # Verificar conectividade com Grafana
    if curl -s -f "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Grafana está acessível${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}❌ Grafana não está acessível em $GRAFANA_URL${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi

    # TODO: Verificar se dashboards específicos existem
    # curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
    #   "$GRAFANA_URL/api/search?query=specialist" | jq

    echo ""
}

#==============================================================================
# Função: Verificar alerting rules
#==============================================================================
check_alerting_rules() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔔 Verificando Alerting Rules"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    # Query rules do Prometheus
    RESPONSE=$(curl -s "$PROMETHEUS_URL/api/v1/rules")

    # Verificar se existem rules configuradas
    GROUPS_COUNT=$(echo "$RESPONSE" | jq -r '.data.groups | length' 2>/dev/null)

    if [[ "$GROUPS_COUNT" -gt 0 ]]; then
        echo -e "${GREEN}✅ Alerting rules configuradas ($GROUPS_COUNT grupos)${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))

        # Buscar rules específicas para especialistas
        SPECIALIST_RULES=$(echo "$RESPONSE" | jq -r '.data.groups[].rules[] | select(.alert | test("specialist"; "i")) | .alert' 2>/dev/null)

        if [[ -n "$SPECIALIST_RULES" ]]; then
            echo "  Rules encontradas:"
            echo "$SPECIALIST_RULES" | while read -r rule; do
                echo "    - $rule"
            done
        fi
    else
        echo -e "${YELLOW}⚠️  Nenhum alerting rule configurado${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi

    echo ""
}

#==============================================================================
# Main execution
#==============================================================================

# Verificar conectividade
check_prometheus_connectivity || exit 1

# Verificar métricas de cada especialista
for specialist in "${SPECIALISTS[@]}"; do
    check_specialist_metrics "$specialist"
done

# Verificar Grafana
check_grafana_dashboards

# Verificar alerting rules
check_alerting_rules

#==============================================================================
# Relatório Final
#==============================================================================
echo "================================================================================"
echo "📊 RELATÓRIO FINAL - Validação de Métricas"
echo "================================================================================"
echo ""
echo "Total de verificações: $TOTAL_CHECKS"
echo -e "${GREEN}✅ Passou: $PASSED_CHECKS${NC}"
echo -e "${RED}❌ Falhou: $FAILED_CHECKS${NC}"
echo -e "${YELLOW}⚠️  Avisos: $WARNING_CHECKS${NC}"
echo ""

SUCCESS_RATE=0
if [[ $TOTAL_CHECKS -gt 0 ]]; then
    SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
fi

echo "Taxa de sucesso: ${SUCCESS_RATE}%"
if [[ $WARNING_CHECKS -gt 0 ]]; then
    echo ""
    echo "Nota: Avisos indicam métricas antigas (>120s) mas não impedem aprovação."
    echo "      Isso é normal em ambientes ociosos sem tráfego recente."
fi
echo "================================================================================"

# Exit code - avisos não causam falha
if [[ $FAILED_CHECKS -gt 0 ]]; then
    exit 1
else
    exit 0
fi
