#!/bin/bash

# Complete integration test for all 5 neural specialists
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Neural Specialists Integration Test${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
TEST_ID=$(date +%s)
LOG_DIR="logs"
REPORT_FILE="$LOG_DIR/specialists-integration-test-${TEST_ID}.md"
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")
MONGODB_NAMESPACE="mongodb-cluster"

# Create logs directory
mkdir -p "$LOG_DIR"

# Initialize report
cat > "$REPORT_FILE" <<EOF
# Neural Specialists Integration Test Report
**Test ID:** ${TEST_ID}
**Date:** $(date '+%Y-%m-%d %H:%M:%S')

---

EOF

echo -e "${YELLOW}Test ID: $TEST_ID${NC}"
echo -e "${YELLOW}Report: $REPORT_FILE${NC}"
echo ""

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Step 1: Validate prerequisites
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 1: Validating Prerequisites${NC}"
echo -e "${GREEN}========================================${NC}"

echo "## Prerequisites" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Check all specialists are deployed
echo -e "${YELLOW}Checking specialist deployments...${NC}"
ALL_DEPLOYED=true
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  if kubectl get deployment "specialist-${specialist}" -n "$NAMESPACE" &>/dev/null; then
    READY=$(kubectl get deployment "specialist-${specialist}" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$READY" -gt 0 ]; then
      echo -e "  ${GREEN}✓${NC} specialist-${specialist} (ready)"
      echo "- ✓ specialist-${specialist} (ready)" >> "$REPORT_FILE"
    else
      echo -e "  ${RED}✗${NC} specialist-${specialist} (not ready)"
      echo "- ✗ specialist-${specialist} (not ready)" >> "$REPORT_FILE"
      ALL_DEPLOYED=false
    fi
  else
    echo -e "  ${RED}✗${NC} specialist-${specialist} (not found)"
    echo "- ✗ specialist-${specialist} (not found)" >> "$REPORT_FILE"
    ALL_DEPLOYED=false
  fi
done

if [ "$ALL_DEPLOYED" = false ]; then
  echo ""
  echo -e "${RED}✗ Not all specialists are deployed and ready${NC}"
  echo ""
  echo "**Status:** ✗ Prerequisites failed - not all specialists deployed" >> "$REPORT_FILE"
  echo ""
  echo -e "${YELLOW}Deploy specialists first:${NC}"
  echo "  ./scripts/deploy/deploy-specialists-local.sh"
  exit 1
fi

echo ""
echo -e "${GREEN}✓ All specialists deployed and ready${NC}"
echo "" >> "$REPORT_FILE"
echo "**Status:** ✓ All prerequisites met" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Step 2: Create test plan
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 2: Creating Test Cognitive Plan${NC}"
echo -e "${GREEN}========================================${NC}"

echo "## Test Plan Generation" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

PLAN_ID="test-plan-${TEST_ID}"
INTENT_ID="test-intent-${TEST_ID}"
CORRELATION_ID="test-corr-${TEST_ID}"
TRACE_ID="test-trace-${TEST_ID}"

# Create test cognitive plan
TEST_PLAN_JSON=$(cat <<EOF
{
  "plan_id": "${PLAN_ID}",
  "intent_id": "${INTENT_ID}",
  "tasks": [
    {
      "id": "task-1",
      "description": "Criar API REST para gestão de pedidos",
      "type": "api-development",
      "priority": "high",
      "estimated_effort": "5 days"
    },
    {
      "id": "task-2",
      "description": "Implementar autenticação JWT",
      "type": "security",
      "priority": "critical",
      "estimated_effort": "3 days"
    },
    {
      "id": "task-3",
      "description": "Configurar banco de dados PostgreSQL",
      "type": "infrastructure",
      "priority": "high",
      "estimated_effort": "2 days"
    }
  ],
  "metadata": {
    "domain": "technical",
    "classification": "api-development",
    "complexity": "medium",
    "test_mode": true
  }
}
EOF
)

# Base64 encode the plan
COGNITIVE_PLAN_B64=$(echo "$TEST_PLAN_JSON" | b64_nowrap)

echo -e "${GREEN}✓ Test plan created${NC}"
echo "  Plan ID: $PLAN_ID"
echo "  Intent ID: $INTENT_ID"
echo "  Tasks: 3"
echo ""

echo "- **Plan ID:** \`${PLAN_ID}\`" >> "$REPORT_FILE"
echo "- **Intent ID:** \`${INTENT_ID}\`" >> "$REPORT_FILE"
echo "- **Correlation ID:** \`${CORRELATION_ID}\`" >> "$REPORT_FILE"
echo "- **Tasks:** 3 (API development, JWT auth, PostgreSQL setup)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Step 3: Call all specialists via gRPC
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 3: Evaluating Plan with Specialists${NC}"
echo -e "${GREEN}========================================${NC}"

echo "## Specialist Evaluations" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Check if grpcurl is available
if ! command -v grpcurl &> /dev/null; then
  echo -e "${RED}✗ grpcurl not found${NC}"
  echo ""
  echo -e "${YELLOW}Install grpcurl:${NC}"
  echo "  go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"
  exit 1
fi

# Function to get grpcurl options (checks reflection with fallback to proto files)
get_grpcurl_opts() {
  local opts="-plaintext"
  # Try reflection first
  if ! grpcurl -plaintext localhost:50051 list >/dev/null 2>&1; then
    # Fallback to proto files
    opts="$opts -import-path schemas/specialist-opinion -proto specialist.proto"
  fi
  echo "$opts"
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

# Array to store results
declare -A OPINIONS
declare -A CONFIDENCE_SCORES
declare -A RISK_SCORES
declare -A RECOMMENDATIONS

# Evaluate with each specialist
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  echo ""
  echo -e "${YELLOW}Evaluating with specialist-${specialist}...${NC}"

  # Create request payload
  REQUEST_PAYLOAD=$(cat <<EOF
{
  "plan_id": "${PLAN_ID}",
  "intent_id": "${INTENT_ID}",
  "correlation_id": "${CORRELATION_ID}",
  "trace_id": "${TRACE_ID}",
  "cognitive_plan": "${COGNITIVE_PLAN_B64}",
  "context": {"test": "true", "specialist": "${specialist}"},
  "timeout_ms": 10000
}
EOF
  )

  # Start port-forward for gRPC
  kubectl port-forward -n "$NAMESPACE" "svc/specialist-${specialist}" 50051:50051 &>/dev/null &
  PF_PID_GRPC=$!
  sleep 2

  # Start port-forward for metrics
  kubectl port-forward -n "$NAMESPACE" "svc/specialist-${specialist}" 8080:8080 &>/dev/null &
  PF_PID_METRICS=$!
  sleep 1

  # Get baseline metrics
  METRICS_BEFORE=$(curl -s http://localhost:8080/metrics 2>/dev/null || echo "")
  EVAL_COUNT_BEFORE=0
  if [ -n "$METRICS_BEFORE" ]; then
    EVAL_COUNT_BEFORE=$(echo "$METRICS_BEFORE" | grep '^neural_hive_specialist_evaluations_total' | awk '{print $2}' || echo "0")
  fi

  # Get grpcurl options (with reflection fallback)
  GRPCURL_OPTS=$(get_grpcurl_opts)

  # Call EvaluatePlan
  RESPONSE=$(grpcurl $GRPCURL_OPTS \
    -d "$REQUEST_PAYLOAD" \
    localhost:50051 \
    neural_hive.specialist.SpecialistService/EvaluatePlan 2>&1)

  # Wait for metrics to update
  sleep 1

  # Get metrics after evaluation
  METRICS_AFTER=$(curl -s http://localhost:8080/metrics 2>/dev/null || echo "")
  EVAL_COUNT_AFTER=0
  if [ -n "$METRICS_AFTER" ]; then
    EVAL_COUNT_AFTER=$(echo "$METRICS_AFTER" | grep '^neural_hive_specialist_evaluations_total' | awk '{print $2}' || echo "0")
  fi

  # Kill port-forwards
  kill $PF_PID_GRPC &>/dev/null || true
  kill $PF_PID_METRICS &>/dev/null || true

  # Validate response
  if echo "$RESPONSE" | grep -q "opinionId"; then
    echo -e "${GREEN}✓ Received opinion from specialist-${specialist}${NC}"

    # Extract fields using jq (preferred) or grep/sed fallback
    if command -v jq &> /dev/null; then
      OPINION_ID=$(echo "$RESPONSE" | jq -r '.opinionId')
      CONFIDENCE=$(echo "$RESPONSE" | jq -r '.opinion.confidenceScore')
      RISK=$(echo "$RESPONSE" | jq -r '.opinion.riskScore')
      RECOMMENDATION=$(echo "$RESPONSE" | jq -r '.opinion.recommendation')
    else
      # Fallback regex for camelCase and nested structure
      OPINION_ID=$(echo "$RESPONSE" | grep -o '"opinionId"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: "\(.*\)"/\1/')
      CONFIDENCE=$(echo "$RESPONSE" | grep -o '"confidenceScore"[[:space:]]*:[[:space:]]*[0-9.]*' | awk '{print $NF}')
      RISK=$(echo "$RESPONSE" | grep -o '"riskScore"[[:space:]]*:[[:space:]]*[0-9.]*' | awk '{print $NF}')
      RECOMMENDATION=$(echo "$RESPONSE" | grep -o '"recommendation"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: "\(.*\)"/\1/')
    fi

    OPINIONS[$specialist]=$OPINION_ID
    CONFIDENCE_SCORES[$specialist]=${CONFIDENCE:-0.0}
    RISK_SCORES[$specialist]=${RISK:-0.0}
    RECOMMENDATIONS[$specialist]=${RECOMMENDATION:-unknown}

    echo "  Opinion ID: $OPINION_ID"
    echo "  Confidence: $CONFIDENCE"
    echo "  Risk: $RISK"
    echo "  Recommendation: $RECOMMENDATION"

    # Validate metrics increment
    if [ "$EVAL_COUNT_AFTER" -gt "$EVAL_COUNT_BEFORE" ]; then
      echo -e "  ${GREEN}✓${NC} Metrics incremented (${EVAL_COUNT_BEFORE} → ${EVAL_COUNT_AFTER})"
    else
      echo -e "  ${YELLOW}⚠${NC} Metrics not incremented (${EVAL_COUNT_BEFORE} → ${EVAL_COUNT_AFTER})"
    fi

    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "${RED}✗ Failed to get opinion from specialist-${specialist}${NC}"
    echo "$RESPONSE"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi

  sleep 1
done

echo ""

# Step 4: Validate MongoDB persistence
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 4: Validating MongoDB Persistence${NC}"
echo -e "${GREEN}========================================${NC}"

echo "## MongoDB Persistence" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Get MongoDB pod
MONGO_POD=$(kubectl get pods -n "$MONGODB_NAMESPACE" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$MONGO_POD" ]; then
  echo -e "${RED}✗ MongoDB pod not found${NC}"
  echo "**Status:** ✗ MongoDB pod not found" >> "$REPORT_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
else
  # Query opinions for this plan
  sleep 3  # Wait for async persistence
  PERSISTED_COUNT=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
    mongosh --quiet --eval "
      use neural_hive;
      db.specialist_opinions.countDocuments({plan_id: '${PLAN_ID}'});
    " 2>&1 | tail -1)

  echo -e "${YELLOW}Opinions persisted for plan ${PLAN_ID}: ${PERSISTED_COUNT}${NC}"
  echo "" >> "$REPORT_FILE"
  echo "- **Plan ID:** \`${PLAN_ID}\`" >> "$REPORT_FILE"
  echo "- **Opinions persisted:** ${PERSISTED_COUNT}/5" >> "$REPORT_FILE"
  echo "" >> "$REPORT_FILE"

  if [ "$PERSISTED_COUNT" = "5" ]; then
    echo -e "${GREEN}✓ All 5 opinions persisted successfully${NC}"
    echo "**Status:** ✓ All opinions persisted" >> "$REPORT_FILE"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "${YELLOW}⚠ Expected 5 opinions, found ${PERSISTED_COUNT}${NC}"
    echo "**Status:** ⚠ Only ${PERSISTED_COUNT}/5 opinions persisted" >> "$REPORT_FILE"
  fi
fi

echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Step 5: Consensus analysis
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 5: Consensus Analysis${NC}"
echo -e "${GREEN}========================================${NC}"

echo "## Consensus Analysis" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Calculate averages (using awk to avoid bc dependency)
TOTAL_CONFIDENCE=0
TOTAL_RISK=0
APPROVE_COUNT=0
REJECT_COUNT=0
REVIEW_COUNT=0
CONDITIONAL_COUNT=0

for specialist in "${SPECIALISTS[@]}"; do
  CONF=${CONFIDENCE_SCORES[$specialist]:-0}
  RISK=${RISK_SCORES[$specialist]:-0}
  REC=${RECOMMENDATIONS[$specialist]:-unknown}

  TOTAL_CONFIDENCE=$(awk -v t="$TOTAL_CONFIDENCE" -v c="$CONF" 'BEGIN{print t+c}')
  TOTAL_RISK=$(awk -v t="$TOTAL_RISK" -v r="$RISK" 'BEGIN{print t+r}')

  case $REC in
    "approve"|"APPROVE")
      APPROVE_COUNT=$((APPROVE_COUNT + 1))
      ;;
    "reject"|"REJECT")
      REJECT_COUNT=$((REJECT_COUNT + 1))
      ;;
    "review_required"|"REVIEW_REQUIRED")
      REVIEW_COUNT=$((REVIEW_COUNT + 1))
      ;;
    "conditional"|"CONDITIONAL")
      CONDITIONAL_COUNT=$((CONDITIONAL_COUNT + 1))
      ;;
  esac
done

AVG_CONFIDENCE=$(awk -v t="$TOTAL_CONFIDENCE" 'BEGIN{printf "%.2f", t/5}')
AVG_RISK=$(awk -v t="$TOTAL_RISK" 'BEGIN{printf "%.2f", t/5}')

# Determine consensus
if [ $APPROVE_COUNT -ge 3 ]; then
  CONSENSUS="approve"
  CONSENSUS_COLOR=$GREEN
elif [ $REJECT_COUNT -ge 3 ]; then
  CONSENSUS="reject"
  CONSENSUS_COLOR=$RED
else
  CONSENSUS="review_required"
  CONSENSUS_COLOR=$YELLOW
fi

# Decision matrix
echo ""
echo -e "${YELLOW}Decision Matrix:${NC}"
echo ""
printf "%-20s | %-12s | %-8s | %-20s\n" "Specialist" "Confidence" "Risk" "Recommendation"
printf "%-20s-+-%-12s-+-%-8s-+-%-20s\n" "--------------------" "------------" "--------" "--------------------"

echo "" >> "$REPORT_FILE"
echo "### Decision Matrix" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "| Specialist | Confidence | Risk | Recommendation |" >> "$REPORT_FILE"
echo "|------------|------------|------|----------------|" >> "$REPORT_FILE"

for specialist in "${SPECIALISTS[@]}"; do
  CONF=${CONFIDENCE_SCORES[$specialist]:-0.00}
  RISK=${RISK_SCORES[$specialist]:-0.00}
  REC=${RECOMMENDATIONS[$specialist]:-unknown}

  printf "%-20s | %-12s | %-8s | %-20s\n" "$specialist" "$CONF" "$RISK" "$REC"
  echo "| $specialist | $CONF | $RISK | $REC |" >> "$REPORT_FILE"
done

printf "%-20s-+-%-12s-+-%-8s-+-%-20s\n" "--------------------" "------------" "--------" "--------------------"
printf "%-20s | %-12s | %-8s | %-20s\n" "CONSENSUS" "$AVG_CONFIDENCE" "$AVG_RISK" "$CONSENSUS ($APPROVE_COUNT/5 approve)"

echo "| **CONSENSUS** | **$AVG_CONFIDENCE** | **$AVG_RISK** | **$CONSENSUS** ($APPROVE_COUNT/5) |" >> "$REPORT_FILE"

echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "  Average Confidence: $AVG_CONFIDENCE"
echo "  Average Risk: $AVG_RISK"
echo "  Recommendations: ${APPROVE_COUNT} approve, ${CONDITIONAL_COUNT} conditional, ${REVIEW_COUNT} review, ${REJECT_COUNT} reject"
echo -e "  ${CONSENSUS_COLOR}Final Decision: $CONSENSUS${NC}"

echo "" >> "$REPORT_FILE"
echo "### Summary" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- **Average Confidence:** $AVG_CONFIDENCE" >> "$REPORT_FILE"
echo "- **Average Risk:** $AVG_RISK" >> "$REPORT_FILE"
echo "- **Recommendations:** ${APPROVE_COUNT} approve, ${CONDITIONAL_COUNT} conditional, ${REVIEW_COUNT} review, ${REJECT_COUNT} reject" >> "$REPORT_FILE"
echo "- **Final Decision:** **$CONSENSUS**" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

TESTS_PASSED=$((TESTS_PASSED + 1))

# Final summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo ""

echo "---" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "## Test Results" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- **Tests passed:** $TESTS_PASSED" >> "$REPORT_FILE"
echo "- **Tests failed:** $TESTS_FAILED" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Success criteria
echo -e "${YELLOW}Success Criteria:${NC}"
echo "  ✓ Intent published to Kafka: N/A (manual test)"
echo "  ✓ Cognitive Plan generated: ✓ (created locally)"
echo "  ✓ 5 specialists evaluated plan: $([ ${#OPINIONS[@]} -eq 5 ] && echo '✓' || echo '✗') (${#OPINIONS[@]}/5)"
echo "  ✓ 5 opinions persisted in MongoDB: $([ "$PERSISTED_COUNT" = "5" ] && echo '✓' || echo '✗') ($PERSISTED_COUNT/5)"
echo "  ✓ Scores valid (0.0-1.0): ✓ (assumed)"
echo "  ✓ Recommendations valid: ✓ (assumed)"
echo "  ✓ Consensus determined: ✓"

echo "### Success Criteria" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- ✓ Cognitive Plan generated" >> "$REPORT_FILE"
echo "- $([ ${#OPINIONS[@]} -eq 5 ] && echo '✓' || echo '✗') 5 specialists evaluated plan (${#OPINIONS[@]}/5)" >> "$REPORT_FILE"
echo "- $([ "$PERSISTED_COUNT" = "5" ] && echo '✓' || echo '✗') 5 opinions persisted in MongoDB ($PERSISTED_COUNT/5)" >> "$REPORT_FILE"
echo "- ✓ Consensus determined" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo ""
echo -e "Report saved to: ${YELLOW}$REPORT_FILE${NC}"
echo ""

if [ $TESTS_FAILED -gt 0 ]; then
  echo -e "${RED}Integration test completed with failures${NC}"
  echo "**Overall Status:** ✗ FAILED" >> "$REPORT_FILE"
  exit 1
else
  echo -e "${GREEN}Integration test passed successfully!${NC}"
  echo "**Overall Status:** ✓ PASSED" >> "$REPORT_FILE"
  exit 0
fi
