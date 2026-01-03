#!/bin/bash
# validate-image-tags.sh
# Validate that all Docker images use semantic version tags (no :latest)
# and optionally verify that image tags exist in registries
#
# Usage:
#   ./scripts/validate-image-tags.sh           # Check YAML files only
#   ./scripts/validate-image-tags.sh --cluster # Also check running pods
#   ./scripts/validate-image-tags.sh --registry # Verify images exist in registries

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CHECK_CLUSTER=false
CHECK_REGISTRY=false
ERRORS_FOUND=0

# Expected images list - update this when introducing new versions
# Format: REGISTRY_TYPE|REPOSITORY|TAG
# REGISTRY_TYPE: dockerhub, ecr, internal
EXPECTED_IMAGES=(
    "dockerhub|curlimages/curl|8.5.0"
    "ecr|neural-hive-mind/pipelines|1.0.7"
    "ecr|neural-hive-ml-training|1.0.7"
    "ecr|neural-hive-ml-monitoring|1.0.7"
)

usage() {
    echo "Usage: $0 [--cluster] [--registry]"
    echo ""
    echo "Options:"
    echo "  --cluster    Also check running pods in the cluster"
    echo "  --registry   Verify that expected images exist in their registries"
    echo "  -h, --help   Show this help message"
    echo ""
    echo "Registry validation supports:"
    echo "  - Docker Hub (using docker manifest inspect)"
    echo "  - AWS ECR (using aws ecr describe-images)"
    echo "  - Internal registry (using curl to registry API)"
    echo ""
    echo "To add new images to validate, edit the EXPECTED_IMAGES array in this script."
    echo "See docs/IMAGE_VERSIONING.md for more details."
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --cluster)
            CHECK_CLUSTER=true
            shift
            ;;
        --registry)
            CHECK_REGISTRY=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

echo "========================================"
echo "Image Tag Validation"
echo "========================================"
echo ""

echo -e "${YELLOW}Checking YAML files for :latest tags...${NC}"
echo ""

SEARCH_DIRS=(
    "$PROJECT_ROOT/k8s"
    "$PROJECT_ROOT/helm-charts"
    "$PROJECT_ROOT/ml_pipelines/k8s"
)

for dir in "${SEARCH_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        FOUND=$(grep -rn "image:.*:latest" "$dir" --include="*.yaml" --include="*.yml" 2>/dev/null || true)
        if [[ -n "$FOUND" ]]; then
            echo -e "${RED}Found :latest tags in $dir:${NC}"
            echo "$FOUND"
            echo ""
            ERRORS_FOUND=$((ERRORS_FOUND + 1))
        fi
    fi
done

if [[ -f "$PROJECT_ROOT/orchestrator-dynamic-deploy.yaml" ]]; then
    FOUND=$(grep -n "image:.*:latest" "$PROJECT_ROOT/orchestrator-dynamic-deploy.yaml" 2>/dev/null || true)
    if [[ -n "$FOUND" ]]; then
        echo -e "${RED}Found :latest tags in orchestrator-dynamic-deploy.yaml:${NC}"
        echo "$FOUND"
        echo ""
        ERRORS_FOUND=$((ERRORS_FOUND + 1))
    fi
fi

if [[ $ERRORS_FOUND -eq 0 ]]; then
    echo -e "${GREEN}No :latest tags found in YAML files${NC}"
fi

if [[ "$CHECK_CLUSTER" == "true" ]]; then
    echo ""
    echo -e "${YELLOW}Checking running pods in cluster...${NC}"
    echo ""

    if ! command -v kubectl &> /dev/null; then
        echo -e "${YELLOW}kubectl not found, skipping cluster check${NC}"
    else
        PODS_WITH_LATEST=$(kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}' 2>/dev/null | grep ":latest" || true)

        if [[ -n "$PODS_WITH_LATEST" ]]; then
            echo -e "${RED}Found pods using :latest tag:${NC}"
            echo "NAMESPACE	POD	IMAGE"
            echo "$PODS_WITH_LATEST"
            echo ""
            ERRORS_FOUND=$((ERRORS_FOUND + 1))
        else
            echo -e "${GREEN}No pods using :latest tag found in cluster${NC}"
        fi
    fi
fi

if [[ "$CHECK_REGISTRY" == "true" ]]; then
    echo ""
    echo -e "${YELLOW}Validating image existence in registries...${NC}"
    echo ""

    validate_dockerhub_image() {
        local repo="$1"
        local tag="$2"
        echo -n "  Docker Hub: ${repo}:${tag} ... "
        if docker manifest inspect "docker.io/${repo}:${tag}" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ exists${NC}"
            return 0
        else
            echo -e "${RED}✗ NOT found${NC}"
            return 1
        fi
    }

    validate_ecr_image() {
        local repo="$1"
        local tag="$2"
        echo -n "  ECR: ${repo}:${tag} ... "

        if ! command -v aws &> /dev/null; then
            echo -e "${YELLOW}⚠ aws CLI not found, skipping${NC}"
            return 0
        fi

        if aws ecr describe-images \
            --repository-name "${repo}" \
            --region us-east-1 \
            --image-ids imageTag="${tag}" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ exists${NC}"
            return 0
        else
            echo -e "${RED}✗ NOT found${NC}"
            return 1
        fi
    }

    validate_internal_image() {
        local repo="$1"
        local tag="$2"
        local registry_url="37.60.241.150:30500"
        echo -n "  Internal: ${repo}:${tag} ... "

        if ! command -v curl &> /dev/null; then
            echo -e "${YELLOW}⚠ curl not found, skipping${NC}"
            return 0
        fi

        # Check if tag exists in internal registry
        TAGS_RESPONSE=$(curl -s "http://${registry_url}/v2/${repo}/tags/list" 2>/dev/null || echo '{}')
        if echo "$TAGS_RESPONSE" | grep -q "\"${tag}\""; then
            echo -e "${GREEN}✓ exists${NC}"
            return 0
        else
            echo -e "${RED}✗ NOT found${NC}"
            return 1
        fi
    }

    REGISTRY_ERRORS=0

    for image_entry in "${EXPECTED_IMAGES[@]}"; do
        IFS='|' read -r registry_type repo tag <<< "$image_entry"

        case "$registry_type" in
            dockerhub)
                if ! validate_dockerhub_image "$repo" "$tag"; then
                    REGISTRY_ERRORS=$((REGISTRY_ERRORS + 1))
                fi
                ;;
            ecr)
                if ! validate_ecr_image "$repo" "$tag"; then
                    REGISTRY_ERRORS=$((REGISTRY_ERRORS + 1))
                fi
                ;;
            internal)
                if ! validate_internal_image "$repo" "$tag"; then
                    REGISTRY_ERRORS=$((REGISTRY_ERRORS + 1))
                fi
                ;;
            *)
                echo -e "${YELLOW}  Unknown registry type: $registry_type${NC}"
                ;;
        esac
    done

    echo ""
    if [[ $REGISTRY_ERRORS -gt 0 ]]; then
        echo -e "${RED}Registry validation: $REGISTRY_ERRORS image(s) not found${NC}"
        ERRORS_FOUND=$((ERRORS_FOUND + REGISTRY_ERRORS))
    else
        echo -e "${GREEN}Registry validation: All expected images exist${NC}"
    fi
fi

echo ""
echo "========================================"
if [[ $ERRORS_FOUND -gt 0 ]]; then
    echo -e "${RED}Validation FAILED: Found $ERRORS_FOUND issue(s)${NC}"
    exit 1
else
    echo -e "${GREEN}Validation PASSED: All checks completed successfully${NC}"
    exit 0
fi
