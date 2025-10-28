#!/bin/bash

##
# Deploy completo da stack de observabilidade do Neural Hive-Mind
#
# Executa deploy do Terraform, instalação dos Helm charts, configuração
# de data sources e import de dashboards. Inclui validações de conectividade
# e health checks.
##

set -euo pipefail

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform/modules/observability-stack"
HELM_CHARTS_DIR="$PROJECT_ROOT/helm-charts"
DASHBOARDS_DIR="$PROJECT_ROOT/monitoring/dashboards"
ALERTS_DIR="$PROJECT_ROOT/monitoring/alerts"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações padrão
NAMESPACE="${NAMESPACE:-observability}"
ENVIRONMENT="${ENVIRONMENT:-production}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_TERRAFORM="${SKIP_TERRAFORM:-false}"
SKIP_HELM="${SKIP_HELM:-false}"
SKIP_VALIDATION="${SKIP_VALIDATION:-false}"

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_prerequisites() {
    log "Verificando pré-requisitos..."

    local missing_tools=()

    # Verificar ferramentas necessárias
    for tool in kubectl helm terraform jq; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done

    if [ ${#missing_tools[@]} -ne 0 ]; then
        error "Ferramentas faltando: ${missing_tools[*]}"
        error "Por favor, instale as ferramentas necessárias"
        exit 1
    fi

    # Verificar conectividade com cluster Kubernetes
    if ! kubectl cluster-info &> /dev/null; then
        error "Não foi possível conectar ao cluster Kubernetes"
        error "Verifique sua configuração do kubectl"
        exit 1
    fi

    # Verificar se namespace existe, criar se necessário
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        warning "Namespace $NAMESPACE não existe, criando..."
        kubectl create namespace "$NAMESPACE"
    fi

    success "Pré-requisitos verificados"
}

extract_terraform_outputs() {
    if [ "$SKIP_TERRAFORM" = "true" ]; then
        warning "Terraform foi pulado, usando configuração padrão"
        # Definir valores padrão quando Terraform é pulado
        export GRAFANA_URL="http://grafana.$NAMESPACE.svc.cluster.local:3000"
        export GRAFANA_API_URL="http://grafana.$NAMESPACE.svc.cluster.local:3000/api"
        export PROMETHEUS_URL="http://prometheus-stack-prometheus.$NAMESPACE.svc.cluster.local:9090"
        export JAEGER_URL="http://jaeger-query.$NAMESPACE.svc.cluster.local:16686"
        return
    fi

    log "Extraindo outputs do Terraform..."

    cd "$TERRAFORM_DIR"

    # Verificar se Terraform está inicializado
    if [ ! -d ".terraform" ]; then
        error "Terraform não está inicializado"
        return 1
    fi

    # Extrair outputs em JSON
    local outputs_file="/tmp/terraform-outputs.json"
    terraform output -json > "$outputs_file" 2>/dev/null || {
        warning "Não foi possível extrair outputs do Terraform"
        return
    }

    # Extrair configurações específicas usando nomes de outputs corretos
    if [ -f "$outputs_file" ]; then
        # Configurações do Grafana
        export GRAFANA_URL=$(jq -r '.grafana_url.value // "http://grafana.'$NAMESPACE'.svc.cluster.local:3000"' "$outputs_file")
        export GRAFANA_API_URL=$(jq -r '.grafana_config.value.api_url // "http://grafana.'$NAMESPACE'.svc.cluster.local:3000/api"' "$outputs_file")
        export GRAFANA_ADMIN_PASSWORD=$(jq -r '.admin_credentials.value.grafana_admin_password // ""' "$outputs_file")

        # Configurações do Prometheus
        export PROMETHEUS_URL=$(jq -r '.prometheus_url.value // "http://prometheus-stack-prometheus.'$NAMESPACE'.svc.cluster.local:9090"' "$outputs_file")
        export PROMETHEUS_API_URL=$(jq -r '.prometheus_config.value.api_url // "http://prometheus-stack-prometheus.'$NAMESPACE'.svc.cluster.local:9090/api/v1"' "$outputs_file")

        # Configurações do Jaeger
        export JAEGER_URL=$(jq -r '.jaeger_url.value // "http://jaeger-query.'$NAMESPACE'.svc.cluster.local:16686"' "$outputs_file")
        export JAEGER_COLLECTOR_URL=$(jq -r '.jaeger_config.value.collector_http // "http://jaeger-collector.'$NAMESPACE'.svc.cluster.local:14268"' "$outputs_file")

        # Configurações do OpenTelemetry Collector
        export OTEL_COLLECTOR_ENDPOINT=$(jq -r '.otel_collector_endpoint.value.grpc // "opentelemetry-collector.'$NAMESPACE'.svc.cluster.local:4317"' "$outputs_file")
        export OTEL_COLLECTOR_HTTP_ENDPOINT=$(jq -r '.otel_collector_endpoint.value.http // "opentelemetry-collector.'$NAMESPACE'.svc.cluster.local:4318"' "$outputs_file")

        # Configurações de correlação
        export CORRELATION_HEADERS=$(jq -r '.correlation_config.value.headers | to_entries | map("\(.key)=\(.value)") | join(",")' "$outputs_file" 2>/dev/null || echo "")

        # Endpoints de validação
        export VALIDATION_ENDPOINTS_FILE="$outputs_file"

        # Configurações de SLOs
        export SLO_CONFIG=$(jq -c '.slo_config.value' "$outputs_file" 2>/dev/null || echo '{}')

        # URLs externas se disponíveis
        export GRAFANA_EXTERNAL_URL=$(jq -r '.grafana_external_url.value // null' "$outputs_file")
        export JAEGER_EXTERNAL_URL=$(jq -r '.jaeger_external_url.value // null' "$outputs_file")

        success "Outputs do Terraform extraídos com sucesso"

        # Log das configurações principais
        log "Configurações extraídas:"
        log "  Grafana: $GRAFANA_URL"
        log "  Prometheus: $PROMETHEUS_URL"
        log "  Jaeger: $JAEGER_URL"
        log "  OTel Collector: $OTEL_COLLECTOR_ENDPOINT"
        if [ "$GRAFANA_EXTERNAL_URL" != "null" ] && [ -n "$GRAFANA_EXTERNAL_URL" ]; then
            log "  Grafana External: $GRAFANA_EXTERNAL_URL"
        fi
    else
        warning "Arquivo de outputs não encontrado"
    fi

    # Manter arquivo temporário para validação posterior
    # rm -f "$outputs_file" 2>/dev/null || true
}

deploy_terraform() {
    if [ "$SKIP_TERRAFORM" = "true" ]; then
        warning "Pulando deploy do Terraform"
        return
    fi

    log "Iniciando deploy do Terraform..."

    cd "$TERRAFORM_DIR"

    # Inicializar Terraform se necessário
    if [ ! -d ".terraform" ]; then
        log "Inicializando Terraform..."
        terraform init
    fi

    # Planejar deploy
    log "Planejando deploy..."
    local plan_file="/tmp/observability-plan"

    terraform plan \
        -var="namespace=$NAMESPACE" \
        -var="environment=$ENVIRONMENT" \
        -out="$plan_file"

    if [ "$DRY_RUN" = "true" ]; then
        warning "Modo dry-run ativado, não executando terraform apply"
        rm -f "$plan_file"
        return
    fi

    # Aplicar mudanças
    log "Aplicando mudanças do Terraform..."
    terraform apply "$plan_file"

    rm -f "$plan_file"
    success "Deploy do Terraform concluído"

    # Extrair outputs após o deploy
    extract_terraform_outputs
}

deploy_helm_charts() {
    if [ "$SKIP_HELM" = "true" ]; then
        warning "Pulando deploy dos Helm charts"
        return
    fi

    log "Iniciando deploy dos Helm charts..."

    cd "$HELM_CHARTS_DIR"

    # Atualizar repositórios Helm
    log "Atualizando repositórios Helm..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo add grafana https://grafana.github.io/helm-charts
    helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
    helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
    helm repo update

    # Deploy do OpenTelemetry Collector
    log "Deployando OpenTelemetry Collector..."
    helm upgrade --install neural-hive-otel-collector ./otel-collector \
        --namespace "$NAMESPACE" \
        --set global.environment="$ENVIRONMENT" \
        --wait \
        --timeout=300s \
        ${DRY_RUN:+--dry-run}

    # Deploy do Prometheus Stack
    log "Deployando Prometheus Stack..."
    helm upgrade --install neural-hive-prometheus ./prometheus-stack \
        --namespace "$NAMESPACE" \
        --set global.environment="$ENVIRONMENT" \
        --wait \
        --timeout=600s \
        ${DRY_RUN:+--dry-run}

    # Deploy do Grafana
    log "Deployando Grafana..."
    helm upgrade --install neural-hive-grafana ./grafana \
        --namespace "$NAMESPACE" \
        --set global.environment="$ENVIRONMENT" \
        --wait \
        --timeout=300s \
        ${DRY_RUN:+--dry-run}

    # Deploy do Jaeger
    log "Deployando Jaeger..."
    helm upgrade --install neural-hive-jaeger ./jaeger \
        --namespace "$NAMESPACE" \
        --set global.environment="$ENVIRONMENT" \
        --wait \
        --timeout=300s \
        ${DRY_RUN:+--dry-run}

    success "Deploy dos Helm charts concluído"
}

apply_environment_values() {
    log "Aplicando valores específicos do ambiente: $ENVIRONMENT"

    # Verificar arquivos de valores por ambiente
    local base_values_dir="$PROJECT_ROOT/environments/$ENVIRONMENT"
    local helm_values_dir="$base_values_dir/helm-values"

    if [ -d "$helm_values_dir" ]; then
        log "Encontrado diretório de valores Helm: $helm_values_dir"

        # Exportar variáveis para uso nos Helm charts
        export HELM_VALUES_DIR="$helm_values_dir"

        # Verificar arquivos específicos
        local value_files=(
            "prometheus-stack-values.yaml"
            "grafana-values.yaml"
            "jaeger-values.yaml"
            "otel-collector-values.yaml"
        )

        for file in "${value_files[@]}"; do
            if [ -f "$helm_values_dir/$file" ]; then
                log "  Encontrado: $file"
            else
                log "  Não encontrado: $file (usando valores padrão)"
            fi
        done

        success "Valores específicos do ambiente configurados"
    else
        warning "Diretório de valores não encontrado: $helm_values_dir"
        log "Usando valores padrão dos Helm charts"
        export HELM_VALUES_DIR=""
    fi

    # Verificar arquivo de valores legado
    local legacy_values_file="$PROJECT_ROOT/environments/$ENVIRONMENT/observability-values.yaml"
    if [ -f "$legacy_values_file" ]; then
        log "Arquivo de valores legado encontrado: $legacy_values_file"
        log "Considere migrar para $helm_values_dir/"
    fi
}

import_dashboards() {
    if [ "$DRY_RUN" = "true" ]; then
        warning "Modo dry-run ativado, não importando dashboards"
        return
    fi

    log "Importando dashboards do Grafana via setup-dashboards.sh..."

    # Aguardar Grafana estar pronto
    log "Aguardando Grafana estar disponível..."
    kubectl wait --namespace "$NAMESPACE" \
        --for=condition=available \
        --timeout=300s \
        deployment/grafana || {
        error "Grafana não ficou disponível no tempo esperado"
        return 1
    }

    # Configurar variáveis para setup-dashboards.sh
    local dashboard_script="$PROJECT_ROOT/scripts/observability/setup-dashboards.sh"

    if [ ! -f "$dashboard_script" ]; then
        error "Script setup-dashboards.sh não encontrado: $dashboard_script"
        return 1
    fi

    # Detectar se Grafana está acessível internamente
    local grafana_accessible=false
    if kubectl exec -n "$NAMESPACE" deployment/grafana -- curl -s --connect-timeout 5 "http://localhost:3000/api/health" >/dev/null 2>&1; then
        grafana_accessible=true
        log "Grafana acessível internamente"
    fi

    # Port-forward temporário para Grafana se necessário
    local use_port_forward=false
    local pf_pid=""

    if [ "$grafana_accessible" = "false" ] || [[ "$GRAFANA_URL" =~ localhost ]]; then
        use_port_forward=true
        log "Configurando port-forward para Grafana..."
        kubectl port-forward --namespace "$NAMESPACE" \
            service/grafana 3000:3000 &
        pf_pid=$!

        # Aguardar port-forward estar ativo
        sleep 15

        # Verificar se port-forward funcionou
        if ! curl -s --connect-timeout 5 "http://localhost:3000/api/health" >/dev/null 2>&1; then
            warning "Port-forward pode não estar funcionando, tentando continuar..."
        fi

        export GRAFANA_URL="http://localhost:3000"
    fi

    # Executar setup-dashboards.sh com configurações extraídas do Terraform
    log "Executando setup-dashboards.sh com as seguintes configurações:"
    log "  GRAFANA_URL: $GRAFANA_URL"
    log "  DASHBOARD_DIR: $DASHBOARDS_DIR"
    log "  ENVIRONMENT: $ENVIRONMENT"

    # Preparar variáveis de ambiente para o script
    local dashboard_env=(
        "GRAFANA_URL=$GRAFANA_URL"
        "DASHBOARD_DIR=$DASHBOARDS_DIR"
        "ENVIRONMENT=$ENVIRONMENT"
    )

    if [ -n "$GRAFANA_ADMIN_PASSWORD" ]; then
        dashboard_env+=("GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD")
    fi

    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        dashboard_env+=("SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL")
    fi

    log "Executando setup-dashboards.sh..."
    env "${dashboard_env[@]}" bash "$dashboard_script" \
        --dashboard-dir "$DASHBOARDS_DIR" \
        --folder-name "Neural Hive-Mind" \
        --backup

    local dashboard_result=$?

    # Cleanup port-forward se foi usado
    if [ "$use_port_forward" = "true" ] && [ -n "$pf_pid" ]; then
        log "Finalizando port-forward..."
        kill $pf_pid 2>/dev/null || true
        # Aguardar processo finalizar
        sleep 2
    fi

    if [ $dashboard_result -eq 0 ]; then
        success "Dashboards importados com sucesso"
    else
        error "Falha na importação de dashboards"
        return 1
    fi
}

apply_alert_rules() {
    if [ "$DRY_RUN" = "true" ]; then
        warning "Modo dry-run ativado, não aplicando regras de alerta"
        return
    fi

    log "Aplicando regras de alerta..."

    # Aplicar alertas via kubectl
    for alert_file in "$ALERTS_DIR"/*.yaml; do
        if [ -f "$alert_file" ]; then
            local alert_name=$(basename "$alert_file" .yaml)
            log "Aplicando alertas: $alert_name"

            # Converter YAML para PrometheusRule CRD
            cat > "/tmp/prometheus-rule-$alert_name.yaml" <<EOF
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: neural-hive-$alert_name
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: neural-hive-$alert_name
    app.kubernetes.io/part-of: neural-hive-observability
    prometheus: kube-prometheus
    role: alert-rules
    neural.hive/component: alerting
    neural.hive/layer: observabilidade
spec:
$(cat "$alert_file" | sed 's/^/  /')
EOF

            # Aplicar PrometheusRule
            kubectl apply -f "/tmp/prometheus-rule-$alert_name.yaml"

            # Cleanup
            rm -f "/tmp/prometheus-rule-$alert_name.yaml"
        fi
    done

    success "Regras de alerta aplicadas"
}

validate_deployment() {
    if [ "$SKIP_VALIDATION" = "true" ]; then
        warning "Pulando validação"
        return
    fi

    log "Validando deployment..."

    # Executar script de validação
    local validation_script="$PROJECT_ROOT/scripts/validation/validate-observability.sh"
    if [ -f "$validation_script" ]; then
        log "Executando validação completa..."
        bash "$validation_script" --namespace "$NAMESPACE"
    else
        warning "Script de validação não encontrado, fazendo verificação básica..."

        # Verificação básica de pods
        local failed_pods=()
        while IFS= read -r pod; do
            if [[ -n "$pod" ]]; then
                failed_pods+=("$pod")
            fi
        done < <(kubectl get pods --namespace "$NAMESPACE" --no-headers | awk '$3 != "Running" && $3 != "Completed" {print $1}')

        if [ ${#failed_pods[@]} -ne 0 ]; then
            error "Pods com problemas: ${failed_pods[*]}"
            return 1
        fi
    fi

    success "Validação concluída"
}

cleanup() {
    log "Limpando recursos temporários..."
    # Cleanup code here if needed
}

show_endpoints() {
    log "Endpoints da stack de observabilidade:"

    echo
    echo "Para acessar os serviços via port-forward:"
    echo "  Prometheus:  kubectl port-forward --namespace $NAMESPACE service/prometheus-stack-prometheus 9090:9090"
    echo "  Grafana:     kubectl port-forward --namespace $NAMESPACE service/grafana 3000:3000"
    echo "  Jaeger:      kubectl port-forward --namespace $NAMESPACE service/jaeger-query 16686:16686"
    echo "  AlertManager: kubectl port-forward --namespace $NAMESPACE service/prometheus-stack-alertmanager 9093:9093"
    echo "  OTel Collector: kubectl port-forward --namespace $NAMESPACE service/opentelemetry-collector 4317:4317"
    echo

    # Mostrar URLs de Ingress se existirem
    local ingresses
    ingresses=$(kubectl get ingresses --namespace "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $1, $3}' || true)

    if [ -n "$ingresses" ]; then
        echo "URLs via Ingress:"
        echo "$ingresses" | while read -r name url; do
            echo "  $name: https://$url"
        done
        echo
    fi
}

main() {
    log "Iniciando deploy da stack de observabilidade do Neural Hive-Mind"
    log "Namespace: $NAMESPACE"
    log "Environment: $ENVIRONMENT"
    log "Dry-run: $DRY_RUN"

    # Trap para cleanup
    trap cleanup EXIT

    # Executar etapas do deploy
    check_prerequisites
    deploy_terraform
    apply_environment_values
    deploy_helm_charts
    import_dashboards
    apply_alert_rules
    validate_deployment
    show_endpoints

    success "Deploy da stack de observabilidade concluído com sucesso!"

    if [ "$DRY_RUN" = "false" ]; then
        log "A stack de observabilidade está sendo inicializada..."
        log "Aguarde alguns minutos para todos os componentes estarem totalmente operacionais"
    fi
}

# Ajuda
show_help() {
    cat << EOF
Deploy da Stack de Observabilidade do Neural Hive-Mind

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -n, --namespace NAMESPACE    Namespace Kubernetes (padrão: observability)
    -e, --environment ENV        Environment (padrão: production)
    -d, --dry-run               Executar em modo dry-run
    --skip-terraform            Pular deploy do Terraform
    --skip-helm                 Pular deploy dos Helm charts
    --skip-validation           Pular validação
    -h, --help                  Mostrar esta ajuda

EXAMPLES:
    # Deploy completo em produção
    $0

    # Deploy em staging
    $0 --environment staging --namespace observability-staging

    # Dry-run para verificar mudanças
    $0 --dry-run

    # Deploy apenas dos Helm charts
    $0 --skip-terraform

ENVIRONMENT VARIABLES:
    NAMESPACE                   Namespace Kubernetes
    ENVIRONMENT                 Environment (production, staging, development)
    DRY_RUN                     Modo dry-run (true/false)
    SKIP_TERRAFORM              Pular Terraform (true/false)
    SKIP_HELM                   Pular Helm (true/false)
    SKIP_VALIDATION             Pular validação (true/false)
EOF
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN="true"
            shift
            ;;
        --skip-terraform)
            SKIP_TERRAFORM="true"
            shift
            ;;
        --skip-helm)
            SKIP_HELM="true"
            shift
            ;;
        --skip-validation)
            SKIP_VALIDATION="true"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            error "Argumento desconhecido: $1"
            show_help
            exit 1
            ;;
    esac
done

# Executar main
main "$@"