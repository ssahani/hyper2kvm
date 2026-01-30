# Quick Start Guide

Get started with hyper2kvm in 5 minutes.

## Prerequisites

- Linux system (Fedora, Ubuntu, RHEL, or SUSE)
- Python 3.10 or later
- Root/sudo access
- Source VM disk files (VMDK, VHD, or raw images)

---

## 1. Install System Dependencies

### Fedora / RHEL / CentOS Stream

```bash
sudo dnf install -y \
  python3 python3-pip \
  qemu-img qemu-kvm \
  libguestfs libguestfs-tools \
  openssh-clients rsync \
  libvirt-client libvirt-daemon-kvm
```

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-pip python3-venv \
  qemu-utils \
  libguestfs-tools \
  openssh-client rsync \
  libvirt-clients libvirt-daemon-system
```

### Verify libguestfs

```bash
sudo libguestfs-test-tool
```

This must pass before proceeding. If it fails, check KVM permissions and kernel modules.

---

## 2. Install hyper2kvm

### Option A: Install from Source (Recommended for Development)

```bash
# Clone the repository
git clone https://github.com/hyper2kvm/hyper2kvm.git
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
```

### Option B: Install from PyPI (When Available)

```bash
pip install hyper2kvm
hyper2kvm --help
```

---

## 3. Your First Migration

### Scenario: Convert a Local VMDK to QCOW2

You have a VMware VMDK file and want to run it on KVM.

#### Step 1: Locate Your VMDK

```bash
ls -lh /path/to/your-vm.vmdk
```

#### Step 2: Run the Conversion

```bash
sudo python -m hyper2kvm local \
  --vmdk /path/to/your-vm.vmdk \
  --flatten \
  --to-output /var/lib/libvirt/images/your-vm.qcow2 \
  --compress
```

**What this does:**
- `local` - Process a local disk file
- `--vmdk` - Source VMDK path
- `--flatten` - Flatten snapshot chains
- `--to-output` - Output QCOW2 path
- `--compress` - Enable QCOW2 compression

#### Step 3: Verify the Output

```bash
qemu-img info /var/lib/libvirt/images/your-vm.qcow2
```

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
```

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
```

### Fetch VMDK from ESXi and Convert

```bash
sudo python -m hyper2kvm fetch-and-fix \
  --host esxi.example.com \
  --user root \
  --remote /vmfs/volumes/datastore1/vm/vm.vmdk \
  --fetch-all \
  --flatten \
  --to-output vm.qcow2
```

### Fix Running VM Over SSH (No Conversion)

```bash
sudo python -m hyper2kvm live-fix \
  --host 192.168.1.100 \
  --user root \
  --sudo \
  --fix-network \
  --fix-bootloader
```

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
```

### Run with Config File

```bash
sudo python -m hyper2kvm --config vm-config.json
```

### Use Example Configs

```bash
# Browse available examples
ls examples/json/

# Use an example
sudo python -m hyper2kvm --config examples/json/10-local/local-linux-basic.json
```

---

## 6. Testing the Converted VM

### Test with QEMU (No LibVirt Required)

```bash
sudo python -m hyper2kvm local \
  --vmdk test.vmdk \
  --to-output test.qcow2 \
  --qemu-test \
  --dry-run
```

### Test with LibVirt

```bash
sudo python -m hyper2kvm local \
  --vmdk test.vmdk \
  --to-output test.qcow2 \
  --libvirt-test
```

### Manual Boot Test

```bash
# Boot directly with QEMU
sudo qemu-system-x86_64 \
  -m 2048 \
  -smp 2 \
  -drive file=/var/lib/libvirt/images/your-vm.qcow2,if=virtio \
  -enable-kvm \
  -nographic
```

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
```

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
```

### Issue: "Permission denied" errors

**Solution:**
```bash
# Run with sudo
sudo python -m hyper2kvm ...

# Or adjust permissions
sudo chown $(whoami) /var/lib/libvirt/images/
```

### Issue: VMDK not found

**Solution:**
```bash
# Use absolute paths
sudo python -m hyper2kvm local \
  --vmdk "$(pwd)/vm.vmdk" \
  --to-output "$(pwd)/output.qcow2"
```

### Issue: Network doesn't work after migration

**Solution:**
```bash
# Use network fixing
sudo python -m hyper2kvm local \
  --vmdk vm.vmdk \
  --to-output vm.qcow2 \
  --fix-network
```

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
```

---

## 9. Next Steps

### Explore Documentation

- **[Installation Guide](INSTALL.md)** - Detailed installation instructions
- **[CLI Reference](CLI_REFERENCE.md)** - Complete command-line options
- **[Examples](../examples/)** - 30+ working configuration examples
- **[Architecture](ARCHITECTURE.md)** - How hyper2kvm works internally
- **[Troubleshooting](FAILURE_MODES.md)** - Common problems and solutions

### Try Advanced Features

- **Batch Migration** - Convert multiple VMs
- **vSphere Integration** - Export directly from vCenter
- **Cloud-Init** - Prepare cloud images
- **Custom Scripts** - Post-processing hooks

### Get Help

- **GitHub Issues:** https://github.com/hyper2kvm/hyper2kvm/issues
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
```

---

**You're ready to start migrating VMs! 🚀**

For detailed information, see the full documentation in the `docs/` directory.
