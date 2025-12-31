#!/bin/bash
# Testa MCP Servers do Neural Hive-Mind
# Uso: ./scripts/test-mcp-servers.sh [--local] [server]

set -e

NAMESPACE="neural-hive-mcp"
LOCAL_MODE=false
TARGET_SERVER=""

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            LOCAL_MODE=true
            shift
            ;;
        trivy|sonarqube|codegen)
            TARGET_SERVER=$1
            shift
            ;;
        *)
            echo "Uso: $0 [--local] [trivy|sonarqube|codegen]"
            exit 1
            ;;
    esac
done

# Função para testar um servidor MCP
test_mcp_server() {
    local name=$1
    local port=$2
    local host=$3

    echo ""
    echo "=========================================="
    echo "Testing $name at $host:$port"
    echo "=========================================="

    # Health check
    echo ""
    echo "1. Health Check..."
    response=$(curl -s --max-time 10 "http://$host:$port/health" || echo '{"error": "connection failed"}')
    echo "Response: $response"

    if echo "$response" | grep -q "healthy"; then
        echo "✓ Health check passed"
    else
        echo "✗ Health check failed"
        return 1
    fi

    # Ready check
    echo ""
    echo "2. Ready Check..."
    response=$(curl -s --max-time 10 "http://$host:$port/ready" || echo '{"error": "connection failed"}')
    echo "Response: $response"

    if echo "$response" | grep -q "ready"; then
        echo "✓ Ready check passed"
    else
        echo "✗ Ready check failed"
    fi

    # Initialize
    echo ""
    echo "3. MCP Initialize..."
    response=$(curl -s --max-time 10 -X POST "http://$host:$port" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' || echo '{"error": "connection failed"}')
    echo "Response: $response"

    if echo "$response" | grep -q "result"; then
        echo "✓ Initialize passed"
    else
        echo "✗ Initialize failed"
    fi

    # List Tools
    echo ""
    echo "4. List Tools..."
    response=$(curl -s --max-time 10 -X POST "http://$host:$port" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' || echo '{"error": "connection failed"}')
    echo "Response: $response"

    if echo "$response" | grep -q "tools"; then
        echo "✓ List tools passed"
    else
        echo "✗ List tools failed"
    fi

    echo ""
    echo "=========================================="
    echo "$name tests completed!"
    echo "=========================================="
}

# Função para port-forward e testar
test_with_port_forward() {
    local service=$1
    local local_port=$2

    echo "Starting port-forward for $service..."

    # Kill any existing port-forward
    pkill -f "port-forward.*$service" 2>/dev/null || true
    sleep 1

    # Start port-forward in background
    kubectl port-forward -n "$NAMESPACE" "svc/$service" "$local_port:3000" &
    PF_PID=$!
    sleep 3

    # Test
    test_mcp_server "$service" "$local_port" "localhost"

    # Kill port-forward
    kill $PF_PID 2>/dev/null || true
}

# Função para testar diretamente no cluster
test_in_cluster() {
    local service=$1
    local host="$service.$NAMESPACE.svc.cluster.local"

    # Usar kubectl exec para fazer requisições de dentro do cluster
    echo ""
    echo "=========================================="
    echo "Testing $service in cluster"
    echo "=========================================="

    # Health check via kubectl exec
    echo ""
    echo "1. Health Check..."
    kubectl run curl-test-$$ --rm -it --restart=Never \
        --image=curlimages/curl:latest \
        -n "$NAMESPACE" \
        -- curl -s "http://$host:3000/health" 2>/dev/null || echo "Failed"

    echo ""
    echo "2. List Tools..."
    kubectl run curl-test-$$ --rm -it --restart=Never \
        --image=curlimages/curl:latest \
        -n "$NAMESPACE" \
        -- curl -s -X POST "http://$host:3000" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null || echo "Failed"
}

echo "=========================================="
echo "MCP Servers Test Suite"
echo "=========================================="
echo "Mode: $([ "$LOCAL_MODE" = true ] && echo 'Local (port-forward)' || echo 'In-Cluster')"
echo ""

# Verificar pods
echo "Checking pods in $NAMESPACE..."
kubectl get pods -n "$NAMESPACE"
echo ""

# Testar servidores
if [ -z "$TARGET_SERVER" ] || [ "$TARGET_SERVER" = "trivy" ]; then
    if [ "$LOCAL_MODE" = true ]; then
        test_with_port_forward "trivy-mcp-server" 3001
    else
        test_in_cluster "trivy-mcp-server"
    fi
fi

if [ -z "$TARGET_SERVER" ] || [ "$TARGET_SERVER" = "sonarqube" ]; then
    if [ "$LOCAL_MODE" = true ]; then
        test_with_port_forward "sonarqube-mcp-server" 3002
    else
        test_in_cluster "sonarqube-mcp-server"
    fi
fi

if [ -z "$TARGET_SERVER" ] || [ "$TARGET_SERVER" = "codegen" ]; then
    if [ "$LOCAL_MODE" = true ]; then
        test_with_port_forward "ai-codegen-mcp-server" 3003
    else
        test_in_cluster "ai-codegen-mcp-server"
    fi
fi

echo ""
echo "=========================================="
echo "All tests completed!"
echo "=========================================="
