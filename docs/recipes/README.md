# Migration Recipes

Quick, practical recipes for common VM migration scenarios. Copy, customize, and run.

## Quick Navigation

### 📚 Recipe Collections
- **[Common Scenarios](01-common-scenarios.md)** - 10+ real-world migration patterns

### 🔍 Find a Recipe

**By Source Platform:**
- [VMware ESXi](#vmware-esxi-recipes)
- [Hyper-V](#hyper-v-recipes)
- [AWS/Azure/Cloud](#cloud-recipes)

**By Guest OS:**
- [Windows](#windows-recipes)
- [Linux](#linux-recipes)
- [Database Servers](#database-recipes)

**By Complexity:**
- [Simple Migrations](#simple-recipes)
- [Advanced Migrations](#advanced-recipes)

---

## Recipe Format

Each recipe follows this structure:

```yaml
# Recipe Name
# Use Case: Brief description
# Time: Estimated completion time
# Difficulty: ⭐ Easy | ⭐⭐ Moderate | ⭐⭐⭐ Advanced

command: <command-type>
# ... configuration ...
```

---

## Quick Recipes

### Recipe 1: Basic VMware to KVM

**Use Case**: Migrate a single Linux VM from VMware  
**Time**: 10 minutes  
**Difficulty**: ⭐ Easy

```yaml
command: local
vmdk: /vmware/centos9-web.vmdk
output_dir: /kvm/vms
to_output: centos9-web.qcow2
out_format: qcow2

# Automatic fixes
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
compress: true
```

**Run it:**
```bash
sudo hyper2kvm --config recipe1.yaml
```

---

### Recipe 2: Windows Server Migration

**Use Case**: Migrate Windows Server with VirtIO drivers  
**Time**: 15 minutes  
**Difficulty**: ⭐⭐ Moderate

```yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/vms
to_output: windows-server-2019.qcow2
out_format: qcow2

# Windows-specific settings
windows_drivers: true
fstab_mode: stabilize-all
update_grub: true
compress: true
report: /kvm/vms/migration-report.md
```

**Run it:**
```bash
sudo hyper2kvm --config recipe2.yaml
```

---

### Recipe 3: Remote Fetch from ESXi

**Use Case**: Fetch VM directly from ESXi host  
**Time**: 20-30 minutes  
**Difficulty**: ⭐⭐ Moderate

```yaml
command: fetch-and-fix
host: 192.168.1.100
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
output_dir: /kvm/vms
to_output: migrated-vm.qcow2

# Fixes
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
```

**Prerequisites:**
```bash
# Set up SSH key authentication
ssh-copy-id root@192.168.1.100
```

**Run it:**
```bash
sudo hyper2kvm --config recipe3.yaml
```

---

### Recipe 4: Batch Migration (Multiple VMs)

**Use Case**: Migrate 10 VMs in parallel  
**Time**: 1-2 hours  
**Difficulty**: ⭐⭐ Moderate

Create `batch.yaml`:
```yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
batch_continue_on_error: true
output_dir: /kvm/batch
```

Create `migrations.json`:
```json
{
  "migrations": [
    {"vmdk": "/vmware/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vmware/vm2.vmdk", "to_output": "vm2.qcow2"},
    {"vmdk": "/vmware/vm3.vmdk", "to_output": "vm3.qcow2"},
    {"vmdk": "/vmware/vm4.vmdk", "to_output": "vm4.qcow2"},
    {"vmdk": "/vmware/vm5.vmdk", "to_output": "vm5.qcow2"}
  ]
}
```

**Run it:**
```bash
sudo hyper2kvm --config batch.yaml
```

---

### Recipe 5: OVA Import

**Use Case**: Import VMware OVA file  
**Time**: 15 minutes  
**Difficulty**: ⭐ Easy

```yaml
command: ova
ova: /downloads/exported-vm.ova
output_dir: /kvm/vms
to_output: imported-vm.qcow2
out_format: qcow2

# Fixes
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
compress: true
```

**Run it:**
```bash
sudo hyper2kvm --config recipe5.yaml
```

---

### Recipe 6: Database Server Migration

**Use Case**: Migrate PostgreSQL/MySQL server  
**Time**: 30-60 minutes  
**Difficulty**: ⭐⭐⭐ Advanced

```yaml
command: local
vmdk: /vmware/postgres-server.vmdk
output_dir: /kvm/vms
to_output: postgres-server.qcow2
out_format: qcow2

# Database-safe fixes
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true

# Performance settings
compress: false  # Don't compress for database VMs
preallocate: true  # Pre-allocate disk for performance
```

**Additional steps:**
```bash
# 1. Run migration
sudo hyper2kvm --config recipe6.yaml

# 2. Before starting DB, verify data
virsh start postgres-server --paused
# Mount and check database files
virsh resume postgres-server
```

---

### Recipe 7: Windows 10/11 Desktop

**Use Case**: Migrate Windows desktop VM  
**Time**: 15-20 minutes  
**Difficulty**: ⭐⭐ Moderate

```yaml
command: local
vmdk: /vmware/windows11-dev.vmdk
output_dir: /kvm/vms
to_output: windows11-dev.qcow2
out_format: qcow2

# Windows desktop settings
windows_drivers: true
fstab_mode: stabilize-all
compress: true

# Keep snapshots if needed
keep_sparse: true
```

**Run it:**
```bash
sudo hyper2kvm --config recipe7.yaml
```

---

### Recipe 8: Live Fix (No Downtime)

**Use Case**: Fix bootloader without migration  
**Time**: 5-10 minutes  
**Difficulty**: ⭐⭐ Moderate

```yaml
command: live-fix
host: 192.168.1.100
user: root
identity: ~/.ssh/id_rsa

# Fixes to apply
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
```

**Run it:**
```bash
sudo hyper2kvm --config recipe8.yaml
```

---

### Recipe 9: RHEL/CentOS with XFS UUID Fix

**Use Case**: Fix cloned VMware VM with duplicate XFS UUIDs  
**Time**: 10-15 minutes  
**Difficulty**: ⭐⭐ Moderate

```yaml
command: local
vmdk: /vmware/rhel9-clone.vmdk
output_dir: /kvm/vms
to_output: rhel9-fixed.qcow2
out_format: qcow2

# XFS fixes
xfs_regenerate_uuid: true
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
compress: true
```

**Run it:**
```bash
sudo hyper2kvm --config recipe9.yaml
```

---

### Recipe 10: Multi-Disk VM

**Use Case**: VM with multiple disks  
**Time**: 20-30 minutes per disk  
**Difficulty**: ⭐⭐⭐ Advanced

```bash
# Migrate each disk separately
sudo hyper2kvm --config << EOF
command: local
vmdk: /vmware/web-server-disk1.vmdk
output_dir: /kvm/vms
to_output: web-server-disk1.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
