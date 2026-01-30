# CLI Syntax Corrections Needed

## Status

✅ **COMPLETED**:
- README.md - All examples updated
- docs/index.md - All examples updated

🔄 **PENDING** (13 files with incorrect CLI syntax):

1. **docs/recipes/01-common-scenarios.md** - 20+ incorrect examples
   - Recipe 1-10 all use `hyper2kvm migrate`
   - Need to replace with YAML config approach

2. **docs/recipes/README.md** - Summary file
   - Update example snippets

3. **docs/tutorials/01-beginner-migration.md** - Tutorial examples
   - Replace migrate commands

4. **docs/tutorials/02-intermediate-workflows.md** - Batch examples
   - Update batch syntax, remove non-existent features

5. **docs/HOW_HYPER2KVM_WORKS.md** - Presentation document
   - Already partially updated, verify all sections

6. **docs/guides/migration/quick-reference.md** - Quick reference
   - Major rewrite needed

7. **docs/getting-started/01-Installation.md** - Installation examples
   - Update post-install examples

8. **docs/features/enhanced-chroot.md** - Feature examples

9. **docs/development/live-migration-implementation-plan.md** - Aspirational
   - Mark as future feature

10. **docs/development/summaries/TESTS_COMPLETE_SUMMARY.md** - Test summary

11. **docs/project/ECOSYSTEM.md** - Ecosystem examples

## Incorrect Patterns to Replace

### Pattern 1: Basic Migration
❌ **OLD**:
```bash
hyper2kvm migrate /vms/server.vmdk \
    --target /kvm/server.qcow2 \
    --fix-all \
    --validate
```

✅ **NEW (YAML)**:
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

✅ **NEW (CLI)**:
```bash
hyper2kvm --cmd local \
    --vmdk /vms/server.vmdk \
    --output-dir /kvm \
    --to-output server.qcow2 \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --compress
```

### Pattern 2: Batch Migration
❌ **OLD**:
```bash
hyper2kvm batch execute batch-config.yaml --parallel 5
hyper2kvm batch status batch-config.yaml
hyper2kvm batch report --format markdown
```

✅ **NEW**:
```yaml
# batch.yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
batch_continue_on_error: true
output_dir: /vms/batch
```
```bash
hyper2kvm --config batch.yaml
```

### Pattern 3: Live Migration
❌ **OLD** (NOT IMPLEMENTED):
```bash
hyper2kvm live analyze /vms/db.vmdk
hyper2kvm live migrate /vms/db.vmdk --target /kvm/db.qcow2
hyper2kvm live rollback /vms/db.vmdk
```

✅ **NEW** (Use live-fix instead):
```yaml
# live-fix.yaml
command: live-fix
host: 192.168.1.100
user: root
identity: ~/.ssh/id_rsa
fstab_mode: stabilize-all
regen_initramfs: true
```
```bash
hyper2kvm --config live-fix.yaml
```

### Pattern 4: Validation
❌ **OLD** (NOT IMPLEMENTED as standalone):
```bash
hyper2kvm validate /kvm/server.qcow2 \
    --check-boot \
    --check-services \
    --check-databases
```

✅ **NEW** (Use libvirt-test instead):
```yaml
# migration.yaml
command: local
vmdk: /vms/server.vmdk
output_dir: /kvm
to_output: server.qcow2
libvirt_test: true
vm_name: test-vm
timeout: 300
```

### Pattern 5: Backup Restore
❌ **OLD** (NOT IMPLEMENTED):
```bash
hyper2kvm backup restore \
    --source veeam:///backups/repo \
    --vm prod-app
hyper2kvm backup list --source veeam:///backups
```

✅ **REMOVE** - Feature not implemented

### Pattern 6: Container Extraction
❌ **OLD** (NOT IMPLEMENTED):
```bash
hyper2kvm container extract /vms/docker-host.qcow2 \
    --output-dir /k8s/manifests \
    --generate-manifests
```

✅ **REMOVE** - Feature not implemented

## Available --cmd Values

Actual implementation supports:
- `local` - Local VMDK/disk migration
- `fetch-and-fix` - SSH fetch from ESXi
- `ova` - OVA extraction
- `ovf` - OVF extraction
- `vhd` - VHD import
- `ami` - AMI/cloud archive import
- `live-fix` - SSH-based live fixing
- `vsphere` - vSphere operations
- `azure` - Azure operations
- `daemon` - Daemon mode
- `generate-systemd` - Systemd unit generation

## Recommended Approach

For each file:
1. Read the file
2. Identify all incorrect CLI examples
3. Replace with YAML config + `hyper2kvm --config` OR `--cmd` approach
4. Remove references to non-existent features
5. Verify examples are realistic and working

## Files Remaining: 11

Priority order:
1. docs/recipes/01-common-scenarios.md (highest user impact)
2. docs/tutorials/01-beginner-migration.md
3. docs/tutorials/02-intermediate-workflows.md
4. docs/guides/migration/quick-reference.md
5. docs/getting-started/01-Installation.md
6. docs/recipes/README.md
7. docs/features/enhanced-chroot.md
8. docs/HOW_HYPER2KVM_WORKS.md (verify)
9. docs/project/ECOSYSTEM.md
10. docs/development/live-migration-implementation-plan.md (mark aspirational)
11. docs/development/summaries/TESTS_COMPLETE_SUMMARY.md

Last updated: 2026-01-27
