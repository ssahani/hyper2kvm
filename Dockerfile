# Multi-stage Dockerfile for hyper2kvm
# Supports both development and production builds

# Stage 1: Base image with system dependencies
FROM fedora:43 AS base

LABEL maintainer="Susant Sahani <ssahani@gmail.com>"
LABEL description="hyper2kvm - Hypervisor to KVM/QEMU Migration Toolkit"
LABEL org.opencontainers.image.source="https://github.com/ssahani/hyper2kvm"
LABEL org.opencontainers.image.licenses="LGPL-3.0-or-later"

# Install system dependencies
RUN dnf update -y && \
    dnf install -y \
        python3 \
        python3-pip \
        python3-devel \
        qemu-img \
        qemu-system-x86 \
        libvirt-daemon \
        libvirt-client \
        openssh-clients \
        git \
        make \
    && dnf clean all

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Stage 2: Development image
FROM base AS development

# Install development tools
RUN pip install --no-cache-dir \
    hatch \
    pre-commit \
    ipython

# Copy project files
COPY . /app/

# Install hyper2kvm in development mode
RUN pip install -e .[dev,full]

# Install pre-commit hooks
RUN git init . && pre-commit install-hooks || true

# Default command for development
CMD ["/bin/bash"]

# Stage 3: Builder for production
FROM base AS builder

# Copy only necessary files for building
COPY pyproject.toml setup.py README.md LICENSE ./
COPY requirements.txt requirements-dev.txt ./
COPY hyper2kvm/ ./hyper2kvm/

# Install build dependencies and build wheel
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Stage 4: Production image
FROM base AS production

# Copy only the built wheel from builder
COPY --from=builder /app/dist/*.whl /tmp/

# Install the wheel with full dependencies
RUN pip install --no-cache-dir /tmp/*.whl[full] && \
    rm -rf /tmp/*.whl

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash hyper2kvm && \
    mkdir -p /data /output && \
    chown -R hyper2kvm:hyper2kvm /data /output

USER hyper2kvm
WORKDIR /data

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import hyper2kvm; print(hyper2kvm.__version__)" || exit 1

# Default command shows help
ENTRYPOINT ["hyper2kvm"]
CMD ["--help"]

# Stage 5: Testing image
FROM development AS testing

# Run tests during build (optional, comment out for faster builds)
# RUN hatch run test

# Default command runs tests
CMD ["hatch", "run", "ci"]
