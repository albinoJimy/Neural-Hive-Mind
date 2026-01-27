#!/bin/bash
#===============================================================================
# setup-self-hosted-runner.sh
# Configura um GitHub Actions self-hosted runner no cluster Kubernetes
# Isso permite executar workflows sem consumir minutos do GitHub
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

NAMESPACE="github-runner"
REPO_URL="https://github.com/albinoJimy/Neural-Hive-Mind"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

print_header() {
    echo ""
    echo "=============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "=============================================================================="
}

usage() {
    cat <<EOF
Uso: $0 [OPCOES]

Configura um GitHub Actions self-hosted runner no cluster Kubernetes.

OPCOES:
    -t, --token <token>     Token de registro do runner (obrigatorio)
    -n, --namespace <ns>    Namespace (padrao: github-runner)
    --uninstall             Remover o runner
    -h, --help              Mostrar ajuda

OBTENDO O TOKEN:
    1. Va para https://github.com/albinoJimy/Neural-Hive-Mind/settings/actions/runners
    2. Clique em "New self-hosted runner"
    3. Selecione "Linux" e copie o token do comando ./config.sh
       (o token comeca com AAAA...)

EXEMPLOS:
    $0 -t AAAA_seu_token_aqui
    $0 --uninstall

EOF
}

RUNNER_TOKEN=""
UNINSTALL="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--token)
            RUNNER_TOKEN="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --uninstall)
            UNINSTALL="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Opcao desconhecida: $1"
            usage
            exit 1
            ;;
    esac
done

# Desinstalar
if [[ "$UNINSTALL" == "true" ]]; then
    print_header "Removendo GitHub Runner"
    kubectl delete namespace "$NAMESPACE" --ignore-not-found
    log_success "Runner removido"
    exit 0
fi

# Validar token
if [[ -z "$RUNNER_TOKEN" ]]; then
    log_error "Token do runner e obrigatorio"
    echo ""
    echo "Para obter o token:"
    echo "  1. Va para: $REPO_URL/settings/actions/runners"
    echo "  2. Clique em 'New self-hosted runner'"
    echo "  3. Copie o token do comando ./config.sh"
    echo ""
    usage
    exit 1
fi

print_header "Configurando GitHub Self-Hosted Runner"

log_info "Repositorio: $REPO_URL"
log_info "Namespace: $NAMESPACE"

# Verificar conexao com cluster
log_info "Verificando conexao com cluster..."
if ! kubectl cluster-info &> /dev/null; then
    log_error "Nao foi possivel conectar ao cluster"
    exit 1
fi
log_success "Conectado ao cluster"

# Criar namespace
log_info "Criando namespace..."
kubectl create namespace "$NAMESPACE" 2>/dev/null || true

# Criar secret com token
log_info "Criando secret com token..."
kubectl delete secret github-runner-secret -n "$NAMESPACE" 2>/dev/null || true
kubectl create secret generic github-runner-secret \
    --from-literal=RUNNER_TOKEN="$RUNNER_TOKEN" \
    -n "$NAMESPACE"

# Aplicar manifesto
log_info "Aplicando manifesto do runner..."
kubectl apply -f "$PROJECT_ROOT/k8s/github-runner/github-runner-deployment.yaml"

# Aguardar runner ficar pronto
log_info "Aguardando runner iniciar..."
kubectl wait --for=condition=available deployment/github-runner \
    -n "$NAMESPACE" --timeout=120s || {
        log_warn "Timeout aguardando runner. Verificando status..."
        kubectl get pods -n "$NAMESPACE"
        kubectl logs -n "$NAMESPACE" -l app=github-runner --tail=20
    }

print_header "Status do Runner"

kubectl get pods -n "$NAMESPACE"

echo ""
log_info "Para verificar os logs do runner:"
echo "  kubectl logs -f -n $NAMESPACE -l app=github-runner"
echo ""
log_info "O runner aparecera em:"
echo "  $REPO_URL/settings/actions/runners"
echo ""

# Verificar se runner registrou
sleep 10
POD_STATUS=$(kubectl get pods -n "$NAMESPACE" -l app=github-runner -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")

if [[ "$POD_STATUS" == "Running" ]]; then
    log_success "Runner iniciado com sucesso!"
    echo ""
    echo "Agora atualize seus workflows para usar o runner self-hosted:"
    echo ""
    echo "  jobs:"
    echo "    build:"
    echo "      runs-on: [self-hosted, linux, kubernetes, neural-hive]"
    echo ""
else
    log_warn "Runner em status: $POD_STATUS"
    log_info "Verifique os logs para mais detalhes"
fi
