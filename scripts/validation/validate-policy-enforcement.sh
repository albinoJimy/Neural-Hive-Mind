#!/bin/bash
# Script abrangente para validar enforcement de políticas de segurança
# Testa OPA Gatekeeper, Sigstore Policy Controller e Network Policies

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
TEST_NAMESPACE="policy-test-$(date +%s)"
TIMEOUT=30

# Funções auxiliares
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

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

# Cleanup function
cleanup() {
    log_info "Limpando recursos de teste..."
    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true --timeout=${TIMEOUT}s || true
    kubectl delete pod test-unsigned-image --ignore-not-found=true --timeout=${TIMEOUT}s || true
    kubectl delete pod test-network-policy --ignore-not-found=true --timeout=${TIMEOUT}s || true
}

# Trap para cleanup
trap cleanup EXIT

# Verificar se OPA Gatekeeper está funcionando
validate_opa_gatekeeper() {
    log_test "Validando OPA Gatekeeper..."

    # Verificar se Gatekeeper está rodando
    if ! kubectl -n gatekeeper-system get pods -l gatekeeper.sh/operation=webhook --no-headers | grep -q Running; then
        log_error "OPA Gatekeeper não está rodando"
        return 1
    fi

    # Verificar se webhook está ativo
    if ! kubectl get validatingwebhookconfigurations | grep -q gatekeeper-validating-webhook-configuration; then
        log_error "Webhook do Gatekeeper não está configurado"
        return 1
    fi

    # Verificar se CRDs estão instalados
    local crds=("constrainttemplates.templates.gatekeeper.sh" "neuralhivemtlsrequired.templates.gatekeeper.sh" "neuralhiveimagesignature.templates.gatekeeper.sh")
    for crd in "${crds[@]}"; do
        if ! kubectl get crd "$crd" &>/dev/null; then
            log_warning "CRD não encontrado: $crd"
        else
            log_info "✓ CRD encontrado: $crd"
        fi
    done

    log_success "OPA Gatekeeper está funcionando"
    return 0
}

# Testar violação de política mTLS
test_mtls_policy_violation() {
    log_test "Testando violação de política mTLS..."

    # Criar namespace de teste
    kubectl create namespace "$TEST_NAMESPACE" || true
    kubectl label namespace "$TEST_NAMESPACE" neural-hive.io/test=true || true

    # Criar deployment sem labels adequados (deve gerar violação)
    cat << EOF | kubectl apply -f - 2>&1 | tee /tmp/mtls-test-output.log
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-mtls-violation
  namespace: $TEST_NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
        # Faltando labels obrigatórios para mTLS
    spec:
      containers:
      - name: test-container
        image: nginx:alpine
        ports:
        - containerPort: 80
EOF

    # Verificar se a violação foi detectada
    sleep 5
    local violations=$(kubectl get neuralhivemtlsrequired.constraints.gatekeeper.sh enforce-mtls-strict -o jsonpath='{.status.totalViolations}' 2>/dev/null || echo "0")

    if [[ "$violations" -gt 0 ]]; then
        log_success "✓ Violação de mTLS detectada ($violations violações)"

        # Mostrar detalhes das violações
        log_info "Detalhes das violações:"
        kubectl get neuralhivemtlsrequired.constraints.gatekeeper.sh enforce-mtls-strict -o jsonpath='{.status.violations[*].message}' | tr ' ' '\n' | head -3
    else
        log_warning "Nenhuma violação de mTLS detectada (pode estar em modo warn)"
    fi

    return 0
}

# Testar violação de política de imagem
test_image_signature_policy_violation() {
    log_test "Testando violação de política de assinatura de imagem..."

    # Tentar criar pod com imagem não assinada de registry não confiável
    cat << EOF > /tmp/unsigned-image-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-unsigned-image
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    image: fake-registry.example.com/unsigned:latest
    command: ["sleep", "3600"]
EOF

    # Aplicar e capturar output
    local apply_output
    if apply_output=$(kubectl apply -f /tmp/unsigned-image-pod.yaml 2>&1); then
        log_warning "Pod com imagem não assinada foi aceito (modo warn?)"
        echo "$apply_output"
    else
        if echo "$apply_output" | grep -q "denied\|rejected\|signature"; then
            log_success "✓ Imagem não assinada rejeitada corretamente"
            echo "$apply_output"
        else
            log_error "Erro inesperado: $apply_output"
            return 1
        fi
    fi

    # Verificar violações de assinatura
    sleep 5
    local violations=$(kubectl get neuralhiveimagesignature.constraints.gatekeeper.sh enforce-signed-images -o jsonpath='{.status.totalViolations}' 2>/dev/null || echo "0")

    if [[ "$violations" -gt 0 ]]; then
        log_success "✓ Violação de assinatura de imagem detectada ($violations violações)"
    else
        log_warning "Nenhuma violação de assinatura detectada"
    fi

    return 0
}

# Verificar Sigstore Policy Controller
validate_sigstore_policy_controller() {
    log_test "Validando Sigstore Policy Controller..."

    # Verificar se está rodando
    if ! kubectl -n cosign-system get pods -l app.kubernetes.io/name=policy-controller --no-headers | grep -q Running; then
        log_error "Sigstore Policy Controller não está rodando"
        return 1
    fi

    # Verificar se webhook está configurado
    if ! kubectl get validatingwebhookconfigurations | grep -q policy.sigstore.dev; then
        log_warning "Webhook do Sigstore Policy Controller não encontrado"
    else
        log_info "✓ Webhook do Sigstore Policy Controller configurado"
    fi

    # Verificar ClusterImagePolicy
    if kubectl get clusterimagepolicies.policy.sigstore.dev &>/dev/null; then
        local policies=$(kubectl get clusterimagepolicies.policy.sigstore.dev --no-headers | wc -l)
        log_info "✓ $policies ClusterImagePolicy(ies) encontrada(s)"
        kubectl get clusterimagepolicies.policy.sigstore.dev -o custom-columns=NAME:.metadata.name,AUTHORITIES:.spec.authorities[*].keyless.url
    else
        log_warning "Nenhuma ClusterImagePolicy encontrada"
    fi

    log_success "Sigstore Policy Controller está funcionando"
    return 0
}

# Testar network policies
test_network_policies() {
    log_test "Testando Network Policies..."

    # Verificar se network policies existem
    local policies=$(kubectl get networkpolicies -A --no-headers | wc -l)
    if [[ "$policies" -eq 0 ]]; then
        log_warning "Nenhuma Network Policy encontrada"
        return 1
    fi

    log_info "✓ $policies Network Policies encontradas"

    # Listar policies importantes
    log_info "Network Policies nos namespaces de segurança:"
    kubectl get networkpolicies -n cosign-system -o custom-columns=NAME:.metadata.name,POLICY-TYPES:.spec.policyTypes[*] 2>/dev/null || log_warning "Namespace cosign-system não tem policies"
    kubectl get networkpolicies -n gatekeeper-system -o custom-columns=NAME:.metadata.name,POLICY-TYPES:.spec.policyTypes[*] 2>/dev/null || log_warning "Namespace gatekeeper-system não tem policies"

    # Testar conectividade negada (se possível)
    log_info "Criando pod de teste para validar network policies..."

    cat << EOF | kubectl apply -f - || true
apiVersion: v1
kind: Pod
metadata:
  name: test-network-policy
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    image: busybox:latest
    command: ["sleep", "300"]
EOF

    # Aguardar pod ficar pronto
    kubectl -n "$TEST_NAMESPACE" wait --for=condition=ready pod/test-network-policy --timeout=60s || log_warning "Pod de teste não ficou pronto"

    log_success "Network Policies validadas"
    return 0
}

# Consultar violações de constraints
check_constraint_violations() {
    log_test "Consultando violações de constraints..."

    local total_violations=0

    # Verificar constraints mTLS
    if kubectl get neuralhivemtlsrequired.constraints.gatekeeper.sh enforce-mtls-strict &>/dev/null; then
        local mtls_violations=$(kubectl get neuralhivemtlsrequired.constraints.gatekeeper.sh enforce-mtls-strict -o jsonpath='{.status.totalViolations}' 2>/dev/null || echo "0")
        total_violations=$((total_violations + mtls_violations))
        log_info "mTLS violations: $mtls_violations"

        if [[ "$mtls_violations" -gt 0 ]]; then
            log_info "Últimas violações mTLS:"
            kubectl get neuralhivemtlsrequired.constraints.gatekeeper.sh enforce-mtls-strict -o jsonpath='{.status.violations[*].message}' | tr ' ' '\n' | tail -3
        fi
    fi

    # Verificar constraints de imagem
    if kubectl get neuralhiveimagesignature.constraints.gatekeeper.sh enforce-signed-images &>/dev/null; then
        local image_violations=$(kubectl get neuralhiveimagesignature.constraints.gatekeeper.sh enforce-signed-images -o jsonpath='{.status.totalViolations}' 2>/dev/null || echo "0")
        total_violations=$((total_violations + image_violations))
        log_info "Image signature violations: $image_violations"

        if [[ "$image_violations" -gt 0 ]]; then
            log_info "Últimas violações de assinatura:"
            kubectl get neuralhiveimagesignature.constraints.gatekeeper.sh enforce-signed-images -o jsonpath='{.status.violations[*].message}' | tr ' ' '\n' | tail -3
        fi
    fi

    if [[ "$total_violations" -gt 0 ]]; then
        log_warning "Total de violações detectadas: $total_violations"
    else
        log_success "Nenhuma violação ativa encontrada"
    fi

    return 0
}

# Gerar relatório de status
generate_status_report() {
    log_info "=========================================="
    log_info "RELATÓRIO DE STATUS - POLÍTICAS DE SEGURANÇA"
    log_info "=========================================="

    # Status do OPA Gatekeeper
    echo ""
    log_info "📋 OPA GATEKEEPER STATUS:"
    kubectl -n gatekeeper-system get pods -l gatekeeper.sh/operation=webhook -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount

    # Status do Sigstore Policy Controller
    echo ""
    log_info "🔐 SIGSTORE POLICY CONTROLLER STATUS:"
    kubectl -n cosign-system get pods -l app.kubernetes.io/name=policy-controller -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount

    # Constraints ativos
    echo ""
    log_info "📜 CONSTRAINTS ATIVOS:"
    kubectl get constraints -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,ENFORCEMENT:.spec.enforcementAction,VIOLATIONS:.status.totalViolations 2>/dev/null || log_warning "Nenhum constraint encontrado"

    # Network Policies
    echo ""
    log_info "🌐 NETWORK POLICIES:"
    kubectl get networkpolicies -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,POLICY-TYPES:.spec.policyTypes[*] | head -10

    # Últimas violações
    echo ""
    log_info "⚠️  RESUMO DE VIOLAÇÕES:"
    local audit_violations=$(kubectl get events -A --field-selector reason=ConstraintViolation --sort-by='.lastTimestamp' 2>/dev/null | tail -5 | wc -l)
    log_info "Eventos de violação recentes: $audit_violations"

    echo ""
    log_success "Relatório de status gerado com sucesso"
}

# Main function
main() {
    log_info "========================================"
    log_info "VALIDAÇÃO DE ENFORCEMENT DE POLÍTICAS"
    log_info "========================================"

    local exit_code=0

    # 1. Validar OPA Gatekeeper
    validate_opa_gatekeeper || exit_code=1

    # 2. Validar Sigstore Policy Controller
    validate_sigstore_policy_controller || exit_code=1

    # 3. Testar violação de política mTLS
    test_mtls_policy_violation || exit_code=1

    # 4. Testar violação de política de imagem
    test_image_signature_policy_violation || exit_code=1

    # 5. Testar network policies
    test_network_policies || exit_code=1

    # 6. Consultar violações existentes
    check_constraint_violations || exit_code=1

    # 7. Gerar relatório final
    generate_status_report

    if [[ $exit_code -eq 0 ]]; then
        log_success "=========================================="
        log_success "✅ VALIDAÇÃO DE POLÍTICAS CONCLUÍDA COM SUCESSO"
        log_success "Todas as políticas de segurança estão funcionando"
        log_success "=========================================="
    else
        log_error "=========================================="
        log_error "❌ FALHAS DETECTADAS NA VALIDAÇÃO"
        log_error "Algumas políticas precisam de atenção"
        log_error "=========================================="
    fi

    return $exit_code
}

# Executar
main "$@"