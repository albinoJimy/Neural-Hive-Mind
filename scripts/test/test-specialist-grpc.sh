#!/bin/bash

# Test gRPC interface of a specialist using grpcurl
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parameters
SPECIALIST="${1:-business}"
NAMESPACE="${2:-specialist-${SPECIALIST}}"
GRPC_PORT=50051
LOG_DIR="logs"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Testing Specialist gRPC Interface${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Specialist: $SPECIALIST"
echo "Namespace: $NAMESPACE"
echo ""

# Create logs directory
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/specialist-${SPECIALIST}-grpc-test.log"

# Check if grpcurl is available
if ! command -v grpcurl &> /dev/null; then
  echo -e "${RED}✗ grpcurl not found${NC}"
  echo ""
  echo -e "${YELLOW}Install grpcurl:${NC}"
  echo "  Go: go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"
  echo "  Homebrew (macOS): brew install grpcurl"
  echo "  Docker: docker run fullstorydev/grpcurl -plaintext ..."
  echo ""
  exit 1
fi

# Check if jq is available (optional, for formatting)
HAS_JQ=false
if command -v jq &> /dev/null; then
  HAS_JQ=true
fi

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to get grpcurl options (checks reflection once port-forward is active)
get_grpcurl_opts() {
  local opts="-plaintext"
  # Try reflection first
  if ! grpcurl -plaintext localhost:$GRPC_PORT list >/dev/null 2>&1; then
    # Fallback to proto files
    opts="$opts -import-path schemas/specialist-opinion -proto specialist.proto"
  fi
  echo "$opts"
}

# Function to format JSON output
format_json() {
  if [ "$HAS_JQ" = true ]; then
    echo "$1" | jq .
  else
    echo "$1"
  fi
}

# Portable base64 encoding without line wrapping
b64_nowrap() {
  if base64 -w 0 </dev/null >/dev/null 2>&1; then
    # GNU base64
    base64 -w 0
  else
    # BSD/macOS base64
    base64 | tr -d '\n'
  fi
}

# Test 1: HealthCheck
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 1: HealthCheck${NC}"
echo -e "${GREEN}========================================${NC}"

# Start port-forward
echo -e "${YELLOW}Starting port-forward...${NC}"
kubectl port-forward -n "$NAMESPACE" "svc/specialist-${SPECIALIST}" $GRPC_PORT:$GRPC_PORT &>/dev/null &
PF_PID=$!

# Wait for port-forward to be ready
sleep 3

# Get grpcurl options (with reflection fallback)
GRPCURL_OPTS=$(get_grpcurl_opts)

# Execute HealthCheck
echo -e "${YELLOW}Calling HealthCheck...${NC}"
HEALTH_RESPONSE=$(grpcurl $GRPCURL_OPTS \
  -d "{\"service_name\": \"specialist-${SPECIALIST}\"}" \
  localhost:$GRPC_PORT \
  neural_hive.specialist.SpecialistService/HealthCheck 2>&1)

if echo "$HEALTH_RESPONSE" | grep -q "SERVING"; then
  echo -e "${GREEN}✓ HealthCheck passed${NC}"
  echo ""
  format_json "$HEALTH_RESPONSE"
  echo "$HEALTH_RESPONSE" >> "$LOG_FILE"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo -e "${RED}✗ HealthCheck failed${NC}"
  echo ""
  echo "$HEALTH_RESPONSE"
  echo "$HEALTH_RESPONSE" >> "$LOG_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Kill port-forward
kill $PF_PID &>/dev/null || true
sleep 1

echo ""

# Test 2: GetCapabilities
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 2: GetCapabilities${NC}"
echo -e "${GREEN}========================================${NC}"

# Start port-forward
echo -e "${YELLOW}Starting port-forward...${NC}"
kubectl port-forward -n "$NAMESPACE" "svc/specialist-${SPECIALIST}" $GRPC_PORT:$GRPC_PORT &>/dev/null &
PF_PID=$!

# Wait for port-forward to be ready
sleep 3

# Execute GetCapabilities
echo -e "${YELLOW}Calling GetCapabilities...${NC}"
CAPABILITIES_RESPONSE=$(grpcurl $GRPCURL_OPTS \
  -d '{}' \
  localhost:$GRPC_PORT \
  neural_hive.specialist.SpecialistService/GetCapabilities 2>&1)

if echo "$CAPABILITIES_RESPONSE" | grep -q "specialist_type"; then
  echo -e "${GREEN}✓ GetCapabilities passed${NC}"
  echo ""
  echo -e "${YELLOW}Specialist Capabilities:${NC}"
  format_json "$CAPABILITIES_RESPONSE"
  echo "$CAPABILITIES_RESPONSE" >> "$LOG_FILE"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo -e "${RED}✗ GetCapabilities failed${NC}"
  echo ""
  echo "$CAPABILITIES_RESPONSE"
  echo "$CAPABILITIES_RESPONSE" >> "$LOG_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Kill port-forward
kill $PF_PID &>/dev/null || true
sleep 1

echo ""

# Test 3: EvaluatePlan (smoke test)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 3: EvaluatePlan (Smoke Test)${NC}"
echo -e "${GREEN}========================================${NC}"

# Create test plan payload
TEST_PLAN_JSON=$(cat <<'EOF'
{
  "tasks": [
    {
      "id": "task-1",
      "description": "Test task for gRPC validation",
      "type": "api-development"
    }
  ],
  "metadata": {
    "test": true
  }
}
EOF
)

# Base64 encode the plan
COGNITIVE_PLAN_B64=$(echo "$TEST_PLAN_JSON" | b64_nowrap)

# Create request payload
TEST_REQUEST=$(cat <<EOF
{
  "plan_id": "test-plan-$(date +%s)",
  "intent_id": "test-intent-$(date +%s)",
  "correlation_id": "test-corr-$(date +%s)",
  "trace_id": "test-trace-$(date +%s)",
  "cognitive_plan": "$COGNITIVE_PLAN_B64",
  "context": {"test": "true"},
  "timeout_ms": 5000
}
EOF
)

# Start port-forward
echo -e "${YELLOW}Starting port-forward...${NC}"
kubectl port-forward -n "$NAMESPACE" "svc/specialist-${SPECIALIST}" $GRPC_PORT:$GRPC_PORT &>/dev/null &
PF_PID=$!

# Wait for port-forward to be ready
sleep 3

# Execute EvaluatePlan
echo -e "${YELLOW}Calling EvaluatePlan...${NC}"
EVALUATE_RESPONSE=$(grpcurl $GRPCURL_OPTS \
  -d "$TEST_REQUEST" \
  localhost:$GRPC_PORT \
  neural_hive.specialist.SpecialistService/EvaluatePlan 2>&1)

if echo "$EVALUATE_RESPONSE" | grep -q "opinionId"; then
  echo -e "${GREEN}✓ EvaluatePlan passed${NC}"
  echo ""
  echo -e "${YELLOW}Specialist Opinion:${NC}"
  format_json "$EVALUATE_RESPONSE"
  echo "$EVALUATE_RESPONSE" >> "$LOG_FILE"
  TESTS_PASSED=$((TESTS_PASSED + 1))

  # Extract and display key metrics
  if [ "$HAS_JQ" = true ]; then
    CONFIDENCE=$(echo "$EVALUATE_RESPONSE" | jq -r '.opinion.confidenceScore // "N/A"')
    RISK=$(echo "$EVALUATE_RESPONSE" | jq -r '.opinion.riskScore // "N/A"')
    RECOMMENDATION=$(echo "$EVALUATE_RESPONSE" | jq -r '.opinion.recommendation // "N/A"')

    echo ""
    echo -e "${YELLOW}Key Metrics:${NC}"
    echo "  Confidence Score: $CONFIDENCE"
    echo "  Risk Score: $RISK"
    echo "  Recommendation: $RECOMMENDATION"
  fi
else
  echo -e "${RED}✗ EvaluatePlan failed${NC}"
  echo ""
  echo "$EVALUATE_RESPONSE"
  echo "$EVALUATE_RESPONSE" >> "$LOG_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Kill port-forward
kill $PF_PID &>/dev/null || true
sleep 1

echo ""

# Test summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}/3"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}/3"
echo ""
echo -e "Log file: ${YELLOW}$LOG_FILE${NC}"
echo ""

if [ $TESTS_FAILED -gt 0 ]; then
  echo -e "${RED}Some tests failed${NC}"
  exit 1
else
  echo -e "${GREEN}All gRPC tests passed!${NC}"
  exit 0
fi
