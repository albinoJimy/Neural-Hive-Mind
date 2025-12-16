#!/usr/bin/env bash
#
# test_kafka_consumers.sh - Validacao de Kafka Consumers da Fase 2
#
# Este script valida os Kafka consumers de todos os servicos da Fase 2:
# - Verifica consumer groups ativos
# - Monitora consumer lag
# - Valida subscricoes de topicos
# - Testa publicacao e consumo de mensagens
#
# Uso: ./test_kafka_consumers.sh [--quiet] [--service SERVICE]
#

set -euo pipefail

# Cores para saida
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Configuracao
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-kafka}"
SERVICE_NAMESPACE="${SERVICE_NAMESPACE:-neural-hive}"

# Consumer groups esperados por servico
declare -A CONSUMER_GROUPS=(
    ["orchestrator-dynamic"]="orchestrator-dynamic-group"
    ["queen-agent"]="queen-agent-group"
    ["worker-agents"]="worker-agents-group"
    ["code-forge"]="code-forge-group"
    ["guard-agents"]="guard-agents-group"
)

# Topicos por consumer group
declare -A CONSUMER_TOPICS=(
    ["orchestrator-dynamic-group"]="cognitive-plans-consolidated"
    ["queen-agent-group"]="consensus-decisions,system-telemetry,orchestration-incidents"
    ["worker-agents-group"]="execution-tickets"
    ["code-forge-group"]="code-generation-tickets"
    ["guard-agents-group"]="security-events"
)

# Limiar de lag aceitavel
MAX_LAG_THRESHOLD=1000
WARNING_LAG_THRESHOLD=100

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# Argumentos
QUIET_MODE=false
SPECIFIC_SERVICE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --quiet)
            QUIET_MODE=true
            shift
            ;;
        --service)
            SPECIFIC_SERVICE="$2"
            shift 2
            ;;
        *)
            echo "Opcao desconhecida: $1"
            echo "Uso: $0 [--quiet] [--service SERVICE]"
            exit 1
            ;;
    esac
done

# Funcoes utilitarias
log_info() {
    if [ "$QUIET_MODE" = false ]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

log_success() {
    if [ "$QUIET_MODE" = false ]; then
        echo -e "${GREEN}[PASS]${NC} $1"
    fi
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_failure() {
    if [ "$QUIET_MODE" = false ]; then
        echo -e "${RED}[FAIL]${NC} $1"
    fi
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_warning() {
    if [ "$QUIET_MODE" = false ]; then
        echo -e "${YELLOW}[WARN]${NC} $1"
    fi
    ((WARNINGS++))
}

log_header() {
    if [ "$QUIET_MODE" = false ]; then
        echo ""
        echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
        echo -e "${BOLD}${CYAN}  $1${NC}"
        echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
        echo ""
    fi
}

log_subheader() {
    if [ "$QUIET_MODE" = false ]; then
        echo -e "${BOLD}  ─── $1 ───${NC}"
    fi
}

# Obter pod do Kafka
get_kafka_pod() {
    kubectl get pods -n "$KAFKA_NAMESPACE" -l "app.kubernetes.io/name=kafka" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo ""
}

# Validar consumer groups ativos
validate_consumer_groups() {
    log_header "VALIDACAO 1: Consumer Groups Ativos"

    local kafka_pod
    kafka_pod=$(get_kafka_pod)

    if [ -z "$kafka_pod" ]; then
        log_failure "Pod do Kafka nao encontrado no namespace $KAFKA_NAMESPACE"
        return 1
    fi

    log_info "Usando pod Kafka: $kafka_pod"

    # Listar consumer groups
    local groups
    groups=$(kubectl exec -n "$KAFKA_NAMESPACE" "$kafka_pod" -- \
        kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null || echo "")

    if [ -z "$groups" ]; then
        log_warning "Nenhum consumer group encontrado"
        return 0
    fi

    log_success "Consumer groups encontrados:"
    echo "$groups" | while read -r group; do
        if [ -n "$group" ]; then
            echo "  - $group"
        fi
    done

    # Verificar consumer groups esperados
    for service in "${!CONSUMER_GROUPS[@]}"; do
        if [ -n "$SPECIFIC_SERVICE" ] && [ "$SPECIFIC_SERVICE" != "$service" ]; then
            continue
        fi

        local expected_group="${CONSUMER_GROUPS[$service]}"

        if echo "$groups" | grep -q "$expected_group"; then
            log_success "$service: Consumer group '$expected_group' ativo"
        else
            log_warning "$service: Consumer group '$expected_group' nao encontrado"
        fi
    done
}

# Validar consumer lag
validate_consumer_lag() {
    log_header "VALIDACAO 2: Consumer Lag"

    local kafka_pod
    kafka_pod=$(get_kafka_pod)

    if [ -z "$kafka_pod" ]; then
        log_failure "Pod do Kafka nao encontrado"
        return 1
    fi

    for service in "${!CONSUMER_GROUPS[@]}"; do
        if [ -n "$SPECIFIC_SERVICE" ] && [ "$SPECIFIC_SERVICE" != "$service" ]; then
            continue
        fi

        local group="${CONSUMER_GROUPS[$service]}"
        log_subheader "Verificando lag do grupo: $group"

        # Obter descricao do consumer group
        local group_desc
        group_desc=$(kubectl exec -n "$KAFKA_NAMESPACE" "$kafka_pod" -- \
            kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
            --group "$group" --describe 2>/dev/null || echo "")

        if [ -z "$group_desc" ] || echo "$group_desc" | grep -q "does not exist"; then
            log_warning "$service: Consumer group '$group' nao existe ou inativo"
            continue
        fi

        # Extrair lag total
        local total_lag=0
        local has_data=false

        while IFS= read -r line; do
            # Pular linhas de cabecalho
            if echo "$line" | grep -qE "^GROUP|^TOPIC|^$"; then
                continue
            fi

            # Extrair lag (ultima coluna)
            local lag
            lag=$(echo "$line" | awk '{print $NF}')

            if [[ "$lag" =~ ^[0-9]+$ ]]; then
                total_lag=$((total_lag + lag))
                has_data=true
            fi
        done <<< "$group_desc"

        if [ "$has_data" = true ]; then
            if [ "$total_lag" -gt "$MAX_LAG_THRESHOLD" ]; then
                log_failure "$service: Lag muito alto ($total_lag > $MAX_LAG_THRESHOLD)"
            elif [ "$total_lag" -gt "$WARNING_LAG_THRESHOLD" ]; then
                log_warning "$service: Lag elevado ($total_lag > $WARNING_LAG_THRESHOLD)"
            else
                log_success "$service: Lag aceitavel (lag=$total_lag)"
            fi
        else
            log_warning "$service: Nao foi possivel extrair lag do grupo"
        fi
    done
}

# Validar subscricoes de topicos via logs
validate_topic_subscriptions() {
    log_header "VALIDACAO 3: Subscricoes de Topicos"

    for service in "${!CONSUMER_GROUPS[@]}"; do
        if [ -n "$SPECIFIC_SERVICE" ] && [ "$SPECIFIC_SERVICE" != "$service" ]; then
            continue
        fi

        local group="${CONSUMER_GROUPS[$service]}"
        local topics="${CONSUMER_TOPICS[$group]}"

        log_subheader "Verificando subscricoes do $service"

        # Obter pod do servico
        local pod
        pod=$(kubectl get pods -n "$SERVICE_NAMESPACE" -l "app=$service" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [ -z "$pod" ]; then
            log_warning "$service: Pod nao encontrado"
            continue
        fi

        # Verificar logs para subscricoes de topicos
        local logs
        logs=$(kubectl logs -n "$SERVICE_NAMESPACE" "$pod" --tail=200 2>/dev/null || echo "")

        if [ -z "$logs" ]; then
            log_warning "$service: Logs nao disponiveis"
            continue
        fi

        # Verificar cada topico
        IFS=',' read -ra TOPIC_ARRAY <<< "$topics"
        for topic in "${TOPIC_ARRAY[@]}"; do
            if echo "$logs" | grep -qi "$topic"; then
                log_success "$service: Topico '$topic' referenciado nos logs"
            else
                log_warning "$service: Topico '$topic' nao encontrado nos logs"
            fi
        done

        # Verificar inicializacao do consumer
        if echo "$logs" | grep -qi "kafka.*consumer.*start\|consumer.*initialized\|subscribed"; then
            log_success "$service: Consumer Kafka inicializado"
        else
            log_warning "$service: Inicializacao do consumer nao confirmada"
        fi

        # Verificar erros do consumer
        local errors
        errors=$(echo "$logs" | grep -i "kafka.*error\|consumer.*error\|connection.*refused" || echo "")

        if [ -n "$errors" ]; then
            log_warning "$service: Erros detectados no consumer Kafka"
            if [ "$QUIET_MODE" = false ]; then
                echo "$errors" | head -3 | sed 's/^/    /'
            fi
        fi
    done
}

# Teste de mensagem (opcional)
test_message_flow() {
    log_header "VALIDACAO 4: Fluxo de Mensagens (Teste)"

    local kafka_pod
    kafka_pod=$(get_kafka_pod)

    if [ -z "$kafka_pod" ]; then
        log_warning "Pod do Kafka nao encontrado - pulando teste de mensagem"
        return 0
    fi

    # Criar topico de teste se nao existir
    local test_topic="validation-test-topic"
    log_info "Criando topico de teste: $test_topic"

    kubectl exec -n "$KAFKA_NAMESPACE" "$kafka_pod" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 \
        --create --if-not-exists --topic "$test_topic" \
        --partitions 1 --replication-factor 1 2>/dev/null || true

    # Publicar mensagem de teste
    local test_message="test-message-$(date +%s)"
    log_info "Publicando mensagem de teste: $test_message"

    echo "$test_message" | kubectl exec -i -n "$KAFKA_NAMESPACE" "$kafka_pod" -- \
        kafka-console-producer.sh --bootstrap-server localhost:9092 \
        --topic "$test_topic" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_success "Mensagem publicada com sucesso"
    else
        log_failure "Falha ao publicar mensagem"
        return 1
    fi

    # Consumir mensagem de teste
    log_info "Consumindo mensagem de teste..."

    local consumed
    consumed=$(kubectl exec -n "$KAFKA_NAMESPACE" "$kafka_pod" -- timeout 5 \
        kafka-console-consumer.sh --bootstrap-server localhost:9092 \
        --topic "$test_topic" --from-beginning --max-messages 1 2>/dev/null || echo "")

    if echo "$consumed" | grep -q "$test_message"; then
        log_success "Mensagem consumida com sucesso"
    else
        log_warning "Mensagem nao foi consumida ou timeout"
    fi

    # Limpar topico de teste
    kubectl exec -n "$KAFKA_NAMESPACE" "$kafka_pod" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 \
        --delete --topic "$test_topic" 2>/dev/null || true
}

# Validar metricas de consumer
validate_consumer_metrics() {
    log_header "VALIDACAO 5: Metricas de Consumer"

    for service in "${!CONSUMER_GROUPS[@]}"; do
        if [ -n "$SPECIFIC_SERVICE" ] && [ "$SPECIFIC_SERVICE" != "$service" ]; then
            continue
        fi

        log_subheader "Verificando metricas do $service"

        # Obter pod do servico
        local pod
        pod=$(kubectl get pods -n "$SERVICE_NAMESPACE" -l "app=$service" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [ -z "$pod" ]; then
            log_warning "$service: Pod nao encontrado"
            continue
        fi

        # Verificar metricas Prometheus
        local metrics
        metrics=$(kubectl exec -n "$SERVICE_NAMESPACE" "$pod" -- \
            curl -s "http://localhost:8000/metrics" 2>/dev/null || echo "")

        if [ -z "$metrics" ]; then
            log_warning "$service: Metricas nao disponiveis"
            continue
        fi

        # Verificar metricas de Kafka
        if echo "$metrics" | grep -q "kafka_consumer"; then
            log_success "$service: Metricas de consumer Kafka disponiveis"

            # Extrair algumas metricas
            local messages_consumed
            messages_consumed=$(echo "$metrics" | grep "kafka_consumer_messages_total" | head -1 | awk '{print $2}')

            if [ -n "$messages_consumed" ]; then
                log_info "$service: Mensagens consumidas: $messages_consumed"
            fi
        else
            log_warning "$service: Metricas de consumer Kafka nao encontradas"
        fi
    done
}

# Gerar relatorio
generate_report() {
    log_header "RELATORIO FINAL"

    local overall_status="PASSED"
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        overall_status="FAILED"
    elif [ "$WARNINGS" -gt 3 ]; then
        overall_status="WARNING"
    fi

    if [ "$QUIET_MODE" = false ]; then
        echo -e "${BOLD}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${BOLD}║          RESUMO DA VALIDACAO KAFKA CONSUMERS                   ║${NC}"
        echo -e "${BOLD}╠════════════════════════════════════════════════════════════════╣${NC}"
        printf "${BOLD}║${NC} %-20s │ %s\n" "Total de Verificacoes:" "$TOTAL_CHECKS ${BOLD}║${NC}"
        printf "${BOLD}║${NC} %-20s │ ${GREEN}%s${NC}\n" "Passou:" "$PASSED_CHECKS ${BOLD}║${NC}"
        printf "${BOLD}║${NC} %-20s │ ${RED}%s${NC}\n" "Falhou:" "$FAILED_CHECKS ${BOLD}║${NC}"
        printf "${BOLD}║${NC} %-20s │ ${YELLOW}%s${NC}\n" "Avisos:" "$WARNINGS ${BOLD}║${NC}"
        echo -e "${BOLD}╠════════════════════════════════════════════════════════════════╣${NC}"

        if [ "$overall_status" = "PASSED" ]; then
            echo -e "${BOLD}║${NC}              ${GREEN}${BOLD}STATUS GERAL: PASSOU${NC}                            ${BOLD}║${NC}"
        elif [ "$overall_status" = "WARNING" ]; then
            echo -e "${BOLD}║${NC}              ${YELLOW}${BOLD}STATUS GERAL: AVISO${NC}                             ${BOLD}║${NC}"
        else
            echo -e "${BOLD}║${NC}              ${RED}${BOLD}STATUS GERAL: FALHOU${NC}                            ${BOLD}║${NC}"
        fi

        echo -e "${BOLD}╚════════════════════════════════════════════════════════════════╝${NC}"
    fi

    # Retornar codigo de saida apropriado
    if [ "$overall_status" = "FAILED" ]; then
        return 1
    fi
    return 0
}

# Main
main() {
    if [ "$QUIET_MODE" = false ]; then
        echo -e "${BOLD}${CYAN}"
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║     NEURAL HIVE MIND - VALIDACAO KAFKA CONSUMERS               ║"
        echo "║                                                                 ║"
        echo "║     Validacao completa dos consumers Kafka da Fase 2           ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo -e "${NC}"
    fi

    local start_time
    start_time=$(date +%s)

    # Executar validacoes
    validate_consumer_groups
    validate_consumer_lag
    validate_topic_subscriptions
    validate_consumer_metrics

    # Teste de mensagem opcional (apenas se nao estiver em modo quiet)
    if [ "$QUIET_MODE" = false ]; then
        test_message_flow
    fi

    # Gerar relatorio
    generate_report
    local result=$?

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ "$QUIET_MODE" = false ]; then
        echo ""
        log_info "Validacao concluida em ${duration} segundos"
    fi

    exit $result
}

# Executar
main "$@"
