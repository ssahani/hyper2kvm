# CLI Syntax Corrections for Documentation

**Date**: 2026-01-27
**Status**: Documentation Update Required

## Summary

This document outlines the correct hyper2kvm CLI syntax to be used throughout all documentation. The tool does NOT use subcommands like `migrate`, `live`, `batch`, `validate`, etc. Instead, it uses:

1. **`hyper2kvm --config <yaml-file>`** (Recommended approach)
2. **`hyper2kvm --cmd <command>`** with additional flags

## Correct CLI Patterns

### Pattern 1: YAML Configuration (Recommended)

```yaml
# config.yaml
command: local              # or: fetch-and-fix, ova, ovf, vhd, ami, live-fix, vsphere, azure, daemon, generate-systemd
vmdk: /path/to/source.vmdk
output_dir: /path/to/output
to_output: converted.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
win_virtio: true
compress: true
verbose: 1
```

```bash
hyper2kvm --config config.yaml
```

### Pattern 2: CLI Flags

```bash
hyper2kvm --cmd local \
    --vmdk /path/to/source.vmdk \
    --output-dir /path/to/output \
    --to-output converted.qcow2 \
    --out-format qcow2 \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --update-grub \
    --compress
```

## Available --cmd Values

| Command | Purpose |
|---------|---------|
| `local` | Local VMDK/disk migration |
| `fetch-and-fix` | SSH fetch from ESXi + migration |
| `ova` | OVA extraction and migration |
| `ovf` | OVF extraction and migration |
| `vhd` | VHD import and migration |
| `ami` | AMI/cloud archive migration |
| `live-fix` | SSH-based live fixing (no conversion) |
| `vsphere` | vSphere operations |
| `azure` | Azure operations |
| `daemon` | Daemon mode (watch directory) |
| `generate-systemd` | Generate systemd unit files |

## Common Migration Scenarios

### Linux VM Migration

**YAML Config:**
```yaml
command: local
vmdk: /vms/linux-server.vmdk
output_dir: /kvm/vms
to_output: linux-server.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
compress: true
```

**CLI Flags:**
```bash
hyper2kvm --cmd local \
    --vmdk /vms/linux-server.vmdk \
    --output-dir /kvm/vms \
    --to-output linux-server.qcow2 \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --update-grub \
    --compress
```

### Windows VM Migration

**YAML Config:**
```yaml
command: local
vmdk: /vms/windows-server.vhdx
output_dir: /kvm/vms
to_output: windows-server.qcow2
out_format: qcow2
win_virtio: true
compress: true
```

**CLI Flags:**
```bash
hyper2kvm --cmd local \
    --vmdk /vms/windows-server.vhdx \
    --output-dir /kvm/vms \
    --to-output windows-server.qcow2 \
    --win-virtio \
    --compress
```

### Fetch from ESXi

**YAML Config:**
```yaml
command: fetch-and-fix
host: esxi.example.com
user: root
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
fetch_all: true
flatten: true
output_dir: /kvm/vms
to_output: vm.qcow2
```

**CLI Flags:**
```bash
hyper2kvm --cmd fetch-and-fix \
    --host esxi.example.com \
    --user root \
    --remote /vmfs/volumes/datastore1/vm/vm.vmdk \
    --fetch-all \
    --flatten \
    --output-dir /kvm/vms \
    --to-output vm.qcow2
```

### SSH-Based Live Fixing

**YAML Config:**
```yaml
command: live-fix
host: 192.168.1.100
user: root
sudo: true
fstab_mode: stabilize-all
regen_initramfs: true
update_grub: true
```

**CLI Flags:**
```bash
hyper2kvm --cmd live-fix \
    --host 192.168.1.100 \
    --user root \
    --sudo \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --update-grub
```

## Batch Migration

For batch migration, use a manifest approach with multiple YAML files or a batch manifest:

### Batch Manifest Approach

```yaml
# batch-manifest.yaml
migrations:
  - command: local
    vmdk: /vms/vm1.vmdk
    output_dir: /kvm/vms
    to_output: vm1.qcow2

  - command: local
    vmdk: /vms/vm2.vmdk
    output_dir: /kvm/vms
    to_output: vm2.qcow2

  - command: local
    vmdk: /vms/vm3.vmdk
    output_dir: /kvm/vms
    to_output: vm3.qcow2
```

Then process with a script:
```bash
#!/bin/bash
for vm in vm1 vm2 vm3; do
    hyper2kvm --config configs/${vm}.yaml
done
```

## Non-Existent Features to Remove from Docs

The following features are NOT implemented and should be removed from documentation:

### ❌ Standalone Validation API
- No `hyper2kvm validate` command
- No `--check-boot`, `--check-fstab`, `--check-services` validation flags
- Validation happens internally during migration

### ❌ Live Migration (Not Yet Implemented)
- No `hyper2kvm live migrate` command
- Future feature documented in development/live-migration-implementation-plan.md
- Do not show as production feature

### ❌ Batch Command
- No `hyper2kvm batch execute` command
- No `hyper2kvm batch validate` command
- No `hyper2kvm batch status` command
- Use shell scripts or daemon mode instead

### ❌ Backup Integration
- No `hyper2kvm backup restore` command
- No `hyper2kvm backup list` command
- Not a backup tool - use qemu-img or other tools

### ❌ Container Extraction
- No `hyper2kvm container extract` command
- Not a VM-to-Kubernetes migration tool

### ❌ Compliance Reporting
- No `--compliance-report` flag
- No automated compliance report generation
- No `--generate-compliance-report` option

### ❌ Rollback API
- No `hyper2kvm rollback` command
- Use manual snapshot restoration with qemu-img/libvirt

## Daemon Mode (Actual Feature)

Daemon mode IS implemented for automated processing:

```yaml
# daemon.yaml
command: daemon
daemon: true
watch_dir: /var/lib/hyper2kvm/queue
output_dir: /var/lib/hyper2kvm/output
workdir: /var/lib/hyper2kvm/work
flatten: true
out_format: qcow2
compress: true
fstab_mode: stabilize-all
regen_initramfs: true
```

```bash
hyper2kvm --config daemon.yaml
```

Drop files into watch_dir for automatic processing.

## File-by-File Corrections Needed

### 1. docs/tutorials/01-beginner-migration.md
- ✅ PARTIALLY UPDATED (basic migration command fixed)
- Remove validation command examples (lines 261-291)
- Update all troubleshooting commands (lines 449-498)

### 2. docs/tutorials/02-intermediate-workflows.md
- Remove all batch command examples
- Replace with shell script batch approach
- Remove compliance reporting references
- Update automation examples to use config files

### 3. docs/index.md
- Remove validation API, backup API, container extraction, live migration from feature table
- Update quick start examples (lines 106-122, 129-167)
- Remove non-existent command references (lines 226-232)

### 4. docs/HOW_HYPER2KVM_WORKS.md
- Remove validation framework architecture (lines 182-221)
- Remove rollback framework architecture (lines 223-260)
- Remove live migration workflow (lines 406-469)
- Remove batch migration architecture (lines 639-668)
- Remove compliance/audit section (lines 595-635)
- Keep VMCraft and offline fixer sections (accurate)

### 5. docs/recipes/README.md
- Keep structure but update command examples
- Reference correct CLI patterns

### 6. docs/recipes/01-common-scenarios.md
- Update all recipe command examples to use correct syntax
- Remove validation, batch, live, backup, container commands
- Use YAML configs for complex scenarios

### 7. docs/guides/migration/quick-reference.md
- This file shows completely different CLI (convert, batch, vsphere commands)
- Major rewrite needed to match actual CLI

### 8. docs/getting-started/01-Installation.md
- Looks mostly accurate (installation instructions)
- Minor updates to example commands (lines 484-487)

### 9. docs/getting-started/02-Quick-Start.md
- Update all command examples to use correct syntax
- Remove validation commands
- Update test commands (lines 265-283)

### 10. docs/features/enhanced-chroot.md
- Update example migration commands (line 121-127)
- Mostly accurate, minor syntax updates

### 11. docs/development/live-migration-implementation-plan.md
- Mark as ASPIRATIONAL/FUTURE
- Add header: "This is a development plan for future implementation"
- Keep as is but clarify it's not yet implemented

### 12. docs/development/summaries/TESTS_COMPLETE_SUMMARY.md
- Test documentation - keep as is
- Tests may reference future APIs

### 13. docs/project/ECOSYSTEM.md
- Update Python CLI examples (lines 146-157)
- Correct command syntax in usage examples (lines 478-601)

## Recommended Documentation Approach

For each documentation file:

1. **Use YAML examples primarily** - More readable and maintainable
2. **Show CLI flags as alternative** - For simple cases
3. **Remove non-existent features** - Don't document what doesn't exist
4. **Mark aspirational features** - Clearly label development plans
5. **Use realistic examples** - Match actual implementation

## Example Replacement Pattern

### OLD (Incorrect):
```bash
hyper2kvm migrate /vms/server.vmdk \
    --target /kvm/server.qcow2 \
    --fix-all \
    --validate
```

### NEW (Correct - YAML):
```yaml
# migration.yaml
command: local
vmdk: /vms/server.vmdk
output_dir: /kvm
to_output: server.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
compress: true
```
```bash
hyper2kvm --config migration.yaml
```

### NEW (Correct - CLI flags):
```bash
hyper2kvm --cmd local \
    --vmdk /vms/server.vmdk \
    --output-dir /kvm \
    --to-output server.qcow2 \
    --out-format qcow2 \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --compress
```

## Next Steps

1. Update each file systematically with correct syntax
2. Remove non-existent feature documentation
3. Mark development plans clearly
4. Test examples for accuracy
5. Update any auto-generated documentation

---

**Status**: Documentation audit complete, corrections outlined
**Files Requiring Updates**: 13 documentation files
**Priority**: High - Users are seeing incorrect examples
