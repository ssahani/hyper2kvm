# 📚 hyper2kvm Documentation Index

> **Complete migration toolkit: VMware/Hyper-V → KVM/QEMU** \
> Built for the Enterprise Linux ecosystem (Fedora, RHEL, CentOS Stream)

---

## 🎯 Quick Navigation

### 🚀 Getting Started
- **[📦 02-Installation](02-Installation.md)** - Install hyper2kvm on Fedora, RHEL, Ubuntu, macOS, Windows
- **[🚀 03-Quick-Start](03-Quick-Start.md)** - 5-minute quick start guide
- **[⚙️ 04-CLI-Reference](04-CLI-Reference.md)** - Complete command-line reference
- **[📝 05-YAML-Examples](05-YAML-Examples.md)** - Configuration file examples

### 🏗️ Architecture & Design
- **[🏗️ 01-Architecture](01-Architecture.md)** - System architecture and design
- **[🎨 07-vSphere-Design](07-vSphere-Design.md)** - vSphere integration architecture

### 👨‍🍳 Recipes & Workflows
- **[📖 06-Cookbook](06-Cookbook.md)** - Common migration recipes
- **[☁️ 30-vSphere-V2V](30-vSphere-V2V.md)** - vSphere to KVM workflows

---

## 🪟 Windows Migration

Windows VMs require special handling due to driver dependencies and registry configuration.

| Guide | Description |
|-------|-------------|
| **[🪟 10-Windows-Guide](10-Windows-Guide.md)** | Complete Windows migration guide |
| **[🔄 11-Windows-Boot-Cycle](11-Windows-Boot-Cycle.md)** | Understanding Windows boot on KVM |
| **[🔧 12-Windows-Troubleshooting](12-Windows-Troubleshooting.md)** | Windows migration troubleshooting |
| **[🌐 13-Windows-Networking](13-Windows-Networking.md)** | Windows networking & VirtIO drivers |

### Windows Features
- ✅ **VirtIO driver injection** - Offline injection into offline Windows VMs
- ✅ **Registry modification** - BOOT_START service configuration
- ✅ **Two-phase boot** - Bootstrap with SATA, finalize with VirtIO
- ✅ **Windows 10 & 11** - Full support including UEFI, Secure Boot, TPM 2.0

---

## 🐧 Linux Distributions

Linux migrations are generally more straightforward, but each distro has specific requirements.

| Distribution | Guide | Key Features |
|--------------|-------|--------------|
| **🎩 RHEL / Fedora / CentOS** | [20-RHEL-10](20-RHEL-10.md) | Dracut, SELinux, NetworkManager |
| **🌟 VMware Photon OS** | [21-Photon-OS](21-Photon-OS.md) | systemd-networkd, RPM-based |
| **🐧 Ubuntu / Debian** | [22-Ubuntu-24.04](22-Ubuntu-24.04.md) | update-initramfs, netplan |
| **🦎 openSUSE / SUSE** | [23-SUSE](23-SUSE.md) | YaST, zypper, SUSE-specific |

### Linux Migration Features
- ✅ **Automatic initramfs regeneration** - Dracut or update-initramfs
- ✅ **UUID-based fstab** - Stable device references
- ✅ **GRUB root= fixing** - Kernel parameters
- ✅ **Network config migration** - NetworkManager, netplan, systemd-networkd

---

## ☁️ vSphere Integration

Migrate VMs directly from VMware vCenter/vSphere.

### Migration Paths

```mermaid
graph LR
    A[vSphere VM] --> B{Export Method}
    B -->|virt-v2v| C[Direct Conversion]
    B -->|govc| D[Download VMDK]
    B -->|OVF Tool| E[Export OVA/OVF]
    C --> F[KVM QCOW2]
    D --> F
    E --> F
```bash

### Export Methods

| Method | Speed | Use Case | Guide |
|--------|-------|----------|-------|
| **virt-v2v + VDDK** | ⚡ Fast | Production, large VMs | [30-vSphere-V2V](30-vSphere-V2V.md) |
| **govc download** | 🐢 Slow | Small VMs, testing | [07-vSphere-Design](07-vSphere-Design.md) |
| **OVF Tool** | ⚖️ Medium | OVA/OVF export | [30-vSphere-V2V](30-vSphere-V2V.md#ovftool) |

---

## 🔧 Configuration

### Configuration File Formats

hyper2kvm supports both YAML and JSON configuration files.

**YAML Example:**
```yaml
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: /output
out_format: qcow2
compress: true
fstab_mode: stabilize-all
regen_initramfs: true
```bash

**JSON Example:**
```json
{
  "cmd": "local",
  "vmdk": "/path/to/vm.vmdk",
  "output_dir": "/output",
  "out_format": "qcow2",
  "compress": true
}
```bash

### Configuration Examples

See the `test-confs/` directory for 30+ production-ready configuration examples:
- Local VMDK conversions (01-05)
- vSphere downloads (10-11)
- virt-v2v exports (20-24)
- OVFTool exports (30-31)
- LibVirt XML templates (60-66)

---

## ⚠️ Troubleshooting

### Common Issues

| Issue | Solution | Guide |
|-------|----------|-------|
| **Boot failure after conversion** | Check initramfs, fstab, GRUB | [90-Failure-Modes](90-Failure-Modes.md#boot-failures) |
| **Network not working** | Verify network config migration | [90-Failure-Modes](90-Failure-Modes.md#network-issues) |
| **Windows BSOD 0x7B** | VirtIO driver injection failed | [12-Windows-Troubleshooting](12-Windows-Troubleshooting.md) |
| **Permission denied errors** | Run with appropriate privileges | [90-Failure-Modes](90-Failure-Modes.md#permissions) |

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
hyper2kvm --config config.yaml --verbose 2 local
```bash

Generate detailed report:

```yaml
verbose: 2
log_file: /tmp/hyper2kvm.log
report: /tmp/hyper2kvm-report.md
```bash

---

## 📖 Complete Documentation

### Core Documentation
1. **[🏗️ Architecture](01-Architecture.md)** - System design, components, data flow
2. **[📦 Installation](02-Installation.md)** - Install on Fedora, RHEL, Ubuntu, Arch, macOS, Windows
3. **[🚀 Quick Start](03-Quick-Start.md)** - Get started in 5 minutes
4. **[⚙️ CLI Reference](04-CLI-Reference.md)** - Complete command-line documentation
5. **[📝 YAML Examples](05-YAML-Examples.md)** - Configuration file reference
6. **[👨‍🍳 Cookbook](06-Cookbook.md)** - Common migration recipes
7. **[🎨 vSphere Design](07-vSphere-Design.md)** - vSphere integration architecture

### Windows Documentation
10. **[🪟 Windows Guide](10-Windows-Guide.md)** - Complete Windows migration guide
11. **[🔄 Windows Boot Cycle](11-Windows-Boot-Cycle.md)** - Windows boot process on KVM
12. **[🔧 Windows Troubleshooting](12-Windows-Troubleshooting.md)** - Fix Windows migration issues
13. **[🌐 Windows Networking](13-Windows-Networking.md)** - Windows network drivers & configuration

### Linux Distribution Guides
20. **[🎩 RHEL 10](20-RHEL-10.md)** - Red Hat Enterprise Linux migration
21. **[🌟 Photon OS](21-Photon-OS.md)** - VMware Photon OS migration
22. **[🐧 Ubuntu 24.04](22-Ubuntu-24.04.md)** - Ubuntu/Debian migration
23. **[🦎 SUSE](23-SUSE.md)** - openSUSE/SUSE Linux migration

### Advanced Topics
30. **[☁️ vSphere V2V](30-vSphere-V2V.md)** - vSphere to KVM using virt-v2v

### Troubleshooting
90. **[⚠️ Failure Modes](90-Failure-Modes.md)** - Troubleshooting guide

---

## 🎓 Learning Path

### Beginner Path
1. Start with **[Quick Start](03-Quick-Start.md)**
2. Read **[Installation](02-Installation.md)**
3. Try a simple local conversion
4. Review **[Cookbook](06-Cookbook.md)** for common recipes

### Intermediate Path
1. Understand **[Architecture](01-Architecture.md)**
2. Explore **[YAML Examples](05-YAML-Examples.md)**
3. Try **[vSphere integration](07-vSphere-Design.md)**
4. Review OS-specific guides (RHEL, Ubuntu, Windows)

### Advanced Path
1. Deep dive into **[vSphere V2V](30-vSphere-V2V.md)**
2. Master **[Windows migrations](10-Windows-Guide.md)**
3. Handle **[Failure Modes](90-Failure-Modes.md)**
4. Contribute to the project!

---

## 🔗 External Resources

### Related Projects
- **[libguestfs](https://libguestfs.org/)** - Offline VM inspection and modification
- **[virt-v2v](https://libguestfs.org/virt-v2v.1.html)** - VM conversion tool
- **[govc](https://github.com/vmware/govmomi/tree/master/govc)** - vSphere CLI
- **[KVM](https://www.linux-kvm.org/)** - Linux virtualization
- **[QEMU](https://www.qemu.org/)** - Machine emulator & virtualizer

### VMware Resources
- **[VDDK Documentation](https://developer.vmware.com/web/sdk/vddk)** - Virtual Disk Development Kit
- **[OVF Tool](https://developer.vmware.com/web/tool/ovf-tool)** - OVF/OVA import/export
- **[vSphere API](https://developer.vmware.com/apis/vsphere-automation/)** - vSphere automation

---

## 📊 Migration Decision Matrix

| Source Platform | Destination | Best Method | Complexity | Guide |
|----------------|-------------|-------------|------------|-------|
| vSphere → | KVM | virt-v2v + VDDK | ⭐⭐⭐ | [30-vSphere-V2V](30-vSphere-V2V.md) |
| Local VMDK (Windows) → | KVM | local + VirtIO inject | ⭐⭐⭐⭐ | [10-Windows-Guide](10-Windows-Guide.md) |
| Local VMDK (Linux) → | KVM | local + offline fix | ⭐⭐ | [03-Quick-Start](03-Quick-Start.md) |
| Hyper-V VHD → | KVM | local (WIP) | ⭐⭐⭐ | N/A |
| OVA/OVF → | KVM | extract + local | ⭐⭐ | [06-Cookbook](06-Cookbook.md#ova) |

**Complexity Legend:**
- ⭐ - Easy
- ⭐⭐ - Medium
- ⭐⭐⭐ - Advanced
- ⭐⭐⭐⭐ - Expert

---

## 📝 Contributing

Found an issue or want to improve the documentation?

1. Fork the repository
2. Make your changes
3. Submit a pull request

See the main [README](../README.md) for contribution guidelines.

---

## 📧 Support

- **Issues:** [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)
- **Discussions:** [GitHub Discussions](https://github.com/ssahani/hyper2kvm/discussions)
- **Email:** ssahani@gmail.com

---

**Last Updated:** 2026-01-15 \
**Documentation Version:** 1.0 \
**Maintained by:** Susant Sahani <ssahani@gmail.com>

---

## 🏆 Featured Documentation

### Most Popular Guides
1. **[🚀 Quick Start](03-Quick-Start.md)** - Start here!
2. **[🪟 Windows Guide](10-Windows-Guide.md)** - Windows migrations
3. **[☁️ vSphere V2V](30-vSphere-V2V.md)** - vSphere integration
4. **[⚠️ Failure Modes](90-Failure-Modes.md)** - Troubleshooting

### Recently Updated
- **[20-RHEL-10](20-RHEL-10.md)** - Updated for RHEL 10 Beta
- **[02-Installation](02-Installation.md)** - Added macOS & Windows WSL2
- **[01-Architecture](01-Architecture.md)** - Complete rewrite

---

Happy migrating! 🚀
