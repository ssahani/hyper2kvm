# hyper2kvm Documentation

Complete documentation for the hyper2kvm VM migration toolkit.

## Table of Contents

### Getting Started
- **[Quick Start Guide](QUICKSTART.md)** - Get running in 5 minutes
- **[Installation](INSTALL.md)** - Detailed installation instructions
- **[CLI Reference](CLI_REFERENCE.md)** - Complete command-line reference

### Core Concepts
- **[Architecture](ARCHITECTURE.md)** - System design and components
- **[YAML Configuration](YAML-EXAMPLES.md)** - Configuration file reference

### Platform-Specific Guides
- **[Windows Migration](WINDOWS.md)** - Windows VM conversion guide
- **[PhotonOS](PHOTONOS.md)** - VMware PhotonOS migrations
- **[RHEL 10](RHEL10.md)** - Red Hat Enterprise Linux 10
- **[Ubuntu 24.04](ubuntu-24.04.03.md)** - Ubuntu migrations
- **[SUSE](SUSE-TEST.MD)** - SUSE Linux conversions

### Advanced Topics
- **[vSphere Integration](VSPEHERE-V2V-EXPORT.md)** - vSphere/ESXi export
- **[vSphere Design](hyper2kvm-vsphere-design.md)** - vSphere architecture
- **[Cookbook](cookbook.md)** - Recipes and examples

### Troubleshooting
- **[Failure Modes](FAILURE_MODES.md)** - Common problems and solutions
- **[Windows Boot Cycle](windows-boot-cycle.md)** - Windows boot troubleshooting
- **[Windows Network & Drivers](windows-network-and-drivers.md)** - Driver issues
- **[Windows 10 Troubleshooting](windows-10-troubleshoot.md)** - Windows 10 specific

---

## Quick Links

### For New Users
1. [Quick Start](QUICKSTART.md) - Start here!
2. [Examples](../examples/README.md) - 30+ working examples
3. [Installation](INSTALL.md) - System setup

### For Migration Projects
1. [CLI Reference](CLI_REFERENCE.md) - All command options
2. [YAML Examples](YAML-EXAMPLES.md) - Configuration templates
3. [Cookbook](cookbook.md) - Common scenarios

### For Troubleshooting
1. [Failure Modes](FAILURE_MODES.md) - Error reference
2. [Windows Guide](WINDOWS.md) - Windows issues
3. [Architecture](ARCHITECTURE.md) - Understanding internals

---

## Documentation by Task

### Converting a Linux VM
1. Read [Quick Start](QUICKSTART.md) → "Linux VM" section
2. Check [Examples](../examples/README.md) → "Local Conversions"
3. Review [CLI Reference](CLI_REFERENCE.md) for options

### Converting a Windows VM
1. Read [Windows Migration](WINDOWS.md) - Complete guide
2. Download VirtIO drivers (see Windows guide)
3. Use [Examples](../examples/README.md) → "Windows with VirtIO"
4. If issues: [Windows Troubleshooting](windows-10-troubleshoot.md)

### Migrating from ESXi/vSphere
1. Read [vSphere Integration](VSPEHERE-V2V-EXPORT.md)
2. Use [Examples](../examples/README.md) → "Fetch from ESXi"
3. Check [vSphere Design](hyper2kvm-vsphere-design.md) for details

### Batch Migration of Many VMs
1. Read [YAML Configuration](YAML-EXAMPLES.md)
2. Use [Examples](../examples/README.md) → "Batch Operations"
3. Check [Cookbook](cookbook.md) for batch recipes

### Troubleshooting Boot Failures
1. Check [Failure Modes](FAILURE_MODES.md)
2. For Windows: [Windows Boot Cycle](windows-boot-cycle.md)
3. Enable debug: `--log-level DEBUG`
4. Generate report: `--report migration-report.md`

---

## Documentation Structure

```
docs/
├── README.md                          # This file - documentation index
├── QUICKSTART.md                      # 5-minute getting started guide
├── INSTALL.md                         # Detailed installation
├── CLI_REFERENCE.md                   # Command-line reference
├── ARCHITECTURE.md                    # System design
├── YAML-EXAMPLES.md                   # Configuration examples
├── cookbook.md                        # Recipes and howtos
├── FAILURE_MODES.md                   # Troubleshooting guide
│
├── Windows-Specific/
│   ├── WINDOWS.md                     # Windows migration guide
│   ├── windows-boot-cycle.md          # Boot troubleshooting
│   ├── windows-network-and-drivers.md # Driver issues
│   └── windows-10-troubleshoot.md     # Windows 10 specific
│
├── Platform-Specific/
│   ├── PHOTONOS.md                    # VMware PhotonOS
│   ├── RHEL10.md                      # RHEL 10
│   ├── ubuntu-24.04.03.md             # Ubuntu 24.04
│   └── SUSE-TEST.MD                   # SUSE Linux
│
└── Integration/
    ├── VSPEHERE-V2V-EXPORT.md         # vSphere export
    └── hyper2kvm-vsphere-design.md    # vSphere architecture
```

---

## Common Scenarios

### Scenario: First-Time User

**Goal:** Convert a single Linux VMDK to QCOW2

**Path:**
1. [Quick Start](QUICKSTART.md) - Installation & first conversion
2. [Examples](../examples/README.md) - local-linux-basic.json
3. Success! Now try more [examples](../examples/)

### Scenario: Production Migration Project

**Goal:** Migrate 100+ VMs from VMware to KVM

**Path:**
1. [Architecture](ARCHITECTURE.md) - Understand the system
2. [vSphere Integration](VSPEHERE-V2V-EXPORT.md) - Setup vSphere export
3. [YAML Configuration](YAML-EXAMPLES.md) - Batch configuration
4. [Cookbook](cookbook.md) - Batch migration recipes
5. [Failure Modes](FAILURE_MODES.md) - Handle errors

### Scenario: Windows VM Won't Boot

**Goal:** Fix boot issues after migration

**Path:**
1. [Windows Boot Cycle](windows-boot-cycle.md) - Understand Windows boot
2. [Windows Troubleshooting](windows-10-troubleshoot.md) - Common fixes
3. [Windows Network & Drivers](windows-network-and-drivers.md) - Driver issues
4. [Failure Modes](FAILURE_MODES.md) - General troubleshooting

### Scenario: Enterprise Automation

**Goal:** Automate migrations with CI/CD

**Path:**
1. [Architecture](ARCHITECTURE.md) - System components
2. [YAML Configuration](YAML-EXAMPLES.md) - Config file format
3. [CLI Reference](CLI_REFERENCE.md) - All options
4. See `.github/workflows/` for CI/CD examples

---

## External Resources

### Required Tools
- [libguestfs](https://libguestfs.org/) - Guest filesystem access
- [QEMU](https://www.qemu.org/) - Virtualization and disk tools
- [libvirt](https://libvirt.org/) - Virtualization API

### Optional Tools
- [virt-v2v](https://libguestfs.org/virt-v2v.1.html) - Alternative converter
- [VirtIO Drivers](https://docs.fedoraproject.org/en-US/quick-docs/creating-windows-virtual-machines-using-virtio-drivers/) - Windows drivers

### References
- [QCOW2 Format](https://www.qemu.org/docs/master/system/images.html#qcow2) - Disk image format
- [VMDK Specification](https://www.vmware.com/support/developer/vddk/) - VMware disk format

---

## Contributing to Documentation

Found an error or want to improve docs?

1. **Fix typos/errors:**
   - Edit the file directly
   - Submit a pull request

2. **Add new guides:**
   - Create a new .md file
   - Add it to this index
   - Submit a pull request

3. **Improve examples:**
   - Add to `examples/` directory
   - Update `examples/README.md`
   - Test thoroughly

### Documentation Style Guide

- Use clear, concise language
- Include working code examples
- Test all commands before documenting
- Use markdown headers consistently
- Link to related documentation
- Include troubleshooting sections

---

## Getting Help

- **GitHub Issues:** https://github.com/hyper2kvm/hyper2kvm/issues
- **Discussions:** https://github.com/hyper2kvm/hyper2kvm/discussions
- **Examples:** See `examples/` directory
- **Source Code:** Browse `hyper2kvm/` for implementation details

---

## Version History

See [CHANGELOG.md](../CHANGELOG.md) for version history and release notes.

---

**Happy migrating! 🚀**

For quick help: `python -m hyper2kvm --help`
