#!/bin/bash

################################################################################
# Pod Diagnostics Collection Script
#
# Description: Automated diagnostic collection for pods in problematic states
# Usage: ./scripts/diagnostics/collect-pod-diagnostics.sh
#
# This script collects comprehensive diagnostic information about:
# - Pod status across all namespaces
# - Detailed logs from problematic pods
# - Cluster resource utilization
# - Dependency health status
# - Image availability
# - Configuration validation
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE=${1:-"neural-hive-specialists"}
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="logs/diagnostics-${TIMESTAMP}"

# Create output directory
mkdir -p "${OUTPUT_DIR}"

echo -e "${BLUE}=== Neural Hive Mind - Pod Diagnostics Collection ===${NC}"
echo "Timestamp: ${TIMESTAMP}"
echo "Target Namespace: ${NAMESPACE}"
echo "Output Directory: ${OUTPUT_DIR}"
echo ""

################################################################################
# Section 1: Cluster Overview
################################################################################

echo -e "${BLUE}[1/8] Collecting cluster overview...${NC}"

echo "Collecting node status..."
kubectl get nodes -o wide > "${OUTPUT_DIR}/nodes-status.txt" 2>&1 || echo "Failed to get nodes" > "${OUTPUT_DIR}/nodes-status.txt"

echo "Collecting node resource usage..."
kubectl top nodes > "${OUTPUT_DIR}/nodes-top.txt" 2>&1 || echo "Metrics not available" > "${OUTPUT_DIR}/nodes-top.txt"

echo "Collecting all namespaces..."
kubectl get namespaces > "${OUTPUT_DIR}/namespaces.txt" 2>&1

echo "Collecting pod counts by namespace..."
kubectl get pods -A --no-headers | awk '{print $1}' | sort | uniq -c > "${OUTPUT_DIR}/pod-counts-by-namespace.txt" 2>&1

################################################################################
# Section 2: Pod Status Collection
################################################################################

echo -e "${BLUE}[2/8] Collecting pod status in ${NAMESPACE}...${NC}"

echo "Collecting all pods status..."
kubectl get pods -n "${NAMESPACE}" -o wide > "${OUTPUT_DIR}/pods-status.txt" 2>&1 || echo "No pods found" > "${OUTPUT_DIR}/pods-status.txt"

echo "Collecting problematic pods (using JSON+jq for accurate detection)..."
# Use jq to accurately detect problematic pods including CrashLoopBackOff in Running phase
if command -v jq &> /dev/null; then
    kubectl get pods -n "${NAMESPACE}" -o json 2>/dev/null | jq -r '
        .items[] |
        select(
            (.status.phase != "Running" and .status.phase != "Succeeded") or
            (.status.containerStatuses[]?.state.waiting.reason // "" | test("CrashLoopBackOff|ImagePullBackOff|ErrImagePull")) or
            (.status.containerStatuses[]?.state.terminated.reason // "" | test("Error")) or
            (.status.containerStatuses[]?.restartCount // 0 > 3) or
            (.status.conditions[]? | select(.type == "Ready" or .type == "Initialized") | .status != "True")
        ) |
        [.metadata.name, .status.phase, (.status.containerStatuses[0].state.waiting.reason // .status.containerStatuses[0].state.terminated.reason // "N/A"), (.status.containerStatuses[0].restartCount // 0 | tostring)] |
        @tsv
    ' > "${OUTPUT_DIR}/pods-problematic.txt" 2>&1 || echo "No problematic pods detected" > "${OUTPUT_DIR}/pods-problematic.txt"
else
    # Fallback if jq not available: use custom-columns with kubectl
    kubectl get pods -n "${NAMESPACE}" -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,REASON:.status.containerStatuses[0].state.waiting.reason,RESTARTS:.status.containerStatuses[0].restartCount 2>/dev/null | awk 'NR==1 || ($2 !~ /Running|Succeeded/ || $3 ~ /CrashLoopBackOff|ImagePullBackOff|ErrImagePull/ || $4 > 3)' > "${OUTPUT_DIR}/pods-problematic.txt" 2>&1 || echo "No problematic pods" > "${OUTPUT_DIR}/pods-problematic.txt"
fi

echo "Collecting pods by status..."
{
    echo "=== Pod Status Summary ==="
    echo ""
    kubectl get pods -n "${NAMESPACE}" --no-headers 2>/dev/null | awk '{print $3}' | sort | uniq -c || echo "No pods"
} > "${OUTPUT_DIR}/pod-status-summary.txt"

################################################################################
# Section 3: Problematic Pod Details
################################################################################

echo -e "${BLUE}[3/8] Collecting details from problematic pods...${NC}"

# Get list of problematic pods using jq (includes CrashLoopBackOff even if phase=Running)
if command -v jq &> /dev/null; then
    PROBLEMATIC_PODS=$(kubectl get pods -n "${NAMESPACE}" -o json 2>/dev/null | jq -r '
        .items[] |
        select(
            (.status.phase != "Running" and .status.phase != "Succeeded") or
            (.status.containerStatuses[]?.state.waiting.reason // "" | test("CrashLoopBackOff|ImagePullBackOff|ErrImagePull")) or
            (.status.containerStatuses[]?.state.terminated.reason // "" | test("Error")) or
            (.status.containerStatuses[]?.restartCount // 0 > 3) or
            (.status.conditions[]? | select(.type == "Ready" or .type == "Initialized") | .status != "True")
        ) |
        .metadata.name
    ' || echo "")
else
    # Fallback: parse from the problematic pods file created earlier
    PROBLEMATIC_PODS=$(cat "${OUTPUT_DIR}/pods-problematic.txt" 2>/dev/null | awk 'NR>1 {print $1}' || echo "")
fi

if [ -n "${PROBLEMATIC_PODS}" ]; then
    echo "Found problematic pods, collecting details..."

    while IFS= read -r pod; do
        if [ -n "${pod}" ] && [ "${pod}" != "No" ]; then
            echo "  Processing pod: ${pod}"

            # Describe pod
            kubectl describe pod "${pod}" -n "${NAMESPACE}" > "${OUTPUT_DIR}/pod-describe-${pod}.txt" 2>&1

            # Get current logs
            kubectl logs "${pod}" -n "${NAMESPACE}" --tail=500 > "${OUTPUT_DIR}/pod-logs-${pod}.txt" 2>&1 || echo "No logs available" > "${OUTPUT_DIR}/pod-logs-${pod}.txt"

            # Get previous logs if container restarted
            kubectl logs "${pod}" -n "${NAMESPACE}" --previous --tail=500 > "${OUTPUT_DIR}/pod-logs-previous-${pod}.txt" 2>&1 || echo "No previous logs" > "${OUTPUT_DIR}/pod-logs-previous-${pod}.txt"

            # Get events for pod
            kubectl get events -n "${NAMESPACE}" --field-selector involvedObject.name="${pod}" --sort-by='.lastTimestamp' > "${OUTPUT_DIR}/pod-events-${pod}.txt" 2>&1
        fi
    done <<< "${PROBLEMATIC_PODS}"
else
    echo "No problematic pods found (all Running or Succeeded)"
    echo "No problematic pods found" > "${OUTPUT_DIR}/no-problematic-pods.txt"
fi

################################################################################
# Section 4: Specialist Deployment Status
################################################################################

echo -e "${BLUE}[4/8] Collecting specialist deployment status...${NC}"

SPECIALISTS=("specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")

for specialist in "${SPECIALISTS[@]}"; do
    echo "  Checking ${specialist}..."

    # Deployment status
    kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o wide > "${OUTPUT_DIR}/deployment-${specialist}.txt" 2>&1 || echo "Deployment not found" > "${OUTPUT_DIR}/deployment-${specialist}.txt"

    # Replica status
    kubectl get replicaset -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" > "${OUTPUT_DIR}/replicaset-${specialist}.txt" 2>&1 || echo "No replicasets" > "${OUTPUT_DIR}/replicaset-${specialist}.txt"

    # Image being used
    kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}' > "${OUTPUT_DIR}/image-${specialist}.txt" 2>&1 || echo "N/A" > "${OUTPUT_DIR}/image-${specialist}.txt"

    # ConfigMap existence
    kubectl get configmap "${specialist}-config" -n "${NAMESPACE}" > "${OUTPUT_DIR}/configmap-${specialist}.txt" 2>&1 || echo "ConfigMap not found" > "${OUTPUT_DIR}/configmap-${specialist}.txt"

    # Secret existence
    kubectl get secret "${specialist}-secret" -n "${NAMESPACE}" > "${OUTPUT_DIR}/secret-${specialist}.txt" 2>&1 || echo "Secret not found" > "${OUTPUT_DIR}/secret-${specialist}.txt"
done

################################################################################
# Section 5: Dependency Health Check
################################################################################

echo -e "${BLUE}[5/8] Checking dependency health...${NC}"

echo "Checking MongoDB..."
kubectl get pods -n "${NAMESPACE}" -l app=mongodb -o wide > "${OUTPUT_DIR}/dependency-mongodb.txt" 2>&1 || echo "MongoDB not found" > "${OUTPUT_DIR}/dependency-mongodb.txt"

echo "Checking MLflow..."
kubectl get pods -n "${NAMESPACE}" -l app=mlflow -o wide > "${OUTPUT_DIR}/dependency-mlflow.txt" 2>&1 || echo "MLflow not found" > "${OUTPUT_DIR}/dependency-mlflow.txt"

echo "Checking Neo4j..."
kubectl get pods -n "${NAMESPACE}" -l app=neo4j -o wide > "${OUTPUT_DIR}/dependency-neo4j.txt" 2>&1 || echo "Neo4j not found" > "${OUTPUT_DIR}/dependency-neo4j.txt"

echo "Checking Redis..."
kubectl get pods -n "${NAMESPACE}" -l app=redis -o wide > "${OUTPUT_DIR}/dependency-redis.txt" 2>&1 || echo "Redis not found" > "${OUTPUT_DIR}/dependency-redis.txt"

echo "Checking Kafka..."
kubectl get pods -n "${NAMESPACE}" -l app=kafka -o wide > "${OUTPUT_DIR}/dependency-kafka.txt" 2>&1 || echo "Kafka not found" > "${OUTPUT_DIR}/dependency-kafka.txt"

################################################################################
# Section 6: Resource Analysis
################################################################################

echo -e "${BLUE}[6/8] Analyzing resource utilization...${NC}"

echo "Collecting cluster capacity vs requests..."
{
    echo "=== Cluster Resource Summary ==="
    echo ""
    for node in $(kubectl get nodes --no-headers | awk '{print $1}'); do
        echo "Node: ${node}"
        kubectl describe node "${node}" | grep -A 10 "Allocated resources:" || echo "N/A"
        echo ""
    done
} > "${OUTPUT_DIR}/resource-allocation.txt"

echo "Collecting pod resource usage..."
kubectl top pods -n "${NAMESPACE}" --sort-by=cpu > "${OUTPUT_DIR}/pods-top-cpu.txt" 2>&1 || echo "Metrics not available" > "${OUTPUT_DIR}/pods-top-cpu.txt"
kubectl top pods -n "${NAMESPACE}" --sort-by=memory > "${OUTPUT_DIR}/pods-top-memory.txt" 2>&1 || echo "Metrics not available" > "${OUTPUT_DIR}/pods-top-memory.txt"

echo "Checking for resource pressure..."
{
    echo "=== Node Conditions (checking for pressure) ==="
    echo ""
    kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.name): \([.status.conditions[] | select(.status=="True") | .type] | join(", "))"'
} > "${OUTPUT_DIR}/node-conditions.txt" 2>&1

################################################################################
# Section 7: Image Availability Check
################################################################################

echo -e "${BLUE}[7/8] Checking image availability...${NC}"

echo "Listing images used by deployments..."
kubectl get deployments -n "${NAMESPACE}" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}' > "${OUTPUT_DIR}/deployment-images.txt" 2>&1

echo "Checking local registry catalog..."
curl -s http://localhost:5000/v2/_catalog 2>&1 | jq '.' > "${OUTPUT_DIR}/registry-catalog.txt" || echo "Registry not accessible" > "${OUTPUT_DIR}/registry-catalog.txt"

# Check tags for each specialist image
for specialist in "${SPECIALISTS[@]}"; do
    curl -s "http://localhost:5000/v2/${specialist}/tags/list" 2>&1 | jq '.' > "${OUTPUT_DIR}/registry-tags-${specialist}.txt" || echo "Image not found in registry" > "${OUTPUT_DIR}/registry-tags-${specialist}.txt"
done

################################################################################
# Section 8: Generate Summary Report
################################################################################

echo -e "${BLUE}[8/8] Generating summary report...${NC}"

{
    echo "# Pod Diagnostics Summary Report"
    echo "Generated: ${TIMESTAMP}"
    echo "Namespace: ${NAMESPACE}"
    echo ""

    echo "## Pod Status Overview"
    echo ""
    echo "\`\`\`"
    kubectl get pods -n "${NAMESPACE}" --no-headers 2>/dev/null | awk '{print $3}' | sort | uniq -c || echo "No pods"
    echo "\`\`\`"
    echo ""

    echo "## Critical Issues Found"
    echo ""

    # Count problematic pods using JSON filtering for accuracy
    CRASH_COUNT=$(kubectl get pods -n "${NAMESPACE}" -o json 2>/dev/null | jq '[.items[] | select(.status.containerStatuses[]?.state.waiting.reason == "CrashLoopBackOff")] | length' || echo "0")
    PENDING_COUNT=$(kubectl get pods -n "${NAMESPACE}" -o json 2>/dev/null | jq '[.items[] | select(.status.phase == "Pending")] | length' || echo "0")
    IMAGE_PULL_COUNT=$(kubectl get pods -n "${NAMESPACE}" -o json 2>/dev/null | jq '[.items[] | select(.status.containerStatuses[]?.state.waiting.reason | test("ImagePullBackOff|ErrImagePull"))] | length' || echo "0")

    if [ "${CRASH_COUNT}" -gt 0 ]; then
        echo "- ❌ ${CRASH_COUNT} pod(s) in CrashLoopBackOff state"
    fi

    if [ "${PENDING_COUNT}" -gt 0 ]; then
        echo "- ❌ ${PENDING_COUNT} pod(s) in Pending state"
    fi

    if [ "${IMAGE_PULL_COUNT}" -gt 0 ]; then
        echo "- ❌ ${IMAGE_PULL_COUNT} pod(s) with ImagePullBackOff errors"
    fi

    if [ "${CRASH_COUNT}" -eq 0 ] && [ "${PENDING_COUNT}" -eq 0 ] && [ "${IMAGE_PULL_COUNT}" -eq 0 ]; then
        echo "- ✅ No critical issues found - all pods are Running or Succeeded"
    fi
    echo ""

    echo "## Resource Utilization"
    echo ""
    echo "\`\`\`"
    kubectl top nodes 2>/dev/null || echo "Metrics not available"
    echo "\`\`\`"
    echo ""

    echo "## Specialist Deployment Status"
    echo ""
    for specialist in "${SPECIALISTS[@]}"; do
        STATUS=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" --no-headers 2>/dev/null | awk '{print $2}' || echo "N/A")
        echo "- ${specialist}: ${STATUS}"
    done
    echo ""

    echo "## Dependency Status"
    echo ""

    MONGODB_STATUS=$(kubectl get pods -n "${NAMESPACE}" -l app=mongodb --no-headers 2>/dev/null | awk '{print $3}' | head -1 || echo "Not Found")
    MLFLOW_STATUS=$(kubectl get pods -n "${NAMESPACE}" -l app=mlflow --no-headers 2>/dev/null | awk '{print $3}' | head -1 || echo "Not Found")
    NEO4J_STATUS=$(kubectl get pods -n "${NAMESPACE}" -l app=neo4j --no-headers 2>/dev/null | awk '{print $3}' | head -1 || echo "Not Found")
    REDIS_STATUS=$(kubectl get pods -n "${NAMESPACE}" -l app=redis --no-headers 2>/dev/null | awk '{print $3}' | head -1 || echo "Not Found")

    echo "- MongoDB: ${MONGODB_STATUS}"
    echo "- MLflow: ${MLFLOW_STATUS}"
    echo "- Neo4j: ${NEO4J_STATUS}"
    echo "- Redis: ${REDIS_STATUS}"
    echo ""

    echo "## Recommended Actions"
    echo ""

    if [ "${CRASH_COUNT}" -gt 0 ]; then
        echo "1. **Investigate CrashLoopBackOff pods:**"
        echo "   - Check logs in: \`${OUTPUT_DIR}/pod-logs-*.txt\`"
        echo "   - Review pod descriptions in: \`${OUTPUT_DIR}/pod-describe-*.txt\`"
        echo "   - Common causes: missing dependencies (structlog), connection failures, resource limits"
        echo ""
    fi

    if [ "${PENDING_COUNT}" -gt 0 ]; then
        echo "2. **Resolve Pending pods:**"
        echo "   - Check resource allocation: \`${OUTPUT_DIR}/resource-allocation.txt\`"
        echo "   - Review node conditions: \`${OUTPUT_DIR}/node-conditions.txt\`"
        echo "   - Consider scaling down replicas or reducing resource requests"
        echo ""
    fi

    if [ "${IMAGE_PULL_COUNT}" -gt 0 ]; then
        echo "3. **Fix image pull errors:**"
        echo "   - Verify images exist: \`${OUTPUT_DIR}/registry-catalog.txt\`"
        echo "   - Rebuild missing images: \`./scripts/remediation/rebuild-specialist-images.sh\`"
        echo ""
    fi

    if [ "${CRASH_COUNT}" -gt 0 ] || [ "${PENDING_COUNT}" -gt 0 ]; then
        echo "4. **Follow remediation guide:**"
        echo "   - See: \`REMEDIATION_GUIDE_PODS.md\` for detailed fix procedures"
        echo ""
    fi

    echo "## Detailed Diagnostic Files"
    echo ""
    echo "All diagnostic files have been saved to: \`${OUTPUT_DIR}/\`"
    echo ""
    echo "Key files:"
    echo "- \`pods-status.txt\` - Current pod status"
    echo "- \`pods-problematic.txt\` - Problematic pods only"
    echo "- \`pod-logs-*.txt\` - Container logs"
    echo "- \`pod-describe-*.txt\` - Detailed pod information"
    echo "- \`resource-allocation.txt\` - Cluster resource usage"
    echo "- \`deployment-*.txt\` - Deployment configurations"
    echo ""

} > "${OUTPUT_DIR}/SUMMARY.md"

################################################################################
# Display Summary
################################################################################

echo ""
echo -e "${GREEN}=== Diagnostic Collection Complete ===${NC}"
echo ""
echo "Summary report saved to: ${OUTPUT_DIR}/SUMMARY.md"
echo ""
echo -e "${BLUE}Quick Summary:${NC}"
cat "${OUTPUT_DIR}/SUMMARY.md" | grep -A 20 "## Critical Issues Found"
echo ""
echo "For full details, review files in: ${OUTPUT_DIR}/"
echo ""

# Exit with error code if problematic pods found
if [ "${CRASH_COUNT}" -gt 0 ] || [ "${PENDING_COUNT}" -gt 0 ] || [ "${IMAGE_PULL_COUNT}" -gt 0 ]; then
    exit 1
else
    exit 0
fi
