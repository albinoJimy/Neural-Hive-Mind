#!/bin/bash

# deploy-memory-layer.sh
# Script de orquestração completa da camada de memória neural
# Implanta Redis Cluster, Keycloak OAuth2, políticas OPA e monitoramento

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurações
NAMESPACE_REDIS="redis-cluster"
NAMESPACE_KEYCLOAK="auth"
NAMESPACE_OPA="gatekeeper-system"
NAMESPACE_APP="gateway-intencoes"
HELM_TIMEOUT="10m"

# Funções utilitárias
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

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale o kubectl primeiro."
        exit 1
    fi

    # Verificar helm
    if ! command -v helm &> /dev/null; then
        log_error "helm não encontrado. Instale o Helm primeiro."
        exit 1
    fi

    # Verificar terraform
    if ! command -v terraform &> /dev/null; then
        log_error "terraform não encontrado. Instale o Terraform primeiro."
        exit 1
    fi

    # Verificar conexão com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes"
        exit 1
    fi

    log_success "Pré-requisitos verificados com sucesso"
}

create_namespaces() {
    log_info "Criando namespaces necessários..."

    local namespaces=($NAMESPACE_REDIS $NAMESPACE_KEYCLOAK $NAMESPACE_OPA $NAMESPACE_APP)

    for ns in "${namespaces[@]}"; do
        if kubectl get namespace "$ns" &> /dev/null; then
            log_warning "Namespace $ns já existe"
        else
            kubectl create namespace "$ns"
            log_success "Namespace $ns criado"
        fi

        # Adicionar labels para Istio injection
        kubectl label namespace "$ns" istio-injection=enabled --overwrite=true
    done
}

deploy_redis_operator() {
    log_info "Implantando Redis Operator..."

    # Adicionar repositório Helm do Redis Operator
    helm repo add ot-helm https://ot-container-kit.github.io/helm-charts/
    helm repo update

    # Instalar Redis Operator
    if helm list -n $NAMESPACE_REDIS | grep -q redis-operator; then
        log_warning "Redis Operator já está instalado"
    else
        helm install redis-operator ot-helm/redis-operator \
            --namespace $NAMESPACE_REDIS \
            --create-namespace \
            --wait \
            --timeout $HELM_TIMEOUT
        log_success "Redis Operator instalado"
    fi

    # Aguardar operator estar pronto
    kubectl wait --for=condition=available --timeout=300s deployment/redis-operator -n $NAMESPACE_REDIS
}

deploy_redis_cluster() {
    log_info "Implantando Redis Cluster..."

    # Aplicar configuração do cluster
    kubectl apply -f /home/jimy/Base/Neural-Hive-Mind/helm-charts/redis-cluster/templates/redis-cluster.yaml -n $NAMESPACE_REDIS

    # Aguardar cluster estar pronto
    log_info "Aguardando Redis Cluster estar pronto..."
    sleep 30

    # Verificar status do cluster
    for i in {1..12}; do
        if kubectl get rediscluster neural-hive-cluster -n $NAMESPACE_REDIS -o jsonpath='{.status.readyReplicas}' | grep -q "6"; then
            log_success "Redis Cluster está pronto"
            break
        elif [ $i -eq 12 ]; then
            log_error "Timeout aguardando Redis Cluster"
            exit 1
        else
            log_info "Aguardando Redis Cluster... (tentativa $i/12)"
            sleep 15
        fi
    done
}

deploy_keycloak() {
    log_info "Verificando Keycloak gerenciado pelo Terraform..."

    # Keycloak é gerenciado pelo Terraform, apenas verificar se está rodando
    log_info "Aguardando deployment do Keycloak estar pronto..."
    if kubectl wait --for=condition=available --timeout=600s deployment/neural-hive-keycloak -n $NAMESPACE_KEYCLOAK 2>/dev/null; then
        log_success "Keycloak está disponível"
    else
        log_warning "Keycloak não encontrado. Certifique-se de que o módulo Terraform foi aplicado."
        log_info "Execute: terraform apply -target=module.keycloak"
    fi
}

deploy_opa_gatekeeper() {
    log_info "Implantando OPA Gatekeeper..."

    # Adicionar repositório Helm do Gatekeeper
    helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
    helm repo update

    # Instalar OPA Gatekeeper
    if helm list -n $NAMESPACE_OPA | grep -q gatekeeper; then
        log_warning "OPA Gatekeeper já está instalado"
    else
        helm install gatekeeper gatekeeper/gatekeeper \
            --namespace $NAMESPACE_OPA \
            --create-namespace \
            --wait \
            --timeout $HELM_TIMEOUT
        log_success "OPA Gatekeeper instalado"
    fi

    # Aguardar Gatekeeper estar pronto
    kubectl wait --for=condition=available --timeout=300s deployment/gatekeeper-controller-manager -n $NAMESPACE_OPA

    # Aplicar CRDs de governança de dados
    log_info "Aplicando CRDs de governança..."
    kubectl apply -f /home/jimy/Base/Neural-Hive-Mind/k8s/bootstrap/data-governance-crds.yaml

    # Aplicar templates e constraints OPA
    log_info "Aplicando constraint templates OPA..."
    kubectl apply -f /home/jimy/Base/Neural-Hive-Mind/policies/constraint-templates/ --recursive

    log_info "Aplicando constraints OPA..."
    kubectl apply -f /home/jimy/Base/Neural-Hive-Mind/policies/constraints/ --recursive
}

deploy_istio_policies() {
    log_info "Aplicando políticas de autenticação Istio..."

    # Aplicar políticas de autenticação Istio
    kubectl apply -f /home/jimy/Base/Neural-Hive-Mind/k8s/bootstrap/istio-auth-policies.yaml -n $NAMESPACE_APP

    log_success "Políticas Istio aplicadas"
}

deploy_monitoring() {
    log_info "Configurando monitoramento..."

    # Aplicar ServiceMonitors
    kubectl apply -f /home/jimy/Base/Neural-Hive-Mind/monitoring/servicemonitors/ --recursive

    # Importar dashboards Grafana (assumindo Grafana já instalado)
    if kubectl get configmap grafana-dashboards-redis -n monitoring &> /dev/null; then
        log_warning "Dashboard Redis já existe"
    else
        kubectl create configmap grafana-dashboards-redis \
            --from-file=/home/jimy/Base/Neural-Hive-Mind/monitoring/dashboards/redis-cluster.json \
            -n monitoring
        kubectl label configmap grafana-dashboards-redis grafana_dashboard=1 -n monitoring
    fi

    if kubectl get configmap grafana-dashboards-keycloak -n monitoring &> /dev/null; then
        log_warning "Dashboard Keycloak já existe"
    else
        kubectl create configmap grafana-dashboards-keycloak \
            --from-file=/home/jimy/Base/Neural-Hive-Mind/monitoring/dashboards/keycloak-auth.json \
            -n monitoring
        kubectl label configmap grafana-dashboards-keycloak grafana_dashboard=1 -n monitoring
    fi

    if kubectl get configmap grafana-dashboards-governance -n monitoring &> /dev/null; then
        log_warning "Dashboard Governança já existe"
    else
        kubectl create configmap grafana-dashboards-governance \
            --from-file=/home/jimy/Base/Neural-Hive-Mind/monitoring/dashboards/data-governance.json \
            -n monitoring
        kubectl label configmap grafana-dashboards-governance grafana_dashboard=1 -n monitoring
    fi

    log_success "Monitoramento configurado"
}

run_validation() {
    log_info "Executando validações..."

    # Executar script de validação do Redis
    if [ -f "/home/jimy/Base/Neural-Hive-Mind/scripts/validation/validate-redis-cluster.sh" ]; then
        bash /home/jimy/Base/Neural-Hive-Mind/scripts/validation/validate-redis-cluster.sh
    fi

    # Executar script de validação do OAuth2
    if [ -f "/home/jimy/Base/Neural-Hive-Mind/scripts/validation/validate-oauth2-flow.sh" ]; then
        bash /home/jimy/Base/Neural-Hive-Mind/scripts/validation/validate-oauth2-flow.sh
    fi
}

main() {
    log_info "=== Iniciando implantação da Camada de Memória Neural ==="
    log_info "Timestamp: $(date)"

    check_prerequisites
    create_namespaces

    # Deploy em ordem de dependências
    deploy_redis_operator
    deploy_redis_cluster
    deploy_keycloak
    deploy_opa_gatekeeper
    deploy_istio_policies
    deploy_monitoring

    log_info "=== Validando implantação ==="
    run_validation

    log_success "=== Implantação da Camada de Memória concluída com sucesso! ==="
    log_info "Próximos passos:"
    log_info "1. Configure o realm 'neural-hive' no Keycloak"
    log_info "2. Crie clientes OAuth2 para os serviços"
    log_info "3. Verifique os dashboards no Grafana"
    log_info "4. Execute testes de integração"
}

# Trap para limpeza em caso de erro
trap 'log_error "Erro durante a implantação. Verifique os logs acima."' ERR

# Executar script principal
main "$@"