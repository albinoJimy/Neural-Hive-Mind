#!/bin/bash
# Setup integration test environment for Worker Agents
# Usage: ./setup-integration-env.sh [--full|--kafka|--mock]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

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

# Parse arguments
PROFILE=""
case "${1:-}" in
    --full)
        PROFILE="--profile full"
        log_info "Starting with full profile (includes ArgoCD and SonarQube)"
        ;;
    --kafka)
        PROFILE="--profile kafka"
        log_info "Starting with Kafka profile"
        ;;
    --mock)
        PROFILE="--profile mock"
        log_info "Starting with mock profile"
        ;;
    *)
        log_info "Starting with minimal services (OPA, Redis)"
        ;;
esac

cd "$PROJECT_DIR"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    log_error "Docker or docker-compose not found. Please install Docker."
    exit 1
fi

# Determine docker compose command
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

log_info "Using compose command: $COMPOSE_CMD"

# Start services
log_info "Starting integration test services..."
$COMPOSE_CMD -f docker-compose.integration.yml up -d $PROFILE

# Wait for services to be healthy
log_info "Waiting for services to be ready..."
"$SCRIPT_DIR/wait-for-services.sh"

log_info "Integration test environment is ready!"
log_info ""
log_info "Services running:"
$COMPOSE_CMD -f docker-compose.integration.yml ps

log_info ""
log_info "To run tests:"
log_info "  cd $PROJECT_DIR"
log_info "  pytest tests/integration/ -m 'integration and not real_integration' -v"
log_info ""
log_info "To stop services:"
log_info "  $SCRIPT_DIR/teardown-integration-env.sh"
