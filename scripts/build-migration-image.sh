#!/bin/bash
# Build hyper2kvm migration container image
# This image is used by MigrationJob to run migrations inside Kubernetes

set -e

# Configuration
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/hyper2kvm/migration}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="hyper2kvm/daemon/Dockerfile.migration"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🐳 Building hyper2kvm Migration Container${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Image: ${GREEN}${IMAGE_NAME}:${IMAGE_TAG}${NC}"
echo -e "  Platforms: ${GREEN}${PLATFORMS}${NC}"
echo ""

# Check if buildx is available
if ! docker buildx version &>/dev/null; then
    echo -e "${YELLOW}⚠️  Docker buildx not found, using regular build${NC}"
    BUILD_CMD="docker build"
    PLATFORM_ARG=""
else
    echo -e "${GREEN}✅ Using docker buildx for multi-platform build${NC}"
    BUILD_CMD="docker buildx build --push"
    PLATFORM_ARG="--platform ${PLATFORMS}"
fi

# Build image
echo ""
echo -e "${BLUE}Building...${NC}"
$BUILD_CMD \
    -f "${DOCKERFILE}" \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    $PLATFORM_ARG \
    .

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✅ Build successful!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  Image: ${GREEN}${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    echo ""
    echo -e "Usage in MigrationJob:"
    echo ""
    echo -e "  Update ${YELLOW}hyper2kvm/operator/migrationjob_controller.py${NC}:"
    echo -e "  ${YELLOW}MIGRATION_IMAGE = \"${IMAGE_NAME}:${IMAGE_TAG}\"${NC}"
    echo ""
else
    echo ""
    echo -e "${YELLOW}❌ Build failed${NC}"
    exit 1
fi
