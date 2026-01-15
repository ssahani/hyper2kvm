# 📁 hyper2kvm Configuration Examples

This directory contains production-ready configuration examples for various migration scenarios.

## 📑 Table of Contents

- [Local VMDK Conversions (01-05)](#local-vmdk-conversions)
- [vSphere Download-Only (10-11)](#vsphere-download-only)
- [vSphere virt-v2v Export (20-24)](#vsphere-virt-v2v-export)
- [vSphere OVFTool Export (30-31)](#vsphere-ovftool-export)
- [vSphere VDDK Operations (40-41)](#vsphere-vddk-operations)
- [Photon OS Variations (50-53)](#photon-os-variations)
- [LibVirt XML Templates (60-66)](#libvirt-xml-templates)
- [Ubuntu Configurations (70)](#ubuntu-configurations)
- [Windows Drivers (80)](#windows-drivers)
- [Complete Examples (90-92)](#complete-examples)

---

## 🖥️ Local VMDK Conversions

Convert local VMDK files to QCOW2 format with offline fixes.

### 01-local-windows-11-vmdk.yaml
**Windows 11 VMDK → QCOW2 with VirtIO**
- ✅ Offline VirtIO driver injection
- ✅ Registry modification for VirtIO storage
- ✅ QCOW2 compression
- ✅ Checksum generation

```bash
hyper2kvm --config test-confs/01-local-windows-11-vmdk.yaml local
```

### 01-local-windows-10-vmdk.yaml
**Windows 10 VMDK → QCOW2 with VirtIO**
- ✅ Offline VirtIO driver injection
- ✅ SATA bootstrap mode support
- ✅ Registry fixes

```bash
hyper2kvm --config test-confs/01-local-windows-10-vmdk.yaml local
```

### 02-local-rhel-10-vmdk.yaml
**RHEL 10 VMDK → QCOW2**
- ✅ UUID-based fstab stabilization
- ✅ GRUB root= fixing
- ✅ Dracut initramfs regeneration
- ✅ SELinux compatibility

```bash
hyper2kvm --config test-confs/02-local-rhel-10-vmdk.yaml local
```

### 03-local-ubuntu-22-vmdk.yaml
**Ubuntu 22.04 LTS VMDK → QCOW2**
- ✅ UUID-based fstab stabilization
- ✅ update-initramfs regeneration
- ✅ Netplan/systemd compatibility

```bash
hyper2kvm --config test-confs/03-local-ubuntu-22-vmdk.yaml local
```

### 04-local-photon-os-vmdk.yaml
**VMware Photon OS VMDK → QCOW2**
- ✅ Dracut initramfs regeneration
- ✅ systemd-networkd compatibility

```bash
hyper2kvm --config test-confs/04-local-photon-os-vmdk.yaml local
```

---

## ☁️ vSphere Download-Only

Download VM files from vCenter without conversion.

### 10-vsphere-download-only.yaml
**Basic vSphere Download**
- ✅ Concurrent downloads (4 parallel)
- ✅ Selective file patterns (exclude logs/locks)
- ✅ Async HTTP for large files

```bash
export VC_PASSWORD='your-vcenter-password'
hyper2kvm --config test-confs/10-vsphere-download-only.yaml vsphere
```

### 11-vsphere-govc-rhel-10-download.yaml
**Download using govc/govmomi**
- ✅ govc-based download (alternative to pyvmomi)
- ✅ RHEL 10.1 specific configuration

```bash
export VC_PASSWORD='your-vcenter-password'
hyper2kvm --config test-confs/11-vsphere-govc-rhel-10-download.yaml vsphere
```

---

## ☁️ vSphere virt-v2v Export

Export VMs from vSphere using virt-v2v.

### 20-vsphere-v2v-rhel-10-export.yaml
**Full virt-v2v Export with VDDK**
- ✅ VDDK transport (fast, efficient)
- ✅ Complete OS conversion
- ✅ QCOW2 output

```bash
export VC_PASSWORD='your-vcenter-password'
hyper2kvm --config test-confs/20-vsphere-v2v-rhel-10-export.yaml vsphere
```

### 21-vsphere-v2v-rhel-10-download.yaml
**virt-v2v Download-Only Mode**

### 22-vsphere-v2v-rhel-10-ova.yaml
**Export to OVA Format**

### 23-vsphere-v2v-rhel-10-ovf.yaml
**Export to OVF Format**

### 24-vsphere-v2v-rhel-10-nfc.yaml
**Export using NFC Transport**

---

## 📦 vSphere OVFTool Export

Export VMs using VMware OVF Tool.

### 30-vsphere-ovftool-rhel-10-ova.yaml
**OVA Export via OVFTool**

### 31-vsphere-ovftool-rhel-10-ovfdir.yaml
**OVF Directory Export via OVFTool**

---

## 💾 vSphere VDDK Operations

Direct disk operations using VMware VDDK.

### 40-vsphere-vddk-download-disk.yaml
**Download VM Disks using VDDK**
- ✅ Fast block-level transfers
- ✅ Incremental copy support

### 41-vsphere-pyvmomi-vddk.yaml
**Force pyvmomi with VDDK**
- ✅ Python-based vSphere access
- ✅ VDDK library integration

---

## 🌟 Photon OS Variations

VMware Photon OS specific configurations.

### 50-photon-os-libvirt.yaml
**Photon OS → LibVirt**

### 51-photon-os-ova.yaml
**Photon OS → OVA**

### 52-photon-os-ami.yaml
**Photon OS → Amazon AMI**

### 53-photon-os-azure-vhd.yaml
**Photon OS → Azure VHD**

---

## 📄 LibVirt XML Templates

Domain XML templates for converted VMs.

### 60-libvirt-guest-uefi.xml
**Generic UEFI Guest Template**

### 61-libvirt-rhel-10-fixed.xml
**RHEL 10 Post-Conversion Template**

### 62-libvirt-windows-10-fixed.xml
**Windows 10 Post-Conversion Template**

### 63-libvirt-windows-10-sata-uefi.xml
**Windows 10 SATA + UEFI Template**

### 64-libvirt-windows-10-fixed-sata.xml
**Windows 10 SATA (Bootstrap Phase)**

### 65-libvirt-windows-10-fixed-virtio.xml
**Windows 10 VirtIO (Final Phase)**

### 66-libvirt-windows-10-test.xml
**Windows 10 Testing Template**

---

## 🐧 Ubuntu Configurations

### 70-ubuntu-libvirt.yaml
**Ubuntu → LibVirt Conversion**

---

## 🪟 Windows Drivers

### 80-windows-drivers-network.yaml
**Windows Network Driver Configuration**
- ✅ VirtIO network drivers
- ✅ Registry configuration

---

## 📚 Complete Examples

### 90-hyper2kvm-full-config.yaml
**Comprehensive Configuration Example (YAML)**
- Shows all available options
- Detailed comments

### 91-hyper2kvm-full-config.json
**Comprehensive Configuration Example (JSON)**
- Same as YAML version in JSON format

### 92-override-nojson.yaml
**YAML Override Example**
- Demonstrates config file merging

---

## 🚀 Quick Start

### 1. Local VMDK Conversion
```bash
# Edit the config to point to your VMDK
vim test-confs/02-local-rhel-10-vmdk.yaml

# Run conversion
hyper2kvm --config test-confs/02-local-rhel-10-vmdk.yaml local
```

### 2. vSphere Download
```bash
# Set vCenter password
export VC_PASSWORD='your-password'

# Download VM files
hyper2kvm --config test-confs/10-vsphere-download-only.yaml vsphere
```

### 3. vSphere to KVM Migration
```bash
# Set vCenter password
export VC_PASSWORD='your-password'

# Export and convert
hyper2kvm --config test-confs/20-vsphere-v2v-rhel-10-export.yaml vsphere
```

---

## 📝 Configuration File Structure

All configuration files follow this structure:

```yaml
# Header with emoji, title, description
# Usage examples
# Feature list
# Requirements

# Main command
cmd: local | vsphere

# Source configuration
vmdk: /path/to/disk.vmdk
# or
vcenter: vcenter.example.com
vm_name: vm-to-convert

# Output configuration
output_dir: /path/to/output
out_format: qcow2
compress: true

# Filesystem fixes
fstab_mode: stabilize-all
regen_initramfs: true
no_grub: false

# Testing (optional)
libvirt_test: false
qemu_test: false
```

---

## 🔧 Customization

To customize a configuration:

1. **Copy the template:**
   ```bash
   cp test-confs/02-local-rhel-10-vmdk.yaml my-config.yaml
   ```

2. **Edit paths and settings:**
   - Update `vmdk:` or `vm_name:`
   - Adjust `output_dir:`
   - Enable/disable features

3. **Run with your config:**
   ```bash
   hyper2kvm --config my-config.yaml local
   ```

---

## 📖 Documentation

For detailed documentation, see:
- **docs/03-Quick-Start.md** - Getting started guide
- **docs/04-CLI-Reference.md** - All CLI options
- **docs/05-YAML-Examples.md** - Configuration examples
- **docs/06-Cookbook.md** - Common recipes

---

## 🆘 Support

If you encounter issues:
1. Check the **docs/90-Failure-Modes.md** guide
2. Enable verbose logging: `verbose: 2`
3. Generate a report: `report: /path/to/report.md`
4. Review logs in your output directory

---

**Last Updated:** 2026-01-15
**Maintained by:** Susant Sahani <ssahani@redhat.com>
