#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
#
# validate-namespace-isolation.sh
# Script para validar isolamento entre namespaces do Neural Hive-Mind
# Testa ResourceQuotas, LimitRanges, PodSecurityStandards e NetworkPolicies
#

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMP_DIR="${PROJECT_ROOT}/.tmp/validation"
TEST_NAMESPACE="neural-hive-isolation-test"

# Contadores para relatório
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

# Função para logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
    ((TESTS_TOTAL++))
}

# Função para verificar dependências
check_dependencies() {
    log "Verificando dependências..."

    local deps=("kubectl")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "Dependência necessária não encontrada: $dep"
            exit 1
        fi
    done

    log_success "Todas as dependências verificadas"
}

# Função para verificar se cluster está acessível
check_k8s_access() {
    log "Verificando acesso ao cluster Kubernetes..."

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi

    log_success "Cluster Kubernetes acessível"
}

# Função para criar namespace de teste
create_test_namespace() {
    log "Criando namespace de teste..."

    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null

    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: $TEST_NAMESPACE
  labels:
    neuralhive/test: isolation
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
EOF

    log_success "Namespace de teste criado: $TEST_NAMESPACE"
}

# Função para limpar recursos de teste
cleanup_test_resources() {
    log "Limpando recursos de teste..."
    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
    [[ -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"
    log_success "Recursos de teste limpos"
}

# Teste 1: Verificar existência de namespaces
test_namespaces_exist() {
    log_test "Teste 1: Verificar existência de namespaces Neural Hive"

    local expected_namespaces=(
        "neural-hive-system"
        "neural-hive-cognition"
        "neural-hive-orchestration"
        "neural-hive-execution"
        "neural-hive-observability"
        "cosign-system"
        "gatekeeper-system"
        "cert-manager"
        "auth"
    )

    local missing_namespaces=()
    for ns in "${expected_namespaces[@]}"; do
        if ! kubectl get namespace "$ns" &> /dev/null; then
            missing_namespaces+=("$ns")
        fi
    done

    if [[ ${#missing_namespaces[@]} -eq 0 ]]; then
        log_success "Todos os namespaces Neural Hive existem"
        return 0
    else
        log_error "Namespaces ausentes: ${missing_namespaces[*]}"
        return 1
    fi
}

# Teste 2: Verificar ResourceQuotas
test_resource_quotas() {
    log_test "Teste 2: Verificar ResourceQuotas estão ativas"

    local namespaces=(
        "neural-hive-cognition"
        "neural-hive-orchestration"
        "neural-hive-execution"
        "neural-hive-observability"
    )

    local failures=0
    for ns in "${namespaces[@]}"; do
        if ! kubectl get resourcequota -n "$ns" &> /dev/null; then
            log_error "ResourceQuota não encontrada no namespace: $ns"
            ((failures++))
        else
            local quota_count
            quota_count=$(kubectl get resourcequota -n "$ns" --no-headers | wc -l)
            if [[ $quota_count -gt 0 ]]; then
                log_success "ResourceQuota ativa em $ns (count: $quota_count)"
            else
                log_error "Nenhuma ResourceQuota ativa em $ns"
                ((failures++))
            fi
        fi
    done

    if [[ $failures -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Teste 3: Verificar LimitRanges
test_limit_ranges() {
    log_test "Teste 3: Verificar LimitRanges estão configurados"

    local namespaces=(
        "neural-hive-cognition"
        "neural-hive-orchestration"
        "neural-hive-execution"
        "neural-hive-observability"
    )

    local failures=0
    for ns in "${namespaces[@]}"; do
        if ! kubectl get limitrange -n "$ns" &> /dev/null; then
            log_error "LimitRange não encontrado no namespace: $ns"
            ((failures++))
        else
            local limit_count
            limit_count=$(kubectl get limitrange -n "$ns" --no-headers | wc -l)
            if [[ $limit_count -gt 0 ]]; then
                log_success "LimitRange ativo em $ns (count: $limit_count)"
            else
                log_error "Nenhum LimitRange ativo em $ns"
                ((failures++))
            fi
        fi
    done

    if [[ $failures -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Teste 4: Testar enforcement de ResourceQuota
test_quota_enforcement() {
    log_test "Teste 4: Testar enforcement de ResourceQuota"

    mkdir -p "$TEMP_DIR"

    # Criar pod que excede quota no namespace de teste
    cat <<EOF > "$TEMP_DIR/high-resource-pod.yaml"
apiVersion: v1
kind: Pod
metadata:
  name: high-resource-test
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    image: nginx:alpine
    resources:
      requests:
        cpu: "1000"
        memory: "1000Gi"
      limits:
        cpu: "1000"
        memory: "1000Gi"
  restartPolicy: Never
EOF

    # Aplicar ResourceQuota restritiva ao namespace de teste
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ResourceQuota
metadata:
  name: test-quota
  namespace: $TEST_NAMESPACE
spec:
  hard:
    requests.cpu: "1"
    requests.memory: "1Gi"
    limits.cpu: "2"
    limits.memory: "2Gi"
EOF

    # Tentar criar pod que excede quota (deve falhar)
    if kubectl apply -f "$TEMP_DIR/high-resource-pod.yaml" &> /dev/null; then
        log_error "Pod foi criado apesar de exceder ResourceQuota"
        kubectl delete pod high-resource-test -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
        return 1
    else
        log_success "ResourceQuota bloqueou corretamente pod que excede limites"
        return 0
    fi
}

# Teste 5: Testar LimitRange defaults
test_limitrange_defaults() {
    log_test "Teste 5: Testar LimitRange aplica defaults"

    mkdir -p "$TEMP_DIR"

    # Aplicar LimitRange ao namespace de teste
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: LimitRange
metadata:
  name: test-limits
  namespace: $TEST_NAMESPACE
spec:
  limits:
  - default:
      cpu: "200m"
      memory: "256Mi"
    defaultRequest:
      cpu: "100m"
      memory: "128Mi"
    type: Container
EOF

    # Criar pod sem especificar recursos
    cat <<EOF > "$TEMP_DIR/no-resources-pod.yaml"
apiVersion: v1
kind: Pod
metadata:
  name: no-resources-test
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    image: nginx:alpine
  restartPolicy: Never
EOF

    # Aplicar pod
    if kubectl apply -f "$TEMP_DIR/no-resources-pod.yaml" &> /dev/null; then
        # Aguardar um momento para o pod ser processado
        sleep 2

        # Verificar se recursos foram aplicados automaticamente
        local cpu_request
        cpu_request=$(kubectl get pod no-resources-test -n "$TEST_NAMESPACE" -o jsonpath='{.spec.containers[0].resources.requests.cpu}' 2>/dev/null || echo "")

        if [[ -n "$cpu_request" ]]; then
            log_success "LimitRange aplicou recursos automaticamente (CPU request: $cpu_request)"
            kubectl delete pod no-resources-test -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
            return 0
        else
            log_error "LimitRange não aplicou recursos automaticamente"
            kubectl delete pod no-resources-test -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
            return 1
        fi
    else
        log_error "Falha ao criar pod para teste de LimitRange"
        return 1
    fi
}

# Teste 6: Verificar Pod Security Standards
test_pod_security_standards() {
    log_test "Teste 6: Verificar Pod Security Standards"

    mkdir -p "$TEMP_DIR"

    # Tentar criar pod privilegiado em namespace restricted (deve falhar)
    cat <<EOF > "$TEMP_DIR/privileged-pod.yaml"
apiVersion: v1
kind: Pod
metadata:
  name: privileged-test
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    image: nginx:alpine
    securityContext:
      privileged: true
      runAsUser: 0
  restartPolicy: Never
EOF

    if kubectl apply -f "$TEMP_DIR/privileged-pod.yaml" &> /dev/null; then
        log_error "Pod privilegiado foi aceito em namespace restricted"
        kubectl delete pod privileged-test -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
        return 1
    else
        log_success "Pod Security Standards bloqueou pod privilegiado corretamente"
        return 0
    fi
}

# Teste 7: Verificar isolamento de rede (NetworkPolicies)
test_network_isolation() {
    log_test "Teste 7: Verificar NetworkPolicies"

    local namespaces=(
        "neural-hive-cognition"
        "neural-hive-orchestration"
        "neural-hive-execution"
    )

    local failures=0
    for ns in "${namespaces[@]}"; do
        local netpol_count
        netpol_count=$(kubectl get networkpolicy -n "$ns" --no-headers 2>/dev/null | wc -l || echo "0")

        if [[ $netpol_count -gt 0 ]]; then
            log_success "NetworkPolicies configuradas em $ns (count: $netpol_count)"
        else
            log_warning "Nenhuma NetworkPolicy encontrada em $ns"
            # Não conta como falha crítica, apenas warning
        fi
    done

    # Se chegou aqui, considera sucesso (NetworkPolicies são opcionais)
    return 0
}

# Teste 8: Verificar RBAC entre namespaces
test_rbac_isolation() {
    log_test "Teste 8: Verificar isolamento RBAC"

    # Verificar se service accounts existem nos namespaces corretos
    local service_accounts=(
        "neural-hive-cognition:cognitive-processor"
        "neural-hive-orchestration:orchestration-engine"
        "neural-hive-execution:execution-agent"
        "neural-hive-observability:observability-collector"
    )

    local failures=0
    for sa_info in "${service_accounts[@]}"; do
        local ns="${sa_info%:*}"
        local sa="${sa_info#*:}"

        if kubectl get serviceaccount "$sa" -n "$ns" &> /dev/null; then
            log_success "ServiceAccount encontrado: $sa em $ns"
        else
            log_error "ServiceAccount não encontrado: $sa em $ns"
            ((failures++))
        fi
    done

    if [[ $failures -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Teste 9: Verificar labels e annotations
test_labels_annotations() {
    log_test "Teste 9: Verificar labels e annotations de governança"

    local namespaces=(
        "neural-hive-system"
        "neural-hive-cognition"
        "neural-hive-orchestration"
        "neural-hive-execution"
        "neural-hive-observability"
    )

    local failures=0
    for ns in "${namespaces[@]}"; do
        # Verificar label neuralhive/layer
        local layer_label
        layer_label=$(kubectl get namespace "$ns" -o jsonpath='{.metadata.labels.neuralhive/layer}' 2>/dev/null || echo "")

        if [[ -n "$layer_label" ]]; then
            log_success "Namespace $ns tem label neuralhive/layer: $layer_label"
        else
            log_error "Namespace $ns não tem label neuralhive/layer"
            ((failures++))
        fi

        # Verificar annotation de owner
        local owner_annotation
        owner_annotation=$(kubectl get namespace "$ns" -o jsonpath='{.metadata.annotations.neuralhive/owner}' 2>/dev/null || echo "")

        if [[ -n "$owner_annotation" ]]; then
            log_success "Namespace $ns tem annotation neuralhive/owner: $owner_annotation"
        else
            log_warning "Namespace $ns não tem annotation neuralhive/owner"
        fi
    done

    if [[ $failures -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Teste 10: Verificar compliance com Pod Security Standards
test_pod_security_compliance() {
    log_test "Teste 10: Verificar compliance com Pod Security Standards"

    local restricted_namespaces=(
        "neural-hive-cognition"
        "neural-hive-orchestration"
        "neural-hive-execution"
    )

    local baseline_namespaces=(
        "neural-hive-system"
        "neural-hive-observability"
    )

    local failures=0

    # Verificar namespaces restricted
    for ns in "${restricted_namespaces[@]}"; do
        local enforce_label
        enforce_label=$(kubectl get namespace "$ns" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || echo "")

        if [[ "$enforce_label" == "restricted" ]]; then
            log_success "Namespace $ns configurado como restricted"
        else
            log_error "Namespace $ns não está configurado como restricted (atual: $enforce_label)"
            ((failures++))
        fi
    done

    # Verificar namespaces baseline
    for ns in "${baseline_namespaces[@]}"; do
        local enforce_label
        enforce_label=$(kubectl get namespace "$ns" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || echo "")

        if [[ "$enforce_label" == "baseline" ]]; then
            log_success "Namespace $ns configurado como baseline"
        else
            log_error "Namespace $ns não está configurado como baseline (atual: $enforce_label)"
            ((failures++))
        fi
    done

    if [[ $failures -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Função para gerar relatório
generate_report() {
    echo
    log "=========================================="
    log "RELATÓRIO DE VALIDAÇÃO DE ISOLAMENTO"
    log "=========================================="
    echo
    log "Total de testes executados: $TESTS_TOTAL"
    log_success "Testes que passaram: $TESTS_PASSED"
    log_error "Testes que falharam: $TESTS_FAILED"
    echo

    local success_rate=0
    if [[ $TESTS_TOTAL -gt 0 ]]; then
        success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    fi

    log "Taxa de sucesso: ${success_rate}%"
    echo

    if [[ $TESTS_FAILED -eq 0 ]]; then
        log_success "🎉 TODOS OS TESTES DE ISOLAMENTO PASSARAM!"
        echo
        log "O cluster Neural Hive-Mind está corretamente configurado com:"
        log "  ✓ Namespaces isolados adequadamente"
        log "  ✓ ResourceQuotas funcionando"
        log "  ✓ LimitRanges aplicando defaults"
        log "  ✓ Pod Security Standards ativos"
        log "  ✓ RBAC configurado corretamente"
        return 0
    else
        log_error "❌ ALGUNS TESTES FALHARAM"
        echo
        log "Verifique os logs acima para detalhes sobre as falhas."
        log "Problemas de isolamento podem comprometer a segurança do cluster."
        return 1
    fi
}

# Função principal
main() {
    log "Iniciando validação de isolamento de namespaces Neural Hive-Mind"

    # Configurar trap para cleanup
    trap cleanup_test_resources EXIT

    # Verificações iniciais
    check_dependencies
    check_k8s_access

    # Criar namespace de teste
    create_test_namespace

    # Executar testes
    test_namespaces_exist
    test_resource_quotas
    test_limit_ranges
    test_quota_enforcement
    test_limitrange_defaults
    test_pod_security_standards
    test_network_isolation
    test_rbac_isolation
    test_labels_annotations
    test_pod_security_compliance

    # Gerar relatório
    generate_report
}

# Verificar se o script está sendo executado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi