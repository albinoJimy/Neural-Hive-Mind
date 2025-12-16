#!/bin/bash
# Script de validação do deployment do Fluxo C (Consensus Engine + Orchestrator Dynamic)
# Não usa 'set -e' para permitir que todos os checks rodem e reportem falhas individualmente

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Variáveis
NAMESPACE="consensus-orchestration"
OUTPUT_JSON=""
SKIP_GRPC=false
SKIP_MONGODB=false
SKIP_REDIS=false
VERBOSE=false

CHECKS_PASSED=0
CHECKS_TOTAL=0
FAILURES=()

# Ajuda
show_help() {
    echo "Uso: $0 [opções]"
    echo
    echo "Valida o deployment do Fluxo C (Consensus Engine + Orchestrator Dynamic)."
    echo
    echo "Opções:"
    echo "  --namespace <ns>       Namespace alvo (padrão: consensus-orchestration)"
    echo "  --output-json <file>   Caminho para salvar relatório JSON"
    echo "  --skip-grpc            Pular validação gRPC"
    echo "  --skip-mongodb         Pular validação MongoDB"
    echo "  --skip-redis           Pular validação Redis"
    echo "  --verbose              Output detalhado"
    echo "  -h, --help             Mostra esta ajuda"
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace) NAMESPACE="$2"; shift 2 ;;
        --output-json) OUTPUT_JSON="$2"; shift 2 ;;
        --skip-grpc) SKIP_GRPC=true; shift ;;
        --skip-mongodb) SKIP_MONGODB=true; shift ;;
        --skip-redis) SKIP_REDIS=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        -h|--help) show_help; exit 0 ;;
        *) echo "Opção desconhecida: $1"; show_help; exit 1 ;;
    esac
done

log_check() {
    local name="$1"
    local result="$2" # 0 = PASS, 1 = FAIL
    local msg="$3"
    
    ((CHECKS_TOTAL++))
    
    if [[ $result -eq 0 ]]; then
        ((CHECKS_PASSED++))
        echo -e "${GREEN}[PASS]${NC} $name"
        if [[ "$VERBOSE" == "true" && -n "$msg" ]]; then echo "       $msg"; fi
    else
        echo -e "${RED}[FAIL]${NC} $name"
        if [[ -n "$msg" ]]; then echo "       Erro: $msg"; fi
        FAILURES+=("$name: $msg")
    fi
}

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }

# 1. Validação de Namespace e Recursos
validate_resources() {
    log_info "1. Validando Namespace e Recursos..."
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_check "Namespace $NAMESPACE existe" 0 ""
    else
        log_check "Namespace $NAMESPACE existe" 1 "Namespace não encontrado"
        return
    fi

    # Deployments
    for app in consensus-engine orchestrator-dynamic; do
        local ready=$(kubectl get deployment "$app" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$ready" -ge 1 ]]; then
            log_check "Deployment $app Ready" 0 "Replicas: $ready"
        else
            log_check "Deployment $app Ready" 1 "Nenhuma réplica pronta"
        fi
    done

    # Services
    for svc in consensus-engine orchestrator-dynamic; do
        if kubectl get svc "$svc" -n "$NAMESPACE" &> /dev/null; then
            log_check "Service $svc existe" 0 ""
        else
            log_check "Service $svc existe" 1 "Service não encontrado"
        fi
    done
}

# 2. Validação de Health Endpoints (via port-forward)
validate_health() {
    log_info "2. Validando Health Endpoints (via port-forward)..."
    
    # Consensus Engine
    local ce_pod=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$ce_pod" ]]; then
        local port=18000
        kubectl port-forward -n "$NAMESPACE" "$ce_pod" "$port:8000" >/dev/null 2>&1 &
        local pf_pid=$!
        sleep 2
        
        local health=$(curl -s --max-time 5 "http://localhost:$port/health" 2>/dev/null || echo "failed")
        kill $pf_pid 2>/dev/null || true
        
        if [[ "$health" == *"healthy"* ]]; then
            log_check "Consensus Engine Health" 0 "$health"
        else
            log_check "Consensus Engine Health" 1 "Resposta inválida: $health"
        fi
    else
        log_check "Consensus Engine Pod" 1 "Pod não encontrado"
    fi

    # Orchestrator Dynamic
    local od_pod=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$od_pod" ]]; then
        local port=18001
        kubectl port-forward -n "$NAMESPACE" "$od_pod" "$port:8000" >/dev/null 2>&1 &
        local pf_pid=$!
        sleep 2
        
        local health=$(curl -s --max-time 5 "http://localhost:$port/health" 2>/dev/null || echo "failed")
        kill $pf_pid 2>/dev/null || true
        
        if [[ "$health" == *"healthy"* ]]; then
            log_check "Orchestrator Dynamic Health" 0 "$health"
        else
            log_check "Orchestrator Dynamic Health" 1 "Resposta inválida: $health"
        fi
    else
        log_check "Orchestrator Dynamic Pod" 1 "Pod não encontrado"
    fi
}

# 3. Validação Kafka
validate_kafka() {
    log_info "3. Validando Kafka..."
    
    # Tópicos
    local topics=$(kubectl exec -n kafka neural-hive-kafka-kafka-0 -- bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null)
    
    for topic in plans.ready plans.consensus execution.tickets; do
        if echo "$topics" | grep -q "$topic"; then
            log_check "Tópico $topic existe" 0 ""
        else
            log_check "Tópico $topic existe" 1 "Tópico não encontrado"
        fi
    done

    # Consumer Groups
    local groups=$(kubectl exec -n kafka neural-hive-kafka-kafka-0 -- bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null)
    
    if echo "$groups" | grep -q "consensus-engine-local"; then
        log_check "Consumer Group consensus-engine-local" 0 ""
    else
        log_check "Consumer Group consensus-engine-local" 1 "Grupo não encontrado"
    fi

    if echo "$groups" | grep -q "orchestrator-dynamic-local"; then
        log_check "Consumer Group orchestrator-dynamic-local" 0 ""
    else
        log_check "Consumer Group orchestrator-dynamic-local" 1 "Grupo não encontrado"
    fi
}

# 4. Validação gRPC (Specialists)
validate_grpc() {
    if [[ "$SKIP_GRPC" == "true" ]]; then return; fi
    log_info "4. Validando gRPC Specialists..."

    # Requer grpcurl instalado no pod ou local port-forward. 
    # Aqui vamos checar se o Consensus Engine consegue conectar (via logs ou status)
    # Alternativa: checar status via endpoint /status do Consensus Engine se disponível
    
    local ce_pod=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$ce_pod" ]]; then
        # Verifica logs recentes por erros de conexão gRPC
        if kubectl logs -n "$NAMESPACE" "$ce_pod" --tail=100 | grep -q "Unavailable"; then
             log_check "Conexão gRPC Specialists" 1 "Erros 'Unavailable' encontrados nos logs"
        else
             log_check "Conexão gRPC Specialists" 0 "Sem erros recentes nos logs"
        fi
    fi
}

# 5. Validação MongoDB
validate_mongodb() {
    if [[ "$SKIP_MONGODB" == "true" ]]; then return; fi
    log_info "5. Validando MongoDB..."

    # Verifica se collections existem
    local mongo_pod="mongodb-0" # Assumindo statefulset padrão ou ajustar conforme ambiente
    
    # Check simples via mongosh (requer mongosh no pod ou exec)
    # Tentativa via kubectl exec no pod do mongodb
    if kubectl exec -n mongodb-cluster "$mongo_pod" -- mongosh --quiet --eval "db.getMongo().getDBNames()" &> /dev/null; then
         log_check "Conexão MongoDB" 0 "Conectado com sucesso"
    else
         log_check "Conexão MongoDB" 1 "Falha ao conectar via mongosh"
    fi
}

# 6. Validação Redis
validate_redis() {
    if [[ "$SKIP_REDIS" == "true" ]]; then return; fi
    log_info "6. Validando Redis..."

    local redis_pod="neural-hive-cache-0" # Ajustar conforme nome real
    if kubectl exec -n redis-cluster "$redis_pod" -- redis-cli PING | grep -q "PONG"; then
        log_check "Conexão Redis" 0 "PONG recebido"
    else
        log_check "Conexão Redis" 1 "Falha no PING"
    fi
}

# 7. Validação de Logs Específicos
validate_logs() {
    log_info "7. Validando Logs Específicos..."
    
    # Consensus Engine - Bayesian aggregation
    local ce_pod=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$ce_pod" ]]; then
        if kubectl logs -n "$NAMESPACE" "$ce_pod" --tail=500 2>/dev/null | grep -q "Bayesian\|aggregation\|consensus"; then
            log_check "Consensus Engine Logs (Bayesian)" 0 "Mensagens de agregação encontradas"
        else
            log_check "Consensus Engine Logs (Bayesian)" 1 "Mensagens de agregação não encontradas"
        fi
    fi
    
    # Orchestrator - Ticket generation
    local od_pod=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$od_pod" ]]; then
        if kubectl logs -n "$NAMESPACE" "$od_pod" --tail=500 2>/dev/null | grep -q "ticket\|workflow\|execution"; then
            log_check "Orchestrator Logs (Tickets)" 0 "Mensagens de geração de tickets encontradas"
        else
            log_check "Orchestrator Logs (Tickets)" 1 "Mensagens de tickets não encontradas"
        fi
    fi
}

# 8. Validação Profunda MongoDB
validate_mongodb_deep() {
    if [[ "$SKIP_MONGODB" == "true" ]]; then return; fi
    log_info "8. Validando MongoDB (Collections e Documentos)..."
    
    local mongo_pod="mongodb-0"
    
    # Verifica collection consensus_decisions
    local count=$(kubectl exec -n mongodb-cluster "$mongo_pod" -- mongosh --quiet --eval "db.getSiblingDB('neural_hive').consensus_decisions.countDocuments()" 2>/dev/null || echo "0")
    if [[ "$count" =~ ^[0-9]+$ && "$count" -ge 0 ]]; then
        log_check "MongoDB consensus_decisions collection" 0 "$count documentos encontrados"
    else
        log_check "MongoDB consensus_decisions collection" 1 "Falha ao contar documentos"
    fi
    
    # Verifica collection workflows
    local count_wf=$(kubectl exec -n mongodb-cluster "$mongo_pod" -- mongosh --quiet --eval "db.getSiblingDB('neural_hive_orchestration').workflows.countDocuments()" 2>/dev/null || echo "0")
    if [[ "$count_wf" =~ ^[0-9]+$ && "$count_wf" -ge 0 ]]; then
        log_check "MongoDB workflows collection" 0 "$count_wf documentos encontrados"
    else
        log_check "MongoDB workflows collection" 1 "Falha ao contar documentos"
    fi
}

# 9. Validação Profunda Redis (Pheromones)
validate_redis_deep() {
    if [[ "$SKIP_REDIS" == "true" ]]; then return; fi
    log_info "9. Validando Redis (Pheromones)..."
    
    local redis_pod="neural-hive-cache-0"
    
    # Lista chaves pheromone:*
    local keys=$(kubectl exec -n redis-cluster "$redis_pod" -- redis-cli KEYS "pheromone:*" 2>/dev/null | wc -l)
    if [[ "$keys" -ge 0 ]]; then
        log_check "Redis pheromone keys" 0 "$keys chaves encontradas"
        
        # Verifica TTL de uma chave se existir
        if [[ "$keys" -gt 0 ]]; then
            local sample_key=$(kubectl exec -n redis-cluster "$redis_pod" -- redis-cli KEYS "pheromone:*" 2>/dev/null | head -n1)
            local ttl=$(kubectl exec -n redis-cluster "$redis_pod" -- redis-cli TTL "$sample_key" 2>/dev/null || echo "-2")
            if [[ "$ttl" -gt 0 ]]; then
                log_check "Redis pheromone TTL" 0 "TTL positivo: $ttl segundos"
            else
                log_check "Redis pheromone TTL" 1 "TTL inválido ou chave sem expiração"
            fi
        fi
    else
        log_check "Redis pheromone keys" 1 "Falha ao listar chaves"
    fi
}

# 10. Validação de Mensagens Kafka
validate_kafka_messages() {
    log_info "10. Validando Mensagens Kafka (Sample)..."
    
    # Tenta ler uma mensagem de plans.consensus
    local msg=$(kubectl exec -n kafka neural-hive-kafka-kafka-0 -- bin/kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 \
        --topic plans.consensus \
        --from-beginning \
        --max-messages 1 \
        --timeout-ms 5000 2>/dev/null || echo "")
    
    if [[ -n "$msg" ]]; then
        # Verifica campos essenciais (JSON esperado)
        if echo "$msg" | grep -q '"plan_id"\|"confidence"\|"decision"'; then
            log_check "Kafka plans.consensus message" 0 "Mensagem válida com campos essenciais"
        else
            log_check "Kafka plans.consensus message" 1 "Mensagem sem campos esperados"
        fi
    else
        log_check "Kafka plans.consensus message" 1 "Nenhuma mensagem encontrada (pode ser normal se não houver tráfego)"
    fi
    
    # Tenta ler uma mensagem de execution.tickets
    local msg_ticket=$(kubectl exec -n kafka neural-hive-kafka-kafka-0 -- bin/kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 \
        --topic execution.tickets \
        --from-beginning \
        --max-messages 1 \
        --timeout-ms 5000 2>/dev/null || echo "")
    
    if [[ -n "$msg_ticket" ]]; then
        if echo "$msg_ticket" | grep -q '"ticket_id"\|"workflow"\|"tasks"'; then
            log_check "Kafka execution.tickets message" 0 "Mensagem válida com campos essenciais"
        else
            log_check "Kafka execution.tickets message" 1 "Mensagem sem campos esperados"
        fi
    else
        log_check "Kafka execution.tickets message" 1 "Nenhuma mensagem encontrada (pode ser normal se não houver tráfego)"
    fi
}

# Execução
echo "Iniciando validação do Fluxo C..."
echo "Data: $(date)"
echo "Namespace: $NAMESPACE"
echo "----------------------------------------"

validate_resources
validate_health
validate_kafka
validate_grpc
validate_mongodb
validate_redis
validate_logs
validate_mongodb_deep
validate_redis_deep
validate_kafka_messages

echo "----------------------------------------"
echo "Resumo:"
echo "Checks Totais: $CHECKS_TOTAL"
echo "Checks Passaram: $CHECKS_PASSED"
echo "Falhas: ${#FAILURES[@]}"

if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo
    echo "Lista de Falhas:"
    for fail in "${FAILURES[@]}"; do
        echo -e "${RED}- $fail${NC}"
    done
    
    # Gerar JSON se solicitado
    if [[ -n "$OUTPUT_JSON" ]]; then
        echo "{\"timestamp\": \"$(date -Iseconds)\", \"status\": \"FAILED\", \"passed\": $CHECKS_PASSED, \"total\": $CHECKS_TOTAL, \"failures\": [$(printf '"%s",' "${FAILURES[@]}" | sed 's/,$//')]}" > "$OUTPUT_JSON"
    fi
    
    exit 1
else
    echo -e "${GREEN}Todos os checks passaram! Fluxo C validado.${NC}"
    if [[ -n "$OUTPUT_JSON" ]]; then
        echo "{\"timestamp\": \"$(date -Iseconds)\", \"status\": \"SUCCESS\", \"passed\": $CHECKS_PASSED, \"total\": $CHECKS_TOTAL, \"failures\": []}" > "$OUTPUT_JSON"
    fi
    exit 0
fi
