#!/bin/bash
# Script para instalar e configurar cert-manager para gerenciar certificados TLS
# Necessário para admission webhooks (OPA Gatekeeper e Sigstore Policy Controller)

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
CERT_MANAGER_VERSION="v1.13.2"
CERT_MANAGER_NAMESPACE="cert-manager"
ENV="${ENV:-dev}"

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

# Verificar se cert-manager já está instalado
check_existing_installation() {
    log_info "Verificando instalação existente do cert-manager..."

    if kubectl get namespace "$CERT_MANAGER_NAMESPACE" &>/dev/null; then
        log_info "Namespace cert-manager já existe"

        # Verificar se pods estão rodando
        local running_pods=$(kubectl -n "$CERT_MANAGER_NAMESPACE" get pods --no-headers | grep Running | wc -l)
        if [[ "$running_pods" -ge 3 ]]; then
            log_success "cert-manager já está instalado e funcionando ($running_pods pods rodando)"
            return 0
        else
            log_warning "cert-manager instalado mas com problemas ($running_pods pods rodando)"
        fi
    else
        log_info "cert-manager não está instalado"
    fi

    return 1
}

# Instalar cert-manager via Helm ou manifests
install_cert_manager() {
    log_info "Instalando cert-manager versão $CERT_MANAGER_VERSION..."

    # Tentar instalar via Helm primeiro
    if command -v helm &> /dev/null; then
        log_info "Instalando cert-manager via Helm..."

        # Adicionar repositório do cert-manager
        helm repo add jetstack https://charts.jetstack.io
        helm repo update

        # Instalar cert-manager
        helm upgrade --install cert-manager jetstack/cert-manager \
            --namespace "$CERT_MANAGER_NAMESPACE" \
            --create-namespace \
            --version "$CERT_MANAGER_VERSION" \
            --set installCRDs=true \
            --set global.leaderElection.namespace="$CERT_MANAGER_NAMESPACE" \
            --set prometheus.enabled=true \
            --wait \
            --timeout=10m

        if [[ $? -eq 0 ]]; then
            log_success "cert-manager instalado via Helm com sucesso"
            return 0
        else
            log_warning "Falha na instalação via Helm, tentando via manifests..."
        fi
    fi

    # Fallback para instalação via manifests
    log_info "Instalando cert-manager via manifests..."

    # Aplicar CRDs
    kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VERSION/cert-manager.crds.yaml"

    # Aplicar cert-manager
    kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VERSION/cert-manager.yaml"

    log_success "cert-manager instalado via manifests"
    return 0
}

# Aguardar cert-manager ficar pronto
wait_for_cert_manager() {
    log_info "Aguardando cert-manager ficar pronto..."

    # Aguardar namespace
    kubectl wait --for=condition=ready namespace/"$CERT_MANAGER_NAMESPACE" --timeout=60s || true

    # Aguardar pods
    kubectl -n "$CERT_MANAGER_NAMESPACE" wait --for=condition=ready pod -l app.kubernetes.io/instance=cert-manager --timeout=300s

    # Verificar se webhooks estão funcionando
    log_info "Verificando webhooks do cert-manager..."
    if kubectl get validatingadmissionwebhooks | grep -q cert-manager-webhook; then
        log_success "✓ Webhook de validação configurado"
    else
        log_warning "Webhook de validação não encontrado"
    fi

    if kubectl get mutatingadmissionwebhooks | grep -q cert-manager-webhook; then
        log_success "✓ Webhook de mutação configurado"
    else
        log_warning "Webhook de mutação não encontrado"
    fi

    log_success "cert-manager está pronto"
}

# Criar ClusterIssuer para certificados self-signed (desenvolvimento)
create_selfsigned_cluster_issuer() {
    log_info "Criando ClusterIssuer self-signed para desenvolvimento..."

    cat << EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-cluster-issuer
  labels:
    neural-hive.io/component: cert-manager
    neural-hive.io/environment: $ENV
spec:
  selfSigned: {}
EOF

    # Aguardar ClusterIssuer ficar pronto
    kubectl wait --for=condition=ready clusterissuer/selfsigned-cluster-issuer --timeout=60s

    log_success "ClusterIssuer self-signed criado"
}

# Criar ClusterIssuer para Let's Encrypt (produção)
create_letsencrypt_cluster_issuer() {
    local email="${LETSENCRYPT_EMAIL:-admin@neural-hive.local}"

    log_info "Criando ClusterIssuer Let's Encrypt para produção..."

    cat << EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-cluster-issuer
  labels:
    neural-hive.io/component: cert-manager
    neural-hive.io/environment: production
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: $email
    privateKeySecretRef:
      name: letsencrypt-cluster-issuer-key
    solvers:
    - http01:
        ingress:
          class: istio
EOF

    # Aguardar ClusterIssuer ficar pronto
    kubectl wait --for=condition=ready clusterissuer/letsencrypt-cluster-issuer --timeout=60s || log_warning "ClusterIssuer Let's Encrypt pode não estar pronto"

    log_success "ClusterIssuer Let's Encrypt criado"
}

# Criar certificados para componentes de segurança
create_security_certificates() {
    log_info "Criando certificados para componentes de segurança..."

    # Certificado para OPA Gatekeeper webhook
    cat << EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: gatekeeper-webhook-cert
  namespace: gatekeeper-system
  labels:
    neural-hive.io/component: cert-manager
    neural-hive.io/service: opa-gatekeeper
spec:
  secretName: gatekeeper-webhook-server-cert
  duration: 8760h # 1 year
  renewBefore: 720h # 30 days
  subject:
    organizationalUnits:
    - neural-hive-security
  commonName: gatekeeper-webhook-service.gatekeeper-system.svc
  dnsNames:
  - gatekeeper-webhook-service.gatekeeper-system.svc
  - gatekeeper-webhook-service.gatekeeper-system.svc.cluster.local
  issuerRef:
    name: selfsigned-cluster-issuer
    kind: ClusterIssuer
    group: cert-manager.io
EOF

    # Sigstore Policy Controller webhook certificate is handled by Helm chart
    # The chart creates the certificate when tls.certManager is set to true
    log_info "Sigstore webhook certificate será gerenciado pelo Helm chart"

    log_success "Certificados para componentes de segurança criados"
}

# Validar instalação do cert-manager
validate_cert_manager() {
    log_info "Validando instalação do cert-manager..."

    # Verificar pods
    local pods_status=$(kubectl -n "$CERT_MANAGER_NAMESPACE" get pods -o jsonpath='{.items[*].status.phase}')
    if echo "$pods_status" | grep -q "Running"; then
        log_success "✓ Pods do cert-manager estão rodando"
    else
        log_error "Pods do cert-manager não estão rodando: $pods_status"
        return 1
    fi

    # Verificar CRDs
    local crds=("certificates.cert-manager.io" "clusterissuers.cert-manager.io" "issuers.cert-manager.io")
    for crd in "${crds[@]}"; do
        if kubectl get crd "$crd" &>/dev/null; then
            log_success "✓ CRD encontrado: $crd"
        else
            log_error "CRD não encontrado: $crd"
            return 1
        fi
    done

    # Testar criação de certificado
    log_info "Testando criação de certificado..."

    cat << EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: test-certificate
  namespace: default
spec:
  secretName: test-certificate-secret
  duration: 2160h # 90 days
  renewBefore: 360h # 15 days
  commonName: test.neural-hive.local
  dnsNames:
  - test.neural-hive.local
  issuerRef:
    name: selfsigned-cluster-issuer
    kind: ClusterIssuer
    group: cert-manager.io
EOF

    # Aguardar certificado ser emitido
    if kubectl wait --for=condition=ready certificate/test-certificate --timeout=60s; then
        log_success "✓ Teste de certificado bem-sucedido"
        kubectl delete certificate test-certificate || true
        kubectl delete secret test-certificate-secret || true
    else
        log_warning "Teste de certificado falhou"
    fi

    log_success "Validação do cert-manager concluída"
    return 0
}

# Gerar relatório de status
generate_status_report() {
    log_info "========================================"
    log_info "RELATÓRIO DE STATUS - CERT-MANAGER"
    log_info "========================================"

    # Status dos pods
    echo ""
    log_info "📋 PODS DO CERT-MANAGER:"
    kubectl -n "$CERT_MANAGER_NAMESPACE" get pods -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp

    # ClusterIssuers
    echo ""
    log_info "🔐 CLUSTER ISSUERS:"
    kubectl get clusterissuers -o custom-columns=NAME:.metadata.name,READY:.status.conditions[0].status,STATUS:.status.conditions[0].reason,AGE:.metadata.creationTimestamp

    # Certificados no cluster
    echo ""
    log_info "📜 CERTIFICADOS:"
    kubectl get certificates -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.conditions[0].status,SECRET:.spec.secretName,AGE:.metadata.creationTimestamp

    # Webhooks
    echo ""
    log_info "🎯 WEBHOOKS CONFIGURADOS:"
    kubectl get validatingadmissionwebhooks | grep cert-manager || log_info "Nenhum webhook de validação encontrado"
    kubectl get mutatingadmissionwebhooks | grep cert-manager || log_info "Nenhum webhook de mutação encontrado"

    echo ""
    log_success "Relatório de status gerado"
}

# Função principal
main() {
    log_info "=============================================="
    log_info "SETUP CERT-MANAGER PARA NEURAL HIVE-MIND"
    log_info "=============================================="
    log_info "Ambiente: $ENV"
    log_info "Versão: $CERT_MANAGER_VERSION"

    # Verificar se já está instalado
    if check_existing_installation; then
        log_info "cert-manager já está funcionando, pulando instalação"
    else
        # Instalar cert-manager
        install_cert_manager

        # Aguardar ficar pronto
        wait_for_cert_manager
    fi

    # Criar ClusterIssuers baseado no ambiente
    if [[ "$ENV" == "prod" || "$ENV" == "production" ]]; then
        create_letsencrypt_cluster_issuer
        create_selfsigned_cluster_issuer  # Também manter self-signed como fallback
    else
        create_selfsigned_cluster_issuer
    fi

    # Criar certificados para componentes de segurança (se os namespaces existirem)
    if kubectl get namespace gatekeeper-system &>/dev/null || kubectl get namespace cosign-system &>/dev/null; then
        create_security_certificates
    else
        log_info "Namespaces de segurança não encontrados, pulando criação de certificados"
    fi

    # Validar instalação
    validate_cert_manager

    # Gerar relatório
    generate_status_report

    log_success "=============================================="
    log_success "✅ CERT-MANAGER CONFIGURADO COM SUCESSO"
    log_success "Próximos passos:"
    log_info "1. Verificar certificados: kubectl get certificates -A"
    log_info "2. Monitorar renovações: kubectl -n $CERT_MANAGER_NAMESPACE logs -l app.kubernetes.io/instance=cert-manager"
    log_success "=============================================="
}

# Executar
main "$@"