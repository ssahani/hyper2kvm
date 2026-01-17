# Quick Start Guide 🚀

Get started with hyper2kvm in 5 minutes ⚡


## Table of Contents

- [Prerequisites ✅](#prerequisites)
- [1. Install System Dependencies 🔧](#1-install-system-dependencies)
  - [Fedora / RHEL / CentOS Stream 🎩](#fedora-rhel-centos-stream)
  - [Ubuntu / Debian](#ubuntu-debian)
  - [Verify libguestfs](#verify-libguestfs)
- [2. Install hyper2kvm](#2-install-hyper2kvm)
  - [Option A: Install from Source (Recommended for Development)](#option-a-install-from-source-recommended-for-development)
  - [Option B: Install from PyPI (When Available)](#option-b-install-from-pypi-when-available)
- [3. Your First Migration 🎯](#3-your-first-migration)
  - [Scenario: Convert a Local VMDK to QCOW2 💫](#scenario-convert-a-local-vmdk-to-qcow2)
    - [Step 1: Locate Your VMDK](#step-1-locate-your-vmdk)
    - [Step 2: Run the Conversion](#step-2-run-the-conversion)
    - [Step 3: Verify the Output](#step-3-verify-the-output)
- [4. Common Scenarios](#4-common-scenarios)
  - [Linux VM with Network/Bootloader Fixes](#linux-vm-with-networkbootloader-fixes)
  - [Windows VM with VirtIO Driver Injection](#windows-vm-with-virtio-driver-injection)
  - [Fetch VMDK from ESXi and Convert](#fetch-vmdk-from-esxi-and-convert)
  - [Fix Running VM Over SSH (No Conversion)](#fix-running-vm-over-ssh-no-conversion)
- [5. Using Configuration Files](#5-using-configuration-files)
  - [Create a Config File (vm-config.json)](#create-a-config-file-vm-configjson)
  - [Run with Config File](#run-with-config-file)
  - [Use Example Configs](#use-example-configs)
- [6. Testing the Converted VM](#6-testing-the-converted-vm)
  - [Test with QEMU (No LibVirt Required)](#test-with-qemu-no-libvirt-required)
  - [Test with LibVirt](#test-with-libvirt)
  - [Manual Boot Test](#manual-boot-test)
- [7. Deploy to Production](#7-deploy-to-production)
  - [Create LibVirt Domain](#create-libvirt-domain)
- [8. Common Issues and Solutions](#8-common-issues-and-solutions)
  - [Issue: libguestfs-test-tool fails](#issue-libguestfs-test-tool-fails)
  - [Issue: "Permission denied" errors](#issue-permission-denied-errors)
  - [Issue: VMDK not found](#issue-vmdk-not-found)
  - [Issue: Network doesn't work after migration](#issue-network-doesnt-work-after-migration)
  - [Issue: Windows won't boot](#issue-windows-wont-boot)
- [9. Next Steps](#9-next-steps)
  - [Explore Documentation](#explore-documentation)
  - [Try Advanced Features](#try-advanced-features)
  - [Get Help](#get-help)
- [10. Command Cheat Sheet](#10-command-cheat-sheet)
  - [Advanced Examples](#advanced-examples)
    - [Example: Batch Migration](#example-batch-migration)
    - [Example: Cloud-Init Injection](#example-cloud-init-injection)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
    - [Issue: Command fails with permission denied](#issue-command-fails-with-permission-denied)
    - [Issue: libguestfs fails to mount disk](#issue-libguestfs-fails-to-mount-disk)
- [Next Steps](#next-steps)
- [Getting Help](#getting-help)

---
## Prerequisites ✅

- 🐧 Linux system (Fedora, Ubuntu, RHEL, or SUSE)
- 🐍 Python 3.10 or later
- 🔑 Root/sudo access
- 💾 Source VM disk files (VMDK, VHD, or raw images)

---

## 1. Install System Dependencies 🔧

### Fedora / RHEL / CentOS Stream 🎩

```bash
sudo dnf install -y \
  python3 python3-pip \
  qemu-img qemu-kvm \
  libguestfs libguestfs-tools \
  openssh-clients rsync \
  libvirt-client libvirt-daemon-kvm
```bash

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-pip python3-venv \
  qemu-utils \
  libguestfs-tools \
  openssh-client rsync \
  libvirt-clients libvirt-daemon-system
```bash

### Verify libguestfs

```bash
sudo libguestfs-test-tool
```bash

This must pass before proceeding. If it fails, check KVM permissions and kernel modules.

---

## 2. Install hyper2kvm

### Option A: Install from Source (Recommended for Development)

```bash
# Clone the repository
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -U pip wheel setuptools
pip install -r requirements.txt
pip install -e .

# Verify installation
python -m hyper2kvm --help
```bash

### Option B: Install from PyPI (When Available)

```bash
pip install hyper2kvm
hyper2kvm --help
```bash

---

## 3. Your First Migration 🎯

### Scenario: Convert a Local VMDK to QCOW2 💫

You have a VMware VMDK file and want to run it on KVM.

#### Step 1: Locate Your VMDK

```bash
ls -lh /path/to/your-vm.vmdk
```bash

#### Step 2: Run the Conversion

```bash
sudo python -m hyper2kvm local \
  --vmdk /path/to/your-vm.vmdk \
  --flatten \
  --to-output /var/lib/libvirt/images/your-vm.qcow2 \
  --compress
```bash

**What this does:**
- `local` - Process a local disk file
- `--vmdk` - Source VMDK path
- `--flatten` - Flatten snapshot chains
- `--to-output` - Output QCOW2 path
- `--compress` - Enable QCOW2 compression

#### Step 3: Verify the Output

```bash
qemu-img info /var/lib/libvirt/images/your-vm.qcow2
```bash

---

## 4. Common Scenarios

### Linux VM with Network/Bootloader Fixes

```bash
sudo python -m hyper2kvm local \
  --vmdk linux-vm.vmdk \
  --flatten \
  --to-output linux-vm.qcow2 \
  --fix-network \
  --fix-bootloader \
  --compress
```bash

### Windows VM with VirtIO Driver Injection

```bash
# First, download VirtIO drivers
wget https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso

# Convert with driver injection
sudo python -m hyper2kvm local \
  --vmdk windows-vm.vmdk \
  --flatten \
  --to-output windows-vm.qcow2 \
  --windows \
  --inject-virtio \
  --virtio-win-iso ./virtio-win.iso \
  --compress
```bash

### Fetch VMDK from ESXi and Convert

```bash
sudo python -m hyper2kvm fetch-and-fix \
  --host esxi.example.com \
  --user root \
  --remote /vmfs/volumes/datastore1/vm/vm.vmdk \
  --fetch-all \
  --flatten \
  --to-output vm.qcow2
```bash

### Fix Running VM Over SSH (No Conversion)

```bash
sudo python -m hyper2kvm live-fix \
  --host 192.168.1.100 \
  --user root \
  --sudo \
  --fix-network \
  --fix-bootloader
```bash

---

## 5. Using Configuration Files

Instead of long command lines, use config files:

### Create a Config File (vm-config.json)

```json
{
  "command": "local",
  "vmdk": "/data/vms/production-web.vmdk",
  "flatten": true,
  "to_output": "/var/lib/libvirt/images/production-web.qcow2",
  "compress": true,
  "fix_network": true,
  "fix_bootloader": true,
  "report": "/var/log/migration-report.md"
}
```bash

### Run with Config File

```bash
sudo python -m hyper2kvm --config vm-config.json
```bash

### Use Example Configs

```bash
# Browse available examples
ls examples/json/

# Use an example
sudo python -m hyper2kvm --config examples/json/10-local/local-linux-basic.json
```bash

---

## 6. Testing the Converted VM

### Test with QEMU (No LibVirt Required)

```bash
sudo python -m hyper2kvm local \
  --vmdk test.vmdk \
  --to-output test.qcow2 \
  --qemu-test \
  --dry-run
```bash

### Test with LibVirt

```bash
sudo python -m hyper2kvm local \
  --vmdk test.vmdk \
  --to-output test.qcow2 \
  --libvirt-test
```bash

### Manual Boot Test

```bash
# Boot directly with QEMU
sudo qemu-system-x86_64 \
  -m 2048 \
  -smp 2 \
  -drive file=/var/lib/libvirt/images/your-vm.qcow2,if=virtio \
  -enable-kvm \
  -nographic
```bash

---

## 7. Deploy to Production

### Create LibVirt Domain

```bash
# Generate domain XML
virt-install \
  --name your-vm \
  --memory 4096 \
  --vcpus 2 \
  --disk path=/var/lib/libvirt/images/your-vm.qcow2,format=qcow2 \
  --network network=default \
  --graphics vnc \
  --import \
  --print-xml > your-vm.xml

# Define and start
sudo virsh define your-vm.xml
sudo virsh start your-vm

# Check status
sudo virsh list --all
sudo virsh console your-vm
```bash

---

## 8. Common Issues and Solutions

### Issue: libguestfs-test-tool fails

**Solution:**
```bash
# Check KVM permissions
ls -l /dev/kvm
sudo usermod -aG kvm $(whoami)
# Log out and back in

# Load KVM modules
sudo modprobe kvm
sudo modprobe kvm_intel  # or kvm_amd
```bash

### Issue: "Permission denied" errors

**Solution:**
```bash
# Run with sudo
sudo python -m hyper2kvm ...

# Or adjust permissions
sudo chown $(whoami) /var/lib/libvirt/images/
```bash

### Issue: VMDK not found

**Solution:**
```bash
# Use absolute paths
sudo python -m hyper2kvm local \
  --vmdk "$(pwd)/vm.vmdk" \
  --to-output "$(pwd)/output.qcow2"
```bash

### Issue: Network doesn't work after migration

**Solution:**
```bash
# Use network fixing
sudo python -m hyper2kvm local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --fix-network
```bash

### Issue: Windows won't boot

**Solution:**
```bash
# Inject VirtIO drivers
sudo python -m hyper2kvm local \
  --vmdk windows.vmdk \
  --to-output windows.qcow2 \
  --windows \
  --inject-virtio \
  --virtio-win-iso /path/to/virtio-win.iso
```bash

---

## 9. Next Steps

### Explore Documentation

- **[Installation Guide](02-Installation.md)** - Detailed installation instructions
- **[CLI Reference](04-CLI-Reference.md)** - Complete command-line options
- **[Examples](../examples/)** - 30+ working configuration examples
- **[Architecture](01-Architecture.md)** - How hyper2kvm works internally
- **[Troubleshooting](90-Failure-Modes.md)** - Common problems and solutions

### Try Advanced Features

- **Batch Migration** - Convert multiple VMs
- **vSphere Integration** - Export directly from vCenter
- **Cloud-Init** - Prepare cloud images
- **Custom Scripts** - Post-processing hooks

### Get Help

- **GitHub Issues:** https://github.com/ssahani/hyper2kvm/issues
- **Documentation:** `docs/` directory
- **Examples:** `examples/` directory

---

## 10. Command Cheat Sheet

```bash
# Basic conversion
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --to-output OUTPUT.qcow2

# With compression and flattening
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --flatten --compress --to-output OUTPUT.qcow2

# Linux with fixes
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --fix-network --fix-bootloader --to-output OUTPUT.qcow2

# Windows with VirtIO
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --windows --inject-virtio --virtio-win-iso VIRTIO.iso --to-output OUTPUT.qcow2

# Fetch from ESXi
sudo python -m hyper2kvm fetch-and-fix --host ESXI_HOST --remote VMDK_PATH --to-output OUTPUT.qcow2

# Using config file
sudo python -m hyper2kvm --config CONFIG.json

# Test conversion
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --to-output OUTPUT.qcow2 --qemu-test

# Dry run (preview)
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --to-output OUTPUT.qcow2 --dry-run

# Generate report
sudo python -m hyper2kvm local --vmdk INPUT.vmdk --to-output OUTPUT.qcow2 --report REPORT.md

# Debug mode
sudo python -m hyper2kvm --log-level DEBUG local --vmdk INPUT.vmdk --to-output OUTPUT.qcow2
```bash

---

**You're ready to start migrating VMs! **

For detailed information, see the full documentation in the `docs/` directory.

### Advanced Examples

#### Example: Batch Migration

```bash
# Create a list of VMs to migrate
cat > vms.txt <<VMLIST
/data/vm1.vmdk
/data/vm2.vmdk
/data/vm3.vmdk
VMLIST

# Migrate all VMs
while read vmdk; do
  name=$(basename "$vmdk" .vmdk)
  sudo python -m hyper2kvm local \
    --vmdk "$vmdk" \
    --flatten \
    --to-output "/var/lib/libvirt/images/${name}.qcow2" \
    --compress
done < vms.txt
```

#### Example: Cloud-Init Injection

```bash
sudo python -m hyper2kvm local \
  --vmdk ubuntu-template.vmdk \
  --to-output cloud-ubuntu.qcow2 \
  --inject-cloud-init \
  --compress
```


## Troubleshooting

### Common Issues

#### Issue: Command fails with permission denied

**Symptoms:**
- Error: "Permission denied" when accessing disk images
- Cannot write to output directory

**Solution:**
```bash
# Run with sudo
sudo python -m hyper2kvm --config your-config.yaml

# Or fix permissions
sudo chown $(whoami) /path/to/output/directory
```

#### Issue: libguestfs fails to mount disk

**Symptoms:**
- Error: "guestfs_mount: failed"
- Cannot inspect guest OS

**Solution:**
```bash
# Test libguestfs
sudo libguestfs-test-tool

# Check KVM permissions
sudo usermod -aG kvm $(whoami)
# Log out and back in

# Verify disk image
qemu-img info /path/to/disk.vmdk
```

For more issues, see [Failure Modes](90-Failure-Modes.md).

## Next Steps

Now that you've completed your first migration:

1. **[Explore Examples](../examples/README.md)** - 40+ ready-to-use configuration files
2. **[Read the Cookbook](06-Cookbook.md)** - Common migration recipes
3. **[Understand Architecture](01-Architecture.md)** - How hyper2kvm works internally
4. **[Windows Migrations](10-Windows-Guide.md)** - If you need to migrate Windows VMs

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)
- **Troubleshooting:** [Failure Modes Guide](90-Failure-Modes.md)
- **Documentation:** All docs in `docs/` directory

