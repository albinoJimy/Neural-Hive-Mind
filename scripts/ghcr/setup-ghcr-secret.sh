#!/bin/bash
#===============================================================================
# setup-ghcr-secret.sh
# Configura o secret do GitHub Container Registry no cluster Kubernetes
#===============================================================================

set -euo pipefail

NAMESPACE="${NAMESPACE:-neural-hive}"
SECRET_NAME="ghcr-secret"

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

Configura o secret do GitHub Container Registry (GHCR) no cluster Kubernetes.

OPCOES:
    -u, --username <user>     GitHub username (obrigatorio)
    -t, --token <token>       GitHub Personal Access Token (obrigatorio)
    -e, --email <email>       Email (opcional)
    -n, --namespace <ns>      Namespace (padrao: neural-hive)
    --dry-run                 Apenas mostrar o que seria feito
    -h, --help                Mostrar ajuda

CRIANDO O TOKEN:
    1. Va para https://github.com/settings/tokens
    2. Clique em "Generate new token (classic)"
    3. Selecione os escopos:
       - read:packages (para pull de imagens)
       - write:packages (para push de imagens)
       - delete:packages (opcional)
    4. Copie o token gerado

EXEMPLOS:
    $0 -u meuusuario -t ghp_xxxxxxxxxxxx
    $0 -u meuusuario -t ghp_xxxxxxxxxxxx -n meu-namespace
    $0 -u meuusuario -t ghp_xxxxxxxxxxxx --dry-run

EOF
}

# Parse argumentos
GITHUB_USER=""
GITHUB_TOKEN=""
GITHUB_EMAIL=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--username)
            GITHUB_USER="$2"
            shift 2
            ;;
        -t|--token)
            GITHUB_TOKEN="$2"
            shift 2
            ;;
        -e|--email)
            GITHUB_EMAIL="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
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

# Validar argumentos obrigatorios
if [[ -z "$GITHUB_USER" || -z "$GITHUB_TOKEN" ]]; then
    log_error "Username e token sao obrigatorios"
    usage
    exit 1
fi

# Email padrao se nao fornecido
if [[ -z "$GITHUB_EMAIL" ]]; then
    GITHUB_EMAIL="${GITHUB_USER}@users.noreply.github.com"
fi

print_header "Configurando GHCR Secret"

log_info "GitHub User: $GITHUB_USER"
log_info "Email: $GITHUB_EMAIL"
log_info "Namespace: $NAMESPACE"
log_info "Secret Name: $SECRET_NAME"

# Verificar conexao com cluster
log_info "Verificando conexao com cluster..."
if ! kubectl cluster-info &> /dev/null; then
    log_error "Nao foi possivel conectar ao cluster"
    exit 1
fi
log_success "Conectado ao cluster"

# Verificar namespace
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_warn "Namespace $NAMESPACE nao existe"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Criaria namespace $NAMESPACE"
    else
        log_info "Criando namespace $NAMESPACE..."
        kubectl create namespace "$NAMESPACE"
    fi
fi

# Verificar se secret ja existe
if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &> /dev/null; then
    log_warn "Secret $SECRET_NAME ja existe no namespace $NAMESPACE"
    read -p "Deseja substituir? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Operacao cancelada"
        exit 0
    fi
    
    if [[ "$DRY_RUN" != "true" ]]; then
        kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE"
    fi
fi

# Criar secret
log_info "Criando secret..."

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Executaria:"
    echo "kubectl create secret docker-registry $SECRET_NAME \\"
    echo "  --docker-server=ghcr.io \\"
    echo "  --docker-username=$GITHUB_USER \\"
    echo "  --docker-password=<TOKEN> \\"
    echo "  --docker-email=$GITHUB_EMAIL \\"
    echo "  -n $NAMESPACE"
else
    kubectl create secret docker-registry "$SECRET_NAME" \
        --docker-server=ghcr.io \
        --docker-username="$GITHUB_USER" \
        --docker-password="$GITHUB_TOKEN" \
        --docker-email="$GITHUB_EMAIL" \
        -n "$NAMESPACE"
    
    log_success "Secret criado com sucesso!"
fi

# Verificar
if [[ "$DRY_RUN" != "true" ]]; then
    log_info "Verificando secret..."
    kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o yaml | head -20
fi

print_header "Proximos Passos"

echo ""
echo "1. Adicione imagePullSecrets aos seus deployments:"
echo ""
echo "   spec:"
echo "     template:"
echo "       spec:"
echo "         imagePullSecrets:"
echo "           - name: $SECRET_NAME"
echo ""
echo "2. Ou execute o script para atualizar todos os deployments:"
echo ""
echo "   ./scripts/ghcr/migrate-to-ghcr.sh"
echo ""
echo "3. Teste o pull de uma imagem:"
echo ""
echo "   kubectl run test-ghcr --rm -it --restart=Never \\"
echo "     --image=ghcr.io/$GITHUB_USER/neural-hive-mind/gateway-intencoes:latest \\"
echo "     --overrides='{\"spec\":{\"imagePullSecrets\":[{\"name\":\"$SECRET_NAME\"}]}}' \\"
echo "     -n $NAMESPACE -- echo 'Pull OK'"
echo ""

log_success "Setup concluido!"
