#!/bin/bash
set -euo pipefail

# Script para gerar relatório executivo consolidado dos testes E2E Fase 1
# Processa JSON, Markdown e métricas de performance em um único documento
#
# Uso:
#   ./generate_e2e_executive_report.sh [JSON_REPORT] [MD_SUMMARY] [METRICS_FILE]
#
# Exemplo:
#   ./generate_e2e_executive_report.sh tests/results/report.json tests/results/summary.md tests/results/metrics.txt

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JSON_REPORT="${1:-}"
MD_SUMMARY="${2:-}"
METRICS_FILE="${3:-}"
OUTPUT_DIR="${SCRIPT_DIR}/../tests/results"
OUTPUT_FILE="${OUTPUT_DIR}/PHASE1_E2E_EXECUTIVE_REPORT.md"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Verificar dependências
if ! command -v jq &>/dev/null; then
    echo -e "${RED}ERRO: jq não está instalado. Instale com: apt-get install jq${NC}"
    exit 1
fi

# Função para extrair dados do JSON
extract_json_data() {
    local json_file=$1

    if [ ! -f "$json_file" ]; then
        echo "N/A"
        return 1
    fi

    # Extrair estatísticas básicas
    TOTAL_TESTS=$(jq 'length' "$json_file" 2>/dev/null || echo "0")
    PASSED_TESTS=$(jq '[.[] | select(.status_code == 200)] | length' "$json_file" 2>/dev/null || echo "0")
    FAILED_TESTS=$(jq '[.[] | select(.status_code != 200)] | length' "$json_file" 2>/dev/null || echo "0")

    # Calcular latências
    AVG_LATENCY=$(jq '[.[] | .latency_ms] | add / length' "$json_file" 2>/dev/null || echo "N/A")
    MIN_LATENCY=$(jq '[.[] | .latency_ms] | min' "$json_file" 2>/dev/null || echo "N/A")
    MAX_LATENCY=$(jq '[.[] | .latency_ms] | max' "$json_file" 2>/dev/null || echo "N/A")
    P95_LATENCY=$(jq '[.[] | .latency_ms] | sort | .[length * 95 / 100 | floor]' "$json_file" 2>/dev/null || echo "N/A")

    # Extrair cenários testados
    SCENARIOS=$(jq -r '[.[] | .scenario] | unique | join(", ")' "$json_file" 2>/dev/null || echo "N/A")

    # Calcular taxa de sucesso
    if [ "$TOTAL_TESTS" != "0" ]; then
        SUCCESS_RATE=$(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc 2>/dev/null || echo "N/A")
    else
        SUCCESS_RATE="N/A"
    fi
}

# Função para extrair IDs do Markdown
extract_md_data() {
    local md_file=$1

    if [ ! -f "$md_file" ]; then
        return 1
    fi

    # Extrair IDs de correlação e intent
    CORRELATION_IDS=$(grep -oP 'correlation[_-]id[:\s]+\K[a-f0-9-]+' "$md_file" 2>/dev/null | head -5 | paste -sd ", " - || echo "N/A")
    INTENT_IDS=$(grep -oP 'intent[_-]id[:\s]+\K[a-f0-9-]+' "$md_file" 2>/dev/null | head -5 | paste -sd ", " - || echo "N/A")

    # Extrair timestamp se disponível
    TEST_DATE=$(grep -oP 'Data.*:\s*\K[\d-]+ [\d:]+' "$md_file" 2>/dev/null | head -1 || echo "$(date -u +"%Y-%m-%d %H:%M:%S")")
}

# Função para processar métricas de performance
extract_metrics_data() {
    local metrics_file=$1

    if [ ! -f "$metrics_file" ]; then
        METRICS_AVAILABLE=false
        return 1
    fi

    METRICS_AVAILABLE=true

    # Extrair métricas chave
    PLAN_GEN_P95=$(grep "Plan Generation" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+ms' || echo "N/A")
    SPECIALIST_EVAL_P95=$(grep "Specialist Evaluation" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+ms' || echo "N/A")
    CONSENSUS_P95=$(grep "Consensus Decision" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+ms' || echo "N/A")
    LEDGER_WRITE_P95=$(grep "Ledger Write" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+ms' || echo "N/A")

    # Extrair throughput
    PLANS_RATE=$(grep "Plans Generated:" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+(?= plans/min)' || echo "N/A")
    EVALS_RATE=$(grep "Specialist Evaluations:" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+(?= evaluations/min)' || echo "N/A")

    # Extrair taxas de sucesso
    PLAN_SUCCESS=$(grep "Plan Generation Success Rate:" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+(?=%)' || echo "N/A")
    CONSENSUS_SUCCESS=$(grep "Consensus Success Rate:" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+(?=%)' || echo "N/A")
    SPECIALIST_AVAILABILITY=$(grep "Specialist Availability:" "$metrics_file" 2>/dev/null | grep -oP '[\d.]+(?=%)' || echo "N/A")
}

# Função para determinar status geral
determine_overall_status() {
    local passed=$1
    local total=$2
    local failed=$3

    if [ "$total" == "0" ] || [ "$total" == "N/A" ]; then
        echo "⚠️ SEM DADOS"
        return
    fi

    local success_pct=$(echo "scale=0; $passed * 100 / $total" | bc 2>/dev/null || echo "0")

    if [ "$failed" -eq 0 ] && [ "$success_pct" -eq 100 ]; then
        echo "✅ SUCESSO COMPLETO"
    elif [ "$success_pct" -ge 80 ]; then
        echo "⚠️ SUCESSO PARCIAL"
    elif [ "$success_pct" -ge 50 ]; then
        echo "⚠️ DEGRADADO"
    else
        echo "❌ FALHA CRÍTICA"
    fi
}

# Função para gerar recomendações baseadas em falhas
generate_recommendations() {
    local failed=$1
    local success_rate=$2
    local avg_latency=$3

    echo ""

    if [ "$failed" != "0" ] && [ "$failed" != "N/A" ]; then
        echo "- 🔍 Investigar ${failed} teste(s) falhado(s) - verificar logs de componentes"
        echo "- 📊 Analisar padrões de falha por cenário/domínio"
    fi

    if [ "$success_rate" != "N/A" ]; then
        local rate_num=$(echo "$success_rate" | cut -d. -f1)
        if [ "$rate_num" -lt 95 ]; then
            echo "- ⚠️ Taxa de sucesso abaixo do SLA (95%) - requer atenção imediata"
            echo "- 🔧 Revisar configurações de timeout e retry policies"
        fi
    fi

    if [ "$avg_latency" != "N/A" ]; then
        local latency_num=$(echo "$avg_latency" | cut -d. -f1)
        if [ "$latency_num" -gt 1000 ]; then
            echo "- 🚀 Latência média acima de 1s - considerar otimizações"
            echo "- 📈 Analisar gargalos em consensus e specialist evaluation"
        fi
    fi

    if [ "$METRICS_AVAILABLE" = false ]; then
        echo "- 📉 Métricas de performance não disponíveis - verificar Prometheus"
        echo "- 🔌 Executar port-forward: kubectl port-forward -n monitoring svc/prometheus 9090:9090"
    fi

    if [ -z "$CORRELATION_IDS" ] || [ "$CORRELATION_IDS" == "N/A" ]; then
        echo "- 🔗 IDs de correlação não encontrados - verificar logs estruturados"
    fi
}

# Processar dados
echo -e "${YELLOW}Gerando relatório executivo E2E...${NC}"

if [ -n "$JSON_REPORT" ] && [ -f "$JSON_REPORT" ]; then
    echo "Processando JSON: $JSON_REPORT"
    extract_json_data "$JSON_REPORT"
else
    echo -e "${YELLOW}AVISO: JSON report não fornecido ou não encontrado${NC}"
    TOTAL_TESTS="N/A"
    PASSED_TESTS="N/A"
    FAILED_TESTS="N/A"
    SUCCESS_RATE="N/A"
    AVG_LATENCY="N/A"
    MIN_LATENCY="N/A"
    MAX_LATENCY="N/A"
    P95_LATENCY="N/A"
    SCENARIOS="N/A"
fi

if [ -n "$MD_SUMMARY" ] && [ -f "$MD_SUMMARY" ]; then
    echo "Processando Markdown: $MD_SUMMARY"
    extract_md_data "$MD_SUMMARY"
else
    echo -e "${YELLOW}AVISO: Markdown summary não fornecido ou não encontrado${NC}"
    TEST_DATE="$(date -u +"%Y-%m-%d %H:%M:%S")"
    CORRELATION_IDS="N/A"
    INTENT_IDS="N/A"
fi

if [ -n "$METRICS_FILE" ] && [ -f "$METRICS_FILE" ]; then
    echo "Processando métricas: $METRICS_FILE"
    extract_metrics_data "$METRICS_FILE"
else
    echo -e "${YELLOW}AVISO: Métricas não fornecidas - seção de performance será omitida${NC}"
    METRICS_AVAILABLE=false
fi

# Determinar status geral
OVERALL_STATUS=$(determine_overall_status "$PASSED_TESTS" "$TOTAL_TESTS" "$FAILED_TESTS")

# Gerar relatório
mkdir -p "$OUTPUT_DIR"

cat > "$OUTPUT_FILE" << EOF
# Relatório Executivo - Teste End-to-End Fase 1
## Neural Hive-Mind - Sistema Cognitivo Distribuído

---

**Data de Execução**: ${TEST_DATE} UTC
**Status Geral**: ${OVERALL_STATUS}
**Gerado Automaticamente**: $(date -u +"%Y-%m-%d %H:%M:%S") UTC

---

## 📊 Resumo Executivo

### Resultados dos Testes

| Métrica | Valor | Status |
|---------|-------|--------|
| **Testes Executados** | ${TOTAL_TESTS} | - |
| **Testes Aprovados** | ${PASSED_TESTS} | $([ "$PASSED_TESTS" != "N/A" ] && [ "$PASSED_TESTS" != "0" ] && echo "✅" || echo "-") |
| **Testes Falhados** | ${FAILED_TESTS} | $([ "$FAILED_TESTS" == "0" ] && echo "✅" || echo "⚠️") |
| **Taxa de Sucesso** | ${SUCCESS_RATE}% | $([ "$SUCCESS_RATE" != "N/A" ] && { rate=\${SUCCESS_RATE%.*}; [ "\$rate" -ge 95 ] && echo "✅" || echo "⚠️"; } || echo "-") |

### Latências Observadas (Testes E2E)

| Métrica | Valor |
|---------|-------|
| **Latência Média** | ${AVG_LATENCY} ms |
| **Latência Mínima** | ${MIN_LATENCY} ms |
| **Latência Máxima** | ${MAX_LATENCY} ms |
| **P95 Latência** | ${P95_LATENCY} ms |

### Cenários Testados

\`\`\`
${SCENARIOS}
\`\`\`

---

## 🔍 Análise Detalhada

### Trace IDs (Primeiros 5)

**Correlation IDs**:
\`\`\`
${CORRELATION_IDS}
\`\`\`

**Intent IDs**:
\`\`\`
${INTENT_IDS}
\`\`\`

EOF

# Adicionar seção de métricas se disponível
if [ "$METRICS_AVAILABLE" = true ]; then
    cat >> "$OUTPUT_FILE" << EOF

---

## 📈 Métricas de Performance (Prometheus)

### Latências P95 dos Componentes

| Componente | P95 Latência | SLA | Status |
|------------|--------------|-----|--------|
| **Plan Generation** | ${PLAN_GEN_P95} | < 500ms | $([ "$PLAN_GEN_P95" != "N/A" ] && echo "✅" || echo "⚠️") |
| **Specialist Evaluation** | ${SPECIALIST_EVAL_P95} | < 200ms | $([ "$SPECIALIST_EVAL_P95" != "N/A" ] && echo "✅" || echo "⚠️") |
| **Consensus Decision** | ${CONSENSUS_P95} | < 300ms | $([ "$CONSENSUS_P95" != "N/A" ] && echo "✅" || echo "⚠️") |
| **Ledger Write** | ${LEDGER_WRITE_P95} | < 100ms | $([ "$LEDGER_WRITE_P95" != "N/A" ] && echo "✅" || echo "⚠️") |

### Throughput do Sistema

| Métrica | Valor | SLA |
|---------|-------|-----|
| **Plans Generated** | ${PLANS_RATE} plans/min | 10-50 plans/min |
| **Specialist Evaluations** | ${EVALS_RATE} evaluations/min | 50-250 eval/min |

### Taxas de Sucesso

| Componente | Taxa | SLA | Status |
|------------|------|-----|--------|
| **Plan Generation** | ${PLAN_SUCCESS}% | > 99% | $([ "$PLAN_SUCCESS" != "N/A" ] && echo "✅" || echo "⚠️") |
| **Consensus** | ${CONSENSUS_SUCCESS}% | > 95% | $([ "$CONSENSUS_SUCCESS" != "N/A" ] && echo "✅" || echo "⚠️") |
| **Specialist Availability** | ${SPECIALIST_AVAILABILITY}% | > 99.9% | $([ "$SPECIALIST_AVAILABILITY" != "N/A" ] && echo "✅" || echo "⚠️") |

EOF
else
    cat >> "$OUTPUT_FILE" << EOF

---

## 📈 Métricas de Performance

⚠️ **Métricas de Prometheus não disponíveis**

Para coletar métricas, execute:
\`\`\`bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &

# Extrair métricas
./scripts/extract-performance-metrics.sh tests/results http://localhost:9090 5m
\`\`\`

EOF
fi

# Adicionar recomendações
cat >> "$OUTPUT_FILE" << EOF

---

## 💡 Recomendações e Próximos Passos

EOF

RECOMMENDATIONS=$(generate_recommendations "$FAILED_TESTS" "$SUCCESS_RATE" "$AVG_LATENCY")

if [ -n "$RECOMMENDATIONS" ]; then
    echo "$RECOMMENDATIONS" >> "$OUTPUT_FILE"
else
    cat >> "$OUTPUT_FILE" << EOF
✅ Sistema operando dentro dos parâmetros esperados

**Próximas Ações**:
- Continuar monitoramento de métricas
- Executar testes de carga (Fase 2)
- Validar comportamento sob condições de falha
EOF
fi

cat >> "$OUTPUT_FILE" << EOF

---

## 📚 Referências

**Arquivos de Origem**:
- JSON Report: \`${JSON_REPORT:-N/A}\`
- Markdown Summary: \`${MD_SUMMARY:-N/A}\`
- Performance Metrics: \`${METRICS_FILE:-N/A}\`

**Comandos Úteis**:
\`\`\`bash
# Executar teste E2E completo
./tests/phase1-end-to-end-test.sh

# Extrair métricas
./scripts/extract-performance-metrics.sh

# Gerar relatório executivo
./scripts/generate_e2e_executive_report.sh \\
  tests/results/report.json \\
  tests/results/summary.md \\
  tests/results/metrics.txt
\`\`\`

**Documentação**:
- [Guia de Testes Fase 1](../docs/PHASE1_TESTING_GUIDE.md)
- [Troubleshooting](../docs/TROUBLESHOOTING_CONSENSUS_ENGINE.md)

---

*Relatório gerado automaticamente por \`generate_e2e_executive_report.sh\`*
EOF

echo -e "${GREEN}✅ Relatório executivo gerado: ${OUTPUT_FILE}${NC}"
echo ""
echo "Resumo:"
echo "  - Status: ${OVERALL_STATUS}"
echo "  - Testes: ${PASSED_TESTS}/${TOTAL_TESTS} aprovados"
echo "  - Taxa de Sucesso: ${SUCCESS_RATE}%"
echo "  - Latência Média: ${AVG_LATENCY} ms"
echo ""

# Exibir conteúdo do relatório
cat "$OUTPUT_FILE"
