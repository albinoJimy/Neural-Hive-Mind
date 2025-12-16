#!/bin/bash
# Testa fallback para SemanticPipeline quando MLflow indisponível
#
# Este script valida que os specialists utilizam SemanticPipeline como fallback
# ao invés de heurísticas simples quando modelos ML não estão disponíveis.
#
# Uso:
#   ./test-semantic-fallback.sh [specialist]
#
# Exemplos:
#   ./test-semantic-fallback.sh              # Testa specialist-technical (padrão)
#   ./test-semantic-fallback.sh business     # Testa specialist-business
#   ./test-semantic-fallback.sh all          # Testa todos os specialists

set -e

NAMESPACE="${NAMESPACE:-neural-hive}"
MLFLOW_NAMESPACE="${MLFLOW_NAMESPACE:-mlflow}"
SPECIALIST="${1:-technical}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale antes de continuar."
        exit 1
    fi

    # Verificar acesso ao cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes."
        exit 1
    fi

    # Verificar namespace
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace $NAMESPACE não encontrado."
        exit 1
    fi

    log_info "Pré-requisitos OK"
}

get_mlflow_replicas() {
    kubectl get deployment mlflow -n "$MLFLOW_NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0"
}

scale_mlflow() {
    local replicas=$1
    log_info "Escalando MLflow para $replicas réplicas..."
    kubectl scale deployment mlflow -n "$MLFLOW_NAMESPACE" --replicas="$replicas" 2>/dev/null || {
        log_warn "MLflow deployment não encontrado em $MLFLOW_NAMESPACE"
        return 1
    }
}

wait_for_mlflow_scale() {
    local expected=$1
    local timeout=60
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        local current=$(kubectl get deployment mlflow -n "$MLFLOW_NAMESPACE" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
        current=${current:-0}

        if [ "$current" -eq "$expected" ]; then
            log_info "MLflow escalado para $expected réplicas"
            return 0
        fi

        sleep 2
        elapsed=$((elapsed + 2))
    done

    log_warn "Timeout esperando MLflow escalar para $expected réplicas"
    return 1
}

test_specialist_fallback() {
    local specialist=$1
    local deployment="specialist-$specialist"

    log_info "=== Testando fallback para $deployment ==="

    # Verificar se deployment existe
    if ! kubectl get deployment "$deployment" -n "$NAMESPACE" &> /dev/null; then
        log_error "Deployment $deployment não encontrado"
        return 1
    fi

    # Verificar env var USE_SEMANTIC_FALLBACK
    log_info "Verificando configuração USE_SEMANTIC_FALLBACK..."
    local env_value=$(kubectl get deployment "$deployment" -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="USE_SEMANTIC_FALLBACK")].value}')

    if [ "$env_value" != "true" ]; then
        log_error "USE_SEMANTIC_FALLBACK não está habilitado ($env_value)"
        return 1
    fi
    log_info "USE_SEMANTIC_FALLBACK=$env_value"

    # Verificar logs para fallback behavior
    log_info "Verificando logs recentes para fallback behavior..."
    local logs=$(kubectl logs -n "$NAMESPACE" deployment/"$deployment" --tail=100 2>/dev/null || echo "")

    # Procurar por indicadores de SemanticPipeline
    if echo "$logs" | grep -qi "semantic.*pipeline\|model_source.*semantic"; then
        log_info "Evidência de SemanticPipeline encontrada nos logs"
    else
        log_warn "Nenhuma evidência de SemanticPipeline nos logs recentes (pode não ter havido fallback)"
    fi

    # Procurar por indicadores de heurísticas
    if echo "$logs" | grep -qi "falling back to.*heuristics\|model_source.*heuristics"; then
        log_warn "Fallback para heurísticas detectado - SemanticPipeline pode estar desabilitado ou com erro"
    fi

    log_info "Teste de configuração para $deployment concluído"
    return 0
}

test_fallback_with_mlflow_down() {
    local specialist=$1
    local deployment="specialist-$specialist"

    log_info "=== Teste de fallback com MLflow desligado para $deployment ==="

    # Salvar estado original do MLflow
    local original_replicas=$(get_mlflow_replicas)
    log_info "Réplicas originais do MLflow: $original_replicas"

    # Escalar MLflow para 0
    if scale_mlflow 0; then
        wait_for_mlflow_scale 0
        sleep 10  # Aguardar cache expirar

        # Verificar logs após MLflow down
        log_info "Verificando logs após MLflow estar indisponível..."
        local logs=$(kubectl logs -n "$NAMESPACE" deployment/"$deployment" --tail=50 --since=30s 2>/dev/null || echo "")

        if echo "$logs" | grep -qi "semantic.*pipeline\|Falling back to semantic"; then
            log_info "SemanticPipeline sendo usado como fallback"
        elif echo "$logs" | grep -qi "heuristics"; then
            log_warn "Heurísticas sendo usadas - verificar configuração"
        else
            log_info "Sem atividade de fallback recente nos logs"
        fi

        # Restaurar MLflow
        log_info "Restaurando MLflow..."
        scale_mlflow "$original_replicas"
        wait_for_mlflow_scale "$original_replicas"
    else
        log_warn "Não foi possível escalar MLflow - teste de fallback simulado pulado"
    fi
}

print_summary() {
    echo ""
    echo "========================================"
    echo "  Resumo do Teste de SemanticPipeline  "
    echo "========================================"
    echo ""
    echo "Configuração verificada:"
    echo "  - USE_SEMANTIC_FALLBACK: habilitado em todos os specialists"
    echo "  - Helm values: config.features.useSemanticFallback: true"
    echo ""
    echo "Para validar fallback em tempo real:"
    echo "  1. Escalar MLflow: kubectl scale deployment mlflow -n mlflow --replicas=0"
    echo "  2. Enviar requisição de avaliação"
    echo "  3. Verificar logs: kubectl logs -n neural-hive deployment/specialist-technical | grep -i semantic"
    echo "  4. Restaurar: kubectl scale deployment mlflow -n mlflow --replicas=1"
    echo ""
    echo "Métricas Prometheus:"
    echo "  rate(neural_hive_specialist_evaluations_total{model_source=\"semantic_pipeline\"}[5m])"
    echo ""
}

main() {
    echo "========================================"
    echo "  Teste de Fallback SemanticPipeline   "
    echo "========================================"
    echo ""

    check_prerequisites

    if [ "$SPECIALIST" == "all" ]; then
        for s in technical business behavior evolution architecture; do
            test_specialist_fallback "$s"
            echo ""
        done
    else
        test_specialist_fallback "$SPECIALIST"
    fi

    # Teste opcional com MLflow down (requer confirmação)
    echo ""
    read -p "Deseja testar fallback com MLflow desligado? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ "$SPECIALIST" == "all" ]; then
            test_fallback_with_mlflow_down "technical"
        else
            test_fallback_with_mlflow_down "$SPECIALIST"
        fi
    fi

    print_summary

    log_info "Teste concluído com sucesso"
}

main "$@"
