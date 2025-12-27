#!/bin/bash
set -e

SERVICES=(
    "queen-agent"
    "execution-ticket-service"
    "guard-agents"
    "worker-agents"
    "scout-agents"
    "self-healing-engine"
    "mcp-tool-catalog"
    "service-registry"
    "gateway-intencoes"
)

echo "🔨 Building modified services..."
for service in "${SERVICES[@]}"; do
    echo "Building $service..."
    docker build -t neural-hive-mind/$service:test \
        -f services/$service/Dockerfile \
        --build-arg VERSION=test \
        . || exit 1
    echo "✅ $service built successfully"
done

echo "✅ All services built successfully!"
