#!/bin/bash
set -e

echo "========================================"
echo "FASE 0 INFRASTRUCTURE VERIFICATION"
echo "========================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
}

echo "1. ISTIO SERVICE MESH"
echo "======================"

if kubectl get deployment -n istio-system istiod -o jsonpath='{.status.readyReplicas}' 2>/dev/null | grep -q "2"; then
    check_pass "istiod running (2/2 replicas)"
else
    check_fail "istiod not ready"
fi

if kubectl get svc -n istio-system istio-ingressgateway &>/dev/null; then
    check_pass "ingress gateway exists"
else
    check_fail "ingress gateway missing"
fi

MTLS_MODE=$(kubectl get peerauthentication -n neural-hive -o jsonpath='{.items[0].spec.mtls.mode}' 2>/dev/null || echo "N/A")
if [ "$MTLS_MODE" = "STRICT" ]; then
    check_pass "mTLS mode: STRICT"
else
    check_warn "mTLS mode: $MTLS_MODE (expected STRICT)"
fi

PODS_WITH_SIDECAR=$(kubectl get pods -n neural-hive -o json | jq -r '[.items[] | select(.spec.containers[].name == "istio-proxy")] | length' 2>/dev/null || echo "0")
TOTAL_PODS=$(kubectl get pods -n neural-hive --no-headers | wc -l)
echo -e "${GREEN}✓${NC} Sidecar injection: $PODS_WITH_SIDECAR/$TOTAL_PODS pods"

echo ""
echo "2. OPA GATEKEEPER"
echo "================="

if kubectl get deployment -n gatekeeper-system -l control-plane=controller-manager -o jsonpath='{.status.readyReplicas}' 2>/dev/null | grep -q "[1-9]"; then
    check_pass "Gatekeeper controller running"
else
    check_fail "Gatekeeper controller not ready"
fi

TEMPLATE_COUNT=$(kubectl get constrainttemplates --no-headers 2>/dev/null | wc -l)
echo -e "${GREEN}✓${NC} Constraint templates: $TEMPLATE_COUNT"

CONSTRAINT_COUNT=$(kubectl get constraints -A --no-headers 2>/dev/null | wc -l)
echo -e "${GREEN}✓${NC} Constraints enforced: $CONSTRAINT_COUNT"

VIOLATIONS=$(kubectl get violations -A --no-headers 2>/dev/null | wc -l)
if [ "$VIOLATIONS" -eq 0 ]; then
    check_pass "No violations"
else
    check_warn "Active violations: $VIOLATIONS"
fi

echo ""
echo "3. REDIS CLUSTER"
echo "================"

REDIS_PODS=$(kubectl get pods -n redis-cluster -l app.kubernetes.io/name=redis --no-headers 2>/dev/null | wc -l)
if [ "$REDIS_PODS" -ge 6 ]; then
    check_pass "Redis cluster pods: $REDIS_PODS (expected >= 6)"
else
    check_fail "Redis cluster pods: $REDIS_PODS (expected >= 6)"
fi

CLUSTER_STATE=$(kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli -c cluster info 2>/dev/null | grep cluster_state | cut -d: -f2 || echo "N/A")
if [ "$CLUSTER_STATE" = "ok" ]; then
    check_pass "Redis cluster state: ok"
else
    check_fail "Redis cluster state: $CLUSTER_STATE"
fi

if kubectl get secret redis-server-tls -n redis-cluster &>/dev/null; then
    check_pass "Redis TLS configured"
else
    check_fail "Redis TLS missing"
fi

echo ""
echo "========================================"
echo "VERIFICATION COMPLETE"
echo "========================================"
echo ""
echo "Run E2E tests with:"
echo "  pytest tests/integration/test_fase0_e2e.py -v"