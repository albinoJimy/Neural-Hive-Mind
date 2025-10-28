#!/bin/bash

# Build Docker images for all specialists in Minikube
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_TAG="${IMAGE_TAG:-local}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Building Specialist Images${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if skip build
if [ "$SKIP_BUILD" = "true" ]; then
  echo -e "${YELLOW}SKIP_BUILD=true, skipping image builds${NC}"
  exit 0
fi

# Configure Docker to use Minikube's daemon
echo -e "${YELLOW}Configuring Docker to use Minikube daemon...${NC}"
eval $(minikube docker-env)
if [ $? -ne 0 ]; then
  echo -e "${RED}Failed to configure Minikube Docker environment${NC}"
  echo -e "${RED}Make sure Minikube is running: minikube status${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Docker configured for Minikube${NC}"
echo ""

# Navigate to project root (script is in scripts/deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${YELLOW}Project root: $PROJECT_ROOT${NC}"
echo -e "${YELLOW}Image tag: $IMAGE_TAG${NC}"
echo ""

# Build counter
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_SPECIALISTS=()

# Build each specialist image
for specialist in "${SPECIALISTS[@]}"; do
  IMAGE_NAME="neural-hive/specialist-${specialist}:${IMAGE_TAG}"
  DOCKERFILE_PATH="services/specialist-${specialist}/Dockerfile"

  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}Building: specialist-${specialist}${NC}"
  echo -e "${GREEN}========================================${NC}"

  # Check if Dockerfile exists
  if [ ! -f "$DOCKERFILE_PATH" ]; then
    echo -e "${RED}✗ Dockerfile not found: $DOCKERFILE_PATH${NC}"
    FAILED_COUNT=$((FAILED_COUNT + 1))
    FAILED_SPECIALISTS+=("$specialist (Dockerfile missing)")
    echo ""
    continue
  fi

  # Start timer
  START_TIME=$(date +%s)

  # Build image (context is project root to include libraries/)
  echo -e "${YELLOW}Building image: $IMAGE_NAME${NC}"
  echo -e "${YELLOW}Dockerfile: $DOCKERFILE_PATH${NC}"
  echo -e "${YELLOW}Context: $PROJECT_ROOT${NC}"
  echo ""

  if docker build -t "$IMAGE_NAME" -f "$DOCKERFILE_PATH" .; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    echo ""
    echo -e "${GREEN}✓ Successfully built $IMAGE_NAME (${DURATION}s)${NC}"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    echo ""
    echo -e "${RED}✗ Failed to build $IMAGE_NAME (${DURATION}s)${NC}"
    FAILED_COUNT=$((FAILED_COUNT + 1))
    FAILED_SPECIALISTS+=("$specialist (build failed)")
  fi

  echo ""
done

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Successful builds: ${GREEN}$SUCCESS_COUNT${NC}/5"
echo -e "Failed builds: ${RED}$FAILED_COUNT${NC}/5"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
  echo -e "${RED}Failed specialists:${NC}"
  for failed in "${FAILED_SPECIALISTS[@]}"; do
    echo -e "${RED}  - $failed${NC}"
  done
  echo ""
fi

# List created images
echo -e "${YELLOW}Specialist images in Minikube:${NC}"
docker images | grep -E "REPOSITORY|specialist" | grep -E "REPOSITORY|neural-hive"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
  echo -e "${RED}Build completed with errors${NC}"
  exit 1
else
  echo -e "${GREEN}All specialist images built successfully!${NC}"
  exit 0
fi
