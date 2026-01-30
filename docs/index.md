# Hyper2KVM Documentation Hub

**Enterprise-Grade VM Migration from Hyper-V, VMware, and Other Hypervisors to KVM/Libvirt**

Welcome to the comprehensive documentation for Hyper2KVM, a production-ready VM migration toolkit designed for seamless hypervisor transitions.

---

## Quick Navigation

### 🚀 Getting Started
- **[Installation Guide](getting-started/01-Installation.md)** - Install Hyper2KVM in 5 minutes
- **[Quick Start Tutorial](getting-started/00-Quickstart.md)** - Your first migration in 10 minutes
- **[Architecture Overview](reference/architecture.md)** - Understand how Hyper2KVM works

### 📚 Tutorials
- **[Beginner Tutorial](tutorials/01-beginner-migration.md)** - Step-by-step first migration
- **[Intermediate Tutorial](tutorials/02-intermediate-workflows.md)** - Batch migrations and automation
- **[Advanced Tutorial](tutorials/03-advanced-features.md)** - Live migration, DR testing, database-aware migrations
- **[Enterprise Tutorial](tutorials/04-enterprise-deployment.md)** - Production deployment strategies

### 🍳 Migration Recipes
- **[Common Scenarios](recipes/01-common-scenarios.md)** - Frequently encountered migration patterns
- **[OS-Specific Recipes](recipes/02-os-specific.md)** - Windows, Linux, BSD migration examples
- **[Application Recipes](recipes/03-application-specific.md)** - Database servers, web servers, domain controllers
- **[Troubleshooting Recipes](recipes/04-troubleshooting.md)** - Common issues and solutions

### 📖 API Reference
- **[VMCraft API](api/vmcraft-api.md)** - Complete guest filesystem manipulation API (480+ methods)
- **[CLI Reference](guides/cli/reference.md)** - Command-line interface and YAML configuration

### 🛠️ User Guides
- **[CLI Reference](guides/cli/reference.md)** - Complete command-line reference
- **[Batch Migration Guide](guides/migration/batch-features.md)** - Migrating multiple VMs
- **[Conversion Directory Configuration](guides/configuration/conversion-directory.md)** - Configure VMDK conversion temporary directory
- **[Security Best Practices](guides/security-best-practices.md)** - Secure migration workflows
- **[Troubleshooting Guide](guides/troubleshooting.md)** - Diagnose and fix issues
- **[TUI Dashboard](guides/tui/dashboard.md)** - Terminal user interface guide

### 🔧 Feature Documentation
- **[VMCraft Complete Guide](features/vmcraft/complete-guide.md)** - Native VM manipulation engine
- **[XFS UUID Regeneration](features/xfs-uuid-regeneration.md)** - Fix cloned VMware VMs with duplicate UUIDs
- **[fstab Stabilization](features/fstab-stabilization.md)** - Automatic fstab repair and device conversion
- **[Enhanced Chroot](features/enhanced-chroot.md)** - Advanced filesystem access
- **[Windows Support](os-support/windows/guide.md)** - VirtIO injection and registry modification
- **[Cloud-Init Injection](features/cloud-init.md)** - Automated cloud configuration

### 🖥️ OS-Specific Documentation
- **[Windows Migration](os-support/windows/guide.md)** - Windows VM migration guide
- **[RHEL/CentOS Migration](os-support/rhel-10.md)** - Red Hat Enterprise Linux
- **[Ubuntu Migration](os-support/ubuntu-2404.md)** - Ubuntu and Debian-based systems
- **[SUSE Migration](os-support/suse.md)** - openSUSE and SLES
- **[Photon OS Migration](os-support/photon-os.md)** - VMware Photon OS

### 👥 Development
- **[Contributing Guide](development/contributing.md)** - Contribute to Hyper2KVM
- **[Architecture Documentation](development/architecture.md)** - Internal architecture
- **[Testing Guide](development/testing-guide.md)** - Running and writing tests
- **[Building from Source](development/building.md)** - Build Hyper2KVM locally

### 📊 Project Information
- **[Project Status](project/PROJECT_STATUS.md)** - Current development status
- **[Priority Features](project/Priority-1-Features.md)** - Roadmap and priorities
- **[Ecosystem](project/ECOSYSTEM.md)** - Related tools and integrations

---

## Feature Highlights

### 🎯 Production-Ready Features

| Feature | Status | Documentation |
|---------|--------|---------------|
| **VMCraft (480+ APIs)** | ✅ Production | [Complete Guide](features/vmcraft/complete-guide.md) |
| **Local VMDK Migration** | ✅ Production | [Quick Start](getting-started/02-Quick-Start.md) |
| **Remote ESXi Fetch** | ✅ Production | [SSH Fetch Guide](guides/migration/remote-fetch.md) |
| **OVA/OVF Extraction** | ✅ Production | [OVA Guide](guides/migration/ova-ovf.md) |
| **VHD/AMI Import** | ✅ Production | [VHD Guide](guides/migration/vhd-ami.md) |
| **Live Fix (SSH)** | ✅ Production | [Live Fix Guide](guides/migration/live-fix.md) |
| **Batch Processing** | ✅ Production | [Batch Guide](guides/migration/batch-features.md) |
| **Windows Support** | ✅ Production | [Windows Guide](os-support/windows/guide.md) |
| **vSphere Operations** | ✅ Production | [vSphere Guide](guides/migration/vsphere.md) |
| **Post-Migration Testing** | ✅ Production | [Testing Guide](guides/testing.md) |

### 🏆 Key Capabilities

- ✅ **480+ VMCraft APIs** - Native Python VM manipulation engine
- ✅ **Multiple Input Formats** - VMDK, OVA, OVF, VHD, AMI, Azure VHD
- ✅ **Automated Fixes** - Bootloader (GRUB), fstab stabilization, initramfs regeneration
- ✅ **XFS UUID Regeneration** - Fix cloned VMware VMs with duplicate UUIDs (automatic fstab rebuild)
- ✅ **Multi-OS Support** - Windows (7-12, Server 2012-2025), Linux (RHEL, Ubuntu, SUSE, Photon), BSD
- ✅ **Remote Operations** - SSH-based fetch from ESXi, live-fix without downtime
- ✅ **Windows VirtIO** - Automatic driver injection and registry modification
- ✅ **Batch Processing** - Parallel multi-VM migrations with JSON manifests
- ✅ **Flexible Output** - qcow2, raw, VDI formats with compression levels
- ✅ **Post-Migration Testing** - Libvirt/QEMU smoke tests with configurable timeout
- ✅ **Cloud Integration** - Cloud-init injection, vSphere/Azure operations

---

## Common Use Cases

### Scenario 1: Local VMDK Migration
**Goal**: Migrate a VMware VMDK to KVM qcow2

```yaml
# migration.yaml
command: local
vmdk: /vms/windows-server.vmdk
output_dir: /vms/converted
to_output: windows-server.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
compress: true
libvirt_test: true
```

```bash
# Install and run
pip install "hyper2kvm[full]"
hyper2kvm --config migration.yaml

# Import to libvirt
virsh define /vms/converted/windows-server.xml
virsh start windows-server
```

**Documentation**: [Beginner Tutorial](tutorials/01-beginner-migration.md) | [Windows Guide](os-support/windows/guide.md)

---

### Scenario 2: Remote ESXi Fetch
**Goal**: Fetch and migrate VM directly from ESXi host

```yaml
# fetch.yaml
command: fetch-and-fix
host: 192.168.1.100
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
output_dir: /vms/migrated
to_output: vm.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
```

```bash
hyper2kvm --config fetch.yaml
```

**Documentation**: [Remote Fetch Guide](guides/migration/remote-fetch.md)

---

### Scenario 3: Batch Migration
**Goal**: Migrate multiple VMs in parallel

```yaml
# batch.yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
batch_continue_on_error: true
output_dir: /vms/batch
```

```json
// migrations.json
{
  "migrations": [
    {"vmdk": "/vms/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vms/vm2.vmdk", "to_output": "vm2.qcow2"},
    {"vmdk": "/vms/vm3.vmdk", "to_output": "vm3.qcow2"}
  ]
}
```

```bash
hyper2kvm --config batch.yaml
```

**Documentation**: [Batch Migration Guide](guides/migration/batch-features.md)

---

## Quick Reference Cards

### Essential Commands

| Command | Description |
|---------|-------------|
| `hyper2kvm --config <yaml>` | Execute migration from YAML config (recommended) |
| `hyper2kvm --cmd local` | Local VMDK/disk migration (alias: `migrate`) |
| `hyper2kvm --cmd fetch-and-fix` | Remote ESXi fetch via SSH |
| `hyper2kvm --cmd ova` | OVA file extraction |
| `hyper2kvm --cmd ovf` | OVF file extraction |
| `hyper2kvm --cmd vhd` | VHD file import |
| `hyper2kvm --cmd ami` | AMI/cloud tarball extraction |
| `hyper2kvm --cmd raw` | Raw disk image/tarball import |
| `hyper2kvm --cmd live-fix` | SSH-based live fixing |
| `hyper2kvm --cmd libvirt-xml` | Parse libvirt XML to manifest |
| `hyper2kvm --help` | Show full command reference |

### Common Workflows

**Standard Migration**:
```
1. Create YAML config file
2. Run: hyper2kvm --config migration.yaml
3. Automatic fstab/bootloader fixing
4. Optional: libvirt/QEMU testing
5. Import to libvirt with virsh
```

**Remote Fetch**:
```
1. Configure SSH access to ESXi
2. Create fetch-and-fix YAML config
3. Final switchover (<5s downtime)
4. Validate target
5. Cutover production traffic
```

**DR Testing**:
```
1. Restore from backup
2. Convert to KVM format
3. Apply migration fixes
4. Run DR validation
5. Generate test report
```

---

## Support and Resources

### Getting Help
- **Documentation**: You're here! Browse by topic above
- **Troubleshooting**: [Troubleshooting Guide](guides/troubleshooting.md)
- **Recipes**: [Migration Recipes](recipes/01-common-scenarios.md)
- **Issues**: [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)

### Learning Path

**Beginner** (0-2 hours):
1. [Installation](getting-started/01-Installation.md)
2. [Quick Start](getting-started/00-Quickstart.md)
3. [Beginner Tutorial](tutorials/01-beginner-migration.md)

**Intermediate** (2-8 hours):
1. [Intermediate Workflows](tutorials/02-intermediate-workflows.md)
2. [Batch Migration](guides/migration/batch-features.md)
3. [OS-Specific Guides](os-support/windows/guide.md)

**Advanced** (8+ hours):
1. [Advanced Features](tutorials/03-advanced-features.md)
2. [Live Migration](features/live-migration.md)
3. [API Reference](api/vmcraft-api.md)

**Enterprise** (Full deployment):
1. [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
2. [Security Best Practices](guides/security-best-practices.md)
3. [Compliance & Audit](features/compliance-audit.md)

---

## Version Compatibility

| Hyper2KVM Version | Python | Supported Hypervisors | Status |
|-------------------|--------|----------------------|--------|
| **1.0.0+** | 3.10+ | Hyper-V, VMware, KVM, AWS, Azure, GCP | ✅ Current |
| **0.9.x** | 3.9+ | Hyper-V, VMware, KVM | 🔄 Legacy |
| **0.8.x** | 3.8+ | Hyper-V, VMware | ⚠️ Deprecated |

---

## Contributing

We welcome contributions! See:
- [Contributing Guide](development/contributing.md)
- [Development Setup](development/building.md)
- [Testing Guide](development/testing-guide.md)

---

## License

Hyper2KVM is licensed under LGPL-3.0-or-later. See LICENSE file for details.

---

**Last Updated**: January 2026
**Documentation Version**: 1.0.0
