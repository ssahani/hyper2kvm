# Dependencies Guide

This document explains the dependencies for hyper2kvm and how to install them.

## Overview

hyper2kvm has two types of dependencies:

1. **System Dependencies** - Installed via OS package manager (apt, dnf, zypper)
2. **Python Dependencies** - Installed via pip

---

## System Dependencies

These **MUST** be installed via your system package manager before installing Python dependencies.

### Required System Packages

| Package | Purpose |
|---------|---------|
| `libguestfs-tools` | Guest filesystem access and modification |
| `python3-guestfs` | Python bindings for libguestfs |
| `qemu-utils` | QEMU disk image utilities (qemu-img) |
| `qemu-system-x86` | QEMU virtualization for testing |
| `libvirt-daemon-system` | LibVirt virtualization management |
| `libvirt-clients` | LibVirt client tools (virsh) |

### Installation by Distribution

#### Fedora / RHEL / CentOS Stream

```bash
sudo dnf install -y \
  python3 \
  python3-pip \
  python3-guestfs \
  libguestfs \
  libguestfs-tools \
  qemu-img \
  qemu-kvm \
  qemu-system-x86 \
  libvirt \
  libvirt-client \
  libvirt-daemon-kvm
```

#### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-pip \
  python3-venv \
  python3-guestfs \
  libguestfs-tools \
  qemu-utils \
  qemu-system-x86 \
  libvirt-daemon-system \
  libvirt-clients
```

#### openSUSE / SLES

```bash
sudo zypper install -y \
  python3 \
  python3-pip \
  python3-virtualenv \
  python3-guestfs \
  libguestfs \
  libguestfs-tools \
  qemu-tools \
  qemu-x86 \
  libvirt-daemon-qemu \
  libvirt-client
```

### Optional System Packages

| Package | Purpose |
|---------|---------|
| `openssh-client` | SSH for remote operations |
| `rsync` | File synchronization |

---

## Python Dependencies

After installing system dependencies, install Python packages via pip.

### Required Python Packages

Install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

**Contents of requirements.txt:**
- `rich>=13.0.0` - Beautiful terminal output
- `click>=8.0.0` - CLI framework
- `PyYAML>=6.0` - YAML configuration parsing
- `requests>=2.31.0` - HTTP client
- `pyvmomi>=8.0.0` - VMware vSphere API

### Development Dependencies

For testing and development:

```bash
pip install -r requirements-dev.txt
```

**Includes:**
- `pytest` - Testing framework
- `pytest-cov` - Code coverage
- `ruff` - Fast Python linter
- `mypy` - Static type checker
- `bandit` - Security scanner

---

## Installation Order

**CRITICAL:** Install in this exact order:

```bash
# 1. Install system dependencies first
sudo apt-get install -y python3-guestfs libguestfs-tools qemu-utils

# 2. Verify libguestfs works
sudo libguestfs-test-tool

# 3. Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Install hyper2kvm
pip install -e .
```

---

## Common Issues

### Issue: "ERROR: No matching distribution found for libguestfs"

**Cause:** `libguestfs` is not a pip package.

**Solution:** Install via system package manager:
```bash
# Ubuntu/Debian
sudo apt-get install python3-guestfs libguestfs-tools

# Fedora/RHEL
sudo dnf install python3-guestfs libguestfs-tools
```

### Issue: "libguestfs-test-tool failed"

**Cause:** libguestfs appliance not properly configured.

**Solution:**
```bash
# Check KVM permissions
sudo usermod -aG kvm $(whoami)
# Log out and back in

# Load KVM modules
sudo modprobe kvm
sudo modprobe kvm_intel  # or kvm_amd

# Run test again
sudo libguestfs-test-tool
```

### Issue: "ImportError: No module named guestfs"

**Cause:** Python guestfs bindings not installed.

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install python3-guestfs

# Fedora/RHEL
sudo dnf install python3-guestfs
```

**Note:** Do NOT use pip to install guestfs - it must come from system packages.

### Issue: Virtual environment issues with system packages

**Cause:** System packages like `python3-guestfs` are not visible in virtualenv.

**Solution:** Use `--system-site-packages` when creating venv:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

Or skip virtualenv for system-wide installation:

```bash
# Install directly (not recommended for development)
pip install --user -r requirements.txt
pip install --user -e .
```

---

## Verifying Installation

After installation, verify everything works:

```bash
# 1. Check system tools
qemu-img --version
virsh --version
guestfish --version

# 2. Check Python can import libguestfs
python3 -c "import guestfs; print('libguestfs OK')"

# 3. Run libguestfs test
sudo libguestfs-test-tool

# 4. Check hyper2kvm
python -m hyper2kvm --help

# 5. Run tests (if dev dependencies installed)
python -m pytest tests/unit/ -v
```

---

## Minimal Installation (No Testing)

If you only need core functionality without testing:

```bash
# System packages
sudo apt-get install python3-guestfs libguestfs-tools qemu-utils

# Python packages (minimal)
pip install rich click PyYAML requests

# Install hyper2kvm
pip install -e .
```

---

## Docker/Container Installation

For containerized environments:

```dockerfile
FROM ubuntu:22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-guestfs \
    libguestfs-tools \
    qemu-utils \
    qemu-system-x86 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Install hyper2kvm
COPY . /app
WORKDIR /app
RUN pip3 install -e .
```

---

## CI/CD Environments

For GitHub Actions, Travis CI, etc:

```yaml
- name: Install system dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      python3-guestfs \
      libguestfs-tools \
      qemu-utils \
      qemu-system-x86

- name: Install Python dependencies
  run: |
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
```

---

## Dependency Updates

### Updating Python Dependencies

```bash
# Update all packages
pip install --upgrade -r requirements.txt

# Update specific package
pip install --upgrade pyvmomi
```

### Updating System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get upgrade libguestfs-tools qemu-utils

# Fedora/RHEL
sudo dnf upgrade libguestfs-tools qemu-img
```

---

## Related Documentation

- [Installation Guide](docs/02-Installation.md)
- [Quick Start](docs/03-Quick-Start.md)
- [Troubleshooting](docs/90-Failure-Modes.md)
