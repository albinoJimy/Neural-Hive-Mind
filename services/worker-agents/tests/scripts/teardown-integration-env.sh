#!/bin/bash
# Teardown integration test environment for Worker Agents
# Usage: ./teardown-integration-env.sh [--volumes]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

cd "$PROJECT_DIR"

# Determine docker compose command
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

VOLUMES_FLAG=""
if [ "${1:-}" = "--volumes" ]; then
    VOLUMES_FLAG="-v"
    log_info "Removing volumes as well"
fi

log_info "Stopping integration test services..."
$COMPOSE_CMD -f docker-compose.integration.yml down $VOLUMES_FLAG --remove-orphans

log_info "Integration test environment stopped."
