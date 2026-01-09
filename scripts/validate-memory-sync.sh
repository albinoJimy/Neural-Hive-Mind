#!/bin/bash
# =============================================================================
# Valida sincronização MongoDB → ClickHouse
#
# Este script executa validação E2E do fluxo de sincronização:
# 1. Insere documento de teste no MongoDB
# 2. Aguarda processamento
# 3. Verifica se documento apareceu no ClickHouse
# 4. Valida integridade de dados
# 5. Limpa dados de teste
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configurações
NAMESPACE="${NAMESPACE:-memory-layer-api}"
MONGODB_POD="${MONGODB_POD:-mongodb-0}"
CLICKHOUSE_POD="${CLICKHOUSE_POD:-clickhouse-0}"
MEMORY_API_POD="${MEMORY_API_POD:-memory-layer-api-0}"
WAIT_SECONDS="${WAIT_SECONDS:-10}"
TEST_ID="sync-test-$(date +%s)"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    log_info "Limpando dados de teste..."

    # Remove do MongoDB
    kubectl exec -n "$NAMESPACE" "$MONGODB_POD" -- mongosh neural_hive --quiet --eval "
        db.operational_context.deleteMany({entity_id: '$TEST_ID'})
    " 2>/dev/null || true

    # Remove do ClickHouse
    kubectl exec -n clickhouse-cluster "$CLICKHOUSE_POD" -- clickhouse-client --query "
        ALTER TABLE neural_hive.operational_context_history DELETE WHERE entity_id = '$TEST_ID'
    " 2>/dev/null || true

    log_info "Cleanup concluído"
}

trap cleanup EXIT

main() {
    log_info "=== Validação de Sincronização Memory Layer ==="
    log_info "Test ID: $TEST_ID"
    echo ""

    # Step 1: Inserir documento de teste no MongoDB
    log_info "Step 1: Inserindo documento de teste no MongoDB..."

    kubectl exec -n "$NAMESPACE" "$MONGODB_POD" -- mongosh neural_hive --quiet --eval "
        db.operational_context.insertOne({
            entity_id: '$TEST_ID',
            data_type: 'context',
            content: 'E2E sync validation test',
            created_at: new Date(),
            metadata: {
                test: true,
                timestamp: $(date +%s)
            }
        })
    "

    if [ $? -ne 0 ]; then
        log_error "Falha ao inserir documento no MongoDB"
        exit 1
    fi
    log_info "Documento inserido com sucesso"

    # Step 2: Aguardar processamento
    log_info "Step 2: Aguardando ${WAIT_SECONDS}s para processamento..."
    sleep "$WAIT_SECONDS"

    # Step 3: Verificar se documento apareceu no ClickHouse
    log_info "Step 3: Verificando documento no ClickHouse..."

    CLICKHOUSE_COUNT=$(kubectl exec -n clickhouse-cluster "$CLICKHOUSE_POD" -- clickhouse-client --query "
        SELECT count() FROM neural_hive.operational_context_history WHERE entity_id = '$TEST_ID'
    " 2>/dev/null || echo "0")

    if [ "$CLICKHOUSE_COUNT" -eq "0" ]; then
        log_warn "Documento ainda não sincronizado (pode estar pendente no Kafka)"

        # Verificar métricas de lag
        log_info "Verificando consumer lag..."
        kubectl exec -n "$NAMESPACE" "$MEMORY_API_POD" -- curl -s localhost:8000/metrics 2>/dev/null | \
            grep memory_sync_consumer_lag || log_warn "Métricas não disponíveis"

        log_warn "Tente aumentar WAIT_SECONDS ou verificar logs do consumer"
        exit 1
    fi

    log_info "Documento encontrado no ClickHouse (count: $CLICKHOUSE_COUNT)"

    # Step 4: Validar integridade de dados
    log_info "Step 4: Validando integridade de dados..."

    CLICKHOUSE_DATA=$(kubectl exec -n clickhouse-cluster "$CLICKHOUSE_POD" -- clickhouse-client --query "
        SELECT entity_id, data_type FROM neural_hive.operational_context_history WHERE entity_id = '$TEST_ID' LIMIT 1 FORMAT TabSeparated
    " 2>/dev/null)

    ENTITY_ID=$(echo "$CLICKHOUSE_DATA" | cut -f1)
    DATA_TYPE=$(echo "$CLICKHOUSE_DATA" | cut -f2)

    if [ "$ENTITY_ID" != "$TEST_ID" ]; then
        log_error "entity_id não corresponde: esperado '$TEST_ID', obtido '$ENTITY_ID'"
        exit 1
    fi

    if [ "$DATA_TYPE" != "context" ]; then
        log_error "data_type não corresponde: esperado 'context', obtido '$DATA_TYPE'"
        exit 1
    fi

    log_info "Integridade validada com sucesso"

    # Step 5: Verificar métricas
    log_info "Step 5: Verificando métricas de sync..."

    METRICS=$(kubectl exec -n "$NAMESPACE" "$MEMORY_API_POD" -- curl -s localhost:8000/metrics 2>/dev/null || echo "")

    if [ -n "$METRICS" ]; then
        PUBLISHED=$(echo "$METRICS" | grep -E "^memory_sync_events_published_total" | awk '{print $2}' | head -1)
        CONSUMED=$(echo "$METRICS" | grep -E "^memory_sync_events_consumed_total" | awk '{print $2}' | head -1)

        if [ -n "$PUBLISHED" ] && [ -n "$CONSUMED" ]; then
            log_info "Eventos publicados: $PUBLISHED"
            log_info "Eventos consumidos: $CONSUMED"
        fi
    else
        log_warn "Não foi possível obter métricas"
    fi

    echo ""
    log_info "=== Validação E2E concluída com SUCESSO ==="
    echo ""
    echo "Resumo:"
    echo "  - MongoDB: documento inserido ✓"
    echo "  - Kafka: evento processado ✓"
    echo "  - ClickHouse: documento sincronizado ✓"
    echo "  - Integridade: dados validados ✓"
}

# Verificar se kubectl está disponível
if ! command -v kubectl &> /dev/null; then
    log_error "kubectl não encontrado no PATH"
    exit 1
fi

# Verificar conexão com cluster
if ! kubectl cluster-info &> /dev/null; then
    log_error "Não foi possível conectar ao cluster Kubernetes"
    exit 1
fi

main "$@"
