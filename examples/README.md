# hyper2kvm Examples

This directory contains **40+ working examples** for common hyper2kvm migration scenarios, organized by use case, plus **library API examples** for programmatic usage.

## Table of Contents

- [Quick Start](#quick-start)
- [Library API Examples](#library-api-examples)
- [Directory Structure](#directory-structure)
- [Common Scenarios](#common-scenarios)
- [Configuration Format](#configuration-format)
- [Complete Workflows](#complete-workflows)
- [Tips and Best Practices](#tips-and-best-practices)

---

## Quick Start

### 5-Minute Migration

```bash
# 1. Install hyper2kvm (see docs/INSTALL.md)
pip install -e .

# 2. Run a basic conversion
sudo python -m hyper2kvm local \
  --vmdk /path/to/vm.vmdk \
  --flatten \
  --to-output vm-fixed.qcow2 \
  --compress

# 3. Or use a config file
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-basic.yaml
```

### Using Configuration Files

```bash
# Single config
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-basic.yaml

# Merge multiple configs (later overrides earlier)
sudo python -m hyper2kvm \
  --config examples/yaml/00-common/common.yaml \
  --config examples/yaml/10-local/local-linux-basic.yaml

# Override with CLI args
sudo python -m hyper2kvm \
  --config examples/yaml/10-local/local-linux-basic.yaml \
  --compress --to-output /custom/path.qcow2
```

---

## Library API Examples

hyper2kvm can be used as a **Python library** for programmatic control over VM migrations. The following example scripts demonstrate library usage:

### Local Conversion

**`library_local_conversion.py`** - Convert local VMDK to qcow2

```python
from hyper2kvm import DiskProcessor

processor = DiskProcessor()
result = processor.process_disk(
    source_path='/data/vm.vmdk',
    output_path='/data/vm.qcow2',
    flatten=True,
    compress=True
)
```

Usage:
```bash
python library_local_conversion.py /data/vm.vmdk /data/vm.qcow2
```

### vSphere Migration

**`library_vsphere_migration.py`** - Migrate from vCenter/ESXi

```python
from hyper2kvm import VMwareClient, Orchestrator

client = VMwareClient(
    host='vcenter.example.com',
    user='administrator@vsphere.local',
    password=password,
    datacenter='DC1'
)

orchestrator = Orchestrator(vmware_client=client)
result = orchestrator.run(
    vm_name='rhel9-prod',
    output_dir='/var/lib/libvirt/images',
    compress=True
)
```

Usage:
```bash
export VCENTER_PASSWORD='your-password'
python library_vsphere_migration.py vcenter.example.com vm-name
```

### Azure Migration

**`library_azure_migration.py`** - Migrate from Azure

```python
from hyper2kvm import AzureSourceProvider, AzureConfig, Orchestrator

config = AzureConfig(
    subscription_id=subscription_id,
    resource_group='my-rg',
    vm_name='ubuntu-vm-01',
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret
)

provider = AzureSourceProvider(config)
orchestrator = Orchestrator(source_provider=provider)
result = orchestrator.run(output_dir='/var/lib/libvirt/images')
```

Usage:
```bash
export AZURE_SUBSCRIPTION_ID='...'
export AZURE_TENANT_ID='...'
export AZURE_CLIENT_ID='...'
export AZURE_CLIENT_SECRET='...'
python library_azure_migration.py my-rg my-vm
```

### Guest OS Fixing

**`library_guest_fixing.py`** - Apply offline fixes to converted VM

```python
from hyper2kvm import GuestDetector
from hyper2kvm.fixers import OfflineFSFix

detector = GuestDetector()
guest = detector.detect_from_image(image_path)

fixer = OfflineFSFix(image_path=image_path, guest_identity=guest)
fixer.fix_fstab()
fixer.fix_grub()
fixer.fix_network()
fixer.regenerate_initramfs()
```

Usage:
```bash
sudo python library_guest_fixing.py /var/lib/libvirt/images/vm.qcow2
```

### Boot Testing

**`library_boot_testing.py`** - Test VM boots correctly

```python
from hyper2kvm.testers import QemuTest

tester = QemuTest(
    image_path=image_path,
    memory=4096,
    vcpus=2,
    uefi=True,
    timeout=180
)

result = tester.test_boot()
if result.success:
    print(f"✓ Boot successful in {result.boot_time}s")
```

Usage:
```bash
python library_boot_testing.py /var/lib/libvirt/images/vm.qcow2 auto
```

### Complete API Documentation

For complete library API documentation, see **[docs/08-Library-API.md](../docs/08-Library-API.md)**

---

## Directory Structure

```
examples/
├── README.md                    # This file
├── scripts/                     # Shell script examples
│   ├── migrate-single-vm.sh     # Single VM migration script
│   ├── migrate-batch.sh         # Batch migration script
│   └── test-migration.sh        # Test converted VMs
│
└── yaml/                        # YAML configuration examples
    ├── 00-common/               # Reusable base configs
    │   ├── common.yaml          # Standard settings
    │   ├── common-fast.yaml     # Speed-optimized
    │   └── common-strict.yaml   # Maximum validation
    │
    ├── 10-local/                # Local VMDK conversions (14 examples)
    │   ├── local-linux-basic.yaml
    │   ├── local-linux-cloud-init.yaml
    │   ├── local-linux-grow-root.yaml
    │   ├── local-windows-virtio-basic.yaml
    │   └── ... (more)
    │
    ├── 11-batch/                # Batch/multi-VM migrations (2 examples)
    │   ├── batch-local-two-vms.yaml
    │   └── batch-local-many.yaml
    │
    ├── 20-live-fix/             # Live SSH fixes (3 examples)
    │   ├── live-fix-basic.yaml
    │   ├── live-fix-batch.yaml
    │   └── live-fix-dry-run.yaml
    │
    ├── 30-fetch-and-fix/        # Remote fetch (3 examples)
    │   ├── fetch-basic.yaml
    │   ├── fetch-batch-parallel.yaml
    │   └── fetch-full-chain-and-test.yaml
    │
    ├── 40-ova-ovf/              # OVA/OVF handling (2 examples)
    │   ├── ova-basic.yaml
    │   └── ovf-basic.yaml
    │
    ├── 50-daemon/               # Automation (2 examples)
    │   ├── daemon-watch.yaml
    │   └── generate-systemd.yaml
    │
    ├── 60-vsphere/              # vSphere integration (11 examples)
    │   ├── vsphere-list-vms.yaml
    │   ├── vsphere-export-vm.yaml
    │   └── ... (more)
    │
    └── 99-merge-demos/          # Config merging examples (3 examples)
        ├── merge-base.yaml
        ├── merge-override.yaml
        └── merge-run-local.yaml
```

**Total:** 40+ working examples

---

## Common Scenarios

### Linux Migrations

#### 1. Basic Linux VM Conversion

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-basic.yaml
```

**What it does:**
- Converts VMDK to qcow2
- Flattens snapshots
- Fixes /etc/fstab (UUID/PARTUUID)
- Regenerates bootloader (GRUB)
- Cleans network config
- Compresses output

**Use when:** You have a Linux VM VMDK file locally

#### 2. Cloud-Init Ready Image

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-cloud-init.yaml
```

**What it does:**
- Everything in basic conversion
- Injects cloud-init
- Configures for cloud deployment
- Sets up console access

**Use when:** Preparing VMs for cloud platforms (OpenStack, etc.)

#### 3. Expand Root Partition

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-grow-root.yaml
```

**What it does:**
- Resizes disk image
- Expands root partition
- Resizes filesystem
- Fixes bootloader and fstab

**Use when:** Your VM disk is too small for the target environment

#### 4. UEFI Boot Test

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-libvirt-smoke-uefi.yaml
```

**What it does:**
- Converts VM
- Validates UEFI boot
- Tests with libvirt
- Generates boot report

**Use when:** Migrating UEFI-based VMs

---

### Windows Migrations

#### 5. Windows with VirtIO Drivers

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-windows-virtio-basic.yaml
```

**What it does:**
- Converts Windows VMDK
- Injects VirtIO storage drivers (offline registry modification)
- Injects VirtIO network drivers
- Two-phase boot strategy (SATA → VirtIO)
- Validates boot

**Use when:** Migrating any Windows VM to KVM

#### 6. Windows with Extra Devices

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-windows-virtio-extra-devices.yaml
```

**What it does:**
- All basic Windows fixes
- Adds VirtIO balloon driver
- Adds VirtIO RNG driver
- Adds VirtIO SCSI driver
- QEMU guest agent

**Use when:** You need advanced VirtIO devices for Windows

---

### Remote/Network Migrations

#### 7. Fetch from ESXi via SSH

```bash
sudo python -m hyper2kvm --config examples/yaml/30-fetch-and-fix/fetch-basic.yaml
```

**What it does:**
- Connects to ESXi host via SSH
- Downloads VMDK files
- Flattens snapshot chains
- Applies all fixes
- Converts to qcow2

**Use when:** Migrating VMs from ESXi without vCenter

#### 8. Parallel Batch Fetch

```bash
sudo python -m hyper2kvm --config examples/yaml/30-fetch-and-fix/fetch-batch-parallel.yaml
```

**What it does:**
- Fetches multiple VMs in parallel
- Processes disks concurrently
- Maximizes throughput
- Individual error isolation

**Use when:** Migrating many VMs from ESXi

---

### vSphere Integration

#### 9. List VMs in vSphere

```bash
sudo python -m hyper2kvm --config examples/yaml/60-vsphere/vsphere-list-vms.yaml
```

**What it does:**
- Connects to vCenter
- Lists all VMs
- Shows VM properties
- Exports to JSON/YAML

**Use when:** Planning migrations from vSphere

#### 10. Export VM from vSphere

```bash
sudo python -m hyper2kvm --config examples/yaml/60-vsphere/vsphere-export-vm.yaml
```

**What it does:**
- Exports VM from vCenter
- Downloads all disks
- Applies fixes
- Converts to qcow2
- Validates boot

**Use when:** Migrating from vCenter/vSphere

#### 11. Enable CBT (Changed Block Tracking)

```bash
sudo python -m hyper2kvm --config examples/yaml/60-vsphere/vsphere-enable-cbt.yaml
```

**What it does:**
- Enables CBT on VM
- Configures for incremental backups
- Prepares for fast syncs

**Use when:** Setting up incremental migration workflows

---

### Live Fixes (No Conversion)

#### 12. Fix Running Linux VM

```bash
sudo python -m hyper2kvm --config examples/yaml/20-live-fix/live-fix-basic.yaml
```

**What it does:**
- Connects to running VM via SSH
- Fixes /etc/fstab
- Regenerates GRUB
- Cleans network config
- NO conversion, NO downtime

**Use when:** Fixing VMs already running on KVM

#### 13. Dry-Run Preview

```bash
sudo python -m hyper2kvm --config examples/yaml/20-live-fix/live-fix-dry-run.yaml
```

**What it does:**
- Shows what WOULD be changed
- No actual modifications
- Generates detailed report

**Use when:** Testing fixes before applying

---

### Batch Operations

#### 14. Migrate Two VMs

```bash
sudo python -m hyper2kvm --config examples/yaml/11-batch/batch-local-two-vms.yaml
```

**What it does:**
- Processes two VMs sequentially
- Independent error handling
- Individual reports

**Use when:** Small batch migrations

#### 15. Migrate Many VMs (YAML Matrix)

```bash
sudo python -m hyper2kvm --config examples/yaml/11-batch/batch-local-many.yaml
```

**What it does:**
- Reads VM list from YAML
- Processes all VMs
- Parallel execution option
- Batch summary report

**Use when:** Large-scale migrations

---

### Advanced Workflows

#### 16. virt-v2v Integration

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-with-virt-v2v-post.yaml
```

**What it does:**
- Runs hyper2kvm fixes first
- Then runs virt-v2v
- Combines strengths of both tools
- Maximum compatibility

**Use when:** Complex migrations needing both tools

#### 17. Raw Disk for DD

```bash
sudo python -m hyper2kvm --config examples/yaml/10-local/local-linux-raw-for-dd.yaml
```

**What it does:**
- Converts to RAW format
- Optimized for `dd` imaging
- Sparse file support
- Exact byte copy

**Use when:** Creating bootable USB or bare-metal deployments

---

## Configuration Format

### YAML Example (Recommended)

```yaml
# Basic Linux migration
cmd: local
vmdk: /data/vms/web-server/web-server.vmdk
flatten: true
to_output: /data/kvm/web-server.qcow2
compress: true

# Fixes
fix_fstab: true
fix_grub: true
fix_network: true

# Validation
libvirt_test: true

# Reporting
report: /var/log/migrations/web-server-$(date +%Y%m%d).md
log_level: INFO
```

### Minimal Example

```yaml
cmd: local
vmdk: /path/to/vm.vmdk
to_output: /output/vm.qcow2
```

### Comprehensive Example

```yaml
# Command and input
cmd: local
vmdk: /data/vm/ubuntu-server.vmdk

# Processing
flatten: true
compress: true
grow_root: 20G

# Linux fixes
fix_fstab: true
fix_grub: true
fix_initramfs: true
fix_network: true
remove_vmware_tools: true

# Cloud preparation
inject_cloud_init: true

# Testing
libvirt_test: true
qemu_test: true

# Output
to_output: /data/kvm/ubuntu-server.qcow2
output_format: qcow2

# Reporting
report: ubuntu-server-migration.md
log_level: DEBUG
dry_run: false
```

---

## Complete Workflows

### Workflow 1: VMware Workstation → KVM

**Scenario:** Migrate a development VM from VMware Workstation to KVM

```bash
# Step 1: Locate the VMDK
ls ~/vmware/Ubuntu-Development/*.vmdk

# Step 2: Convert with fixes
sudo python -m hyper2kvm local \
  --vmdk ~/vmware/Ubuntu-Development/Ubuntu-Development.vmdk \
  --flatten \
  --to-output ~/kvm/ubuntu-dev.qcow2 \
  --compress \
  --fix-fstab \
  --fix-grub \
  --fix-network

# Step 3: Test boot
sudo python -m hyper2kvm local \
  --vmdk ~/kvm/ubuntu-dev.qcow2 \
  --qemu-test

# Step 4: Import to libvirt
sudo cp ~/kvm/ubuntu-dev.qcow2 /var/lib/libvirt/images/
sudo virt-install \
  --name ubuntu-dev \
  --memory 4096 \
  --vcpus 2 \
  --disk /var/lib/libvirt/images/ubuntu-dev.qcow2,bus=virtio \
  --network bridge=virbr0,model=virtio \
  --graphics vnc \
  --import
```

### Workflow 2: ESXi → KVM (Production)

**Scenario:** Migrate production web server from ESXi to KVM

```bash
# Step 1: Fetch from ESXi
sudo python -m hyper2kvm fetch-and-fix \
  --host esxi-prod-01.example.com \
  --user root \
  --identity ~/.ssh/esxi_key \
  --remote /vmfs/volumes/production/web-01/web-01.vmdk \
  --fetch-all \
  --flatten \
  --to-output /staging/web-01.qcow2 \
  --compress \
  --report /staging/reports/web-01-migration.md

# Step 2: Test on staging KVM host
scp /staging/web-01.qcow2 staging-kvm:/var/lib/libvirt/images/
ssh staging-kvm "sudo virsh define /staging/web-01.xml && sudo virsh start web-01"

# Step 3: Validate
ssh staging-kvm "curl http://localhost"  # Test web service

# Step 4: Production deployment
scp /staging/web-01.qcow2 prod-kvm:/var/lib/libvirt/images/
ssh prod-kvm "sudo virsh define /prod/web-01.xml && sudo virsh start web-01"
```

### Workflow 3: vSphere → KVM (Batch)

**Scenario:** Migrate 10 VMs from vCenter to KVM

```bash
# Step 1: Create VM list (vms-to-migrate.yaml)
cat > vms-to-migrate.yaml <<EOF
vms:
  - vm_name: web-01
    output: /data/kvm/web-01.qcow2
  - vm_name: web-02
    output: /data/kvm/web-02.qcow2
  - vm_name: db-01
    output: /data/kvm/db-01.qcow2
  # ... more VMs
EOF

# Step 2: Export all VMs
sudo python -m hyper2kvm vsphere \
  --vcenter vcenter.example.com \
  --username admin@vsphere.local \
  --password-file ~/.vcenter_pass \
  --vs-action export-batch \
  --config vms-to-migrate.yaml \
  --parallel 4

# Step 3: Validate all
for vm in /data/kvm/*.qcow2; do
  sudo python -m hyper2kvm local \
    --vmdk "$vm" \
    --libvirt-test \
    --dry-run
done
```

### Workflow 4: Windows Migration

**Scenario:** Migrate Windows 10 VM with full driver support

```bash
# Step 1: Download VirtIO drivers
wget https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso \
  -O /data/virtio-win.iso

# Step 2: Convert with driver injection
sudo python -m hyper2kvm local \
  --vmdk /data/vmware/Windows10-Pro/Windows10-Pro.vmdk \
  --windows \
  --inject-virtio \
  --virtio-win-iso /data/virtio-win.iso \
  --flatten \
  --compress \
  --to-output /data/kvm/windows10.qcow2 \
  --report /data/reports/windows10-migration.md

# Step 3: Import to libvirt with UEFI
sudo virt-install \
  --name windows10 \
  --memory 8192 \
  --vcpus 4 \
  --disk /data/kvm/windows10.qcow2,bus=virtio \
  --network network=default,model=virtio \
  --os-variant win10 \
  --boot uefi \
  --graphics spice \
  --import
```

---

## Tips and Best Practices

### General Best Practices

1. **Always Flatten Snapshots**
   ```yaml
   flatten: true
   ```
   Ensures clean, single-file output without dependencies

2. **Use Compression**
   ```yaml
   compress: true
   ```
   QCOW2 compression saves 40-60% disk space

3. **Generate Reports**
   ```yaml
   report: migration-report-$(date +%Y%m%d-%H%M%S).md
   ```
   Documents all changes for troubleshooting

4. **Test Before Production**
   ```yaml
   dry_run: true
   libvirt_test: true
   ```
   Validate conversion plan and boot capability

5. **Keep Backups**
   - Never delete source VMDKs until new VM is verified
   - Keep migration reports for audit trail

### Performance Optimization

1. **Parallel Processing**
   ```yaml
   parallel_processing: true
   parallel_workers: 4
   ```
   Use for multi-disk VMs

2. **Skip Unnecessary Fixes**
   ```yaml
   fix_network: false  # If network already correct
   ```

3. **Use RAW for Speed**
   ```yaml
   output_format: raw  # Faster than qcow2, but larger
   ```

### Troubleshooting

1. **Enable Debug Logging**
   ```yaml
   log_level: DEBUG
   ```

2. **Dry-Run First**
   ```yaml
   dry_run: true
   ```

3. **Test Individual Components**
   ```bash
   # Test disk inspection
   sudo guestfish --ro -a vm.vmdk -i

   # Test qemu-img
   qemu-img info vm.vmdk
   ```

### Security

1. **Use SSH Keys**
   ```yaml
   identity: ~/.ssh/esxi_key
   ```

2. **Store Credentials Securely**
   ```yaml
   password_file: ~/.vcenter_pass  # Not in YAML!
   ```

3. **Validate Checksums**
   ```yaml
   verify_checksums: true
   ```

---

## Creating Custom Configurations

### Template

```yaml
# ============================================
# Migration Configuration
# ============================================
# Description: [What this migration does]
# Use Case: [When to use this]
# Prerequisites: [What you need]
# ============================================

# Command
cmd: local  # or fetch-and-fix, vsphere, etc.

# Input
vmdk: /path/to/source.vmdk

# Processing
flatten: true
compress: true

# Fixes (enable as needed)
fix_fstab: true
fix_grub: true
fix_network: true

# Output
to_output: /path/to/output.qcow2

# Testing
libvirt_test: false
dry_run: false

# Reporting
report: migration-report.md
log_level: INFO
```

### Save and Run

```bash
# Save as my-migration.yaml
sudo python -m hyper2kvm --config my-migration.yaml
```

---

## Example Index

### By Use Case

**Quick Conversions:**
- `10-local/local-linux-basic.yaml` - Fastest path to qcow2
- `10-local/local-windows-virtio-basic.yaml` - Windows quick migration

**Production Migrations:**
- `30-fetch-and-fix/fetch-full-chain-and-test.yaml` - Complete workflow
- `60-vsphere/vsphere-export-vm.yaml` - vSphere export

**Testing/Validation:**
- `10-local/local-linux-qemu-smoke.yaml` - QEMU boot test
- `10-local/local-linux-libvirt-smoke-uefi.yaml` - UEFI validation
- `20-live-fix/live-fix-dry-run.yaml` - Preview changes

**Advanced:**
- `10-local/local-with-virt-v2v-post.yaml` - Hybrid approach
- `11-batch/batch-local-many.yaml` - Mass migration
- `50-daemon/daemon-watch.yaml` - Automated monitoring

### By Operating System

**Linux:**
- Ubuntu/Debian: `10-local/local-linux-basic.yaml`
- RHEL/CentOS: `10-local/local-linux-basic.yaml`
- Cloud Images: `10-local/local-linux-cloud-init.yaml`

**Windows:**
- Windows 10/11: `10-local/local-windows-virtio-basic.yaml`
- Windows Server: `10-local/local-windows-virtio-extra-devices.yaml`

**Specialized:**
- PhotonOS: `yaml/photon-ova.yaml`
- RHEL 10: `yaml/stabilizeall-esx8-rhel10.yaml`

---

## Getting Help

**Documentation:**
- [Quick Start Guide](../docs/03-Quick-Start.md)
- [CLI Reference](../docs/04-CLI-Reference.md)
- [YAML Configuration Guide](../docs/05-YAML-Examples.md)
- [Troubleshooting](../docs/90-Failure-Modes.md)

**Command-Line Help:**
```bash
python -m hyper2kvm --help
python -m hyper2kvm local --help
python -m hyper2kvm vsphere --help
```

**Community:**
- GitHub Issues: https://github.com/ssahani/hyper2kvm/issues
- Discussions: https://github.com/ssahani/hyper2kvm/discussions

---

## Contributing Examples

Have a useful migration scenario? Share it!

1. Create your configuration file
2. Test it thoroughly
3. Document the use case
4. Submit a pull request

**Example template:**
```yaml
# ============================================
# [Example Name]
# ============================================
# Description: [Clear description of what this does]
# Use Case: [When someone should use this]
# Prerequisites: [What's needed to run this]
# Author: [Your name]
# Date: [Date created]
# ============================================

cmd: [command]
# ... rest of config
```

---

**Explore the `yaml/` directory for 40+ ready-to-use examples!**
