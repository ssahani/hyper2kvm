# Windows Driver Injection Guide

This document explains how to inject VirtIO and additional PnP drivers into Windows VMs during migration from VMware to KVM.

## Overview

hyper2kvm supports injecting Windows drivers in two ways:
1. **Boot-critical drivers** (.sys files) - Injected directly into `System32\drivers` with registry entries
2. **PnP drivers** (INF packages) - Staged for installation on first boot via `pnputil`

## VirtIO Driver Injection

### Basic Configuration

```yaml
# Specify path to virtio-win drivers directory or ISO
virtio_drivers_dir: /path/to/virtio-win-extracted

# Optional: Custom driver configuration
virtio_config: /path/to/custom-virtio-config.yaml
```

### How It Works

1. **Driver Discovery**: Searches for drivers matching Windows version (w10, w11, w7, etc.)
2. **Binary Injection**: Copies .sys files to `C:\Windows\System32\drivers\`
3. **Registry Configuration**:
   - Adds services to `HKLM\SYSTEM\CurrentControlSet\Services`
   - Configures CriticalDeviceDatabase for storage drivers
   - Removes StartOverride values that could disable drivers
4. **Package Staging**: Stages INF/CAT/DLL files to `C:\hyper2kvm\drivers\virtio\<service>\`
5. **DevicePath Update**: Adds staging directory to SOFTWARE\Microsoft\Windows\CurrentVersion\DevicePath
6. **Firstboot Service**: Creates a Windows service that runs on first boot to install staged drivers

## Adding Additional PnP Drivers

The `virtio_drivers_dir` can contain **any Windows drivers**, not just VirtIO! Here's how to structure them:

### Method 1: Add to VirtIO Directory Structure

```bash
/path/to/drivers/
├── viostor/              # VirtIO SCSI
│   └── w10/amd64/
│       ├── viostor.sys
│       ├── viostor.inf
│       └── viostor.cat
├── NetKVM/               # VirtIO Network
│   └── w10/amd64/
│       ├── netkvm.sys
│       ├── netkvm.inf
│       └── netkvm.cat
└── CustomDriver/         # Your custom driver
    └── w10/amd64/
        ├── mydriver.sys
        ├── mydriver.inf
        └── mydriver.cat
```

Then define the custom driver in a YAML config:

```yaml
# custom-drivers.yaml
drivers:
  custom:  # New driver type category
    - name: MyDriver
      service: mydriver
      pattern: CustomDriver/w10/amd64/mydriver.sys
      class_guid: "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
      inf_hint: mydriver.inf
      start_type: demand  # or boot, system, auto, disabled
      pci_ids:
        - "pci#ven_XXXX&dev_YYYY"

buckets:
  w10:
    - w10
    - w11  # Fallback
```

Use it:

```yaml
# migration-config.yaml
virtio_drivers_dir: /path/to/drivers
virtio_config: /path/to/custom-drivers.yaml
```

### Method 2: INF-Only Drivers (No Binary Injection)

If you just want drivers installed via PnP (not injected as boot-critical), you can place them in the staging directory directly:

```yaml
# In your migration YAML
virtio_drivers_dir: /path/to/drivers
```

Structure:

```bash
/path/to/drivers/
├── MyDriver/
│   └── w10/amd64/
│       ├── driver.inf
│       ├── driver.cat
│       ├── driver.sys
│       └── driver.dll  # Optional coinstallers, etc.
```

The firstboot service will find and install all `*.inf` files recursively in:
- `C:\hyper2kvm\drivers\virtio\**\*.inf`

## Firstboot Service Details

### What It Does

The `hyper2kvm-firstboot` service runs once on first boot as LocalSystem and:

1. Searches for all INF files: `dir /b /s "C:\hyper2kvm\drivers\virtio\*.inf"`
2. Installs each driver: `pnputil /add-driver <path> /install`
3. Logs to: `C:\Windows\Temp\hyper2kvm-firstboot.log`
4. Writes completion marker: `C:\hyper2kvm\firstboot.done`
5. Self-deletes the service

### Manual Driver Installation

If the firstboot service fails, you can manually install drivers:

```cmd
REM Run as Administrator
cd C:\hyper2kvm\drivers\virtio

REM Install all drivers
for /r %i in (*.inf) do pnputil /add-driver "%i" /install

REM Or use the generated setup script
C:\hyper2kvm\setup.cmd
```

## Verification

### Check Drivers in C:\

Mount the converted QCOW2 and verify:

```bash
guestfish --ro -a win10-converted.qcow2 -m /dev/sda3
> ls /Windows/System32/drivers/ | grep -E "(viostor|vioscsi|netkvm|balloon)"
```

### Check Staged Drivers

```bash
> ls /hyper2kvm/drivers/virtio/
balloon/
netkvm/
vioscsi/
viostor/
```

### Check Firstboot Service

After conversion but before first boot:

```bash
> download /Windows/System32/config/SYSTEM SYSTEM.hive
# Use Registry Editor or hivexsh to check:
# HKLM\SYSTEM\ControlSet001\Services\hyper2kvm-firstboot
```

### Check DevicePath

```bash
> download /Windows/System32/config/SOFTWARE SOFTWARE.hive
# Check:
# HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\DevicePath
# Should contain: %SystemDrive%\hyper2kvm\drivers\virtio
```

## Troubleshooting

### Drivers Not Found

**Issue**: Firstboot log shows no drivers found

**Solution**: Check path structure matches:
```
C:\hyper2kvm\drivers\virtio\<service>\*.inf
```

**Fix**: Update `_DEFAULT_DRIVER_STAGE_DIR` in `registry/firstboot.py` (already fixed in latest version)

### Boot Failed / BSOD 0x0000007B

**Issue**: INACCESSIBLE_BOOT_DEVICE

**Causes**:
1. Storage drivers (viostor/vioscsi) not installed in registry
2. CriticalDeviceDatabase not populated
3. Wrong driver for controller type (virtio-scsi vs virtio-blk)

**Solution**:
- Check migration report: `virtio.drivers_found` should include `viostor` or `vioscsi`
- Verify registry edits: `virtio.registry_changes.success = true`
- Match VM disk controller to driver (virtio-scsi → vioscsi, virtio-blk → viostor)

### Drivers Not Installing

**Issue**: Windows boots but drivers not installed

**Causes**:
1. Firstboot service didn't run
2. Marker exists: `C:\hyper2kvm\firstboot.done`
3. pnputil failed (unsigned drivers, etc.)

**Solution**:
1. Check service: `sc query hyper2kvm-firstboot`
2. Check log: `C:\Windows\Temp\hyper2kvm-firstboot.log`
3. Delete marker and reboot: `del C:\hyper2kvm\firstboot.done`
4. Run manually: `C:\hyper2kvm\setup.cmd`

### Certificate/Signature Errors

**Issue**: pnputil fails with signature errors

**Solution**:
1. Disable driver signature enforcement (test mode):
   ```cmd
   bcdedit /set testsigning on
   ```

2. Or install cert from driver:
   ```cmd
   pnputil /add-driver driver.inf /install /subdirs
   ```

## Advanced: Custom Driver Definitions

For boot-critical drivers (storage, etc.), you need to define them in the VirtIO config:

```yaml
# virtio-config.yaml
drivers:
  storage:  # Must be one of: storage, network, balloon, input, gpu, filesystem, serial, rng
    - name: MyStorageDriver
      service: mystor
      pattern: MyStorageDriver/w10/amd64/mystor.sys
      class_guid: "{4D36E967-E325-11CE-BFC1-08002BE10318}"  # SCSI adapter class
      inf_hint: mystor.inf
      start_type: boot  # Critical for storage!
      type: kernel
      error_control: normal
      pci_ids:
        - "pci#ven_1234&dev_5678"
      critical_device_database: true  # Add to CDD for early binding

buckets:
  w10:
    - w10
    - w8.1
    - w8
```

## References

- [VirtIO Drivers Official](https://fedorapeople.org/groups/virt/virtio-win/)
- [Windows Driver Installation](https://docs.microsoft.com/en-us/windows-hardware/drivers/install/)
- [pnputil Documentation](https://docs.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil)
- [CriticalDeviceDatabase](https://docs.microsoft.com/en-us/windows-hardware/drivers/install/critical-device-database)

## Example YAML Configurations

### Basic VirtIO Only

```yaml
cmd: local
vmdk: /path/to/windows.vmdk
output_dir: /path/to/output
windows: true

# VirtIO drivers
virtio_drivers_dir: /usr/share/virtio-win

# Output
to_output: /path/to/output/windows-converted.qcow2
report: /path/to/output/report.md
```

### VirtIO + Custom Drivers

```yaml
cmd: local
vmdk: /path/to/windows.vmdk
output_dir: /path/to/output
windows: true

# VirtIO + custom drivers in same directory
virtio_drivers_dir: /path/to/all-drivers

# Custom driver definitions
virtio_config: /path/to/custom-drivers.yaml

# Output
to_output: /path/to/output/windows-converted.qcow2
report: /path/to/output/report.md
```

### Testing Without Conversion

```yaml
# Dry run to test driver injection only
dry_run: true
cmd: local
vmdk: /path/to/windows.vmdk
windows: true
virtio_drivers_dir: /path/to/virtio-win
report: /path/to/test-report.md
```

Check the report to verify:
- `virtio.injected: true`
- `virtio.drivers_found: [...]`
- `virtio.packages_staged: [...]`
- `virtio.firstboot.success: true`
