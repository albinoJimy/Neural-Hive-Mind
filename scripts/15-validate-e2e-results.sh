#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Script: 15-validate-e2e-results.sh
# Descrição: Valida resultados de testes E2E do Neural Hive-Mind
# Uso: ./15-validate-e2e-results.sh --input-file <arquivo>
# ==============================================================================

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variáveis padrão
INPUT_FILE=""
OUTPUT_FILE="${OUTPUT_FILE:-/tmp/e2e-validation-report.md}"
VERBOSE="${VERBOSE:-false}"

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# ==============================================================================
# Funções de Utilidade
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    cat << EOF
Uso: $0 --input-file <arquivo> [opções]

Opções:
  --input-file FILE         Arquivo de entrada (JSON ou Markdown) com dados E2E (obrigatório)
  --output-file FILE        Arquivo de saída do relatório (padrão: /tmp/e2e-validation-report.md)
  --verbose                 Modo verboso
  -h, --help                Mostra esta mensagem

Exemplos:
  $0 --input-file e2e-results.json
  $0 --input-file E2E_TESTING_CHECKLIST.md --output-file report.md

EOF
}

# ==============================================================================
# Parse de Argumentos
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --input-file)
            INPUT_FILE="$2"
            shift 2
            ;;
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            show_usage
            exit 1
            ;;
    esac
done

# ==============================================================================
# Validação de Argumentos
# ==============================================================================

if [ -z "$INPUT_FILE" ]; then
    log_error "Arquivo de entrada não especificado"
    show_usage
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    log_error "Arquivo de entrada não encontrado: $INPUT_FILE"
    exit 1
fi

log_info "Validando resultados E2E do arquivo: $INPUT_FILE"

# ==============================================================================
# Detectar Formato do Arquivo
# ==============================================================================

FILE_EXT="${INPUT_FILE##*.}"
FILE_FORMAT=""

if [ "$FILE_EXT" = "json" ]; then
    FILE_FORMAT="json"
    log_info "Formato detectado: JSON"
elif [ "$FILE_EXT" = "md" ]; then
    FILE_FORMAT="markdown"
    log_info "Formato detectado: Markdown"
else
    log_warning "Formato desconhecido, tentando detectar automaticamente..."
    if jq empty "$INPUT_FILE" 2>/dev/null; then
        FILE_FORMAT="json"
        log_info "Formato detectado: JSON"
    else
        FILE_FORMAT="markdown"
        log_info "Formato detectado: Markdown"
    fi
fi

# ==============================================================================
# Funções de Validação
# ==============================================================================

validate_field() {
    local field_name="$1"
    local field_value="$2"
    local validation_type="${3:-non_empty}"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    case "$validation_type" in
        non_empty)
            if [ -n "$field_value" ] && [ "$field_value" != "null" ] && [ "$field_value" != "_________________" ]; then
                PASSED_CHECKS=$((PASSED_CHECKS + 1))
                echo "PASS"
                return 0
            else
                FAILED_CHECKS=$((FAILED_CHECKS + 1))
                echo "FAIL"
                return 1
            fi
            ;;
        uuid)
            if [[ "$field_value" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
                PASSED_CHECKS=$((PASSED_CHECKS + 1))
                echo "PASS"
                return 0
            else
                FAILED_CHECKS=$((FAILED_CHECKS + 1))
                echo "FAIL"
                return 1
            fi
            ;;
        numeric)
            if [[ "$field_value" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
                PASSED_CHECKS=$((PASSED_CHECKS + 1))
                echo "PASS"
                return 0
            else
                FAILED_CHECKS=$((FAILED_CHECKS + 1))
                echo "FAIL"
                return 1
            fi
            ;;
        boolean)
            if [ "$field_value" = "true" ] || [ "$field_value" = "false" ]; then
                PASSED_CHECKS=$((PASSED_CHECKS + 1))
                echo "PASS"
                return 0
            else
                FAILED_CHECKS=$((FAILED_CHECKS + 1))
                echo "FAIL"
                return 1
            fi
            ;;
        *)
            log_warning "Tipo de validação desconhecido: $validation_type"
            echo "SKIP"
            return 2
            ;;
    esac
}

# ==============================================================================
# Processar Arquivo JSON
# ==============================================================================

process_json_file() {
    local json_file="$1"
    
    log_info "Processando arquivo JSON..."
    
    # Validar estrutura básica
    if ! jq empty "$json_file" 2>/dev/null; then
        log_error "Arquivo JSON inválido"
        return 1
    fi
    
    # Extrair campos principais
    INTENT_ID=$(jq -r '.intent_id // empty' "$json_file")
    PLAN_ID=$(jq -r '.plan_id // empty' "$json_file")
    DECISION_ID=$(jq -r '.decision_id // empty' "$json_file")
    TICKET_ID=$(jq -r '.ticket_id // empty' "$json_file")
    
    CONFIDENCE=$(jq -r '.confidence // empty' "$json_file")
    CONSENSUS_SCORE=$(jq -r '.consensus_score // empty' "$json_file")
    DIVERGENCE_SCORE=$(jq -r '.divergence_score // empty' "$json_file")
    
    NUM_SPECIALISTS=$(jq -r '.specialists_count // (.specialists | length) // empty' "$json_file")
    NUM_TICKETS=$(jq -r '.tickets_count // (.tickets | length) // empty' "$json_file")
    
    # Flags booleanas
    GATEWAY_HEALTHY=$(jq -r '.gateway_healthy // empty' "$json_file")
    KAFKA_PUBLISHED=$(jq -r '.kafka_published // empty' "$json_file")
    MONGODB_PERSISTED=$(jq -r '.mongodb_persisted // empty' "$json_file")
    REDIS_CACHED=$(jq -r '.redis_cached // empty' "$json_file")
    
    # Gerar relatório
    generate_report
}

# ==============================================================================
# Processar Arquivo Markdown
# ==============================================================================

process_markdown_file() {
    local md_file="$1"
    
    log_info "Processando arquivo Markdown..."
    
    # Extrair valores anotados (formato: campo → `valor`)
    INTENT_ID=$(grep -oP 'intent_id.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    PLAN_ID=$(grep -oP 'plan_id.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    DECISION_ID=$(grep -oP 'decision_id.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    TICKET_ID=$(grep -oP 'ticket_id.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    
    CONFIDENCE=$(grep -oP 'confidence.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    CONSENSUS_SCORE=$(grep -oP 'consensus_score.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    DIVERGENCE_SCORE=$(grep -oP 'divergence_score.*?→\s*`\K[^`]+' "$md_file" | head -1 || echo "")
    
    # Contar checkboxes marcados
    TOTAL_CHECKBOXES=$(grep -c '^\s*- \[.\]' "$md_file" || echo "0")
    CHECKED_BOXES=$(grep -c '^\s*- \[x\]' "$md_file" || echo "0")
    
    log_info "Checkboxes marcados: $CHECKED_BOXES / $TOTAL_CHECKBOXES"
    
    # Gerar relatório
    generate_report
}

# ==============================================================================
# Gerar Relatório
# ==============================================================================

generate_report() {
    log_info "Gerando relatório de validação..."
    
    cat > "$OUTPUT_FILE" << EOF
# Relatório de Validação E2E - Neural Hive-Mind

**Data**: $(date -u +%Y-%m-%dT%H:%M:%SZ)  
**Arquivo de entrada**: \`$INPUT_FILE\`  
**Formato**: $FILE_FORMAT

---

## Resumo Executivo

| Métrica | Valor | Status |
|---------|-------|--------|
| Total de validações | $TOTAL_CHECKS | 📊 |
| Validações aprovadas | $PASSED_CHECKS | ✅ |
| Validações falhadas | $FAILED_CHECKS | ❌ |
| Taxa de sucesso | $(awk "BEGIN {printf \"%.1f\", ($PASSED_CHECKS / ($TOTAL_CHECKS > 0 ? $TOTAL_CHECKS : 1)) * 100}")% | 📈 |

EOF

    if [ "$FILE_FORMAT" = "markdown" ]; then
        cat >> "$OUTPUT_FILE" << EOF
| Checkboxes marcados | $CHECKED_BOXES / $TOTAL_CHECKBOXES | 📋 |

EOF
    fi

    cat >> "$OUTPUT_FILE" << EOF
---

## Validação de Campos Principais

### Fluxo A: Gateway → Kafka

| Campo | Valor | Validação | Status |
|-------|-------|-----------|--------|
EOF

    # Validar intent_id
    STATUS=$(validate_field "intent_id" "$INTENT_ID" "uuid")
    echo "| intent_id | \`$INTENT_ID\` | UUID | $STATUS |" >> "$OUTPUT_FILE"
    
    # Validar confidence
    STATUS=$(validate_field "confidence" "$CONFIDENCE" "numeric")
    echo "| confidence | \`$CONFIDENCE\` | Numérico | $STATUS |" >> "$OUTPUT_FILE"
    
    cat >> "$OUTPUT_FILE" << EOF

### Fluxo B: STE → Specialists → Plano

| Campo | Valor | Validação | Status |
|-------|-------|-----------|--------|
EOF

    # Validar plan_id
    STATUS=$(validate_field "plan_id" "$PLAN_ID" "uuid")
    echo "| plan_id | \`$PLAN_ID\` | UUID | $STATUS |" >> "$OUTPUT_FILE"
    
    # Validar num_specialists
    STATUS=$(validate_field "num_specialists" "$NUM_SPECIALISTS" "numeric")
    echo "| specialists_count | \`$NUM_SPECIALISTS\` | Numérico | $STATUS |" >> "$OUTPUT_FILE"
    
    cat >> "$OUTPUT_FILE" << EOF

### Fluxo C: Consensus → Orchestrator → Tickets

| Campo | Valor | Validação | Status |
|-------|-------|-----------|--------|
EOF

    # Validar decision_id
    STATUS=$(validate_field "decision_id" "$DECISION_ID" "uuid")
    echo "| decision_id | \`$DECISION_ID\` | UUID | $STATUS |" >> "$OUTPUT_FILE"
    
    # Validar consensus_score
    STATUS=$(validate_field "consensus_score" "$CONSENSUS_SCORE" "numeric")
    echo "| consensus_score | \`$CONSENSUS_SCORE\` | Numérico | $STATUS |" >> "$OUTPUT_FILE"
    
    # Validar divergence_score
    STATUS=$(validate_field "divergence_score" "$DIVERGENCE_SCORE" "numeric")
    echo "| divergence_score | \`$DIVERGENCE_SCORE\` | Numérico | $STATUS |" >> "$OUTPUT_FILE"
    
    # Validar ticket_id
    STATUS=$(validate_field "ticket_id" "$TICKET_ID" "uuid")
    echo "| ticket_id | \`$TICKET_ID\` | UUID | $STATUS |" >> "$OUTPUT_FILE"
    
    # Validar num_tickets
    STATUS=$(validate_field "num_tickets" "$NUM_TICKETS" "numeric")
    echo "| tickets_count | \`$NUM_TICKETS\` | Numérico | $STATUS |" >> "$OUTPUT_FILE"
    
    cat >> "$OUTPUT_FILE" << EOF

---

## Validação de Flags Booleanas

| Flag | Valor | Status |
|------|-------|--------|
EOF

    if [ -n "$GATEWAY_HEALTHY" ]; then
        STATUS=$(validate_field "gateway_healthy" "$GATEWAY_HEALTHY" "boolean")
        echo "| gateway_healthy | \`$GATEWAY_HEALTHY\` | $STATUS |" >> "$OUTPUT_FILE"
    fi
    
    if [ -n "$KAFKA_PUBLISHED" ]; then
        STATUS=$(validate_field "kafka_published" "$KAFKA_PUBLISHED" "boolean")
        echo "| kafka_published | \`$KAFKA_PUBLISHED\` | $STATUS |" >> "$OUTPUT_FILE"
    fi
    
    if [ -n "$MONGODB_PERSISTED" ]; then
        STATUS=$(validate_field "mongodb_persisted" "$MONGODB_PERSISTED" "boolean")
        echo "| mongodb_persisted | \`$MONGODB_PERSISTED\` | $STATUS |" >> "$OUTPUT_FILE"
    fi
    
    if [ -n "$REDIS_CACHED" ]; then
        STATUS=$(validate_field "redis_cached" "$REDIS_CACHED" "boolean")
        echo "| redis_cached | \`$REDIS_CACHED\` | $STATUS |" >> "$OUTPUT_FILE"
    fi
    
    cat >> "$OUTPUT_FILE" << EOF

---

## Status Final

EOF

    # Determinar status final
    if [ $FAILED_CHECKS -eq 0 ]; then
        cat >> "$OUTPUT_FILE" << EOF
✅ **PASS**: Todas as validações foram aprovadas!

O sistema Neural Hive-Mind está funcionando corretamente end-to-end.
EOF
    elif [ $PASSED_CHECKS -gt $FAILED_CHECKS ]; then
        cat >> "$OUTPUT_FILE" << EOF
⚠️ **PARTIAL**: Algumas validações falharam

**Validações aprovadas**: $PASSED_CHECKS  
**Validações falhadas**: $FAILED_CHECKS

Revise os campos falhados acima e investigue as causas.
EOF
    else
        cat >> "$OUTPUT_FILE" << EOF
❌ **FAIL**: Muitas validações falharam

**Validações aprovadas**: $PASSED_CHECKS  
**Validações falhadas**: $FAILED_CHECKS

Há problemas críticos no pipeline E2E. Revise logs e configurações.
EOF
    fi
    
    cat >> "$OUTPUT_FILE" << EOF

---

## Recomendações

EOF

    if [ -z "$INTENT_ID" ] || [ "$INTENT_ID" = "_________________" ]; then
        echo "- ⚠️ **intent_id não preenchido**: Verifique se a intenção foi enviada ao Gateway" >> "$OUTPUT_FILE"
    fi
    
    if [ -z "$PLAN_ID" ] || [ "$PLAN_ID" = "_________________" ]; then
        echo "- ⚠️ **plan_id não preenchido**: Verifique se o STE processou a intenção" >> "$OUTPUT_FILE"
    fi
    
    if [ -z "$DECISION_ID" ] || [ "$DECISION_ID" = "_________________" ]; then
        echo "- ⚠️ **decision_id não preenchido**: Verifique se o Consensus Engine agregou as opiniões" >> "$OUTPUT_FILE"
    fi
    
    if [ -z "$TICKET_ID" ] || [ "$TICKET_ID" = "_________________" ]; then
        echo "- ⚠️ **ticket_id não preenchido**: Verifique se o Orchestrator gerou os tickets" >> "$OUTPUT_FILE"
    fi
    
    if [ $FAILED_CHECKS -gt 0 ]; then
        cat >> "$OUTPUT_FILE" << EOF

### Próximos Passos

1. Revisar logs dos componentes que falharam
2. Verificar conectividade entre serviços (Kafka, MongoDB, Redis)
3. Validar configurações de namespaces e labels
4. Re-executar testes E2E após correções
5. Consultar guia de troubleshooting: \`docs/manual-deployment/08-e2e-testing-manual-guide.md\`
EOF
    fi
    
    cat >> "$OUTPUT_FILE" << EOF

---

**Relatório gerado por**: \`15-validate-e2e-results.sh\`  
**Versão**: 1.0.0
EOF

    log_success "Relatório gerado: $OUTPUT_FILE"
}

# ==============================================================================
# Processar Arquivo de Entrada
# ==============================================================================

if [ "$FILE_FORMAT" = "json" ]; then
    process_json_file "$INPUT_FILE"
else
    process_markdown_file "$INPUT_FILE"
fi

# ==============================================================================
# Exibir Resumo
# ==============================================================================

echo ""
log_success "=========================================="
log_success "Validação E2E concluída!"
log_success "=========================================="
echo ""
log_info "Total de validações: $TOTAL_CHECKS"
log_success "Aprovadas: $PASSED_CHECKS"
log_error "Falhadas: $FAILED_CHECKS"
echo ""

if [ $FAILED_CHECKS -eq 0 ]; then
    log_success "✅ Status: PASS"
    exit 0
elif [ $PASSED_CHECKS -gt $FAILED_CHECKS ]; then
    log_warning "⚠️ Status: PARTIAL"
    exit 0
else
    log_error "❌ Status: FAIL"
    exit 1
fi
