#!/bin/bash
# =============================================================================
# Neural Hive-Mind - Multi-Region Deploy Script
# =============================================================================
# Script para deploy multi-região com failover automático
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configurações
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

REGIONS=("us-east-1" "us-west-2" "eu-west-1")
CLUSTERS=("neural-hive-east" "neural-hive-west" "neural-hive-eu")
CONTEXTS=("neural-hive-east" "neural-hive-west" "neural-hive-eu")

NAMESPACE="neural-hive-mind"
TIMEOUT="${TIMEOUT:-600}"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# Funções Auxiliares
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    if ! command -v aws &> /dev/null; then
        log_error "awscli não encontrado"
        exit 1
    fi

    if ! command -v helm &> /dev/null; then
        log_error "helm não encontrado"
        exit 1
    fi

    log_info "Pré-requisitos OK"
}

# -----------------------------------------------------------------------------
# Terraform Deploy
# -----------------------------------------------------------------------------

deploy_terraform() {
    local region=$1
    local env_dir="${PROJECT_ROOT}/infrastructure/terraform/environments/prod-${region}"

    log_info "Deploy Terraform em ${region}..."

    cd "${env_dir}" || exit 1

    # Init
    terraform init \
        -backend-config="bucket=${TF_STATE_BUCKET:-neural-hive-mind-terraform-state}" \
        -backend-config="key=environments/prod-${region}/terraform.tfstate" \
        -backend-config="region=us-east-1" \
        -backend-config="encrypt=true" \
        -backend-config="dynamodb_table=neural-hive-mind-terraform-locks"

    # Validate
    terraform validate

    # Plan
    terraform plan -out=tfplan

    # Apply
    terraform apply -auto-approve tfplan

    # Outputs
    terraform output -json > outputs.json

    log_info "Terraform deploy concluído em ${region}"
}

# -----------------------------------------------------------------------------
# Kubernetes Context Setup
# -----------------------------------------------------------------------------

setup_contexts() {
    log_info "Configurando contexts Kubernetes..."

    for i in "${!REGIONS[@]}"; do
        local region="${REGIONS[$i]}"
        local cluster="${CLUSTERS[$i]}"

        log_info "Atualizando contexto para ${cluster} (${region})..."

        # Atualizar kubeconfig
        aws eks update-kubeconfig \
            --region "${region}" \
            --name "${cluster}" \
            --alias "${CONTEXTS[$i]}" \
            --profile "${AWS_PROFILE:-default}"

        # Criar namespace
        kubectl create namespace "${NAMESPACE}" --context="${CONTEXTS[$i]}" --dry-run=client -o yaml | \
            kubectl apply --context="${CONTEXTS[$i]}" -f -

        # Label nodes com região
        kubectl label nodes --context="${CONTEXTS[$i]}" \
            --all topology.kubernetes.io/zone="${region}" \
            --overwrite=true
    done

    log_info "Contexts configurados"
}

# -----------------------------------------------------------------------------
# Istio Multi-Cluster Setup
# -----------------------------------------------------------------------------

setup_istio_mesh() {
    log_info "Configurando Istio multi-cluster mesh..."

    # Instalar Istio no cluster primário
    log_info "Instalando Istio primário..."
    istioctl install \
        --context="${CONTEXTS[0]}" \
        --set profile=default \
        --set meshConfig.meshID=mesh1 \
        --set meshConfig.network=network1 \
        --set values.global.multiCluster.clusterName="${CLUSTERS[0]}" \
        --set values.gateways.istio-ingressgateway.type=LoadBalancer \
        -y

    # Instalar Istio remoto nos clusters secundários
    for i in 1 2; do
        log_info "Instalando Istio remoto em ${CLUSTERS[$i]}..."
        istioctl install \
            --context="${CONTEXTS[$i]}" \
            --set profile=remote \
            --set meshConfig.meshID=mesh1 \
            --set meshConfig.network="network$((i+1))" \
            --set values.global.multiCluster.clusterName="${CLUSTERS[$i]}" \
            -y
    done

    # Configurar secrets de mesh expansion
    log_info "Configurando mesh expansion..."
    for i in 1 2; do
        local secondary_context="${CONTEXTS[$i]}"
        local secret_name="istio-remote-secret-${REGIONS[$i]}"

        # Criar secret no cluster primário
        kubectl get secret --context="${secondary_context}" -n istio-system istio-ca-secret -o yaml | \
            kubectl apply --context="${CONTEXTS[0]}" -f -

        # Criar service account
        kubectl apply --context="${secondary_context}" -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: istio-multi-cluster
  namespace: istio-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: istio-multi-cluster
rules:
  - apiGroups: [""]
    resources: ["endpoints", "pods", "services"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: istio-multi-cluster
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: istio-multi-cluster
subjects:
  - kind: ServiceAccount
    name: istio-multi-cluster
    namespace: istio-system
EOF
    done

    log_info "Istio mesh configurado"
}

# -----------------------------------------------------------------------------
# Deploy Services
# -----------------------------------------------------------------------------

deploy_services() {
    local context=$1
    local region=$2

    log_info "Deploy services em ${region}..."

    # Deploy serviços core
    helm upgrade --install neural-hive-mind \
        "${PROJECT_ROOT}/helm-charts/neural-hive-mind" \
        --namespace "${NAMESPACE}" \
        --kube-context "${context}" \
        --set global.region="${region}" \
        --set global.clusterRole="primary" \
        --timeout "${TIMEOUT}s" \
        --wait \
        --debug

    # Deploy serviços específicos da região
    if [[ "${region}" == "eu-west-1" ]]; then
        # Deploy serviços de compliance GDPR
        helm upgrade --install nhm-gdpr-services \
            "${PROJECT_ROOT}/helm-charts/gdpr-services" \
            --namespace "${NAMESPACE}" \
            --kube-context "${context}" \
            --set compliance.gdpr.enabled=true \
            --timeout "${TIMEOUT}s"
    fi
}

# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------

health_check() {
    local context=$1
    local region=$2

    log_info "Verificando saúde em ${region}..."

    local ready_pods=0
    local total_pods=0

    while [[ $ready_pods -lt $total_pods || $total_pods -eq 0 ]]; do
        total_pods=$(kubectl get pods --context="${context}" -n "${NAMESPACE}" --no-headers | wc -l)
        ready_pods=$(kubectl get pods --context="${context}" -n "${NAMESPACE}" --no-headers | grep -c "Running" || echo "0")

        log_info "Pods em ${region}: ${ready_pods}/${total_pods} ready"

        if [[ $ready_pods -eq $total_pods && $total_pods -gt 0 ]]; then
            log_info "Todos os pods running em ${region}"
            break
        fi

        sleep 10
    done
}

# -----------------------------------------------------------------------------
# Failover Test
# -----------------------------------------------------------------------------

test_failover() {
    log_info "Testando failover..."

    # Simular falha no primário
    log_warn "Simulando falha no primário..."
    kubectl scale deployment --context="${CONTEXTS[0]}" \
        -n "${NAMESPACE}" gateway-intencoes --replicas=0

    sleep 30

    # Verificar se tráfego foi redirecionado
    local west_pods=$(kubectl get pods --context="${CONTEXTS[1]}" -n "${NAMESPACE}" -l app=gateway-intencoes --no-headers | wc -l)

    if [[ $west_pods -gt 0 ]]; then
        log_info "Failover funcionando: tráfego redirecionado para secondary"
    else
        log_error "Failover falhou"
    fi

    # Restaurar primário
    log_info "Restaurando primário..."
    kubectl scale deployment --context="${CONTEXTS[0]}" \
        -n "${NAMESPACE}" gateway-intencoes --replicas=3
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    local command=${1:-all}

    check_prerequisites

    case "${command}" in
        terraform)
            for region in "${REGIONS[@]}"; do
                deploy_terraform "${region}"
            done
            ;;
        contexts)
            setup_contexts
            ;;
        istio)
            setup_istio_mesh
            ;;
        deploy)
            for i in "${!REGIONS[@]}"; do
                deploy_services "${CONTEXTS[$i]}" "${REGIONS[$i]}"
                health_check "${CONTEXTS[$i]}" "${REGIONS[$i]}"
            done
            ;;
        health)
            for i in "${!REGIONS[@]}"; do
                health_check "${CONTEXTS[$i]}" "${REGIONS[$i]}"
            done
            ;;
        failover-test)
            test_failover
            ;;
        all)
            for region in "${REGIONS[@]}"; do
                deploy_terraform "${region}"
            done
            setup_contexts
            setup_istio_mesh
            for i in "${!REGIONS[@]}"; do
                deploy_services "${CONTEXTS[$i]}" "${REGIONS[$i]}"
                health_check "${CONTEXTS[$i]}" "${REGIONS[$i]}"
            done
            ;;
        *)
            echo "Uso: $0 {terraform|contexts|istio|deploy|health|failover-test|all}"
            exit 1
            ;;
    esac
}

main "$@"
