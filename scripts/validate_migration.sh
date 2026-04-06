#!/bin/bash
# validate_migration.sh - Validação da migração etcd→Redis do Service Registry
#
# Uso: ./validate_migration.sh [namespace]
#
# Exemplo:
#   ./validate_migration.sh neural-hive           # Valida em namespace específico
#   ./validate_migration.sh                        # Usa namespace padrão

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
NAMESPACE="${1:-neural-hive}"
DEPLOYMENT_NAME="service-registry"
SERVICE_NAME="${DEPLOYMENT_NAME}"
TIMEOUT_SECONDS=300
ELAPSED=0
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# Funções de utilidade
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS_COUNT++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL_COUNT++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN_COUNT++))
}

log_header() {
    echo ""
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Verificar se kubectl está disponível
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Por favor instale kubectl."
        exit 1
    fi
}

# Verificar se grpcurl está disponível (opcional)
check_grpcurl() {
    if ! command -v grpcurl &> /dev/null; then
        log_warning "grpcurl não encontrado. Alguns testes serão pulados."
        return 1
    fi
    return 0
}

# 1. Verificar Deployments
check_deployments() {
    log_header "1. Verificando Deployments"

    local deployment
    deployment=$(kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")

    if [[ -z "${deployment}" ]]; then
        log_error "Deployment ${DEPLOYMENT_NAME} não encontrado no namespace ${NAMESPACE}"
        return 1
    fi

    log_success "Deployment ${DEPLOYMENT_NAME} encontrado"

    # Verificar replicas
    local replicas ready_replicas
    replicas=$(kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    ready_replicas=$(kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")

    if [[ "${ready_replicas}" -ge "${replicas}" ]]; then
        log_success "Replicas prontas: ${ready_replicas}/${replicas}"
    else
        log_error "Replicas insuficientes: ${ready_replicas}/${replicas} esperado"
        return 1
    fi

    # Verificar se pods estão running
    local pod_count ready_count
    pod_count=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" --no-headers 2>/dev/null | wc -l || echo "0")
    ready_count=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" --no-headers 2>/dev/null | grep -c "Running" || echo "0")

    if [[ "${pod_count}" -gt 0 && "${ready_count}" -eq "${pod_count}" ]]; then
        log_success "Todos os pods estão Running (${ready_count}/${pod_count})"
    else
        log_error "Pods não estão todos Running: ${ready_count}/${pod_count}"
        kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}"
        return 1
    fi

    # Verificar CrashLoopBackOff
    local crash_loops
    crash_loops=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" --no-headers 2>/dev/null | grep -c "CrashLoopBackOff" || echo "0")

    if [[ "${crash_loops}" -eq 0 ]]; then
        log_success "Nenhum pod em CrashLoopBackOff"
    else
        log_error "${crash_loops} pod(s) em CrashLoopBackOff"
        kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}"
        return 1
    fi
}

# 2. Verificar Logs
check_logs() {
    log_header "2. Verificando Logs"

    local errors warnings deprecation_warnings
    errors=$(kubectl logs -n "${NAMESPACE}" deployment/"${DEPLOYMENT_NAME}" --tail=100 2>/dev/null | grep -i "error" || echo "")
    warnings=$(kubectl logs -n "${NAMESPACE}" deployment/"${DEPLOYMENT_NAME}" --tail=100 2>/dev/null | grep -i "warning" | grep -v "deprecated" || echo "")
    deprecation_warnings=$(kubectl logs -n "${NAMESPACE}" deployment/"${DEPLOYMENT_NAME}" --tail=100 2>/dev/null | grep -i "deprecated" || echo "")

    if [[ -z "${errors}" ]]; then
        log_success "Nenhum erro encontrado nos logs (últimas 100 linhas)"
    else
        log_error "Erros encontrados nos logs:"
        echo "${errors}" | head -5
        return 1
    fi

    if [[ -z "${warnings}" ]]; then
        log_success "Nenhum warning crítico encontrado"
    else
        log_warning "Warnings encontrados (não-críticos):"
        echo "${warnings}" | head -3
    fi

    # Verificar warnings de deprecation (esperados na Fase 1)
    if [[ -n "${deprecation_warnings}" ]]; then
        if echo "${deprecation_warnings}" | grep -q "ETCD_"; then
            log_warning "Configs ETCD_* deprecated detectadas (esperado na Fase 1)"
            log_info "Planeje migração para REGISTRY_REDIS_* (ver docs/service-registry/MIGRATION_ETCD_TO_REDIS.md)"
        fi
    fi

    # Verificar se Redis client foi inicializado
    local redis_init
    redis_init=$(kubectl logs -n "${NAMESPACE}" deployment/"${DEPLOYMENT_NAME}" 2>/dev/null | grep "redis_registry_client_initialized" || echo "")

    if [[ -n "${redis_init}" ]]; then
        log_success "Cliente Redis inicializado corretamente"
        echo "${redis_init}" | tail -1 | sed 's/^/    /'
    else
        log_error "Cliente Redis não encontrado nos logs"
        return 1
    fi
}

# 3. Verificar ConfigMap
check_configmap() {
    log_header "3. Verificando ConfigMap"

    local configmap_name
    configmap_name=$(kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="config")].configMap.name}' 2>/dev/null || echo "")

    if [[ -z "${configmap_name}" ]]; then
        log_warning "Nenhum ConfigMap montado no deployment"
        return 0
    fi

    log_success "ConfigMap montado: ${configmap_name}"

    # Verificar configs antigas (ETCD_*)
    local has_etcd_configs
    has_etcd_configs=$(kubectl get configmap "${configmap_name}" -n "${NAMESPACE}" -o json 2>/dev/null | jq -r '.data | keys[] | select(startswith("ETCD_"))' | wc -l || echo "0")

    if [[ "${has_etcd_configs}" -gt 0 ]]; then
        log_warning "Configs ETCD_* encontradas (deprecated)"
        kubectl get configmap "${configmap_name}" -n "${NAMESPACE}" -o json 2>/dev/null | jq -r '.data | keys[] | select(startswith("ETCD_"))' | sed 's/^/    /'

        # Verificar se novas configs também existem
        local has_redis_configs
        has_redis_configs=$(kubectl get configmap "${configmap_name}" -n "${NAMESPACE}" -o json 2>/dev/null | jq -r '.data | keys[] | select(startswith("REGISTRY_REDIS_"))' | wc -l || echo "0")

        if [[ "${has_redis_configs}" -gt 0 ]]; then
            log_success "Configs REGISTRY_REDIS_* também presentes (prioridade será usada)"
        else
            log_warning "Apenas configs ETCD_* presentes (planeje migração)"
        fi
    else
        # Verificar configs novas
        local has_redis_configs
        has_redis_configs=$(kubectl get configmap "${configmap_name}" -n "${NAMESPACE}" -o json 2>/dev/null | jq -r '.data | keys[] | select(startswith("REGISTRY_REDIS_"))' | wc -l || echo "0")

        if [[ "${has_redis_configs}" -gt 0 ]]; then
            log_success "Configs REGISTRY_REDIS_* encontradas (migração completa)"
        else
            log_warning "Nenhuma config de registry encontrada (usando defaults)"
        fi
    fi
}

# 4. Verificar Health Check
check_health() {
    log_header "4. Verificando Health Check"

    # Verificar endpoints Kubernetes
    local endpoints
    endpoints=$(kubectl get endpoints "${SERVICE_NAME}" -n "${NAMESPACE}" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || echo "")

    if [[ -n "${endpoints}" ]]; then
        log_success "Endpoints Kubernetes encontrados"
    else
        log_error "Nenhum endpoint encontrado"
        return 1
    fi

    # Testar gRPC health check (se grpcurl disponível)
    if check_grpcurl; then
        local pod_name
        pod_name=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [[ -n "${pod_name}" ]]; then
            local grpc_health
            grpc_health=$(kubectl exec -n "${NAMESPACE}" "${pod_name}" -- grpcurl -plaintext localhost:8000 grpc.health.v1.Health/Check 2>/dev/null | grep -c "SERVING" || echo "0")

            if [[ "${grpc_health}" -eq 1 ]]; then
                log_success "gRPC health check passou (SERVING)"
            else
                log_error "gRPC health check falhou"
                return 1
            fi
        fi
    else
        log_warning "grpcurl não disponível, pulando teste gRPC"
    fi
}

# 5. Verificar Conectividade Redis
check_redis_connectivity() {
    log_header "5. Verificando Conectividade Redis"

    local pod_name
    pod_name=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "${pod_name}" ]]; then
        log_error "Nenhum pod encontrado para teste de conectividade"
        return 1
    fi

    # Verificar se Redis está acessível via Python
    local redis_check
    redis_check=$(kubectl exec -n "${NAMESPACE}" "${pod_name}" -- python -c "
import asyncio
import sys
sys.path.insert(0, '/app/src')
from src.clients.redis_registry_client import RedisRegistryClient

async def test():
    try:
        client = RedisRegistryClient(['redis:6379'], 'test', '', 5)
        await client.initialize()
        result = await client.health_check()
        await client.close()
        print('OK' if result else 'FAIL')
    except Exception as e:
        print(f'ERROR: {e}')

asyncio.run(test())
" 2>/dev/null || echo "")

    if [[ "${redis_check}" == *"OK"* ]]; then
        log_success "Conectividade Redis confirmada"
    else
        log_error "Falha na conectividade Redis: ${redis_check}"
        return 1
    fi
}

# 6. Verificar API gRPC
check_grpc_api() {
    log_header "6. Verificando API gRPC"

    if ! check_grpcurl; then
        log_warning "grpcurl não disponível, pulando teste de API"
        return 0
    fi

    local pod_name
    pod_name=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "${pod_name}" ]]; then
        log_error "Nenhum pod encontrado para teste de API"
        return 1
    fi

    # Listar serviços
    local services
    services=$(kubectl exec -n "${NAMESPACE}" "${pod_name}" -- grpcurl -plaintext localhost:8000 list 2>/dev/null || echo "")

    if echo "${services}" | grep -q "neural_hive.service_registry.v1"; then
        log_success "ServiceRegistry service disponível"
    else
        log_error "ServiceRegistry service não encontrado"
        return 1
    fi

    # Testar ListAgents
    local list_response
    list_response=$(kubectl exec -n "${NAMESPACE}" "${pod_name}" -- grpcurl -plaintext localhost:8000 neural_hive.service_registry.v1.ServiceRegistry/ListAgents 2>/dev/null || echo "")

    if echo "${list_response}" | grep -q "agents"; then
        log_success "ListAgents RPC funcionando"

        # Contar agentes
        local agent_count
        agent_count=$(echo "${list_response}" | jq -r '.agents | length' 2>/dev/null || echo "0")
        log_info "Agentes registrados: ${agent_count}"
    else
        log_error "ListAgents RPC falhou"
        return 1
    fi
}

# 7. Verificar Integração com Outros Serviços
check_integration() {
    log_header "7. Verificando Integração"

    # Verificar se worker-agents consegue registrar (verificar logs)
    local worker_logs
    worker_logs=$(kubectl logs -n "${NAMESPACE}" -l app=worker-agents --tail=20 2>/dev/null | grep -i "registered" || echo "")

    if [[ -n "${worker_logs}" ]]; then
        log_success "Worker agents registrando corretamente"
    else
        log_warning "Não foi possível confirmar registro de worker agents"
        log_info "Verifique manualmente: kubectl logs -n ${NAMESPACE} -l app=worker-agents"
    fi

    # Verificar queen-agent discovery
    local queen_logs
    queen_logs=$(kubectl logs -n "${NAMESPACE}" -l app=queen-agent --tail=20 2>/dev/null | grep -i "discovered.*worker" || echo "")

    if [[ -n "${queen_logs}" ]]; then
        log_success "Queen agent descobrindo workers"
    else
        log_warning "Não foi possível confirmar descoberta de workers pelo queen"
    fi
}

# 8. Verificar Métricas
check_metrics() {
    log_header "8. Verificando Métricas"

    local pod_name
    pod_name=$(kubectl get pods -n "${NAMESPACE}" -l app="${DEPLOYMENT_NAME}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "${pod_name}" ]]; then
        log_warning "Nenhum pod encontrado para teste de métricas"
        return 0
    fi

    # Verificar endpoint de métricas
    local metrics
    metrics=$(kubectl exec -n "${NAMESPACE}" "${pod_name}" -- curl -s http://localhost:9090/metrics 2>/dev/null || echo "")

    if [[ -n "${metrics}" ]]; then
        log_success "Endpoint de métricas respondendo"

        # Verificar métricas específicas
        if echo "${metrics}" | grep -q "registry_"; then
            log_success "Métricas do registry encontradas"
        fi

        if echo "${metrics}" | grep -q "redis_"; then
            log_success "Métricas do Redis encontradas"
        fi
    else
        log_warning "Endpoint de métricas não respondeu"
    fi
}

# Relatório final
print_summary() {
    log_header "Resumo da Validação"

    echo ""
    echo -e "  Verificações passadas: ${GREEN}${PASS_COUNT}${NC}"
    echo -e "  Avisos:               ${YELLOW}${WARN_COUNT}${NC}"
    echo -e "  Falhas:               ${RED}${FAIL_COUNT}${NC}"
    echo ""

    if [[ "${FAIL_COUNT}" -eq 0 ]]; then
        echo -e "${GREEN}=== Migração validada com sucesso ===${NC}"
        echo ""
        echo "Próximos passos:"
        echo "  1. Monitore os logs por 30 minutos: kubectl logs -f -n ${NAMESPACE} deployment/${DEPLOYMENT_NAME}"
        echo "  2. Verifique documentação: docs/service-registry/MIGRATION_ETCD_TO_REDIS.md"
        echo "  3. Planeje migração de configs ETCD_* → REGISTRY_REDIS_* (se ainda usando ETCD_*)"
        return 0
    else
        echo -e "${RED}=== Validação falhou ===${NC}"
        echo ""
        echo "Ações recomendadas:"
        echo "  1. Verifique os logs para entender as falhas"
        echo "  2. Consulte o plano de rollback: docs/service-registry/ROLLBACK_ETCD_TO_REDIS.md"
        echo "  3. Execute rollback se necessário: kubectl rollout undo -n ${NAMESPACE} deployment/${DEPLOYMENT_NAME}"
        return 1
    fi
}

# Main
main() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  Service Registry - Validação Migração etcd→Redis          ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "Namespace: ${NAMESPACE}"
    echo "Timeout: ${TIMEOUT_SECONDS}s"
    echo ""

    check_kubectl

    # Executar validações
    check_deployments || true
    check_logs || true
    check_configmap || true
    check_health || true
    check_redis_connectivity || true
    check_grpc_api || true
    check_integration || true
    check_metrics || true

    # Imprimir resumo
    print_summary
}

# Executar
main "$@"
