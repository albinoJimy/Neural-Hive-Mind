#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

NAMESPACE="registry"
CHART_PATH="${SCRIPT_DIR}/../helm-charts/docker-registry"
ENVIRONMENT="${2:-staging}"

deploy_registry_ha() {
    local env="$1"
    local values_file="${CHART_PATH}/values-ha.yaml"

    log_section "Deploying Registry HA - Environment: ${env}"

    # Verificar se values-ha.yaml existe
    if [[ ! -f "${values_file}" ]]; then
        log_error "Arquivo ${values_file} não encontrado"
        return 1
    fi

    # Criar namespace se não existir
    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    # Deploy Redis para cache (se não existir)
    if ! kubectl get deployment redis-registry -n "${NAMESPACE}" >/dev/null 2>&1; then
        log_info "Deploying Redis para cache distribuído..."
        kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-registry
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis-registry
  template:
    metadata:
      labels:
        app: redis-registry
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Service
metadata:
  name: redis-registry
  namespace: ${NAMESPACE}
spec:
  selector:
    app: redis-registry
  ports:
  - port: 6379
    targetPort: 6379
EOF
    fi

    # Deploy registry com Helm
    log_info "Deploying Docker Registry HA..."
    helm upgrade --install docker-registry "${CHART_PATH}" \
        --namespace "${NAMESPACE}" \
        --values "${values_file}" \
        --set storage.s3.bucket="neural-hive-registry-${env}" \
        --wait \
        --timeout 5m

    # Aguardar LoadBalancer obter IP
    log_info "Aguardando LoadBalancer obter External IP..."
    local timeout=120
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        local lb_ip
        lb_ip=$(kubectl get svc docker-registry -n "${NAMESPACE}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        if [[ -n "${lb_ip}" ]]; then
            log_success "Registry HA deployed!"
            log_info "LoadBalancer IP: ${lb_ip}"
            log_info "DNS: registry.neural-hive.local"
            log_info ""
            log_info "Adicione ao /etc/hosts ou DNS:"
            log_info "  ${lb_ip} registry.neural-hive.local"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    log_warning "LoadBalancer ainda não possui External IP (timeout)"
    log_info "Verifique com: kubectl get svc docker-registry -n ${NAMESPACE}"
}

verify_registry() {
    log_section "Verificando Registry HA"

    # Check pods
    log_info "Pods do registry:"
    kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=docker-registry

    # Check service
    log_info "Service do registry:"
    kubectl get svc docker-registry -n "${NAMESPACE}"

    # Test connectivity
    local registry_url="registry.neural-hive.local:5000"
    log_info "Testando conectividade com ${registry_url}..."

    if curl -sf "http://${registry_url}/v2/" >/dev/null 2>&1; then
        log_success "Registry acessível via DNS!"
    else
        log_warning "Registry não acessível via DNS (pode precisar configurar /etc/hosts)"
    fi
}

rollback_registry() {
    log_section "Rollback para configuração anterior"

    helm rollback docker-registry -n "${NAMESPACE}"
    log_success "Rollback concluído"
}

case "${1:-deploy}" in
    deploy)
        deploy_registry_ha "${ENVIRONMENT}"
        verify_registry
        ;;
    verify)
        verify_registry
        ;;
    rollback)
        rollback_registry
        ;;
    *)
        log_error "Comando inválido: $1"
        echo "Uso: $0 {deploy|verify|rollback} [environment]"
        exit 1
        ;;
esac
