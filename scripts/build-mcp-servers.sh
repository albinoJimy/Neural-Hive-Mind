#!/bin/bash
# Build MCP Server Docker Images
# Uses parent context (services/mcp-servers/) to include shared module
#
# Usage: ./scripts/build-mcp-servers.sh [server-name] [--push] [--tag TAG]
#
# Examples:
#   ./scripts/build-mcp-servers.sh                    # Build all servers
#   ./scripts/build-mcp-servers.sh trivy              # Build only trivy
#   ./scripts/build-mcp-servers.sh --push             # Build all and push
#   ./scripts/build-mcp-servers.sh trivy --push       # Build trivy and push

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_SERVERS_DIR="$PROJECT_ROOT/services/mcp-servers"
REGISTRY="${MCP_REGISTRY:-37.60.241.150:30500}"
TAG="${MCP_TAG:-1.0.0}"
PUSH_IMAGES=false
TARGET_SERVER=""

# All available MCP servers
ALL_SERVERS=("trivy-mcp-server" "sonarqube-mcp-server" "ai-codegen-mcp-server")

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH_IMAGES=true
            shift
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        trivy|trivy-mcp-server)
            TARGET_SERVER="trivy-mcp-server"
            shift
            ;;
        sonarqube|sonarqube-mcp-server)
            TARGET_SERVER="sonarqube-mcp-server"
            shift
            ;;
        ai-codegen|codegen|ai-codegen-mcp-server)
            TARGET_SERVER="ai-codegen-mcp-server"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [server-name] [--push] [--tag TAG] [--registry REGISTRY]"
            echo ""
            echo "Servers: trivy, sonarqube, ai-codegen (or full names with -mcp-server suffix)"
            echo ""
            echo "Options:"
            echo "  --push              Push images to registry after building"
            echo "  --tag TAG           Image tag (default: 1.0.0)"
            echo "  --registry REGISTRY Registry URL (default: 37.60.241.150:30500)"
            echo ""
            echo "Environment variables:"
            echo "  MCP_REGISTRY        Override default registry"
            echo "  MCP_TAG             Override default tag"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Determine which servers to build
if [[ -n "$TARGET_SERVER" ]]; then
    SERVERS=("$TARGET_SERVER")
else
    SERVERS=("${ALL_SERVERS[@]}")
fi

echo "=========================================="
echo "Build MCP Servers - Neural Hive-Mind"
echo "=========================================="
echo "Registry: $REGISTRY"
echo "Tag: $TAG"
echo "Push: $PUSH_IMAGES"
echo "Servers: ${SERVERS[*]}"
echo ""

# Verify shared module exists
if [[ ! -d "$MCP_SERVERS_DIR/shared" ]]; then
    echo "ERROR: Shared module not found at $MCP_SERVERS_DIR/shared"
    exit 1
fi

if [[ ! -f "$MCP_SERVERS_DIR/shared/mcp_base.py" ]]; then
    echo "ERROR: mcp_base.py not found in shared module"
    exit 1
fi

echo "Shared module verified at $MCP_SERVERS_DIR/shared"
echo ""

# Build function
build_server() {
    local server=$1
    local dockerfile="$MCP_SERVERS_DIR/$server/Dockerfile"
    local image_name="$REGISTRY/$server:$TAG"

    if [[ ! -f "$dockerfile" ]]; then
        echo "ERROR: Dockerfile not found: $dockerfile"
        return 1
    fi

    echo "----------------------------------------"
    echo "Building $server..."
    echo "  Dockerfile: $dockerfile"
    echo "  Context: $MCP_SERVERS_DIR"
    echo "  Image: $image_name"
    echo "----------------------------------------"

    # Build with parent context
    docker build \
        -f "$dockerfile" \
        -t "$image_name" \
        "$MCP_SERVERS_DIR"

    echo "$server built successfully!"

    if [[ "$PUSH_IMAGES" = true ]]; then
        echo "Pushing $image_name..."
        docker push "$image_name"
        echo "$server pushed successfully!"
    fi

    echo ""
}

# Build all selected servers
BUILD_SUCCESS=true
for server in "${SERVERS[@]}"; do
    if ! build_server "$server"; then
        BUILD_SUCCESS=false
        echo "FAILED: $server"
    fi
done

# Summary
echo "=========================================="
if [[ "$BUILD_SUCCESS" = true ]]; then
    echo "All MCP Server images built successfully!"
else
    echo "Some builds failed. Check output above."
    exit 1
fi
echo "=========================================="
echo ""
echo "Built images:"
for server in "${SERVERS[@]}"; do
    echo "  - $REGISTRY/$server:$TAG"
done
echo ""

# Verification command
echo "To verify the shared module in containers:"
echo "  docker run --rm $REGISTRY/${SERVERS[0]}:$TAG ls -la /app/shared/"
echo "  docker run --rm $REGISTRY/${SERVERS[0]}:$TAG python -c 'from shared.mcp_base import BaseMCPServer; print(\"OK\")'"
