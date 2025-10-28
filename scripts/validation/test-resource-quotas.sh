#!/bin/bash
#
# test-resource-quotas.sh
# Script para testar ResourceQuotas e LimitRanges do Neural Hive-Mind
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; ((TESTS_PASSED++)); }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; ((TESTS_FAILED++)); }
log_test() { echo -e "${BLUE}[TEST]${NC} $1"; ((TESTS_TOTAL++)); }

TEMP_DIR="/tmp/neuralhive-quota-test"
TEST_NAMESPACE="neural-hive-quota-test"

cleanup() {
    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
    [[ -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"
}

create_test_namespace() {
    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null

    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: $TEST_NAMESPACE
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: test-quota
  namespace: $TEST_NAMESPACE
spec:
  hard:
    requests.cpu: "1"
    requests.memory: "2Gi"
    limits.cpu: "2"
    limits.memory: "4Gi"
    persistentvolumeclaims: "2"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: test-limits
  namespace: $TEST_NAMESPACE
spec:
  limits:
  - default:
      cpu: "500m"
      memory: "1Gi"
    defaultRequest:
      cpu: "100m"
      memory: "256Mi"
    max:
      cpu: "1"
      memory: "2Gi"
    type: Container
EOF
}

test_quota_enforcement() {
    log_test "Teste 1: Enforcement de ResourceQuota"

    mkdir -p "$TEMP_DIR"

    # Pod que excede quota
    cat <<EOF > "$TEMP_DIR/exceed-quota-pod.yaml"
apiVersion: v1
kind: Pod
metadata:
  name: exceed-quota
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test
    image: nginx:alpine
    resources:
      requests:
        cpu: "2"
        memory: "5Gi"
  restartPolicy: Never
EOF

    if kubectl apply -f "$TEMP_DIR/exceed-quota-pod.yaml" &> /dev/null; then
        log_error "Pod que excede quota foi aceito"
        kubectl delete pod exceed-quota -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
        return 1
    else
        log_success "ResourceQuota bloqueou pod que excede limites"
        return 0
    fi
}

test_limitrange_defaults() {
    log_test "Teste 2: LimitRange aplica defaults"

    cat <<EOF > "$TEMP_DIR/default-pod.yaml"
apiVersion: v1
kind: Pod
metadata:
  name: default-resources
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test
    image: nginx:alpine
  restartPolicy: Never
EOF

    if kubectl apply -f "$TEMP_DIR/default-pod.yaml" &> /dev/null; then
        sleep 2
        local cpu_request
        cpu_request=$(kubectl get pod default-resources -n "$TEST_NAMESPACE" -o jsonpath='{.spec.containers[0].resources.requests.cpu}' 2>/dev/null || echo "")

        if [[ -n "$cpu_request" ]]; then
            log_success "LimitRange aplicou defaults automaticamente"
            kubectl delete pod default-resources -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
            return 0
        else
            log_error "LimitRange não aplicou defaults"
            kubectl delete pod default-resources -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
            return 1
        fi
    else
        log_error "Falha ao criar pod para teste de defaults"
        return 1
    fi
}

test_quota_usage() {
    log_test "Teste 3: Verificar uso de quota"

    local namespaces=("neural-hive-cognition" "neural-hive-orchestration" "neural-hive-execution" "neural-hive-observability")

    for ns in "${namespaces[@]}"; do
        if kubectl get namespace "$ns" &> /dev/null; then
            local quota_info
            quota_info=$(kubectl get resourcequota -n "$ns" -o jsonpath='{.items[0].status.used}' 2>/dev/null || echo "{}")

            if [[ "$quota_info" != "{}" ]]; then
                log_success "Quota ativa em $ns"
            else
                log_error "Quota não encontrada em $ns"
                return 1
            fi
        fi
    done

    return 0
}

test_pvc_limits() {
    log_test "Teste 4: Testar limites de PVC"

    # Tentar criar mais PVCs que o limite
    for i in {1..3}; do
        cat <<EOF | kubectl apply -f - &> /dev/null || true
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc-$i
  namespace: $TEST_NAMESPACE
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF
    done

    sleep 2
    local pvc_count
    pvc_count=$(kubectl get pvc -n "$TEST_NAMESPACE" --no-headers | wc -l)

    if [[ $pvc_count -le 2 ]]; then
        log_success "ResourceQuota limitou criação de PVCs"
        return 0
    else
        log_error "ResourceQuota não limitou PVCs adequadamente"
        return 1
    fi
}

test_namespace_quotas() {
    log_test "Teste 5: Verificar quotas por namespace"

    local namespaces=("neural-hive-cognition" "neural-hive-orchestration" "neural-hive-execution" "neural-hive-observability")
    local failures=0

    for ns in "${namespaces[@]}"; do
        if kubectl get namespace "$ns" &> /dev/null; then
            local quota_count
            quota_count=$(kubectl get resourcequota -n "$ns" --no-headers 2>/dev/null | wc -l || echo "0")

            if [[ $quota_count -gt 0 ]]; then
                log_success "ResourceQuota ativa em $ns"
            else
                log_error "ResourceQuota ausente em $ns"
                ((failures++))
            fi
        fi
    done

    [[ $failures -eq 0 ]]
}

generate_report() {
    echo
    log "=========================================="
    log "RELATÓRIO DE TESTES DE QUOTA"
    log "=========================================="
    echo
    log "Total de testes: $TESTS_TOTAL"
    log_success "Sucessos: $TESTS_PASSED"
    log_error "Falhas: $TESTS_FAILED"

    if [[ $TESTS_FAILED -eq 0 ]]; then
        log_success "🎉 TODOS OS TESTES DE QUOTA PASSARAM!"
        return 0
    else
        log_error "❌ ALGUNS TESTES FALHARAM"
        return 1
    fi
}

main() {
    log "Iniciando testes de ResourceQuotas e LimitRanges"

    trap cleanup EXIT

    create_test_namespace
    mkdir -p "$TEMP_DIR"

    test_quota_enforcement
    test_limitrange_defaults
    test_quota_usage
    test_pvc_limits
    test_namespace_quotas

    generate_report
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi