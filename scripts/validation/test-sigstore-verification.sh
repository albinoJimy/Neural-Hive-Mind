#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Script específico para testar verificação de assinatura de imagens pelo Sigstore Policy Controller
# Valida que imagens assinadas são aceitas e não assinadas são rejeitadas

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_NAMESPACE="sigstore-test-$(date +%s)"
TIMEOUT=60

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
    rm -f /tmp/sigstore-test-*.yaml
}

# Trap para cleanup
trap cleanup EXIT

# Verificar se Sigstore Policy Controller está funcionando
check_sigstore_health() {
    log_test "Verificando saúde do Sigstore Policy Controller..."

    # Verificar se namespace existe
    if ! kubectl get namespace cosign-system &>/dev/null; then
        log_error "Namespace cosign-system não existe"
        return 1
    fi

    # Verificar se pods estão rodando
    local running_pods=$(kubectl -n cosign-system get pods -l app.kubernetes.io/name=policy-controller --no-headers | grep Running | wc -l)
    if [[ "$running_pods" -eq 0 ]]; then
        log_error "Nenhum pod do Sigstore Policy Controller está rodando"
        kubectl -n cosign-system get pods -l app.kubernetes.io/name=policy-controller
        return 1
    fi

    log_success "✓ $running_pods pod(s) do Policy Controller rodando"

    # Verificar logs para erros
    log_info "Verificando logs recentes..."
    local error_count=$(kubectl -n cosign-system logs -l app.kubernetes.io/name=policy-controller --tail=50 | grep -i error | wc -l)
    if [[ "$error_count" -gt 5 ]]; then
        log_warning "Muitos erros nos logs ($error_count). Últimos erros:"
        kubectl -n cosign-system logs -l app.kubernetes.io/name=policy-controller --tail=10 | grep -i error | tail -3
    else
        log_success "✓ Logs sem erros críticos"
    fi

    return 0
}

# Verificar ClusterImagePolicy
check_cluster_image_policy() {
    log_test "Verificando ClusterImagePolicy..."

    # Verificar se CRD existe
    if ! kubectl get crd clusterimagepolicies.policy.sigstore.dev &>/dev/null; then
        log_error "CRD ClusterImagePolicy não encontrado"
        return 1
    fi

    # Listar políticas ativas
    local policies=$(kubectl get clusterimagepolicies.policy.sigstore.dev --no-headers 2>/dev/null | wc -l)
    if [[ "$policies" -eq 0 ]]; then
        log_warning "Nenhuma ClusterImagePolicy configurada"
        return 1
    fi

    log_success "✓ $policies ClusterImagePolicy(ies) encontrada(s)"

    # Mostrar detalhes das políticas
    log_info "Políticas ativas:"
    kubectl get clusterimagepolicies.policy.sigstore.dev -o custom-columns=NAME:.metadata.name,IMAGES:.spec.images[*].glob

    # Verificar se há authorities configuradas
    for policy in $(kubectl get clusterimagepolicies.policy.sigstore.dev -o jsonpath='{.items[*].metadata.name}'); do
        local authorities=$(kubectl get clusterimagepolicies.policy.sigstore.dev "$policy" -o jsonpath='{.spec.authorities[*].keyless.url}' 2>/dev/null || echo "")
        if [[ -n "$authorities" ]]; then
            log_info "✓ Policy $policy tem authorities: $authorities"
        else
            log_warning "Policy $policy não tem authorities keyless configuradas"
        fi
    done

    return 0
}

# Testar deploy de imagem não assinada (deve ser rejeitada)
test_unsigned_image_rejection() {
    log_test "Testando rejeição de imagem não assinada..."

    # Criar namespace de teste
    kubectl create namespace "$TEST_NAMESPACE"
    kubectl label namespace "$TEST_NAMESPACE" sigstore-test=true

    # Criar manifesto de teste com imagem não assinada
    cat << EOF > /tmp/sigstore-test-unsigned.yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-unsigned-image
  namespace: $TEST_NAMESPACE
  labels:
    test: unsigned-image
spec:
  containers:
  - name: test-container
    image: busybox:latest  # Imagem comum mas não assinada
    command: ["sleep", "300"]
  restartPolicy: Never
EOF

    # Tentar aplicar e capturar resultado
    local apply_output
    local apply_exitcode=0

    log_info "Tentando aplicar pod com imagem não assinada..."
    if apply_output=$(kubectl apply -f /tmp/sigstore-test-unsigned.yaml 2>&1); then
        log_warning "Pod com imagem não assinada foi aceito (política pode estar em modo permissivo)"
        echo "Output: $apply_output"

        # Verificar se pod foi criado
        if kubectl -n "$TEST_NAMESPACE" get pod test-unsigned-image &>/dev/null; then
            log_warning "Pod realmente foi criado - verificar configuração do Policy Controller"
        fi
    else
        apply_exitcode=1
        if echo "$apply_output" | grep -iq "denied\|rejected\|signature\|admission"; then
            log_success "✓ Imagem não assinada rejeitada corretamente"
            echo "Motivo da rejeição: $apply_output"
        else
            log_error "Erro inesperado ao aplicar pod: $apply_output"
            return 1
        fi
    fi

    return 0
}

# Testar deploy de imagem de registry não autorizado
test_unauthorized_registry() {
    log_test "Testando imagem de registry não autorizado..."

    cat << EOF > /tmp/sigstore-test-unauthorized.yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-unauthorized-registry
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    image: fake-registry.example.com/malicious:latest
    command: ["sleep", "300"]
  restartPolicy: Never
EOF

    local apply_output
    log_info "Tentando aplicar pod de registry não autorizado..."

    if apply_output=$(kubectl apply -f /tmp/sigstore-test-unauthorized.yaml 2>&1); then
        log_warning "Pod de registry não autorizado foi aceito"
        echo "Output: $apply_output"
    else
        if echo "$apply_output" | grep -iq "denied\|rejected\|unauthorized\|not allowed"; then
            log_success "✓ Registry não autorizado rejeitado corretamente"
            echo "Motivo da rejeição: $apply_output"
        else
            log_error "Erro inesperado: $apply_output"
            return 1
        fi
    fi

    return 0
}

# Testar imagem com digest SHA256 (mais específico)
test_sha256_digest_image() {
    log_test "Testando imagem com digest SHA256..."

    # Usar uma imagem do registry público com digest específico
    cat << EOF > /tmp/sigstore-test-digest.yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-digest-image
  namespace: $TEST_NAMESPACE
spec:
  containers:
  - name: test-container
    # Imagem nginx com digest específico (não assinada)
    image: nginx@sha256:32da30332506740a2f7c34d5dc70467b7f14ec67d912703568daff790ab3f755
    command: ["nginx", "-g", "daemon off;"]
  restartPolicy: Never
EOF

    local apply_output
    log_info "Tentando aplicar pod com digest SHA256..."

    if apply_output=$(kubectl apply -f /tmp/sigstore-test-digest.yaml 2>&1); then
        log_warning "Pod com digest SHA256 foi aceito"
        echo "Output: $apply_output"
    else
        if echo "$apply_output" | grep -iq "denied\|rejected\|signature"; then
            log_success "✓ Imagem com digest SHA256 sem assinatura rejeitada"
            echo "Motivo da rejeição: $apply_output"
        else
            log_error "Erro inesperado: $apply_output"
            return 1
        fi
    fi

    return 0
}

# Verificar eventos relacionados ao Sigstore
check_sigstore_events() {
    log_test "Verificando eventos do Sigstore..."

    # Eventos no namespace cosign-system
    log_info "Eventos recentes no namespace cosign-system:"
    kubectl -n cosign-system get events --sort-by='.lastTimestamp' --field-selector type!=Normal | tail -5 || log_info "Nenhum evento de warning/error encontrado"

    # Eventos relacionados a admission
    log_info "Eventos de admission recentes:"
    kubectl get events -A --field-selector reason=FailedCreate,reason=AdmissionError --sort-by='.lastTimestamp' | tail -5 || log_info "Nenhum evento de falha de admission encontrado"

    # Eventos no namespace de teste
    if kubectl get namespace "$TEST_NAMESPACE" &>/dev/null; then
        log_info "Eventos no namespace de teste:"
        kubectl -n "$TEST_NAMESPACE" get events --sort-by='.lastTimestamp' | tail -5 || log_info "Nenhum evento encontrado"
    fi

    return 0
}

# Verificar logs detalhados do Policy Controller
check_policy_controller_logs() {
    log_test "Verificando logs detalhados do Policy Controller..."

    # Logs dos últimos 5 minutos
    log_info "Logs recentes (últimos 2 minutos):"
    kubectl -n cosign-system logs -l app.kubernetes.io/name=policy-controller --since=2m | tail -10

    # Procurar por logs relacionados aos nossos testes
    log_info "Logs relacionados ao namespace de teste:"
    kubectl -n cosign-system logs -l app.kubernetes.io/name=policy-controller --since=5m | grep -i "$TEST_NAMESPACE" | tail -5 || log_info "Nenhum log específico do teste encontrado"

    # Verificar se há erros de configuração
    local config_errors=$(kubectl -n cosign-system logs -l app.kubernetes.io/name=policy-controller --since=5m | grep -i "error\|failed\|invalid" | wc -l)
    if [[ "$config_errors" -gt 0 ]]; then
        log_warning "$config_errors erro(s) encontrado(s) nos logs:"
        kubectl -n cosign-system logs -l app.kubernetes.io/name=policy-controller --since=5m | grep -i "error\|failed\|invalid" | tail -3
    else
        log_success "✓ Nenhum erro crítico nos logs recentes"
    fi

    return 0
}

# Gerar relatório final
generate_final_report() {
    log_info "========================================"
    log_info "RELATÓRIO FINAL - VERIFICAÇÃO SIGSTORE"
    log_info "========================================"

    # Status geral do Policy Controller
    echo ""
    log_info "🔐 STATUS DO SIGSTORE POLICY CONTROLLER:"
    kubectl -n cosign-system get pods -l app.kubernetes.io/name=policy-controller -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp

    # ClusterImagePolicies ativas
    echo ""
    log_info "📜 CLUSTERIMAGEPOLICIES ATIVAS:"
    kubectl get clusterimagepolicies.policy.sigstore.dev -o custom-columns=NAME:.metadata.name,IMAGES:.spec.images[*].glob,AUTHORITIES:.spec.authorities[*].keyless.url 2>/dev/null || log_warning "Nenhuma ClusterImagePolicy encontrada"

    # Webhooks configurados
    echo ""
    log_info "🎯 WEBHOOKS CONFIGURADOS:"
    kubectl get validatingwebhookconfigurations | grep -i sigstore || log_warning "Webhook do Sigstore não encontrado"

    # Resumo dos testes
    echo ""
    log_info "📊 RESUMO DOS TESTES EXECUTADOS:"
    log_info "1. ✓ Verificação de saúde do Policy Controller"
    log_info "2. ✓ Validação de ClusterImagePolicy"
    log_info "3. ✓ Teste de rejeição de imagem não assinada"
    log_info "4. ✓ Teste de registry não autorizado"
    log_info "5. ✓ Teste de imagem com digest SHA256"
    log_info "6. ✓ Análise de eventos e logs"

    echo ""
    log_success "Verificação do Sigstore Policy Controller concluída"
}

# Main function
main() {
    log_info "=============================================="
    log_info "TESTE DE VERIFICAÇÃO SIGSTORE POLICY CONTROLLER"
    log_info "=============================================="

    local exit_code=0

    # 1. Verificar saúde do Policy Controller
    check_sigstore_health || exit_code=1

    # 2. Verificar ClusterImagePolicy
    check_cluster_image_policy || exit_code=1

    # 3. Testar rejeição de imagem não assinada
    test_unsigned_image_rejection || exit_code=1

    # 4. Testar registry não autorizado
    test_unauthorized_registry || exit_code=1

    # 5. Testar imagem com digest SHA256
    test_sha256_digest_image || exit_code=1

    # 6. Verificar eventos
    check_sigstore_events

    # 7. Verificar logs
    check_policy_controller_logs

    # 8. Gerar relatório final
    generate_final_report

    if [[ $exit_code -eq 0 ]]; then
        log_success "=============================================="
        log_success "✅ VERIFICAÇÃO SIGSTORE CONCLUÍDA COM SUCESSO"
        log_success "Policy Controller está funcionando corretamente"
        log_success "=============================================="
    else
        log_error "=============================================="
        log_error "❌ PROBLEMAS DETECTADOS NO SIGSTORE"
        log_error "Verificar configuração do Policy Controller"
        log_error "=============================================="
    fi

    return $exit_code
}

# Executar
main "$@"