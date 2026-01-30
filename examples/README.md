# hyper2kvm Examples

This directory contains working examples for common hyper2kvm migration scenarios.

## Directory Structure

```
examples/
├── json/               # JSON configuration files (machine-friendly)
│   ├── 00-common/     # Shared/base configurations
│   ├── 10-local/      # Local VMDK conversions
│   ├── 11-batch/      # Batch/multi-VM migrations
│   ├── 20-live-fix/   # Live SSH-based fixes
│   ├── 30-vsphere/    # vSphere/ESXi integration
│   └── 40-fetch/      # Remote fetch scenarios
└── yaml/              # YAML configuration files (human-friendly)
    └── (mirrors json structure)
```

---

## Quick Start Examples

### 1. Convert a Local VMDK to QCOW2

```bash
# Basic conversion with automatic fixes
sudo python -m hyper2kvm local \
  --vmdk /path/to/linux.vmdk \
  --flatten \
  --to-output linux-fixed.qcow2 \
  --compress
```

**Using config file:**
```bash
sudo python -m hyper2kvm --config examples/json/10-local/local-linux-basic.json
```

### 2. Fetch and Convert Remote VMDK from ESXi

```bash
# Fetch VMDK from ESXi over SSH and convert
sudo python -m hyper2kvm fetch-and-fix \
  --host esxi.example.com \
  --user root \
  --remote /vmfs/volumes/datastore1/vm/vm.vmdk \
  --fetch-all \
  --flatten \
  --to-output vm-converted.qcow2
```

**Using config file:**
```bash
sudo python -m hyper2kvm --config examples/json/40-fetch/fetch-esxi-linux.json
```

### 3. Fix a Running Linux VM Over SSH

```bash
# Apply network/bootloader fixes to a live VM
sudo python -m hyper2kvm live-fix \
  --host 192.168.1.100 \
  --user root \
  --sudo \
  --fix-network \
  --fix-bootloader
```

**Using config file:**
```bash
sudo python -m hyper2kvm --config examples/json/20-live-fix/live-fix-basic.json
```

### 4. Windows VM with VirtIO Driver Injection

```bash
# Convert Windows VM and inject VirtIO drivers
sudo python -m hyper2kvm local \
  --vmdk /path/to/windows.vmdk \
  --flatten \
  --to-output windows-fixed.qcow2 \
  --windows \
  --inject-virtio \
  --virtio-win-iso /path/to/virtio-win.iso
```

**Using config file:**
```bash
sudo python -m hyper2kvm --config examples/json/10-local/local-windows-virtio-basic.json
```

### 5. Batch Migration of Multiple VMs

```bash
# Process multiple VMs from YAML matrix
sudo python -m hyper2kvm --config examples/json/11-batch/batch-local-many.json
```

---

## Example Categories

### 00-common: Base Configurations

Shared settings that can be merged with specific scenarios:

- **common.json** - Standard settings for most migrations
- **common-fast.json** - Optimized for speed (less validation)
- **common-strict.json** - Maximum safety and validation

**Usage:**
```bash
# Merge common settings with specific config
sudo python -m hyper2kvm \
  --config examples/json/00-common/common.json \
  --config examples/json/10-local/local-linux-basic.json
```

### 10-local: Local VMDK Conversions

Process VMDK files already on local disk:

- **local-linux-basic.json** - Simple Linux VM conversion
- **local-linux-cloud-init.json** - Cloud image preparation
- **local-linux-grow-root.json** - Expand root partition during conversion
- **local-windows-virtio-basic.json** - Windows with VirtIO drivers
- **local-with-virt-v2v-primary.json** - Use virt-v2v as primary converter

### 11-batch: Batch Operations

Process multiple VMs in one run:

- **batch-local-two-vms.json** - Convert two VMs
- **batch-local-many.json** - YAML matrix for many VMs

### 20-live-fix: Live SSH Fixes

Fix running VMs without conversion:

- **live-fix-basic.json** - Network and bootloader fixes
- **live-fix-batch.json** - Fix multiple running VMs

### 30-vsphere: vSphere Integration

Export and convert VMs from vSphere:

- **vsphere-export-single.json** - Export one VM
- **vsphere-export-batch.json** - Export multiple VMs
- **vsphere-with-credentials.json** - Using credential file

### 40-fetch: Remote Fetch

Fetch VMDKs from remote systems:

- **fetch-esxi-linux.json** - Fetch from ESXi host
- **fetch-with-identity.json** - Using SSH key authentication

---

## Configuration File Format

### JSON Format

```json
{
  "command": "local",
  "vmdk": "/path/to/disk.vmdk",
  "flatten": true,
  "to_output": "output.qcow2",
  "compress": true,
  "report": "migration-report.md"
}
```

### YAML Format

```yaml
command: local
vmdk: /path/to/disk.vmdk
flatten: true
to_output: output.qcow2
compress: true
report: migration-report.md
```

---

## Common Options

### Input Options
- `vmdk`: Path to source VMDK file
- `command`: Operation mode (local, fetch-and-fix, live-fix, vsphere)

### Output Options
- `to_output`: Output file path (.qcow2 recommended)
- `compress`: Enable compression
- `flatten`: Flatten snapshot chains

### Processing Options
- `fix_network`: Fix network configuration
- `fix_bootloader`: Regenerate bootloader config
- `inject_virtio`: Inject Windows VirtIO drivers (Windows only)
- `grow_root`: Expand root partition

### Testing Options
- `libvirt_test`: Boot test with libvirt
- `qemu_test`: Boot test with QEMU
- `dry_run`: Show plan without executing

### Reporting
- `report`: Generate markdown migration report
- `log_level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

---

## Merging Configuration Files

You can layer multiple config files:

```bash
# Base settings + specific VM config
sudo python -m hyper2kvm \
  --config examples/json/00-common/common.json \
  --config my-vm.json

# Override with command-line args
sudo python -m hyper2kvm \
  --config examples/json/10-local/local-linux-basic.json \
  --compress \
  --to-output custom-output.qcow2
```

**Merge priority** (later overrides earlier):
1. First config file
2. Second config file
3. Command-line arguments

---

## Creating Your Own Config

### Step 1: Start with a Template

```bash
cp examples/json/10-local/local-linux-basic.json my-migration.json
```

### Step 2: Edit for Your Environment

```json
{
  "command": "local",
  "vmdk": "/data/vms/myvm/myvm.vmdk",
  "flatten": true,
  "to_output": "/data/converted/myvm.qcow2",
  "compress": true,
  "fix_network": true,
  "fix_bootloader": true,
  "report": "/data/reports/myvm-migration.md",
  "log_level": "INFO"
}
```

### Step 3: Run

```bash
sudo python -m hyper2kvm --config my-migration.json
```

---

## Example Workflows

### Workflow 1: ESXi to KVM Migration

1. **Export from ESXi:**
   ```bash
   sudo python -m hyper2kvm fetch-and-fix \
     --host esxi.example.com \
     --remote /vmfs/volumes/ds1/prod-web/prod-web.vmdk \
     --fetch-all \
     --to-output prod-web.qcow2
   ```

2. **Test the converted VM:**
   ```bash
   sudo python -m hyper2kvm local \
     --vmdk prod-web.qcow2 \
     --libvirt-test \
     --dry-run
   ```

3. **Deploy to production KVM:**
   ```bash
   sudo cp prod-web.qcow2 /var/lib/libvirt/images/
   sudo virsh define prod-web.xml
   sudo virsh start prod-web
   ```

### Workflow 2: Batch Migration

1. **Create VM list (vms.yaml):**
   ```yaml
   vms:
     - vmdk: /data/vm1/vm1.vmdk
       to_output: /data/converted/vm1.qcow2
     - vmdk: /data/vm2/vm2.vmdk
       to_output: /data/converted/vm2.qcow2
   ```

2. **Run batch migration:**
   ```bash
   sudo python -m hyper2kvm --config vms.yaml
   ```

### Workflow 3: Windows with VirtIO

1. **Download VirtIO drivers:**
   ```bash
   wget https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso
   ```

2. **Convert with driver injection:**
   ```bash
   sudo python -m hyper2kvm local \
     --vmdk windows10.vmdk \
     --windows \
     --inject-virtio \
     --virtio-win-iso virtio-win.iso \
     --to-output windows10-kvm.qcow2
   ```

---

## Troubleshooting Examples

### Enable Debug Logging

```json
{
  "command": "local",
  "vmdk": "/path/to/problematic.vmdk",
  "log_level": "DEBUG",
  "to_output": "debug-output.qcow2"
}
```

### Dry Run (Preview Only)

```json
{
  "command": "local",
  "vmdk": "/path/to/test.vmdk",
  "dry_run": true,
  "to_output": "test.qcow2"
}
```

### Generate Detailed Report

```json
{
  "command": "local",
  "vmdk": "/path/to/vm.vmdk",
  "report": "detailed-migration-report.md",
  "to_output": "vm.qcow2"
}
```

---

## Tips and Best Practices

### 1. Always Flatten Snapshots
```json
{"flatten": true}
```
Ensures a clean, single-file output without snapshot dependencies.

### 2. Use Compression for Storage
```json
{"compress": true}
```
QCOW2 compression significantly reduces disk usage.

### 3. Test Before Production
```json
{"libvirt_test": true, "dry_run": true}
```
Validate the conversion plan before executing.

### 4. Keep Backups
```json
{"backup": true}
```
Always maintain original VMDKs until conversion is verified.

### 5. Generate Reports
```json
{"report": "migration-$(date +%Y%m%d).md"}
```
Document what was changed for troubleshooting.

---

## Need Help?

- **Documentation:** See `docs/` directory
- **CLI Reference:** `python -m hyper2kvm --help`
- **Issues:** https://github.com/hyper2kvm/hyper2kvm/issues
- **Examples:** This directory has 30+ working examples

---

## Contributing Examples

Have a useful migration scenario? Contribute it!

1. Create your config file
2. Test it thoroughly
3. Add documentation
4. Submit a pull request

Example template:
```json
{
  "// DESCRIPTION": "What this example does",
  "// USE_CASE": "When to use this",
  "// PREREQUISITES": "What you need",
  "command": "...",
  "...": "..."
}
```
