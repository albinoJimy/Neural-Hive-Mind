#!/bin/bash

# validate-redis-cluster.sh
# Script de validação do Redis Cluster
# Verifica conectividade, distribuição de dados e performance

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurações
NAMESPACE="redis-system"
CLUSTER_NAME="neural-hive-cluster"
TEST_KEY_PREFIX="neural-hive-test"
NUM_TEST_KEYS=100

# Funções utilitárias
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

check_cluster_status() {
    log_info "Verificando status do Redis Cluster..."

    # Verificar se o cluster existe
    if ! kubectl get rediscluster $CLUSTER_NAME -n $NAMESPACE &> /dev/null; then
        log_error "Redis Cluster '$CLUSTER_NAME' não encontrado no namespace '$NAMESPACE'"
        return 1
    fi

    # Verificar número de réplicas prontas
    local ready_replicas=$(kubectl get rediscluster $CLUSTER_NAME -n $NAMESPACE -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$ready_replicas" != "6" ]; then
        log_error "Redis Cluster não está completamente pronto. Réplicas prontas: $ready_replicas/6"
        return 1
    fi

    log_success "Redis Cluster está ativo com 6 réplicas"
    return 0
}

check_pod_status() {
    log_info "Verificando status dos pods Redis..."

    local pods=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster -o name | wc -l)
    if [ "$pods" -lt 6 ]; then
        log_error "Número insuficiente de pods Redis: $pods/6"
        return 1
    fi

    # Verificar se todos os pods estão running
    local running_pods=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster --field-selector=status.phase=Running -o name | wc -l)
    if [ "$running_pods" -ne 6 ]; then
        log_error "Nem todos os pods estão em estado Running: $running_pods/6"
        kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster
        return 1
    fi

    log_success "Todos os 6 pods Redis estão em estado Running"
    return 0
}

check_cluster_connectivity() {
    log_info "Testando conectividade do cluster Redis..."

    # Obter pod de um master para testes
    local master_pod=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$master_pod" ]; then
        log_error "Não foi possível encontrar pod master do Redis"
        return 1
    fi

    # Testar comando CLUSTER NODES
    if ! kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli cluster nodes &> /dev/null; then
        log_error "Falha ao executar 'cluster nodes' no Redis"
        return 1
    fi

    # Verificar número de nós no cluster
    local cluster_size=$(kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli cluster nodes | wc -l)
    if [ "$cluster_size" -ne 6 ]; then
        log_error "Número incorreto de nós no cluster: $cluster_size/6"
        return 1
    fi

    log_success "Conectividade do cluster Redis verificada"
    return 0
}

test_data_distribution() {
    log_info "Testando distribuição de dados no cluster..."

    local master_pod=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}')

    # Inserir chaves de teste
    log_info "Inserindo $NUM_TEST_KEYS chaves de teste..."
    for i in $(seq 1 $NUM_TEST_KEYS); do
        kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli set "${TEST_KEY_PREFIX}:$i" "test-value-$i" EX 300 &> /dev/null
    done

    # Verificar distribuição entre masters
    log_info "Verificando distribuição entre masters..."
    local masters=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[*].metadata.name}')
    local total_keys=0
    local distribution_ok=true

    for master in $masters; do
        local keys_count=$(kubectl exec -n $NAMESPACE "$master" -- redis-cli --scan --pattern "${TEST_KEY_PREFIX}:*" | wc -l)
        total_keys=$((total_keys + keys_count))
        log_info "Master $master: $keys_count chaves"

        # Verificar se cada master tem pelo menos algumas chaves (distribuição não vazia)
        if [ "$keys_count" -eq 0 ]; then
            log_warning "Master $master não possui chaves de teste"
            distribution_ok=false
        fi
    done

    if [ "$total_keys" -ne "$NUM_TEST_KEYS" ]; then
        log_error "Número total de chaves incorreto: $total_keys/$NUM_TEST_KEYS"
        return 1
    fi

    if [ "$distribution_ok" = false ]; then
        log_warning "Distribuição de dados pode não estar balanceada"
    else
        log_success "Distribuição de dados no cluster está funcionando"
    fi

    return 0
}

test_read_write_performance() {
    log_info "Testando performance de leitura/escrita..."

    local master_pod=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}')

    # Teste de escrita
    local write_start=$(date +%s%N)
    for i in $(seq 1 50); do
        kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli set "perf-test:write:$i" "performance-test-value-$i" EX 300 &> /dev/null
    done
    local write_end=$(date +%s%N)
    local write_time=$(((write_end - write_start) / 1000000))  # ms

    # Teste de leitura
    local read_start=$(date +%s%N)
    for i in $(seq 1 50); do
        kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli get "perf-test:write:$i" &> /dev/null
    done
    local read_end=$(date +%s%N)
    local read_time=$(((read_end - read_start) / 1000000))  # ms

    log_info "Performance de escrita: ${write_time}ms para 50 operações ($(bc -l <<< "scale=2; $write_time/50")ms por operação)"
    log_info "Performance de leitura: ${read_time}ms para 50 operações ($(bc -l <<< "scale=2; $read_time/50")ms por operação)"

    # Alertar se performance está muito lenta
    if [ "$write_time" -gt 5000 ]; then  # > 5s para 50 escritas
        log_warning "Performance de escrita está lenta"
    fi

    if [ "$read_time" -gt 2000 ]; then  # > 2s para 50 leituras
        log_warning "Performance de leitura está lenta"
    fi

    log_success "Teste de performance concluído"
    return 0
}

test_failover() {
    log_info "Testando capacidade de failover..."

    # Este teste é mais complexo e pode ser destrutivo
    # Por enquanto, apenas verificamos se há slaves configurados
    local master_pod=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}')

    # Verificar se há slaves conectados
    local slaves_info=$(kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli info replication | grep "connected_slaves:")
    local num_slaves=$(echo "$slaves_info" | cut -d':' -f2 | tr -d '\r')

    if [ "$num_slaves" -eq 0 ]; then
        log_warning "Nenhum slave conectado detectado para failover"
    else
        log_success "Slaves configurados para failover: $num_slaves"
    fi

    return 0
}

cleanup_test_data() {
    log_info "Limpando dados de teste..."

    local master_pod=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}')

    # Remover chaves de teste de distribuição
    kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli --scan --pattern "${TEST_KEY_PREFIX}:*" | \
        xargs -I {} kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli del {} &> /dev/null || true

    # Remover chaves de teste de performance
    kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli --scan --pattern "perf-test:*" | \
        xargs -I {} kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli del {} &> /dev/null || true

    log_success "Dados de teste removidos"
}

generate_report() {
    log_info "=== RELATÓRIO DE VALIDAÇÃO DO REDIS CLUSTER ==="
    log_info "Timestamp: $(date)"
    log_info "Namespace: $NAMESPACE"
    log_info "Cluster: $CLUSTER_NAME"

    # Status geral
    if check_cluster_status && check_pod_status && check_cluster_connectivity; then
        log_success "✅ Status do cluster: SAUDÁVEL"
    else
        log_error "❌ Status do cluster: PROBLEMAS DETECTADOS"
        return 1
    fi

    # Informações do cluster
    local master_pod=$(kubectl get pods -n $NAMESPACE -l app=neural-hive-cluster,role=master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$master_pod" ]; then
        log_info "Informações do cluster:"
        kubectl exec -n $NAMESPACE "$master_pod" -- redis-cli cluster info | grep -E "(cluster_state|cluster_slots_assigned|cluster_known_nodes)" | while read line; do
            log_info "  $line"
        done
    fi

    return 0
}

main() {
    log_info "=== Iniciando validação do Redis Cluster ==="

    local validation_failed=false

    # Verificações básicas
    if ! check_cluster_status; then
        validation_failed=true
    fi

    if ! check_pod_status; then
        validation_failed=true
    fi

    if ! check_cluster_connectivity; then
        validation_failed=true
    fi

    # Testes funcionais (apenas se básicos passaram)
    if [ "$validation_failed" = false ]; then
        if ! test_data_distribution; then
            validation_failed=true
        fi

        if ! test_read_write_performance; then
            validation_failed=true
        fi

        if ! test_failover; then
            validation_failed=true
        fi

        cleanup_test_data
    fi

    # Relatório final
    generate_report

    if [ "$validation_failed" = true ]; then
        log_error "=== Validação FALHOU - verifique os erros acima ==="
        exit 1
    else
        log_success "=== Validação do Redis Cluster CONCLUÍDA COM SUCESSO ==="
        exit 0
    fi
}

# Trap para limpeza em caso de erro
trap cleanup_test_data ERR

# Executar validação principal
main "$@"