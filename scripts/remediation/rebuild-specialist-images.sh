#!/bin/bash

################################################################################
# Specialist Images Rebuild Script
#
# Description: Rebuild all 5 specialist Docker images with updated dependencies
# Usage: ./scripts/remediation/rebuild-specialist-images.sh [OPTIONS]
#
# Options:
#   --parallel          Build all specialists in parallel (faster but riskier)
#   --sequential        Build specialists one at a time (default, safer)
#   --version VERSION   Specify version tag (default: v1.0.10)
#   --dry-run           Show what would be built without building
#   --no-push           Build images but don't push to registry
#   --cleanup           Remove old images after successful build
#
# Environment Variables:
#   REGISTRY            Docker registry to use (default: localhost:5000)
#                       Examples: localhost:5000, ghcr.io/myorg, docker.io/myorg
#
# Example:
#   ./scripts/remediation/rebuild-specialist-images.sh --parallel --version v1.0.10
#   REGISTRY=ghcr.io/myorg ./scripts/remediation/rebuild-specialist-images.sh
#
# Note: For production deployments, use an external registry (GHCR, ECR, GCR)
#       and ensure cluster nodes can access it. Configure imagePullSecrets if needed.
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
REGISTRY="${REGISTRY:-localhost:5000}"
BUILD_MODE="sequential"
DRY_RUN=false
NO_PUSH=false
CLEANUP=false

# Determine BUILD_CONTEXT dynamically
if command -v git &> /dev/null && git rev-parse --show-toplevel &> /dev/null; then
    BUILD_CONTEXT="$(git rev-parse --show-toplevel)"
else
    # Fallback: calculate from script location
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    BUILD_CONTEXT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="${BUILD_CONTEXT}/logs/build-${VERSION}-${TIMESTAMP}"

# List of specialists
SPECIALISTS=("specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel)
            BUILD_MODE="parallel"
            shift
            ;;
        --sequential)
            BUILD_MODE="sequential"
            shift
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-push)
            NO_PUSH=true
            shift
            ;;
        --cleanup)
            CLEANUP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--parallel|--sequential] [--version VERSION] [--dry-run] [--no-push] [--cleanup]"
            exit 1
            ;;
    esac
done

# Create log directory
mkdir -p "${LOG_DIR}"

echo -e "${BLUE}=== Neural Hive Mind - Specialist Image Rebuild ===${NC}"
echo "Timestamp: ${TIMESTAMP}"
echo "Version: ${VERSION}"
echo "Registry: ${REGISTRY}"
echo "Build Mode: ${BUILD_MODE}"
echo "Build Context: ${BUILD_CONTEXT}"
echo "Log Directory: ${LOG_DIR}"
echo ""
echo "NOTE: This script expects to be run from within the Neural Hive Mind repository."
echo ""

################################################################################
# Pre-flight Checks
################################################################################

echo -e "${BLUE}[Pre-flight] Running pre-flight checks...${NC}"

# Verify we're in a valid repository
echo "Verifying build context..."
if [ ! -d "${BUILD_CONTEXT}/services" ]; then
    echo -e "${RED}❌ Invalid build context: ${BUILD_CONTEXT}${NC}"
    echo "  Expected services/ directory not found."
    echo "  Ensure script is run from within the Neural Hive Mind repository."
    exit 1
fi
echo -e "${GREEN}✅ Build context valid: ${BUILD_CONTEXT}${NC}"

# Check if Docker daemon is running
echo "Checking Docker daemon..."
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker daemon is running${NC}"

# Check available disk space (need at least 10GB)
echo "Checking available disk space..."
AVAILABLE_SPACE=$(df -BG "${BUILD_CONTEXT}" | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "${AVAILABLE_SPACE}" -lt 10 ]; then
    echo -e "${YELLOW}⚠️  Low disk space: ${AVAILABLE_SPACE}GB available (10GB recommended)${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✅ Sufficient disk space: ${AVAILABLE_SPACE}GB available${NC}"
fi

# Check if registry is accessible
echo "Checking registry accessibility..."
# Handle different registry types (localhost vs external)
if [[ "${REGISTRY}" =~ ^localhost: ]]; then
    # Local registry - use HTTP
    if ! curl -s "http://${REGISTRY}/v2/" > /dev/null; then
        echo -e "${RED}❌ Registry ${REGISTRY} is not accessible${NC}"
        echo "  Ensure local registry is running: docker run -d -p 5000:5000 --name registry registry:2"
        exit 1
    fi
    echo -e "${GREEN}✅ Registry ${REGISTRY} is accessible${NC}"
else
    # External registry - use HTTPS
    if ! curl -s "https://${REGISTRY}/v2/" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Registry ${REGISTRY} accessibility check failed (may require auth)${NC}"
        echo "  Ensure you are logged in: docker login ${REGISTRY}"
    else
        echo -e "${GREEN}✅ Registry ${REGISTRY} is accessible${NC}"
    fi
fi

# Verify requirements.txt files contain structlog
echo "Verifying structlog dependency in requirements.txt files..."
MISSING_STRUCTLOG=()
for specialist in "${SPECIALISTS[@]}"; do
    REQ_FILE="${BUILD_CONTEXT}/services/${specialist}/requirements.txt"
    if [ ! -f "${REQ_FILE}" ]; then
        echo -e "${RED}❌ Missing requirements.txt: ${REQ_FILE}${NC}"
        exit 1
    fi
    if ! grep -q "structlog" "${REQ_FILE}"; then
        MISSING_STRUCTLOG+=("${specialist}")
    fi
done

if [ ${#MISSING_STRUCTLOG[@]} -gt 0 ]; then
    echo -e "${RED}❌ structlog missing in requirements.txt for: ${MISSING_STRUCTLOG[*]}${NC}"
    exit 1
fi
echo -e "${GREEN}✅ All requirements.txt files contain structlog${NC}"

echo ""

if [ "${DRY_RUN}" = true ]; then
    echo -e "${YELLOW}[DRY RUN MODE] Would build the following images:${NC}"
    for specialist in "${SPECIALISTS[@]}"; do
        echo "  - ${REGISTRY}/${specialist}:${VERSION}"
        echo "  - ${REGISTRY}/${specialist}:latest"
    done
    echo ""
    echo "Build mode: ${BUILD_MODE}"
    echo "Push to registry: $([ "${NO_PUSH}" = false ] && echo "yes" || echo "no")"
    echo "Cleanup old images: $([ "${CLEANUP}" = true ] && echo "yes" || echo "no")"
    exit 0
fi

################################################################################
# Build Function
################################################################################

build_specialist() {
    local specialist=$1
    local start_time=$(date +%s)

    echo -e "${BLUE}Building ${specialist}...${NC}"

    local dockerfile="${BUILD_CONTEXT}/services/${specialist}/Dockerfile"
    local image_name="${REGISTRY}/${specialist}"
    local image_version="${image_name}:${VERSION}"
    local image_latest="${image_name}:latest"

    # Check if Dockerfile exists
    if [ ! -f "${dockerfile}" ]; then
        echo -e "${RED}❌ Dockerfile not found: ${dockerfile}${NC}"
        return 1
    fi

    # Build image with BuildKit
    echo "  Building ${image_version}..."
    if DOCKER_BUILDKIT=1 docker build \
        -f "${dockerfile}" \
        -t "${image_version}" \
        -t "${image_latest}" \
        --label "version=${VERSION}" \
        --label "specialist=${specialist}" \
        --label "build.timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "${BUILD_CONTEXT}" > "${LOG_DIR}/build-${specialist}.log" 2>&1; then

        local end_time=$(date +%s)
        local build_time=$((end_time - start_time))
        local image_size=$(docker images "${image_version}" --format "{{.Size}}")

        echo -e "${GREEN}✅ Build successful: ${specialist} (${build_time}s, ${image_size})${NC}"

        # Push to registry
        if [ "${NO_PUSH}" = false ]; then
            echo "  Pushing ${image_version}..."
            if docker push "${image_version}" >> "${LOG_DIR}/build-${specialist}.log" 2>&1; then
                echo -e "${GREEN}✅ Push successful: ${image_version}${NC}"
            else
                echo -e "${RED}❌ Push failed: ${image_version}${NC}"
                return 1
            fi

            echo "  Pushing ${image_latest}..."
            if docker push "${image_latest}" >> "${LOG_DIR}/build-${specialist}.log" 2>&1; then
                echo -e "${GREEN}✅ Push successful: ${image_latest}${NC}"
            else
                echo -e "${RED}❌ Push failed: ${image_latest}${NC}"
                return 1
            fi
        fi

        # Verify structlog is installed
        echo "  Verifying structlog installation..."
        if docker run --rm "${image_version}" python -c "import structlog" >> "${LOG_DIR}/build-${specialist}.log" 2>&1; then
            echo -e "${GREEN}✅ structlog verified in ${specialist}${NC}"
        else
            echo -e "${RED}❌ structlog not found in ${specialist}${NC}"
            return 1
        fi

        return 0
    else
        local end_time=$(date +%s)
        local build_time=$((end_time - start_time))
        echo -e "${RED}❌ Build failed: ${specialist} (${build_time}s)${NC}"
        echo "  Check logs: ${LOG_DIR}/build-${specialist}.log"
        return 1
    fi
}

################################################################################
# Sequential Build Mode
################################################################################

if [ "${BUILD_MODE}" = "sequential" ]; then
    echo -e "${BLUE}[Build] Starting sequential build...${NC}"
    echo ""

    BUILD_RESULTS=()
    FAILED_BUILDS=()

    for specialist in "${SPECIALISTS[@]}"; do
        if build_specialist "${specialist}"; then
            BUILD_RESULTS+=("${specialist}:success")
        else
            BUILD_RESULTS+=("${specialist}:failed")
            FAILED_BUILDS+=("${specialist}")
            echo -e "${RED}❌ Stopping build due to failure in ${specialist}${NC}"
            break
        fi
        echo ""
    done

################################################################################
# Parallel Build Mode
################################################################################

elif [ "${BUILD_MODE}" = "parallel" ]; then
    echo -e "${BLUE}[Build] Starting parallel build...${NC}"
    echo ""

    BUILD_RESULTS=()
    FAILED_BUILDS=()
    PIDS=()

    # Start all builds in background
    for specialist in "${SPECIALISTS[@]}"; do
        (
            if build_specialist "${specialist}"; then
                echo "SUCCESS:${specialist}" > "${LOG_DIR}/result-${specialist}.txt"
                exit 0
            else
                echo "FAILED:${specialist}" > "${LOG_DIR}/result-${specialist}.txt"
                exit 1
            fi
        ) &
        PIDS+=($!)
    done

    # Wait for all builds to complete
    echo "Waiting for all builds to complete..."
    for pid in "${PIDS[@]}"; do
        wait "${pid}" || true
    done

    # Collect results
    for specialist in "${SPECIALISTS[@]}"; do
        if [ -f "${LOG_DIR}/result-${specialist}.txt" ]; then
            result=$(cat "${LOG_DIR}/result-${specialist}.txt")
            if [[ "${result}" == SUCCESS:* ]]; then
                BUILD_RESULTS+=("${specialist}:success")
            else
                BUILD_RESULTS+=("${specialist}:failed")
                FAILED_BUILDS+=("${specialist}")
            fi
        else
            BUILD_RESULTS+=("${specialist}:unknown")
            FAILED_BUILDS+=("${specialist}")
        fi
    done

    echo ""
fi

################################################################################
# Post-Build Validation
################################################################################

echo -e "${BLUE}[Validation] Running post-build validation...${NC}"

echo "Listing newly built images..."
{
    echo "=== Built Images ==="
    for specialist in "${SPECIALISTS[@]}"; do
        echo "--- ${specialist} ---"
        docker images "${REGISTRY}/${specialist}" --filter "label=version=${VERSION}" 2>/dev/null
        if [ $? -ne 0 ] || [ $(docker images "${REGISTRY}/${specialist}" --filter "label=version=${VERSION}" 2>/dev/null | wc -l) -le 1 ]; then
            # Fallback if filter doesn't work or no results
            docker images "${REGISTRY}/${specialist}" 2>/dev/null | head -2
        fi
    done
} | tee "${LOG_DIR}/built-images.txt"

echo ""

################################################################################
# Cleanup
################################################################################

if [ "${CLEANUP}" = true ] && [ ${#FAILED_BUILDS[@]} -eq 0 ]; then
    echo -e "${BLUE}[Cleanup] Removing old images...${NC}"

    # Remove dangling images
    echo "Removing dangling images..."
    docker image prune -f > /dev/null 2>&1 || true

    # Remove old versions (keep current version and latest)
    for specialist in "${SPECIALISTS[@]}"; do
        echo "Cleaning up old versions of ${specialist}..."
        docker images "${REGISTRY}/${specialist}" --format "{{.Tag}}" | grep -v "^${VERSION}$" | grep -v "^latest$" | xargs -r -I {} docker rmi "${REGISTRY}/${specialist}:{}" > /dev/null 2>&1 || true
    done

    echo -e "${GREEN}✅ Cleanup complete${NC}"
    echo ""
fi

################################################################################
# Generate Build Report
################################################################################

{
    echo "# Build Report"
    echo "Generated: ${TIMESTAMP}"
    echo "Version: ${VERSION}"
    echo "Build Mode: ${BUILD_MODE}"
    echo ""

    echo "## Build Results"
    echo ""
    for result in "${BUILD_RESULTS[@]}"; do
        specialist=$(echo "${result}" | cut -d: -f1)
        status=$(echo "${result}" | cut -d: -f2)
        if [ "${status}" = "success" ]; then
            echo "- ✅ ${specialist}: SUCCESS"
        else
            echo "- ❌ ${specialist}: FAILED"
        fi
    done
    echo ""

    if [ ${#FAILED_BUILDS[@]} -gt 0 ]; then
        echo "## Failed Builds"
        echo ""
        for specialist in "${FAILED_BUILDS[@]}"; do
            echo "- ${specialist}"
            echo "  - Log: ${LOG_DIR}/build-${specialist}.log"
        done
        echo ""
    fi

    echo "## Image Details"
    echo ""
    echo "\`\`\`"
    docker images "${REGISTRY}/specialist-*" | head -20
    echo "\`\`\`"
    echo ""

    echo "## Registry Verification"
    echo ""
    for specialist in "${SPECIALISTS[@]}"; do
        echo "### ${specialist}"
        echo "\`\`\`"
        curl -s "http://${REGISTRY}/v2/${specialist}/tags/list" 2>/dev/null | jq '.' || echo "Not available"
        echo "\`\`\`"
    done

} > "${LOG_DIR}/BUILD_REPORT.md"

################################################################################
# Summary
################################################################################

echo -e "${BLUE}=== Build Summary ===${NC}"
echo ""

SUCCESS_COUNT=$((${#SPECIALISTS[@]} - ${#FAILED_BUILDS[@]}))
echo "Total Specialists: ${#SPECIALISTS[@]}"
echo "Successful: ${SUCCESS_COUNT}"
echo "Failed: ${#FAILED_BUILDS[@]}"
echo ""

if [ ${#FAILED_BUILDS[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ All images built and pushed successfully!${NC}"
    echo ""
    echo "Next Steps:"
    echo "1. Update deployments: ./scripts/remediation/update-specialist-deployments.sh"
    echo "2. Validate health: ./scripts/validation/validate-specialist-health.sh"
    echo ""
    echo "Build report: ${LOG_DIR}/BUILD_REPORT.md"
    exit 0
else
    echo -e "${RED}❌ Some builds failed${NC}"
    echo ""
    echo "Failed specialists: ${FAILED_BUILDS[*]}"
    echo ""
    echo "Troubleshooting:"
    echo "- Check build logs in: ${LOG_DIR}/"
    echo "- Review Dockerfiles in: services/specialist-*/Dockerfile"
    echo "- Verify dependencies in: services/specialist-*/requirements.txt"
    echo ""
    echo "Build report: ${LOG_DIR}/BUILD_REPORT.md"
    exit 1
fi
