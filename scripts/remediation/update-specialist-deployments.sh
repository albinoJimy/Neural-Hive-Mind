#!/bin/bash

################################################################################
# Specialist Deployments Update Script
#
# Description: Update all 5 specialist deployments with new images and configurations
# Usage: ./scripts/remediation/update-specialist-deployments.sh [OPTIONS]
#
# Options:
#   --incremental       Update specialists one at a time (default, safer)
#   --parallel          Update all specialists simultaneously (faster but riskier)
#   --version VERSION   Specify version tag (default: v1.0.10)
#   --namespace NS      Specify namespace (default: neural-hive-specialists)
#   --dry-run           Show what would be updated without actually updating
#   --skip-validation   Skip pre-update validation checks
#
# Environment Variables:
#   REGISTRY            Docker registry to use (default: localhost:5000)
#                       Must match the registry used during image build
#
# Example:
#   ./scripts/remediation/update-specialist-deployments.sh --incremental --version v1.0.10
#   REGISTRY=ghcr.io/myorg ./scripts/remediation/update-specialist-deployments.sh
#
# Note: For production deployments, ensure cluster nodes can pull from the registry.
#       Configure imagePullSecrets in helm values if using private registries.
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VERSION="${VERSION:-v1.0.10}"
NAMESPACE="${NAMESPACE:-neural-hive-specialists}"
REGISTRY="${REGISTRY:-localhost:5000}"
UPDATE_MODE="incremental"
DRY_RUN=false
SKIP_VALIDATION=false
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="logs/deployment-update-${VERSION}-${TIMESTAMP}"
BACKUP_DIR="${LOG_DIR}/backups"

# List of specialists
SPECIALISTS=("specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --incremental)
            UPDATE_MODE="incremental"
            shift
            ;;
        --parallel)
            UPDATE_MODE="parallel"
            shift
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-validation)
            SKIP_VALIDATION=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--incremental|--parallel] [--version VERSION] [--namespace NS] [--dry-run] [--skip-validation]"
            exit 1
            ;;
    esac
done

# Create log and backup directories
mkdir -p "${LOG_DIR}"
mkdir -p "${BACKUP_DIR}"

echo -e "${BLUE}=== Neural Hive Mind - Specialist Deployments Update ===${NC}"
echo "Timestamp: ${TIMESTAMP}"
echo "Version: ${VERSION}"
echo "Namespace: ${NAMESPACE}"
echo "Registry: ${REGISTRY}"
echo "Update Mode: ${UPDATE_MODE}"
echo "Log Directory: ${LOG_DIR}"
echo ""

################################################################################
# Phase 1: Pre-Update Validation
################################################################################

if [ "${SKIP_VALIDATION}" = false ]; then
    echo -e "${BLUE}[Phase 1] Running pre-update validation...${NC}"

    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}❌ kubectl not found${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ kubectl available${NC}"

    # Check if namespace exists
    if ! kubectl get namespace "${NAMESPACE}" > /dev/null 2>&1; then
        echo -e "${RED}❌ Namespace ${NAMESPACE} does not exist${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Namespace ${NAMESPACE} exists${NC}"

    # Verify new images exist in registry
    echo "Verifying images in registry..."
    MISSING_IMAGES=()
    for specialist in "${SPECIALISTS[@]}"; do
        IMAGE="${REGISTRY}/${specialist}:${VERSION}"
        # Handle different registry types
        if [[ "${REGISTRY}" =~ ^localhost: ]]; then
            # Local registry - use HTTP
            if ! curl -s "http://${REGISTRY}/v2/${specialist}/tags/list" | grep -q "\"${VERSION}\""; then
                MISSING_IMAGES+=("${IMAGE}")
            fi
        else
            # External registry - check with docker
            if ! docker manifest inspect "${IMAGE}" > /dev/null 2>&1; then
                MISSING_IMAGES+=("${IMAGE}")
            fi
        fi
    done

    if [ ${#MISSING_IMAGES[@]} -gt 0 ]; then
        echo -e "${RED}❌ Missing images in registry:${NC}"
        for image in "${MISSING_IMAGES[@]}"; do
            echo "  - ${image}"
        done
        echo ""
        echo "Run: ./scripts/remediation/rebuild-specialist-images.sh --version ${VERSION}"
        exit 1
    fi
    echo -e "${GREEN}✅ All images available in registry${NC}"

    # Check helm is available
    if ! command -v helm &> /dev/null; then
        echo -e "${YELLOW}⚠️  helm not found (using kubectl only)${NC}"
    else
        echo -e "${GREEN}✅ helm available${NC}"
    fi

    # Check cluster resources
    echo "Checking cluster resource availability..."
    kubectl top nodes > "${LOG_DIR}/cluster-resources-pre.txt" 2>&1 || echo "Metrics not available" > "${LOG_DIR}/cluster-resources-pre.txt"

    echo ""
fi

################################################################################
# Phase 2: Backup Current State
################################################################################

echo -e "${BLUE}[Phase 2] Backing up current deployment state...${NC}"

for specialist in "${SPECIALISTS[@]}"; do
    echo "  Backing up ${specialist}..."
    kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o yaml > "${BACKUP_DIR}/${specialist}-deployment.yaml" 2>&1 || echo "Deployment not found" > "${BACKUP_DIR}/${specialist}-deployment.yaml"
    kubectl get replicaset -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" -o yaml > "${BACKUP_DIR}/${specialist}-replicaset.yaml" 2>&1 || echo "ReplicaSet not found" > "${BACKUP_DIR}/${specialist}-replicaset.yaml"
    kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --tail=100 > "${BACKUP_DIR}/${specialist}-logs.txt" 2>&1 || echo "No logs" > "${BACKUP_DIR}/${specialist}-logs.txt"
done

echo -e "${GREEN}✅ Backup complete: ${BACKUP_DIR}${NC}"
echo ""

if [ "${DRY_RUN}" = true ]; then
    echo -e "${YELLOW}[DRY RUN MODE] Would update the following deployments:${NC}"
    for specialist in "${SPECIALISTS[@]}"; do
        CURRENT_IMAGE=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "N/A")
        NEW_IMAGE="${REGISTRY}/${specialist}:${VERSION}"
        echo "  ${specialist}:"
        echo "    Current: ${CURRENT_IMAGE}"
        echo "    New:     ${NEW_IMAGE}"
    done
    echo ""
    echo "Update mode: ${UPDATE_MODE}"
    exit 0
fi

################################################################################
# Update Function
################################################################################

update_specialist() {
    local specialist=$1
    local start_time=$(date +%s)

    echo -e "${BLUE}Updating ${specialist}...${NC}"

    local new_image="${REGISTRY}/${specialist}:${VERSION}"

    # Update deployment image using helm upgrade
    echo "  Upgrading via helm to ${new_image}..."

    # Determine environment-specific values file
    local values_file="environments/dev/helm-values/${specialist}-values.yaml"
    if [ ! -f "${values_file}" ]; then
        values_file="helm-charts/${specialist}/values.yaml"
    fi

    if command -v helm &> /dev/null; then
        # Use helm upgrade with image overrides
        if helm upgrade "${specialist}" "helm-charts/${specialist}" \
            -n "${NAMESPACE}" \
            -f "${values_file}" \
            --set image.repository="${REGISTRY}/${specialist}" \
            --set image.tag="${VERSION}" \
            --wait \
            --timeout=5m >> "${LOG_DIR}/update-${specialist}.log" 2>&1; then

            echo -e "${GREEN}✅ Helm upgrade successful${NC}"

            # Wait for rollout to complete
            echo "  Waiting for rollout to complete..."
            sleep 5

            # Monitor rollout
            echo "  Monitoring rollout progress..."
            if kubectl rollout status deployment/"${specialist}" -n "${NAMESPACE}" --timeout=5m >> "${LOG_DIR}/update-${specialist}.log" 2>&1; then
                local end_time=$(date +%s)
                local update_time=$((end_time - start_time))

                echo -e "${GREEN}✅ Rollout successful (${update_time}s)${NC}"

                # Verify pod status
                local ready_pods=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
                local desired_pods=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")

                if [ "${ready_pods}" = "${desired_pods}" ]; then
                    echo -e "${GREEN}✅ All pods ready (${ready_pods}/${desired_pods})${NC}"
                else
                    echo -e "${YELLOW}⚠️  Pods not fully ready (${ready_pods}/${desired_pods})${NC}"
                    return 1
                fi

                # Check for errors in logs
                echo "  Checking logs for errors..."
                if kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" --tail=50 | grep -i "error\|exception\|failed" >> "${LOG_DIR}/update-${specialist}.log" 2>&1; then
                    echo -e "${YELLOW}⚠️  Errors found in logs (check ${LOG_DIR}/update-${specialist}.log)${NC}"
                else
                    echo -e "${GREEN}✅ No errors in logs${NC}"
                fi

                return 0
            else
                local end_time=$(date +%s)
                local update_time=$((end_time - start_time))

                echo -e "${RED}❌ Rollout failed (${update_time}s)${NC}"
                echo "  Check logs: ${LOG_DIR}/update-${specialist}.log"

                # Get pod status for troubleshooting
                kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" >> "${LOG_DIR}/update-${specialist}.log" 2>&1
                kubectl describe pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${specialist}" >> "${LOG_DIR}/update-${specialist}.log" 2>&1

                return 1
            fi
        else
            echo -e "${RED}❌ Helm upgrade failed${NC}"
            return 1
        fi
    else
        # Fallback to kubectl set image if helm is not available
        echo -e "${YELLOW}⚠️  helm not found, falling back to kubectl set image${NC}"
        echo "  Setting image to ${new_image}..."
        if kubectl set image deployment/"${specialist}" \
            "${specialist}=${new_image}" \
            -n "${NAMESPACE}" >> "${LOG_DIR}/update-${specialist}.log" 2>&1; then

            echo -e "${GREEN}✅ Image updated${NC}"

            # Wait and monitor rollout
            echo "  Waiting for rollout to start..."
            sleep 5
            echo "  Monitoring rollout progress..."

            if kubectl rollout status deployment/"${specialist}" -n "${NAMESPACE}" --timeout=5m >> "${LOG_DIR}/update-${specialist}.log" 2>&1; then
                local end_time=$(date +%s)
                local update_time=$((end_time - start_time))
                echo -e "${GREEN}✅ Rollout successful (${update_time}s)${NC}"
                return 0
            else
                echo -e "${RED}❌ Rollout failed${NC}"
                return 1
            fi
        else
            echo -e "${RED}❌ Failed to update image${NC}"
            return 1
        fi
    fi
}

################################################################################
# Phase 3: Execute Updates
################################################################################

echo -e "${BLUE}[Phase 3] Executing deployment updates (${UPDATE_MODE} mode)...${NC}"
echo ""

UPDATE_RESULTS=()
FAILED_UPDATES=()

if [ "${UPDATE_MODE}" = "incremental" ]; then
    # Incremental mode - update one at a time
    for specialist in "${SPECIALISTS[@]}"; do
        if update_specialist "${specialist}"; then
            UPDATE_RESULTS+=("${specialist}:success")
        else
            UPDATE_RESULTS+=("${specialist}:failed")
            FAILED_UPDATES+=("${specialist}")

            echo -e "${RED}❌ Update failed for ${specialist}${NC}"
            echo ""
            read -p "Continue with remaining specialists? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Stopping updates. Remaining specialists not updated."
                break
            fi
        fi
        echo ""
    done

elif [ "${UPDATE_MODE}" = "parallel" ]; then
    # Parallel mode - update all simultaneously
    PIDS=()

    for specialist in "${SPECIALISTS[@]}"; do
        (
            if update_specialist "${specialist}"; then
                echo "SUCCESS:${specialist}" > "${LOG_DIR}/result-${specialist}.txt"
                exit 0
            else
                echo "FAILED:${specialist}" > "${LOG_DIR}/result-${specialist}.txt"
                exit 1
            fi
        ) &
        PIDS+=($!)
    done

    # Wait for all updates to complete
    echo "Waiting for all updates to complete..."
    for pid in "${PIDS[@]}"; do
        wait "${pid}" || true
    done

    # Collect results
    for specialist in "${SPECIALISTS[@]}"; do
        if [ -f "${LOG_DIR}/result-${specialist}.txt" ]; then
            result=$(cat "${LOG_DIR}/result-${specialist}.txt")
            if [[ "${result}" == SUCCESS:* ]]; then
                UPDATE_RESULTS+=("${specialist}:success")
            else
                UPDATE_RESULTS+=("${specialist}:failed")
                FAILED_UPDATES+=("${specialist}")
            fi
        else
            UPDATE_RESULTS+=("${specialist}:unknown")
            FAILED_UPDATES+=("${specialist}")
        fi
    done
fi

echo ""

################################################################################
# Phase 4: Post-Update Validation
################################################################################

echo -e "${BLUE}[Phase 4] Running post-update validation...${NC}"

echo "Collecting updated deployment status..."
kubectl get deployments -n "${NAMESPACE}" -o wide > "${LOG_DIR}/deployments-post.txt" 2>&1
kubectl get pods -n "${NAMESPACE}" -o wide > "${LOG_DIR}/pods-post.txt" 2>&1
kubectl top pods -n "${NAMESPACE}" > "${LOG_DIR}/pods-resources-post.txt" 2>&1 || echo "Metrics not available" > "${LOG_DIR}/pods-resources-post.txt"

echo "Verifying image versions..."
{
    echo "=== Updated Image Versions ==="
    for specialist in "${SPECIALISTS[@]}"; do
        IMAGE=$(kubectl get deployment "${specialist}" -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "N/A")
        echo "${specialist}: ${IMAGE}"
    done
} | tee "${LOG_DIR}/image-versions-post.txt"

echo ""

################################################################################
# Generate Update Report
################################################################################

{
    echo "# Deployment Update Report"
    echo "Generated: ${TIMESTAMP}"
    echo "Version: ${VERSION}"
    echo "Namespace: ${NAMESPACE}"
    echo "Update Mode: ${UPDATE_MODE}"
    echo ""

    echo "## Update Results"
    echo ""
    for result in "${UPDATE_RESULTS[@]}"; do
        specialist=$(echo "${result}" | cut -d: -f1)
        status=$(echo "${result}" | cut -d: -f2)
        if [ "${status}" = "success" ]; then
            echo "- ✅ ${specialist}: SUCCESS"
        else
            echo "- ❌ ${specialist}: FAILED"
        fi
    done
    echo ""

    if [ ${#FAILED_UPDATES[@]} -gt 0 ]; then
        echo "## Failed Updates"
        echo ""
        for specialist in "${FAILED_UPDATES[@]}"; do
            echo "- ${specialist}"
            echo "  - Log: ${LOG_DIR}/update-${specialist}.log"
            echo "  - Rollback: kubectl rollout undo deployment/${specialist} -n ${NAMESPACE}"
        done
        echo ""
    fi

    echo "## Current Deployment Status"
    echo ""
    echo "\`\`\`"
    kubectl get deployments -n "${NAMESPACE}" -o wide 2>/dev/null || echo "N/A"
    echo "\`\`\`"
    echo ""

    echo "## Pod Status"
    echo ""
    echo "\`\`\`"
    kubectl get pods -n "${NAMESPACE}" -o wide 2>/dev/null || echo "N/A"
    echo "\`\`\`"
    echo ""

    echo "## Backups"
    echo ""
    echo "Pre-update backups saved to: \`${BACKUP_DIR}\`"
    echo ""

} > "${LOG_DIR}/UPDATE_REPORT.md"

################################################################################
# Summary
################################################################################

echo -e "${BLUE}=== Update Summary ===${NC}"
echo ""

SUCCESS_COUNT=$((${#SPECIALISTS[@]} - ${#FAILED_UPDATES[@]}))
echo "Total Specialists: ${#SPECIALISTS[@]}"
echo "Successful: ${SUCCESS_COUNT}"
echo "Failed: ${#FAILED_UPDATES[@]}"
echo ""

if [ ${#FAILED_UPDATES[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ All deployments updated successfully!${NC}"
    echo ""
    echo "Next Steps:"
    echo "1. Validate health: ./scripts/validation/validate-specialist-health.sh"
    echo "2. Monitor for 10 minutes to ensure stability"
    echo "3. Test end-to-end flow"
    echo ""
    echo "Update report: ${LOG_DIR}/UPDATE_REPORT.md"
    exit 0
else
    echo -e "${RED}❌ Some deployments failed to update${NC}"
    echo ""
    echo "Failed specialists: ${FAILED_UPDATES[*]}"
    echo ""
    echo "Rollback Commands:"
    for specialist in "${FAILED_UPDATES[@]}"; do
        echo "  kubectl rollout undo deployment/${specialist} -n ${NAMESPACE}"
    done
    echo ""
    echo "Or restore from backup:"
    echo "  kubectl apply -f ${BACKUP_DIR}/<specialist>-deployment.yaml"
    echo ""
    echo "Update report: ${LOG_DIR}/UPDATE_REPORT.md"
    exit 1
fi
