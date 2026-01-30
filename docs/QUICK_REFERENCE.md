# Hyper2KVM Quick Reference Card

One-page reference for common commands, workflows, and configurations.

---

## Installation (Pick One)

```bash
# Python package
pip install hyper2kvm

# From source
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm && pip install -e .

# Container
docker pull ghcr.io/ssahani/hyper2kvm:latest
```

---

## Basic Migration Workflows

### 1. Simple Local Migration (Most Common)

```bash
hyper2kvm --config << EOF
command: local
vmdk: /vmware/myvm.vmdk
output_dir: /kvm/vms
to_output: myvm.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
EOF
```

**Time**: 10-30 min | **Success Rate**: 96%+

### 2. Quick Migration (Default Settings)

```bash
h2kvmctl migrate local /vmware/myvm.vmdk --output /kvm/vms/myvm.qcow2
```

### 3. Interactive TUI Mode

```bash
h2kvmctl tui
# Follow on-screen prompts
```

### 4. Remote vSphere Export

```bash
hyper2kvm --config << EOF
command: vsphere_export
vcenter_host: vcenter.example.com
vcenter_user: admin@vsphere.local
vcenter_password: secret
vm_name: production-web-01
output_dir: /kvm/vms
to_output: prod-web.qcow2
EOF
```

---

## Essential YAML Options

### Migration Modes

```yaml
# Local file migration
command: local
vmdk: /path/to/vm.vmdk

# Remote vSphere
command: vsphere_export
vcenter_host: vcenter.example.com
vm_name: myvm

# Remote ESXi
command: remote_esxi
esxi_host: 192.168.1.100
esxi_user: root
vm_name: myvm
```

### Output Options

```yaml
output_dir: /kvm/vms          # Output directory
to_output: myvm.qcow2         # Output filename
compress: true                # Enable compression (smaller but slower)
format: qcow2                 # Format: qcow2 (default), raw
```

### Boot Fix Options (Recommended)

```yaml
fstab_mode: stabilize-all     # Fix fstab entries (always use)
xfs_regenerate_uuid: true     # Fix cloned VMware VMs
regen_initramfs: true         # Rebuild initramfs for new drivers
update_grub: true             # Update GRUB configuration
```

### Advanced Options

```yaml
enable_vmcraft: true          # Use VMCraft engine (default)
network_retry: 3              # Network operation retries
timeout: 3600                 # Operation timeout (seconds)
keep_original: true           # Keep original VMDK (default)
validate: true                # Run post-migration validation
```

---

## Common Command Patterns

### Inspect Before Migration

```bash
# Analyze VMDK
./scripts/vmdk_inspect.py /vmware/myvm.vmdk

# With auto-fix recommendations
./scripts/vmdk_inspect.py /vmware/myvm.vmdk --auto-fix
```

### Batch Migration

```bash
# Submit multiple migrations to daemon
hyper2kvm daemon start

for vmdk in /vmware/*.vmdk; do
    hyper2kvm daemon submit migration-$(basename $vmdk .vmdk).yaml
done

# Monitor progress
hyper2kvm daemon status
```

### Live Fix (Minimal Downtime)

```bash
# Fix running VM via SSH (<5 sec downtime)
h2kvmctl fix ssh 192.168.1.100 --user root --key ~/.ssh/id_rsa
```

---

## Troubleshooting Commands

### Check Migration Status

```bash
# View logs
journalctl -u hyper2kvm -f

# Check daemon jobs
h2kvmctl daemon list

# Validate QCOW2
qemu-img check /kvm/vms/myvm.qcow2
```

### Fix Common Issues

```bash
# Regenerate initramfs manually
h2kvmctl fix initramfs /dev/vda1

# Fix fstab
h2kvmctl fix fstab /dev/vda1 --mode stabilize-all

# Fix XFS UUID
h2kvmctl fix xfs-uuid /dev/vda1
```

### Boot VM for Testing

```bash
# Quick boot test
qemu-system-x86_64 -m 2048 -hda /kvm/vms/myvm.qcow2 -vnc :0
```

---

## fstab Stabilization Modes

| Mode | Behavior | Use When |
|------|----------|----------|
| `stabilize-all` | Convert all entries to UUID | **Recommended** - Always use |
| `uuid-only` | Only update UUID entries | Preserve LABEL entries |
| `label-fallback` | Prefer UUID, fallback to LABEL | Mixed environments |
| `preserve` | Keep original entries | Testing only |

---

## OS-Specific Quick Fixes

### RHEL/CentOS/Rocky

```yaml
command: local
vmdk: /vmware/rhel9.vmdk
output_dir: /kvm/vms
to_output: rhel9.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
```

### Ubuntu/Debian

```yaml
command: local
vmdk: /vmware/ubuntu.vmdk
output_dir: /kvm/vms
to_output: ubuntu.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
```

### Windows

```yaml
command: local
vmdk: /vmware/windows.vmdk
output_dir: /kvm/vms
to_output: windows.qcow2
inject_virtio_drivers: true
windows_version: 2019        # 2012, 2016, 2019, 2022, 10, 11
```

### VMware Cloned VMs

```yaml
command: local
vmdk: /vmware/cloned-vm.vmdk
output_dir: /kvm/vms
to_output: fixed-vm.qcow2
xfs_regenerate_uuid: true    # Critical for clones
fstab_mode: stabilize-all
regen_initramfs: true
```

---

## Performance Tuning

### Fast Migration (Less Compression)

```yaml
compress: false               # Faster but larger
parallel_streams: 4           # Use multiple streams
```

### Small Output (More Compression)

```yaml
compress: true                # Slower but smaller
compression_level: 9          # Max compression
```

### Large VM (Resource Management)

```yaml
chunk_size: 1G                # Process in chunks
memory_limit: 4096            # Limit memory usage (MB)
```

---

## Kubernetes Deployment

### Quick Deploy with Helm

```bash
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm-charts
helm install hyper2kvm hyper2kvm/hyper2kvm -n hyper2kvm-system --create-namespace
```

### Submit Migration Job

```yaml
apiVersion: hyper2kvm.io/v1
kind: MigrationJob
metadata:
  name: migrate-web-server
spec:
  source:
    type: vmdk
    path: /mnt/vmware/web-server.vmdk
  output:
    format: qcow2
    path: /mnt/kvm/web-server.qcow2
  options:
    fstabMode: stabilize-all
    regenInitramfs: true
```

```bash
kubectl apply -f migration-job.yaml
kubectl get migrationjob migrate-web-server -w
```

---

## Environment Variables

```bash
# Logging
export HYPER2KVM_LOG_LEVEL=DEBUG    # DEBUG, INFO, WARNING, ERROR
export HYPER2KVM_LOG_FILE=/var/log/hyper2kvm.log

# Performance
export HYPER2KVM_WORKERS=4          # Parallel workers
export HYPER2KVM_CACHE_DIR=/tmp/h2kvm

# Network
export HYPER2KVM_TIMEOUT=3600       # Operation timeout
export HYPER2KVM_RETRY=3            # Retry attempts
```

---

## File Locations

```
# Configuration
/etc/hyper2kvm/config.yaml          # System config
~/.hyper2kvm/config.yaml            # User config

# Logs
/var/log/hyper2kvm/                 # System logs
~/.hyper2kvm/logs/                  # User logs

# Cache
/var/cache/hyper2kvm/               # System cache
~/.cache/hyper2kvm/                 # User cache

# Daemon
/var/run/hyper2kvm.pid              # Daemon PID
/var/run/hyper2kvm.sock             # Daemon socket
```

---

## Common Error Fixes

### Error: "VMDK not found"
```bash
# Check path and permissions
ls -l /path/to/vm.vmdk
chmod 644 /path/to/vm.vmdk
```

### Error: "Boot failure - kernel panic"
```yaml
# Add these options
regen_initramfs: true
update_grub: true
fstab_mode: stabilize-all
```

### Error: "Duplicate UUID"
```yaml
# For cloned VMware VMs
xfs_regenerate_uuid: true
```

### Error: "Network timeout"
```yaml
# Increase retries and timeout
network_retry: 5
timeout: 7200
```

---

## Success Rates by OS

| OS Family | Success Rate | Avg Time |
|-----------|--------------|----------|
| **RHEL/CentOS** | 98% | 15 min |
| **Ubuntu** | 97% | 12 min |
| **SUSE** | 96% | 18 min |
| **Windows** | 94% | 25 min |
| **Other Linux** | 95% | 20 min |

---

## Quick Links

- **Documentation**: `/docs/index.md`
- **Tutorials**: `/docs/tutorials/`
- **Recipes**: `/docs/recipes/`
- **FAQ**: `/docs/FAQ.md`
- **Troubleshooting**: `/docs/guides/troubleshooting.md`
- **API Reference**: `/docs/reference/api/`

---

## Version Information

**Hyper2KVM**: v2.1.0
**API Version**: v1.0
**Schema Version**: v1.0
**Last Updated**: February 2026

---

## Support

- **Issues**: https://github.com/ssahani/hyper2kvm/issues
- **Discussions**: https://github.com/ssahani/hyper2kvm/discussions
- **Documentation**: https://github.com/ssahani/hyper2kvm/tree/main/docs

---

**Print this page** for quick reference at your desk!
