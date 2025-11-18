#!/bin/bash
# Script para importar dashboards do Grafana

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
DASHBOARDS_DIR="${DASHBOARDS_DIR:-$PROJECT_ROOT/monitoring/dashboards}"

# Configurações
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
FOLDER_NAME="${FOLDER_NAME:-Neural Hive-Mind}"

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Verificar conectividade com Grafana
log "Verificando conectividade com Grafana..."
if ! curl -s --connect-timeout 5 "$GRAFANA_URL/api/health" > /dev/null; then
    error "Grafana não está acessível em $GRAFANA_URL"
    error "Execute: kubectl port-forward -n neural-hive-observability svc/neural-hive-grafana 3000:80"
    exit 1
fi

success "Grafana acessível"

# Criar folder no Grafana
log "Criando folder '$FOLDER_NAME'..."
FOLDER_RESPONSE=$(curl -s -X POST "$GRAFANA_URL/api/folders" \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
    -d "{\"title\":\"$FOLDER_NAME\"}" 2>/dev/null || echo '{}')

FOLDER_UID=$(echo "$FOLDER_RESPONSE" | jq -r '.uid // empty')

if [ -z "$FOLDER_UID" ]; then
    # Folder pode já existir, tentar buscar
    FOLDER_UID=$(curl -s "$GRAFANA_URL/api/folders" \
        -u "$GRAFANA_USER:$GRAFANA_PASSWORD" | \
        jq -r ".[] | select(.title==\"$FOLDER_NAME\") | .uid" || echo "")
fi

if [ -n "$FOLDER_UID" ]; then
    success "Folder UID: $FOLDER_UID"
else
    warning "Não foi possível criar/encontrar folder, usando General"
    FOLDER_UID=""
fi

# Importar dashboards
log "Importando dashboards de $DASHBOARDS_DIR..."

IMPORTED=0
FAILED=0

for dashboard_file in "$DASHBOARDS_DIR"/*.json; do
    if [ ! -f "$dashboard_file" ]; then
        continue
    fi

    DASHBOARD_NAME=$(basename "$dashboard_file" .json)
    log "Importando: $DASHBOARD_NAME"

    # Ler dashboard JSON
    DASHBOARD_JSON=$(cat "$dashboard_file")

    # Preparar payload
    PAYLOAD=$(jq -n \
        --arg folderUid "$FOLDER_UID" \
        --argjson dashboard "$DASHBOARD_JSON" \
        '{
            dashboard: $dashboard,
            folderUid: $folderUid,
            overwrite: true
        }')

    # Importar via API
    RESPONSE=$(curl -s -X POST "$GRAFANA_URL/api/dashboards/db" \
        -H "Content-Type: application/json" \
        -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
        -d "$PAYLOAD")

    STATUS=$(echo "$RESPONSE" | jq -r '.status // "error"')

    if [ "$STATUS" = "success" ]; then
        DASHBOARD_UID=$(echo "$RESPONSE" | jq -r '.uid')
        DASHBOARD_URL=$(echo "$RESPONSE" | jq -r '.url')
        success "  ✓ $DASHBOARD_NAME (UID: $DASHBOARD_UID)"
        ((IMPORTED++))
    else
        MESSAGE=$(echo "$RESPONSE" | jq -r '.message // "Unknown error"')
        error "  ✗ $DASHBOARD_NAME: $MESSAGE"
        ((FAILED++))
    fi
done

echo ""
log "Resumo da importação:"
log "  Importados: $IMPORTED"
log "  Falhas: $FAILED"

if [ $FAILED -eq 0 ]; then
    success "Todos os dashboards foram importados com sucesso!"
    exit 0
else
    warning "Alguns dashboards falharam na importação"
    exit 1
fi
