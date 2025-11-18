#!/bin/bash

#######################################################################################################
# Script: generate-compliance-report.sh
# Descrição: Gera relatório executivo de compliance baseado nos resultados dos testes
# Autor: Neural Hive-Mind Team
# Data: 2025-11-12
# Versão: 1.0.0
#
# Referências:
# - scripts/helpers/test-helpers.sh (função generate_markdown_summary linhas 496-555)
#######################################################################################################

set -euo pipefail

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Configurações
readonly REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly RESULTS_DIR="$REPO_DIR/tests/results"
readonly OUTPUT_FILE="$RESULTS_DIR/GOVERNANCE_COMPLIANCE_EXECUTIVE_REPORT.md"

# Logging functions
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

# Função para parsear resultados de teste
parse_test_results() {
    local input_json="$1"

    if [[ ! -f "$input_json" ]]; then
        log_error "Arquivo de resultados não encontrado: $input_json"
        exit 1
    fi

    log_info "Parseando resultados de $input_json..."

    # Verificar se jq está disponível
    if ! command -v jq &> /dev/null; then
        log_error "jq não instalado. Instale jq para gerar relatório."
        exit 1
    fi

    # Extrair dados do JSON
    TEST_NAME=$(jq -r '.test_name // "Governance Compliance Test"' "$input_json")
    START_TIME=$(jq -r '.start_time // "N/A"' "$input_json")
    END_TIME=$(jq -r '.end_time // "N/A"' "$input_json")
    DURATION=$(jq -r '.duration_seconds // 0' "$input_json")

    AUDITABILITY=$(jq -r '.scores.auditability // 0' "$input_json")
    EXPLAINABILITY=$(jq -r '.scores.explainability // 0' "$input_json")
    COMPLIANCE=$(jq -r '.scores.compliance // 0' "$input_json")
    INTEGRITY=$(jq -r '.scores.integrity // 100' "$input_json")

    TOTAL_PHASES=$(jq -r '.summary.total // 0' "$input_json")
    PASSED_PHASES=$(jq -r '.summary.passed // 0' "$input_json")
    FAILED_PHASES=$(jq -r '.summary.failed // 0' "$input_json")

    log_success "Resultados parseados com sucesso"
}

# Função para calcular Overall Governance Score
calculate_overall_score() {
    OVERALL_SCORE=$(awk "BEGIN {printf \"%.1f\", ($AUDITABILITY + $EXPLAINABILITY + $COMPLIANCE + $INTEGRITY) / 4}")

    log_info "Overall Governance Score: $OVERALL_SCORE%"
}

# Função para determinar status de compliance
determine_compliance_status() {
    local score_int=${OVERALL_SCORE%.*}

    if [[ "$score_int" -ge 95 ]]; then
        COMPLIANCE_STATUS="✅ COMPLIANT"
        STATUS_COLOR="GREEN"
    elif [[ "$score_int" -ge 80 ]]; then
        COMPLIANCE_STATUS="⚠️ PARTIAL COMPLIANCE"
        STATUS_COLOR="YELLOW"
    else
        COMPLIANCE_STATUS="❌ NON-COMPLIANT"
        STATUS_COLOR="RED"
    fi

    log_info "Status: $COMPLIANCE_STATUS"
}

# Função para gerar executive summary
generate_executive_summary() {
    cat <<EOF
# Relatório de Compliance - Neural Hive-Mind Fase 1

**Data**: $(date +%Y-%m-%d\ %H:%M:%S)
**Teste**: $TEST_NAME
**Duração**: ${DURATION}s
**Overall Governance Score**: **$OVERALL_SCORE%** $COMPLIANCE_STATUS

---

## Executive Summary

Este relatório apresenta os resultados da validação de governança e compliance da Fase 1 do Neural Hive-Mind. O sistema foi avaliado em 4 dimensões principais: Auditabilidade, Explicabilidade, Compliance de Políticas e Integridade de Dados.

### Status Geral

- **Overall Governance Score**: $OVERALL_SCORE%
- **Status**: $COMPLIANCE_STATUS
- **Fases Aprovadas**: $PASSED_PHASES / $TOTAL_PHASES
- **Taxa de Sucesso**: $(awk "BEGIN {printf \"%.1f\", ($PASSED_PHASES / $TOTAL_PHASES) * 100}")%

---

## Scores por Categoria

| Categoria | Score | Target | Status |
|-----------|-------|--------|--------|
| **Auditabilidade** | $AUDITABILITY% | 100% | $([ "${AUDITABILITY%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| **Explicabilidade** | $EXPLAINABILITY% | 100% | $([ "${EXPLAINABILITY%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| **Compliance** | $COMPLIANCE% | 100% | $([ "${COMPLIANCE%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| **Integridade** | $INTEGRITY% | 100% | $([ "${INTEGRITY%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| **Overall** | **$OVERALL_SCORE%** | **≥95%** | **$([ "${OVERALL_SCORE%.*}" -ge 95 ] && echo "✅" || echo "⚠️")** |

---

EOF
}

# Função para gerar SLO compliance table
generate_slo_compliance_table() {
    cat <<EOF
## SLO Compliance - Fase 1

| SLO | Target | Atual | Status |
|-----|--------|-------|--------|
| Auditabilidade (Ledger) | 100% | $AUDITABILITY% | $([ "${AUDITABILITY%.*}" -ge 95 ] && echo "✅" || echo "❌") |
| Explicabilidade (Coverage) | 100% | $EXPLAINABILITY% | $([ "${EXPLAINABILITY%.*}" -ge 95 ] && echo "✅" || echo "❌") |
| Compliance (Violações) | 100% | $COMPLIANCE% | $([ "${COMPLIANCE%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| Integridade (Hash) | 100% | $INTEGRITY% | $([ "${INTEGRITY%.*}" -ge 95 ] && echo "✅" || echo "❌") |

### Detalhamento por SLO

#### 1. Auditabilidade (Ledger Cognitivo)
- **Objetivo**: 100% dos registros no ledger devem ter hash SHA-256
- **Resultado**: $AUDITABILITY%
- **Métrica Prometheus**: \`neural_hive_ledger_writes_total\`
- **Status**: $([ "${AUDITABILITY%.*}" -ge 95 ] && echo "✅ Atingido" || echo "❌ Não atingido")

#### 2. Explicabilidade (Coverage)
- **Objetivo**: 100% das decisões devem ter explainability_token
- **Resultado**: $EXPLAINABILITY%
- **Métrica Prometheus**: \`neural_hive_explainability_tokens_generated_total / neural_hive_consensus_decisions_total\`
- **Status**: $([ "${EXPLAINABILITY%.*}" -ge 95 ] && echo "✅ Atingido" || echo "❌ Não atingido")

#### 3. Compliance (Políticas OPA)
- **Objetivo**: 0 violações críticas (enforcement_action=deny)
- **Resultado**: $COMPLIANCE%
- **Métrica Prometheus**: \`gatekeeper_constraint_violations{enforcement_action="deny"}\`
- **Status**: $([ "${COMPLIANCE%.*}" -ge 95 ] && echo "✅ Atingido" || echo "⚠️ Violações warning detectadas")

#### 4. Integridade (Hash Verification)
- **Objetivo**: 100% dos hashes recalculados devem corresponder aos armazenados
- **Resultado**: $INTEGRITY%
- **Status**: $([ "${INTEGRITY%.*}" -ge 95 ] && echo "✅ Atingido" || echo "❌ Hashes inválidos detectados")

---

EOF
}

# Função para gerar detailed findings
generate_detailed_findings() {
    local input_json="$1"

    cat <<EOF
## Resultados Detalhados por Fase

EOF

    # Parsear resultados individuais
    local results_count
    results_count=$(jq '.results | length' "$input_json")

    for ((i=0; i<results_count; i++)); do
        local section
        local status
        local message

        section=$(jq -r ".results[$i].section" "$input_json")
        status=$(jq -r ".results[$i].status" "$input_json")
        message=$(jq -r ".results[$i].message" "$input_json")

        local icon="❓"
        case "$status" in
            passed) icon="✅" ;;
            failed) icon="❌" ;;
            warning) icon="⚠️" ;;
        esac

        echo "### $((i+1)). $section"
        echo ""
        echo "- **Status**: $icon $status"
        echo "- **Detalhes**: $message"
        echo ""
    done

    echo "---"
    echo ""
}

# Função para gerar recommendations
generate_recommendations() {
    cat <<EOF
## Recomendações

EOF

    local has_recommendations=0

    # Auditability
    if [[ "${AUDITABILITY%.*}" -lt 100 ]]; then
        cat <<EOF
### 1. Auditabilidade
- ⚠️ **Problema**: Nem todos os registros têm hash SHA-256
- **Ação**: Investigar registros sem hash e regenerar hashes ausentes
- **Prioridade**: Alta
- **Comando**: \`./scripts/governance/verify-ledger-integrity.sh\`

EOF
        has_recommendations=1
    fi

    # Explainability
    if [[ "${EXPLAINABILITY%.*}" -lt 100 ]]; then
        cat <<EOF
### 2. Explicabilidade
- ⚠️ **Problema**: Nem todas as decisões têm explainability_token
- **Ação**: Verificar feature flag \`enable_explainability\` e regenerar tokens ausentes
- **Prioridade**: Alta
- **Comando**: Habilitar flag em \`consensus-engine-config\`

EOF
        has_recommendations=1
    fi

    # Compliance
    if [[ "${COMPLIANCE%.*}" -lt 98 ]]; then
        cat <<EOF
### 3. Compliance
- ⚠️ **Problema**: Violações de políticas OPA detectadas
- **Ação**: Remediar violações antes de transicionar para enforcement mode 'deny'
- **Prioridade**: Média
- **Comando**: \`kubectl get constraints -A -o yaml\`

EOF
        has_recommendations=1
    fi

    # Integrity
    if [[ "${INTEGRITY%.*}" -lt 100 ]]; then
        cat <<EOF
### 4. Integridade
- ❌ **Problema**: Hashes inválidos detectados (possível adulteração)
- **Ação**: Investigar registros com hash inválido e restaurar de backup se necessário
- **Prioridade**: Crítica
- **Comando**: \`python3 scripts/governance/verify-hash-integrity.py --collection consensus_decisions --sample-size 100\`

EOF
        has_recommendations=1
    fi

    if [[ "$has_recommendations" -eq 0 ]]; then
        echo "✅ **Nenhuma recomendação necessária** - Sistema operando dentro dos SLOs"
        echo ""
    fi

    echo "---"
    echo ""
}

# Função para gerar next steps
generate_next_steps() {
    cat <<EOF
## Próximos Passos

EOF

    local score_int=${OVERALL_SCORE%.*}

    if [[ "$score_int" -ge 95 ]]; then
        cat <<EOF
### Status: COMPLIANT ✅

O sistema está em compliance com os requisitos de governança da Fase 1. Próximos passos:

1. **Monitorar violações por 7 dias** (modo warn)
   - Verificar alertas de governança no Prometheus
   - Revisar dashboards de compliance no Grafana

2. **Transição para enforcement mode 'deny'**
   - Atualizar constraints: \`enforcementAction: deny\`
   - Aplicar: \`kubectl apply -f policies/constraints/\`

3. **Deploy de componentes de segurança avançados** (Fase 2)
   - Istio mTLS (PeerAuthentication STRICT)
   - Sigstore (assinatura de imagens)
   - Vault (gestão de secrets)

4. **Habilitar auditoria contínua**
   - Configurar backup automático do ledger
   - Habilitar alertas de integridade
   - Configurar retention policy

EOF
    elif [[ "$score_int" -ge 80 ]]; then
        cat <<EOF
### Status: PARTIAL COMPLIANCE ⚠️

O sistema está parcialmente em compliance. Antes de prosseguir:

1. **Remediar violações identificadas**
   - Revisar recomendações acima
   - Aplicar correções necessárias
   - Re-executar teste de governança

2. **Monitorar métricas de governança**
   - Auditability Score ≥ 95%
   - Explainability Coverage ≥ 99%
   - Compliance Score ≥ 98%

3. **Re-validar após correções**
   - Executar: \`./tests/governance-compliance-test.sh\`
   - Gerar novo relatório
   - Confirmar Overall Score ≥ 95%

EOF
    else
        cat <<EOF
### Status: NON-COMPLIANT ❌

O sistema NÃO está em compliance. Ações urgentes necessárias:

1. **Revisão completa de governança**
   - Investigar falhas críticas
   - Revisar logs de deployment
   - Verificar integridade do ledger

2. **Restaurar de backup se necessário**
   - Verificar backups disponíveis
   - Restaurar dados comprometidos
   - Re-deployar componentes afetados

3. **Executar troubleshooting**
   - Verificar logs do Consensus Engine
   - Verificar conectividade MongoDB/Redis
   - Verificar status do OPA Gatekeeper

4. **Re-executar deployment**
   - Seguir: \`docs/GOVERNANCE_DEPLOYMENT_GUIDE.md\`
   - Validar cada fase individualmente
   - Confirmar pré-requisitos atendidos

EOF
    fi

    echo "---"
    echo ""
}

# Função para gerar footer
generate_footer() {
    cat <<EOF
## Referências

- [Governance Operations Guide](../../docs/operations/governance-operations.md)
- [Phase 1 Testing Guide](../../docs/PHASE1_TESTING_GUIDE.md)
- [Documento 04 - Segurança e Governança](../../docs/documento-04-seguranca-governanca-neural-hive-mind.md)
- [OPA Gatekeeper Documentation](https://open-policy-agent.github.io/gatekeeper/)

---

**Gerado por**: \`generate-compliance-report.sh\`
**Data**: $(date +%Y-%m-%d\ %H:%M:%S)
**Versão**: 1.0.0
EOF
}

# Main execution
main() {
    log_info "========================================="
    log_info "Geração de Relatório de Compliance"
    log_info "========================================="
    echo ""

    # Parsear argumentos
    local input_json=""
    local output_dir="$RESULTS_DIR"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --input-json)
                input_json="$2"
                shift 2
                ;;
            --output-dir)
                output_dir="$2"
                shift 2
                ;;
            *)
                log_error "Argumento desconhecido: $1"
                echo "Uso: $0 --input-json <arquivo.json> [--output-dir <diretório>]"
                exit 1
                ;;
        esac
    done

    # Validar argumentos
    if [[ -z "$input_json" ]]; then
        log_error "Arquivo de entrada não especificado"
        echo "Uso: $0 --input-json <arquivo.json> [--output-dir <diretório>]"
        exit 1
    fi

    # Criar diretório de saída
    mkdir -p "$output_dir"

    # Parsear resultados
    parse_test_results "$input_json"

    # Calcular overall score
    calculate_overall_score

    # Determinar status
    determine_compliance_status

    # Gerar relatório
    log_info "Gerando relatório executivo..."

    {
        generate_executive_summary
        generate_slo_compliance_table
        generate_detailed_findings "$input_json"
        generate_recommendations
        generate_next_steps
        generate_footer
    } > "$OUTPUT_FILE"

    log_success "Relatório gerado: $OUTPUT_FILE"

    # Exibir resumo
    echo ""
    log_info "========================================="
    log_info "RESUMO"
    log_info "========================================="
    log_info "Overall Governance Score: $OVERALL_SCORE%"
    log_info "Status: $COMPLIANCE_STATUS"
    log_info "Relatório: $OUTPUT_FILE"
    echo ""

    exit 0
}

# Executar main
main "$@"
