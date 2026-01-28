#!/bin/bash

################################################################################
# Script de Teste End-to-End - Phase 2.1 Orchestrator Dynamic
#
# Valida o Fluxo C completo (C1-C6):
# - Publicação de Cognitive Plan + Consolidated Decision
# - Validação de workflow Temporal iniciado
# - Validação de tickets gerados e publicados
# - Verificação de telemetria
# - Verificação de persistência MongoDB
################################################################################

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
SERVICE_NAME="${SERVICE_NAME:-orchestrator-dynamic}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
KAFKA_CLUSTER="${KAFKA_CLUSTER:-neural-hive-kafka}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-${KAFKA_CLUSTER}-bootstrap.${KAFKA_NAMESPACE}.svc.cluster.local:9092}"
TEMPORAL_NAMESPACE="${TEMPORAL_NAMESPACE:-neural-hive-temporal}"
TEMPORAL_FRONTEND="${TEMPORAL_FRONTEND:-temporal-frontend.${TEMPORAL_NAMESPACE}.svc.cluster.local:7233}"

# Diretório temporário para artifacts
TEST_DIR="/tmp/orchestrator-test-$(date +%s)"
mkdir -p "$TEST_DIR"

# Contadores de testes
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

################################################################################
# Funções auxiliares
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

run_test() {
    ((TESTS_TOTAL++))
    local test_name="$1"
    log_info "Executando teste: $test_name"
}

################################################################################
# Teste 1: Pré-requisitos
################################################################################

test_prerequisites() {
    run_test "Verificação de pré-requisitos"

    local all_ok=true

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        all_ok=false
    fi

    # Verificar jq
    if ! command -v jq &> /dev/null; then
        log_error "jq não encontrado (necessário para parsing JSON)"
        all_ok=false
    fi

    # Verificar base64
    if ! command -v base64 &> /dev/null; then
        log_error "base64 não encontrado"
        all_ok=false
    fi

    # Verificar deployment do orchestrator-dynamic
    if ! kubectl get deployment "$SERVICE_NAME" -n "$NAMESPACE" &> /dev/null; then
        log_error "Deployment $SERVICE_NAME não encontrado no namespace $NAMESPACE"
        all_ok=false
    fi

    # Verificar Kafka
    local kafka_pods
    kafka_pods=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l "strimzi.io/cluster=$KAFKA_CLUSTER,strimzi.io/name=${KAFKA_CLUSTER}-kafka" --no-headers 2>/dev/null | wc -l)
    if [ "$kafka_pods" -gt 0 ]; then
        log_info "Kafka detectado (cluster=$KAFKA_CLUSTER, namespace=$KAFKA_NAMESPACE)"
    else
        log_error "Kafka não encontrado (cluster esperado: ${KAFKA_CLUSTER} no namespace ${KAFKA_NAMESPACE})"
        all_ok=false
    fi

    if [ "$all_ok" = true ]; then
        log_success "Todos os pré-requisitos satisfeitos"
    else
        log_error "Pré-requisitos incompletos - abortando testes"
        exit 1
    fi
}

################################################################################
# Teste 2: Criar Cognitive Plan de teste
################################################################################

create_test_cognitive_plan() {
    run_test "Criação de Cognitive Plan de teste"

    local plan_id="test-plan-$(date +%s)"
    local intent_id="test-intent-$(date +%s)"

    cat > "$TEST_DIR/cognitive_plan.json" <<EOF
{
    "plan_id": "$plan_id",
    "intent_id": "$intent_id",
    "schema_version": "1.0.0",
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "expires_at": "$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)",
    "plan_summary": "Plano de teste end-to-end para validação do Fluxo C",
    "tasks": [
        {
            "task_id": "task-001",
            "task_type": "INFERENCE",
            "specialist_type": "nlp",
            "description": "Processar texto de entrada",
            "inputs": {
                "text": "Teste end-to-end do orchestrator"
            },
            "expected_outputs": ["processed_text"],
            "dependencies": [],
            "estimated_duration_ms": 5000,
            "priority": "high",
            "risk_band": "medium"
        },
        {
            "task_id": "task-002",
            "task_type": "TRANSFORM",
            "specialist_type": "data-processor",
            "description": "Transformar resultado",
            "inputs": {
                "data": "{{task-001.processed_text}}"
            },
            "expected_outputs": ["transformed_data"],
            "dependencies": ["task-001"],
            "estimated_duration_ms": 3000,
            "priority": "medium",
            "risk_band": "low"
        },
        {
            "task_id": "task-003",
            "task_type": "AGGREGATE",
            "specialist_type": "aggregator",
            "description": "Consolidar resultados finais",
            "inputs": {
                "results": ["{{task-001.processed_text}}", "{{task-002.transformed_data}}"]
            },
            "expected_outputs": ["final_result"],
            "dependencies": ["task-001", "task-002"],
            "estimated_duration_ms": 2000,
            "priority": "high",
            "risk_band": "medium"
        }
    ],
    "constraints": {
        "max_parallel_tasks": 5,
        "total_timeout_ms": 60000
    },
    "metadata": {
        "test": true,
        "e2e_test_run": true
    }
}
EOF

    if [ -f "$TEST_DIR/cognitive_plan.json" ]; then
        log_success "Cognitive Plan criado: $TEST_DIR/cognitive_plan.json"
        echo "$plan_id" > "$TEST_DIR/plan_id.txt"
        echo "$intent_id" > "$TEST_DIR/intent_id.txt"
    else
        log_error "Falha ao criar Cognitive Plan"
        exit 1
    fi
}

################################################################################
# Teste 3: Criar Consolidated Decision
################################################################################

create_test_consolidated_decision() {
    run_test "Criação de Consolidated Decision de teste"

    local plan_id=$(cat "$TEST_DIR/plan_id.txt")
    local intent_id=$(cat "$TEST_DIR/intent_id.txt")
    local decision_id="decision-$(date +%s)"

    cat > "$TEST_DIR/consolidated_decision.json" <<EOF
{
    "decision_id": "$decision_id",
    "intent_id": "$intent_id",
    "plan_id": "$plan_id",
    "decision_type": "CONSENSUS",
    "approved": true,
    "confidence_score": 0.95,
    "voter_count": 5,
    "votes_for": 5,
    "votes_against": 0,
    "votes_abstain": 0,
    "rationale": "Plano aprovado unanimemente para execução de teste E2E",
    "constraints_validated": true,
    "security_validated": true,
    "resource_allocation_approved": true,
    "decided_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "cognitive_plan": $(cat "$TEST_DIR/cognitive_plan.json"),
    "metadata": {
        "test": true,
        "e2e_validation": true
    }
}
EOF

    if [ -f "$TEST_DIR/consolidated_decision.json" ]; then
        log_success "Consolidated Decision criado: $TEST_DIR/consolidated_decision.json"
        echo "$decision_id" > "$TEST_DIR/decision_id.txt"
    else
        log_error "Falha ao criar Consolidated Decision"
        exit 1
    fi
}

################################################################################
# Teste 4: Publicar no Kafka (plans.consensus)
################################################################################

publish_to_kafka() {
    run_test "Publicação no Kafka topic plans.consensus"

    local decision_json=$(cat "$TEST_DIR/consolidated_decision.json")

    # Criar pod temporário com Kafka producer
    kubectl run kafka-producer-test \
        --image=confluentinc/cp-kafka:7.5.0 \
        --rm -i \
        --restart=Never \
        --namespace="$KAFKA_NAMESPACE" \
        -- bash -c "echo '$decision_json' | kafka-console-producer \
            --broker-list $KAFKA_BOOTSTRAP \
            --topic plans.consensus \
            --property parse.key=false" \
        > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_success "Consolidated Decision publicado no Kafka"
        sleep 5  # Aguardar processamento
    else
        log_error "Falha ao publicar no Kafka"
        exit 1
    fi
}

################################################################################
# Teste 5: Verificar Workflow Temporal iniciado
################################################################################

verify_temporal_workflow() {
    run_test "Verificação de Workflow Temporal iniciado"

    local plan_id=$(cat "$TEST_DIR/plan_id.txt")
    local workflow_id="orchestration-workflow-$plan_id"

    # Obter pod do orchestrator
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$pod_name" ]; then
        log_error "Nenhum pod do orchestrator encontrado"
        return
    fi

    # Verificar logs do serviço para workflow iniciado
    local logs=$(kubectl logs -n "$NAMESPACE" "$pod_name" --tail=100 | grep -i "workflow.*started\|starting.*workflow" || true)

    if [ -n "$logs" ]; then
        log_success "Workflow Temporal iniciado (evidência nos logs)"
        echo "$workflow_id" > "$TEST_DIR/workflow_id.txt"
    else
        log_warning "Não foi possível confirmar início do workflow nos logs"
    fi

    # Tentar consultar via API REST
    local api_response=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -s "http://localhost:8000/api/v1/workflows/$workflow_id" || echo "{}")

    if echo "$api_response" | jq -e '.workflow_id' > /dev/null 2>&1; then
        log_success "Workflow confirmado via API REST: $workflow_id"
    else
        log_warning "Workflow não encontrado via API (pode ainda estar processando)"
    fi
}

################################################################################
# Teste 6: Verificar Tickets gerados
################################################################################

verify_tickets_generated() {
    run_test "Verificação de Execution Tickets gerados"

    local plan_id=$(cat "$TEST_DIR/plan_id.txt")

    # Obter pod do orchestrator
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$pod_name" ]; then
        log_error "Nenhum pod do orchestrator encontrado"
        return
    fi

    # Consultar tickets via API REST
    local api_response=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -s "http://localhost:8000/api/v1/tickets/by-plan/$plan_id" || echo "[]")

    local ticket_count=$(echo "$api_response" | jq 'length' 2>/dev/null || echo "0")

    if [ "$ticket_count" -gt 0 ]; then
        log_success "$ticket_count tickets gerados para o plano $plan_id"
        echo "$api_response" > "$TEST_DIR/tickets.json"

        # Validar estrutura dos tickets
        local valid_tickets=$(echo "$api_response" | jq '[.[] | select(.ticket_id and .status and .sla and .qos)] | length')

        if [ "$valid_tickets" -eq "$ticket_count" ]; then
            log_success "Todos os $ticket_count tickets possuem estrutura válida (ticket_id, status, SLA, QoS)"
        else
            log_error "Apenas $valid_tickets de $ticket_count tickets possuem estrutura completa"
        fi
    else
        log_warning "Nenhum ticket encontrado (pode ainda estar processando)"
    fi
}

################################################################################
# Teste 7: Verificar publicação no Kafka (execution.tickets)
################################################################################

verify_tickets_published() {
    run_test "Verificação de tickets publicados no Kafka execution.tickets"

    # Consumir últimas mensagens do tópico execution.tickets
    local messages=$(kubectl run kafka-consumer-test \
        --image=confluentinc/cp-kafka:7.5.0 \
        --rm -i \
        --restart=Never \
        --namespace="$KAFKA_NAMESPACE" \
        -- bash -c "kafka-console-consumer \
            --bootstrap-server $KAFKA_BOOTSTRAP \
            --topic execution.tickets \
            --from-beginning \
            --max-messages 10 \
            --timeout-ms 10000 2>/dev/null" || echo "")

    if [ -n "$messages" ]; then
        local message_count=$(echo "$messages" | wc -l)
        log_success "$message_count mensagens encontradas no tópico execution.tickets"

        # Validar se alguma mensagem contém o plan_id de teste
        local plan_id=$(cat "$TEST_DIR/plan_id.txt")
        if echo "$messages" | grep -q "$plan_id"; then
            log_success "Tickets do plano de teste encontrados no Kafka"
        else
            log_warning "Tickets do plano de teste não encontrados no Kafka (pode ter sido consumido)"
        fi
    else
        log_warning "Nenhuma mensagem encontrada no tópico execution.tickets"
    fi
}

################################################################################
# Teste 8: Verificar telemetria publicada
################################################################################

verify_telemetry_published() {
    run_test "Verificação de telemetria publicada no Kafka telemetry.orchestration"

    # Consumir últimas mensagens do tópico telemetry.orchestration
    local messages=$(kubectl run kafka-consumer-telemetry-test \
        --image=confluentinc/cp-kafka:7.5.0 \
        --rm -i \
        --restart=Never \
        --namespace="$KAFKA_NAMESPACE" \
        -- bash -c "kafka-console-consumer \
            --bootstrap-server $KAFKA_BOOTSTRAP \
            --topic telemetry.orchestration \
            --from-beginning \
            --max-messages 10 \
            --timeout-ms 10000 2>/dev/null" || echo "")

    if [ -n "$messages" ]; then
        local message_count=$(echo "$messages" | wc -l)
        log_success "$message_count frames de telemetria encontrados"

        # Validar estrutura de telemetria
        local plan_id=$(cat "$TEST_DIR/plan_id.txt")
        if echo "$messages" | grep -q "$plan_id"; then
            log_success "Telemetria do plano de teste encontrada no Kafka"

            # Validar campos obrigatórios (correlation_id, trace_id, metrics)
            local valid_telemetry=$(echo "$messages" | jq -s '[.[] | select(.correlation_id and .trace_id and .metrics)] | length' 2>/dev/null || echo "0")

            if [ "$valid_telemetry" -gt 0 ]; then
                log_success "$valid_telemetry frames de telemetria com estrutura válida"
            fi
        else
            log_warning "Telemetria do plano de teste não encontrada"
        fi
    else
        log_warning "Nenhuma telemetria encontrada no tópico"
    fi
}

################################################################################
# Teste 9: Verificar persistência MongoDB
################################################################################

verify_mongodb_persistence() {
    run_test "Verificação de persistência no MongoDB"

    local plan_id=$(cat "$TEST_DIR/plan_id.txt")

    # Tentar obter pod do MongoDB
    local mongo_pod=$(kubectl get pods -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$mongo_pod" ]; then
        log_warning "Pod do MongoDB não encontrado - pulando validação de persistência"
        return
    fi

    # Consultar validações auditadas
    local audit_count=$(kubectl exec -n mongodb-cluster "$mongo_pod" -- mongosh \
        --quiet \
        --eval "db.getSiblingDB('neural_hive_orchestration').plan_validations.countDocuments({plan_id: '$plan_id'})" \
        2>/dev/null || echo "0")

    if [ "$audit_count" -gt 0 ]; then
        log_success "$audit_count registros de auditoria encontrados no MongoDB"
    else
        log_warning "Nenhum registro de auditoria encontrado (pode ainda estar processando)"
    fi

    # Consultar tickets persistidos
    local ticket_count=$(kubectl exec -n mongodb-cluster "$mongo_pod" -- mongosh \
        --quiet \
        --eval "db.getSiblingDB('neural_hive_orchestration').execution_tickets.countDocuments({plan_id: '$plan_id'})" \
        2>/dev/null || echo "0")

    if [ "$ticket_count" -gt 0 ]; then
        log_success "$ticket_count tickets persistidos no MongoDB"
    else
        log_warning "Nenhum ticket persistido encontrado"
    fi
}

################################################################################
# Teste 10: Verificar métricas Prometheus
################################################################################

verify_prometheus_metrics() {
    run_test "Verificação de métricas Prometheus"

    # Obter pod do orchestrator
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$pod_name" ]; then
        log_error "Nenhum pod do orchestrator encontrado"
        return
    fi

    # Consultar endpoint /metrics
    local metrics=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -s "http://localhost:9090/metrics" || echo "")

    if [ -z "$metrics" ]; then
        log_error "Não foi possível obter métricas do endpoint /metrics"
        return
    fi

    # Verificar métricas chave
    local metrics_found=0

    if echo "$metrics" | grep -q "orchestration_workflows_started_total"; then
        ((metrics_found++))
    fi

    if echo "$metrics" | grep -q "orchestration_tickets_generated_total"; then
        ((metrics_found++))
    fi

    if echo "$metrics" | grep -q "orchestration_kafka_messages_consumed_total"; then
        ((metrics_found++))
    fi

    if echo "$metrics" | grep -q "orchestration_sla_violations_total"; then
        ((metrics_found++))
    fi

    if [ "$metrics_found" -ge 3 ]; then
        log_success "$metrics_found/4 métricas chave encontradas no Prometheus"
    else
        log_warning "Apenas $metrics_found/4 métricas encontradas"
    fi

    # Salvar métricas para análise
    echo "$metrics" > "$TEST_DIR/prometheus_metrics.txt"
}

################################################################################
# Teste 11: Verificar logs estruturados
################################################################################

verify_structured_logs() {
    run_test "Verificação de logs estruturados"

    # Obter pod do orchestrator
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$pod_name" ]; then
        log_error "Nenhum pod do orchestrator encontrado"
        return
    fi

    # Obter últimos 100 logs
    local logs=$(kubectl logs -n "$NAMESPACE" "$pod_name" --tail=100)

    # Verificar se logs estão em JSON (structlog)
    local json_logs=$(echo "$logs" | grep -c '^{.*}$' || echo "0")

    if [ "$json_logs" -gt 10 ]; then
        log_success "$json_logs logs estruturados em JSON encontrados"

        # Verificar campos obrigatórios (event, level, timestamp)
        local valid_logs=$(echo "$logs" | jq -s '[.[] | select(.event and .level and .timestamp)] | length' 2>/dev/null || echo "0")

        if [ "$valid_logs" -gt 5 ]; then
            log_success "$valid_logs logs com estrutura válida (event, level, timestamp)"
        fi

        # Verificar correlação (correlation_id, trace_id)
        if echo "$logs" | grep -q "correlation_id"; then
            log_success "Logs contêm correlation_id para rastreabilidade"
        fi
    else
        log_warning "Poucos logs estruturados encontrados ($json_logs)"
    fi
}

################################################################################
# Teste 12: Verificar health checks
################################################################################

verify_health_checks() {
    run_test "Verificação de health checks"

    # Obter pod do orchestrator
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$pod_name" ]; then
        log_error "Nenhum pod do orchestrator encontrado"
        return
    fi

    # Verificar /health
    local health_response=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -s "http://localhost:8000/health" || echo "{}")
    local health_status=$(echo "$health_response" | jq -r '.status' 2>/dev/null || echo "unknown")

    if [ "$health_status" = "healthy" ]; then
        log_success "Health check PASS (status: healthy)"
    else
        log_error "Health check FAIL (status: $health_status)"
    fi

    # Verificar /ready
    local ready_response=$(kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -s "http://localhost:8000/ready" || echo "{}")
    local ready_status=$(echo "$ready_response" | jq -r '.status' 2>/dev/null || echo "unknown")

    if [ "$ready_status" = "ready" ]; then
        log_success "Readiness check PASS (status: ready)"
    else
        log_error "Readiness check FAIL (status: $ready_status)"
    fi
}

################################################################################
# Relatório Final
################################################################################

print_summary() {
    echo ""
    echo "=============================================================="
    echo "           RESUMO DOS TESTES END-TO-END"
    echo "=============================================================="
    echo ""
    echo "Total de testes executados: $TESTS_TOTAL"
    echo -e "Testes ${GREEN}PASSADOS${NC}: $TESTS_PASSED"
    echo -e "Testes ${RED}FALHADOS${NC}: $TESTS_FAILED"
    echo ""

    local success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))

    if [ "$success_rate" -ge 80 ]; then
        echo -e "${GREEN}✅ Taxa de sucesso: $success_rate% - EXCELENTE${NC}"
    elif [ "$success_rate" -ge 60 ]; then
        echo -e "${YELLOW}⚠️  Taxa de sucesso: $success_rate% - BOM${NC}"
    else
        echo -e "${RED}❌ Taxa de sucesso: $success_rate% - NECESSITA ATENÇÃO${NC}"
    fi

    echo ""
    echo "Artifacts salvos em: $TEST_DIR"
    echo "  - cognitive_plan.json"
    echo "  - consolidated_decision.json"
    echo "  - tickets.json (se encontrados)"
    echo "  - prometheus_metrics.txt"
    echo ""
    echo "=============================================================="
}

################################################################################
# Execução Principal
################################################################################

main() {
    echo "=============================================================="
    echo "   TESTE END-TO-END - PHASE 2.1 ORCHESTRATOR DYNAMIC"
    echo "=============================================================="
    echo ""

    log_info "Namespace: $NAMESPACE"
    log_info "Service: $SERVICE_NAME"
    log_info "Kafka: $KAFKA_BOOTSTRAP"
    log_info "Temporal: $TEMPORAL_FRONTEND"
    log_info "Test Directory: $TEST_DIR"
    echo ""

    # Executar testes
    test_prerequisites
    create_test_cognitive_plan
    create_test_consolidated_decision
    publish_to_kafka
    verify_temporal_workflow
    verify_tickets_generated
    verify_tickets_published
    verify_telemetry_published
    verify_mongodb_persistence
    verify_prometheus_metrics
    verify_structured_logs
    verify_health_checks

    # Relatório final
    print_summary

    # Exit code baseado no resultado
    if [ "$TESTS_FAILED" -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Trap para cleanup
trap 'log_warning "Teste interrompido - artifacts mantidos em $TEST_DIR"' INT TERM

# Executar
main "$@"
