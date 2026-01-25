#!/bin/bash
# Script de simulação de incidentes para Flow C
# ATENÇÃO: Executar apenas em ambiente de staging/desenvolvimento
# Este script simula cenários de falha controlados para validação de runbooks

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuração do ambiente
ORCHESTRATION_NS="${ORCHESTRATION_NS:-neural-hive-orchestration}"
EXECUTION_NS="${EXECUTION_NS:-neural-hive-execution}"
REGISTRY_NS="${REGISTRY_NS:-neural-hive-registry}"
KAFKA_NS="${KAFKA_NS:-kafka}"
MONGODB_NS="${MONGODB_NS:-mongodb-cluster}"
REDIS_NS="${REDIS_NS:-redis-cluster}"
MONITORING_NS="${MONITORING_NS:-monitoring}"
TEMPORAL_NS="${TEMPORAL_NS:-temporal}"

# Nomes dos releases Helm
ORCHESTRATOR_RELEASE="${ORCHESTRATOR_RELEASE:-orchestrator-dynamic}"
WORKER_RELEASE="${WORKER_RELEASE:-worker-agents}"

# Pods de serviços externos
KAFKA_POD="${KAFKA_POD:-neural-hive-kafka-kafka-0}"
REDIS_POD="${REDIS_POD:-redis-cluster-0}"

# Variável para tracking do estado original
ORIGINAL_WORKER_REPLICAS=""
SIMULATION_ACTIVE=false

# Função de cleanup para garantir rollback
cleanup() {
    if [ "$SIMULATION_ACTIVE" = true ]; then
        echo ""
        echo -e "${YELLOW}Executando cleanup/rollback automático...${NC}"
        rollback_all
    fi
}

trap cleanup EXIT

# Verificação de segurança
check_environment() {
    echo -e "${BLUE}=== Verificação de Ambiente ===${NC}"

    # Verificar se não está em produção
    CONTEXT=$(kubectl config current-context)
    if [[ "$CONTEXT" == *"prod"* ]] || [[ "$CONTEXT" == *"production"* ]]; then
        echo -e "${RED}ERRO: Este script não deve ser executado em produção!${NC}"
        echo "Contexto atual: $CONTEXT"
        exit 1
    fi

    echo "Contexto Kubernetes: $CONTEXT"
    echo ""

    # Confirmação do usuário
    read -p "Este script irá simular incidentes no cluster. Continuar? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Operação cancelada."
        exit 0
    fi

    echo ""
}

# Salvar estado original
save_original_state() {
    echo -e "${BLUE}=== Salvando Estado Original ===${NC}"

    ORIGINAL_WORKER_REPLICAS=$(kubectl get deployment worker-agents -n ${EXECUTION_NS} -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "3")
    echo "Worker replicas originais: ${ORIGINAL_WORKER_REPLICAS}"

    # Salvar offsets de consumer groups
    echo "Salvando offsets de consumer groups..."
    kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
        kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups \
        > /tmp/kafka-offsets-before-simulation.txt 2>/dev/null || true

    echo ""
}

# Cenário 1: Workers Indisponíveis
simulate_workers_unavailable() {
    echo -e "${BLUE}=== Cenário 1: Simulando Workers Indisponíveis ===${NC}"
    SIMULATION_ACTIVE=true

    echo "Escalando worker-agents para 0 réplicas..."
    kubectl scale deployment worker-agents --replicas=0 -n ${EXECUTION_NS}

    echo "Aguardando pods terminarem..."
    kubectl wait --for=delete pod -l app=worker-agents -n ${EXECUTION_NS} --timeout=120s 2>/dev/null || true

    echo ""
    echo -e "${YELLOW}Incidente simulado: FlowCWorkersUnavailable${NC}"
    echo "Verificar alerta no Prometheus/Alertmanager"
    echo ""
    echo "Para testar o runbook de troubleshooting, execute:"
    echo "  kubectl get pods -n ${EXECUTION_NS} -l app=worker-agents"
    echo "  curl -s \"http://prometheus.${MONITORING_NS}:9090/api/v1/query?query=neural_hive_service_registry_agents_total{agent_type=\\\"worker\\\"}\" | jq"
    echo ""

    read -p "Pressione ENTER para iniciar rollback ou Ctrl+C para manter o incidente ativo..."

    rollback_workers
}

# Cenário 2: Consumer Group Pausado
simulate_consumer_pause() {
    echo -e "${BLUE}=== Cenário 2: Simulando Consumer Group Pausado ===${NC}"
    SIMULATION_ACTIVE=true

    echo "Pausando consumer group orchestrator-dynamic..."

    # Parar o orchestrator para simular consumer pausado
    kubectl scale deployment orchestrator-dynamic --replicas=0 -n ${ORCHESTRATION_NS}

    echo "Aguardando pods terminarem..."
    kubectl wait --for=delete pod -l app=orchestrator-dynamic -n ${ORCHESTRATION_NS} --timeout=120s 2>/dev/null || true

    echo ""
    echo -e "${YELLOW}Incidente simulado: Consumer group pausado (orchestrator-dynamic parado)${NC}"
    echo "Verificar lag de consumer group:"
    echo ""
    echo "Para testar o runbook, execute:"
    echo "  kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orchestrator-dynamic"
    echo ""

    read -p "Pressione ENTER para iniciar rollback ou Ctrl+C para manter o incidente ativo..."

    rollback_orchestrator
}

# Cenário 3: Workflow Stuck
simulate_stuck_workflow() {
    echo -e "${BLUE}=== Cenário 3: Simulando Workflow Stuck ===${NC}"
    SIMULATION_ACTIVE=true

    echo "Verificando se há workflows ativos..."

    # Listar workflows
    kubectl exec -n ${ORCHESTRATION_NS} deployment/orchestrator-dynamic -- \
        temporal workflow list --namespace neural-hive-mind --limit 5 2>/dev/null || {
        echo -e "${YELLOW}Orchestrator não disponível. Iniciando...${NC}"
        kubectl scale deployment orchestrator-dynamic --replicas=2 -n ${ORCHESTRATION_NS}
        kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n ${ORCHESTRATION_NS} --timeout=120s
    }

    echo ""
    echo -e "${YELLOW}Para simular workflow stuck:${NC}"
    echo "1. Injetar um workflow de teste com timeout longo"
    echo "2. Parar workers para impedir progresso"
    echo "3. Verificar alerta FlowCHighLatency"
    echo ""
    echo "Comandos para diagnóstico (do runbook):"
    echo "  kubectl exec -n ${ORCHESTRATION_NS} deployment/orchestrator-dynamic -- temporal workflow list --namespace neural-hive-mind --query 'ExecutionStatus=\"Running\"'"
    echo ""

    # Simular parando workers temporariamente
    echo "Escalando workers para 0 para simular stuck..."
    kubectl scale deployment worker-agents --replicas=0 -n ${EXECUTION_NS}

    echo ""
    read -p "Pressione ENTER para iniciar rollback ou Ctrl+C para manter o incidente ativo..."

    rollback_workers
}

# Cenário 4: Circuit Breaker Aberto (MongoDB)
simulate_circuit_breaker_open() {
    echo -e "${BLUE}=== Cenário 4: Simulando Circuit Breaker Aberto (MongoDB) ===${NC}"
    SIMULATION_ACTIVE=true

    echo -e "${YELLOW}AVISO: Este cenário pode causar perda de dados temporária!${NC}"
    read -p "Continuar? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Cenário cancelado."
        return
    fi

    echo "Simulando falha de MongoDB escalando para 0..."
    # Isso é destrutivo - apenas para staging
    kubectl scale statefulset mongodb --replicas=0 -n ${MONGODB_NS} 2>/dev/null || \
        echo "MongoDB StatefulSet não encontrado, tentando deployment..."

    echo ""
    echo -e "${YELLOW}Incidente simulado: Circuit breaker MongoDB deve abrir${NC}"
    echo "Verificar logs do orchestrator:"
    echo "  kubectl logs -n ${ORCHESTRATION_NS} -l app=orchestrator-dynamic --tail=100 | grep circuit_breaker"
    echo ""

    read -p "Pressione ENTER para iniciar rollback IMEDIATO..."

    rollback_mongodb
}

# Funções de rollback
rollback_workers() {
    echo -e "${GREEN}=== Rollback: Restaurando Workers ===${NC}"
    REPLICAS="${ORIGINAL_WORKER_REPLICAS:-3}"
    kubectl scale deployment worker-agents --replicas=${REPLICAS} -n ${EXECUTION_NS}
    kubectl wait --for=condition=ready pod -l app=worker-agents -n ${EXECUTION_NS} --timeout=120s
    echo "Workers restaurados para ${REPLICAS} réplicas."
    SIMULATION_ACTIVE=false
}

rollback_orchestrator() {
    echo -e "${GREEN}=== Rollback: Restaurando Orchestrator ===${NC}"
    kubectl scale deployment orchestrator-dynamic --replicas=2 -n ${ORCHESTRATION_NS}
    kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n ${ORCHESTRATION_NS} --timeout=120s
    echo "Orchestrator restaurado."
    SIMULATION_ACTIVE=false
}

rollback_mongodb() {
    echo -e "${GREEN}=== Rollback: Restaurando MongoDB ===${NC}"
    kubectl scale statefulset mongodb --replicas=3 -n ${MONGODB_NS} 2>/dev/null || \
        echo "StatefulSet não encontrado"
    echo "MongoDB restaurado (aguardar sincronização do replica set)."
    SIMULATION_ACTIVE=false
}

rollback_all() {
    echo -e "${GREEN}=== Rollback Completo ===${NC}"

    # Restaurar workers
    REPLICAS="${ORIGINAL_WORKER_REPLICAS:-3}"
    kubectl scale deployment worker-agents --replicas=${REPLICAS} -n ${EXECUTION_NS} 2>/dev/null || true

    # Restaurar orchestrator
    kubectl scale deployment orchestrator-dynamic --replicas=2 -n ${ORCHESTRATION_NS} 2>/dev/null || true

    # Restaurar MongoDB (se foi alterado)
    kubectl scale statefulset mongodb --replicas=3 -n ${MONGODB_NS} 2>/dev/null || true

    echo "Aguardando serviços retornarem..."
    kubectl wait --for=condition=ready pod -l app=worker-agents -n ${EXECUTION_NS} --timeout=120s 2>/dev/null || true
    kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n ${ORCHESTRATION_NS} --timeout=120s 2>/dev/null || true

    echo "Rollback completo."
    SIMULATION_ACTIVE=false
}

# Validação pós-simulação
validate_recovery() {
    echo -e "${BLUE}=== Validação de Recuperação ===${NC}"

    echo "Verificando pods..."
    kubectl get pods -n ${ORCHESTRATION_NS} -l app=orchestrator-dynamic
    kubectl get pods -n ${EXECUTION_NS} -l app=worker-agents

    echo ""
    echo "Verificando métricas..."
    curl -s "http://prometheus.${MONITORING_NS}:9090/api/v1/query?query=up{job=\"orchestrator-dynamic\"}" 2>/dev/null | jq '.data.result[0].value[1]' 2>/dev/null || echo "Prometheus não acessível"

    echo ""
    echo "Validação de recuperação concluída."
}

# Menu principal
show_menu() {
    echo ""
    echo "=========================================="
    echo "  Flow C - Simulação de Incidentes"
    echo "=========================================="
    echo ""
    echo "Cenários disponíveis:"
    echo "  1) Workers Indisponíveis (FlowCWorkersUnavailable)"
    echo "  2) Consumer Group Pausado (lag em Kafka)"
    echo "  3) Workflow Stuck (FlowCHighLatency)"
    echo "  4) Circuit Breaker Aberto (MongoDB) [DESTRUTIVO]"
    echo "  5) Rollback Completo"
    echo "  6) Validar Recuperação"
    echo "  0) Sair"
    echo ""
    read -p "Selecione um cenário: " CHOICE

    case $CHOICE in
        1) simulate_workers_unavailable ;;
        2) simulate_consumer_pause ;;
        3) simulate_stuck_workflow ;;
        4) simulate_circuit_breaker_open ;;
        5) rollback_all ;;
        6) validate_recovery ;;
        0) echo "Saindo..."; exit 0 ;;
        *) echo "Opção inválida" ;;
    esac
}

# Main
main() {
    check_environment
    save_original_state

    while true; do
        show_menu
    done
}

# Execução
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Uso: $0 [opção]"
    echo ""
    echo "Opções:"
    echo "  --help, -h     Mostrar esta ajuda"
    echo "  --rollback     Executar rollback completo"
    echo "  (sem opção)    Iniciar menu interativo"
    echo ""
    echo "Variáveis de ambiente:"
    echo "  ORCHESTRATION_NS    Namespace do orchestrator (default: neural-hive-orchestration)"
    echo "  EXECUTION_NS        Namespace dos workers (default: neural-hive-execution)"
    echo "  KAFKA_NS            Namespace do Kafka (default: kafka)"
    echo "  KAFKA_POD           Nome do pod Kafka (default: neural-hive-kafka-kafka-0)"
    exit 0
elif [ "$1" = "--rollback" ]; then
    rollback_all
    exit 0
else
    main
fi
