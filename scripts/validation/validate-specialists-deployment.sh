#!/bin/bash

# Validate specialists deployment post-deployment
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validating Specialists Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")
LOG_DIR="logs"
REPORT_FILE="$LOG_DIR/specialists-validation-report.txt"

# Create logs directory
mkdir -p "$LOG_DIR"

# Initialize report
cat > "$REPORT_FILE" <<EOF
Neural Specialists Deployment Validation Report
================================================
Date: $(date '+%Y-%m-%d %H:%M:%S')

EOF

# Validation counters
TOTAL_VALIDATIONS=0
PASSED_VALIDATIONS=0
FAILED_VALIDATIONS=0
WARNING_VALIDATIONS=0

# Track issues
declare -a ISSUES

# Validation 1: Namespaces
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 1: Namespaces${NC}"
echo -e "${GREEN}========================================${NC}"

echo "1. Namespaces" >> "$REPORT_FILE"
echo "-------------" >> "$REPORT_FILE"

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))

  if kubectl get namespace "$NAMESPACE" &>/dev/null; then
    # Check labels
    LABELS=$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.metadata.labels}')
    if echo "$LABELS" | grep -q "neural-hive.io/component" && echo "$LABELS" | grep -q "neural-hive.io/layer"; then
      echo -e "  ${GREEN}✓${NC} Namespace $NAMESPACE (with labels)"
      echo "  ✓ $NAMESPACE (with labels)" >> "$REPORT_FILE"
      PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
    else
      echo -e "  ${YELLOW}⚠${NC} Namespace $NAMESPACE (missing labels)"
      echo "  ⚠ $NAMESPACE (missing labels)" >> "$REPORT_FILE"
      WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
      ISSUES+=("Namespace $NAMESPACE missing recommended labels")
    fi
  else
    echo -e "  ${RED}✗${NC} Namespace $NAMESPACE not found"
    echo "  ✗ $NAMESPACE not found" >> "$REPORT_FILE"
    FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
    ISSUES+=("Namespace $NAMESPACE not found")
  fi
done

echo "" >> "$REPORT_FILE"
echo ""

# Validation 2: Deployments and Pods
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 2: Deployments and Pods${NC}"
echo -e "${GREEN}========================================${NC}"

echo "2. Deployments and Pods" >> "$REPORT_FILE"
echo "----------------------" >> "$REPORT_FILE"

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  DEPLOYMENT="specialist-${specialist}"

  echo ""
  echo -e "${YELLOW}Checking specialist-${specialist}...${NC}"
  echo "" >> "$REPORT_FILE"
  echo "  specialist-${specialist}:" >> "$REPORT_FILE"

  # Check deployment exists
  TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
  if kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" &>/dev/null; then
    # Get replica counts
    DESIRED=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
    READY=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    AVAILABLE=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")

    if [ "$READY" = "$DESIRED" ] && [ "$AVAILABLE" = "$DESIRED" ]; then
      echo -e "    ${GREEN}✓${NC} Deployment: $DESIRED/$DESIRED replicas ready"
      echo "    ✓ Deployment: $DESIRED/$DESIRED replicas ready" >> "$REPORT_FILE"
      PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
    else
      echo -e "    ${RED}✗${NC} Deployment: $READY/$DESIRED ready, $AVAILABLE available"
      echo "    ✗ Deployment: $READY/$DESIRED ready, $AVAILABLE available" >> "$REPORT_FILE"
      FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
      ISSUES+=("Deployment $DEPLOYMENT not fully ready: $READY/$DESIRED")
    fi

    # Check pod status
    TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
    POD_STATUS=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$DEPLOYMENT" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")

    if [ "$POD_STATUS" = "Running" ]; then
      echo -e "    ${GREEN}✓${NC} Pod: Running"
      echo "    ✓ Pod: Running" >> "$REPORT_FILE"
      PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))

      # Check readiness
      TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
      READY_STATUS=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$DEPLOYMENT" -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

      if [ "$READY_STATUS" = "True" ]; then
        echo -e "    ${GREEN}✓${NC} Readiness: Passed"
        echo "    ✓ Readiness: Passed" >> "$REPORT_FILE"
        PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
      else
        echo -e "    ${RED}✗${NC} Readiness: Failed"
        echo "    ✗ Readiness: Failed" >> "$REPORT_FILE"
        FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
        ISSUES+=("Pod for $DEPLOYMENT failed readiness probe")
      fi
    else
      echo -e "    ${RED}✗${NC} Pod: $POD_STATUS"
      echo "    ✗ Pod: $POD_STATUS" >> "$REPORT_FILE"
      FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
      ISSUES+=("Pod for $DEPLOYMENT in state: $POD_STATUS")
    fi
  else
    echo -e "    ${RED}✗${NC} Deployment not found"
    echo "    ✗ Deployment not found" >> "$REPORT_FILE"
    FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
    ISSUES+=("Deployment $DEPLOYMENT not found")
  fi
done

echo "" >> "$REPORT_FILE"
echo ""

# Validation 3: Services and Endpoints
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 3: Services and Endpoints${NC}"
echo -e "${GREEN}========================================${NC}"

echo "3. Services and Endpoints" >> "$REPORT_FILE"
echo "-------------------------" >> "$REPORT_FILE"

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  SERVICE="specialist-${specialist}"

  # Check service exists
  TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
  if kubectl get service "$SERVICE" -n "$NAMESPACE" &>/dev/null; then
    # Check ports
    PORTS=$(kubectl get service "$SERVICE" -n "$NAMESPACE" -o jsonpath='{.spec.ports[*].port}')
    if echo "$PORTS" | grep -q "50051" && echo "$PORTS" | grep -q "8000" && echo "$PORTS" | grep -q "8080"; then
      echo -e "  ${GREEN}✓${NC} Service $SERVICE (3 ports: grpc, http, metrics)"
      echo "  ✓ Service $SERVICE (3 ports)" >> "$REPORT_FILE"
      PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
    else
      echo -e "  ${YELLOW}⚠${NC} Service $SERVICE (ports: $PORTS)"
      echo "  ⚠ Service $SERVICE (unexpected ports: $PORTS)" >> "$REPORT_FILE"
      WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
    fi

    # Check endpoints
    TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
    ENDPOINTS=$(kubectl get endpoints "$SERVICE" -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
    if [ -n "$ENDPOINTS" ]; then
      echo -e "  ${GREEN}✓${NC} Endpoints populated for $SERVICE"
      echo "  ✓ Endpoints populated for $SERVICE" >> "$REPORT_FILE"
      PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
    else
      echo -e "  ${RED}✗${NC} Endpoints not populated for $SERVICE"
      echo "  ✗ Endpoints not populated for $SERVICE" >> "$REPORT_FILE"
      FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
      ISSUES+=("Service $SERVICE has no endpoints")
    fi
  else
    echo -e "  ${RED}✗${NC} Service $SERVICE not found"
    echo "  ✗ Service $SERVICE not found" >> "$REPORT_FILE"
    FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
    ISSUES+=("Service $SERVICE not found")
  fi
done

echo "" >> "$REPORT_FILE"
echo ""

# Validation 4: Secrets
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 4: Secrets${NC}"
echo -e "${GREEN}========================================${NC}"

echo "4. Secrets" >> "$REPORT_FILE"
echo "----------" >> "$REPORT_FILE"

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"

  TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
  if kubectl get secret specialist-secrets -n "$NAMESPACE" &>/dev/null; then
    # Check required keys
    KEYS=$(kubectl get secret specialist-secrets -n "$NAMESPACE" -o jsonpath='{.data}' | grep -o '"[^"]*"' | tr -d '"')
    REQUIRED_KEYS=("mlflow_tracking_uri" "mongodb_uri" "neo4j_password" "redis_password")
    MISSING_KEYS=()

    for key in "${REQUIRED_KEYS[@]}"; do
      if ! echo "$KEYS" | grep -q "$key"; then
        MISSING_KEYS+=("$key")
      fi
    done

    if [ ${#MISSING_KEYS[@]} -eq 0 ]; then
      echo -e "  ${GREEN}✓${NC} Secret specialist-secrets in $NAMESPACE (all keys present)"
      echo "  ✓ Secret specialist-secrets in $NAMESPACE" >> "$REPORT_FILE"
      PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
    else
      echo -e "  ${YELLOW}⚠${NC} Secret specialist-secrets in $NAMESPACE (missing: ${MISSING_KEYS[*]})"
      echo "  ⚠ Secret specialist-secrets in $NAMESPACE (missing keys)" >> "$REPORT_FILE"
      WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
    fi
  else
    echo -e "  ${RED}✗${NC} Secret specialist-secrets not found in $NAMESPACE"
    echo "  ✗ Secret specialist-secrets not found in $NAMESPACE" >> "$REPORT_FILE"
    FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
    ISSUES+=("Secret specialist-secrets not found in $NAMESPACE")
  fi
done

echo "" >> "$REPORT_FILE"
echo ""

# Validation 5: Health checks
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 5: Health Checks${NC}"
echo -e "${GREEN}========================================${NC}"

echo "5. Health Checks" >> "$REPORT_FILE"
echo "----------------" >> "$REPORT_FILE"

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  DEPLOYMENT="specialist-${specialist}"

  TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))

  # Execute health check via port-forward to avoid curl dependency in container
  kubectl port-forward -n "$NAMESPACE" "svc/specialist-${specialist}" 8000:8000 &>/dev/null &
  PF_PID=$!
  sleep 2

  HEALTH_RESPONSE=$(curl -s http://localhost:8000/health 2>&1 || echo "error")

  # Kill port-forward
  kill $PF_PID &>/dev/null || true
  sleep 1

  if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "  ${GREEN}✓${NC} Health check passed for $specialist"
    echo "  ✓ Health check passed for $specialist" >> "$REPORT_FILE"
    PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
  else
    echo -e "  ${RED}✗${NC} Health check failed for $specialist"
    echo "  ✗ Health check failed for $specialist" >> "$REPORT_FILE"
    FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
    ISSUES+=("Health check failed for specialist-$specialist")
  fi
done

echo "" >> "$REPORT_FILE"
echo ""

# Validation 6: External dependencies connectivity
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 6: External Dependencies${NC}"
echo -e "${GREEN}========================================${NC}"

echo "6. External Dependencies" >> "$REPORT_FILE"
echo "------------------------" >> "$REPORT_FILE"

echo -e "${YELLOW}Checking external dependencies connectivity...${NC}"
echo ""

# Check MongoDB connectivity
echo -e "${YELLOW}MongoDB connectivity...${NC}"
TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
MONGO_POD=$(kubectl get pods -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$MONGO_POD" ]; then
  if kubectl exec -n mongodb-cluster "$MONGO_POD" -- mongosh --quiet --eval "db.adminCommand('ping')" &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} MongoDB accessible"
    echo "  ✓ MongoDB accessible" >> "$REPORT_FILE"
    PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
  else
    echo -e "  ${RED}✗${NC} MongoDB ping failed"
    echo "  ✗ MongoDB ping failed" >> "$REPORT_FILE"
    FAILED_VALIDATIONS=$((FAILED_VALIDATIONS + 1))
    ISSUES+=("MongoDB connectivity failed")
  fi
else
  echo -e "  ${YELLOW}⚠${NC} MongoDB pod not found (skipping check)"
  echo "  ⚠ MongoDB pod not found" >> "$REPORT_FILE"
  WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
fi

# Check Neo4j connectivity
echo -e "${YELLOW}Neo4j connectivity...${NC}"
TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
# Run a temporary busybox pod to check connectivity
NEO4J_HOST="neo4j.neo4j.svc.cluster.local"
NEO4J_PORT=7687
if kubectl run neo4j-test --rm -i --restart=Never --image=busybox:latest -- nc -zv "$NEO4J_HOST" "$NEO4J_PORT" &>/dev/null; then
  echo -e "  ${GREEN}✓${NC} Neo4j port $NEO4J_PORT accessible"
  echo "  ✓ Neo4j accessible on port $NEO4J_PORT" >> "$REPORT_FILE"
  PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
else
  echo -e "  ${YELLOW}⚠${NC} Neo4j connectivity check failed (may not be deployed)"
  echo "  ⚠ Neo4j connectivity check failed" >> "$REPORT_FILE"
  WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
fi

# Check Redis connectivity
echo -e "${YELLOW}Redis connectivity...${NC}"
TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
REDIS_HOST="redis.redis.svc.cluster.local"
REDIS_PORT=6379
if kubectl run redis-test --rm -i --restart=Never --image=busybox:latest -- nc -zv "$REDIS_HOST" "$REDIS_PORT" &>/dev/null; then
  echo -e "  ${GREEN}✓${NC} Redis port $REDIS_PORT accessible"
  echo "  ✓ Redis accessible on port $REDIS_PORT" >> "$REPORT_FILE"
  PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
else
  echo -e "  ${YELLOW}⚠${NC} Redis connectivity check failed (may not be deployed)"
  echo "  ⚠ Redis connectivity check failed" >> "$REPORT_FILE"
  WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
fi

# Check MLflow connectivity
echo -e "${YELLOW}MLflow connectivity...${NC}"
TOTAL_VALIDATIONS=$((TOTAL_VALIDATIONS + 1))
MLFLOW_HOST="mlflow.mlflow.svc.cluster.local"
MLFLOW_PORT=5000
if kubectl run mlflow-test --rm -i --restart=Never --timeout=10s --image=curlimages/curl:latest -- curl -sf "http://$MLFLOW_HOST:$MLFLOW_PORT/" &>/dev/null; then
  echo -e "  ${GREEN}✓${NC} MLflow HTTP accessible"
  echo "  ✓ MLflow HTTP accessible" >> "$REPORT_FILE"
  PASSED_VALIDATIONS=$((PASSED_VALIDATIONS + 1))
else
  echo -e "  ${YELLOW}⚠${NC} MLflow connectivity check failed (may not be deployed)"
  echo "  ⚠ MLflow connectivity check failed" >> "$REPORT_FILE"
  WARNING_VALIDATIONS=$((WARNING_VALIDATIONS + 1))
fi

echo "" >> "$REPORT_FILE"
echo ""

# Validation 7: Resource usage
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation 7: Resource Usage${NC}"
echo -e "${GREEN}========================================${NC}"

echo "7. Resource Usage" >> "$REPORT_FILE"
echo "-----------------" >> "$REPORT_FILE"

echo -e "${YELLOW}Checking resource usage...${NC}"
echo ""

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"

  # Get resource usage (may fail if metrics-server not installed)
  METRICS=$(kubectl top pods -n "$NAMESPACE" 2>&1 || echo "metrics-server not available")

  if echo "$METRICS" | grep -q "error\|not available"; then
    echo -e "  ${YELLOW}⚠${NC} Metrics not available for $specialist (metrics-server may not be installed)"
    echo "  ⚠ Metrics not available for $specialist" >> "$REPORT_FILE"
  else
    echo -e "  ${GREEN}✓${NC} Metrics available for $specialist"
    echo "  ✓ Metrics available for $specialist:" >> "$REPORT_FILE"
    echo "$METRICS" | tail -1 | while read -r line; do
      echo "    $line" >> "$REPORT_FILE"
    done
  fi
done

echo "" >> "$REPORT_FILE"
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validation Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

HEALTHY_SPECIALISTS=0
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  READY=$(kubectl get deployment "specialist-${specialist}" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  if [ "$READY" -gt 0 ]; then
    HEALTHY_SPECIALISTS=$((HEALTHY_SPECIALISTS + 1))
  fi
done

echo "Summary" >> "$REPORT_FILE"
echo "-------" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo -e "Specialists healthy: ${GREEN}$HEALTHY_SPECIALISTS${NC}/5"
echo -e "Total validations: $TOTAL_VALIDATIONS"
echo -e "Passed: ${GREEN}$PASSED_VALIDATIONS${NC}"
echo -e "Failed: ${RED}$FAILED_VALIDATIONS${NC}"
echo -e "Warnings: ${YELLOW}$WARNING_VALIDATIONS${NC}"

echo "Specialists healthy: $HEALTHY_SPECIALISTS/5" >> "$REPORT_FILE"
echo "Total validations: $TOTAL_VALIDATIONS" >> "$REPORT_FILE"
echo "Passed: $PASSED_VALIDATIONS" >> "$REPORT_FILE"
echo "Failed: $FAILED_VALIDATIONS" >> "$REPORT_FILE"
echo "Warnings: $WARNING_VALIDATIONS" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Issues found
if [ ${#ISSUES[@]} -gt 0 ]; then
  echo ""
  echo -e "${YELLOW}Issues Found:${NC}"
  echo "" >> "$REPORT_FILE"
  echo "Issues:" >> "$REPORT_FILE"

  for issue in "${ISSUES[@]}"; do
    echo -e "  ${YELLOW}⚠${NC} $issue"
    echo "  - $issue" >> "$REPORT_FILE"
  done
  echo "" >> "$REPORT_FILE"
fi

# Final score
SCORE=$((PASSED_VALIDATIONS * 100 / TOTAL_VALIDATIONS))
echo ""
echo -e "Deployment Score: ${GREEN}${SCORE}%${NC}"
echo "" >> "$REPORT_FILE"
echo "Deployment Score: ${SCORE}%" >> "$REPORT_FILE"

echo ""
echo -e "Report saved to: ${YELLOW}$REPORT_FILE${NC}"
echo ""

# Exit code
if [ $FAILED_VALIDATIONS -gt 0 ]; then
  echo -e "${RED}Deployment validation completed with failures${NC}"
  echo ""
  exit 1
elif [ $WARNING_VALIDATIONS -gt 0 ]; then
  echo -e "${YELLOW}Deployment validation completed with warnings${NC}"
  echo ""
  exit 0
else
  echo -e "${GREEN}Deployment 100% validated!${NC}"
  echo ""
  exit 0
fi
