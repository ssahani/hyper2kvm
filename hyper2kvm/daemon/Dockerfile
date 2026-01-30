FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    qemu-utils \
    lvm2 \
    util-linux \
    mount \
    kmod \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    kubernetes==28.1.0

# Create app directory
WORKDIR /app

# Copy NBD prep daemon
COPY nbd_prep.py /app/

# Make it executable
RUN chmod +x /app/nbd_prep.py

# Run as root (required for NBD operations)
USER root

ENTRYPOINT ["python3", "/app/nbd_prep.py"]
