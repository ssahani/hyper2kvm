# Hyper2KVM Frequently Asked Questions (FAQ)

Common questions and answers about using Hyper2KVM for VM migration.

## Table of Contents

### General Questions
- [What is Hyper2KVM?](#what-is-hyper2kvm)
- [What makes it different from other tools?](#what-makes-it-different)
- [Is it production-ready?](#is-it-production-ready)
- [What platforms does it support?](#supported-platforms)
- [Do I need to stop the source VM?](#vm-downtime)

### Installation & Setup
- [How do I install Hyper2KVM?](#installation)
- [What are the system requirements?](#system-requirements)
- [Do I need root access?](#root-access)
- [Can I run it in a container?](#container-deployment)

### Migration Questions
- [How long does a migration take?](#migration-time)
- [Can I migrate Windows VMs?](#windows-support)
- [What about multi-disk VMs?](#multi-disk-vms)
- [Can I migrate running VMs?](#live-migration)
- [How do I migrate multiple VMs?](#batch-migration)

### Technical Questions
- [What formats are supported?](#supported-formats)
- [Does it work with encrypted disks?](#encrypted-disks)
- [Can it handle snapshots?](#snapshots)
- [What about thin-provisioned disks?](#thin-provisioning)

### Troubleshooting
- [VM won't boot after migration](#boot-failure)
- [Network doesn't work](#network-failure)
- [Migration fails with error](#migration-errors)
- [How do I rollback?](#rollback)

---

## General Questions

### What is Hyper2KVM?

Hyper2KVM is an enterprise-grade VM migration toolkit that converts virtual machines from VMware, Hyper-V, AWS, Azure, and other hypervisors into production-ready KVM systems.

**Key Features:**
- **Automated Fixes**: Bootloader, fstab, initramfs regeneration
- **VMCraft Engine**: 480+ native Python APIs for VM manipulation
- **Multi-Format Support**: VMDK, OVA, OVF, VHD, AMI, raw
- **Windows Support**: VirtIO driver injection, registry modification
- **Batch Processing**: Parallel multi-VM migrations
- **Enterprise Ready**: Kubernetes operator, monitoring, HA

**See**: [Main Documentation](index.md)

---

### What makes it different from other tools?

Unlike traditional migration tools that "boot and hope," Hyper2KVM applies **deterministic offline fixes** to ensure **first-boot success**:

| Feature | virt-v2v | Other Tools | Hyper2KVM |
|---------|----------|-------------|-----------|
| **Offline Fixes** | Limited | None | Comprehensive |
| **Windows VirtIO** | Manual | Manual | Automatic |
| **fstab Repair** | Basic | None | Advanced |
| **Initramfs Rebuild** | No | No | Yes |
| **XFS UUID Fix** | No | No | Yes |
| **Batch Migration** | Limited | Limited | Full |
| **Native Python** | No (C) | Varies | Yes |
| **Kubernetes** | No | No | Yes |

**Key Differentiator**: **VMCraft** - Native Python VM manipulation engine with 480+ APIs.

---

### Is it production-ready?

**Yes!** Hyper2KVM v2.1.0+ is production-ready:

✅ **Tested**:
- 450+ automated tests
- 87.5% code coverage
- 500+ successful migrations

✅ **Platforms**:
- OpenShift Container Platform 4.10-4.16
- Kubernetes 1.24-1.33
- RHEL/CentOS, Ubuntu, SUSE, Photon OS
- Windows Server 2012-2025, Windows 10/11

✅ **Enterprise Features**:
- High availability
- Monitoring (Prometheus/Grafana)
- Security (SCCs, RBAC)
- Audit logging

**See**: [Test Results](test-results/TEST_RESULTS.md)

---

### Supported Platforms

**Source Hypervisors:**
- ✅ VMware ESXi 6.5-8.0
- ✅ VMware Workstation/Fusion
- ✅ Hyper-V (2012-2022)
- ✅ AWS EC2
- ✅ Azure VMs
- ✅ Google Cloud
- ✅ KVM (P2V-like scenarios)

**Guest Operating Systems:**
- ✅ Windows 7-11, Server 2008-2025
- ✅ RHEL/CentOS 7-10
- ✅ Ubuntu 18.04-24.04
- ✅ Debian 10-12
- ✅ SUSE/openSUSE 15+
- ✅ Oracle Linux
- ✅ Photon OS 3.0-5.0
- ✅ Rocky Linux, AlmaLinux

**Output Formats:**
- ✅ qcow2 (recommended)
- ✅ raw
- ✅ VDI (VirtualBox)

**See**: [OS Support](os-support/README.md)

---

### VM Downtime

**Short Answer**: Depends on method

**Methods:**

1. **Standard Migration** (Recommended)
   - **Downtime**: Full downtime during migration
   - **Duration**: 10-30 minutes depending on size
   - **Best for**: Most migrations

2. **Live Fix** (Advanced)
   - **Downtime**: <5 seconds for final switchover
   - **Duration**: Preparation + quick switchover
   - **Best for**: Production systems
   - **See**: [Live Fix Guide](guides/migration/playbooks.md#live-fix)

3. **Batch Migration**
   - **Downtime**: Per VM (can stagger)
   - **Duration**: Parallel processing
   - **Best for**: Multiple VMs

**See**: [Migration Playbooks](guides/migration/playbooks.md)

---

## Installation & Setup

### Installation

**Quick Install:**

```bash
# Full installation (recommended)
pip install "hyper2kvm[full]"

# Minimal installation
pip install hyper2kvm

# From source
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
pip install -e ".[full]"
```

**Verification:**

```bash
h2kvmctl --version
hyper2kvm --version
```

**See**: [Installation Guide](getting-started/01-Installation.md)

---

### System Requirements

**Minimum:**
- Python 3.10+
- 4 GB RAM
- 2 CPU cores
- 2x VM size disk space
- Linux OS

**Recommended:**
- Python 3.11+
- 8+ GB RAM
- 4+ CPU cores
- 3x VM size disk space
- RHEL 9 / Ubuntu 22.04+

**See**: [System Requirements](getting-started/README.md#prerequisites)

---

### Root Access

**Yes, most operations require root/sudo.**

**Why:**
- Mount filesystems
- Modify disk images
- Access guest filesystems
- Install bootloaders
- Modify system files

**Usage:**

```bash
# Run with sudo
sudo h2kvmctl --config migration.yaml

# Or use sudo -i
sudo -i
h2kvmctl --config migration.yaml
```

**Security**: See [Security Best Practices](guides/security-best-practices.md)

---

### Container Deployment

**Yes! Multiple options:**

1. **Docker/Podman**
   ```bash
   podman run -d -v /data:/data \
     ghcr.io/ssahani/hyper2kvm:2.1.0-worker
   ```

2. **Kubernetes**
   ```bash
   helm install hyper2kvm-operator ./helm/hyper2kvm-operator
   ```

3. **OpenShift**
   ```bash
   # Via OperatorHub or Helm
   ```

**See**: [Container Deployment Guide](deployment/container-deployment-guide.md)

---

## Migration Questions

### Migration Time

**Typical Times:**

| VM Size | OS Type | Time |
|---------|---------|------|
| <20 GB | Linux | 3-5 min |
| <20 GB | Windows | 5-8 min |
| 20-50 GB | Linux | 8-15 min |
| 20-50 GB | Windows | 12-20 min |
| >50 GB | Linux | 20-40 min |
| >50 GB | Windows | 30-60 min |

**Factors:**
- Disk size
- Compression level
- Network speed (remote fetch)
- Fixes enabled
- System performance

**See**: [Performance Metrics](test-results/README.md#migration-time-benchmarks)

---

### Windows Support

**Yes! Full Windows support including:**

✅ **VirtIO Driver Injection**
- Automatic driver installation
- Registry modification
- Network adapter configuration

✅ **Supported Versions:**
- Windows 7-11
- Windows Server 2008 R2 - 2025

✅ **Features:**
- Boot sector fixes
- Driver injection
- Registry updates
- Network configuration

**Example:**

```yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/vms
to_output: windows-server.qcow2

# Windows-specific
windows_drivers: true
```

**See**: [Windows Migration Guide](os-support/windows/guide.md)

---

### Multi-Disk VMs

**Yes, but requires multiple migrations:**

```bash
# Disk 1 (boot disk with fixes)
sudo hyper2kvm --config << EOF
command: local
vmdk: /vmware/vm-disk1.vmdk
output_dir: /kvm/vms
to_output: vm-disk1.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
EOF

# Disk 2 (data disk, no fixes needed)
sudo hyper2kvm --config << EOF
command: local
vmdk: /vmware/vm-disk2.vmdk
output_dir: /kvm/vms
to_output: vm-disk2.qcow2
compress: true
EOF
```

**Then update libvirt XML to include both disks.**

**See**: [Recipe #10](recipes/README.md#recipe-10-multi-disk-vm)

---

### Live Migration

**Yes, using live-fix method:**

```yaml
command: live-fix
host: esxi-host.example.com
user: root
identity: ~/.ssh/id_rsa

# Fixes
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
```

**Process:**
1. Connect to running VM via SSH
2. Apply fixes while running
3. Quick switchover (<5s downtime)

**See**: [Migration Playbooks](guides/migration/playbooks.md#live-fix)

---

### Batch Migration

**Yes! Multiple methods:**

**Method 1: JSON Manifest**

```yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
output_dir: /kvm/batch
```

```json
{
  "migrations": [
    {"vmdk": "/vmware/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vmware/vm2.vmdk", "to_output": "vm2.qcow2"},
    {"vmdk": "/vmware/vm3.vmdk", "to_output": "vm3.qcow2"}
  ]
}
```

**Method 2: Kubernetes Operator**

Submit multiple MigrationJob CRDs.

**See**: [Batch Migration Guide](guides/migration/batch-features.md)

---

## Technical Questions

### Supported Formats

**Input Formats:**
- ✅ VMDK (all types: monolithic, split, sparse, streamOptimized)
- ✅ OVA (VMware export archive)
- ✅ OVF (VMware export descriptor)
- ✅ VHD/VHDX (Hyper-V)
- ✅ AMI (AWS EC2 tarball)
- ✅ raw disk images
- ✅ Azure VHD

**Output Formats:**
- ✅ qcow2 (recommended)
- ✅ raw
- ✅ VDI (VirtualBox)

**See**: [CLI Reference](guides/cli/reference.md)

---

### Encrypted Disks

**Partial Support:**

**BitLocker (Windows):**
- ❌ Cannot migrate while encrypted
- ✅ Decrypt before migration
- ✅ Re-encrypt after migration

**LUKS (Linux):**
- ❌ Cannot modify while encrypted
- ✅ Decrypt before migration
- ✅ Re-encrypt after migration

**Workaround:**

```bash
# 1. Decrypt on source
# Windows: Disable BitLocker
# Linux: cryptsetup luksClose

# 2. Migrate
sudo hyper2kvm --config migration.yaml

# 3. Re-encrypt on target
# Windows: Enable BitLocker
# Linux: cryptsetup luksFormat
```

**See**: [Security Best Practices](guides/security-best-practices.md)

---

### Snapshots

**VMware Snapshots:**
- ❌ Not supported (linked clones)
- ✅ Consolidate snapshots first
- ✅ Export as standalone VM

**Process:**

```bash
# In VMware
1. Right-click VM → Snapshots → Consolidate
2. Wait for consolidation
3. Export VM or migrate VMDK
```

**See**: [VMDK Inspector](features/vmdk-inspector.md)

---

### Thin Provisioning

**Yes, supported:**

**Source:**
- ✅ Thin-provisioned VMDKs
- ✅ Thick-provisioned VMDKs

**Output:**
- ✅ Sparse qcow2 (default, space-efficient)
- ✅ Preallocated qcow2 (for performance)
- ✅ raw (full size)

**Example:**

```yaml
# Sparse output (saves space)
compress: true
keep_sparse: true

# Preallocated output (better performance)
preallocate: true
compress: false
```

---

## Troubleshooting

### Boot Failure

**Problem**: VM doesn't boot after migration

**Common Causes:**
1. Missing virtio drivers in initramfs
2. Wrong fstab entries
3. GRUB configuration issues
4. Wrong disk controller

**Solution:**

```yaml
command: offline-fix
qcow2: /kvm/vms/failed-boot.qcow2

# Comprehensive fixes
fstab_mode: stabilize-all
regen_initramfs: true
initramfs_add_drivers:
  - virtio
  - virtio_blk
  - virtio_scsi
  - virtio_net
update_grub: true
```

**See**: [Troubleshooting Guide](guides/troubleshooting.md#boot-failures)

---

### Network Failure

**Problem**: No network connectivity after migration

**Common Causes:**
1. Missing virtio_net driver
2. MAC address change
3. Network interface name change
4. NetworkManager issues

**Solution:**

```yaml
command: offline-fix
qcow2: /kvm/vms/no-network.qcow2

# Network fixes
regen_initramfs: true
initramfs_add_drivers:
  - virtio_net
  - e1000
fstab_mode: stabilize-all
```

**Manual Fix:**

```bash
# Inside VM after boot
ip link  # Check interface name
nmcli device  # Check NetworkManager
```

**See**: [Troubleshooting Guide](guides/troubleshooting.md#network-issues)

---

### Migration Errors

**Problem**: Migration fails with error

**Common Errors:**

1. **Permission Denied**
   ```bash
   # Solution: Run with sudo
   sudo hyper2kvm --config migration.yaml
   ```

2. **Disk Space**
   ```bash
   # Check available space (need 3x VM size)
   df -h /output/directory
   ```

3. **Missing Dependencies**
   ```bash
   # Install required tools
   sudo dnf install -y qemu-img qemu-system-x86  # RHEL/Fedora
   sudo apt-get install -y qemu-utils  # Ubuntu
   ```

4. **Corrupt VMDK**
   ```bash
   # Validate VMDK first
   ./scripts/vmdk_inspect.py /path/to/vm.vmdk
   ```

**See**: [Troubleshooting Guide](guides/troubleshooting.md)

---

### Rollback

**If migration fails or VM doesn't work:**

**Option 1: Keep Original**
- Original VM is never modified
- Simply don't delete source
- Start original VM if needed

**Option 2: Use Snapshots**
```bash
# Before migration
qemu-img snapshot -c before_migration vm.qcow2

# Rollback if needed
qemu-img snapshot -a before_migration vm.qcow2
```

**Option 3: Backup**
```bash
# Before migration
cp /vmware/original.vmdk /backup/original.vmdk.backup
```

**See**: [Migration Playbooks](guides/migration/playbooks.md#rollback-procedures)

---

## Additional Resources

### Documentation
- **[Main Documentation Hub](index.md)** - Complete documentation
- **[Getting Started](getting-started/)** - Installation and setup
- **[Tutorials](tutorials/)** - Step-by-step learning
- **[Recipes](recipes/)** - Quick solutions
- **[Troubleshooting](guides/troubleshooting.md)** - Fix common issues

### Support
- **GitHub Issues**: [Report bugs](https://github.com/ssahani/hyper2kvm/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/ssahani/hyper2kvm/discussions)

### Examples
- **[Migration Recipes](recipes/)** - Real-world examples
- **[Config Examples](../examples/)** - Sample configurations

---

**Can't find your question?** [Ask on GitHub Discussions](https://github.com/ssahani/hyper2kvm/discussions)

---

**Last Updated**: February 2026  
**Total Questions**: 25+  
**Coverage**: Installation, Migration, Troubleshooting, Technical
