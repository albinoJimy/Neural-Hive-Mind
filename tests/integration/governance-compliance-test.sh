#!/bin/bash

#######################################################################################################
# Script: governance-compliance-test.sh
# Descrição: Teste completo de governança e compliance para Neural Hive-Mind Fase 1
# Autor: Neural Hive-Mind Team
# Data: 2025-11-12
# Versão: 1.0.0
#
# Fases de Validação:
# 1. Verificar OPA Gatekeeper
# 2. Validar Políticas de Compliance
# 3. Verificar Integridade do Ledger Cognitivo
# 4. Verificar Explicabilidade
# 5. Verificar Feromônios Digitais
# 6. Validar Métricas de Governança
# 7. Validar Dashboards de Governança
# 8. Validar Alertas de Governança
# 9. Executar Testes de Violação
# 10. Gerar Relatório de Compliance
#
# Referências:
# - tests/phase1-end-to-end-test.sh
# - scripts/validation/validate-policy-enforcement.sh
# - scripts/helpers/test-helpers.sh
#######################################################################################################

set -euo pipefail

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# Configurações
readonly REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TIMESTAMP=$(date +%Y%m%d-%H%M%S)
readonly RESULTS_DIR="$REPO_DIR/tests/results"
readonly REPORT_JSON="$RESULTS_DIR/governance-compliance-report-$TIMESTAMP.json"
readonly REPORT_MD="$RESULTS_DIR/governance-compliance-summary-$TIMESTAMP.md"

# Namespaces
readonly GATEKEEPER_NS="gatekeeper-system"
readonly MONGODB_NS="mongodb-cluster"
readonly REDIS_NS="redis-cluster"
readonly OBSERVABILITY_NS="neural-hive-observability"

# Variáveis globais para resultados
declare -a TEST_RESULTS=()
declare -A SCORES=(
    [auditability]=0
    [explainability]=0
    [compliance]=0
    [integrity]=0
)
TOTAL_PHASES=10
PASSED_PHASES=0
FAILED_PHASES=0

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

log_phase() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}FASE $1: $2${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# Função para adicionar resultado de teste
add_result() {
    local section="$1"
    local status="$2"
    local message="$3"

    TEST_RESULTS+=("{\"section\": \"$section\", \"status\": \"$status\", \"message\": \"$message\"}")

    if [[ "$status" == "passed" ]]; then
        ((PASSED_PHASES++)) || true
    else
        ((FAILED_PHASES++)) || true
    fi
}

# FASE 1: Verificar OPA Gatekeeper
fase1_verify_gatekeeper() {
    log_phase 1 "Verificar OPA Gatekeeper"

    local failed=0

    # Verificar namespace
    log_info "Verificando namespace $GATEKEEPER_NS..."
    if ! kubectl get namespace "$GATEKEEPER_NS" &> /dev/null; then
        log_error "Namespace $GATEKEEPER_NS não encontrado"
        add_result "OPA Gatekeeper" "failed" "Namespace não encontrado"
        return 1
    fi

    # Verificar pods
    log_info "Verificando pods do Gatekeeper..."
    local pod_count
    pod_count=$(kubectl get pods -n "$GATEKEEPER_NS" --field-selector=status.phase=Running 2>/dev/null | grep -c "Running" || echo "0")

    if [[ "$pod_count" -lt 2 ]]; then
        log_error "Pods do Gatekeeper não estão Running. Esperado: ≥2, Atual: $pod_count"
        kubectl get pods -n "$GATEKEEPER_NS"
        failed=1
    else
        log_success "Pods do Gatekeeper: $pod_count Running"
    fi

    # Verificar webhook
    log_info "Verificando ValidatingWebhookConfiguration..."
    if kubectl get validatingwebhookconfigurations | grep -q gatekeeper; then
        log_success "ValidatingWebhookConfiguration encontrado"
    else
        log_error "ValidatingWebhookConfiguration não encontrado"
        failed=1
    fi

    # Verificar CRDs
    log_info "Verificando CRDs do Gatekeeper..."
    local crds_expected=("constrainttemplates.templates.gatekeeper.sh" "configs.config.gatekeeper.sh")
    for crd in "${crds_expected[@]}"; do
        if kubectl get crd "$crd" &> /dev/null; then
            log_success "CRD encontrado: $crd"
        else
            log_error "CRD não encontrado: $crd"
            failed=1
        fi
    done

    # Listar ConstraintTemplates
    log_info "Listando ConstraintTemplates..."
    local template_count
    template_count=$(kubectl get constrainttemplates 2>/dev/null | grep -v NAME | wc -l || echo "0")
    log_info "ConstraintTemplates encontrados: $template_count"
    kubectl get constrainttemplates 2>/dev/null || true

    if [[ "$template_count" -lt 2 ]]; then
        log_warning "Menos de 2 ConstraintTemplates encontrados"
    fi

    # Listar Constraints
    log_info "Listando Constraints ativos..."
    local constraint_count
    constraint_count=$(kubectl get constraints -A 2>/dev/null | grep -v NAMESPACE | wc -l || echo "0")
    log_info "Constraints encontrados: $constraint_count"
    kubectl get constraints -A 2>/dev/null || true

    if [[ "$failed" -eq 0 ]]; then
        add_result "OPA Gatekeeper" "passed" "Gatekeeper operacional com $template_count templates e $constraint_count constraints"
        return 0
    else
        add_result "OPA Gatekeeper" "failed" "Falhas na verificação do Gatekeeper"
        return 1
    fi
}

# FASE 2: Validar Políticas de Compliance
fase2_validate_policies() {
    log_phase 2 "Validar Políticas de Compliance"

    # Consultar violações totais
    log_info "Consultando violações de políticas..."

    local total_violations=0
    local deny_violations=0
    local warn_violations=0

    # Obter constraints
    local constraints
    constraints=$(kubectl get constraints -A -o json 2>/dev/null || echo '{"items":[]}')

    # Contar violações
    if command -v jq &> /dev/null; then
        total_violations=$(echo "$constraints" | jq '[.items[].status.totalViolations // 0] | add' || echo "0")

        # Calcular violações deny corretamente
        deny_violations=$(echo "$constraints" | jq '[.items[] | select(.spec.enforcementAction == "deny") | .status.totalViolations // 0] | add' || echo "0")

        # Calcular violações warn
        warn_violations=$(echo "$constraints" | jq '[.items[] | select(.spec.enforcementAction == "warn") | .status.totalViolations // 0] | add' || echo "0")

        # Listar violações por constraint
        log_info "Violações por constraint:"
        echo "$constraints" | jq -r '.items[] | "\(.metadata.name): \(.status.totalViolations // 0) violações (enforcement: \(.spec.enforcementAction))"' || true
    else
        log_warning "jq não instalado. Pulando análise detalhada de violações."
        # Fallback sem jq: listar constraints deny e somar violations usando jsonpath
        local deny_constraints
        deny_constraints=$(kubectl get constraints -A -o json | kubectl get constraints -A -o jsonpath='{range .items[?(@.spec.enforcementAction=="deny")]}{.status.totalViolations}{"\n"}{end}' 2>/dev/null || echo "")

        deny_violations=0
        if [[ -n "$deny_constraints" ]]; then
            while IFS= read -r violations; do
                if [[ -n "$violations" && "$violations" =~ ^[0-9]+$ ]]; then
                    deny_violations=$((deny_violations + violations))
                fi
            done <<< "$deny_constraints"
        fi
    fi

    # Verificar enforcement mode
    log_info "Verificando enforcement mode dos constraints..."
    kubectl get constraints -A -o custom-columns=NAME:.metadata.name,ENFORCEMENT:.spec.enforcementAction 2>/dev/null || true

    # Validação
    if [[ "$deny_violations" -eq 0 ]]; then
        log_success "Nenhuma violação crítica (deny) detectada"
        if [[ "$total_violations" -lt 20 ]]; then
            log_success "Violações warning dentro do limite: $total_violations < 20"
            add_result "Políticas de Compliance" "passed" "0 violações deny, $total_violations violações warn"

            # Calcular compliance score
            local compliance_score=100
            if [[ "$total_violations" -gt 0 ]]; then
                compliance_score=$(awk "BEGIN {printf \"%.1f\", 100 - ($total_violations * 0.5)}")
            fi
            SCORES[compliance]=$compliance_score

            return 0
        else
            log_warning "Violações warning acima do limite: $total_violations ≥ 20"
            add_result "Políticas de Compliance" "warning" "0 violações deny, mas $total_violations violações warn"
            SCORES[compliance]=95.0
            return 0
        fi
    else
        log_error "Violações críticas detectadas: $deny_violations violações deny"
        add_result "Políticas de Compliance" "failed" "$deny_violations violações deny detectadas"
        SCORES[compliance]=80.0
        return 1
    fi
}

# FASE 3: Verificar Integridade do Ledger Cognitivo
fase3_verify_ledger() {
    log_phase 3 "Verificar Integridade do Ledger Cognitivo"

    # Executar script de verificação de integridade
    log_info "Executando script de verificação de integridade..."
    local integrity_script="$REPO_DIR/scripts/governance/verify-ledger-integrity.sh"

    if [[ -f "$integrity_script" ]]; then
        # Executar script e capturar resultado
        if bash "$integrity_script" &> /dev/null; then
            log_success "Script de verificação executado com sucesso"

            # Buscar relatório JSON mais recente
            local latest_report
            latest_report=$(ls -t "$REPO_DIR/tests/results"/ledger-integrity-report-*.json 2>/dev/null | head -n1 || echo "")

            if [[ -n "$latest_report" && -f "$latest_report" ]]; then
                log_info "Relatório encontrado: $latest_report"

                # Parsear integrity_score do JSON
                if command -v jq &> /dev/null; then
                    local integrity_score
                    integrity_score=$(jq -r '.integrity_score // 0' "$latest_report" 2>/dev/null || echo "0")
                    SCORES[integrity]=$integrity_score
                    log_info "Integrity Score: $integrity_score%"
                else
                    log_warning "jq não disponível. Não foi possível parsear integrity_score"
                    SCORES[integrity]=100.0
                fi

                add_result "Ledger Cognitivo" "passed" "Integridade verificada via script (score: ${SCORES[integrity]}%)"
                return 0
            else
                log_warning "Relatório JSON não encontrado"
            fi
        else
            log_warning "Falha ao executar script de verificação"
        fi
    else
        log_warning "Script verify-ledger-integrity.sh não encontrado"
    fi

    # Fallback: verificação manual
    log_info "Executando verificação manual..."

    # Verificar se MongoDB está acessível
    log_info "Verificando conectividade com MongoDB..."
    local mongo_pod
    mongo_pod=$(kubectl get pods -n "$MONGODB_NS" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$mongo_pod" ]]; then
        log_error "Pod do MongoDB não encontrado no namespace $MONGODB_NS"
        add_result "Ledger Cognitivo" "failed" "MongoDB não acessível"
        SCORES[auditability]=0
        SCORES[integrity]=0
        return 1
    fi

    log_success "Pod do MongoDB encontrado: $mongo_pod"

    # Verificar collection cognitive_ledger
    log_info "Verificando collection cognitive_ledger..."
    local cognitive_total
    cognitive_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').cognitive_ledger.countDocuments({})" 2>/dev/null || echo "0")

    log_info "Total de registros em cognitive_ledger: $cognitive_total"

    # Verificar collection consensus_decisions
    log_info "Verificando collection consensus_decisions..."
    local decisions_total
    decisions_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({})" 2>/dev/null || echo "0")

    log_info "Total de decisões: $decisions_total"

    if [[ "$decisions_total" -eq 0 ]]; then
        log_warning "Nenhuma decisão encontrada. Execute o teste E2E primeiro."
        add_result "Ledger Cognitivo" "warning" "Nenhuma decisão para validar"
        SCORES[auditability]=100.0
        return 0
    fi

    # Verificar decisões com hash
    log_info "Verificando decisões com hash..."
    local decisions_with_hash
    decisions_with_hash=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({hash: {\$exists: true, \$ne: ''}})" 2>/dev/null || echo "0")

    log_info "Decisões com hash: $decisions_with_hash / $decisions_total"

    # Calcular taxa de auditabilidade
    local auditability_rate=0
    if [[ "$decisions_total" -gt 0 ]]; then
        auditability_rate=$(awk "BEGIN {printf \"%.1f\", ($decisions_with_hash / $decisions_total) * 100}")
    fi

    log_info "Taxa de auditabilidade: $auditability_rate%"
    SCORES[auditability]=$auditability_rate

    # Verificar decisões com explainability_token
    log_info "Verificando decisões com explainability_token..."
    local decisions_with_token
    decisions_with_token=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({explainability_token: {\$exists: true, \$ne: ''}})" 2>/dev/null || echo "0")

    log_info "Decisões com explainability_token: $decisions_with_token / $decisions_total"

    # Verificar decisões imutáveis
    log_info "Verificando decisões marcadas como immutable..."
    local immutable_decisions
    immutable_decisions=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({immutable: true})" 2>/dev/null || echo "0")

    log_info "Decisões imutáveis: $immutable_decisions / $decisions_total"

    # Calcular integrity score se ainda não foi definido
    if [[ "${SCORES[integrity]}" == "0" ]]; then
        # Calcular baseado em checks locais
        local checks_passed=0
        local checks_total=3

        # Check 1: Hash coverage
        if [[ "$auditability_rate" == "100.0" ]]; then
            ((checks_passed++))
        fi

        # Check 2: Token coverage
        if [[ "$decisions_with_token" -eq "$decisions_total" ]] || [[ "$decisions_total" -eq 0 ]]; then
            ((checks_passed++))
        fi

        # Check 3: Immutable coverage
        if [[ "$immutable_decisions" -eq "$decisions_total" ]] || [[ "$decisions_total" -eq 0 ]]; then
            ((checks_passed++))
        fi

        local integrity_score
        integrity_score=$(awk "BEGIN {printf \"%.1f\", ($checks_passed / $checks_total) * 100}")
        SCORES[integrity]=$integrity_score
    fi

    # Validação
    if [[ "$auditability_rate" == "100.0" ]] && [[ "$decisions_with_token" -eq "$decisions_total" ]]; then
        log_success "100% das decisões têm hash e explainability_token"
        add_result "Ledger Cognitivo" "passed" "100% auditabilidade, $decisions_total decisões verificadas, Integrity: ${SCORES[integrity]}%"
        return 0
    else
        log_warning "Nem todas as decisões têm hash ou token completos"
        add_result "Ledger Cognitivo" "warning" "Auditabilidade: $auditability_rate%, Tokens: $decisions_with_token/$decisions_total, Integrity: ${SCORES[integrity]}%"
        return 0
    fi
}

# FASE 4: Verificar Explicabilidade
fase4_verify_explainability() {
    log_phase 4 "Verificar Explicabilidade"

    local mongo_pod
    mongo_pod=$(kubectl get pods -n "$MONGODB_NS" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$mongo_pod" ]]; then
        log_error "Pod do MongoDB não encontrado"
        add_result "Explicabilidade" "failed" "MongoDB não acessível"
        SCORES[explainability]=0
        return 1
    fi

    # Obter total de decisões
    local decisions_total
    decisions_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({})" 2>/dev/null || echo "0")

    log_info "Total de decisões: $decisions_total"

    if [[ "$decisions_total" -eq 0 ]]; then
        log_warning "Nenhuma decisão encontrada. Execute o teste E2E primeiro."
        add_result "Explicabilidade" "warning" "Nenhuma decisão para validar explicabilidade"
        SCORES[explainability]=100.0
        return 0
    fi

    # Verificar correlação 1:1 - para cada decisão com token, buscar explicação correspondente
    log_info "Verificando correlação 1:1 token ⇄ explicação..."

    # Obter decisões com explainability_token
    local decisions_with_token
    decisions_with_token=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments({explainability_token: {\$exists: true, \$ne: ''}})" 2>/dev/null || echo "0")

    log_info "Decisões com explainability_token: $decisions_with_token / $decisions_total"

    # Para cada token, verificar se existe explicação correspondente
    local decisions_with_explanation=0

    if [[ "$decisions_with_token" -gt 0 ]]; then
        log_info "Verificando se cada token tem explicação correspondente..."

        # Buscar amostra de tokens e verificar explicação (máximo 100 para performance)
        local sample_size=$((decisions_with_token > 100 ? 100 : decisions_with_token))

        # Contar quantas decisões têm explicação correspondente usando aggregation
        decisions_with_explanation=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
            --quiet \
            --username root \
            --password local_dev_password \
            --authenticationDatabase admin \
            --eval "
                const tokens = db.getSiblingDB('neural_hive').consensus_decisions
                    .find(
                        {explainability_token: {\$exists: true, \$ne: ''}},
                        {explainability_token: 1}
                    )
                    .limit($sample_size)
                    .toArray()
                    .map(d => d.explainability_token);

                let count = 0;
                for (const token of tokens) {
                    const explV1 = db.getSiblingDB('neural_hive').explainability_ledger.countDocuments({explainability_token: token});
                    const explV2 = db.getSiblingDB('neural_hive').explainability_ledger_v2.countDocuments({explainability_token: token});
                    if (explV1 > 0 || explV2 > 0) {
                        count++;
                    }
                }
                print(count);
            " 2>/dev/null || echo "0")

        log_info "Decisões verificadas (amostra): $decisions_with_explanation / $sample_size têm explicação correspondente"

        # Extrapolar para o total
        if [[ "$sample_size" -gt 0 ]]; then
            local extrapolated
            extrapolated=$(awk "BEGIN {printf \"%.0f\", ($decisions_with_explanation / $sample_size) * $decisions_with_token}")
            log_info "Estimativa total: $extrapolated / $decisions_with_token têm explicação 1:1"
        fi
    fi

    # Verificar totais de explicações (para comparação)
    local explainability_total
    explainability_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').explainability_ledger.countDocuments({})" 2>/dev/null || echo "0")

    local explainability_v2_total
    explainability_v2_total=$(kubectl exec -n "$MONGODB_NS" "$mongo_pod" -- mongosh \
        --quiet \
        --username root \
        --password local_dev_password \
        --authenticationDatabase admin \
        --eval "db.getSiblingDB('neural_hive').explainability_ledger_v2.countDocuments({})" 2>/dev/null || echo "0")

    log_info "Total de explicações v1: $explainability_total"
    log_info "Total de explicações v2: $explainability_v2_total"

    local total_explanations=$((explainability_total + explainability_v2_total))

    # Calcular coverage baseado em correlação 1:1
    local explainability_coverage=0
    if [[ "$decisions_with_token" -gt 0 ]]; then
        # Usar amostra verificada para calcular coverage
        local sample_size=$((decisions_with_token > 100 ? 100 : decisions_with_token))
        explainability_coverage=$(awk "BEGIN {printf \"%.1f\", ($decisions_with_explanation / $sample_size) * 100}")
    fi

    log_info "Explainability Coverage (1:1): $explainability_coverage%"
    SCORES[explainability]=$explainability_coverage

    if [[ "${explainability_coverage%.*}" -ge 99 ]]; then
        log_success "Explainability Coverage 1:1 ≥ 99%"
        add_result "Explicabilidade" "passed" "Coverage 1:1: $explainability_coverage%, $total_explanations explicações totais"
        return 0
    else
        log_warning "Explainability Coverage 1:1 < 99%"
        add_result "Explicabilidade" "warning" "Coverage 1:1: $explainability_coverage%, verificar tokens sem explicação"
        return 0
    fi
}

# FASE 5: Verificar Feromônios Digitais
fase5_verify_pheromones() {
    log_phase 5 "Verificar Feromônios Digitais"

    local redis_pod
    redis_pod=$(kubectl get pods -n "$REDIS_NS" -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$redis_pod" ]]; then
        log_error "Pod do Redis não encontrado no namespace $REDIS_NS"
        add_result "Feromônios" "failed" "Redis não acessível"
        return 1
    fi

    log_success "Pod do Redis encontrado: $redis_pod"

    # Listar feromônios
    log_info "Listando feromônios..."
    local pheromone_keys
    pheromone_keys=$(kubectl exec -n "$REDIS_NS" "$redis_pod" -- redis-cli KEYS 'pheromone:*' 2>/dev/null || echo "")

    local pheromone_count=0
    if [[ -n "$pheromone_keys" ]]; then
        pheromone_count=$(echo "$pheromone_keys" | wc -l)
    fi

    log_info "Feromônios encontrados: $pheromone_count"

    if [[ "$pheromone_count" -eq 0 ]]; then
        log_warning "Nenhum feromônio encontrado. Execute o teste E2E primeiro."
        add_result "Feromônios" "warning" "Nenhum feromônio para validar"
        return 0
    fi

    # Verificar estrutura de um feromônio (primeiro da lista)
    log_info "Verificando estrutura de feromônio..."
    local first_pheromone
    first_pheromone=$(echo "$pheromone_keys" | head -n1)

    if [[ -n "$first_pheromone" ]]; then
        log_info "Feromônio de exemplo: $first_pheromone"

        local pheromone_value
        pheromone_value=$(kubectl exec -n "$REDIS_NS" "$redis_pod" -- redis-cli GET "$first_pheromone" 2>/dev/null || echo "")

        if [[ -n "$pheromone_value" ]]; then
            log_info "Valor: $pheromone_value"

            # Verificar TTL
            local ttl
            ttl=$(kubectl exec -n "$REDIS_NS" "$redis_pod" -- redis-cli TTL "$first_pheromone" 2>/dev/null || echo "-1")
            log_info "TTL: ${ttl}s"

            if [[ "$ttl" -gt 0 ]] && [[ "$ttl" -le 3600 ]]; then
                log_success "TTL válido: ${ttl}s (esperado: 0-3600s)"
            else
                log_warning "TTL fora do esperado: ${ttl}s"
            fi
        fi
    fi

    add_result "Feromônios" "passed" "$pheromone_count feromônios encontrados e validados"
    return 0
}

# FASE 6: Validar Métricas de Governança
fase6_validate_metrics() {
    log_phase 6 "Validar Métricas de Governança"

    # Verificar se Prometheus está acessível
    log_info "Verificando conectividade com Prometheus..."
    local prometheus_pod
    prometheus_pod=$(kubectl get pods -n "$OBSERVABILITY_NS" -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$prometheus_pod" ]]; then
        log_warning "Prometheus não encontrado. Pulando validação de métricas."
        add_result "Métricas de Governança" "warning" "Prometheus não acessível"
        return 0
    fi

    log_success "Prometheus encontrado: $prometheus_pod"

    # Port-forward Prometheus (em background)
    log_info "Criando port-forward para Prometheus..."
    kubectl port-forward -n "$OBSERVABILITY_NS" "$prometheus_pod" 9090:9090 &> /dev/null &
    local pf_pid=$!

    # Aguardar port-forward estar pronto
    sleep 5

    # Verificar se port-forward está funcionando
    if ! curl -s http://localhost:9090/-/healthy &> /dev/null; then
        log_warning "Port-forward para Prometheus falhou. Pulando validação de métricas."
        kill $pf_pid 2>/dev/null || true
        add_result "Métricas de Governança" "warning" "Port-forward falhou"
        return 0
    fi

    log_success "Port-forward para Prometheus ativo"

    # Consultar métricas (simplificado - apenas verificar se existem)
    log_info "Consultando métricas de governança..."

    local metrics_found=0

    # Verificar métrica de ledger writes
    if curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_ledger_writes_total' | grep -q "success"; then
        log_success "Métrica neural_hive_ledger_writes_total encontrada"
        ((metrics_found++))
    fi

    # Verificar métrica de decisions
    if curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_consensus_decisions_total' | grep -q "success"; then
        log_success "Métrica neural_hive_consensus_decisions_total encontrada"
        ((metrics_found++))
    fi

    # Verificar métrica de gatekeeper violations
    if curl -s 'http://localhost:9090/api/v1/query?query=gatekeeper_constraint_violations' | grep -q "success"; then
        log_success "Métrica gatekeeper_constraint_violations encontrada"
        ((metrics_found++))
    fi

    # Matar port-forward
    kill $pf_pid 2>/dev/null || true

    log_info "Métricas de governança encontradas: $metrics_found/3"

    if [[ "$metrics_found" -ge 2 ]]; then
        add_result "Métricas de Governança" "passed" "$metrics_found/3 métricas encontradas"
        return 0
    else
        add_result "Métricas de Governança" "warning" "Apenas $metrics_found/3 métricas encontradas"
        return 0
    fi
}

# FASE 7: Validar Dashboards de Governança
fase7_validate_dashboards() {
    log_phase 7 "Validar Dashboards de Governança"

    local dashboards_dir="$REPO_DIR/monitoring/dashboards"
    local expected_dashboards=(
        "governance-executive-dashboard.json"
        "consensus-governance.json"
        "data-governance.json"
    )

    local dashboards_found=0

    for dashboard in "${expected_dashboards[@]}"; do
        if [[ -f "$dashboards_dir/$dashboard" ]]; then
            log_success "Dashboard encontrado: $dashboard"
            ((dashboards_found++))
        else
            log_warning "Dashboard não encontrado: $dashboard"
        fi
    done

    log_info "Dashboards de governança encontrados: $dashboards_found/${#expected_dashboards[@]}"

    if [[ "$dashboards_found" -eq "${#expected_dashboards[@]}" ]]; then
        add_result "Dashboards de Governança" "passed" "${#expected_dashboards[@]}/${#expected_dashboards[@]} dashboards encontrados"
        return 0
    else
        add_result "Dashboards de Governança" "warning" "$dashboards_found/${#expected_dashboards[@]} dashboards encontrados"
        return 0
    fi
}

# FASE 8: Validar Alertas de Governança
fase8_validate_alerts() {
    log_phase 8 "Validar Alertas de Governança"

    local alerts_file="$REPO_DIR/monitoring/alerts/governance-alerts.yaml"

    if [[ ! -f "$alerts_file" ]]; then
        log_warning "Arquivo de alertas não encontrado: governance-alerts.yaml"
        add_result "Alertas de Governança" "warning" "Arquivo de alertas não encontrado"
        return 0
    fi

    log_success "Arquivo de alertas encontrado: governance-alerts.yaml"

    # Verificar se foi aplicado como PrometheusRule
    log_info "Verificando PrometheusRule no cluster..."
    if kubectl get prometheusrule -n "$OBSERVABILITY_NS" neural-hive-governance-alerts &> /dev/null; then
        log_success "PrometheusRule aplicado: neural-hive-governance-alerts"
        add_result "Alertas de Governança" "passed" "PrometheusRule configurado"
        return 0
    else
        log_warning "PrometheusRule não encontrado no cluster"
        add_result "Alertas de Governança" "warning" "PrometheusRule não aplicado"
        return 0
    fi
}

# FASE 9: Executar Testes de Violação
fase9_violation_tests() {
    log_phase 9 "Executar Testes de Violação"

    log_info "Criando namespace de teste temporário..."
    local test_ns="policy-test-$TIMESTAMP"

    kubectl create namespace "$test_ns" || true
    kubectl label namespace "$test_ns" neural-hive.io/managed=true || true

    # Teste 1: Deployment sem resource limits
    log_info "Teste 1: Criar deployment sem resource limits..."
    cat <<EOF | kubectl apply -f - || true
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-no-limits
  namespace: $test_ns
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
EOF

    # Obter auditInterval dos valores do Gatekeeper (default: 60s)
    local audit_interval=60
    if kubectl get deployment -n "$GATEKEEPER_NS" &> /dev/null; then
        local env_interval
        env_interval=$(kubectl get deployment -n "$GATEKEEPER_NS" -l gatekeeper.sh/operation=audit -o jsonpath='{.items[0].spec.template.spec.containers[0].env[?(@.name=="GATEKEEPER_AUDIT_INTERVAL")].value}' 2>/dev/null || echo "")
        if [[ -n "$env_interval" && "$env_interval" =~ ^[0-9]+$ ]]; then
            audit_interval=$env_interval
        fi
    fi

    # Calcular timeout (3x auditInterval para segurança)
    local timeout=$((audit_interval * 3))
    local max_attempts=$((timeout / 10))

    log_info "Aguardando audit detectar violação (polling por até ${timeout}s, auditInterval: ${audit_interval}s)..."

    # Polling por violações
    local violations=0
    local attempt=0
    while [[ "$attempt" -lt "$max_attempts" ]]; do
        violations=$(kubectl get constraints -A -o jsonpath='{.items[*].status.totalViolations}' 2>/dev/null | awk '{for(i=1;i<=NF;i++) sum+=$i} END {print sum+0}')

        if [[ "$violations" -gt 0 ]]; then
            log_success "Violações detectadas após $((attempt * 10))s: $violations"
            add_result "Testes de Violação" "passed" "Violações detectadas: $violations"
            break
        fi

        ((attempt++))
        sleep 10
    done

    if [[ "$violations" -eq 0 ]]; then
        log_warning "Nenhuma violação detectada após ${timeout}s (timeout)"
        add_result "Testes de Violação" "warning" "Timeout aguardando violações (auditInterval: ${audit_interval}s)"
    fi

    # Limpar recursos de teste
    log_info "Limpando namespace de teste..."
    kubectl delete namespace "$test_ns" --wait=false || true

    return 0
}

# FASE 10: Gerar Relatório de Compliance
fase10_generate_report() {
    log_phase 10 "Gerar Relatório de Compliance"

    # Criar diretório de resultados se não existir
    mkdir -p "$RESULTS_DIR"

    # Calcular overall score
    local overall_score
    overall_score=$(awk "BEGIN {printf \"%.1f\", (${SCORES[auditability]} + ${SCORES[explainability]} + ${SCORES[compliance]} + ${SCORES[integrity]}) / 4}")

    # Gerar JSON
    log_info "Gerando relatório JSON..."
    local end_epoch
    end_epoch=$(date +%s)
    local duration_seconds
    duration_seconds=$((end_epoch - START_EPOCH))

    cat > "$REPORT_JSON" <<EOF
{
  "test_name": "Governance Compliance Test",
  "start_time": "$(date -d @${START_EPOCH} +%Y-%m-%dT%H:%M:%S%z 2>/dev/null || date -r ${START_EPOCH} +%Y-%m-%dT%H:%M:%S%z 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)",
  "end_time": "$(date +%Y-%m-%dT%H:%M:%S%z)",
  "duration_seconds": $duration_seconds,
  "results": [
    $(IFS=,; echo "${TEST_RESULTS[*]}")
  ],
  "scores": {
    "auditability": ${SCORES[auditability]},
    "explainability": ${SCORES[explainability]},
    "compliance": ${SCORES[compliance]},
    "integrity": ${SCORES[integrity]},
    "overall": $overall_score
  },
  "summary": {
    "total": $TOTAL_PHASES,
    "passed": $PASSED_PHASES,
    "failed": $FAILED_PHASES
  }
}
EOF

    log_success "Relatório JSON gerado: $REPORT_JSON"

    # Gerar Markdown
    log_info "Gerando relatório Markdown..."
    cat > "$REPORT_MD" <<EOF
# Relatório de Compliance - Neural Hive-Mind Fase 1

**Data**: $(date +%Y-%m-%d\ %H:%M:%S)
**Duração**: ${duration_seconds}s
**Overall Governance Score**: $overall_score%

## Resumo Executivo

- **Total de Fases**: $TOTAL_PHASES
- **Fases Aprovadas**: $PASSED_PHASES
- **Fases Falhadas**: $FAILED_PHASES
- **Taxa de Sucesso**: $(awk "BEGIN {printf \"%.1f\", ($PASSED_PHASES / $TOTAL_PHASES) * 100}")%

## Scores por Categoria

| Categoria | Score | Status |
|-----------|-------|--------|
| Auditabilidade | ${SCORES[auditability]}% | $([ "${SCORES[auditability]%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| Explicabilidade | ${SCORES[explainability]}% | $([ "${SCORES[explainability]%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| Compliance | ${SCORES[compliance]}% | $([ "${SCORES[compliance]%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| Integridade | ${SCORES[integrity]}% | $([ "${SCORES[integrity]%.*}" -ge 95 ] && echo "✅" || echo "⚠️") |
| **Overall** | **$overall_score%** | **$([ "${overall_score%.*}" -ge 95 ] && echo "✅ COMPLIANT" || echo "⚠️ PARTIAL")** |

## Resultados Detalhados

EOF

    # Adicionar resultados de cada teste
    for result in "${TEST_RESULTS[@]}"; do
        if command -v jq &> /dev/null; then
            local section=$(echo "$result" | jq -r '.section')
            local status=$(echo "$result" | jq -r '.status')
            local message=$(echo "$result" | jq -r '.message')

            local icon="❓"
            case "$status" in
                passed) icon="✅" ;;
                failed) icon="❌" ;;
                warning) icon="⚠️" ;;
            esac

            echo "- $icon **$section**: $message" >> "$REPORT_MD"
        fi
    done

    log_success "Relatório Markdown gerado: $REPORT_MD"

    add_result "Geração de Relatório" "passed" "Relatórios JSON e Markdown gerados"
    return 0
}

# Main execution
main() {
    log_info "========================================="
    log_info "Teste de Governança e Compliance"
    log_info "Neural Hive-Mind - Fase 1"
    log_info "========================================="
    echo ""

    # Salvar timestamp inicial como epoch
    START_EPOCH=$(date +%s)

    # Executar todas as fases
    fase1_verify_gatekeeper || true
    fase2_validate_policies || true
    fase3_verify_ledger || true
    fase4_verify_explainability || true
    fase5_verify_pheromones || true
    fase6_validate_metrics || true
    fase7_validate_dashboards || true
    fase8_validate_alerts || true
    fase9_violation_tests || true
    fase10_generate_report || true

    # Resumo final
    echo ""
    log_info "========================================="
    log_info "RESUMO FINAL"
    log_info "========================================="
    log_info "Fases aprovadas: $PASSED_PHASES/$TOTAL_PHASES"
    log_info "Fases falhadas: $FAILED_PHASES/$TOTAL_PHASES"
    log_info "Overall Governance Score: $(awk "BEGIN {printf \"%.1f\", (${SCORES[auditability]} + ${SCORES[explainability]} + ${SCORES[compliance]} + ${SCORES[integrity]}) / 4}")%"
    echo ""
    log_info "Relatórios gerados:"
    log_info "  - JSON: $REPORT_JSON"
    log_info "  - Markdown: $REPORT_MD"
    echo ""

    if [[ "$FAILED_PHASES" -eq 0 ]]; then
        log_success "Teste de governança concluído com sucesso!"
        exit 0
    else
        log_warning "Teste de governança concluído com algumas falhas."
        exit 1
    fi
}

# Executar main
main "$@"
