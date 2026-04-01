#!/bin/bash
# FluxCD Installation Script for Neural Hive-Mind
#
# Este script instala e configura o FluxCD para operações GitOps
# em ambientes de produção e desenvolvimento do Neural Hive-Mind.
#
# Uso:
#   ./install-fluxcd.sh [environment]
#
# Exemplos:
#   ./install-fluxcd.sh prod
#   ./install-fluxcd.sh dev

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de log
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

# Validações
validate_prerequisites() {
    log_info "Validando pré-requisitos..."

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale antes de continuar."
        exit 1
    fi

    # Verificar conexão com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes."
        exit 1
    fi

    # Verificar flux (instalar se necessário)
    if ! command -v flux &> /dev/null; then
        log_warning "flux CLI não encontrado. Instalando..."
        install_flux_cli
    fi

    log_success "Pré-requisitos validados."
}

# Instalar Flux CLI
install_flux_cli() {
    log_info "Instalando Flux CLI..."

    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -sL https://fluxcd.io/install.sh | sudo bash
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install fluxcd/tap/flux
    else
        log_error "Sistema operacional não suportado: $OSTYPE"
        exit 1
    fi

    log_success "Flux CLI instalado."
}

# Configurar variáveis de ambiente
setup_environment() {
    local env=${1:-prod}
    local cluster_name="neural-hive-${env}"
    local namespace="flux-system"
    local git_repo_url="ssh://git@github.com/albinoJimy/Neural-Hive-Mind.git"
    local branch="${env}"

    if [[ "$env" == "prod" ]]; then
        branch="main"
    fi

    log_info "Configurando ambiente: $env"
    log_info "  Cluster: $cluster_name"
    log_info "  Namespace: $namespace"
    log_info "  Git Branch: $branch"

    export CLUSTER_NAME="$cluster_name"
    export ENVIRONMENT="$env"
    export NAMESPACE="$namespace"
    export GIT_REPO_URL="$git_repo_url"
    export GIT_BRANCH="$branch"
}

# Criar segredos
create_secrets() {
    log_info "Criando segredos para FluxCD..."

    # Secret para SSH do GitHub
    log_info "Configurando segredo SSH do GitHub..."
    kubectl create secret generic neural-hive-mind-git-ssh \
        --namespace="${NAMESPACE}" \
        --from-file=identity="${HOME}/.ssh/id_rsa_flux" \
        --from-file=known_hosts="${HOME}/.ssh/known_hosts" \
        --dry-run=client -o yaml | kubectl apply -f -

    # Secret para GHCR (GitHub Container Registry)
    log_info "Configurando credenciais do GHCR..."
    if [[ -n "${GHCR_USERNAME:-}" ]] && [[ -n "${GHCR_PASSWORD:-}" ]]; then
        kubectl create secret docker-registry ghcr-credentials \
            --namespace="${NAMESPACE}" \
            --docker-server=ghcr.io \
            --docker-username="${GHCR_USERNAME}" \
            --docker-password="${GHCR_PASSWORD}" \
            --dry-run=client -o yaml | kubectl apply -f -
    else
        log_warning "Variáveis GHCR_USERNAME e GHCR_PASSWORD não definidas."
        log_warning "Configure manualmente: kubectl create secret docker-registry ghcr-credentials ..."
    fi

    # Secret para SOPS (se utilizado)
    if [[ -f "${HOME}/.sops/gpg_key.txt" ]]; then
        kubectl create secret generic sops-gpg \
            --namespace="${NAMESPACE}" \
            --from-file=sops.asc="${HOME}/.sops/gpg_key.txt" \
            --dry-run=client -o yaml | kubectl apply -f -
    fi

    log_success "Segredos criados."
}

# Instalar componentes do FluxCD
install_flux_components() {
    log_info "Instalando componentes do FluxCD no cluster..."

    local flux_dir="/home/jimy/NHM/Neural-Hive-Mind/infrastructure/fluxcd/clusters/${ENVIRONMENT}"

    # Verificar se diretório existe
    if [[ ! -d "$flux_dir" ]]; then
        log_error "Diretório ${flux_dir} não encontrado."
        exit 1
    fi

    # Aplicar manifests do FluxCD
    kubectl apply -k "${flux_dir}/flux-system"

    log_success "Componentes do FluxCD instalados."

    # Aguardar pods ficarem prontos
    log_info "Aguardando pods do FluxCD ficarem prontos..."
    kubectl wait --for=condition=ready pod -l "app.kubernetes.io/instance=flux-system" -n "${NAMESPACE}" --timeout=300s

    log_success "FluxCD está pronto."
}

# Verificar instalação
verify_installation() {
    log_info "Verificando instalação do FluxCD..."

    # Verificar componentes
    flux check --namespace "${NAMESPACE}"

    # Listar Kustomizations
    log_info "Kustomizations gerenciadas:"
    flux get kustomizations --namespace "${NAMESPACE}"

    # Listar HelmReleases
    log_info "HelmReleases gerenciadas:"
    flux get helmreleases --all-namespaces

    log_success "Instalação verificada."
}

# Habilitar automação de imagem
enable_image_automation() {
    log_info "Habilitando automação de imagem..."

    # Verificar ImageRepositories
    log_info "ImageRepositories configuradas:"
    flux get image repositories --namespace "${NAMESPACE}"

    # Verificar ImagePolicies
    log_info "ImagePolicies configuradas:"
    flux get image policies --namespace "${NAMESPACE}"

    log_success "Automação de imagem habilitada."
}

# Função principal
main() {
    local env="${1:-prod}"

    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  FluxCD Installation - Neural Hive-Mind                    ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""

    validate_prerequisites
    setup_environment "$env"
    create_secrets
    install_flux_components
    verify_installation
    enable_image_automation

    echo ""
    log_success "Instalação do FluxCD concluída com sucesso!"
    echo ""
    log_info "Próximos passos:"
    echo "  1. Monitore os syncs: flux get kustomizations --watch"
    echo "  2. Verifique os HelmReleases: flux get helmreleases --all-namespaces"
    echo "  3. Configure image automation: flux reconcile image update <name>"
    echo ""
}

# Executar
main "$@"
