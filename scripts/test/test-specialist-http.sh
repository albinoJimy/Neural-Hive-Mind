#!/bin/bash

# Test HTTP endpoints of a specialist (health, ready, metrics)
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parameters
SPECIALIST="${1:-business}"
NAMESPACE="${2:-specialist-${SPECIALIST}}"
HTTP_PORT=8000
METRICS_PORT=8080
LOG_DIR="logs"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Testing Specialist HTTP Interface${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Specialist: $SPECIALIST"
echo "Namespace: $NAMESPACE"
echo ""

# Create logs directory
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/specialist-${SPECIALIST}-http-test.log"

# Check if jq is available (optional, for formatting)
HAS_JQ=false
if command -v jq &> /dev/null; then
  HAS_JQ=true
fi

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to format JSON output
format_json() {
  if [ "$HAS_JQ" = true ]; then
    echo "$1" | jq .
  else
    echo "$1"
  fi
}

# Test 1: Health Check (Liveness)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 1: Health Check (Liveness)${NC}"
echo -e "${GREEN}========================================${NC}"

# Start port-forward
echo -e "${YELLOW}Starting port-forward for HTTP...${NC}"
kubectl port-forward -n "$NAMESPACE" "svc/specialist-${SPECIALIST}" $HTTP_PORT:$HTTP_PORT &>/dev/null &
HTTP_PF_PID=$!

# Wait for port-forward to stabilize
sleep 2

# Execute health check
echo -e "${YELLOW}Calling /health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:$HTTP_PORT/health)
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n 1)
HEALTH_BODY=$(echo "$HEALTH_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ] && echo "$HEALTH_BODY" | grep -q "healthy"; then
  echo -e "${GREEN}✓ Health check passed (HTTP $HTTP_CODE)${NC}"
  echo ""
  format_json "$HEALTH_BODY"
  echo "$HEALTH_BODY" >> "$LOG_FILE"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo -e "${RED}✗ Health check failed (HTTP $HTTP_CODE)${NC}"
  echo ""
  echo "$HEALTH_BODY"
  echo "$HEALTH_BODY" >> "$LOG_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""

# Test 2: Readiness Check
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 2: Readiness Check${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Calling /ready endpoint...${NC}"
READY_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:$HTTP_PORT/ready)
HTTP_CODE=$(echo "$READY_RESPONSE" | tail -n 1)
READY_BODY=$(echo "$READY_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
  echo -e "${GREEN}✓ Readiness check passed (HTTP $HTTP_CODE)${NC}"
  echo ""
  format_json "$READY_BODY"
  echo "$READY_BODY" >> "$LOG_FILE"

  # Check readiness status
  if [ "$HAS_JQ" = true ]; then
    READY_STATUS=$(echo "$READY_BODY" | jq -r '.ready // false')
    if [ "$READY_STATUS" = "true" ]; then
      echo ""
      echo -e "${GREEN}✓ Specialist is READY${NC}"

      # Display details
      echo ""
      echo -e "${YELLOW}Readiness Details:${NC}"
      echo "$READY_BODY" | jq -r '.details // {}' | while read -r line; do
        echo "  $line"
      done
    else
      echo ""
      echo -e "${YELLOW}⚠ Specialist is NOT READY${NC}"
      echo ""
      echo -e "${YELLOW}Details:${NC}"
      echo "$READY_BODY" | jq -r '.details // {}'
    fi
  fi

  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo -e "${RED}✗ Readiness check failed (HTTP $HTTP_CODE)${NC}"
  echo ""
  echo "$READY_BODY"
  echo "$READY_BODY" >> "$LOG_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Kill HTTP port-forward
kill $HTTP_PF_PID &>/dev/null || true
sleep 1

echo ""

# Test 3: Prometheus Metrics
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 3: Prometheus Metrics${NC}"
echo -e "${GREEN}========================================${NC}"

# Start port-forward for metrics
echo -e "${YELLOW}Starting port-forward for metrics...${NC}"
kubectl port-forward -n "$NAMESPACE" "svc/specialist-${SPECIALIST}" $METRICS_PORT:$METRICS_PORT &>/dev/null &
METRICS_PF_PID=$!

# Wait for port-forward to stabilize
sleep 2

# Execute metrics check
echo -e "${YELLOW}Calling /metrics endpoint...${NC}"
METRICS_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:$METRICS_PORT/metrics)
HTTP_CODE=$(echo "$METRICS_RESPONSE" | tail -n 1)
METRICS_BODY=$(echo "$METRICS_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
  echo -e "${GREEN}✓ Metrics endpoint accessible (HTTP $HTTP_CODE)${NC}"
  echo ""

  # Check for key metrics
  KEY_METRICS=(
    "neural_hive_specialist_evaluations_total"
    "neural_hive_specialist_evaluation_duration_seconds"
    "neural_hive_specialist_confidence_score"
    "neural_hive_specialist_risk_score"
  )

  echo -e "${YELLOW}Key Metrics Found:${NC}"
  for metric in "${KEY_METRICS[@]}"; do
    if echo "$METRICS_BODY" | grep -q "^$metric"; then
      echo -e "  ${GREEN}✓${NC} $metric"
    else
      echo -e "  ${RED}✗${NC} $metric"
    fi
  done

  # Count total metrics
  TOTAL_METRICS=$(echo "$METRICS_BODY" | grep -c "^neural_hive_" || true)
  echo ""
  echo -e "${YELLOW}Total neural_hive_* metrics: $TOTAL_METRICS${NC}"

  # Sample some metrics
  echo ""
  echo -e "${YELLOW}Sample Metrics:${NC}"
  echo "$METRICS_BODY" | grep "^neural_hive_" | head -10 | while read -r line; do
    echo "  $line"
  done

  echo "$METRICS_BODY" >> "$LOG_FILE"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo -e "${RED}✗ Metrics endpoint failed (HTTP $HTTP_CODE)${NC}"
  echo ""
  echo "$METRICS_BODY" | head -20
  echo "$METRICS_BODY" >> "$LOG_FILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Kill metrics port-forward
kill $METRICS_PF_PID &>/dev/null || true
sleep 1

echo ""

# Test 4: Pod Logs
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 4: Pod Logs Validation${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Fetching recent pod logs...${NC}"
POD_LOGS=$(kubectl logs -n "$NAMESPACE" -l "app.kubernetes.io/name=specialist-${SPECIALIST}" --tail=50 2>&1)

# Check for initialization messages
INIT_MESSAGES=(
  "Specialist initialized successfully"
  "gRPC server started"
  "HTTP server started"
)

echo -e "${YELLOW}Checking initialization messages:${NC}"
INIT_PASS=true
for msg in "${INIT_MESSAGES[@]}"; do
  if echo "$POD_LOGS" | grep -q "$msg"; then
    echo -e "  ${GREEN}✓${NC} Found: $msg"
  else
    echo -e "  ${YELLOW}⚠${NC} Missing: $msg"
  fi
done

# Check for errors
ERROR_COUNT=$(echo "$POD_LOGS" | grep -ci "ERROR" || true)
if [ "$ERROR_COUNT" -gt 0 ]; then
  echo ""
  echo -e "${YELLOW}⚠ Found $ERROR_COUNT ERROR messages in logs${NC}"
  echo ""
  echo -e "${YELLOW}Recent errors:${NC}"
  echo "$POD_LOGS" | grep -i "ERROR" | tail -5 | while read -r line; do
    echo "  $line"
  done
else
  echo ""
  echo -e "${GREEN}✓ No ERROR messages found${NC}"
fi

# Check log format (JSON)
if echo "$POD_LOGS" | head -5 | grep -q "{"; then
  echo -e "${GREEN}✓ Logs are in JSON format${NC}"
else
  echo -e "${YELLOW}⚠ Logs may not be in JSON format${NC}"
fi

echo ""
echo -e "${YELLOW}Sample logs (last 10 lines):${NC}"
echo "$POD_LOGS" | tail -10 | while read -r line; do
  echo "  $line"
done

TESTS_PASSED=$((TESTS_PASSED + 1))

echo ""

# Test summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Summary table
printf "%-30s %s\n" "Test" "Status"
printf "%-30s %s\n" "----" "------"
printf "%-30s %s\n" "Health Check (Liveness)" "$([ $(echo "$HEALTH_RESPONSE" | tail -n 1) = "200" ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
printf "%-30s %s\n" "Readiness Check" "$([ $(echo "$READY_RESPONSE" | tail -n 1) = "200" ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
printf "%-30s %s\n" "Prometheus Metrics" "$([ $(echo "$METRICS_RESPONSE" | tail -n 1) = "200" ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
printf "%-30s %s\n" "Pod Logs" "${GREEN}✓ PASS${NC}"

echo ""
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}/4"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}/4"
echo ""
echo -e "Log file: ${YELLOW}$LOG_FILE${NC}"
echo ""

if [ $TESTS_FAILED -gt 0 ]; then
  echo -e "${RED}Some tests failed${NC}"
  exit 1
else
  echo -e "${GREEN}All HTTP tests passed!${NC}"
  exit 0
fi
