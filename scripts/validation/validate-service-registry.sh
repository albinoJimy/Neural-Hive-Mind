#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Validating Service Registry Implementation ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success_count=0
warning_count=0
error_count=0

check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((success_count++))
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((warning_count++))
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((error_count++))
}

# 1. Check proto stubs exist
echo "1. Checking proto stubs..."
PROTO_FILES=(
    "services/service-registry/src/proto/service_registry_pb2.py"
    "services/service-registry/src/proto/service_registry_pb2_grpc.py"
    "libraries/neural_hive_integration/neural_hive_integration/proto_stubs/service_registry_pb2.py"
    "libraries/neural_hive_integration/neural_hive_integration/proto_stubs/service_registry_pb2_grpc.py"
)

for file in "${PROTO_FILES[@]}"; do
    if [ -f "$ROOT_DIR/$file" ]; then
        check_pass "Proto stub exists: $file"
    else
        check_fail "Proto stub missing: $file"
    fi
done

# 2. Check compile script exists and is executable
echo ""
echo "2. Checking compile script..."
COMPILE_SCRIPT="services/service-registry/scripts/compile_protos.sh"
if [ -f "$ROOT_DIR/$COMPILE_SCRIPT" ]; then
    check_pass "Compile script exists: $COMPILE_SCRIPT"
    if [ -x "$ROOT_DIR/$COMPILE_SCRIPT" ]; then
        check_pass "Compile script is executable"
    else
        check_warn "Compile script is not executable"
    fi
else
    check_fail "Compile script missing: $COMPILE_SCRIPT"
fi

# 3. Check clients use neural_hive_integration imports
echo ""
echo "3. Checking client imports..."
SERVICES=(
    "guard-agents"
    "analyst-agents"
    "worker-agents"
    "scout-agents"
    "optimizer-agents"
    "queen-agent"
    "mcp-tool-catalog"
    "code-forge"
    "orchestrator-dynamic"
    "self-healing-engine"
)

for service in "${SERVICES[@]}"; do
    client_file="$ROOT_DIR/services/$service/src/clients/service_registry_client.py"
    if [ -f "$client_file" ]; then
        if grep -q "neural_hive_integration" "$client_file"; then
            check_pass "$service uses neural_hive_integration imports"
        else
            check_warn "$service does not use neural_hive_integration imports"
        fi

        # Check for TODO placeholders
        if grep -q "TODO.*proto" "$client_file" 2>/dev/null; then
            check_warn "$service still has TODO placeholders"
        fi
    else
        check_warn "$service client file not found: $client_file"
    fi
done

# 4. Check integration tests exist
echo ""
echo "4. Checking integration tests..."
TEST_FILES=(
    "services/guard-agents/tests/integration/test_service_registry_integration.py"
    "services/analyst-agents/tests/integration/test_service_registry_client.py"
)

for file in "${TEST_FILES[@]}"; do
    if [ -f "$ROOT_DIR/$file" ]; then
        check_pass "Integration test exists: $file"
    else
        check_warn "Integration test missing: $file"
    fi
done

# 5. Check Makefile target
echo ""
echo "5. Checking Makefile targets..."
if grep -q "proto-service-registry" "$ROOT_DIR/Makefile"; then
    check_pass "Makefile has proto-service-registry target"
else
    check_fail "Makefile missing proto-service-registry target"
fi

# 6. Check README exists
echo ""
echo "6. Checking documentation..."
if [ -f "$ROOT_DIR/services/service-registry/README.md" ]; then
    check_pass "Service Registry README.md exists"
else
    check_warn "Service Registry README.md missing"
fi

# Summary
echo ""
echo "=== Validation Summary ==="
echo -e "  ${GREEN}Passed:${NC} $success_count"
echo -e "  ${YELLOW}Warnings:${NC} $warning_count"
echo -e "  ${RED}Errors:${NC} $error_count"
echo ""

if [ $error_count -gt 0 ]; then
    echo -e "${RED}Validation FAILED${NC} - $error_count error(s) found"
    exit 1
elif [ $warning_count -gt 0 ]; then
    echo -e "${YELLOW}Validation PASSED with warnings${NC} - $warning_count warning(s)"
    exit 0
else
    echo -e "${GREEN}Validation PASSED${NC} - All checks successful!"
    exit 0
fi
