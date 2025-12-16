#!/usr/bin/env bash
# Script auxiliar para validar resultados coletados manualmente em testes E2E
# NÃO executa testes, apenas valida dados já coletados

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações padrão
INPUT_FILE=""
OUTPUT_DIR=".tmp"
FORMAT="markdown"
VERBOSE=false

# SLOs esperados
SLO_E2E_DURATION_MS=5000
SLO_GATEWAY_LATENCY_MS=200
SLO_STE_LATENCY_MS=2000
SLO_SPECIALISTS_LATENCY_MS=1000
SLO_CONSENSUS_LATENCY_MS=2000
SLO_ORCHESTRATOR_LATENCY_MS=1000
SLO_SUCCESS_RATE=0.95

# Contadores de validação
TOTAL_VALIDATIONS=0
PASSED_VALIDATIONS=0
FAILED_VALIDATIONS=0
WARNING_VALIDATIONS=0

# Função de ajuda
show_help() {
    cat << EOF
Uso: $(basename "$0") [OPÇÕES]

Valida resultados coletados manualmente em testes E2E do Neural Hive-Mind.

OPÇÕES:
    -h, --help                  Mostra esta mensagem de ajuda
    -v, --verbose               Modo verbose
    -i, --input-file FILE       Arquivo de input com resultados (JSON ou Markdown)
    -o, --output-dir DIR        Diretório de saída para relatório (padrão: .tmp)
    -f, --format FORMAT         Formato do input: json|markdown (padrão: markdown)

EXEMPLOS:
    $(basename "$0") -i results.json -f json
    $(basename "$0") -i e2e-test-report.md -f markdown -v

EOF
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -i|--input-file)
            INPUT_FILE="$2"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -f|--format)
            FORMAT="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Erro: Opção desconhecida: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Validar argumentos obrigatórios
if [ -z "$INPUT_FILE" ]; then
    echo -e "${RED}Erro: --input-file é obrigatório${NC}"
    show_help
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo -e "${RED}Erro: Arquivo não encontrado: $INPUT_FILE${NC}"
    exit 1
fi

# Função de log
log() {
    local level=$1
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    case $level in
        INFO)
            echo -e "${BLUE}[$timestamp] INFO:${NC} $*"
            ;;
        SUCCESS)
            echo -e "${GREEN}[$timestamp] SUCCESS:${NC} $*"
            ;;
        WARN)
            echo -e "${YELLOW}[$timestamp] WARN:${NC} $*"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] ERROR:${NC} $*"
            ;;
    esac
}

# Validar formato do input
validate_input_format() {
    log INFO "Validando formato do input: $FORMAT"
    
    case $FORMAT in
        json)
            if ! jq empty "$INPUT_FILE" 2>/dev/null; then
                log ERROR "Arquivo não é um JSON válido"
                exit 2
            fi
            ;;
        markdown)
            if ! grep -q "^# Relatório de Teste E2E" "$INPUT_FILE"; then
                log WARN "Arquivo não parece ser um relatório E2E válido"
            fi
            ;;
        *)
            log ERROR "Formato inválido: $FORMAT (use json ou markdown)"
            exit 2
            ;;
    esac
    
    log SUCCESS "Formato validado: $FORMAT"
}

# Extrair dados do input (JSON)
extract_json_data() {
    log INFO "Extraindo dados do JSON..."
    
    # Fluxo A
    INTENT_ID=$(jq -r '.fluxo_a.intent_id // ""' "$INPUT_FILE")
    DOMAIN=$(jq -r '.fluxo_a.domain // ""' "$INPUT_FILE")
    CONFIDENCE=$(jq -r '.fluxo_a.confidence // 0' "$INPUT_FILE")
    KAFKA_PUBLISHED=$(jq -r '.fluxo_a.kafka_published // false' "$INPUT_FILE")
    
    # Fluxo B
    PLAN_ID=$(jq -r '.fluxo_b.plan_id // ""' "$INPUT_FILE")
    NUM_TASKS=$(jq -r '.fluxo_b.num_tasks // 0' "$INPUT_FILE")
    SPECIALISTS_RESPONDED=$(jq -r '.fluxo_b.specialists_responded // 0' "$INPUT_FILE")
    
    # Fluxo C
    DECISION_ID=$(jq -r '.fluxo_c.decision_id // ""' "$INPUT_FILE")
    FINAL_DECISION=$(jq -r '.fluxo_c.final_decision // ""' "$INPUT_FILE")
    NUM_TICKETS=$(jq -r '.fluxo_c.num_tickets // 0' "$INPUT_FILE")
    
    # Métricas E2E
    TOTAL_DURATION_MS=$(jq -r '.e2e_metrics.total_duration_ms // 0' "$INPUT_FILE")
    GATEWAY_LATENCY_MS=$(jq -r '.e2e_metrics.gateway_latency_ms // 0' "$INPUT_FILE")
    STE_LATENCY_MS=$(jq -r '.e2e_metrics.ste_latency_ms // 0' "$INPUT_FILE")
    SPECIALISTS_LATENCY_MS=$(jq -r '.e2e_metrics.specialists_latency_ms // 0' "$INPUT_FILE")
    CONSENSUS_LATENCY_MS=$(jq -r '.e2e_metrics.consensus_latency_ms // 0' "$INPUT_FILE")
    ORCHESTRATOR_LATENCY_MS=$(jq -r '.e2e_metrics.orchestrator_latency_ms // 0' "$INPUT_FILE")
}

# Extrair dados do input (Markdown)
extract_markdown_data() {
    log INFO "Extraindo dados do Markdown..."
    
    # Usar grep/awk para extrair valores
    INTENT_ID=$(grep -oP '(?<=\*\*intent_id\*\*: ).*' "$INPUT_FILE" | head -1 | tr -d ' ')
    DOMAIN=$(grep -oP '(?<=\*\*domain\*\*: ).*' "$INPUT_FILE" | head -1 | tr -d ' ')
    PLAN_ID=$(grep -oP '(?<=\*\*plan_id\*\*: ).*' "$INPUT_FILE" | head -1 | tr -d ' ')
    DECISION_ID=$(grep -oP '(?<=\*\*decision_id\*\*: ).*' "$INPUT_FILE" | head -1 | tr -d ' ')
    
    # Valores numéricos
    CONFIDENCE=$(grep -oP '(?<=\*\*confidence\*\*: )[0-9.]+' "$INPUT_FILE" | head -1)
    NUM_TASKS=$(grep -oP '(?<=\*\*num_tasks\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    SPECIALISTS_RESPONDED=$(grep -oP '(?<=\*\*Opinions\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    NUM_TICKETS=$(grep -oP '(?<=\*\*Número de tickets\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    
    # Métricas E2E
    TOTAL_DURATION_MS=$(grep -oP '(?<=\*\*Duração total E2E\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    GATEWAY_LATENCY_MS=$(grep -oP '(?<=\*\*Latência Gateway\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    STE_LATENCY_MS=$(grep -oP '(?<=\*\*Latência STE\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    SPECIALISTS_LATENCY_MS=$(grep -oP '(?<=\*\*Latência Specialists\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    CONSENSUS_LATENCY_MS=$(grep -oP '(?<=\*\*Latência Consensus\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    ORCHESTRATOR_LATENCY_MS=$(grep -oP '(?<=\*\*Latência Orchestrator\*\*: )[0-9]+' "$INPUT_FILE" | head -1)
    
    # Valores padrão se não encontrados
    CONFIDENCE=${CONFIDENCE:-0}
    NUM_TASKS=${NUM_TASKS:-0}
    SPECIALISTS_RESPONDED=${SPECIALISTS_RESPONDED:-0}
    NUM_TICKETS=${NUM_TICKETS:-0}
    TOTAL_DURATION_MS=${TOTAL_DURATION_MS:-0}
    GATEWAY_LATENCY_MS=${GATEWAY_LATENCY_MS:-0}
    STE_LATENCY_MS=${STE_LATENCY_MS:-0}
    SPECIALISTS_LATENCY_MS=${SPECIALISTS_LATENCY_MS:-0}
    CONSENSUS_LATENCY_MS=${CONSENSUS_LATENCY_MS:-0}
    ORCHESTRATOR_LATENCY_MS=${ORCHESTRATOR_LATENCY_MS:-0}
}

# Função de validação
validate() {
    local name=$1
    local condition=$2
    local message=$3
    
    TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
    
    if eval "$condition"; then
        PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
        echo "✅ PASS: $name"
        [ "$VERBOSE" = true ] && log SUCCESS "$message"
        return 0
    else
        FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
        echo "❌ FAIL: $name"
        log ERROR "$message"
        return 1
    fi
}

# Função de validação com warning
validate_warn() {
    local name=$1
    local condition=$2
    local message=$3
    
    TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
    
    if eval "$condition"; then
        PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
        echo "✅ PASS: $name"
        [ "$VERBOSE" = true ] && log SUCCESS "$message"
        return 0
    else
        WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
        echo "⚠️  WARN: $name"
        log WARN "$message"
        return 1
    fi
}

# Validar completude dos dados
validate_data_completeness() {
    log INFO "Validando completude dos dados..."
    
    echo ""
    echo "=== COMPLETUDE DOS DADOS ==="
    
    validate "Intent ID presente" "[ -n \"$INTENT_ID\" ]" "Intent ID não encontrado"
    validate "Domain identificado" "[ -n \"$DOMAIN\" ]" "Domain não identificrado"
    validate "Confidence válido" "[ \"$(echo \"$CONFIDENCE > 0\" | bc)\" -eq 1 ]" "Confidence inválido ou zero"
    validate "Plan ID presente" "[ -n \"$PLAN_ID\" ]" "Plan ID não encontrado"
    validate "Decision ID presente" "[ -n \"$DECISION_ID\" ]" "Decision ID não encontrado"
    validate "Número de tarefas > 0" "[ \"$NUM_TASKS\" -gt 0 ]" "Número de tarefas é zero"
    validate "5 Specialists responderam" "[ \"$SPECIALISTS_RESPONDED\" -eq 5 ]" "Esperado 5 specialists, encontrado: $SPECIALISTS_RESPONDED"
    validate "Tickets gerados" "[ \"$NUM_TICKETS\" -gt 0 ]" "Nenhum ticket gerado"
}

# Validar SLOs
validate_slos() {
    log INFO "Validando SLOs..."
    
    echo ""
    echo "=== VALIDAÇÃO DE SLOs ==="
    
    if [ "$TOTAL_DURATION_MS" -gt 0 ]; then
        validate "Duração E2E < ${SLO_E2E_DURATION_MS}ms" \
            "[ \"$TOTAL_DURATION_MS\" -lt \"$SLO_E2E_DURATION_MS\" ]" \
            "Duração E2E: ${TOTAL_DURATION_MS}ms (SLO: <${SLO_E2E_DURATION_MS}ms)"
    else
        validate_warn "Duração E2E informada" "false" "Duração E2E não foi informada"
    fi
    
    if [ "$GATEWAY_LATENCY_MS" -gt 0 ]; then
        validate "Latência Gateway < ${SLO_GATEWAY_LATENCY_MS}ms" \
            "[ \"$GATEWAY_LATENCY_MS\" -lt \"$SLO_GATEWAY_LATENCY_MS\" ]" \
            "Latência Gateway: ${GATEWAY_LATENCY_MS}ms (SLO: <${SLO_GATEWAY_LATENCY_MS}ms)"
    fi
    
    if [ "$STE_LATENCY_MS" -gt 0 ]; then
        validate "Latência STE < ${SLO_STE_LATENCY_MS}ms" \
            "[ \"$STE_LATENCY_MS\" -lt \"$SLO_STE_LATENCY_MS\" ]" \
            "Latência STE: ${STE_LATENCY_MS}ms (SLO: <${SLO_STE_LATENCY_MS}ms)"
    fi
    
    if [ "$SPECIALISTS_LATENCY_MS" -gt 0 ]; then
        validate "Latência Specialists < ${SLO_SPECIALISTS_LATENCY_MS}ms" \
            "[ \"$SPECIALISTS_LATENCY_MS\" -lt \"$SLO_SPECIALISTS_LATENCY_MS\" ]" \
            "Latência Specialists: ${SPECIALISTS_LATENCY_MS}ms (SLO: <${SLO_SPECIALISTS_LATENCY_MS}ms)"
    fi
    
    if [ "$CONSENSUS_LATENCY_MS" -gt 0 ]; then
        validate "Latência Consensus < ${SLO_CONSENSUS_LATENCY_MS}ms" \
            "[ \"$CONSENSUS_LATENCY_MS\" -lt \"$SLO_CONSENSUS_LATENCY_MS\" ]" \
            "Latência Consensus: ${CONSENSUS_LATENCY_MS}ms (SLO: <${SLO_CONSENSUS_LATENCY_MS}ms)"
    fi
    
    if [ "$ORCHESTRATOR_LATENCY_MS" -gt 0 ]; then
        validate "Latência Orchestrator < ${SLO_ORCHESTRATOR_LATENCY_MS}ms" \
            "[ \"$ORCHESTRATOR_LATENCY_MS\" -lt \"$SLO_ORCHESTRATOR_LATENCY_MS\" ]" \
            "Latência Orchestrator: ${ORCHESTRATOR_LATENCY_MS}ms (SLO: <${SLO_ORCHESTRATOR_LATENCY_MS}ms)"
    fi
}

# Validar correlação
validate_correlation() {
    log INFO "Validando correlação..."
    
    echo ""
    echo "=== VALIDAÇÃO DE CORRELAÇÃO ==="
    
    validate "Intent ID não vazio" "[ -n \"$INTENT_ID\" ]" "Intent ID vazio"
    validate "Plan ID não vazio" "[ -n \"$PLAN_ID\" ]" "Plan ID vazio"
    validate "Decision ID não vazio" "[ -n \"$DECISION_ID\" ]" "Decision ID vazio"
    
    # Validar que IDs são diferentes (não são placeholders)
    validate_warn "Intent ID não é placeholder" \
        "[ \"$INTENT_ID\" != \"___________________________\" ]" \
        "Intent ID parece ser um placeholder"
    
    validate_warn "Plan ID não é placeholder" \
        "[ \"$PLAN_ID\" != \"___________________________\" ]" \
        "Plan ID parece ser um placeholder"
    
    validate_warn "Decision ID não é placeholder" \
        "[ \"$DECISION_ID\" != \"___________________________\" ]" \
        "Decision ID parece ser um placeholder"
}

# Gerar relatório de validação
generate_validation_report() {
    log INFO "Gerando relatório de validação..."
    
    mkdir -p "$OUTPUT_DIR"
    local report_file="$OUTPUT_DIR/e2e-validation-report.md"
    
    local completeness_score=$(echo "scale=2; $PASSED_VALIDATIONS * 100 / $TOTAL_VALIDATIONS" | bc)
    local status="PASS"
    
    if [ "$FAILED_VALIDATIONS" -gt 0 ]; then
        status="FAIL"
    elif [ "$WARNING_VALIDATIONS" -gt 0 ]; then
        status="PASS com WARNINGS"
    fi
    
    cat > "$report_file" <<EOF
# Relatório de Validação E2E - Neural Hive-Mind

**Data da Validação**: $(date '+%Y-%m-%d %H:%M:%S')  
**Arquivo de Input**: $INPUT_FILE  
**Score de Completude**: ${completeness_score}% ($PASSED_VALIDATIONS/$TOTAL_VALIDATIONS validações passaram)

## Resumo Executivo
**Status**: $status

- ✅ Validações Passadas: $PASSED_VALIDATIONS
- ❌ Validações Falhadas: $FAILED_VALIDATIONS
- ⚠️  Warnings: $WARNING_VALIDATIONS
- 📊 Total: $TOTAL_VALIDATIONS

---

## Dados Extraídos

### Fluxo A (Gateway → Kafka)
| Campo | Valor |
|-------|-------|
| Intent ID | $INTENT_ID |
| Domain | $DOMAIN |
| Confidence | $CONFIDENCE |

### Fluxo B (STE → Specialists → Plano)
| Campo | Valor |
|-------|-------|
| Plan ID | $PLAN_ID |
| Número de Tarefas | $NUM_TASKS |
| Specialists Responderam | $SPECIALISTS_RESPONDED / 5 |

### Fluxo C (Consensus → Orchestrator → Tickets)
| Campo | Valor |
|-------|-------|
| Decision ID | $DECISION_ID |
| Final Decision | $FINAL_DECISION |
| Número de Tickets | $NUM_TICKETS |

---

## Métricas E2E

| Métrica | Valor | SLO | Status |
|---------|-------|-----|--------|
| Duração Total | ${TOTAL_DURATION_MS} ms | < ${SLO_E2E_DURATION_MS} ms | $([ "$TOTAL_DURATION_MS" -lt "$SLO_E2E_DURATION_MS" ] && echo "✅ PASS" || echo "❌ FAIL") |
| Latência Gateway | ${GATEWAY_LATENCY_MS} ms | < ${SLO_GATEWAY_LATENCY_MS} ms | $([ "$GATEWAY_LATENCY_MS" -lt "$SLO_GATEWAY_LATENCY_MS" ] && echo "✅ PASS" || echo "❌ FAIL") |
| Latência STE | ${STE_LATENCY_MS} ms | < ${SLO_STE_LATENCY_MS} ms | $([ "$STE_LATENCY_MS" -lt "$SLO_STE_LATENCY_MS" ] && echo "✅ PASS" || echo "❌ FAIL") |
| Latência Specialists | ${SPECIALISTS_LATENCY_MS} ms | < ${SLO_SPECIALISTS_LATENCY_MS} ms | $([ "$SPECIALISTS_LATENCY_MS" -lt "$SLO_SPECIALISTS_LATENCY_MS" ] && echo "✅ PASS" || echo "❌ FAIL") |
| Latência Consensus | ${CONSENSUS_LATENCY_MS} ms | < ${SLO_CONSENSUS_LATENCY_MS} ms | $([ "$CONSENSUS_LATENCY_MS" -lt "$SLO_CONSENSUS_LATENCY_MS" ] && echo "✅ PASS" || echo "❌ FAIL") |
| Latência Orchestrator | ${ORCHESTRATOR_LATENCY_MS} ms | < ${SLO_ORCHESTRATOR_LATENCY_MS} ms | $([ "$ORCHESTRATOR_LATENCY_MS" -lt "$SLO_ORCHESTRATOR_LATENCY_MS" ] && echo "✅ PASS" || echo "❌ FAIL") |

---

## Recomendações

EOF
    
    if [ "$FAILED_VALIDATIONS" -eq 0 ] && [ "$WARNING_VALIDATIONS" -eq 0 ]; then
        cat >> "$report_file" <<EOF
✅ **Sistema operacional e dentro dos SLOs**

1. Executar testes adicionais com diferentes tipos de intenções
2. Testar cenários de falha (specialist timeout, Kafka indisponível)
3. Validar comportamento de retry e compensação
4. Testar carga (múltiplas intenções simultâneas)
EOF
    else
        cat >> "$report_file" <<EOF
⚠️ **Ações corretivas necessárias**

EOF
        
        if [ "$FAILED_VALIDATIONS" -gt 0 ]; then
            cat >> "$report_file" <<EOF
1. Revisar validações falhadas acima
2. Verificar logs dos componentes com falha
3. Validar conectividade entre serviços
4. Verificar configurações de timeout e retry
EOF
        fi
        
        if [ "$WARNING_VALIDATIONS" -gt 0 ]; then
            cat >> "$report_file" <<EOF
5. Revisar warnings identificados
6. Completar dados faltantes no relatório de teste
7. Validar que todos os IDs foram corretamente anotados
EOF
        fi
    fi
    
    cat >> "$report_file" <<EOF

---

**Gerado em**: $(date '+%Y-%m-%d %H:%M:%S')  
**Script**: $(basename "$0")
EOF
    
    log SUCCESS "Relatório de validação gerado: $report_file"
}

# Main
main() {
    log INFO "Iniciando validação de resultados E2E..."
    
    validate_input_format
    
    if [ "$FORMAT" = "json" ]; then
        extract_json_data
    else
        extract_markdown_data
    fi
    
    validate_data_completeness
    validate_slos
    validate_correlation
    
    generate_validation_report
    
    echo ""
    echo "=== RESULTADO FINAL ==="
    echo "Total de Validações: $TOTAL_VALIDATIONS"
    echo "✅ Passadas: $PASSED_VALIDATIONS"
    echo "❌ Falhadas: $FAILED_VALIDATIONS"
    echo "⚠️  Warnings: $WARNING_VALIDATIONS"
    
    local completeness_score=$(echo "scale=2; $PASSED_VALIDATIONS * 100 / $TOTAL_VALIDATIONS" | bc)
    echo "Score de Completude: ${completeness_score}%"
    
    echo ""
    if [ "$FAILED_VALIDATIONS" -eq 0 ]; then
        log SUCCESS "Validação concluída com sucesso!"
        exit 0
    else
        log ERROR "Validação falhou. Verifique o relatório: $OUTPUT_DIR/e2e-validation-report.md"
        exit 1
    fi
}

main "$@"
