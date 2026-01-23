#!/bin/bash
# Validacao de SLOs de Modelos ML
# Script para verificar se todos os componentes de SLO estao configurados corretamente

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo " Validacao de SLOs de Modelos ML"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Funcao para verificar arquivo existe
check_file() {
    local file=$1
    local description=$2
    if [ -f "$file" ]; then
        echo -e "${GREEN}[OK]${NC} $description"
        return 0
    else
        echo -e "${RED}[ERRO]${NC} $description - Arquivo nao encontrado: $file"
        ((ERRORS++))
        return 1
    fi
}

# Funcao para verificar conteudo no arquivo
check_content() {
    local file=$1
    local pattern=$2
    local description=$3
    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo -e "${GREEN}[OK]${NC} $description"
        return 0
    else
        echo -e "${RED}[ERRO]${NC} $description - Padrao nao encontrado"
        ((ERRORS++))
        return 1
    fi
}

# Funcao para verificar YAML valido
check_yaml() {
    local file=$1
    local description=$2
    if command -v yq &> /dev/null; then
        if yq eval '.' "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}[OK]${NC} $description - YAML valido"
            return 0
        else
            echo -e "${RED}[ERRO]${NC} $description - YAML invalido"
            ((ERRORS++))
            return 1
        fi
    elif command -v python3 &> /dev/null; then
        if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
            echo -e "${GREEN}[OK]${NC} $description - YAML valido"
            return 0
        else
            echo -e "${RED}[ERRO]${NC} $description - YAML invalido"
            ((ERRORS++))
            return 1
        fi
    else
        echo -e "${YELLOW}[WARN]${NC} $description - Nao foi possivel validar YAML (yq/python3 nao disponivel)"
        ((WARNINGS++))
        return 0
    fi
}

# Funcao para verificar JSON valido
check_json() {
    local file=$1
    local description=$2
    if command -v jq &> /dev/null; then
        if jq '.' "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}[OK]${NC} $description - JSON valido"
            return 0
        else
            echo -e "${RED}[ERRO]${NC} $description - JSON invalido"
            ((ERRORS++))
            return 1
        fi
    elif command -v python3 &> /dev/null; then
        if python3 -c "import json; json.load(open('$file'))" 2>/dev/null; then
            echo -e "${GREEN}[OK]${NC} $description - JSON valido"
            return 0
        else
            echo -e "${RED}[ERRO]${NC} $description - JSON invalido"
            ((ERRORS++))
            return 1
        fi
    else
        echo -e "${YELLOW}[WARN]${NC} $description - Nao foi possivel validar JSON (jq/python3 nao disponivel)"
        ((WARNINGS++))
        return 0
    fi
}

echo "1. Verificando arquivos de configuracao..."
echo "-------------------------------------------"

# Verificar SLO Definitions
check_file "monitoring/slos/ml-model-slos.yaml" "SLO Definitions (CRD)"
check_yaml "monitoring/slos/ml-model-slos.yaml" "SLO Definitions"

# Verificar Recording Rules
check_file "monitoring/slos/ml-slo-recording-rules.yaml" "Recording Rules"
check_yaml "monitoring/slos/ml-slo-recording-rules.yaml" "Recording Rules"

# Verificar Alertas
check_file "prometheus-rules/ml-slo-alerts.yaml" "Alertas de SLO"
check_yaml "prometheus-rules/ml-slo-alerts.yaml" "Alertas de SLO"

# Verificar Dashboard ML SLOs
check_file "monitoring/dashboards/ml-slos-dashboard.json" "Dashboard ML SLOs"
check_json "monitoring/dashboards/ml-slos-dashboard.json" "Dashboard ML SLOs"

# Verificar Dashboard SLOs Error Budgets
check_file "monitoring/dashboards/slos-error-budgets.json" "Dashboard SLOs Error Budgets"
check_json "monitoring/dashboards/slos-error-budgets.json" "Dashboard SLOs Error Budgets"

# Verificar Documentacao
check_file "docs/slos/ml-models.md" "Documentacao de SLOs"

echo ""
echo "2. Verificando definicoes de SLO..."
echo "-------------------------------------------"

# Verificar 4 SLOs definidos
check_content "monitoring/slos/ml-model-slos.yaml" "ml-model-f1-score" "SLO F1 Score definido"
check_content "monitoring/slos/ml-model-slos.yaml" "ml-model-latency-p95" "SLO Latency P95 definido"
check_content "monitoring/slos/ml-model-slos.yaml" "ml-model-feedback-rate" "SLO Feedback Rate definido"
check_content "monitoring/slos/ml-model-slos.yaml" "ml-model-uptime" "SLO Uptime definido"

echo ""
echo "3. Verificando recording rules..."
echo "-------------------------------------------"

# Verificar recording rules principais
check_content "monitoring/slos/ml-slo-recording-rules.yaml" "neural_hive:slo:ml_f1_score:7d" "Recording rule F1 Score"
check_content "monitoring/slos/ml-slo-recording-rules.yaml" "neural_hive:slo:ml_latency_p95" "Recording rule Latency P95"
check_content "monitoring/slos/ml-slo-recording-rules.yaml" "neural_hive:slo:ml_feedback_rate:7d" "Recording rule Feedback Rate"
check_content "monitoring/slos/ml-slo-recording-rules.yaml" "neural_hive:slo:ml_availability:30d" "Recording rule Availability"

# Verificar error budget recording rules
check_content "monitoring/slos/ml-slo-recording-rules.yaml" "neural_hive:slo:ml_error_budget_remaining" "Recording rules Error Budget"
check_content "monitoring/slos/ml-slo-recording-rules.yaml" "neural_hive:slo:ml_compliance" "Recording rules Compliance"

echo ""
echo "4. Verificando alertas..."
echo "-------------------------------------------"

# Verificar alertas de violacao
check_content "prometheus-rules/ml-slo-alerts.yaml" "MLModelF1ScoreSLO" "Alerta F1 Score"
check_content "prometheus-rules/ml-slo-alerts.yaml" "MLModelLatency" "Alerta Latency"
check_content "prometheus-rules/ml-slo-alerts.yaml" "MLModelFeedbackRate" "Alerta Feedback Rate"
check_content "prometheus-rules/ml-slo-alerts.yaml" "MLModelUptime" "Alerta Uptime"

# Verificar alertas de burn rate
check_content "prometheus-rules/ml-slo-alerts.yaml" "ErrorBudget" "Alertas Error Budget Burn"

echo ""
echo "5. Verificando dashboard ML SLOs..."
echo "-------------------------------------------"

# Verificar componentes do dashboard
check_content "monitoring/dashboards/ml-slos-dashboard.json" "F1 Score" "Painel F1 Score"
check_content "monitoring/dashboards/ml-slos-dashboard.json" "Latency" "Painel Latency"
check_content "monitoring/dashboards/ml-slos-dashboard.json" "Feedback" "Painel Feedback"
check_content "monitoring/dashboards/ml-slos-dashboard.json" "Uptime" "Painel Uptime"
check_content "monitoring/dashboards/ml-slos-dashboard.json" "Error Budget" "Painel Error Budget"

echo ""
echo "6. Verificando integracao com dashboard existente..."
echo "-------------------------------------------"

# Verificar ML SLOs integrados no dashboard principal
check_content "monitoring/dashboards/slos-error-budgets.json" "ml-slos-dashboard" "Link para ML SLOs Dashboard"
check_content "monitoring/dashboards/slos-error-budgets.json" "ML F1 Score" "Painel ML F1 Score integrado"
check_content "monitoring/dashboards/slos-error-budgets.json" "ml_error_budget_consumed:f1_score" "ML Error Budget integrado"

echo ""
echo "=========================================="
echo " Resultado da Validacao"
echo "=========================================="

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}Todas as validacoes passaram!${NC}"
    echo ""
    echo "Dashboards disponiveis:"
    echo "  - ML SLOs: /d/ml-slos-dashboard/ml-slos"
    echo "  - SLOs & Error Budgets: /d/slos-error-budgets"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}Validacao concluida com $WARNINGS aviso(s)${NC}"
    exit 0
else
    echo -e "${RED}Validacao falhou com $ERRORS erro(s) e $WARNINGS aviso(s)${NC}"
    exit 1
fi
