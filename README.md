# vmdk2kvm.py Use Cases

This Markdown document provides a comprehensive overview of all use cases for the `vmdk2kvm.py` tool, based on its features, commands, and capabilities. The tool is designed for converting and fixing VMware VMDK images for KVM/QEMU environments, with support for various input sources, fixes, outputs, and automation. Use cases are categorized for clarity, including multiple examples of CLI commands, configuration files, and variations for different scenarios.

## 1. **Offline Conversion from Local VMDK**
   - **Description**: Convert and fix a local VMDK file (descriptor or monolithic) offline using libguestfs. This includes flattening snapshots, rewriting fstab/crypttab, GRUB updates, initramfs regeneration, VMware tools removal, virtio driver injection (for Windows), network config fixes, and optional output conversion to qcow2/raw/vdi.
   - **When to Use**: When you have a local VMDK and want to prepare it for KVM without running the VM.
   - **Key Features Involved**: Flattening, filesystem/boot fixes, Windows BCD, virtio injection, compression, checksum, resize, reports.
   - **Example CLI (Basic Conversion)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk path/to/vm.vmdk --output-dir ./out --to-output vm-fixed.qcow2 --out-format qcow2
     ```
   - **Example CLI (With Flattening and Fixes)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk path/to/snapshot-vm.vmdk --flatten --flatten-format raw --regen-initramfs --remove-vmware-tools --fstab-mode stabilize-all
     ```
   - **Example CLI (Windows-Specific with Virtio Injection)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk path/to/windows-vm.vmdk --virtio-drivers-dir /path/to/virtio-win --resize 50G --checksum
     ```
   - **Example CLI (Dry-Run with Report)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk path/to/vm.vmdk --dry-run --print-fstab --report migration-report.md
     ```
   - **Config Example (Basic YAML)**:
     ```yaml
     command: local
     vmdk: path/to/vm.vmdk
     to_output: vm-fixed.qcow2
     out_format: qcow2
     ```
   - **Config Example (Advanced with Multiple Options)**:
     ```yaml
     command: local
     vmdk: path/to/vm.vmdk
     flatten: true
     flatten_format: qcow2
     regen_initramfs: true
     remove_vmware_tools: true
     resize: +20G
     cloud_init_config: cloud-config.yaml
     ```

## 2. **Fetching and Fixing from Remote ESXi Host**
   - **Description**: Fetch VMDK descriptor (and optionally full snapshot chain) from a remote ESXi host via SSH/SCP, then perform offline fixes and conversion.
   - **When to Use**: Migrating VMs from ESXi without manual download; handles snapshot chains automatically.
   - **Key Features Involved**: SSH fetching, recursive parent fetch, all offline fixes.
   - **Example CLI (Basic Fetch)**:
     ```
     sudo ./vmdk2kvm.py fetch-and-fix --host esxi.example.com --user root --remote /vmfs/volumes/datastore1/vm/vm.vmdk --to-output vm-fixed.qcow2
     ```
   - **Example CLI (With Full Chain and Compression)**:
     ```
     sudo ./vmdk2kvm.py fetch-and-fix --host esxi-host --fetch-all --fetch-dir ./downloads --compress --compress-level 9 --checksum
     ```
   - **Example CLI (With Identity Key and Custom Port)**:
     ```
     sudo ./vmdk2kvm.py fetch-and-fix --host esxi-host --port 2222 --identity ~/.ssh/esxi_key --remote /path/to/vm.vmdk --regen-initramfs
     ```
   - **Example CLI (Dry-Run Fetch)**:
     ```
     sudo ./vmdk2kvm.py fetch-and-fix --host esxi-host --remote /path/to/vm.vmdk --dry-run --report fetch-report.md
     ```
   - **Config Example (YAML)**:
     ```yaml
     command: fetch-and-fix
     host: esxi.example.com
     remote: /vmfs/volumes/datastore1/vm/vm.vmdk
     fetch_all: true
     flatten: true
     ```

## 3. **Extracting and Converting from OVA Packages**
   - **Description**: Extract disks from an OVA file, parse the OVF manifest, and apply fixes/conversion to the extracted VMDKs.
   - **When to Use**: When VMs are exported as OVA from VMware/vSphere.
   - **Key Features Involved**: Tar extraction, OVF parsing, multi-disk handling, offline fixes.
   - **Example CLI (Basic Extraction)**:
     ```
     sudo ./vmdk2kvm.py ova --ova path/to/vm.ova --output-dir ./extracted-out --to-output extracted-vm.qcow2
     ```
   - **Example CLI (Parallel Processing for Multi-Disk)**:
     ```
     sudo ./vmdk2kvm.py ova --ova multi-disk-vm.ova --parallel-processing --flatten --resize +15G
     ```
   - **Example CLI (With Cloud-Init Injection)**:
     ```
     sudo ./vmdk2kvm.py ova --ova cloud-ready-vm.ova --cloud-init-config cloud-config.yaml --regen-initramfs
     ```
   - **Example CLI (UEFI Test After Extraction)**:
     ```
     sudo ./vmdk2kvm.py ova --ova vm.ova --libvirt-test --uefi --vm-name extracted-test --headless
     ```
   - **Config Example (YAML)**:
     ```yaml
     command: ova
     ova: path/to/vm.ova
     parallel_processing: true
     to_output: extracted-vm.qcow2
     ```

## 4. **Parsing and Converting from OVF (with Disks in Directory)**
   - **Description**: Parse an OVF file and process referenced disks in the same directory, applying fixes and conversion.
   - **When to Use**: For unpacked OVF exports where disks are already extracted.
   - **Key Features Involved**: XML parsing, multi-disk support, offline fixes.
   - **Example CLI (Basic Parsing)**:
     ```
     sudo ./vmdk2kvm.py ovf --ovf path/to/vm.ovf --to-output parsed-vm.qcow2 --out-format raw
     ```
   - **Example CLI (With VMware Removal and Report)**:
     ```
     sudo ./vmdk2kvm.py ovf --ovf vm.ovf --remove-vmware-tools --report ovf-report.md --checksum
     ```
   - **Example CLI (QEMU Smoke Test)**:
     ```
     sudo ./vmdk2kvm.py ovf --ovf vm.ovf --qemu-test --memory 4096 --vcpus 4
     ```
   - **Example CLI (No GRUB Updates)**:
     ```
     sudo ./vmdk2kvm.py ovf --ovf vm.ovf --no-grub --fstab-mode bypath-only
     ```
   - **Config Example (YAML)**:
     ```yaml
     command: ovf
     ovf: path/to/vm.ovf
     remove_vmware_tools: true
     ```

## 5. **Live Fixes on Running VM via SSH**
   - **Description**: Connect to a running VM over SSH (with optional sudo) and apply live fixes like fstab rewriting, GRUB updates, initramfs regeneration, and VMware tools removal. No offline mounting.
   - **When to Use**: When the VM is already running on KVM but needs in-place fixes (e.g., after a quick migration).
   - **Key Features Involved**: SSH-based commands, best-effort stable identifiers, distro-aware regeneration.
   - **Example CLI (Basic Live Fix)**:
     ```
     ./vmdk2kvm.py live-fix --host 192.168.1.100 --user admin --print-fstab
     ```
   - **Example CLI (With Sudo and Regeneration)**:
     ```
     ./vmdk2kvm.py live-fix --host vm-host --sudo --regen-initramfs --remove-vmware-tools
     ```
   - **Example CLI (Custom SSH Options)**:
     ```
     ./vmdk2kvm.py live-fix --host vm-host --port 2222 --identity ~/.ssh/key --ssh-opt "-o StrictHostKeyChecking=no"
     ```
   - **Example CLI (No GRUB, Verbose)**:
     ```
     ./vmdk2kvm.py live-fix --host vm-host --no-grub -vv
     ```
   - **Config Example (YAML)**:
     ```yaml
     command: live-fix
     host: vm-host
     sudo: true
     regen_initramfs: true
     ```

## 6. **Multi-VM Batch Processing via Config**
   - **Description**: Define multiple VMs in a single YAML/JSON config and process them sequentially, with overrides from multiple config files.
   - **When to Use**: Batch migrations of several VMs with shared or custom settings.
   - **Key Features Involved**: Config merging, multi-VM support in 'vms' list.
   - **Config Example (Basic Multi-VM YAML)**:
     ```yaml
     vms:
       - vmdk: vm1.vmdk
         to_output: vm1.qcow2
       - vmdk: vm2.vmdk
         to_output: vm2.qcow2
     flatten: true
     ```
   - **Config Example (With Overrides and Fixes)**:
     ```yaml
     vms:
       - vmdk: linux-vm.vmdk
         resize: +5G
         remove_vmware_tools: true
       - vmdk: windows-vm.vmdk
         virtio_drivers_dir: /path/to/virtio
         out_format: raw
     compress: true
     regen_initramfs: true
     ```
   - **Config Example (Merging Multiple Files)**: Run with `--config base.yaml --config overrides.yaml`
     - base.yaml:
       ```yaml
       flatten: true
       out_format: qcow2
       ```
     - overrides.yaml:
       ```yaml
       vms:
         - vmdk: vm3.vmdk
           to_output: vm3-fixed.qcow2
       compress_level: 8
       ```

## 7. **Daemon Mode for Automated Processing**
   - **Description**: Run as a background service (e.g., via systemd) watching a directory for new VMDK files, automatically processing them upon detection.
   - **When to Use**: In automated workflows where VMDKs are dropped into a folder (e.g., from exports or backups).
   - **Key Features Involved**: Watchdog monitoring, systemd integration.
   - **Example CLI (Daemon with Watch Dir)**:
     ```
     sudo ./vmdk2kvm.py daemon --watch-dir /var/vmdks --config auto-config.yaml
     ```
   - **Example CLI (Generate Systemd Unit)**:
     ```
     ./vmdk2kvm.py generate-systemd --output /etc/systemd/system/vmdk2kvm.service
     ```
   - **Config Example for Daemon (YAML)**:
     ```yaml
     flatten: true
     to_output: auto-fixed.qcow2
     regen_initramfs: true
     ```

## 8. **Integration with virt-v2v**
   - **Description**: Use virt-v2v for conversion if available, with fallback to internal fixer; optional post-internal-fix run of virt-v2v.
   - **When to Use**: Leveraging libvirt's virt-v2v for advanced conversions while applying custom fixes.
   - **Key Features Involved**: --use-v2v and --post-v2v flags.
   - **Example CLI (Use virt-v2v First)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk vm.vmdk --use-v2v --compress
     ```
   - **Example CLI (Post-Fix virt-v2v)**:
     ```
     sudo ./vmdk2kvm.py ova --ova vm.ova --post-v2v --parallel-processing
     ```

## 9. **Windows-Specific Migrations**
   - **Description**: Handle Windows guests with BCD edits, virtio driver injection, and registry modifications for KVM compatibility.
   - **When to Use**: Migrating Windows VMs; specify virtio drivers directory.
   - **Key Features Involved**: Windows detection, BCD backups, hivex for registry edits.
   - **Example CLI (Basic Windows)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk windows-vm.vmdk --virtio-drivers-dir /iso/virtio-win
     ```
   - **Example CLI (With Resize and Test)**:
     ```
     sudo ./vmdk2kvm.py local --vmdk win10.vmdk --virtio-drivers-dir /path/to/drivers --resize 100G --libvirt-test --uefi
     ```

## 10. **Cloud-Init Injection for Cloud Readiness**
    - **Description**: Inject cloud-init configurations into the guest for cloud environments (e.g., AWS, Azure).
    - **When to Use**: Preparing images for cloud deployment; installs cloud-init if missing.
    - **Key Features Involved**: YAML/JSON config injection, optional auto-install.
    - **Example CLI (Basic Injection)**:
      ```
      sudo ./vmdk2kvm.py local --vmdk cloud-vm.vmdk --cloud-init-config user-data.yaml
      ```
    - **Example CLI (With Install if Missing)**: Assume config has `install_if_missing: true`.
      ```
      sudo ./vmdk2kvm.py local --vmdk vm.vmdk --cloud-init-config full-cloud.yaml
      ```
    - **Config Example (YAML for Cloud-Init)**:
      ```yaml
      cloud_init_config: path/to/config.yaml
      ```

## 11. **Testing Converted Images**
    - **Description**: Perform smoke tests with libvirt (define/start domain) or direct QEMU launch, supporting UEFI/BIOS, headless mode.
    - **When to Use**: Verifying bootability post-conversion.
    - **Key Features Involved**: --libvirt-test, --qemu-test, customizable VM specs.
    - **Example CLI (Libvirt Test)**:
      ```
      sudo ./vmdk2kvm.py local --vmdk vm.vmdk --libvirt-test --vm-name test-vm --memory 4096 --vcpus 4 --timeout 120
      ```
    - **Example CLI (QEMU Test with UEFI)**:
      ```
      sudo ./vmdk2kvm.py local --vmdk vm.vmdk --qemu-test --uefi
      ```
    - **Example CLI (Keep Domain After Test)**:
      ```
      sudo ./vmdk2kvm.py ova --ova vm.ova --libvirt-test --keep-domain
      ```

## 12. **Safety and Recovery Features**
    - **Description**: Use dry-run for previews, enable checkpoints for recovery, generate reports, and parallel process multi-disk VMs.
    - **When to Use**: In production for error-prone migrations; recover from interruptions.
    - **Key Features Involved**: --dry-run, --enable-recovery, --report, --parallel-processing.
    - **Example CLI (Dry-Run with Recovery)**:
      ```
      sudo ./vmdk2kvm.py local --vmdk vm.vmdk --dry-run --enable-recovery --report dry-report.md
      ```
    - **Example CLI (Parallel with No Backup)**:
      ```
      sudo ./vmdk2kvm.py ova --ova multi.ova --parallel-processing --no-backup
      ```

## 13. **Generating Systemd Unit for Daemon**
    - **Description**: Create a systemd service file for running in daemon mode.
    - **When to Use**: Deploying as a service on Linux servers.
    - **Example CLI (Generate Unit)**:
      ```
      ./vmdk2kvm.py generate-systemd --output vmdk2kvm.service
      ```
    - **Example CLI (Custom Path in Unit)**: Edit the generated file to customize ExecStart.

These use cases cover the full spectrum of the tool's functionality, with variations for different needs like Windows, cloud, testing, and automation. For detailed options, run `./vmdk2kvm.py --help`. If a use case requires custom scripting, combine with configs for automation.
# vmdk2kvm
