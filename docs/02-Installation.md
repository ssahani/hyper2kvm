## Installation

### Table of Contents

- [Quick Start](#quick-start-recommended-editable-install)
- [Shell Completion (Optional)](#shell-completion-optional)
- [System Dependencies by OS](#system-dependencies-by-os)
  - [Linux](#linux)
  - [macOS](#macos)
  - [Windows (WSL)](#windows-wsl)
- [Verify Installation](#verify-libguestfs-works-do-this-once)
- [Running](#running)
- [Developer Install](#developer-install)

### Quick start (recommended: editable install)

```bash
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip wheel setuptools
python -m pip install -r requirements.txt
python -m pip install -e .

# sanity check
python -m hyper2kvm --help
# or, if you keep the launcher:
python ./hyper2kvm.py --help
```

### Shell Completion (Optional)

Enable intelligent tab completion for bash, zsh, or fish shells. This provides automatic completion for all command-line arguments and options.

**Prerequisites:**

```bash
# Install argcomplete (required for shell completion)
pip install argcomplete

# Or via system package manager
sudo dnf install python3-argcomplete  # Fedora/RHEL/CentOS
sudo apt install python3-argcomplete  # Debian/Ubuntu
sudo pacman -S python-argcomplete     # Arch Linux
brew install argcomplete              # macOS
```

**Installation:**

```bash
# Interactive installation (recommended)
./completions/install-completions.sh

# Or install for a specific shell
./completions/install-completions.sh bash
./completions/install-completions.sh zsh
./completions/install-completions.sh fish

# Install for all shells
./completions/install-completions.sh all
```

**Usage:**

After installation, you can use tab completion:

```bash
hyper2kvm --<TAB>              # Shows all available options
hyper2kvm --vm<TAB>            # Completes to --vmdk, --vm-name, etc.
hyper2kvm --vmdk /path/<TAB>   # Path completion
```

For detailed installation instructions and troubleshooting, see [completions/README.md](../completions/README.md).

### System dependencies by OS

`hyper2kvm` is Python, but it **drives real system tools**. You typically need:

* `qemu-img` (from qemu) - Required for disk conversion
* `libguestfs` + tools - Required for offline inspection/editing
* `libvirt` - Only if you use `--libvirt-test`
* `openssh-client` / `scp` - For `fetch-and-fix` and `live-fix`
* optional: `pyvmomi` + `requests` - For `vsphere` downloads/actions
* optional: `watchdog` - For daemon watch mode

---

## Linux

#### Fedora / RHEL / CentOS Stream

```bash
sudo dnf install -y \
  python3 python3-pip python3-virtualenv \
  qemu-img qemu-kvm \
  libguestfs libguestfs-tools libguestfs-xfs \
  openssh-clients rsync \
  libvirt-client libvirt-daemon-kvm

# For libguestfs on Fedora/RHEL: "libguestfs-test-tool" is handy
sudo dnf install -y libguestfs-test-tool
```bash

#### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-pip python3-venv \
  qemu-utils \
  libguestfs-tools \
  openssh-client rsync \
  libvirt-clients libvirt-daemon-system qemu-system-x86
```bash

#### openSUSE / SLES

```bash
sudo zypper install -y \
  python3 python3-pip python3-virtualenv \
  qemu-tools \
  libguestfs libguestfs-tools \
  openssh rsync \
  libvirt-client libvirt-daemon-qemu
```bash

#### Arch Linux / Manjaro

```bash
sudo pacman -Syu --noconfirm \
  python python-pip python-virtualenv \
  qemu-img qemu-system-x86 \
  libguestfs \
  openssh rsync \
  libvirt virt-manager

# Enable and start libvirtd service
sudo systemctl enable --now libvirtd
```bash

#### Alpine Linux

```bash
# Alpine uses apk
sudo apk add --no-cache \
  python3 py3-pip py3-virtualenv \
  qemu-img qemu-system-x86_64 \
  libguestfs libguestfs-tools \
  openssh-client rsync \
  libvirt libvirt-daemon libvirt-client

# Start services
sudo rc-service libvirtd start
sudo rc-update add libvirtd
```bash

---

## macOS

macOS support is **experimental** due to limitations with libguestfs. You can use it for some operations, but full functionality requires a Linux environment.

### Option 1: Using Homebrew (Limited functionality)

```bash
# Install Homebrew if not already installed
# /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install QEMU (qemu-img works natively)
brew install qemu

# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```bash

**Note:** libguestfs is **not available** on macOS. You can use qemu-img for conversions, but offline inspection/fixing won't work.

### Option 2: Using Docker (Recommended for macOS)

Run hyper2kvm in a Linux container with full libguestfs support:

```bash
# Build container
docker build -t hyper2kvm .

# Run with volume mounts
docker run -it --rm \
  --privileged \
  -v $(pwd)/input:/input \
  -v $(pwd)/output:/output \
  hyper2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

### Option 3: Use a Linux VM

The most reliable option for macOS users:
1. Install UTM, Parallels, or VMware Fusion
2. Create an Ubuntu or Fedora VM
3. Follow Linux installation instructions inside the VM

---

## Windows (WSL)

hyper2kvm works in **Windows Subsystem for Linux (WSL2)** with some caveats.

### Prerequisites

1. **Install WSL2** (Windows 10/11):
   ```powershell
   # Run in PowerShell as Administrator
   wsl --install -d Ubuntu
   ```

2. **Enable nested virtualization** (required for KVM):
   ```powershell
   # Only works on Windows 11 or Windows 10 build 19044+
   # May require enabling in BIOS/UEFI
   ```

### Installation in WSL2

Once inside your WSL2 Ubuntu environment:

```bash
# Update package list
sudo apt-get update

# Install system dependencies
sudo apt-get install -y \
  python3 python3-pip python3-venv \
  qemu-utils qemu-system-x86 \
  libguestfs-tools \
  openssh-client rsync \
  libvirt-clients libvirt-daemon-system

# Clone and install hyper2kvm
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```bash

### Known WSL2 Limitations

- **KVM acceleration** may not work (depends on Windows version and CPU)
- **libguestfs** might have issues with nested virtualization
- File I/O between Windows and WSL2 can be slow
- Use `/mnt/c/` to access Windows drives

### Workaround: Use Docker Desktop for Windows

```powershell
# In PowerShell (Windows side)
docker run -it --rm --privileged `
  -v C:\VMs\input:/input `
  -v C:\VMs\output:/output `
  hyper2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

---

### Verify libguestfs works (do this once)

If `libguestfs` can’t launch its appliance, everything else becomes sadness.

```bash
sudo libguestfs-test-tool
```bash

If that fails, it's usually KVM permissions, missing kernel modules, or a broken appliance setup.

---

## Container/Alternative Installation Methods

### Using Docker

Create a `Dockerfile`:

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    qemu-utils qemu-system-x86 \
    libguestfs-tools python3-guestfs \
    openssh-client rsync \
    libvirt-clients libvirt-daemon-system \
    git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN python3 -m pip install --no-cache-dir -r requirements.txt && \
    python3 -m pip install -e .

ENTRYPOINT ["python3", "-m", "hyper2kvm"]
```bash

Build and run:

```bash
docker build -t hyper2kvm .
docker run -it --rm --privileged \
  -v /path/to/input:/input \
  -v /path/to/output:/output \
  hyper2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

### Using Podman

Podman works the same as Docker:

```bash
podman build -t hyper2kvm .
podman run -it --rm --privileged \
  -v /path/to/input:/input:Z \
  -v /path/to/output:/output:Z \
  hyper2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

**Note:** The `:Z` suffix is required for SELinux systems (Fedora/RHEL).

### Using a Virtual Environment (Recommended for development)

This isolates hyper2kvm's dependencies from system Python:

```bash
# Create virtual environment
python3 -m venv ~/.venvs/hyper2kvm

# Activate it
source ~/.venvs/hyper2kvm/bin/activate

# Install
pip install -r requirements.txt
pip install -e .

# Use it
python -m hyper2kvm --help

# Deactivate when done
deactivate
```bash

---

## Troubleshooting Installation

### libguestfs fails with "permission denied"

**Problem:** libguestfs can't access KVM.

**Solution:**
```bash
# Add your user to kvm and libvirt groups
sudo usermod -a -G kvm,libvirt $USER

# Log out and back in, or:
newgrp kvm

# Verify permissions
ls -l /dev/kvm
# Should show: crw-rw----+ 1 root kvm

# Test again
sudo libguestfs-test-tool
```bash

### "could not access KVM kernel module"

**Problem:** KVM kernel module not loaded.

**Solution:**
```bash
# Check if KVM is available
lsmod | grep kvm

# Load KVM modules (Intel)
sudo modprobe kvm_intel

# Or for AMD
sudo modprobe kvm_amd

# Make permanent
echo "kvm_intel" | sudo tee -a /etc/modules
# or
echo "kvm_amd" | sudo tee -a /etc/modules
```bash

### "No matching distribution found for libguestfs"

**Problem:** Trying to install libguestfs via pip.

**Solution:** libguestfs is a **system package**, not a Python package. Install it using your OS package manager (apt, dnf, zypper, pacman) as shown in the sections above. Then use `python3-guestfs` if available.

### "qemu-img: command not found"

**Problem:** QEMU not installed or not in PATH.

**Solution:**
```bash
# Fedora/RHEL
sudo dnf install qemu-img

# Ubuntu/Debian
sudo apt-get install qemu-utils

# Arch
sudo pacman -S qemu-img

# Verify
which qemu-img
qemu-img --version
```bash

### Python version too old

**Problem:** hyper2kvm requires Python 3.10+.

**Solution:**
```bash
# Check Python version
python3 --version

# Ubuntu: Use deadsnakes PPA for newer Python
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv

# Then use python3.12 explicitly
python3.12 -m venv .venv
```bash

### SELinux blocks libguestfs (Fedora/RHEL)

**Problem:** SELinux denies libguestfs operations.

**Solution:**
```bash
# Temporary: Set SELinux to permissive
sudo setenforce 0

# Run your command
sudo python -m hyper2kvm ...

# Re-enable SELinux
sudo setenforce 1

# Permanent fix: Use audit2allow to create policy
# (Advanced - consult SELinux documentation)
```bash

Or run in a container with `--privileged`.

---

## Running

After installation:

```bash
# module entrypoint (preferred)
python -m hyper2kvm --help

# or your top-level script
python ./hyper2kvm.py --help
```bash

Examples:

```bash
sudo python -m hyper2kvm local --vmdk ./mtv-ubuntu22-4.vmdk --flatten --to-output ubuntu.qcow2 --compress
sudo python -m hyper2kvm fetch-and-fix --host esxi.example.com --remote /vmfs/volumes/ds/vm/vm.vmdk --fetch-all --flatten --to-output vm.qcow2
sudo python -m hyper2kvm live-fix --host 192.168.1.50 --sudo --print-fstab
```bash

---

## Developer install

### Run tests

```bash
# Install dependencies
python -m pip install -r requirements.txt
python -m pip install -e .

# Install test dependencies
pip install pytest pytest-cov pytest-xdist ruff mypy bandit

# Run unit tests
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=hyper2kvm --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/test_core/test_utils.py -v

# Run linting
ruff check hyper2kvm/

# Run type checking
mypy hyper2kvm/ --ignore-missing-imports

# Run security scan
bandit -r hyper2kvm/
```bash

### Continuous Integration

Tests run automatically on GitHub Actions for every push and pull request:
- Unit tests on Python 3.10, 3.11, 3.12
- Code quality checks (ruff, mypy)
- Security scanning (Bandit, pip-audit)
- Documentation validation

See `.github/workflows/` for CI configuration.


