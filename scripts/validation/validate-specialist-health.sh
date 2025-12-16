#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

################################################################################
# Specialist Health Validation Script
#
# Description: Comprehensive validation of all specialist health after remediation
# Usage: ./scripts/validation/validate-specialist-health.sh [OPTIONS]
#
# Options:
#   --namespace NS      Specify namespace (default: neural-hive-specialists)
#   --specialist NAME   Test only specific specialist (e.g., business, technical)
#   --skip-integration  Skip integration tests (only check pod/endpoint health)
#   --verbose           Show detailed output
#
# Example:
#   ./scripts/validation/validate-specialist-health.sh --verbose
#   ./scripts/validation/validate-specialist-health.sh --specialist business
#
# Note: Dependency connectivity tests use service-level checks from the host,
# avoiding kubectl exec to ensure reliability across minimal/optimized container images.
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="${NAMESPACE:-neural-hive-specialists}"
TARGET_SPECIALIST=""
SKIP_INTEGRATION=false
VERBOSE=false
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="logs/validation-${TIMESTAMP}"

# List of specialists (used when --specialist not provided)
ALL_SPECIALISTS=("specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")
SPECIALISTS=()

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --specialist)
            TARGET_SPECIALIST="$2"
            shift 2
            ;;
        --skip-integration)
            SKIP_INTEGRATION=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--namespace NS] [--specialist NAME] [--skip-integration] [--verbose]"
            exit 1
            ;;
    esac
done

# Configure specialists list based on --specialist flag
if [ -n "${TARGET_SPECIALIST}" ]; then
    # Single specialist mode - add "specialist-" prefix if not present
    if [[ "${TARGET_SPECIALIST}" == specialist-* ]]; then
        SPECIALISTS=("${TARGET_SPECIALIST}")
    else
        SPECIALISTS=("specialist-${TARGET_SPECIALIST}")
    fi
else
    # All specialists mode
    SPECIALISTS=("${ALL_SPECIALISTS[@]}")
fi

# Create log directory
mkdir -p "${LOG_DIR}"

echo -e "${BLUE}=== Specialist Health Validation ===${NC}"
echo "Timestamp: ${TIMESTAMP}"
echo "Namespace: ${NAMESPACE}"
echo ""

################################################################################
# Helper Functions
################################################################################

pass_check() {
    ((TOTAL_CHECKS++))
    ((PASSED_CHECKS++))
    echo -e "${GREEN}✅ $1${NC}"
    [ "${VERBOSE}" = true ] && [ -n "${2:-}" ] && echo "   $2"
}

fail_check() {
    ((TOTAL_CHECKS++))
    ((FAILED_CHECKS++))
    echo -e "${RED}❌ $1${NC}"
    [ -n "${2:-}" ] && echo "   $2"
}

warn_check() {
    ((TOTAL_CHECKS++))
    ((WARNING_CHECKS++))
    echo -e "${YELLOW}⚠️  $1${NC}"
    [ -n "${2:-}" ] && echo "   $2"
}

# Check TCP connectivity from host (avoids exec into pods)
check_tcp_connectivity() {
    local service=$1
    local host=$2
    local port=$3

    # Try netcat if available
    if command -v nc &> /dev/null; then
        if timeout 5 nc -zv "${host}" "${port}" &> /dev/null; then
            return 0
        fi
    # Fallback to /dev/tcp if nc not available
    elif timeout 5 bash -c "cat < /dev/null > /dev/tcp/${host}/${port}" 2>/dev/null; then
        return 0
    # Final fallback: use kubectl run with temporary pod
    else
        if kubectl run test-connectivity-${service} --image=busybox --rm -i --restart=Never --command -- timeout 5 sh -c "cat < /dev/null > /dev/tcp/${host}/${port}" &> /dev/null; then
            return 0
        fi
    fi
    return 1
}

# Check HTTP connectivity from host (avoids exec into pods)
check_http_connectivity() {
    local service=$1
    local url=$2

    # Use kubectl port-forward to access cluster-internal services
    local temp_pod=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=specialist-business --no-headers 2>/dev/null | head -1 | awk '{print $1}' || echo "")

    if [ -n "${temp_pod}" ]; then
        # Extract host and port from URL
        local host_port=$(echo "${url}" | sed -E 's|http://([^/]+).*|\1|')
        local host=$(echo "${host_port}" | cut -d: -f1)
        local port=$(echo "${host_port}" | cut -d: -f2)

        # Use port-forward to test
        kubectl port-forward "${temp_pod}" -n "${NAMESPACE}" "${port}:${port}" > /dev/null 2>&1 &
        local pf_pid=$!
        sleep 1

        if curl -s -f --max-time 5 "http://localhost:${port}/health" > /dev/null 2>&1 || curl -s -f --max-time 5 "http://localhost:${port}/" > /dev/null 2>&1; then
            kill ${pf_pid} 2>/dev/null || true
            wait ${pf_pid} 2>/dev/null || true
            return 0
        fi

        kill ${pf_pid} 2>/dev/null || true
        wait ${pf_pid} 2>/dev/null || true
    fi

    return 1
}

################################################################################
# Validation Category 1: Pod Status
################################################################################

echo -e "${BLUE}[1/9] Validating pod status...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo ""
    echo "  ${specialist}:"

    # Check if deployment exists
    if ! kubectl get deployment "${specialist}" -n "${NAMESPACE}" > /dev/null 2>&1; then
        fail_check "Deployment not found"
        continue
    fi

    # Get pod status
    POD_STATUS=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $3}' || echo "NotFound")
    POD_READY=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $2}' || echo "0/0")
    RESTART_COUNT=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $4}' || echo "N/A")
    POD_AGE=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $5}' || echo "N/A")

    # Validate status
    if [ "${POD_STATUS}" = "Running" ]; then
        pass_check "Pod Status: Running" "Ready: ${POD_READY}, Age: ${POD_AGE}"
    elif [ "${POD_STATUS}" = "Pending" ]; then
        warn_check "Pod Status: Pending" "May be starting up"
    elif [ "${POD_STATUS}" = "CrashLoopBackOff" ]; then
        fail_check "Pod Status: CrashLoopBackOff" "Check logs for errors"
    else
        fail_check "Pod Status: ${POD_STATUS}"
    fi

    # Validate ready status
    if [ "${POD_READY}" = "1/1" ]; then
        pass_check "Ready Status: 1/1"
    else
        fail_check "Ready Status: ${POD_READY}" "Pod not ready"
    fi

    # Validate restart count
    if [ "${RESTART_COUNT}" = "0" ]; then
        pass_check "Restart Count: 0"
    elif [ "${RESTART_COUNT}" = "N/A" ]; then
        warn_check "Restart Count: N/A" "Pod may not exist"
    elif [ "${RESTART_COUNT}" -lt 3 ]; then
        warn_check "Restart Count: ${RESTART_COUNT}" "Some restarts occurred"
    else
        fail_check "Restart Count: ${RESTART_COUNT}" "Too many restarts"
    fi
done

echo ""

################################################################################
# Validation Category 2: Container Health
################################################################################

echo -e "${BLUE}[2/9] Validating container health...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo ""
    echo "  ${specialist}:"

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $1}' || echo "")

    if [ -z "${POD_NAME}" ]; then
        fail_check "No pod found"
        continue
    fi

    # Check container status
    CONTAINER_STATUS=$(kubectl get pod "${POD_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.containerStatuses[0].state}' 2>/dev/null || echo "")

    if echo "${CONTAINER_STATUS}" | grep -q "running"; then
        pass_check "Container Status: Running"
    else
        fail_check "Container Status: Not Running" "${CONTAINER_STATUS}"
    fi

    # Check for OOMKilled
    if kubectl describe pod "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | grep -q "OOMKilled"; then
        fail_check "OOM Detected" "Container was killed due to out of memory"
    else
        pass_check "No OOM Events"
    fi

    # Check resource usage
    CPU_USAGE=$(kubectl top pod "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | tail -1 | awk '{print $2}' || echo "N/A")
    MEM_USAGE=$(kubectl top pod "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | tail -1 | awk '{print $3}' || echo "N/A")

    if [ "${CPU_USAGE}" != "N/A" ] && [ "${MEM_USAGE}" != "N/A" ]; then
        pass_check "Resource Usage" "CPU: ${CPU_USAGE}, Memory: ${MEM_USAGE}"
    else
        warn_check "Resource Usage: N/A" "Metrics not available"
    fi
done

echo ""

################################################################################
# Validation Category 3: Logs Validation
################################################################################

echo -e "${BLUE}[3/9] Validating logs...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo ""
    echo "  ${specialist}:"

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $1}' || echo "")

    if [ -z "${POD_NAME}" ]; then
        fail_check "No pod found"
        continue
    fi

    # Get logs
    LOGS=$(kubectl logs "${POD_NAME}" -n "${NAMESPACE}" --tail=100 2>&1 || echo "")

    # Check for structlog errors
    if echo "${LOGS}" | grep -q "ModuleNotFoundError.*structlog"; then
        fail_check "structlog Error Found" "Missing structlog dependency"
    else
        pass_check "No structlog Errors"
    fi

    # Check for startup messages
    if echo "${LOGS}" | grep -q "gRPC server started\|Starting gRPC server"; then
        pass_check "gRPC Server Started"
    else
        warn_check "gRPC Server Message Not Found" "May still be starting"
    fi

    if echo "${LOGS}" | grep -q "HTTP server started\|Starting HTTP server"; then
        pass_check "HTTP Server Started"
    else
        warn_check "HTTP Server Message Not Found" "May still be starting"
    fi

    # Check for critical errors
    ERROR_COUNT=$(echo "${LOGS}" | grep -i "error\|exception\|failed" | grep -v "no error\|0 errors" | wc -l || echo "0")
    if [ "${ERROR_COUNT}" -eq 0 ]; then
        pass_check "No Critical Errors"
    else
        warn_check "${ERROR_COUNT} Error(s) Found" "Check logs: kubectl logs ${POD_NAME} -n ${NAMESPACE}"
    fi

    # Check dependency connections
    if echo "${LOGS}" | grep -q "Connected to MongoDB\|MongoDB.*connected"; then
        pass_check "MongoDB Connected"
    else
        warn_check "MongoDB Connection Not Confirmed"
    fi

    # Save logs for reference
    kubectl logs "${POD_NAME}" -n "${NAMESPACE}" --tail=100 > "${LOG_DIR}/logs-${specialist}.txt" 2>&1
done

echo ""

################################################################################
# Validation Category 4: Endpoint Validation
################################################################################

echo -e "${BLUE}[4/9] Validating endpoints...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo ""
    echo "  ${specialist}:"

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $1}' || echo "")

    if [ -z "${POD_NAME}" ]; then
        fail_check "No pod found"
        continue
    fi

    # Test health endpoint using port-forward
    kubectl port-forward "${POD_NAME}" -n "${NAMESPACE}" 8000:8000 > /dev/null 2>&1 &
    PF_PID_8000=$!
    sleep 1
    if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
        pass_check "Health Endpoint: 200 OK"
    else
        fail_check "Health Endpoint: Failed"
    fi
    kill ${PF_PID_8000} 2>/dev/null || true
    wait ${PF_PID_8000} 2>/dev/null || true

    # Test ready endpoint using port-forward
    kubectl port-forward "${POD_NAME}" -n "${NAMESPACE}" 8000:8000 > /dev/null 2>&1 &
    PF_PID_8000=$!
    sleep 1
    if curl -s -f http://localhost:8000/ready > /dev/null 2>&1; then
        pass_check "Ready Endpoint: 200 OK"
    else
        warn_check "Ready Endpoint: Failed" "Pod may not be fully ready"
    fi
    kill ${PF_PID_8000} 2>/dev/null || true
    wait ${PF_PID_8000} 2>/dev/null || true

    # Test metrics endpoint using port-forward
    kubectl port-forward "${POD_NAME}" -n "${NAMESPACE}" 8080:8080 > /dev/null 2>&1 &
    PF_PID_8080=$!
    sleep 1
    if curl -s http://localhost:8080/metrics 2>/dev/null | grep -q "# HELP"; then
        pass_check "Metrics Endpoint: Available"
    else
        warn_check "Metrics Endpoint: Failed"
    fi
    kill ${PF_PID_8080} 2>/dev/null || true
    wait ${PF_PID_8080} 2>/dev/null || true

    # Test gRPC endpoint using port-forward
    kubectl port-forward "${POD_NAME}" -n "${NAMESPACE}" 50051:50051 > /dev/null 2>&1 &
    PF_PID_50051=$!
    sleep 1
    if timeout 2 bash -c "cat < /dev/null > /dev/tcp/localhost/50051" 2>/dev/null; then
        pass_check "gRPC Endpoint: Reachable"
    else
        fail_check "gRPC Endpoint: Not Reachable"
    fi
    kill ${PF_PID_50051} 2>/dev/null || true
    wait ${PF_PID_50051} 2>/dev/null || true
done

echo ""

################################################################################
# Validation Category 5: Dependency Connectivity
################################################################################

echo -e "${BLUE}[5/9] Validating dependency connectivity...${NC}"
echo ""
echo "  Testing service-level connectivity (host-side checks)"
echo ""

# Test MongoDB connectivity
if check_tcp_connectivity "mongodb" "mongodb.mongodb-cluster.svc.cluster.local" "27017"; then
    pass_check "MongoDB: Reachable" "mongodb.mongodb-cluster.svc.cluster.local:27017"
else
    fail_check "MongoDB: Not Reachable" "Cannot connect to MongoDB service"
fi

# Test MLflow connectivity
if check_http_connectivity "mlflow" "http://mlflow.mlflow.svc.cluster.local:5000"; then
    pass_check "MLflow: Reachable" "mlflow.mlflow.svc.cluster.local:5000"
else
    warn_check "MLflow: Not Reachable" "MLflow service may not be deployed or ready"
fi

# Test Neo4j connectivity
if check_tcp_connectivity "neo4j" "neo4j-bolt.neo4j-cluster.svc.cluster.local" "7687"; then
    pass_check "Neo4j: Reachable" "neo4j-bolt.neo4j-cluster.svc.cluster.local:7687"
else
    fail_check "Neo4j: Not Reachable" "Cannot connect to Neo4j Bolt service"
fi

# Test Redis connectivity
if check_tcp_connectivity "redis" "neural-hive-cache.redis-cluster.svc.cluster.local" "6379"; then
    pass_check "Redis: Reachable" "neural-hive-cache.redis-cluster.svc.cluster.local:6379"
else
    fail_check "Redis: Not Reachable" "Cannot connect to Redis service"
fi

echo ""

################################################################################
# Validation Category 6: Resource Usage
################################################################################

echo -e "${BLUE}[6/9] Validating resource usage...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo ""
    echo "  ${specialist}:"

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $1}' || echo "")

    if [ -z "${POD_NAME}" ]; then
        fail_check "No pod found"
        continue
    fi

    # Get resource limits
    CPU_LIMIT=$(kubectl get pod "${POD_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.containers[0].resources.limits.cpu}' 2>/dev/null || echo "N/A")
    MEM_LIMIT=$(kubectl get pod "${POD_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.containers[0].resources.limits.memory}' 2>/dev/null || echo "N/A")

    # Get current usage
    CPU_USAGE=$(kubectl top pod "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | tail -1 | awk '{print $2}' || echo "N/A")
    MEM_USAGE=$(kubectl top pod "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | tail -1 | awk '{print $3}' || echo "N/A")

    if [ "${CPU_USAGE}" != "N/A" ] && [ "${CPU_LIMIT}" != "N/A" ]; then
        pass_check "CPU Usage: ${CPU_USAGE} / ${CPU_LIMIT}"
    else
        warn_check "CPU Usage: N/A"
    fi

    if [ "${MEM_USAGE}" != "N/A" ] && [ "${MEM_LIMIT}" != "N/A" ]; then
        pass_check "Memory Usage: ${MEM_USAGE} / ${MEM_LIMIT}"
    else
        warn_check "Memory Usage: N/A"
    fi
done

echo ""

################################################################################
# Validation Category 7: Configuration Validation
################################################################################

echo -e "${BLUE}[7/9] Validating configuration...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo ""
    echo "  ${specialist}:"

    # Check image version
    IMAGE=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "N/A")
    if [ "${IMAGE}" != "N/A" ]; then
        pass_check "Image: ${IMAGE}"
    else
        fail_check "Image: N/A"
    fi

    # Check startup probe
    STARTUP_PROBE=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].startupProbe}' 2>/dev/null || echo "")
    if [ -n "${STARTUP_PROBE}" ]; then
        pass_check "Startup Probe: Configured"
    else
        warn_check "Startup Probe: Not Configured"
    fi

    # Check ConfigMap
    if kubectl get configmap "${specialist}-config" -n "${NAMESPACE}" > /dev/null 2>&1; then
        pass_check "ConfigMap: Exists"
    else
        warn_check "ConfigMap: Not Found"
    fi

    # Check Secret
    if kubectl get secret "${specialist}-secret" -n "${NAMESPACE}" > /dev/null 2>&1; then
        pass_check "Secret: Exists"
    else
        warn_check "Secret: Not Found"
    fi
done

echo ""

################################################################################
# Validation Category 8: Integration Testing (Optional)
################################################################################

if [ "${SKIP_INTEGRATION}" = false ]; then
    echo -e "${BLUE}[8/9] Running integration tests...${NC}"
    echo ""
    echo "  (Integration tests would go here)"
    echo "  Use --skip-integration to skip this section"
else
    echo -e "${BLUE}[8/9] Skipping integration tests (--skip-integration)${NC}"
fi

echo ""

################################################################################
# Validation Category 9: Model & ML Pipeline Health
################################################################################

echo -e "${BLUE}[9/9] Validating model & ML pipeline health...${NC}"
echo ""

for specialist in "${SPECIALISTS[@]}"; do
    # Extract specialist type (remove "specialist-" prefix)
    SPECIALIST_TYPE=${specialist#specialist-}

    echo "  ${specialist}:"

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --no-headers 2>/dev/null | head -1 | awk '{print $1}' || echo "")

    if [ -z "${POD_NAME}" ]; then
        fail_check "No pod found"
        continue
    fi

    # Query enhanced /status endpoint for model_loaded
    kubectl port-forward "${POD_NAME}" -n "${NAMESPACE}" 8000:8000 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 1

    STATUS_RESPONSE=$(curl -s http://localhost:8000/status 2>/dev/null || echo "{}")

    kill ${PF_PID} 2>/dev/null || true
    wait ${PF_PID} 2>/dev/null || true

    # Parse model_loaded from details
    MODEL_LOADED=$(echo "${STATUS_RESPONSE}" | jq -r '.details.model_loaded // "unknown"' 2>/dev/null)
    MLFLOW_CONNECTED=$(echo "${STATUS_RESPONSE}" | jq -r '.details.mlflow_connected // "unknown"' 2>/dev/null)
    STATUS_VALUE=$(echo "${STATUS_RESPONSE}" | jq -r '.status // "UNKNOWN"' 2>/dev/null)

    # Validate model loaded
    if [ "${MODEL_LOADED}" = "True" ] || [ "${MODEL_LOADED}" = "true" ]; then
        pass_check "Model Loaded: Yes"
    elif [ "${MODEL_LOADED}" = "False" ] || [ "${MODEL_LOADED}" = "false" ]; then
        fail_check "Model Loaded: No" "Model not loaded - check MLflow and pod logs"
    else
        warn_check "Model Loaded: Unknown" "Could not determine model status"
    fi

    # Validate MLflow connection
    if [ "${MLFLOW_CONNECTED}" = "True" ] || [ "${MLFLOW_CONNECTED}" = "true" ]; then
        pass_check "MLflow Connected: Yes"
    elif [ "${MLFLOW_CONNECTED}" = "False" ] || [ "${MLFLOW_CONNECTED}" = "false" ]; then
        warn_check "MLflow Connected: No" "MLflow not connected - specialist may use fallback"
    fi

    # Validate serving status
    if [ "${STATUS_VALUE}" = "SERVING" ]; then
        pass_check "Serving Status: SERVING"
    else
        fail_check "Serving Status: ${STATUS_VALUE}" "Expected SERVING, got ${STATUS_VALUE}"
    fi

    # Check degraded reasons if present
    DEGRADED_REASONS=$(echo "${STATUS_RESPONSE}" | jq -r '.details.degraded_reasons[]? // empty' 2>/dev/null)
    if [ -n "${DEGRADED_REASONS}" ]; then
        warn_check "Degraded Mode Detected" "Reasons: ${DEGRADED_REASONS}"
    fi

    # Optional: Run inference test if test script exists
    INFERENCE_SCRIPT="./test-specialist-inference.py"
    if [ -f "${INFERENCE_SCRIPT}" ] && [ "${VERBOSE}" = true ]; then
        if python3 "${INFERENCE_SCRIPT}" --specialist "${SPECIALIST_TYPE}" --namespace "${NAMESPACE}" > /dev/null 2>&1; then
            pass_check "Model Inference: Working" "Test inference completed successfully"
        else
            warn_check "Model Inference: Failed" "Inference test did not pass"
        fi
    fi
done

echo ""

################################################################################
# Generate Summary Report
################################################################################

{
    echo "# Specialist Health Validation Report"
    echo "Generated: ${TIMESTAMP}"
    echo "Namespace: ${NAMESPACE}"
    echo ""

    echo "## Summary"
    echo ""
    echo "- Total Checks: ${TOTAL_CHECKS}"
    echo "- Passed: ${PASSED_CHECKS}"
    echo "- Failed: ${FAILED_CHECKS}"
    echo "- Warnings: ${WARNING_CHECKS}"
    echo ""

    if [ "${FAILED_CHECKS}" -eq 0 ] && [ "${WARNING_CHECKS}" -eq 0 ]; then
        echo "✅ **All checks passed!**"
    elif [ "${FAILED_CHECKS}" -eq 0 ]; then
        echo "⚠️  **All checks passed with warnings**"
    else
        echo "❌ **Some checks failed**"
    fi
    echo ""

    echo "## Detailed Results"
    echo ""
    echo "See logs in: \`${LOG_DIR}/\`"
    echo ""

} > "${LOG_DIR}/VALIDATION_REPORT.md"

################################################################################
# Summary
################################################################################

echo -e "${BLUE}=== Validation Summary ===${NC}"
echo ""
echo "Total Checks: ${TOTAL_CHECKS}"
echo "Passed: ${PASSED_CHECKS}"
echo "Failed: ${FAILED_CHECKS}"
echo "Warnings: ${WARNING_CHECKS}"
echo ""

if [ "${FAILED_CHECKS}" -eq 0 ] && [ "${WARNING_CHECKS}" -eq 0 ]; then
    echo -e "${GREEN}✅ All specialists are healthy!${NC}"
    echo ""
    echo "Validation report: ${LOG_DIR}/VALIDATION_REPORT.md"
    exit 0
elif [ "${FAILED_CHECKS}" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  All checks passed with warnings${NC}"
    echo ""
    echo "Review warnings in: ${LOG_DIR}/VALIDATION_REPORT.md"
    exit 0
else
    echo -e "${RED}❌ Validation failed${NC}"
    echo ""
    echo "Failed checks: ${FAILED_CHECKS}"
    echo "Review details in: ${LOG_DIR}/VALIDATION_REPORT.md"
    echo ""
    echo "Troubleshooting:"
    echo "- Check pod logs: kubectl logs <pod-name> -n ${NAMESPACE}"
    echo "- Check pod description: kubectl describe pod <pod-name> -n ${NAMESPACE}"
    echo "- Run diagnostics: ./scripts/diagnostics/collect-pod-diagnostics.sh"
    exit 1
fi
