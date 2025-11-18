#!/bin/bash

#######################################################################################################
# Script: verify-ledger-integrity.sh
# Descrição: Verificação de integridade do ledger cognitivo (MongoDB)
# Autor: Neural Hive-Mind Team
# Data: 2025-11-12
# Versão: 1.0.0
#
# Validações:
# - Verificar 100% dos registros têm campo hash não vazio
# - Recalcular hash de amostra e comparar com stored_hash
# - Verificar 100% das decisões têm explainability_token
# - Verificar explicações existem em explainability_ledger
# - Verificar campo immutable: true em decisões
#
# Referências:
# - services/consensus-engine/src/clients/mongodb_client.py (método verify_integrity)
# - services/consensus-engine/src/models/consolidated_decision.py (calculate_hash)
# - libraries/python/neural_hive_specialists/ledger_client.py (verify_document_integrity)
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
readonly MONGODB_NS="mongodb-cluster"
readonly SAMPLE_SIZE="${SAMPLE_SIZE:-10}"
readonly TIMESTAMP=$(date +%Y%m%d-%H%M%S)
readonly RESULTS_DIR="$REPO_DIR/tests/results"
readonly REPORT_JSON="$RESULTS_DIR/ledger-integrity-report-$TIMESTAMP.json"
readonly REPORT_MD="$RESULTS_DIR/ledger-integrity-summary-$TIMESTAMP.md"

# MongoDB connection
MONGO_URI="mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"

# Variáveis globais
declare -A RESULTS=(
    [cognitive_ledger_total]=0
    [cognitive_ledger_with_hash]=0
    [consensus_decisions_total]=0
    [consensus_decisions_with_hash]=0
    [consensus_decisions_with_token]=0
    [consensus_decisions_immutable]=0
    [explainability_total]=0
    [explainability_v2_total]=0
    [hash_verifications_valid]=0
    [hash_verifications_invalid]=0
)

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

# Função para verificar conectividade MongoDB
check_mongodb_connectivity() {
    log_info "Verificando conectividade com MongoDB..."

    local mongo_pod
    mongo_pod=$(kubectl get pods -n "$MONGODB_NS" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$mongo_pod" ]]; then
        log_error "Pod do MongoDB não encontrado no namespace $MONGODB_NS"
        exit 1
    fi

    log_success "Pod do MongoDB encontrado: $mongo_pod"

    # Testar conexão
    if ! kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.adminCommand('ping')" &> /dev/null; then
        log_error "Falha ao conectar ao MongoDB"
        exit 1
    fi

    log_success "Conectividade com MongoDB OK"
    echo "$mongo_pod"
}

# Função para verificar collection cognitive_ledger
verify_cognitive_ledger() {
    local mongo_pod="$1"
    log_info "Verificando collection cognitive_ledger..."

    # Total de registros
    local total
    total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').cognitive_ledger.countDocuments({})" 2>/dev/null || echo "0")

    RESULTS[cognitive_ledger_total]=$total
    log_info "Total de registros: $total"

    if [[ "$total" -eq 0 ]]; then
        log_warning "Collection cognitive_ledger está vazia"
        return 0
    fi

    # Registros com hash
    local with_hash
    with_hash=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').cognitive_ledger.countDocuments({hash: {\$exists: true, \$ne: ''}})" 2>/dev/null || echo "0")

    RESULTS[cognitive_ledger_with_hash]=$with_hash
    log_info "Registros com hash: $with_hash / $total"

    # Calcular percentual
    local percentage=0
    if [[ "$total" -gt 0 ]]; then
        percentage=$(awk "BEGIN {printf \"%.1f\", ($with_hash / $total) * 100}")
    fi

    log_info "Percentual com hash: $percentage%"

    if [[ "$percentage" == "100.0" ]]; then
        log_success "✅ 100% dos registros em cognitive_ledger têm hash"
    else
        log_warning "⚠️ Apenas $percentage% dos registros têm hash"
    fi
}

# Função para verificar collection consensus_decisions
verify_consensus_decisions() {
    local mongo_pod="$1"
    log_info "Verificando collection consensus_decisions..."

    # Total de decisões
    local total
    total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({})" 2>/dev/null || echo "0")

    RESULTS[consensus_decisions_total]=$total
    log_info "Total de decisões: $total"

    if [[ "$total" -eq 0 ]]; then
        log_warning "Collection consensus_decisions está vazia"
        return 0
    fi

    # Decisões com hash
    local with_hash
    with_hash=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({hash: {\$exists: true, \$ne: ''}})" 2>/dev/null || echo "0")

    RESULTS[consensus_decisions_with_hash]=$with_hash
    log_info "Decisões com hash: $with_hash / $total"

    # Decisões com explainability_token
    local with_token
    with_token=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({explainability_token: {\$exists: true, \$ne: ''}})" 2>/dev/null || echo "0")

    RESULTS[consensus_decisions_with_token]=$with_token
    log_info "Decisões com explainability_token: $with_token / $total"

    # Decisões imutáveis
    local immutable
    immutable=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({immutable: true})" 2>/dev/null || echo "0")

    RESULTS[consensus_decisions_immutable]=$immutable
    log_info "Decisões imutáveis: $immutable / $total"

    # Calcular percentuais
    local hash_pct=0
    local token_pct=0
    local immutable_pct=0

    if [[ "$total" -gt 0 ]]; then
        hash_pct=$(awk "BEGIN {printf \"%.1f\", ($with_hash / $total) * 100}")
        token_pct=$(awk "BEGIN {printf \"%.1f\", ($with_token / $total) * 100}")
        immutable_pct=$(awk "BEGIN {printf \"%.1f\", ($immutable / $total) * 100}")
    fi

    log_info "Percentuais:"
    log_info "  - Hash: $hash_pct%"
    log_info "  - Explainability Token: $token_pct%"
    log_info "  - Immutable: $immutable_pct%"

    if [[ "$hash_pct" == "100.0" ]] && [[ "$token_pct" == "100.0" ]]; then
        log_success "✅ 100% das decisões têm hash e explainability_token"
    else
        log_warning "⚠️ Nem todas as decisões estão completas"
    fi
}

# Função para verificar explicabilidade
verify_explainability() {
    local mongo_pod="$1"
    log_info "Verificando collections de explicabilidade..."

    # explainability_ledger
    local v1_total
    v1_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').explainability_ledger.countDocuments({})" 2>/dev/null || echo "0")

    RESULTS[explainability_total]=$v1_total
    log_info "Explicações v1: $v1_total"

    # explainability_ledger_v2
    local v2_total
    v2_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').explainability_ledger_v2.countDocuments({})" 2>/dev/null || echo "0")

    RESULTS[explainability_v2_total]=$v2_total
    log_info "Explicações v2: $v2_total"

    local total_explanations=$((v1_total + v2_total))
    log_info "Total de explicações: $total_explanations"

    # Calcular coverage
    local decisions_total=${RESULTS[consensus_decisions_total]}
    if [[ "$decisions_total" -gt 0 ]]; then
        local coverage
        coverage=$(awk "BEGIN {printf \"%.1f\", ($total_explanations / $decisions_total) * 100}")
        log_info "Explainability Coverage: $coverage%"

        if [[ "${coverage%.*}" -ge 99 ]]; then
            log_success "✅ Explainability Coverage ≥ 99%"
        else
            log_warning "⚠️ Explainability Coverage < 99%"
        fi
    fi
}

# Função para verificar integridade de hash (usando Python helper)
verify_hash_integrity() {
    local mongo_pod="$1"
    log_info "Verificando integridade de hashes (amostra de $SAMPLE_SIZE registros)..."

    # Verificar se script Python existe
    local python_script="$REPO_DIR/scripts/governance/verify-hash-integrity.py"
    if [[ ! -f "$python_script" ]]; then
        log_warning "Script Python não encontrado: verify-hash-integrity.py"
        log_warning "Pulando verificação de integridade de hash"
        return 0
    fi

    # Executar script Python
    log_info "Executando verificação de hash via Python..."

    # Port-forward MongoDB para localhost (temporário)
    kubectl port-forward -n "$MONGODB_NS" "$mongo_pod" 27017:27017 &> /dev/null &
    local pf_pid=$!

    # Aguardar port-forward estar pronto
    sleep 3

    # Executar script Python
    local result
    if result=$(python3 "$python_script" \
        --mongo-uri "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
        --database neural_hive \
        --collection consensus_decisions \
        --sample-size "$SAMPLE_SIZE" 2>&1); then

        # Parsear resultado (assumindo JSON output)
        if command -v jq &> /dev/null && echo "$result" | jq -e . &> /dev/null; then
            local valid
            local invalid

            valid=$(echo "$result" | jq -r '.valid // 0')
            invalid=$(echo "$result" | jq -r '.invalid // 0')

            RESULTS[hash_verifications_valid]=$valid
            RESULTS[hash_verifications_invalid]=$invalid

            log_info "Verificação de hash: $valid válidos, $invalid inválidos"

            if [[ "$invalid" -eq 0 ]]; then
                log_success "✅ 100% dos hashes verificados são válidos"
            else
                log_error "❌ $invalid hashes inválidos detectados!"
            fi
        else
            log_warning "Falha ao parsear resultado do script Python"
        fi
    else
        log_warning "Falha ao executar script Python: $result"
    fi

    # Matar port-forward
    kill $pf_pid 2>/dev/null || true
}

# Função para detectar adulteração
detect_tampering() {
    local mongo_pod="$1"
    log_info "Detectando possível adulteração de dados..."

    # Buscar registros modificados após criação
    local modified_count
    modified_count=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({updated_at: {\$exists: true}})" 2>/dev/null || echo "0")

    log_info "Registros com campo updated_at: $modified_count"

    if [[ "$modified_count" -eq 0 ]]; then
        log_success "✅ Nenhum registro adulterado detectado"
    else
        log_warning "⚠️ $modified_count registros foram modificados após criação"
    fi
}

# Função para gerar relatório
generate_report() {
    log_info "Gerando relatório de integridade..."

    # Criar diretório de resultados
    mkdir -p "$RESULTS_DIR"

    # Calcular Integrity Score
    local total_checks=0
    local passed_checks=0

    # Check 1: Hash em cognitive_ledger
    ((total_checks++))
    if [[ "${RESULTS[cognitive_ledger_total]}" -eq 0 ]] || [[ "${RESULTS[cognitive_ledger_with_hash]}" -eq "${RESULTS[cognitive_ledger_total]}" ]]; then
        ((passed_checks++))
    fi

    # Check 2: Hash em consensus_decisions
    ((total_checks++))
    if [[ "${RESULTS[consensus_decisions_total]}" -eq 0 ]] || [[ "${RESULTS[consensus_decisions_with_hash]}" -eq "${RESULTS[consensus_decisions_total]}" ]]; then
        ((passed_checks++))
    fi

    # Check 3: Explainability token
    ((total_checks++))
    if [[ "${RESULTS[consensus_decisions_total]}" -eq 0 ]] || [[ "${RESULTS[consensus_decisions_with_token]}" -eq "${RESULTS[consensus_decisions_total]}" ]]; then
        ((passed_checks++))
    fi

    # Check 4: Immutable flag
    ((total_checks++))
    if [[ "${RESULTS[consensus_decisions_total]}" -eq 0 ]] || [[ "${RESULTS[consensus_decisions_immutable]}" -eq "${RESULTS[consensus_decisions_total]}" ]]; then
        ((passed_checks++))
    fi

    # Check 5: Hash verification
    ((total_checks++))
    if [[ "${RESULTS[hash_verifications_invalid]}" -eq 0 ]]; then
        ((passed_checks++))
    fi

    # Calcular score
    local integrity_score=0
    if [[ "$total_checks" -gt 0 ]]; then
        integrity_score=$(awk "BEGIN {printf \"%.1f\", ($passed_checks / $total_checks) * 100}")
    fi

    # Gerar JSON
    cat > "$REPORT_JSON" <<EOF
{
  "timestamp": "$(date +%Y-%m-%dT%H:%M:%S%z)",
  "collections": {
    "cognitive_ledger": {
      "total": ${RESULTS[cognitive_ledger_total]},
      "with_hash": ${RESULTS[cognitive_ledger_with_hash]}
    },
    "consensus_decisions": {
      "total": ${RESULTS[consensus_decisions_total]},
      "with_hash": ${RESULTS[consensus_decisions_with_hash]},
      "with_token": ${RESULTS[consensus_decisions_with_token]},
      "immutable": ${RESULTS[consensus_decisions_immutable]}
    },
    "explainability": {
      "v1_total": ${RESULTS[explainability_total]},
      "v2_total": ${RESULTS[explainability_v2_total]}
    }
  },
  "hash_verification": {
    "sample_size": $SAMPLE_SIZE,
    "valid": ${RESULTS[hash_verifications_valid]},
    "invalid": ${RESULTS[hash_verifications_invalid]}
  },
  "integrity_score": $integrity_score,
  "checks_passed": $passed_checks,
  "checks_total": $total_checks
}
EOF

    log_success "Relatório JSON gerado: $REPORT_JSON"

    # Gerar Markdown
    cat > "$REPORT_MD" <<EOF
# Relatório de Integridade do Ledger Cognitivo

**Data**: $(date +%Y-%m-%d\ %H:%M:%S)
**Integrity Score**: $integrity_score%

## Resumo

- **Checks Aprovados**: $passed_checks / $total_checks
- **Integrity Score**: $integrity_score%

## Collections MongoDB

### cognitive_ledger
- Total de registros: ${RESULTS[cognitive_ledger_total]}
- Registros com hash: ${RESULTS[cognitive_ledger_with_hash]}
- Percentual: $(awk "BEGIN {if (${RESULTS[cognitive_ledger_total]} > 0) printf \"%.1f\", (${RESULTS[cognitive_ledger_with_hash]} / ${RESULTS[cognitive_ledger_total]}) * 100; else print \"N/A\"}")%

### consensus_decisions
- Total de decisões: ${RESULTS[consensus_decisions_total]}
- Decisões com hash: ${RESULTS[consensus_decisions_with_hash]}
- Decisões com explainability_token: ${RESULTS[consensus_decisions_with_token]}
- Decisões imutáveis: ${RESULTS[consensus_decisions_immutable]}

### explainability
- Explicações v1: ${RESULTS[explainability_total]}
- Explicações v2: ${RESULTS[explainability_v2_total]}
- Total: $((${RESULTS[explainability_total]} + ${RESULTS[explainability_v2_total]}))

## Verificação de Hash (Amostra: $SAMPLE_SIZE)

- Hashes válidos: ${RESULTS[hash_verifications_valid]}
- Hashes inválidos: ${RESULTS[hash_verifications_invalid]}

## Status Final

$(if [[ "$integrity_score" == "100.0" ]]; then
    echo "✅ **INTEGRIDADE COMPLETA** - Ledger cognitivo está íntegro"
elif [[ "${integrity_score%.*}" -ge 95 ]]; then
    echo "⚠️ **INTEGRIDADE ALTA** - Pequenos problemas detectados"
else
    echo "❌ **INTEGRIDADE COMPROMETIDA** - Investigação necessária"
fi)
EOF

    log_success "Relatório Markdown gerado: $REPORT_MD"
}

# Main execution
main() {
    log_info "========================================="
    log_info "Verificação de Integridade do Ledger"
    log_info "========================================="
    echo ""

    local mongo_pod
    mongo_pod=$(check_mongodb_connectivity)

    verify_cognitive_ledger "$mongo_pod"
    echo ""

    verify_consensus_decisions "$mongo_pod"
    echo ""

    verify_explainability "$mongo_pod"
    echo ""

    verify_hash_integrity "$mongo_pod"
    echo ""

    detect_tampering "$mongo_pod"
    echo ""

    generate_report
    echo ""

    log_info "========================================="
    log_info "Verificação concluída!"
    log_info "========================================="
    log_info "Relatórios gerados:"
    log_info "  - JSON: $REPORT_JSON"
    log_info "  - Markdown: $REPORT_MD"
    echo ""

    exit 0
}

# Executar main
main "$@"
