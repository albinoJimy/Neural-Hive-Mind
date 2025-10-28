#!/bin/bash

# Validação das configurações de observabilidade do Neural Hive-Mind
# Este script valida se todas as configurações estão corretas antes do deploy

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color

# Contadores
ERRORS=0
WARNINGS=0

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    ((ERRORS++))
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
    ((WARNINGS++))
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_info() {
    echo -e "[INFO] $1"
}

# Validar se ferramentas necessárias estão disponíveis
check_dependencies() {
    log_info "Verificando dependências..."

    local deps=("yq" "jq" "helm" "kubectl")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "Dependência não encontrada: $dep"
        else
            log_success "Dependência encontrada: $dep"
        fi
    done
}

# Validar arquivos YAML do Prometheus
validate_prometheus_configs() {
    log_info "Validando configurações do Prometheus..."

    local alert_files=("${PROJECT_ROOT}/monitoring/alerts/"*.yaml)
    for file in "${alert_files[@]}"; do
        if [[ -f "$file" ]]; then
            if yq eval '.' "$file" > /dev/null 2>&1; then
                log_success "YAML válido: $(basename "$file")"
            else
                log_error "YAML inválido: $(basename "$file")"
            fi

            # Verificar se todas as regras têm labels obrigatórios
            if ! yq eval '.groups[].rules[] | select(.alert) | has("labels")' "$file" | grep -q "true"; then
                log_warning "Algumas regras em $(basename "$file") podem não ter labels"
            fi

            # Verificar se têm neural_hive_component
            if ! yq eval '.groups[].rules[].labels | select(.) | has("neural_hive_component")' "$file" | grep -q "true"; then
                log_warning "Algumas regras em $(basename "$file") não têm label neural_hive_component"
            fi
        fi
    done
}

# Validar dashboards JSON
validate_grafana_dashboards() {
    log_info "Validando dashboards do Grafana..."

    local dashboard_files=("${PROJECT_ROOT}/monitoring/dashboards/"*.json)
    for file in "${dashboard_files[@]}"; do
        if [[ -f "$file" ]]; then
            if jq empty "$file" 2>/dev/null; then
                log_success "JSON válido: $(basename "$file")"

                # Verificar se tem datasource configurado
                if ! jq '.templating.list[] | select(.type == "datasource")' "$file" | grep -q "datasource"; then
                    log_warning "Dashboard $(basename "$file") pode não ter datasource configurado"
                fi

                # Verificar se tem tags apropriadas
                local tags_count
                tags_count=$(jq '.tags | length' "$file")
                if [[ "$tags_count" -eq 0 ]]; then
                    log_warning "Dashboard $(basename "$file") não tem tags definidas"
                fi
            else
                log_error "JSON inválido: $(basename "$file")"
            fi
        fi
    done
}

# Validar templates Helm
validate_helm_templates() {
    log_info "Validando templates Helm..."

    local charts=("helm-charts/grafana" "helm-charts/prometheus-stack" "helm-charts/otel-collector")
    for chart_path in "${charts[@]}"; do
        local full_path="${PROJECT_ROOT}/${chart_path}"
        if [[ -d "$full_path" ]]; then
            if helm template test "$full_path" > /dev/null 2>&1; then
                log_success "Template Helm válido: $chart_path"
            else
                log_error "Template Helm inválido: $chart_path"
            fi

            # Verificar se Chart.yaml existe e é válido
            if [[ -f "$full_path/Chart.yaml" ]]; then
                if yq eval '.' "$full_path/Chart.yaml" > /dev/null 2>&1; then
                    log_success "Chart.yaml válido: $chart_path"
                else
                    log_error "Chart.yaml inválido: $chart_path"
                fi
            else
                log_error "Chart.yaml não encontrado: $chart_path"
            fi
        else
            log_warning "Diretório do chart não encontrado: $chart_path"
        fi
    done
}

# Validar estrutura de arquivos
validate_file_structure() {
    log_info "Validando estrutura de arquivos..."

    local required_files=(
        "monitoring/alerts/slo-alerts.yaml"
        "monitoring/alerts/infrastructure-alerts.yaml"
        "monitoring/dashboards/neural-hive-overview.json"
        "monitoring/dashboards/infrastructure-overview.json"
        "monitoring/dashboards/observability-stack.json"
        "helm-charts/grafana/values.yaml"
        "helm-charts/grafana/Chart.yaml"
        "helm-charts/otel-collector/values.yaml"
        "libraries/python/neural_hive_observability/__init__.py"
        "libraries/python/neural_hive_observability/config.py"
        "libraries/python/neural_hive_observability/metrics.py"
    )

    for file in "${required_files[@]}"; do
        if [[ -f "${PROJECT_ROOT}/$file" ]]; then
            log_success "Arquivo encontrado: $file"
        else
            log_error "Arquivo obrigatório não encontrado: $file"
        fi
    done
}

# Validar métricas Python
validate_python_metrics() {
    log_info "Validando bibliotecas Python de métricas..."

    local python_files=(
        "libraries/python/neural_hive_observability/metrics.py"
        "services/gateway-intencoes/src/observability/metrics.py"
    )

    for file in "${python_files[@]}"; do
        local full_path="${PROJECT_ROOT}/$file"
        if [[ -f "$full_path" ]]; then
            # Verificar se usa o padrão de nomenclatura correto
            if grep -q "neural_hive_" "$full_path"; then
                log_success "Padrão de métrica correto encontrado em: $(basename "$file")"
            else
                log_warning "Padrão de métrica neural_hive_ não encontrado em: $(basename "$file")"
            fi

            # Verificar se importa as bibliotecas corretas
            if grep -q "from prometheus_client" "$full_path"; then
                log_success "Importação prometheus_client encontrada em: $(basename "$file")"
            else
                log_warning "Importação prometheus_client não encontrada em: $(basename "$file")"
            fi
        fi
    done
}

# Validar configuração do OpenTelemetry
validate_otel_config() {
    log_info "Validando configuração OpenTelemetry..."

    local otel_config="${PROJECT_ROOT}/helm-charts/otel-collector/templates/configmap.yaml"
    if [[ -f "$otel_config" ]]; then
        # Verificar se tem configuração OTLP
        if grep -q "otlp" "$otel_config"; then
            log_success "Configuração OTLP encontrada"
        else
            log_error "Configuração OTLP não encontrada no OTel Collector"
        fi

        # Verificar se tem exporters configurados
        if grep -q "exporters:" "$otel_config"; then
            log_success "Exporters configurados no OTel Collector"
        else
            log_warning "Exporters podem não estar configurados no OTel Collector"
        fi
    else
        log_error "Configuração do OpenTelemetry Collector não encontrada"
    fi
}

# Validar ServiceMonitors
validate_service_monitors() {
    log_info "Validando ServiceMonitors..."

    # Buscar por arquivos que contenham ServiceMonitor
    if find "${PROJECT_ROOT}" -name "*.yaml" -exec grep -l "kind: ServiceMonitor" {} \; | head -1 > /dev/null; then
        log_success "ServiceMonitors encontrados"

        # Verificar se têm labels padrão
        local service_monitors
        service_monitors=$(find "${PROJECT_ROOT}" -name "*.yaml" -exec grep -l "kind: ServiceMonitor" {} \;)

        for sm in $service_monitors; do
            if grep -q "neural.hive/metrics" "$sm"; then
                log_success "Label neural.hive/metrics encontrado em: $(basename "$sm")"
            else
                log_warning "Label neural.hive/metrics não encontrado em: $(basename "$sm")"
            fi
        done
    else
        log_warning "Nenhum ServiceMonitor encontrado"
    fi
}

# Validar secrets
validate_secrets() {
    log_info "Validando configurações de secrets..."

    local grafana_values="${PROJECT_ROOT}/helm-charts/grafana/values.yaml"
    if [[ -f "$grafana_values" ]]; then
        if grep -q "existingSecret" "$grafana_values"; then
            log_success "Configuração de secret encontrada no Grafana"
        else
            log_warning "Configuração de secret não encontrada no Grafana"
        fi

        if grep -q "envFromSecret" "$grafana_values"; then
            log_success "envFromSecret configurado no Grafana"
        else
            log_warning "envFromSecret não configurado no Grafana"
        fi
    fi

    # Verificar se existe template de secret
    local secret_template="${PROJECT_ROOT}/helm-charts/grafana/templates/secret.yaml"
    if [[ -f "$secret_template" ]]; then
        log_success "Template de secret encontrado"
    else
        log_error "Template de secret não encontrado"
    fi
}

# Função principal
main() {
    echo "=== Validação de Configurações de Observabilidade Neural Hive-Mind ==="
    echo "Projeto: ${PROJECT_ROOT}"
    echo ""

    check_dependencies
    echo ""

    validate_file_structure
    echo ""

    validate_prometheus_configs
    echo ""

    validate_grafana_dashboards
    echo ""

    validate_helm_templates
    echo ""

    validate_python_metrics
    echo ""

    validate_otel_config
    echo ""

    validate_service_monitors
    echo ""

    validate_secrets
    echo ""

    # Resumo final
    echo "=== RESUMO ==="
    if [[ $ERRORS -eq 0 ]]; then
        log_success "Validação concluída sem erros!"
    else
        log_error "Validação concluída com $ERRORS erro(s)!"
    fi

    if [[ $WARNINGS -gt 0 ]]; then
        log_warning "Total de avisos: $WARNINGS"
    fi

    echo ""
    echo "Detalhes:"
    echo "  - Erros: $ERRORS"
    echo "  - Avisos: $WARNINGS"

    exit $ERRORS
}

# Executar se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi