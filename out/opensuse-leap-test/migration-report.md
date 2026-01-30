# hyper2kvm Report

## Run Metadata
```json
{
  "dry_run": false,
  "fstab_mode": "stabilize-all",
  "image": "/home/ssahani/vmware/Clone of openSUSE_Leap_15.4_VM_LinuxVMImages.COM/openSUSE_Leap_15.4_VM_LinuxVMImages.COM-cl1.vmdk",
  "inspect_root": "/dev/nbd2p2",
  "no_backup": false,
  "print_fstab": false,
  "regen_initramfs": true,
  "remove_vmware_tools": false,
  "resize": null,
  "root_btrfs_subvol": null,
  "root_dev": "/dev/nbd2p2",
  "timestamps": {
    "end": "2026-01-26T08:52:18.565589",
    "start": "2026-01-26T08:51:48.022978"
  },
  "update_grub": true,
  "version": "0.1.0",
  "virtio_drivers_dir": null
}
```

## Host Context (best-effort)
```json
{
  "cwd": "/home/ssahani/tt/hyper2kvm",
  "uid": 0,
  "user": "root"
}
```

## Tool Inventory (host)
```json
{
  "python": {
    "executable": "/usr/sbin/python",
    "version": "3.14.2 (main, Dec  5 2025, 00:00:00) [GCC 15.2.1 20251111 (Red Hat 15.2.1-4)]"
  },
  "qemu-img": {
    "path": "/usr/sbin/qemu-img"
  },
  "qemu-system-x86_64": {
    "path": "/usr/sbin/qemu-system-x86_64"
  },
  "rsync": {
    "path": "/usr/sbin/rsync"
  },
  "sgdisk": {
    "path": "/usr/sbin/sgdisk"
  },
  "virsh": {
    "path": "/usr/sbin/virsh"
  }
}
```

## Summary

- Image: `/home/ssahani/vmware/Clone of openSUSE_Leap_15.4_VM_LinuxVMImages.COM/openSUSE_Leap_15.4_VM_LinuxVMImages.COM-cl1.vmdk`
- Root: `/dev/nbd2p2`
- Dry-run: `False`
- fstab changes: `0`
- crypttab changes: `0`
- network files updated: `0`
- grub root updated: `0`
- stale device.map removed: `0`
- vmware tools removed: `False`
- cloud-init injected: `False`

## Validation

### Validation Results
```json
{
  "results": {
    "exit_code": {
      "critical": false,
      "details": {
        "raw": "0"
      },
      "passed": false
    },
    "failed_critical": {
      "critical": false,
      "details": {},
      "passed": false
    },
    "ok": {
      "critical": false,
      "details": {},
      "passed": true
    },
    "results": {
      "critical": false,
      "details": {
        "boot_files_present": {
          "attempts": 1,
          "critical": true,
          "duration_s": 0.0,
          "mode": "inprocess",
          "passed": true,
          "result": true,
          "result_truncated": false,
          "skip_reason": null,
          "skipped": false,
          "tags": [],
          "terminated": false,
          "timed_out": false
        },
        "fstab_exists": {
          "attempts": 1,
          "critical": true,
          "duration_s": 0.0,
          "mode": "inprocess",
          "passed": true,
          "result": true,
          "result_truncated": false,
          "skip_reason": null,
          "skipped": false,
          "tags": [],
          "terminated": false,
          "timed_out": false
        },
        "initramfs_tools": {
          "attempts": 1,
          "critical": false,
          "duration_s": 0.136,
          "mode": "inprocess",
          "passed": true,
          "result": true,
          "result_truncated": false,
          "skip_reason": null,
          "skipped": false,
          "tags": [],
          "terminated": false,
          "timed_out": false
        },
        "kernel_present": {
          "attempts": 1,
          "critical": true,
          "duration_s": 0.488,
          "mode": "inprocess",
          "passed": true,
          "result": true,
          "result_truncated": false,
          "skip_reason": null,
          "skipped": false,
          "tags": [],
          "terminated": false,
          "timed_out": false
        }
      },
      "passed": false
    },
    "stats": {
      "critical": false,
      "details": {
        "by_tag": {
          "_untagged": {
            "executed": 4,
            "failed": 0,
            "passed": 4,
            "skipped": 0,
            "total": 4
          }
        },
        "duration_s": 0.625,
        "failed": 0,
        "skipped": 0,
        "slowest": [
          {
            "duration_s": 0.488,
            "mode": "inprocess",
            "name": "kernel_present"
          },
          {
            "duration_s": 0.136,
            "mode": "inprocess",
            "name": "initramfs_tools"
          },
          {
            "duration_s": 0.0,
            "mode": "inprocess",
            "name": "fstab_exists"
          },
          {
            "duration_s": 0.0,
            "mode": "inprocess",
            "name": "boot_files_present"
          }
        ],
        "total": 4
      },
      "passed": true
    }
  },
  "summary": {
    "critical_failed": 0,
    "failed": 3,
    "ok": false,
    "passed": 2,
    "total": 5
  }
}
```

### Failed Checks

- Critical failed: `none`
- Non-critical failed: failed_critical, results, exit_code

## Changes
```json
{
  "cloud_init_injected": {
    "enabled": false
  },
  "crypttab": 0,
  "firstboot_scripts_injected": {
    "injected": false,
    "reason": "no_config"
  },
  "fstab": 0,
  "grub_device_map_removed": 0,
  "grub_root": 0,
  "hostname_config_injected": {
    "injected": false,
    "reason": "no_config"
  },
  "network": {
    "analysis": {
      "recommendations": [
        "No network configuration files found. Manual network setup may be required."
      ],
      "stats": {
        "backups_created": 0,
        "by_type": {},
        "details": [],
        "dry_run": false,
        "files_failed": 0,
        "files_modified": 0,
        "total_files": 0,
        "total_fixes_applied": 0
      },
      "warnings": []
    },
    "count": 0,
    "updated_files": []
  },
  "network_config_injected": {
    "injected": false,
    "reason": "no_files"
  },
  "service_config_injected": {
    "injected": false,
    "reason": "no_config"
  },
  "user_config_injected": {
    "injected": false,
    "reason": "no_config"
  },
  "vmware_tools_removed": {
    "enabled": false
  }
}
```

### /etc/crypttab
- Changes: `0`

### Network Config
- Updated files: `0`
## Analysis

### Disk Usage
```json
{
  "analysis": "success",
  "free_gb": 503.8830146789551,
  "recommend_cleanup": false,
  "recommend_resize": false,
  "total_gb": 509.990234375,
  "used_gb": 6.107219696044922,
  "used_percent": 1.2
}
```

### mdraid
```json
{
  "present": false
}
```

### Windows
```json
{
  "enabled": false,
  "skipped": "not_windows"
}
```

### Virtio Injection
```json
{
  "enabled": false,
  "skipped": "not_windows"
}
```

### Initramfs/GRUB Regeneration
```json
{
  "bls": false,
  "boot_mounts": {
    "attempted": true,
    "errors": [],
    "mounted": []
  },
  "bootloader": {
    "attempts": [
      {
        "cmd": [
          "grub2-mkconfig",
          "-o",
          "/boot/grub2/grub.cfg"
        ],
        "ok": false,
        "out": "Command failed: sudo chroot /tmp/hyper2kvm-guestfs-qxk3ohiu grub2-mkconfig -o /boot/grub2/grub.cfg (command=sudo chroot /tmp/hyper2kvm-guestfs-qxk3ohiu grub2-mkconfig -o /boot/grub2/grub.cfg, returncode=1, stdout=None, stderr=awk: fatal: cannot open file `/proc/self/mountinfo' for reading (No such file or directory)\n/usr/sbin/grub2-probe: error: cannot find a device for / (is /dev mounted?).\n)"
      },
      {
        "cmd": [
          "grub2-install",
          "--recheck"
        ],
        "ok": false,
        "out": "Command failed: sudo chroot /tmp/hyper2kvm-guestfs-qxk3ohiu grub2-install --recheck (command=sudo chroot /tmp/hyper2kvm-guestfs-qxk3ohiu grub2-install --recheck, returncode=1, stdout=None, stderr=Installing for i386-pc platform.\ngrub2-install: error: install device isn't specified.\n)"
      },
      {
        "cmd": [
          "bootctl",
          "status"
        ],
        "ok": true,
        "out": "System:\n    Not booted with EFI\n\n"
      }
    ],
    "success": true
  },
  "device_map_removed": 0,
  "distro": "opensuse-leap",
  "dry_run": false,
  "enabled": true,
  "family": "suse",
  "guest_boot": "bios",
  "guest_kernels": [
    "5.14.21-150400.22-default"
  ],
  "initramfs": {
    "attempts": [
      {
        "cmd": [
          "dracut",
          "-f",
          "--kver",
          "5.14.21-150400.22-default",
          "--add-drivers",
          "virtio virtio_ring virtio_blk virtio_scsi virtio_net virtio_pci nvme ahci sd_mod dm_mod dm_crypt xts"
        ],
        "ok": true,
        "out": ""
      }
    ],
    "success": true
  },
  "initramfs_add_drivers": [
    "virtio",
    "virtio_ring",
    "virtio_blk",
    "virtio_scsi",
    "virtio_net",
    "virtio_pci",
    "nvme",
    "ahci",
    "sd_mod",
    "dm_mod",
    "dm_crypt",
    "xts"
  ],
  "initramfs_driver_injection": {
    "actions": [
      {
        "changed": false,
        "note": "dracut_dropin_already_present",
        "path": "/etc/dracut.conf.d/hyper2kvm-drivers.conf"
      },
      {
        "changed": false,
        "path": "/etc/modules-load.d/hyper2kvm.conf",
        "reason": "already_present"
      }
    ],
    "drivers": [
      "virtio",
      "virtio_ring",
      "virtio_blk",
      "virtio_scsi",
      "virtio_net",
      "virtio_pci",
      "nvme",
      "ahci",
      "sd_mod",
      "dm_mod",
      "dm_crypt",
      "xts"
    ],
    "warnings": []
  },
  "major": 15,
  "root_update_changed": 0,
  "sanity": {
    "boot": {
      "boot_ls": [
        ".vmlinuz-5.14.21-150400.22-default.hmac",
        "System.map-5.14.21-150400.22-default",
        "boot.readme",
        "config-5.14.21-150400.22-default",
        "grub2",
        "initrd",
        "initrd-5.14.21-150400.22-default",
        "symvers-5.14.21-150400.22-default.gz",
        "sysctl.conf-5.14.21-150400.22-default",
        "vmlinux-5.14.21-150400.22-default.gz",
        "vmlinuz",
        "vmlinuz-5.14.21-150400.22-default"
      ]
    }
  }
}
```

### Cloud-init
```json
{
  "enabled": false
}
```

### VMware Tools Removal
```json
{
  "enabled": false
}
```

## Next Actions (hints)
- GRUB root= may not have been updated (no match found). Verify kernel cmdline in grub.cfg.
- If the guest still fails to boot, run initramfs+grub regen inside the VM once after first boot (or re-run with --regen-initramfs).

