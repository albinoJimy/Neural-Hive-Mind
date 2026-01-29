#!/bin/bash

# ==============================================================================
# Test gRPC Specialists - Direct Invocation with grpcurl
# ==============================================================================
# Purpose: Test EvaluatePlan method on all 5 specialists using grpcurl
# References:
#   - schemas/specialist-opinion/specialist.proto
#   - services/consensus-engine/src/clients/specialists_grpc_client.py
#   - test-grpc-specialists.sh
# ==============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-neural-hive}"
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
PASSED=0
FAILED=0

# Results storage
declare -A RESULTS_SECONDS
declare -A RESULTS_NANOS

echo "========================================"
echo "Test gRPC Direct - Specialists"
echo "Timestamp: $(date -Iseconds)"
echo "========================================"
echo ""

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"
if ! command -v grpcurl &> /dev/null; then
    echo -e "${RED}✗ grpcurl not found${NC}"
    echo "Install with: go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}✗ jq not found${NC}"
    echo "Install with: apt-get install jq"
    exit 1
fi

echo -e "${GREEN}✓ grpcurl found: $(command -v grpcurl)${NC}"
echo -e "${GREEN}✓ jq found: $(command -v jq)${NC}"
echo ""

# Prepare test payload
echo -e "${BLUE}Preparing test payload...${NC}"
COGNITIVE_PLAN_JSON='{"plan_id":"test-plan-isolated-001","intent_id":"test-intent-001","version":"1.0.0"}'
# Portable base64 encoding (works on both GNU and BSD base64)
COGNITIVE_PLAN_BASE64=$(printf '%s' "$COGNITIVE_PLAN_JSON" | base64 | tr -d '\n')

cat > /tmp/evaluate_plan_request.json <<EOF
{
  "planId": "test-plan-isolated-001",
  "intentId": "test-intent-001",
  "correlationId": "test-correlation-001",
  "traceId": "test-trace-001",
  "spanId": "test-span-001",
  "cognitivePlan": "$COGNITIVE_PLAN_BASE64",
  "planVersion": "1.0.0",
  "context": {
    "test": "true"
  },
  "timeoutMs": 30000
}
EOF

echo -e "${GREEN}✓ Payload created: /tmp/evaluate_plan_request.json${NC}"
echo ""

# Test each specialist
for spec in "${SPECIALISTS[@]}"; do
    SERVICE="specialist-${spec}.specialist-${spec}.svc.cluster.local:50051"

    echo "========================================"
    echo -e "${YELLOW}Testing Specialist: ${spec}${NC}"
    echo "Service: $SERVICE"
    echo "========================================"
    echo ""

    SPEC_PASSED=0
    SPEC_FAILED=0

    # Test 1: List services
    echo -e "${BLUE}[Test 1/5] Listing services...${NC}"
    if SERVICES_OUTPUT=$(grpcurl -plaintext "$SERVICE" list 2>&1); then
        if echo "$SERVICES_OUTPUT" | grep -q "neural_hive.specialist.SpecialistService"; then
            echo -e "${GREEN}✓ Service found: neural_hive.specialist.SpecialistService${NC}"
            ((SPEC_PASSED++))
        else
            echo -e "${RED}✗ Service not found in output${NC}"
            echo "$SERVICES_OUTPUT"
            ((SPEC_FAILED++))
        fi
    else
        echo -e "${RED}✗ Failed to list services${NC}"
        echo "$SERVICES_OUTPUT"
        ((SPEC_FAILED++))
    fi
    echo ""

    # Test 2: Describe EvaluatePlan
    echo -e "${BLUE}[Test 2/5] Describing EvaluatePlan method...${NC}"
    if DESCRIBE_OUTPUT=$(grpcurl -plaintext "$SERVICE" describe neural_hive.specialist.SpecialistService.EvaluatePlan 2>&1); then
        if echo "$DESCRIBE_OUTPUT" | grep -q "EvaluatePlanRequest" && echo "$DESCRIBE_OUTPUT" | grep -q "EvaluatePlanResponse"; then
            echo -e "${GREEN}✓ Method signature validated${NC}"
            ((SPEC_PASSED++))
        else
            echo -e "${RED}✗ Invalid method signature${NC}"
            echo "$DESCRIBE_OUTPUT"
            ((SPEC_FAILED++))
        fi
    else
        echo -e "${RED}✗ Failed to describe method${NC}"
        echo "$DESCRIBE_OUTPUT"
        ((SPEC_FAILED++))
    fi
    echo ""

    # Test 3: Invoke EvaluatePlan
    echo -e "${BLUE}[Test 3/5] Invoking EvaluatePlan...${NC}"
    RESPONSE_FILE="/tmp/grpc_response_${spec}.json"
    if RESPONSE=$(timeout 35s grpcurl -plaintext -H 'grpc-timeout: 30S' -d @/tmp/evaluate_plan_request.json "$SERVICE" neural_hive.specialist.SpecialistService/EvaluatePlan 2>&1); then
        if [ -n "$RESPONSE" ]; then
            echo "$RESPONSE" > "$RESPONSE_FILE"
            echo -e "${GREEN}✓ Response received and saved to $RESPONSE_FILE${NC}"
            ((SPEC_PASSED++))
        else
            echo -e "${RED}✗ Empty response${NC}"
            ((SPEC_FAILED++))
        fi
    else
        echo -e "${RED}✗ Failed to invoke EvaluatePlan${NC}"
        echo "$RESPONSE"
        ((SPEC_FAILED++))
        continue
    fi
    echo ""

    # Test 4: Validate response structure
    echo -e "${BLUE}[Test 4/5] Validating response structure...${NC}"
    OPINION_ID=$(echo "$RESPONSE" | jq -r '.opinionId // empty')
    SPECIALIST_TYPE=$(echo "$RESPONSE" | jq -r '.specialistType // empty')
    SPECIALIST_VERSION=$(echo "$RESPONSE" | jq -r '.specialistVersion // empty')
    EVALUATED_AT=$(echo "$RESPONSE" | jq -r '.evaluatedAt // empty')
    PROCESSING_TIME=$(echo "$RESPONSE" | jq -r '.processingTimeMs // empty')

    TEST_4_PASSED=true

    # Validate basic fields
    if [ -n "$OPINION_ID" ] && [ -n "$SPECIALIST_TYPE" ] && [ -n "$EVALUATED_AT" ] && [ -n "$PROCESSING_TIME" ]; then
        echo -e "${GREEN}✓ Basic required fields present${NC}"
        echo "  opinion_id: $OPINION_ID"
        echo "  specialist_type: $SPECIALIST_TYPE"
        echo "  processing_time_ms: $PROCESSING_TIME"
    else
        echo -e "${RED}✗ Missing basic required fields${NC}"
        echo "  opinion_id: ${OPINION_ID:-MISSING}"
        echo "  specialist_type: ${SPECIALIST_TYPE:-MISSING}"
        echo "  evaluated_at: ${EVALUATED_AT:-MISSING}"
        echo "  processing_time_ms: ${PROCESSING_TIME:-MISSING}"
        TEST_4_PASSED=false
    fi

    # Validate specialist_version field
    if [ -n "$SPECIALIST_VERSION" ] && [ "$SPECIALIST_VERSION" != "null" ]; then
        echo -e "${GREEN}✓ specialist_version field present: $SPECIALIST_VERSION${NC}"
    else
        echo -e "${RED}✗ specialist_version field missing or null${NC}"
        TEST_4_PASSED=false
    fi

    # Validate opinion is an object (not null)
    if echo "$RESPONSE" | jq -e '.opinion | type == "object"' > /dev/null 2>&1; then
        echo -e "${GREEN}✓ opinion field is an object${NC}"
    else
        echo -e "${RED}✗ opinion field is not an object or is null${NC}"
        TEST_4_PASSED=false
    fi

    if [ "$TEST_4_PASSED" = true ]; then
        ((SPEC_PASSED++))
    else
        ((SPEC_FAILED++))
        continue
    fi
    echo ""

    # Test 5: Validate evaluated_at (CRITICAL)
    echo -e "${BLUE}[Test 5/5] Validating evaluated_at field (CRITICAL)...${NC}"
    SECONDS_VALUE=$(echo "$RESPONSE" | jq -r '.evaluatedAt.seconds // empty')
    NANOS_VALUE=$(echo "$RESPONSE" | jq -r '.evaluatedAt.nanos // empty')

    TEST_PASSED=true

    # Validate seconds exists and is a number
    if [ -n "$SECONDS_VALUE" ] && [ "$SECONDS_VALUE" != "null" ]; then
        echo -e "${GREEN}✓ evaluated_at.seconds exists: $SECONDS_VALUE${NC}"
        RESULTS_SECONDS[$spec]=$SECONDS_VALUE

        # Validate it's a valid timestamp (after 2023-01-01)
        if [ "$SECONDS_VALUE" -gt 1700000000 ]; then
            echo -e "${GREEN}✓ evaluated_at.seconds is valid Unix timestamp${NC}"
        else
            echo -e "${RED}✗ evaluated_at.seconds value too old: $SECONDS_VALUE${NC}"
            TEST_PASSED=false
        fi
    else
        echo -e "${RED}✗ evaluated_at.seconds is missing or null${NC}"
        TEST_PASSED=false
    fi

    # Validate nanos exists and is in valid range
    if [ -n "$NANOS_VALUE" ] && [ "$NANOS_VALUE" != "null" ]; then
        echo -e "${GREEN}✓ evaluated_at.nanos exists: $NANOS_VALUE${NC}"
        RESULTS_NANOS[$spec]=$NANOS_VALUE

        # Validate range [0, 999999999]
        if [ "$NANOS_VALUE" -ge 0 ] && [ "$NANOS_VALUE" -le 999999999 ]; then
            echo -e "${GREEN}✓ evaluated_at.nanos in valid range [0, 999999999]${NC}"
        else
            echo -e "${RED}✗ evaluated_at.nanos out of range: $NANOS_VALUE${NC}"
            TEST_PASSED=false
        fi
    else
        echo -e "${RED}✗ evaluated_at.nanos is missing or null${NC}"
        TEST_PASSED=false
    fi

    if [ "$TEST_PASSED" = true ]; then
        echo -e "${GREEN}✓ evaluated_at validation PASSED${NC}"
        ((SPEC_PASSED++))
    else
        echo -e "${RED}✗ evaluated_at validation FAILED${NC}"
        ((SPEC_FAILED++))
    fi
    echo ""

    # Update global counters
    PASSED=$((PASSED + SPEC_PASSED))
    FAILED=$((FAILED + SPEC_FAILED))

    echo -e "${YELLOW}Specialist $spec Summary: $SPEC_PASSED passed, $SPEC_FAILED failed${NC}"
    echo ""
done

# Final summary
echo "========================================"
echo "FINAL SUMMARY"
echo "========================================"
echo ""

TOTAL=$((PASSED + FAILED))
if [ $TOTAL -gt 0 ]; then
    PASS_RATE=$((PASSED * 100 / TOTAL))
else
    PASS_RATE=0
fi

echo "Total tests: $TOTAL"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "Pass rate: ${PASS_RATE}%"
echo ""

# Results table
echo "Specialist Results:"
echo "| Specialist    | evaluated_at.seconds | evaluated_at.nanos |"
echo "|---------------|---------------------|-------------------|"
for spec in "${SPECIALISTS[@]}"; do
    SECS="${RESULTS_SECONDS[$spec]:-N/A}"
    NANOS="${RESULTS_NANOS[$spec]:-N/A}"
    printf "| %-13s | %-19s | %-17s |\n" "$spec" "$SECS" "$NANOS"
done
echo ""

echo "Response files saved:"
for spec in "${SPECIALISTS[@]}"; do
    if [ -f "/tmp/grpc_response_${spec}.json" ]; then
        SIZE=$(stat -c%s "/tmp/grpc_response_${spec}.json")
        echo "  /tmp/grpc_response_${spec}.json (${SIZE} bytes)"
    fi
done
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${YELLOW}⚠ Some tests failed. Review output above for details.${NC}"
    echo "Next steps:"
    echo "  1. Check response files in /tmp/grpc_response_*.json"
    echo "  2. Run test-grpc-isolated.py for programmatic validation"
    echo "  3. Compare protobuf versions with compare-protobuf-versions.sh"
    exit 1
else
    echo -e "${GREEN}✓ All tests passed successfully!${NC}"
    exit 0
fi
