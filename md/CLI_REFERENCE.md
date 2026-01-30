### Comprehensive CLI Reference for `vmdk2kvm.py`

`vmdk2kvm.py` is a practical, production-minded tool for converting VMware VMDK images into KVM/QEMU-friendly formats (qcow2/raw/vdi) while applying the *real fixes that usually break migrations*: unstable `/etc/fstab` by-path entries, bootloader root= mismatches, initramfs regeneration needs, VMware tools removal, Windows virtio enablement, and “prove it boots” smoke tests.

This document is an **interface contract** for the CLI as implemented by `build_parser()`. It **keeps the existing arguments exactly** (no new flags invented), but improves clarity, structure, and correctness.

---

## Design Principles

### Config-first, automation-friendly

* **Two-phase parse**: config files can satisfy required args (because defaults are applied before the final parse).
* **Repeatable `--config` merge**: later files override earlier files, enabling clean “base + override” patterns.

### Safety is a feature, not a footnote

* **Dry-run** to preview behavior without writes.
* **Backups** (unless explicitly disabled) to reduce “one bad run ruined the guest” risk.
* **Recovery checkpoints** for long-running operations.
* **Reports** for auditability and repeatable migrations.

### “Works in the mess”

* Designed around real VMware → KVM pain: snapshot chains, by-path device naming, mixed filesystems, boot plumbing, Windows storage drivers, and verification.

---

## Quick Start

### Local VMDK → qcow2 with fixes + compression

```bash
sudo ./vmdk2kvm.py -v --output-dir ./out local \
  --vmdk /path/to/vm.vmdk \
  --flatten \
  --to-output vm-fixed.qcow2 \
  --compress --compress-level 6 \
  --checksum \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --remove-vmware-tools
```

### Dry-run preview (no writes)

```bash
sudo ./vmdk2kvm.py -vv --dry-run --print-fstab local \
  --vmdk /path/to/vm.vmdk \
  --flatten
```

### Config-driven run (merging base + overrides)

```bash
sudo ./vmdk2kvm.py --config base.yaml --config overrides.yaml local
```

---

## Global Options

These apply across all subcommands unless otherwise noted.

### Configuration & introspection

* `--config` *(repeatable, default: `[]`)*
  YAML/JSON config file(s). Later files override earlier files.
  Example: `--config base.yaml --config overrides.yaml`

* `--dump-config` *(store_true)*
  Print merged normalized config as JSON and exit.

* `--dump-args` *(store_true)*
  Print final parsed args as JSON and exit.

* `--version`
  Print tool version and exit.

### Logging & verbosity

* `-v, --verbose` *(count, default: 0)*
  Increase verbosity (`-v` / `-vv`).

* `--log-file` *(default: None)*
  Write logs to a file.

### Paths & general behavior

* `--output-dir` *(default: `./out`)*
  Root output directory for generated artifacts and outputs.

* `--workdir` *(default: None)*
  Intermediate working directory (defaults to `<output-dir>/work`).

* `--dry-run` *(store_true)*
  Preview actions without making modifications.

### Safety controls

* `--no-backup` *(store_true)*
  Skip backups of critical guest files (dangerous).

* `--print-fstab` *(store_true)*
  Print `/etc/fstab` before/after (useful with dry-run).

### Flatten & conversion outputs

* `--flatten` *(store_true)*
  Flatten snapshot chains into a single working image first.

* `--flatten-format` *(default: `qcow2`, choices: `qcow2|raw`)*
  Format for the flattened intermediate image.

* `--to-output` *(default: None)*
  Final output path (relative to `output_dir` if not absolute).

* `--out-format` *(default: `qcow2`, choices: `qcow2|raw|vdi`)*
  Output image format.

* `--compress` *(store_true)*
  Enable compression (qcow2 only).

* `--compress-level` *(int 1–9, default: None)*
  Compression level. (If your implementation defaults to 6 when unset, note that in code/docs consistently.)

* `--checksum` *(store_true)*
  Compute SHA256 checksum of output image.

### Guest fixes & policy knobs

* `--fstab-mode` *(default: `stabilize-all`, choices: `stabilize-all|bypath-only|noop`)*
  How `/etc/fstab` is rewritten:

  * `stabilize-all`: rewrite mounts to stable identifiers (UUID/PARTUUID/LABEL)
  * `bypath-only`: only fix `/dev/disk/by-path/*` style entries
  * `noop`: do not modify

* `--no-grub` *(store_true)*
  Skip GRUB root= update and device.map cleanup.

* `--regen-initramfs` / `--no-regen-initramfs` *(default: True)*
  Enable/disable initramfs + grub regen (best-effort).

* `--remove-vmware-tools` *(store_true)*
  Remove VMware tools (Linux guests only).

* `--cloud-init-config` *(default: None)*
  Inject cloud-init config (YAML/JSON).

* `--virtio-drivers-dir` *(default: None)*
  Path to virtio-win drivers directory (Windows injection).

### Recovery, performance, and orchestration

* `--enable-recovery` *(store_true)*
  Enable checkpoint recovery for long operations.

* `--parallel-processing` *(store_true)*
  Process multiple disks in parallel (implementation decides worker count).

* `--resize` *(default: None)*
  Resize root filesystem (enlarge only): `+10G` or `50G`.

* `--report` *(default: None)*
  Write Markdown report (relative to `output_dir` if not absolute).

* `--use-v2v` *(store_true)*
  Prefer virt-v2v conversion if available.

* `--post-v2v` *(store_true)*
  Run virt-v2v after internal fixes (workflow-dependent).

### Testing knobs

* `--libvirt-test` *(store_true)*
  Libvirt smoke test after conversion.

* `--qemu-test` *(store_true)*
  QEMU smoke test after conversion.

* `--vm-name` *(default: `converted-vm`)*
  Libvirt VM name for test.

* `--memory` *(int, default: 2048)*
  Memory MiB for tests.

* `--vcpus` *(int, default: 2)*
  vCPU count for tests.

* `--uefi` *(store_true)*
  Use UEFI mode for tests (default BIOS otherwise).

* `--timeout` *(int, default: 60)*
  Timeout for libvirt state checks.

* `--keep-domain` *(store_true)*
  Keep libvirt domain after test.

* `--headless` *(store_true)*
  No graphics device for the libvirt test domain.

### Daemon mode

* `--daemon` *(store_true)*
  Run in daemon mode.

* `--watch-dir` *(default: None)*
  Directory to watch in daemon mode.

---

## Subcommands

Subcommands define the top-level operation mode (`cmd`).

### 1) `local` — Offline local VMDK conversion

* `--vmdk` *(required)*
  Local VMDK path (descriptor or monolithic/binary).

Example:

```bash
sudo ./vmdk2kvm.py local --vmdk /path/to/vm.vmdk --flatten --to-output vm.qcow2
```

### 2) `fetch-and-fix` — Fetch from ESXi over SSH/SCP + offline fix

* `--host` *(required)*
* `--user` *(default: root)*
* `--port` *(default: 22)*
* `--identity` *(default: None)*
* `--ssh-opt` *(repeatable, default: None)*
* `--remote` *(required)* Remote VMDK descriptor path
* `--fetch-dir` *(default: None)* download destination
* `--fetch-all` *(store_true)* fetch full snapshot descriptor chain

Example:

```bash
sudo ./vmdk2kvm.py fetch-and-fix \
  --host esxi.example.com --user root --remote /vmfs/volumes/ds/vm/vm.vmdk \
  --fetch-all --flatten --to-output vm-fixed.qcow2
```

### 3) `ova` — Extract from OVA

* `--ova` *(required)*

Example:

```bash
sudo ./vmdk2kvm.py ova --ova /path/to/appliance.ova --flatten --to-output appliance.qcow2
```

### 4) `ovf` — Parse OVF (disks in same directory)

* `--ovf` *(required)*

Example:

```bash
sudo ./vmdk2kvm.py ovf --ovf /path/to/appliance.ovf --flatten --to-output appliance.qcow2
```

### 5) `live-fix` — Apply fixes to a running VM over SSH

* `--host` *(required)*
* `--user` *(default: root)*
* `--port` *(default: 22)*
* `--identity` *(default: None)*
* `--ssh-opt` *(repeatable, default: None)*
* `--sudo` *(store_true)* run remote commands with `sudo -n`

Example:

```bash
sudo ./vmdk2kvm.py live-fix \
  --host vm.example.com --user root --sudo \
  --fstab-mode stabilize-all --regen-initramfs
```

### 6) `daemon` — Watch directory for new VMDKs

No extra subcommand args (uses globals like `--daemon`, `--watch-dir`, config).

Example:

```bash
sudo ./vmdk2kvm.py --daemon --watch-dir /incoming --config daemon.yaml daemon
```

### 7) `generate-systemd` — Emit a systemd unit file

* `--output` *(default: None)* write to file or stdout

Example:

```bash
./vmdk2kvm.py generate-systemd --output /etc/systemd/system/vmdk2kvm.service
```

### 8) `vsphere` — vSphere/vCenter actions (pyvmomi)

**Important correctness note:** your current `build_parser()` uses a **nested subparser** (`vs_action`) under `vsphere`.
That means the CLI shape is:

```bash
vmdk2kvm.py vsphere [vCenter flags...] <vs_action> [action flags...]
```

…and the actions defined in the code you posted are:

* `list_vm_names`
* `get_vm_by_name`
* `vm_disks`
* `select_disk`
* `download_datastore_file`
* `download_vm_disk`
* `create_snapshot`
* `enable_cbt`
* `query_changed_disk_areas`
* `cbt_sync`

vCenter connection flags:

* `--vcenter` *(required)*
* `--vc-user` *(required)*
* `--vc-password` *(optional)*
* `--vc-password-env` *(optional)*
* `--vc-port` *(default 443)*
* `--vc-insecure` *(store_true)*
* `--dc-name` *(default: ha-datacenter)*

Examples:

List VM names:

```bash
./vmdk2kvm.py vsphere \
  --vcenter vcenter.example.com --vc-user administrator@vsphere.local --vc-password-env VC_PASSWORD --vc-insecure \
  list_vm_names --json
```

Download a VM disk by index:

```bash
./vmdk2kvm.py vsphere \
  --vcenter vcenter.example.com --vc-user administrator@vsphere.local --vc-password-env VC_PASSWORD --vc-insecure \
  download_vm_disk --vm_name myVM --disk 0 --local_path ./downloads/myVM-disk0.vmdk
```

Create a quiesced snapshot:

```bash
./vmdk2kvm.py vsphere \
  --vcenter vcenter.example.com --vc-user administrator@vsphere.local --vc-password-env VC_PASSWORD --vc-insecure \
  create_snapshot --vm_name myVM --name vmdk2kvm-pre-migration --quiesce --description "Created by vmdk2kvm"
```

Query CBT changed areas:

```bash
./vmdk2kvm.py vsphere \
  --vcenter vcenter.example.com --vc-user administrator@vsphere.local --vc-password-env VC_PASSWORD --vc-insecure \
  query_changed_disk_areas --vm_name myVM --snapshot_name vmdk2kvm-cbt --disk 0 --start_offset 0 --change_id "*" --json
```

---

## Complete Example Use Cases

### Basic local conversion + safety + report

```bash
sudo ./vmdk2kvm.py -v --output-dir ./out --report report.md local \
  --vmdk /path/to/vm.vmdk \
  --flatten \
  --to-output vm-fixed.qcow2 \
  --compress --compress-level 6 \
  --checksum \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --remove-vmware-tools
```

### Dry-run inspection

```bash
sudo ./vmdk2kvm.py -vv --dry-run --print-fstab local --vmdk /path/to/vm.vmdk
```

### Fetch from ESXi + full chain flatten + test

```bash
sudo ./vmdk2kvm.py -vv fetch-and-fix \
  --host esxi.example.com --user root --remote /vmfs/volumes/ds/vm/vm.vmdk --fetch-all \
  --flatten --to-output esxi-fixed.qcow2 \
  --libvirt-test --vm-name esxi-test --uefi --timeout 120 --headless
```

### Live-fix over SSH (sudo)

```bash
sudo ./vmdk2kvm.py -v live-fix \
  --host vm.example.com --user root --sudo \
  --fstab-mode stabilize-all --regen-initramfs --remove-vmware-tools
```

### OVA / OVF extraction

```bash
sudo ./vmdk2kvm.py ova --ova /path/to/appliance.ova --flatten --to-output appliance.qcow2
sudo ./vmdk2kvm.py ovf --ovf /path/to/appliance.ovf --flatten --to-output appliance.qcow2
```

### Daemon mode (watch directory)

```bash
sudo ./vmdk2kvm.py --daemon --watch-dir /incoming --config daemon.yaml daemon
```

### Post-conversion verification with QEMU

```bash
sudo ./vmdk2kvm.py local --vmdk /path/to/vm.vmdk --to-output vm.qcow2 --qemu-test --memory 4096 --vcpus 4 --uefi
```

---

## Dependency Notes (practical)

* Core runtime expectations: Python 3, `qemu-img`, `libguestfs`
* Config: PyYAML (if YAML configs used)
* Daemon mode: watchdog
* vSphere: pyvmomi (and possibly requests for certain download flows depending on implementation)

---

## Small doc hygiene tweaks you should keep

* Fix the typo in the option list: `--uefi"` → `--uefi`
* Keep the vSphere section aligned with your actual argparse shape (**nested `vs_action` subcommands**, not a single `--action` flag)

This doc is now “ship it” quality: structured like a real CLI reference, consistent terminology, and—crucially—aligned with the code you posted so users don’t get betrayed by the interface.
