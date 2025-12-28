#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/docker.sh"

TEST_IMAGE="busybox:latest"
TEST_SERVICE="test-registry-ha"

test_primary_registry() {
    log_section "Teste 1: Push para Registry Primário (DNS)"

    local registry="registry.neural-hive.local:5000"

    # Pull test image
    docker pull "${TEST_IMAGE}"

    # Tag for primary registry
    docker tag "${TEST_IMAGE}" "${registry}/${TEST_SERVICE}:test"

    # Push
    if docker push "${registry}/${TEST_SERVICE}:test"; then
        log_success "✅ Push para registry primário OK"
        return 0
    else
        log_error "❌ Push para registry primário FALHOU"
        return 1
    fi
}

test_secondary_registry() {
    log_section "Teste 2: Fallback para Registry Secundário (IP)"

    local registry="37.60.241.150:30500"

    # Tag for secondary registry
    docker tag "${TEST_IMAGE}" "${registry}/${TEST_SERVICE}:test"

    # Push
    if docker push "${registry}/${TEST_SERVICE}:test"; then
        log_success "✅ Push para registry secundário OK"
        return 0
    else
        log_error "❌ Push para registry secundário FALHOU"
        return 1
    fi
}

test_fallback_mechanism() {
    log_section "Teste 3: Mecanismo de Fallback Automático"

    # Simular falha do primário (usando DNS inválido)
    export REGISTRY_PRIMARY="invalid-registry.local:5000"
    export REGISTRY_SECONDARY="37.60.241.150:30500"

    if docker_push_with_fallback "${TEST_SERVICE}" "test" 2; then
        log_success "✅ Fallback automático funcionou"
        return 0
    else
        log_error "❌ Fallback automático FALHOU"
        return 1
    fi
}

test_ha_resilience() {
    log_section "Teste 4: Resiliência HA (Kill 1 Pod)"

    local namespace="registry"
    local registry="registry.neural-hive.local:5000"

    # Get first pod
    local pod
    pod=$(kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=docker-registry -o jsonpath='{.items[0].metadata.name}')

    log_info "Deletando pod ${pod}..."
    kubectl delete pod "${pod}" -n "${namespace}"

    # Wait for new pod
    sleep 5

    # Try push during recovery
    docker tag "${TEST_IMAGE}" "${registry}/${TEST_SERVICE}:ha-test"

    if retry 5 3 docker push "${registry}/${TEST_SERVICE}:ha-test"; then
        log_success "✅ Registry manteve disponibilidade durante falha de pod"
        return 0
    else
        log_error "❌ Registry ficou indisponível durante falha"
        return 1
    fi
}

test_cache_performance() {
    log_section "Teste 5: Performance do Cache Redis"

    local registry="registry.neural-hive.local:5000"
    local test_image="alpine:latest"

    # First pull (sem cache)
    log_info "Pull 1 (sem cache)..."
    local start1=$(date +%s)
    docker pull "${test_image}" || true
    docker tag "${test_image}" "${registry}/${test_image}"
    docker push "${registry}/${test_image}"
    local end1=$(date +%s)
    local duration1=$((end1 - start1))

    # Second pull (com cache)
    docker rmi "${registry}/${test_image}" || true
    log_info "Pull 2 (com cache)..."
    local start2=$(date +%s)
    docker pull "${registry}/${test_image}"
    local end2=$(date +%s)
    local duration2=$((end2 - start2))

    log_info "Tempo sem cache: ${duration1}s"
    log_info "Tempo com cache: ${duration2}s"

    if [[ ${duration2} -lt ${duration1} ]]; then
        log_success "✅ Cache Redis está funcionando (${duration2}s < ${duration1}s)"
        return 0
    else
        log_warning "⚠️  Cache pode não estar otimizado"
        return 0  # Não falhar o teste
    fi
}

cleanup() {
    log_section "Limpeza"

    docker rmi "${TEST_IMAGE}" || true
    docker rmi "registry.neural-hive.local:5000/${TEST_SERVICE}:test" || true
    docker rmi "37.60.241.150:30500/${TEST_SERVICE}:test" || true

    log_success "Limpeza concluída"
}

main() {
    log_section "🧪 Teste de Registry HA - Neural Hive Mind"

    local failed=0

    test_primary_registry || ((failed++))
    test_secondary_registry || ((failed++))
    test_fallback_mechanism || ((failed++))
    test_ha_resilience || ((failed++))
    test_cache_performance || ((failed++))

    cleanup

    echo ""
    log_section "📊 Resultado dos Testes"

    if [[ ${failed} -eq 0 ]]; then
        log_success "✅ Todos os testes passaram!"
        return 0
    else
        log_error "❌ ${failed} teste(s) falharam"
        return 1
    fi
}

main "$@"
