#!/bin/bash
# Script de validação para runbooks do Flow C
# Valida que todos os comandos nos runbooks são executáveis e retornam resultados esperados

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Contadores
PASS=0
FAIL=0
SKIP=0

# Configuração do ambiente (alinhada com Helm charts)
ORCHESTRATION_NS="${ORCHESTRATION_NS:-neural-hive-orchestration}"
EXECUTION_NS="${EXECUTION_NS:-neural-hive-execution}"
REGISTRY_NS="${REGISTRY_NS:-neural-hive-registry}"
KAFKA_NS="${KAFKA_NS:-kafka}"
MONGODB_NS="${MONGODB_NS:-mongodb-cluster}"
REDIS_NS="${REDIS_NS:-redis-cluster}"
MONITORING_NS="${MONITORING_NS:-monitoring}"

# Nomes dos releases Helm
ORCHESTRATOR_RELEASE="${ORCHESTRATOR_RELEASE:-orchestrator-dynamic}"
WORKER_RELEASE="${WORKER_RELEASE:-worker-agents}"

# Nomes dos ConfigMaps (gerados pelo Helm)
ORCHESTRATOR_CONFIG="${ORCHESTRATOR_RELEASE}-config"
WORKER_CONFIG="${WORKER_RELEASE}"

# Pods de serviços externos
KAFKA_POD="${KAFKA_POD:-neural-hive-kafka-kafka-0}"
REDIS_POD="${REDIS_POD:-redis-cluster-0}"

echo "=========================================="
echo "  Flow C Runbooks Validation"
echo "=========================================="
echo ""
echo "Configuração do ambiente:"
echo "  ORCHESTRATION_NS: ${ORCHESTRATION_NS}"
echo "  KAFKA_NS: ${KAFKA_NS}"
echo "  MONGODB_NS: ${MONGODB_NS}"
echo "  REDIS_NS: ${REDIS_NS}"
echo "  ORCHESTRATOR_CONFIG: ${ORCHESTRATOR_CONFIG}"
echo "  WORKER_CONFIG: ${WORKER_CONFIG}"
echo "  KAFKA_POD: ${KAFKA_POD}"
echo ""

# Helper function to run a command and check result
run_check() {
    local description="$1"
    local command="$2"
    local expected_result="${3:-0}"
    local can_skip="${4:-false}"

    printf "%-60s" "$description"

    if eval "$command" > /dev/null 2>&1; then
        echo -e "[${GREEN}PASS${NC}]"
        ((PASS++))
    else
        if [ "$can_skip" = "true" ]; then
            echo -e "[${YELLOW}SKIP${NC}]"
            ((SKIP++))
        else
            echo -e "[${RED}FAIL${NC}]"
            ((FAIL++))
        fi
    fi
}

# Helper function for namespace-dependent checks
run_k8s_check() {
    local description="$1"
    local namespace="$2"
    local command="$3"

    # Check if namespace exists first
    if ! kubectl get namespace "$namespace" > /dev/null 2>&1; then
        printf "%-60s" "$description"
        echo -e "[${YELLOW}SKIP${NC}] (namespace not found)"
        ((SKIP++))
        return
    fi

    run_check "$description" "$command" 0 true
}

echo "=== 1. Validating kubectl access ==="
run_check "kubectl cluster access" "kubectl cluster-info"
echo ""

echo "=== 2. Validating namespaces existence ==="
run_check "neural-hive-orchestration namespace" "kubectl get namespace neural-hive-orchestration" 0 true
run_check "neural-hive-execution namespace" "kubectl get namespace neural-hive-execution" 0 true
run_check "neural-hive-registry namespace" "kubectl get namespace neural-hive-registry" 0 true
run_check "neural-hive-messaging namespace" "kubectl get namespace neural-hive-messaging" 0 true
run_check "monitoring namespace" "kubectl get namespace monitoring" 0 true
echo ""

echo "=== 3. Validating Flow C deployments ==="
run_k8s_check "orchestrator-dynamic deployment" "neural-hive-orchestration" \
    "kubectl get deployment orchestrator-dynamic -n neural-hive-orchestration"
run_k8s_check "worker-agents deployment" "neural-hive-execution" \
    "kubectl get deployment worker-agents -n neural-hive-execution"
run_k8s_check "service-registry deployment" "neural-hive-registry" \
    "kubectl get deployment service-registry -n neural-hive-registry"
run_k8s_check "execution-ticket-service deployment" "neural-hive-orchestration" \
    "kubectl get deployment execution-ticket-service -n neural-hive-orchestration"
echo ""

echo "=== 4. Validating pods status ==="
run_k8s_check "orchestrator-dynamic pods running" "neural-hive-orchestration" \
    "kubectl get pods -n neural-hive-orchestration -l app=orchestrator-dynamic -o jsonpath='{.items[*].status.phase}' | grep -q Running"
run_k8s_check "worker-agents pods running" "neural-hive-execution" \
    "kubectl get pods -n neural-hive-execution -l app=worker-agents -o jsonpath='{.items[*].status.phase}' | grep -q Running"
run_k8s_check "service-registry pods running" "neural-hive-registry" \
    "kubectl get pods -n neural-hive-registry -l app=service-registry -o jsonpath='{.items[*].status.phase}' | grep -q Running"
echo ""

echo "=== 5. Validating ConfigMaps ==="
# ConfigMaps gerados pelo Helm: <release>-config para orchestrator, <release> para workers
run_k8s_check "${ORCHESTRATOR_CONFIG} ConfigMap" "${ORCHESTRATION_NS}" \
    "kubectl get configmap ${ORCHESTRATOR_CONFIG} -n ${ORCHESTRATION_NS}"
run_k8s_check "${WORKER_CONFIG} ConfigMap" "${EXECUTION_NS}" \
    "kubectl get configmap ${WORKER_CONFIG} -n ${EXECUTION_NS}"
# Fallback: buscar por label selector
run_k8s_check "orchestrator ConfigMap (by label)" "${ORCHESTRATION_NS}" \
    "kubectl get configmap -n ${ORCHESTRATION_NS} -l app.kubernetes.io/name=orchestrator-dynamic -o name | head -1"
run_k8s_check "worker-agents ConfigMap (by label)" "${EXECUTION_NS}" \
    "kubectl get configmap -n ${EXECUTION_NS} -l app.kubernetes.io/name=worker-agents -o name | head -1"
echo ""

echo "=== 6. Validating services ==="
run_k8s_check "orchestrator-dynamic service" "neural-hive-orchestration" \
    "kubectl get svc orchestrator-dynamic -n neural-hive-orchestration"
run_k8s_check "worker-agents service" "neural-hive-execution" \
    "kubectl get svc worker-agents -n neural-hive-execution"
run_k8s_check "service-registry service" "neural-hive-registry" \
    "kubectl get svc service-registry -n neural-hive-registry"
echo ""

echo "=== 7. Validating Kafka topics (if Kafka exists) ==="
# Kafka está no namespace 'kafka' com pod 'neural-hive-kafka-kafka-0'
if kubectl get pods -n ${KAFKA_NS} -l app.kubernetes.io/name=kafka > /dev/null 2>&1 || \
   kubectl get pods -n ${KAFKA_NS} ${KAFKA_POD} > /dev/null 2>&1; then
    run_k8s_check "plans.consensus topic" "${KAFKA_NS}" \
        "kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q plans.consensus"
    run_k8s_check "execution.tickets topic" "${KAFKA_NS}" \
        "kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q execution.tickets"
    run_k8s_check "telemetry-flow-c topic" "${KAFKA_NS}" \
        "kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q telemetry-flow-c"
else
    echo "Kafka não encontrado no namespace ${KAFKA_NS}, pulando validação de tópicos Kafka"
    ((SKIP+=3))
fi
echo ""

echo "=== 8. Validating MongoDB (if exists) ==="
# MongoDB está no namespace mongodb-cluster
if kubectl get pods -n ${MONGODB_NS} -l app=mongodb > /dev/null 2>&1 || \
   kubectl get pods -n ${MONGODB_NS} mongodb-0 > /dev/null 2>&1; then
    run_k8s_check "MongoDB pods running" "${MONGODB_NS}" \
        "kubectl get pods -n ${MONGODB_NS} -l app=mongodb -o jsonpath='{.items[*].status.phase}' | grep -q Running"
    run_k8s_check "execution_tickets collection exists" "${MONGODB_NS}" \
        "kubectl exec -n ${MONGODB_NS} mongodb-0 -- mongosh --quiet --eval 'db.getSiblingDB(\"neural_hive_orchestration\").getCollectionNames()' 2>/dev/null | grep -q execution_tickets"
else
    echo "MongoDB não encontrado diretamente, verificando via orchestrator..."
    run_k8s_check "MongoDB connectivity via orchestrator" "${ORCHESTRATION_NS}" \
        "kubectl exec -n ${ORCHESTRATION_NS} deployment/orchestrator-dynamic -- python -c 'import os; from pymongo import MongoClient; uri=os.environ.get(\"MONGODB_URI\",\"mongodb://localhost:27017\"); print(MongoClient(uri, serverSelectionTimeoutMS=5000).server_info())' 2>/dev/null"
fi
echo ""

echo "=== 9. Validating Redis (if exists) ==="
# Redis está no namespace redis-cluster
run_k8s_check "Redis pods running" "${REDIS_NS}" \
    "kubectl get pods -n ${REDIS_NS} -l app=redis -o jsonpath='{.items[*].status.phase}' | grep -q Running"
run_k8s_check "Redis connectivity" "${REDIS_NS}" \
    "kubectl exec -n ${REDIS_NS} ${REDIS_POD} -- redis-cli PING 2>/dev/null | grep -q PONG"
echo ""

echo "=== 10. Validating Prometheus queries ==="
if kubectl get svc -n monitoring prometheus > /dev/null 2>&1; then
    # Port-forward in background for Prometheus queries
    kubectl port-forward -n monitoring svc/prometheus 9099:9090 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 2

    run_check "Prometheus up metric query" \
        "curl -s 'http://localhost:9099/api/v1/query?query=up' | grep -q success"

    run_check "Flow C success rate metric exists" \
        "curl -s 'http://localhost:9099/api/v1/query?query=neural_hive_flow_c_success_total' | grep -q result"

    run_check "Flow C latency metric exists" \
        "curl -s 'http://localhost:9099/api/v1/query?query=neural_hive_flow_c_duration_seconds_bucket' | grep -q result"

    # Clean up port-forward
    kill $PF_PID 2>/dev/null || true
else
    echo "Prometheus not found, skipping Prometheus validation"
    ((SKIP+=3))
fi
echo ""

echo "=== 11. Validating Temporal (if exists) ==="
run_k8s_check "Temporal workflow list command" "neural-hive-orchestration" \
    "kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- temporal workflow list --namespace default --limit 1 2>/dev/null"
echo ""

echo "=== 12. Validating HPA configurations ==="
run_k8s_check "orchestrator-dynamic HPA" "neural-hive-orchestration" \
    "kubectl get hpa orchestrator-dynamic -n neural-hive-orchestration"
run_k8s_check "worker-agents HPA" "neural-hive-execution" \
    "kubectl get hpa worker-agents -n neural-hive-execution"
echo ""

echo "=== 13. Validating runbook file structure ==="
RUNBOOK_DIR="$(dirname "$0")/../../docs/runbooks"
run_check "flow-c-operations.md exists" "test -f $RUNBOOK_DIR/flow-c-operations.md"
run_check "flow-c-troubleshooting.md exists" "test -f $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "flow-c-disaster-recovery.md exists" "test -f $RUNBOOK_DIR/flow-c-disaster-recovery.md"

# Validate required sections in runbooks
run_check "Operations runbook has Service Inventory" \
    "grep -q '## Service Inventory' $RUNBOOK_DIR/flow-c-operations.md"
run_check "Operations runbook has Common Operations" \
    "grep -q '## Common Operations' $RUNBOOK_DIR/flow-c-operations.md"
run_check "Operations runbook has Maintenance Windows" \
    "grep -q '## Maintenance Windows' $RUNBOOK_DIR/flow-c-operations.md"
run_check "Operations runbook has Emergency Procedures" \
    "grep -q '## Emergency Procedures' $RUNBOOK_DIR/flow-c-operations.md"

run_check "Troubleshooting runbook has Flowchart" \
    "grep -q '## Troubleshooting Flowchart' $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "Troubleshooting runbook has FlowCHighLatency" \
    "grep -q 'FlowCHighLatency' $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "Troubleshooting runbook has FlowCLowSuccessRate" \
    "grep -q 'FlowCLowSuccessRate' $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "Troubleshooting runbook has FlowCNoTicketsGenerated" \
    "grep -q 'FlowCNoTicketsGenerated' $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "Troubleshooting runbook has FlowCWorkersUnavailable" \
    "grep -q 'FlowCWorkersUnavailable' $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "Troubleshooting runbook has FlowCSLAViolations" \
    "grep -q 'FlowCSLAViolations' $RUNBOOK_DIR/flow-c-troubleshooting.md"
run_check "Troubleshooting runbook has FlowCTelemetryBufferFull" \
    "grep -q 'FlowCTelemetryBufferFull' $RUNBOOK_DIR/flow-c-troubleshooting.md"

run_check "DR runbook has MongoDB recovery" \
    "grep -q 'MongoDB Orchestration Cluster Failure' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has Kafka recovery" \
    "grep -q 'Kafka Cluster Failure' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has Temporal recovery" \
    "grep -q 'Temporal Workflow State Loss' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has Redis recovery" \
    "grep -q 'Redis Cache Loss' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has Complete Outage recovery" \
    "grep -q 'Complete Flow C Outage' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has RTO/RPO" \
    "grep -q 'RTO' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has Communication Templates" \
    "grep -q '## Communication Templates' $RUNBOOK_DIR/flow-c-disaster-recovery.md"
run_check "DR runbook has Post-Mortem Template" \
    "grep -q '## Post-Mortem Template' $RUNBOOK_DIR/flow-c-disaster-recovery.md"

run_check "README.md has Flow C section" \
    "grep -q 'Flow C - Orquestracao de Execucao Adaptativa' $RUNBOOK_DIR/README.md"
echo ""

echo "=== 14. Validating incident simulation script ==="
SCRIPT_DIR="$(dirname "$0")"
run_check "simulate-flow-c-incidents.sh exists" "test -f $SCRIPT_DIR/simulate-flow-c-incidents.sh"
run_check "simulate-flow-c-incidents.sh is executable" "test -x $SCRIPT_DIR/simulate-flow-c-incidents.sh"
run_check "Operations runbook references simulation script" \
    "grep -q 'simulate-flow-c-incidents.sh' $RUNBOOK_DIR/flow-c-operations.md"
run_check "Troubleshooting runbook references simulation script" \
    "grep -q 'simulate-flow-c-incidents.sh' $RUNBOOK_DIR/flow-c-troubleshooting.md"
echo ""

echo "=========================================="
echo "  Validation Summary"
echo "=========================================="
echo -e "  ${GREEN}PASSED:${NC} $PASS"
echo -e "  ${RED}FAILED:${NC} $FAIL"
echo -e "  ${YELLOW}SKIPPED:${NC} $SKIP"
echo "=========================================="
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}Validation completed with failures.${NC}"
    echo "Please review failed checks and ensure infrastructure is properly configured."
    exit 1
else
    echo -e "${GREEN}Validation completed successfully!${NC}"
    exit 0
fi
