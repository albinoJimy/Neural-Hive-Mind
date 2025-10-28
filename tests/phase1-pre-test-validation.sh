#!/bin/bash
set -euo pipefail

# Source shared test helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/helpers/test-helpers.sh"

log_section "Neural Hive-Mind - Phase 1 Pre-Test Validation"

# Counters
CHECKS_TOTAL=0
CHECKS_PASSED=0
CHECKS_FAILED=0

# Helper function to track checks
track_check() {
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    if [ "$1" -eq 0 ]; then
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
        return 0
    else
        CHECKS_FAILED=$((CHECKS_FAILED + 1))
        return 1
    fi
}

# ========================================
# SECTION 1: Tool Validation
# ========================================
log_section "Section 1: Tool Validation"

log_info "Checking required tools..."

check_command_exists kubectl
track_check $?
check_status $? "kubectl is installed"

check_command_exists curl
track_check $?
check_status $? "curl is available"

check_command_exists jq
track_check $?
check_status $? "jq is available"

log_info "Checking kubectl cluster connection..."
check_kubectl_connection
track_check $?
check_status $? "kubectl can connect to cluster"

# ========================================
# SECTION 2: Infrastructure Validation
# ========================================
log_section "Section 2: Infrastructure Validation"

log_info "Verifying infrastructure components..."

# Kafka
log_info "Checking Kafka cluster..."
if kubectl get statefulset -n neural-hive-kafka neural-hive-kafka-kafka &> /dev/null; then
    READY=$(kubectl get statefulset -n neural-hive-kafka neural-hive-kafka-kafka -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    READY=${READY:-0}
    [ "$READY" -gt 0 ]
    track_check $?
    check_status $? "Kafka cluster (${READY} replicas ready)"
else
    track_check 1
    log_error "Kafka statefulset not found"
fi

# Redis
log_info "Checking Redis cluster..."
if kubectl get statefulset -n redis-cluster &> /dev/null 2>&1 || kubectl get deployment -n redis-cluster &> /dev/null 2>&1; then
    READY=$(kubectl get pods -n redis-cluster --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    READY=${READY:-0}
    [ "$READY" -gt 0 ]
    track_check $?
    check_status $? "Redis cluster (${READY} pods running)"
else
    track_check 1
    log_error "Redis cluster not found"
fi

# MongoDB
log_info "Checking MongoDB cluster..."
if kubectl get statefulset -n mongodb-cluster &> /dev/null; then
    READY=$(kubectl get statefulset -n mongodb-cluster -o jsonpath='{.items[0].status.readyReplicas}' 2>/dev/null || echo "0")
    READY=${READY:-0}
    [ "$READY" -gt 0 ]
    track_check $?
    check_status $? "MongoDB cluster (${READY} replicas ready)"
else
    track_check 1
    log_error "MongoDB statefulset not found"
fi

# Neo4j
log_info "Checking Neo4j cluster..."
if kubectl get statefulset -n neo4j-cluster &> /dev/null; then
    READY=$(kubectl get statefulset -n neo4j-cluster -o jsonpath='{.items[0].status.readyReplicas}' 2>/dev/null || echo "0")
    READY=${READY:-0}
    [ "$READY" -gt 0 ]
    track_check $?
    check_status $? "Neo4j cluster (${READY} replicas ready)"
else
    track_check 1
    log_error "Neo4j statefulset not found"
fi

# ClickHouse
log_info "Checking ClickHouse cluster..."
if kubectl get statefulset -n clickhouse-cluster &> /dev/null; then
    READY=$(kubectl get statefulset -n clickhouse-cluster -o jsonpath='{.items[0].status.readyReplicas}' 2>/dev/null || echo "0")
    READY=${READY:-0}
    [ "$READY" -gt 0 ]
    track_check $?
    check_status $? "ClickHouse cluster (${READY} replicas ready)"
else
    track_check 1
    log_error "ClickHouse statefulset not found"
fi

# ========================================
# SECTION 3: Phase 1 Services Validation
# ========================================
log_section "Section 3: Phase 1 Services Validation"

log_info "Verifying Phase 1 services..."

# Function to check service deployment
check_service() {
    local service_name=$1
    local namespace=$2

    if kubectl get deployment -n "$namespace" "$service_name" &> /dev/null; then
        READY=$(kubectl get deployment -n "$namespace" "$service_name" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        READY=${READY:-0}
        [ "$READY" -gt 0 ]
        track_check $?
        check_status $? "$service_name (${READY} replicas ready)"
    else
        track_check 1
        log_warning "$service_name deployment not found in namespace $namespace"
    fi
}

check_service "gateway-intencoes" "gateway-intencoes"
check_service "semantic-translation-engine" "semantic-translation-engine"
check_service "specialist-business" "specialist-business"
check_service "specialist-technical" "specialist-technical"
check_service "specialist-behavior" "specialist-behavior"
check_service "specialist-evolution" "specialist-evolution"
check_service "specialist-architecture" "specialist-architecture"
check_service "consensus-engine" "consensus-engine"
check_service "memory-layer-api" "memory-layer-api"

# ========================================
# SECTION 4: Kafka Topics Validation
# ========================================
log_section "Section 4: Kafka Topics Validation"

log_info "Verifying Kafka topics..."

KAFKA_POD=$(get_pod_name "neural-hive-kafka" "app.kubernetes.io/name=kafka")
if [ -n "$KAFKA_POD" ]; then
    for topic in "intentions.business" "plans.ready" "plans.consensus"; do
        if kafka_check_topic_exists "neural-hive-kafka" "$topic" "$KAFKA_POD"; then
            track_check 0
            log_success "Topic $topic exists"
        else
            track_check 1
            log_warning "Topic $topic not found"
        fi
    done
else
    track_check 1
    log_error "Kafka pod not found - cannot verify topics"
fi

# ========================================
# SECTION 5: Observability Stack Validation
# ========================================
log_section "Section 5: Observability Stack Validation"

log_info "Verifying observability stack..."

# Prometheus
if kubectl get deployment -n neural-hive-observability prometheus-server &> /dev/null 2>&1 || \
   kubectl get statefulset -n neural-hive-observability prometheus &> /dev/null 2>&1; then
    track_check 0
    log_success "Prometheus is deployed"
else
    track_check 1
    log_warning "Prometheus not found"
fi

# Jaeger
if kubectl get deployment -n neural-hive-observability jaeger &> /dev/null 2>&1; then
    track_check 0
    log_success "Jaeger is deployed"
else
    track_check 1
    log_warning "Jaeger not found"
fi

# Grafana
if kubectl get deployment -n neural-hive-observability grafana &> /dev/null 2>&1; then
    track_check 0
    log_success "Grafana is deployed"
else
    track_check 1
    log_warning "Grafana not found"
fi

# ========================================
# SECTION 6: Monitoring Artifacts Validation
# ========================================
log_section "Section 6: Monitoring Artifacts Validation"

log_info "Verifying monitoring artifacts..."

MONITORING_DIR="${SCRIPT_DIR}/../monitoring"

# Check dashboards
for dashboard in "specialists-cognitive-layer.json" "consensus-governance.json" "memory-layer-data-quality.json"; do
    if [ -f "${MONITORING_DIR}/dashboards/${dashboard}" ]; then
        track_check 0
        log_success "Dashboard ${dashboard} exists"
    else
        track_check 1
        log_warning "Dashboard ${dashboard} not found"
    fi
done

# Check alert files
for alert_file in "specialists-alerts.yaml" "consensus-alerts.yaml" "data-quality-alerts.yaml"; do
    if [ -f "${MONITORING_DIR}/alerts/${alert_file}" ]; then
        track_check 0
        log_success "Alert file ${alert_file} exists"
    else
        track_check 1
        log_warning "Alert file ${alert_file} not found"
    fi
done

# ========================================
# SUMMARY
# ========================================
log_section "Validation Summary"

SUCCESS_RATE=$((CHECKS_PASSED * 100 / CHECKS_TOTAL))

echo ""
echo -e "${YELLOW}Total Checks:${NC}   $CHECKS_TOTAL"
echo -e "${GREEN}Passed:${NC}        $CHECKS_PASSED"
echo -e "${RED}Failed:${NC}        $CHECKS_FAILED"
echo -e "${CYAN}Success Rate:${NC}  ${SUCCESS_RATE}%"
echo ""

if [ "$CHECKS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ All pre-test validation checks passed!${NC}"
    echo -e "${GREEN}You are ready to run the Phase 1 end-to-end test.${NC}"
    echo ""
    echo "Run: ./tests/phase1-end-to-end-test.sh"
    exit 0
else
    echo -e "${YELLOW}⚠ Some validation checks failed.${NC}"
    echo ""
    echo "Recommendations:"
    echo "1. Review the failed checks above"
    echo "2. Ensure all infrastructure is deployed correctly"
    echo "3. Check service logs for errors:"
    echo "   kubectl logs -n <namespace> <pod-name>"
    echo "4. Refer to DEPLOYMENT_LOCAL.md for setup instructions"
    echo ""
    exit 1
fi
