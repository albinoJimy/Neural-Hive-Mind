#!/bin/bash

SERVICES=(
    "queen-agent:8000"
    "execution-ticket-service:8000"
    "guard-agents:8080"
    "worker-agents:8080"
    "scout-agents:8000"
    "self-healing-engine:8080"
    "mcp-tool-catalog:8080"
    "service-registry:50051"
    "gateway-intencoes:8000"
)

for service_port in "${SERVICES[@]}"; do
    IFS=':' read -r service port <<< "$service_port"
    echo "Testing $service..."
    
    # Start container
    docker run -d --name test-$service \
        -p $port:$port \
        neural-hive-mind/$service:test
    
    # Wait for startup
    sleep 10
    
    # Check if running
    if docker ps | grep -q test-$service; then
        echo "✅ $service started successfully"
    else
        echo "❌ $service failed to start"
        docker logs test-$service
    fi
    
    # Cleanup
    docker stop test-$service
    docker rm test-$service
done
