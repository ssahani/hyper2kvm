#!/bin/bash
# Build and push operator images for OpenShift/Kubernetes deployment
# Usage: ./scripts/build-operator-images.sh [VERSION] [REGISTRY]

set -e

# Default values
VERSION="${1:-2.1.0}"
REGISTRY="${2:-ghcr.io/ssahani}"
CONTAINER_TOOL="${CONTAINER_TOOL:-docker}"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

echo_success() {
    echo -e "${GREEN}✓${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check container tool
if ! command -v ${CONTAINER_TOOL} &> /dev/null; then
    echo_error "Container tool '${CONTAINER_TOOL}' not found"
    echo_info "Install Docker or Podman, or set CONTAINER_TOOL environment variable"
    exit 1
fi

echo_info "Using container tool: ${CONTAINER_TOOL}"
echo_info "Version: ${VERSION}"
echo_info "Registry: ${REGISTRY}"
echo ""

# Build operator image
echo_info "Building operator image..."
${CONTAINER_TOOL} build \
    --target operator \
    --platform linux/amd64,linux/arm64 \
    -t ${REGISTRY}/hyper2kvm:${VERSION}-operator \
    -t ${REGISTRY}/hyper2kvm:latest-operator \
    -f Dockerfile \
    .

if [ $? -eq 0 ]; then
    echo_success "Operator image built successfully"
else
    echo_error "Failed to build operator image"
    exit 1
fi

# Build worker image
echo_info "Building worker image..."
${CONTAINER_TOOL} build \
    --target worker \
    --platform linux/amd64,linux/arm64 \
    -t ${REGISTRY}/hyper2kvm:${VERSION}-worker \
    -t ${REGISTRY}/hyper2kvm:latest-worker \
    -f Dockerfile \
    .

if [ $? -eq 0 ]; then
    echo_success "Worker image built successfully"
else
    echo_error "Failed to build worker image"
    exit 1
fi

# Build CLI image
echo_info "Building CLI image..."
${CONTAINER_TOOL} build \
    --target cli \
    --platform linux/amd64,linux/arm64 \
    -t ${REGISTRY}/hyper2kvm:${VERSION}-cli \
    -t ${REGISTRY}/hyper2kvm:latest-cli \
    -f Dockerfile \
    .

if [ $? -eq 0 ]; then
    echo_success "CLI image built successfully"
else
    echo_error "Failed to build CLI image"
    exit 1
fi

# Build daemon image
echo_info "Building daemon image..."
${CONTAINER_TOOL} build \
    --target daemon \
    --platform linux/amd64,linux/arm64 \
    -t ${REGISTRY}/hyper2kvm:${VERSION}-daemon \
    -t ${REGISTRY}/hyper2kvm:latest-daemon \
    -f Dockerfile \
    .

if [ $? -eq 0 ]; then
    echo_success "Daemon image built successfully"
else
    echo_error "Failed to build daemon image"
    exit 1
fi

echo ""
echo_success "All images built successfully!"
echo ""
echo_info "Built images:"
echo "  - ${REGISTRY}/hyper2kvm:${VERSION}-operator"
echo "  - ${REGISTRY}/hyper2kvm:${VERSION}-worker"
echo "  - ${REGISTRY}/hyper2kvm:${VERSION}-cli"
echo "  - ${REGISTRY}/hyper2kvm:${VERSION}-daemon"
echo ""

# Ask to push
read -p "Push images to registry? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo_info "Pushing images to ${REGISTRY}..."

    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:${VERSION}-operator
    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:latest-operator

    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:${VERSION}-worker
    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:latest-worker

    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:${VERSION}-cli
    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:latest-cli

    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:${VERSION}-daemon
    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:latest-daemon

    echo_success "All images pushed successfully!"
else
    echo_warning "Images not pushed. Push manually with:"
    echo "  ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:${VERSION}-operator"
    echo "  ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm:${VERSION}-worker"
fi

echo ""
echo_info "Next steps:"
echo "  1. Build OLM bundle: ./scripts/build-olm-bundle.sh ${VERSION}"
echo "  2. Test on OpenShift: ./scripts/deploy-to-openshift.sh ${VERSION}"
