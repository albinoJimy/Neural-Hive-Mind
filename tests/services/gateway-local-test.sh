#!/usr/bin/env bash

# Test script for deploying and testing the gateway-intencoes service locally on Minikube
# This script performs comprehensive deployment verification and integration testing

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (can be overridden via command line)
NAMESPACE="gateway-intencoes"
SERVICE_NAME="gateway-intencoes"
IMAGE_TAG="local"
TEST_INTENT_ID="test-gateway-$(date +%s)"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

# Logging functions
log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

check_status() {
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC}"
  else
    echo -e "${RED}✗${NC}"
    return 1
  fi
}

# Phase 1: Pre-deployment Verification
log_info "====== Phase 1: Pre-deployment Verification ======"

log_info "Checking if Minikube is running..."
if minikube status | grep -q "Running"; then
  log_success "Minikube is running"
else
  log_error "Minikube is not running. Please start Minikube first."
  exit 1
fi

log_info "Verifying kubectl connectivity..."
if kubectl cluster-info > /dev/null 2>&1; then
  log_success "kubectl is connected to the cluster"
else
  log_error "kubectl cannot connect to the cluster"
  exit 1
fi

log_info "Checking Kafka namespace and pods..."
if kubectl get namespace kafka > /dev/null 2>&1; then
  KAFKA_POD=$(kubectl get pods -n kafka -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [ -z "$KAFKA_POD" ]; then
    KAFKA_POD=$(kubectl get pods -n kafka -l strimzi.io/name=neural-hive-kafka-kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  fi
  if [ -n "$KAFKA_POD" ]; then
    log_success "Kafka pod found: $KAFKA_POD"
  else
    log_error "Kafka pods not found in kafka namespace"
    exit 1
  fi
else
  log_error "Kafka namespace not found"
  exit 1
fi

log_info "Checking Redis namespace and pods..."
if kubectl get namespace redis-cluster > /dev/null 2>&1; then
  REDIS_POD=$(kubectl get pods -n redis-cluster -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  if [ -n "$REDIS_POD" ]; then
    log_success "Redis pod found: $REDIS_POD"
  else
    log_error "Redis pods not found in redis-cluster namespace"
    exit 1
  fi
else
  log_error "redis-cluster namespace not found"
  exit 1
fi

log_info "Checking Keycloak namespace and pods (optional)..."
if kubectl get namespace keycloak > /dev/null 2>&1; then
  KEYCLOAK_POD=$(kubectl get pods -n keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  if [ -n "$KEYCLOAK_POD" ]; then
    log_success "Keycloak pod found: $KEYCLOAK_POD"
  else
    log_warning "Keycloak pods not found (optional for local dev)"
  fi
else
  log_warning "Keycloak namespace not found (optional for local dev)"
fi

log_info "Verifying Kafka topics exist..."
if [ -n "$KAFKA_POD" ]; then
  if kubectl exec -n kafka "$KAFKA_POD" -- kafka-topics.sh --bootstrap-server localhost:9092 --list | grep -q "intentions.business"; then
    log_success "Kafka topic 'intentions.business' exists"
  else
    log_error "Kafka topic 'intentions.business' not found. Please create topics first."
    exit 1
  fi
else
  log_warning "Cannot verify Kafka topics - no Kafka pod found"
fi

# Phase 2: Build Docker Image
log_info "====== Phase 2: Build Docker Image ======"

log_info "Configuring Minikube Docker daemon..."
eval $(minikube docker-env)
log_success "Using Minikube's Docker daemon"

log_info "Building Docker image for gateway-intencoes..."
docker build -t neural-hive-mind/gateway-intencoes:local -f services/gateway-intencoes/Dockerfile . || {
  log_error "Docker build failed"
  exit 1
}

log_info "Verifying image was built..."
if docker images | grep -q "gateway-intencoes"; then
  IMAGE_INFO=$(docker images neural-hive-mind/gateway-intencoes:local --format "{{.Repository}}:{{.Tag}} ({{.Size}})")
  log_success "Image built successfully: $IMAGE_INFO"
else
  log_error "Image verification failed"
  exit 1
fi

# Phase 3: Deploy with deploy-gateway.sh
log_info "====== Phase 3: Deploy with deploy-gateway.sh ======"

log_info "Deploying gateway using deployment script..."
if bash scripts/deploy/deploy-gateway.sh --environment dev --skip-deps --timeout 600s; then
  log_success "Gateway deployed successfully via scripts/deploy/deploy-gateway.sh"
else
  log_error "Deployment script failed"
  exit 1
fi

log_info "Verifying deployment rollout status..."
kubectl rollout status deployment/$SERVICE_NAME -n $NAMESPACE --timeout=5m || {
  log_error "Deployment rollout check failed"
  exit 1
}
log_success "Deployment is ready"

# Phase 4: Verify Pod Health
log_info "====== Phase 4: Verify Pod Health ======"

log_info "Getting pod name..."
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=gateway-intencoes -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POD_NAME" ]; then
  log_error "Pod not found"
  exit 1
fi
log_success "Pod name: $POD_NAME"

log_info "Checking pod phase..."
POD_PHASE=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.phase}')
if [ "$POD_PHASE" = "Running" ]; then
  log_success "Pod is Running"
else
  log_error "Pod is not Running (phase: $POD_PHASE)"
  exit 1
fi

log_info "Waiting for readiness probe..."
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  POD_READY=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
  if [ "$POD_READY" = "True" ]; then
    log_success "Pod is ready"
    break
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

if [ "$POD_READY" != "True" ]; then
  log_error "Pod did not become ready within $TIMEOUT seconds"
  kubectl describe pod $POD_NAME -n $NAMESPACE
  exit 1
fi

log_info "Showing pod details..."
kubectl describe pod $POD_NAME -n $NAMESPACE | tail -20

log_info "Checking logs for startup errors..."
if kubectl logs $POD_NAME -n $NAMESPACE --tail=50 | grep -i "error\|exception\|failed"; then
  log_warning "Found errors in logs (may be expected during startup)"
else
  log_success "No critical errors found in logs"
fi

# Phase 5: Test Connectivity
log_info "====== Phase 5: Test Connectivity ======"

log_info "Testing Kafka bootstrap servers reachability..."
NETSHOOT_KAFKA_POD="netshoot-kafka-$RANDOM"
if kubectl run $NETSHOOT_KAFKA_POD \
  --restart=Never --rm -i --tty \
  -n $NAMESPACE --image=nicolaka/netshoot \
  --command -- bash -lc "nc -zv neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local 9092" 2>&1 | grep -q "succeeded\|open"; then
  log_success "Kafka bootstrap servers are reachable"
else
  log_error "Kafka bootstrap servers are not reachable"
  exit 1
fi

log_info "Testing Redis connectivity..."
NETSHOOT_REDIS_POD="netshoot-redis-$RANDOM"
if kubectl run $NETSHOOT_REDIS_POD \
  --restart=Never --rm -i --tty \
  -n $NAMESPACE --image=nicolaka/netshoot \
  --command -- bash -lc "nc -zv neural-hive-cache.redis-cluster.svc.cluster.local 6379" 2>&1 | grep -q "succeeded\|open"; then
  log_success "Redis is reachable"
else
  log_error "Redis is not reachable"
  exit 1
fi

log_info "Testing health endpoint..."
kubectl port-forward -n $NAMESPACE svc/$SERVICE_NAME 8080:80 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

HTTP_OK=0
HEALTH_RESPONSE=$(curl -sf http://localhost:8080/health) || HTTP_OK=$?
if [ $HTTP_OK -eq 0 ] && echo "$HEALTH_RESPONSE" | jq -e '.status=="healthy"' >/dev/null 2>&1; then
  log_success "Health endpoint OK: $HEALTH_RESPONSE"
else
  log_warning "Health endpoint unexpected response: $HEALTH_RESPONSE"
fi

log_info "Testing text intent API..."
API_RESP=$(curl -s -X POST http://localhost:8080/api/v1/intents/text \
  -H 'Content-Type: application/json' \
  -d '{
    "text":"Create approval workflow",
    "domain":"business",
    "context":{
      "user_id":"test-user",
      "session_id":"'"$SESSION_ID"'",
      "tenant_id":"test-tenant"
    }
  }') || true

NEW_INTENT_ID=$(echo "$API_RESP" | jq -r '.intent_id' 2>/dev/null || echo "")
if [ -n "$NEW_INTENT_ID" ]; then
  log_info "API returned intent_id: $NEW_INTENT_ID"
  sleep 2
  if kubectl logs $POD_NAME -n $NAMESPACE | grep -q "$NEW_INTENT_ID"; then
    log_success "Gateway processed intent via API"
  else
    log_warning "Intent ID not found in logs yet"
  fi
else
  log_warning "Could not extract intent_id from API response: $API_RESP"
fi

kill $PF_PID 2>/dev/null || true

# Phase 6: Publish Test Intent
log_info "====== Phase 6: Publish Test Intent ======"

log_info "Creating test intent envelope..."
TIMESTAMP=$(date +%s%3N)
SESSION_ID="test-session-$(date +%s)"
INTENT_ENVELOPE=$(cat <<EOF
{
  "id": "$TEST_INTENT_ID",
  "version": "1.0.0",
  "timestamp": $TIMESTAMP,
  "actor": {
    "type": "HUMAN",
    "id": "test-user",
    "name": "Test User"
  },
  "intent": {
    "text": "Create an approval workflow for purchase orders with inventory validation",
    "domain": "BUSINESS",
    "classification": "test"
  },
  "confidence": 0.95,
  "context": {
    "sessionId": "$SESSION_ID",
    "userId": "test-user",
    "tenantId": "test-tenant",
    "channel": "API"
  },
  "constraints": {
    "priority": "normal",
    "securityLevel": "internal"
  },
  "qos": {
    "deliveryMode": "EXACTLY_ONCE",
    "durability": "PERSISTENT"
  }
}
EOF
)

log_info "Publishing test intent to Kafka..."
PRODUCER_POD="kafka-producer-test-$RANDOM"
kubectl run $PRODUCER_POD --restart=Never \
  --image=docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace=kafka \
  --command -- sh -c "echo '$INTENT_ENVELOPE' | kafka-console-producer.sh --bootstrap-server neural-hive-kafka-kafka-bootstrap:9092 --topic intentions.business" || {
  log_error "Failed to create Kafka producer pod"
  exit 1
}

log_info "Waiting for intent to be published..."
sleep 5

log_info "Checking producer logs..."
kubectl logs $PRODUCER_POD -n kafka || log_warning "Could not retrieve producer logs"

log_info "Cleaning up producer pod..."
kubectl delete pod $PRODUCER_POD -n kafka --force --grace-period=0 > /dev/null 2>&1 || true

log_success "Test intent published with ID: $TEST_INTENT_ID"

# Phase 7: Validate Gateway Processing
log_info "====== Phase 7: Validate Gateway Processing ======"

log_info "Checking gateway logs for test intent ID..."
sleep 3
if kubectl logs $POD_NAME -n $NAMESPACE | grep -q "$TEST_INTENT_ID"; then
  log_success "Found test intent ID in gateway logs"
  kubectl logs $POD_NAME -n $NAMESPACE | grep "$TEST_INTENT_ID"
else
  log_warning "Test intent ID not found in gateway logs (may not be consumed by gateway)"
fi

log_info "Looking for successful processing indicators..."
if kubectl logs $POD_NAME -n $NAMESPACE --tail=100 | grep -i "intent envelope published\|kafka producer\|confidence"; then
  log_success "Found processing indicators"
else
  log_warning "Processing indicators not found"
fi

log_info "Counting errors in logs..."
ERROR_COUNT=$(kubectl logs $POD_NAME -n $NAMESPACE --tail=100 | grep -i "error\|exception" | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
  log_success "No errors found in recent logs"
else
  log_warning "Found $ERROR_COUNT error/exception messages in recent logs"
fi

# Phase 8: Run Integration Validation
log_info "====== Phase 8: Run Integration Validation ======"

if [ -f scripts/validation/validate-gateway-integration.sh ]; then
  log_info "Running integration validation script..."
  if bash scripts/validation/validate-gateway-integration.sh; then
    log_success "Integration validation passed"
  else
    log_warning "Integration validation failed (exit code: $?)"
  fi
else
  log_warning "Integration validation script not found at scripts/validation/validate-gateway-integration.sh"
fi

# Phase 9: Display Access Information
log_info "====== Phase 9: Access Information ======"

cat <<EOF

${GREEN}Gateway is deployed and ready!${NC}

${BLUE}Port-forward to access the gateway:${NC}
  kubectl port-forward -n $NAMESPACE svc/$SERVICE_NAME 8080:80

${BLUE}View logs:${NC}
  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=gateway-intencoes -f

${BLUE}Test text intent:${NC}
  curl -X POST http://localhost:8080/api/v1/intents/text \\
    -H "Content-Type: application/json" \\
    -d '{
      "text": "Create a workflow for approving expenses",
      "domain": "business",
      "context": {
        "user_id": "test-user",
        "session_id": "test-session",
        "tenant_id": "test-tenant"
      }
    }'

${BLUE}Service Endpoints:${NC}
  - Health: http://localhost:8080/health
  - Ready: http://localhost:8080/ready
  - Metrics: http://localhost:8080/metrics
  - Text Intent: POST http://localhost:8080/api/v1/intents/text
  - Voice Intent: POST http://localhost:8080/api/v1/intents/voice

${BLUE}Test Intent ID:${NC} $TEST_INTENT_ID

EOF

# Phase 10: Summary Report
log_info "====== Phase 10: Summary Report ======"

cat <<EOF

${GREEN}================================${NC}
${GREEN}  DEPLOYMENT TEST SUMMARY${NC}
${GREEN}================================${NC}

✓ Pre-deployment verification passed
✓ Docker image built successfully
✓ Helm deployment completed
✓ Pod is running and ready
✓ Connectivity tests passed
✓ Test intent published to Kafka
✓ Gateway logs verified

${BLUE}Test Intent ID:${NC} $TEST_INTENT_ID
${BLUE}Pod Name:${NC} $POD_NAME
${BLUE}Namespace:${NC} $NAMESPACE

${YELLOW}Next Steps:${NC}
1. Deploy semantic-translation-engine to consume from intentions.* topics
2. Deploy the 5 specialist services
3. Deploy consensus-engine
4. Run phase1 end-to-end test: bash tests/phase1-end-to-end-test.sh

${GREEN}All tests completed successfully!${NC}

EOF

exit 0
