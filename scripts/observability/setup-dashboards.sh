#!/bin/bash

# Setup Dashboards Script for Neural Hive-Mind Observability
# Este script instala/atualiza dashboards do Grafana via API

set -euo pipefail

# Configurações
GRAFANA_URL="${GRAFANA_URL:-https://grafana.neural-hive.local}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
DASHBOARD_DIR="${DASHBOARD_DIR:-monitoring/dashboards}"
FOLDER_NAME="${FOLDER_NAME:-Neural Hive-Mind}"
DRY_RUN="${DRY_RUN:-false}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Função para verificar dependências
check_dependencies() {
    log "Verificando dependências..."

    local deps=("curl" "jq")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            error "Dependência não encontrada: $dep"
        fi
    done

    success "Dependências OK"
}

# Função para obter/criar API key automaticamente
get_or_create_api_key() {
    log "Verificando API key do Grafana..."

    if [ -n "$GRAFANA_API_KEY" ]; then
        log "Usando API key fornecida"
        return
    fi

    # Tentar obter via credenciais admin
    local admin_user="${GRAFANA_ADMIN_USER:-admin}"
    local admin_password="${GRAFANA_ADMIN_PASSWORD:-}"

    if [ -z "$admin_password" ]; then
        error "GRAFANA_API_KEY ou GRAFANA_ADMIN_PASSWORD deve ser fornecida"
    fi

    log "Criando API key usando credenciais de admin..."

    # Criar API key temporária para setup
    local api_key_payload='{
        "name": "dashboard-setup-temp",
        "role": "Admin",
        "secondsToLive": 3600
    }'

    local response
    response=$(curl -s -X POST \
        -u "$admin_user:$admin_password" \
        -H "Content-Type: application/json" \
        -d "$api_key_payload" \
        "$GRAFANA_URL/api/auth/keys" || echo "error")

    local key
    key=$(echo "$response" | jq -r '.key // empty')

    if [ -n "$key" ]; then
        GRAFANA_API_KEY="$key"
        success "API key criada automaticamente"
    else
        error "Falha ao criar API key: $(echo "$response" | jq -r '.message // "unknown error"')"
    fi
}

# Função para verificar conectividade com Grafana
check_grafana_connectivity() {
    log "Verificando conectividade com Grafana..."

    # Tentar obter API key se necessário
    get_or_create_api_key

    local response
    response=$(curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
                   "$GRAFANA_URL/api/health" || echo "error")

    if [[ "$response" == *"ok"* ]]; then
        success "Grafana acessível"
    else
        error "Não foi possível conectar ao Grafana: $response"
    fi
}

# Função para obter/criar folder no Grafana
get_or_create_folder() {
    local folder_name="$1"
    log "Verificando folder: $folder_name"

    local folders_response
    folders_response=$(curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
                          "$GRAFANA_URL/api/folders")

    local folder_uid
    folder_uid=$(echo "$folders_response" | jq -r ".[] | select(.title == \"$folder_name\") | .uid")

    if [ "$folder_uid" == "null" ] || [ -z "$folder_uid" ]; then
        log "Criando folder: $folder_name"

        local create_response
        create_response=$(curl -s -X POST \
            -H "Authorization: Bearer $GRAFANA_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{\"title\":\"$folder_name\"}" \
            "$GRAFANA_URL/api/folders")

        folder_uid=$(echo "$create_response" | jq -r '.uid')
        success "Folder criado: $folder_uid"
    else
        log "Folder encontrado: $folder_uid"
    fi

    echo "$folder_uid"
}

# Função para validar dashboard JSON
validate_dashboard() {
    local dashboard_file="$1"

    if ! jq empty "$dashboard_file" 2>/dev/null; then
        error "JSON inválido: $dashboard_file"
    fi

    # Verificar campos obrigatórios
    local title
    title=$(jq -r '.title' "$dashboard_file")
    if [ "$title" == "null" ] || [ -z "$title" ]; then
        error "Dashboard sem título: $dashboard_file"
    fi

    log "Dashboard válido: $title"
}

# Função para instalar/atualizar dashboard
install_dashboard() {
    local dashboard_file="$1"
    local folder_uid="$2"

    local dashboard_title
    dashboard_title=$(jq -r '.title' "$dashboard_file")

    log "Processando dashboard: $dashboard_title"

    if [ "$DRY_RUN" == "true" ]; then
        log "[DRY-RUN] Seria instalado: $dashboard_title"
        return
    fi

    # Preparar payload
    local dashboard_content
    dashboard_content=$(jq --arg folder_uid "$folder_uid" '
        {
            dashboard: (. + {id: null, version: null}),
            folderId: null,
            folderUid: $folder_uid,
            message: "Updated by setup-dashboards.sh",
            overwrite: true
        }' "$dashboard_file")

    # Enviar para Grafana
    local response
    response=$(curl -s -X POST \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$dashboard_content" \
        "$GRAFANA_URL/api/dashboards/db")

    local status
    status=$(echo "$response" | jq -r '.status // .message // "unknown"')

    if [[ "$status" == "success" ]]; then
        success "Dashboard instalado: $dashboard_title"
    else
        error "Falha ao instalar $dashboard_title: $status"
    fi
}

# Função para processar todos os dashboards
process_dashboards() {
    local folder_uid="$1"

    log "Processando dashboards em: $DASHBOARD_DIR"

    if [ ! -d "$DASHBOARD_DIR" ]; then
        error "Diretório não encontrado: $DASHBOARD_DIR"
    fi

    local dashboard_count=0

    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        if [ -f "$dashboard_file" ]; then
            validate_dashboard "$dashboard_file"
            install_dashboard "$dashboard_file" "$folder_uid"
            ((dashboard_count++))
        fi
    done

    success "Processados $dashboard_count dashboards"
}

# Função para configurar datasources automaticamente
configure_datasources() {
    log "Configurando datasources automaticamente..."

    # Configuração de datasources padrão
    local prometheus_config='{
        "name": "Prometheus",
        "type": "prometheus",
        "url": "http://prometheus-stack-prometheus:9090",
        "access": "proxy",
        "isDefault": true,
        "jsonData": {
            "httpMethod": "POST",
            "exemplarTraceIdDestinations": [
                {
                    "name": "trace_id",
                    "datasourceUid": "jaeger",
                    "urlDisplayLabel": "View Trace"
                }
            ],
            "timeoutSeconds": 60,
            "prometheusType": "Prometheus",
            "prometheusVersion": "2.45.0",
            "incrementalQuerying": true,
            "disableMetricsLookup": false,
            "customQueryParameters": "",
            "cacheLevel": "High"
        }
    }'

    local jaeger_config='{
        "name": "Jaeger",
        "type": "jaeger",
        "url": "http://jaeger-query:16686",
        "access": "proxy",
        "uid": "jaeger",
        "jsonData": {
            "nodeGraph": {
                "enabled": true
            },
            "spanBar": {
                "type": "Tag",
                "tag": "http.status_code"
            },
            "search": {
                "hideSystemTags": false
            }
        }
    }'

    # Verificar datasources existentes
    local datasources_response
    datasources_response=$(curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
                              "$GRAFANA_URL/api/datasources")

    # Configurar Prometheus
    local prometheus_exists
    prometheus_exists=$(echo "$datasources_response" | jq -r '.[] | select(.type == "prometheus") | .name')

    if [ -z "$prometheus_exists" ] || [ "$prometheus_exists" == "null" ]; then
        log "Criando datasource Prometheus..."
        local prom_response
        prom_response=$(curl -s -X POST \
            -H "Authorization: Bearer $GRAFANA_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$prometheus_config" \
            "$GRAFANA_URL/api/datasources")

        local prom_status
        prom_status=$(echo "$prom_response" | jq -r '.message // .id // "unknown"')

        if [[ "$prom_status" =~ ^[0-9]+$ ]]; then
            success "Prometheus datasource criado (ID: $prom_status)"
        else
            warn "Erro ao criar Prometheus datasource: $prom_status"
        fi
    else
        log "Prometheus datasource já existe"
    fi

    # Configurar Jaeger
    local jaeger_exists
    jaeger_exists=$(echo "$datasources_response" | jq -r '.[] | select(.type == "jaeger") | .name')

    if [ -z "$jaeger_exists" ] || [ "$jaeger_exists" == "null" ]; then
        log "Criando datasource Jaeger..."
        local jaeger_response
        jaeger_response=$(curl -s -X POST \
            -H "Authorization: Bearer $GRAFANA_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$jaeger_config" \
            "$GRAFANA_URL/api/datasources")

        local jaeger_status
        jaeger_status=$(echo "$jaeger_response" | jq -r '.message // .id // "unknown"')

        if [[ "$jaeger_status" =~ ^[0-9]+$ ]]; then
            success "Jaeger datasource criado (ID: $jaeger_status)"
        else
            warn "Erro ao criar Jaeger datasource: $jaeger_status"
        fi
    else
        log "Jaeger datasource já existe"
    fi

    success "Configuração de datasources concluída"
}

# Função para testar dashboards
test_dashboards() {
    log "Testando dashboards instalados..."

    local dashboards_response
    dashboards_response=$(curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
                             "$GRAFANA_URL/api/search?type=dash-db&folderTitle=$FOLDER_NAME")

    local dashboard_count
    dashboard_count=$(echo "$dashboards_response" | jq '. | length')

    if [ "$dashboard_count" -gt 0 ]; then
        success "$dashboard_count dashboards encontrados no folder"

        # Listar dashboards
        echo "$dashboards_response" | jq -r '.[] | "  - " + .title + " (" + .uid + ")"'
    else
        warn "Nenhum dashboard encontrado no folder"
    fi
}

# Função para backup dos dashboards existentes
backup_dashboards() {
    local backup_dir="backups/dashboards-$(date +%Y%m%d-%H%M%S)"

    log "Criando backup em: $backup_dir"
    mkdir -p "$backup_dir"

    local dashboards_response
    dashboards_response=$(curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
                             "$GRAFANA_URL/api/search?type=dash-db")

    local backup_count=0

    while IFS= read -r dashboard; do
        local uid title
        uid=$(echo "$dashboard" | jq -r '.uid')
        title=$(echo "$dashboard" | jq -r '.title')

        if [ "$uid" != "null" ] && [ -n "$uid" ]; then
            local dashboard_json
            dashboard_json=$(curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
                                "$GRAFANA_URL/api/dashboards/uid/$uid")

            local filename
            filename=$(echo "$title" | sed 's/[^a-zA-Z0-9]/-/g' | tr '[:upper:]' '[:lower:]').json
            echo "$dashboard_json" | jq '.dashboard' > "$backup_dir/$filename"
            ((backup_count++))
        fi
    done < <(echo "$dashboards_response" | jq -c '.[]')

    success "Backup criado: $backup_count dashboards em $backup_dir"
}

# Função de ajuda
show_help() {
    cat << EOF
Neural Hive-Mind Dashboard Setup Script

Uso: $0 [opções]

Opções:
  -h, --help           Mostrar esta ajuda
  -u, --url URL        URL do Grafana (padrão: https://grafana.neural-hive.local)
  -k, --api-key KEY    Chave da API do Grafana
  -d, --dashboard-dir  Diretório com dashboards (padrão: monitoring/dashboards)
  -f, --folder-name    Nome do folder no Grafana (padrão: Neural Hive-Mind)
  -b, --backup         Criar backup dos dashboards existentes
  -t, --test-only      Apenas testar conectividade e listar dashboards
  --dry-run            Não fazer alterações, apenas mostrar o que seria feito

Variáveis de ambiente:
  GRAFANA_URL          URL do Grafana
  GRAFANA_API_KEY      Chave da API do Grafana
  DASHBOARD_DIR        Diretório com dashboards
  FOLDER_NAME          Nome do folder no Grafana
  DRY_RUN              true/false para dry run

Exemplos:
  $0 -k "glsa_xxx" -b                    # Com backup
  $0 --dry-run                           # Apenas mostrar o que seria feito
  GRAFANA_API_KEY="key" $0 --test-only   # Apenas testar
EOF
}

# Função principal
main() {
    local backup_enabled=false
    local test_only=false

    # Parse argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -u|--url)
                GRAFANA_URL="$2"
                shift 2
                ;;
            -k|--api-key)
                GRAFANA_API_KEY="$2"
                shift 2
                ;;
            -d|--dashboard-dir)
                DASHBOARD_DIR="$2"
                shift 2
                ;;
            -f|--folder-name)
                FOLDER_NAME="$2"
                shift 2
                ;;
            -b|--backup)
                backup_enabled=true
                shift
                ;;
            -t|--test-only)
                test_only=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            *)
                error "Opção desconhecida: $1"
                ;;
        esac
    done

    log "=== Neural Hive-Mind Dashboard Setup ==="
    log "Grafana URL: $GRAFANA_URL"
    log "Dashboard Dir: $DASHBOARD_DIR"
    log "Folder Name: $FOLDER_NAME"
    log "Dry Run: $DRY_RUN"
    log "Environment: ${ENVIRONMENT:-production}"

    # Verificações básicas
    check_dependencies
    check_grafana_connectivity
    configure_datasources

    if [ "$test_only" == "true" ]; then
        test_dashboards
        exit 0
    fi

    # Backup se solicitado
    if [ "$backup_enabled" == "true" ]; then
        backup_dashboards
    fi

    # Processar dashboards
    local folder_uid
    folder_uid=$(get_or_create_folder "$FOLDER_NAME")
    process_dashboards "$folder_uid"

    # Teste final
    test_dashboards

    success "Setup de dashboards concluído!"
}

# Executar se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi