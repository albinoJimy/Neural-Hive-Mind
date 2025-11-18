#!/bin/bash
# validate-phase1-final.sh - Final validation script for Phase 1 completion
# Executes comprehensive checks across infrastructure, services, observability, and governance

set -e

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="/jimy/Neural-Hive-Mind/tests/results/phase1"
OUTPUT_FILE="$OUTPUT_DIR/e2e/phase1-final-validation-$TIMESTAMP.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR/e2e"

# Log function
log() {
    echo -e "$1" | tee -a "$OUTPUT_FILE"
}

check_pass() {
    ((TOTAL_CHECKS++))
    ((PASSED_CHECKS++))
    log "${GREEN}✅ PASS${NC}: $1"
}

check_fail() {
    ((TOTAL_CHECKS++))
    ((FAILED_CHECKS++))
    log "${RED}❌ FAIL${NC}: $1"
}

check_warn() {
    ((TOTAL_CHECKS++))
    ((WARNING_CHECKS++))
    log "${YELLOW}⚠️  WARN${NC}: $1"
}

# Header
log "========================================================"
log "Neural Hive-Mind - Phase 1 Final Validation"
log "========================================================"
log "Timestamp: $(date)"
log "Output: $OUTPUT_FILE"
log ""

# ============================================================
# 1. INFRASTRUCTURE VALIDATION
# ============================================================
log "========================================================"
log "1. INFRASTRUCTURE VALIDATION"
log "========================================================"
log ""

# 1.1 Kafka
log "1.1 Checking Kafka..."
if kubectl get statefulset -n kafka -l strimzi.io/cluster >/dev/null 2>&1; then
    KAFKA_PODS=$(kubectl get pods -n kafka -l strimzi.io/kind=Kafka -o json | jq -r '.items | length')
    KAFKA_READY=$(kubectl get pods -n kafka -l strimzi.io/kind=Kafka -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$KAFKA_PODS" -gt 0 && "$KAFKA_READY" -eq "$KAFKA_PODS" ]]; then
        check_pass "Kafka cluster operational ($KAFKA_READY/$KAFKA_PODS pods ready)"
    else
        check_fail "Kafka cluster not fully ready ($KAFKA_READY/$KAFKA_PODS pods ready)"
    fi
else
    check_fail "Kafka StatefulSet not found"
fi

# 1.2 MongoDB
log "1.2 Checking MongoDB..."
if kubectl get pods -n mongodb-cluster >/dev/null 2>&1; then
    MONGO_PODS=$(kubectl get pods -n mongodb-cluster -o json | jq -r '.items | length')
    MONGO_READY=$(kubectl get pods -n mongodb-cluster -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$MONGO_PODS" -gt 0 && "$MONGO_READY" -eq "$MONGO_PODS" ]]; then
        check_pass "MongoDB cluster operational ($MONGO_READY/$MONGO_PODS pods ready)"
    else
        check_fail "MongoDB cluster not fully ready ($MONGO_READY/$MONGO_PODS pods ready)"
    fi
else
    check_fail "MongoDB pods not found"
fi

# 1.3 Redis
log "1.3 Checking Redis..."
if kubectl get pods -n redis-cluster >/dev/null 2>&1; then
    REDIS_PODS=$(kubectl get pods -n redis-cluster -o json | jq -r '.items | length')
    REDIS_READY=$(kubectl get pods -n redis-cluster -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$REDIS_PODS" -gt 0 && "$REDIS_READY" -eq "$REDIS_PODS" ]]; then
        check_pass "Redis cluster operational ($REDIS_READY/$REDIS_PODS pods ready)"
    else
        check_warn "Redis not fully ready ($REDIS_READY/$REDIS_PODS pods ready)"
    fi
else
    check_warn "Redis pods not found (acceptable for minimal deployment)"
fi

# 1.4 Neo4j
log "1.4 Checking Neo4j..."
if kubectl get pods -n neo4j-cluster >/dev/null 2>&1; then
    NEO4J_PODS=$(kubectl get pods -n neo4j-cluster -o json | jq -r '.items | length')
    NEO4J_READY=$(kubectl get pods -n neo4j-cluster -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$NEO4J_PODS" -gt 0 && "$NEO4J_READY" -eq "$NEO4J_PODS" ]]; then
        check_pass "Neo4j cluster operational ($NEO4J_READY/$NEO4J_PODS pods ready)"
    else
        check_fail "Neo4j cluster not fully ready ($NEO4J_READY/$NEO4J_PODS pods ready)"
    fi
else
    check_fail "Neo4j pods not found"
fi

# 1.5 ClickHouse (optional)
log "1.5 Checking ClickHouse (optional)..."
if kubectl get pods -n clickhouse-cluster >/dev/null 2>&1; then
    CLICKHOUSE_PODS=$(kubectl get pods -n clickhouse-cluster -o json | jq -r '.items | length')
    CLICKHOUSE_READY=$(kubectl get pods -n clickhouse-cluster -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$CLICKHOUSE_PODS" -gt 0 && "$CLICKHOUSE_READY" -eq "$CLICKHOUSE_PODS" ]]; then
        check_pass "ClickHouse cluster operational (optional - $CLICKHOUSE_READY/$CLICKHOUSE_PODS pods ready)"
    else
        check_warn "ClickHouse not ready (optional - $CLICKHOUSE_READY/$CLICKHOUSE_PODS pods ready)"
    fi
else
    check_warn "ClickHouse not deployed (optional component)"
fi

log ""

# ============================================================
# 2. SERVICES VALIDATION
# ============================================================
log "========================================================"
log "2. SERVICES VALIDATION"
log "========================================================"
log ""

# Array of services to check
declare -A SERVICES=(
    ["gateway-intencoes"]="gateway-intencoes"
    ["semantic-translation-engine"]="semantic-translation-engine"
    ["specialist-business"]="specialist-business"
    ["specialist-technical"]="specialist-technical"
    ["specialist-behavior"]="specialist-behavior"
    ["specialist-evolution"]="specialist-evolution"
    ["specialist-architecture"]="specialist-architecture"
    ["consensus-engine"]="consensus-engine"
    ["memory-layer-api"]="memory-layer-api"
)

for namespace in "${!SERVICES[@]}"; do
    service="${SERVICES[$namespace]}"
    log "2.${TOTAL_CHECKS} Checking $service..."

    if kubectl get deployment "$service" -n "$namespace" >/dev/null 2>&1; then
        DESIRED=$(kubectl get deployment "$service" -n "$namespace" -o json | jq -r '.spec.replicas')
        READY=$(kubectl get deployment "$service" -n "$namespace" -o json | jq -r '.status.readyReplicas // 0')

        if [[ "$READY" -eq "$DESIRED" && "$READY" -gt 0 ]]; then
            check_pass "$service deployment ready ($READY/$DESIRED replicas)"
        else
            check_fail "$service deployment not ready ($READY/$DESIRED replicas)"
        fi
    else
        check_fail "$service deployment not found in namespace $namespace"
    fi
done

log ""

# ============================================================
# 3. END-TO-END CONNECTIVITY VALIDATION
# ============================================================
log "========================================================"
log "3. END-TO-END CONNECTIVITY VALIDATION"
log "========================================================"
log ""

# 3.1 Kafka Topics
log "3.1 Checking Kafka topics..."
KAFKA_POD=$(kubectl get pod -n kafka -l strimzi.io/kind=Kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -n "$KAFKA_POD" ]]; then
    TOPICS=$(kubectl exec -n kafka "$KAFKA_POD" -- kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l)
    if [[ "$TOPICS" -ge 10 ]]; then
        check_pass "Kafka topics operational ($TOPICS topics found)"
    else
        check_warn "Low number of Kafka topics ($TOPICS topics found)"
    fi
else
    check_fail "Cannot access Kafka pod for topic validation"
fi

# 3.2 DNS Resolution
log "3.2 Checking DNS resolution..."
TEST_SERVICES=("mongodb.mongodb-cluster.svc.cluster.local" "neo4j.neo4j-cluster.svc.cluster.local" "gateway-intencoes.gateway-intencoes.svc.cluster.local")
DNS_SUCCESS=0
for svc in "${TEST_SERVICES[@]}"; do
    if kubectl run dns-test-$RANDOM --image=busybox --rm -it --restart=Never -- nslookup "$svc" >/dev/null 2>&1; then
        ((DNS_SUCCESS++))
    fi
done
if [[ "$DNS_SUCCESS" -eq "${#TEST_SERVICES[@]}" ]]; then
    check_pass "DNS resolution operational (${DNS_SUCCESS}/${#TEST_SERVICES[@]} services resolved)"
else
    check_warn "DNS resolution partial (${DNS_SUCCESS}/${#TEST_SERVICES[@]} services resolved)"
fi

log ""

# ============================================================
# 4. OBSERVABILITY VALIDATION
# ============================================================
log "========================================================"
log "4. OBSERVABILITY VALIDATION"
log "========================================================"
log ""

# 4.1 Prometheus (if deployed)
log "4.1 Checking Prometheus..."
if kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=prometheus >/dev/null 2>&1; then
    PROM_PODS=$(kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=prometheus -o json | jq -r '.items | length')
    PROM_READY=$(kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=prometheus -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$PROM_PODS" -gt 0 && "$PROM_READY" -eq "$PROM_PODS" ]]; then
        check_pass "Prometheus operational ($PROM_READY/$PROM_PODS pods ready)"
    else
        check_warn "Prometheus not fully ready ($PROM_READY/$PROM_PODS pods ready)"
    fi
else
    check_warn "Prometheus not deployed (observability stack pending)"
fi

# 4.2 Grafana (if deployed)
log "4.2 Checking Grafana..."
if kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=grafana >/dev/null 2>&1; then
    GRAFANA_PODS=$(kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=grafana -o json | jq -r '.items | length')
    GRAFANA_READY=$(kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=grafana -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$GRAFANA_PODS" -gt 0 && "$GRAFANA_READY" -eq "$GRAFANA_PODS" ]]; then
        check_pass "Grafana operational ($GRAFANA_READY/$GRAFANA_PODS pods ready)"
    else
        check_warn "Grafana not fully ready ($GRAFANA_READY/$GRAFANA_PODS pods ready)"
    fi
else
    check_warn "Grafana not deployed (observability stack pending)"
fi

# 4.3 ServiceMonitors
log "4.3 Checking ServiceMonitors..."
if kubectl get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1; then
    SM_COUNT=$(kubectl get servicemonitors -A 2>/dev/null | wc -l)
    if [[ "$SM_COUNT" -ge 5 ]]; then
        check_pass "ServiceMonitors configured ($SM_COUNT found)"
    else
        check_warn "Few ServiceMonitors configured ($SM_COUNT found)"
    fi
else
    check_warn "ServiceMonitor CRD not installed"
fi

log ""

# ============================================================
# 5. GOVERNANCE VALIDATION
# ============================================================
log "========================================================"
log "5. GOVERNANCE VALIDATION"
log "========================================================"
log ""

# 5.1 OPA Gatekeeper
log "5.1 Checking OPA Gatekeeper..."
if kubectl get pods -n gatekeeper-system >/dev/null 2>&1; then
    GK_PODS=$(kubectl get pods -n gatekeeper-system -o json | jq -r '.items | length')
    GK_READY=$(kubectl get pods -n gatekeeper-system -o json | jq -r '[.items[] | select(.status.phase=="Running")] | length')
    if [[ "$GK_PODS" -gt 0 && "$GK_READY" -eq "$GK_PODS" ]]; then
        check_pass "OPA Gatekeeper operational ($GK_READY/$GK_PODS pods ready)"
    else
        check_fail "OPA Gatekeeper not fully ready ($GK_READY/$GK_PODS pods ready)"
    fi
else
    check_fail "OPA Gatekeeper not deployed"
fi

# 5.2 ConstraintTemplates
log "5.2 Checking ConstraintTemplates..."
if kubectl get crd constrainttemplates.templates.gatekeeper.sh >/dev/null 2>&1; then
    CT_COUNT=$(kubectl get constrainttemplates 2>/dev/null | wc -l)
    if [[ "$CT_COUNT" -ge 2 ]]; then
        check_pass "ConstraintTemplates configured ($CT_COUNT found)"
    else
        check_warn "Few ConstraintTemplates configured ($CT_COUNT found)"
    fi
else
    check_fail "ConstraintTemplate CRD not installed"
fi

# 5.3 Constraints
log "5.3 Checking Constraints..."
if kubectl get crd constraints >/dev/null 2>&1 || kubectl get constraints -A >/dev/null 2>&1; then
    check_pass "Constraints API available"
else
    check_warn "Constraints not configured"
fi

log ""

# ============================================================
# 6. SUMMARY
# ============================================================
log "========================================================"
log "VALIDATION SUMMARY"
log "========================================================"
log ""
log "Total Checks: $TOTAL_CHECKS"
log "${GREEN}Passed: $PASSED_CHECKS${NC}"
log "${RED}Failed: $FAILED_CHECKS${NC}"
log "${YELLOW}Warnings: $WARNING_CHECKS${NC}"
log ""

# Calculate success rate
SUCCESS_RATE=$(echo "scale=2; ($PASSED_CHECKS / $TOTAL_CHECKS) * 100" | bc)
log "Success Rate: ${SUCCESS_RATE}%"
log ""

# Final verdict
if [[ "$FAILED_CHECKS" -eq 0 ]]; then
    log "${GREEN}========================================================"
    log "✅ PHASE 1 VALIDATION: PASSED"
    log "========================================================${NC}"
    log ""
    log "All critical components are operational."
    log "Phase 1 is ready for production use."
    EXIT_CODE=0
elif [[ "$FAILED_CHECKS" -le 2 ]]; then
    log "${YELLOW}========================================================"
    log "⚠️  PHASE 1 VALIDATION: PASSED WITH WARNINGS"
    log "========================================================${NC}"
    log ""
    log "Most components operational, but some issues detected."
    log "Review failed checks before production deployment."
    EXIT_CODE=0
else
    log "${RED}========================================================"
    log "❌ PHASE 1 VALIDATION: FAILED"
    log "========================================================${NC}"
    log ""
    log "Critical issues detected. Review failed checks."
    log "Do NOT proceed to production until resolved."
    EXIT_CODE=1
fi

log ""
log "Full report saved to: $OUTPUT_FILE"
log "========================================================"

exit $EXIT_CODE
