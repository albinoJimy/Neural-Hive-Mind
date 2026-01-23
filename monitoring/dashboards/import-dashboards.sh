#!/bin/bash
# Script para importar dashboards Grafana via API

set -e

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"

DASHBOARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed."
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed."
        exit 1
    fi
}

# Wait for Grafana to be ready
wait_for_grafana() {
    local max_attempts=30
    local attempt=1

    log_info "Waiting for Grafana to be ready at ${GRAFANA_URL}..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s "${GRAFANA_URL}/api/health" > /dev/null 2>&1; then
            log_info "Grafana is ready!"
            return 0
        fi
        log_warn "Attempt $attempt/$max_attempts: Grafana not ready yet..."
        sleep 2
        ((attempt++))
    done

    log_error "Grafana did not become ready after $max_attempts attempts"
    return 1
}

# Import a single dashboard
import_dashboard() {
    local dashboard_file="$1"
    local dashboard_name=$(basename "$dashboard_file" .json)

    log_info "Importing dashboard: $dashboard_name"

    # Check if file exists
    if [ ! -f "$dashboard_file" ]; then
        log_error "Dashboard file not found: $dashboard_file"
        return 1
    fi

    # Prepare payload - extract dashboard content and wrap in import format
    local dashboard_content=$(cat "$dashboard_file")

    # Check if the file already has "dashboard" wrapper
    if echo "$dashboard_content" | jq -e '.dashboard' > /dev/null 2>&1; then
        # Extract the inner dashboard object
        dashboard_content=$(echo "$dashboard_content" | jq '.dashboard')
    fi

    # Create import payload
    local payload=$(jq -n \
        --argjson dashboard "$dashboard_content" \
        '{dashboard: $dashboard, overwrite: true, message: "Imported via script"}')

    # Import via API
    local response
    local http_code

    if [ -n "$GRAFANA_API_KEY" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Authorization: Bearer $GRAFANA_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "${GRAFANA_URL}/api/dashboards/db")
    else
        response=$(curl -s -w "\n%{http_code}" -X POST \
            -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "${GRAFANA_URL}/api/dashboards/db")
    fi

    # Extract HTTP code from response
    http_code=$(echo "$response" | tail -n1)
    response=$(echo "$response" | sed '$d')

    if [ "$http_code" -eq 200 ]; then
        local uid=$(echo "$response" | jq -r '.uid // "unknown"')
        local url=$(echo "$response" | jq -r '.url // "unknown"')
        log_info "Dashboard $dashboard_name imported successfully"
        log_info "  UID: $uid"
        log_info "  URL: ${GRAFANA_URL}${url}"
        return 0
    else
        log_error "Failed to import dashboard $dashboard_name (HTTP $http_code)"
        log_error "Response: $response"
        return 1
    fi
}

# Import all dashboards in directory
import_all_dashboards() {
    local count=0
    local failed=0

    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        if [ -f "$dashboard_file" ]; then
            if import_dashboard "$dashboard_file"; then
                ((count++))
            else
                ((failed++))
            fi
        fi
    done

    echo ""
    log_info "Import complete: $count dashboards imported, $failed failed"
}

# Import specific dashboard(s)
import_specific_dashboards() {
    local count=0
    local failed=0

    for dashboard_name in "$@"; do
        local dashboard_file="$DASHBOARD_DIR/${dashboard_name}.json"

        if [ ! -f "$dashboard_file" ]; then
            # Try with path as-is
            dashboard_file="$dashboard_name"
        fi

        if [ -f "$dashboard_file" ]; then
            if import_dashboard "$dashboard_file"; then
                ((count++))
            else
                ((failed++))
            fi
        else
            log_error "Dashboard file not found: $dashboard_name"
            ((failed++))
        fi
    done

    echo ""
    log_info "Import complete: $count dashboards imported, $failed failed"
}

# Show usage
usage() {
    echo "Usage: $0 [OPTIONS] [DASHBOARD_NAMES...]"
    echo ""
    echo "Import Grafana dashboards from JSON files."
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -a, --all      Import all dashboards in the directory"
    echo "  -w, --wait     Wait for Grafana to be ready before importing"
    echo ""
    echo "Environment Variables:"
    echo "  GRAFANA_URL      Grafana URL (default: http://localhost:3000)"
    echo "  GRAFANA_API_KEY  API key for authentication"
    echo "  GRAFANA_USER     Username for basic auth (default: admin)"
    echo "  GRAFANA_PASSWORD Password for basic auth (default: admin)"
    echo ""
    echo "Examples:"
    echo "  $0 ml-feedback-retraining              # Import specific dashboard"
    echo "  $0 -a                                   # Import all dashboards"
    echo "  $0 -w ml-feedback-retraining           # Wait for Grafana, then import"
    echo ""
}

# Main
main() {
    local import_all=false
    local wait_grafana=false
    local dashboards=()

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -a|--all)
                import_all=true
                shift
                ;;
            -w|--wait)
                wait_grafana=true
                shift
                ;;
            *)
                dashboards+=("$1")
                shift
                ;;
        esac
    done

    check_dependencies

    if [ "$wait_grafana" = true ]; then
        wait_for_grafana || exit 1
    fi

    if [ "$import_all" = true ]; then
        import_all_dashboards
    elif [ ${#dashboards[@]} -gt 0 ]; then
        import_specific_dashboards "${dashboards[@]}"
    else
        # Default: import ml-feedback-retraining dashboard
        import_dashboard "$DASHBOARD_DIR/ml-feedback-retraining.json"
    fi
}

main "$@"
