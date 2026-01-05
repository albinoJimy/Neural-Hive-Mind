#!/bin/bash
# Wait for integration test services to be ready
# Usage: ./wait-for-services.sh [timeout_seconds]

set -e

TIMEOUT="${1:-120}"
START_TIME=$(date +%s)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_timeout() {
    local current_time=$(date +%s)
    local elapsed=$((current_time - START_TIME))
    if [ $elapsed -ge $TIMEOUT ]; then
        log_error "Timeout waiting for services after ${elapsed}s"
        exit 1
    fi
}

wait_for_http() {
    local name="$1"
    local url="$2"
    local max_attempts=30
    local attempt=0

    log_info "Waiting for $name at $url..."

    while [ $attempt -lt $max_attempts ]; do
        check_timeout
        if curl -sf "$url" > /dev/null 2>&1; then
            log_info "$name is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log_warn "$name not available at $url (may not be required)"
    return 1
}

wait_for_tcp() {
    local name="$1"
    local host="$2"
    local port="$3"
    local max_attempts=30
    local attempt=0

    log_info "Waiting for $name at $host:$port..."

    while [ $attempt -lt $max_attempts ]; do
        check_timeout
        if nc -z "$host" "$port" 2>/dev/null; then
            log_info "$name is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log_warn "$name not available at $host:$port (may not be required)"
    return 1
}

log_info "Starting service health checks (timeout: ${TIMEOUT}s)..."

# Wait for OPA (always required for mock mode)
wait_for_http "OPA" "http://localhost:8181/health" || true

# Wait for Redis
wait_for_tcp "Redis" "localhost" "6379" || true

# Optional services - check if they're running
if docker ps | grep -q worker-agents-argocd; then
    wait_for_http "ArgoCD" "http://localhost:8081/healthz" || true
fi

if docker ps | grep -q worker-agents-sonarqube; then
    wait_for_http "SonarQube" "http://localhost:9000/api/system/status" || true
fi

if docker ps | grep -q worker-agents-kafka; then
    wait_for_tcp "Kafka" "localhost" "9092" || true
fi

log_info "Service health checks completed"
