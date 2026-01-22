#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target kafka"
echo "⚠️  Exemplo: scripts/validate.sh --target kafka"
echo ""
echo "Executando script legado..."
echo ""
# Validação de tópicos Kafka do Neural Hive-Mind
# Verifica existência, nomenclatura, configuração e consumer groups
# Version: 1.0

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

# ============================================================================
# CONFIGURAÇÃO KAFKA
# ============================================================================

# Kafka cluster configuration
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
KAFKA_BROKER="${KAFKA_BROKER:-kafka-0.kafka.${KAFKA_NAMESPACE}.svc.cluster.local:9092}"
KAFKA_POD="${KAFKA_POD:-kafka-0}"
SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL:-http://schema-registry.kafka.svc.cluster.local:8081}"

# Tópicos esperados (baseado em helm-charts/kafka-topics/values.yaml)
EXPECTED_INTENTION_TOPICS=(
    "intentions.business"
    "intentions.technical"
    "intentions.infrastructure"
    "intentions.security"
)

EXPECTED_SYSTEM_TOPICS=(
    "intentions.dead-letter"
    "intentions.audit"
    "memory.sync.events"
    "memory.quality.alerts"
    "memory.lineage.events"
    "autocura.events"
    "cognitive-plans-approval-requests"
    "cognitive-plans-approval-responses"
)

# Configurações esperadas por tópico
declare -A EXPECTED_PARTITIONS=(
    ["intentions.business"]="6"
    ["intentions.technical"]="8"
    ["intentions.infrastructure"]="6"
    ["intentions.security"]="4"
)

declare -A EXPECTED_REPLICATION=(
    ["intentions.business"]="3"
    ["intentions.technical"]="3"
    ["intentions.infrastructure"]="3"
    ["intentions.security"]="3"
)

# Consumer groups críticos
CRITICAL_CONSUMER_GROUPS=(
    "semantic-translation-engine"
    "consensus-engine"
    "approval-service"
    "orchestrator-dynamic"
)

# Thresholds
MAX_ACCEPTABLE_LAG=1000
WARNING_LAG=100

# ============================================================================
# FUNÇÕES DE VALIDAÇÃO KAFKA
# ============================================================================

# Verificar conectividade com brokers Kafka
check_kafka_broker_connectivity() {
    log_info "Verificando conectividade com brokers Kafka..."

    local test_start_time=$(date +%s)
    local brokers_available=0
    local total_brokers=0

    # Verificar se o pod Kafka existe e está running
    local kafka_pod_status=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app.kubernetes.io/name=kafka -o jsonpath='{.items[*].status.phase}' 2>/dev/null || echo "")

    if [[ -z "$kafka_pod_status" ]]; then
        add_test_result "kafka-broker-connectivity" "FAIL" "critical" \
            "Nenhum pod Kafka encontrado no namespace $KAFKA_NAMESPACE" \
            "Verificar deployment do Kafka: kubectl get pods -n $KAFKA_NAMESPACE"
        return 1
    fi

    # Contar brokers
    for status in $kafka_pod_status; do
        total_brokers=$((total_brokers + 1))
        if [[ "$status" == "Running" ]]; then
            brokers_available=$((brokers_available + 1))
        fi
    done

    # Testar conectividade TCP com o broker principal
    local connectivity_test=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        timeout 5 bash -c "cat < /dev/null > /dev/tcp/localhost/9092" 2>/dev/null && echo "OK" || echo "FAIL")

    local check_time=$(($(date +%s) - test_start_time))

    if [[ "$connectivity_test" == "OK" && $brokers_available -eq $total_brokers ]]; then
        add_test_result "kafka-broker-connectivity" "PASS" "critical" \
            "Todos os $total_brokers brokers Kafka estão acessíveis" "" "$check_time"
        log_success "✅ Kafka brokers: $brokers_available/$total_brokers disponíveis"
        return 0
    elif [[ $brokers_available -gt 0 ]]; then
        add_test_result "kafka-broker-connectivity" "WARNING" "critical" \
            "$brokers_available de $total_brokers brokers disponíveis" \
            "Verificar status dos brokers: kubectl get pods -n $KAFKA_NAMESPACE -l app.kubernetes.io/name=kafka" "$check_time"
        log_warning "⚠️  Kafka brokers: $brokers_available/$total_brokers disponíveis"
        return 0
    else
        add_test_result "kafka-broker-connectivity" "FAIL" "critical" \
            "Nenhum broker Kafka acessível" \
            "Reiniciar Kafka: kubectl rollout restart statefulset/kafka -n $KAFKA_NAMESPACE" "$check_time"
        log_error "❌ Kafka brokers: nenhum disponível"
        return 1
    fi
}

# Validar existência de tópicos
validate_topic_existence() {
    log_info "Validando existência de tópicos Kafka..."

    local test_start_time=$(date +%s)

    # Obter lista de tópicos existentes
    local existing_topics=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null || echo "")

    if [[ -z "$existing_topics" ]]; then
        add_test_result "kafka-topic-existence" "FAIL" "critical" \
            "Não foi possível listar tópicos Kafka" \
            "Verificar conectividade e permissões do Kafka"
        return 1
    fi

    local missing_topics=()
    local found_topics=()

    # Verificar tópicos de intenções (críticos)
    for topic in "${EXPECTED_INTENTION_TOPICS[@]}"; do
        if echo "$existing_topics" | grep -q "^${topic}$"; then
            found_topics+=("$topic")
            log_success "✅ Tópico $topic existe"
        else
            missing_topics+=("$topic")
            log_error "❌ Tópico $topic AUSENTE"
        fi
    done

    # Verificar tópicos de sistema
    for topic in "${EXPECTED_SYSTEM_TOPICS[@]}"; do
        if echo "$existing_topics" | grep -q "^${topic}$"; then
            found_topics+=("$topic")
            log_debug "✅ Tópico de sistema $topic existe"
        else
            log_warning "⚠️  Tópico de sistema $topic ausente"
        fi
    done

    local check_time=$(($(date +%s) - test_start_time))
    local total_expected=$((${#EXPECTED_INTENTION_TOPICS[@]} + ${#EXPECTED_SYSTEM_TOPICS[@]}))

    if [[ ${#missing_topics[@]} -eq 0 ]]; then
        add_test_result "kafka-topic-existence" "PASS" "critical" \
            "Todos os ${#found_topics[@]} tópicos esperados existem" "" "$check_time"
        return 0
    elif [[ ${#missing_topics[@]} -le 3 ]]; then
        add_test_result "kafka-topic-existence" "WARNING" "critical" \
            "${#missing_topics[@]} tópicos ausentes: ${missing_topics[*]}" \
            "Aplicar Helm chart: helm upgrade kafka-topics ./helm-charts/kafka-topics -n $KAFKA_NAMESPACE" "$check_time"
        return 1
    else
        add_test_result "kafka-topic-existence" "FAIL" "critical" \
            "${#missing_topics[@]} tópicos críticos ausentes: ${missing_topics[*]}" \
            "Aplicar Helm chart: helm upgrade --install kafka-topics ./helm-charts/kafka-topics -n $KAFKA_NAMESPACE" "$check_time"
        return 1
    fi
}

# Validar configuração dos tópicos (partitions, replication factor)
validate_topic_configuration() {
    log_info "Validando configuração dos tópicos..."

    local test_start_time=$(date +%s)
    local config_issues=0

    for topic in "${EXPECTED_INTENTION_TOPICS[@]}"; do
        # Obter descrição do tópico
        local topic_desc=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
            kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic "$topic" 2>/dev/null || echo "")

        if [[ -z "$topic_desc" ]]; then
            log_warning "⚠️  Não foi possível obter descrição do tópico $topic"
            continue
        fi

        # Extrair partições
        local partitions=$(echo "$topic_desc" | grep "PartitionCount" | sed 's/.*PartitionCount:\s*\([0-9]*\).*/\1/' || echo "0")
        local replication=$(echo "$topic_desc" | grep "ReplicationFactor" | sed 's/.*ReplicationFactor:\s*\([0-9]*\).*/\1/' || echo "0")

        local expected_partitions="${EXPECTED_PARTITIONS[$topic]:-6}"
        local expected_replication="${EXPECTED_REPLICATION[$topic]:-3}"

        if [[ "$partitions" -lt "$expected_partitions" ]]; then
            log_warning "⚠️  Tópico $topic: partições=$partitions (esperado>=$expected_partitions)"
            config_issues=$((config_issues + 1))
        else
            log_debug "✅ Tópico $topic: partições=$partitions OK"
        fi

        if [[ "$replication" -lt "$expected_replication" ]]; then
            log_warning "⚠️  Tópico $topic: RF=$replication (esperado>=$expected_replication)"
            config_issues=$((config_issues + 1))
        else
            log_debug "✅ Tópico $topic: RF=$replication OK"
        fi
    done

    local check_time=$(($(date +%s) - test_start_time))

    if [[ $config_issues -eq 0 ]]; then
        add_test_result "kafka-topic-configuration" "PASS" "high" \
            "Configuração de todos os tópicos está correta" "" "$check_time"
        return 0
    else
        add_test_result "kafka-topic-configuration" "WARNING" "high" \
            "$config_issues problemas de configuração encontrados" \
            "Revisar configurações em helm-charts/kafka-topics/values.yaml" "$check_time"
        return 1
    fi
}

# Verificar nomenclatura de tópicos (ponto vs hífen)
check_topic_naming_convention() {
    log_info "Verificando convenção de nomenclatura de tópicos..."

    local test_start_time=$(date +%s)

    # Obter lista de tópicos
    local existing_topics=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null || echo "")

    local incorrect_topics=()

    # Verificar tópicos com hífen que deveriam usar ponto
    while IFS= read -r topic; do
        if [[ "$topic" =~ ^intentions-[a-z]+$ ]]; then
            incorrect_topics+=("$topic")
            log_error "❌ Tópico com nomenclatura incorreta: $topic (usar ponto ao invés de hífen)"
        fi
    done <<< "$existing_topics"

    local check_time=$(($(date +%s) - test_start_time))

    if [[ ${#incorrect_topics[@]} -eq 0 ]]; then
        add_test_result "kafka-topic-naming" "PASS" "medium" \
            "Todos os tópicos seguem a convenção de nomenclatura correta" "" "$check_time"
        log_success "✅ Convenção de nomenclatura OK"
        return 0
    else
        add_test_result "kafka-topic-naming" "WARNING" "medium" \
            "${#incorrect_topics[@]} tópicos com nomenclatura incorreta: ${incorrect_topics[*]}" \
            "Deletar tópicos incorretos e recriar com nomenclatura correta (intentions.* ao invés de intentions-*)" "$check_time"
        return 1
    fi
}

# Verificar consumer groups ativos
check_consumer_groups() {
    log_info "Verificando consumer groups..."

    local test_start_time=$(date +%s)

    # Listar consumer groups
    local consumer_groups=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null || echo "")

    if [[ -z "$consumer_groups" ]]; then
        add_test_result "kafka-consumer-groups" "WARNING" "medium" \
            "Nenhum consumer group encontrado" \
            "Verificar se os serviços consumidores estão running"
        return 1
    fi

    local missing_groups=()
    local found_groups=()

    for group in "${CRITICAL_CONSUMER_GROUPS[@]}"; do
        if echo "$consumer_groups" | grep -q "$group"; then
            found_groups+=("$group")
            log_success "✅ Consumer group $group encontrado"
        else
            missing_groups+=("$group")
            log_warning "⚠️  Consumer group $group não encontrado"
        fi
    done

    local check_time=$(($(date +%s) - test_start_time))

    if [[ ${#missing_groups[@]} -eq 0 ]]; then
        add_test_result "kafka-consumer-groups" "PASS" "medium" \
            "Todos os ${#found_groups[@]} consumer groups críticos estão ativos" "" "$check_time"
        return 0
    else
        add_test_result "kafka-consumer-groups" "WARNING" "medium" \
            "${#missing_groups[@]} consumer groups ausentes: ${missing_groups[*]}" \
            "Verificar se serviços correspondentes estão running" "$check_time"
        return 1
    fi
}

# Verificar lag de consumo por tópico
check_topic_lag() {
    log_info "Verificando lag de consumo..."

    local test_start_time=$(date +%s)
    local high_lag_groups=()
    local warning_lag_groups=()

    # Verificar lag para cada consumer group crítico
    for group in "${CRITICAL_CONSUMER_GROUPS[@]}"; do
        local lag_info=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
            kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group "$group" 2>/dev/null || echo "")

        if [[ -z "$lag_info" ]] || [[ "$lag_info" == *"does not exist"* ]]; then
            continue
        fi

        # Extrair lag total (soma de todas as partições)
        local total_lag=$(echo "$lag_info" | awk 'NR>1 {sum += $6} END {print sum+0}')

        if [[ $total_lag -gt $MAX_ACCEPTABLE_LAG ]]; then
            high_lag_groups+=("$group:$total_lag")
            log_error "❌ Consumer group $group: lag crítico de $total_lag mensagens"
        elif [[ $total_lag -gt $WARNING_LAG ]]; then
            warning_lag_groups+=("$group:$total_lag")
            log_warning "⚠️  Consumer group $group: lag de $total_lag mensagens"
        else
            log_debug "✅ Consumer group $group: lag=$total_lag OK"
        fi
    done

    local check_time=$(($(date +%s) - test_start_time))

    if [[ ${#high_lag_groups[@]} -gt 0 ]]; then
        add_test_result "kafka-consumer-lag" "FAIL" "high" \
            "${#high_lag_groups[@]} consumer groups com lag crítico: ${high_lag_groups[*]}" \
            "Verificar performance dos consumidores e considerar scale out" "$check_time"
        return 1
    elif [[ ${#warning_lag_groups[@]} -gt 0 ]]; then
        add_test_result "kafka-consumer-lag" "WARNING" "high" \
            "${#warning_lag_groups[@]} consumer groups com lag elevado: ${warning_lag_groups[*]}" \
            "Monitorar tendência de lag e considerar otimização" "$check_time"
        return 0
    else
        add_test_result "kafka-consumer-lag" "PASS" "high" \
            "Todos os consumer groups com lag aceitável (<$WARNING_LAG)" "" "$check_time"
        return 0
    fi
}

# Verificar Schema Registry
check_schema_registry() {
    log_info "Verificando Schema Registry..."

    local test_start_time=$(date +%s)

    # Verificar se pod do Schema Registry está running
    local sr_status=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app=schema-registry -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")

    if [[ "$sr_status" != "Running" ]]; then
        add_test_result "kafka-schema-registry" "FAIL" "high" \
            "Schema Registry não está running (status: $sr_status)" \
            "Verificar deployment do Schema Registry: kubectl get pods -n $KAFKA_NAMESPACE -l app=schema-registry"
        return 1
    fi

    # Testar endpoint do Schema Registry
    local sr_response=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        curl -s -o /dev/null -w "%{http_code}" "${SCHEMA_REGISTRY_URL}/subjects" 2>/dev/null || echo "000")

    local check_time=$(($(date +%s) - test_start_time))

    if [[ "$sr_response" == "200" ]]; then
        # Listar schemas registrados
        local subjects=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
            curl -s "${SCHEMA_REGISTRY_URL}/subjects" 2>/dev/null || echo "[]")
        local subject_count=$(echo "$subjects" | jq '. | length' 2>/dev/null || echo "0")

        add_test_result "kafka-schema-registry" "PASS" "high" \
            "Schema Registry acessível com $subject_count schemas registrados" "" "$check_time"
        log_success "✅ Schema Registry: $subject_count schemas registrados"
        return 0
    else
        add_test_result "kafka-schema-registry" "FAIL" "high" \
            "Schema Registry não está respondendo (HTTP $sr_response)" \
            "Verificar logs: kubectl logs -n $KAFKA_NAMESPACE -l app=schema-registry" "$check_time"
        return 1
    fi
}

# Gerar relatório de saúde Kafka
generate_kafka_health_report() {
    log_info "Gerando relatório de saúde Kafka..."

    local report_file="/tmp/kafka-health-report-$(date +%Y%m%d_%H%M%S).json"

    # Coletar métricas adicionais
    local broker_count=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l app.kubernetes.io/name=kafka --no-headers 2>/dev/null | wc -l)
    local topic_count=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l || echo "0")
    local consumer_count=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l || echo "0")

    cat > "$report_file" <<EOF
{
    "timestamp": "$(date -Iseconds)",
    "cluster": {
        "namespace": "$KAFKA_NAMESPACE",
        "broker_count": $broker_count,
        "topic_count": $topic_count,
        "consumer_group_count": $consumer_count
    },
    "intention_topics": {
        "expected": ${#EXPECTED_INTENTION_TOPICS[@]},
        "topics": $(printf '%s\n' "${EXPECTED_INTENTION_TOPICS[@]}" | jq -R . | jq -s .)
    },
    "validation_results": $(jq '.test_results' "$REPORT_FILE" 2>/dev/null || echo '{}'),
    "recommendations": [
        "Executar validação regularmente via CI/CD",
        "Monitorar lag de consumer groups via Prometheus",
        "Configurar alertas para tópicos ausentes"
    ]
}
EOF

    log_info "Relatório de saúde Kafka salvo em: $report_file"
    echo "$report_file"
}

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

main() {
    init_report "Validação de tópicos Kafka do Neural Hive-Mind"

    log_info "Iniciando validação de tópicos Kafka..."
    log_info "Namespace: $KAFKA_NAMESPACE"
    log_info "Broker: $KAFKA_BROKER"

    # Verificar pré-requisitos
    if ! command -v kubectl &> /dev/null; then
        add_test_result "prerequisites" "FAIL" "critical" "kubectl não encontrado" "Instalar kubectl"
        generate_summary_report
        exit 1
    fi

    # Verificar se namespace existe
    if ! kubectl get namespace "$KAFKA_NAMESPACE" &> /dev/null; then
        add_test_result "kafka-namespace" "FAIL" "critical" \
            "Namespace $KAFKA_NAMESPACE não existe" \
            "Criar namespace: kubectl create namespace $KAFKA_NAMESPACE"
        generate_summary_report
        exit 1
    fi

    add_test_result "prerequisites" "PASS" "high" "Todos os pré-requisitos atendidos" ""

    # Executar validações
    check_kafka_broker_connectivity
    validate_topic_existence
    validate_topic_configuration
    check_topic_naming_convention
    check_consumer_groups
    check_topic_lag
    check_schema_registry

    # Gerar relatórios
    generate_kafka_health_report
    generate_summary_report

    local html_report=$(export_html_report)

    log_success "==============================================="
    log_success "Validação de tópicos Kafka completa!"
    log_info "Health Score: $TOTAL_SCORE/$MAX_POSSIBLE_SCORE ($(( TOTAL_SCORE * 100 / MAX_POSSIBLE_SCORE ))%)"
    log_info "Relatório JSON: $(export_json_report)"
    log_info "Relatório HTML: $html_report"
    log_success "==============================================="

    # Retornar código de saída baseado nos resultados
    if [[ $FAILED_TESTS -gt 0 ]]; then
        exit 1
    else
        exit 0
    fi
}

main "$@"
