# Manifest Workflow Daemon - 3-Directory Processing

The manifest workflow daemon provides declarative, observable VM conversion processing using manifest files.

## Features

- **Declarative Pipeline**: Define entire conversion workflow in JSON/YAML
- **Clear State Tracking**: Manifests move through well-defined directories
- **Batch Processing**: Process multiple VMs with a single manifest
- **Detailed Reports**: JSON reports with artifact tracking
- **Error Handling**: Failed manifests with detailed error context

## Directory Structure

```
manifest_workflow_dir/
├── to_be_processed/   # Drop zone for manifest files (.json, .yaml)
├── processing/        # Active manifests being processed
├── processed/         # Completed manifests with reports
│   └── 2026-01-24/
│       ├── my-vm.json
│       └── my-vm.json.report.json
└── failed/            # Failed manifests with error details
    └── 2026-01-24/
        ├── bad-vm.json
        └── bad-vm.json.error.json
```

## Quick Start

### 1. Start the Manifest Workflow Daemon

```bash
# Using config file
sudo hyper2kvm --config manifest-daemon.yaml

# Or via command line
sudo hyper2kvm daemon \
  --manifest-workflow-mode \
  --manifest-workflow-dir /var/lib/hyper2kvm/manifest-workflow \
  --output-dir /var/lib/hyper2kvm/output \
  --max-concurrent-jobs 2
```

### 2. Drop Manifest Files

Create a manifest file describing your conversion:

```json
{
  "version": "1.0",
  "pipeline": {
    "load": {
      "source_type": "vmdk",
      "source_path": "/data/my-vm.vmdk"
    },
    "fix": {
      "fstab": {"enabled": true, "mode": "stabilize-all"},
      "grub": {"enabled": true},
      "initramfs": {"enabled": true, "regenerate": true}
    },
    "convert": {
      "output_format": "qcow2",
      "compress": true
    }
  }
}
```

Drop it into the queue:

```bash
cp my-vm-manifest.json /var/lib/hyper2kvm/manifest-workflow/to_be_processed/
```

### 3. Monitor Progress

```bash
# Watch directories
watch ls -lh /var/lib/hyper2kvm/manifest-workflow/*/

# Check logs
tail -f /var/log/hyper2kvm/manifest-daemon.log

# View completed reports
cat /var/lib/hyper2kvm/manifest-workflow/processed/2026-01-24/my-vm.json.report.json
```

## Manifest Format

### Simple VM Manifest

```json
{
  "version": "1.0",
  "pipeline": {
    "load": {
      "source_type": "vmdk|ova|ovf|vhd|vhdx|raw|ami",
      "source_path": "/path/to/disk"
    },
    "inspect": {
      "enabled": true,
      "detect_os": true
    },
    "fix": {
      "fstab": {
        "enabled": true,
        "mode": "stabilize-all|bypath-only|noop"
      },
      "grub": {
        "enabled": true
      },
      "initramfs": {
        "enabled": true,
        "regenerate": true
      },
      "network": {
        "enabled": true,
        "fix_level": "full|basic|none"
      }
    },
    "convert": {
      "output_format": "qcow2|raw|vdi",
      "compress": true,
      "output_path": "optional-custom-name.qcow2"
    },
    "validate": {
      "enabled": true,
      "boot_test": false
    }
  }
}
```

### Batch Manifest

Process multiple VMs with different settings:

```json
{
  "version": "1.0",
  "batch": true,
  "vms": [
    {
      "name": "vm1",
      "pipeline": {
        "load": {"source_type": "vmdk", "source_path": "/data/vm1.vmdk"},
        "fix": {"fstab": {"enabled": true}},
        "convert": {"output_format": "qcow2", "compress": true}
      }
    },
    {
      "name": "vm2",
      "pipeline": {
        "load": {"source_type": "vhd", "source_path": "/data/vm2.vhd"},
        "convert": {"output_format": "raw"}
      }
    }
  ]
}
```

## Pipeline Stages

### 1. LOAD
Load source disk image:
- `source_type`: vmdk, ova, ovf, vhd, vhdx, raw, ami
- `source_path`: Path to source disk

### 2. INSPECT
Detect guest OS and configuration:
- `enabled`: Enable inspection
- `detect_os`: Detect operating system

### 3. FIX
Apply offline fixes:
- **fstab**: Rewrite `/etc/fstab` entries
  - `mode`: stabilize-all, bypath-only, noop
- **grub**: Repair GRUB bootloader
- **initramfs**: Regenerate initramfs
- **network**: Fix network configuration
  - `fix_level`: full, basic, none

### 4. CONVERT
Convert to target format:
- `output_format`: qcow2, raw, vdi
- `compress`: Enable compression (qcow2 only)
- `output_path`: Optional custom output name

### 5. VALIDATE
Validate conversion:
- `enabled`: Enable validation
- `boot_test`: Test boot (requires QEMU)

## Output Reports

For successful conversions, a report is generated:

```json
{
  "manifest": "my-vm",
  "status": "completed",
  "completed_at": "2026-01-24T14:30:45",
  "stages": {
    "load": {"status": "success", "artifacts": [...]},
    "inspect": {"status": "success", "os_detected": "..."},
    "fix": {"status": "success", "fixes_applied": [...]},
    "convert": {"status": "success", "output_file": "..."},
    "validate": {"status": "success", "checks": [...]}
  },
  "artifacts": {
    "input": "/data/my-vm.vmdk",
    "output": "/output/my-vm-converted.qcow2"
  }
}
```

## Error Reports

For failed conversions:

```json
{
  "job_id": "my-vm",
  "original_name": "my-vm.json",
  "failed_at": "2026-01-24T14:30:45",
  "error": "File not found: /data/my-vm.vmdk",
  "exception": "Traceback...",
  "status": "failed"
}
```

## Examples

This directory contains:

- `manifest-daemon.yaml` - Daemon configuration
- `simple-vm-manifest.json` - Single VM example
- `batch-manifest.json` - Batch processing example
- `photon-manifest.json` - Real Photon OS example

## Systemd Integration

```bash
# /etc/systemd/system/hyper2kvm-manifest.service
[Unit]
Description=hyper2kvm Manifest Workflow Daemon
After=network.target

[Service]
Type=simple
User=hyper2kvm
Group=hyper2kvm
ExecStart=/usr/bin/python3 -m hyper2kvm --config /etc/hyper2kvm/manifest-daemon.yaml
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

## Comparison: Disk Workflow vs Manifest Workflow

| Feature | Disk Workflow | Manifest Workflow |
|---------|--------------|-------------------|
| **Input** | Disk files (.vmdk, .vhd, etc.) | Manifest files (.json, .yaml) |
| **Configuration** | Job configs (optional) | Pipeline definition (required) |
| **Pipeline** | Implicit | Explicit/declarative |
| **Reporting** | Basic metadata | Detailed stage-by-stage reports |
| **Batch** | Config file with jobs | Manifest with VMs array |
| **Use Case** | Quick disk conversions | Complex workflows with validation |

## Best Practices

1. **Use manifests for complex workflows**: When you need precise control over each pipeline stage
2. **Version your manifests**: Commit manifest files to version control
3. **Test with dry-run first**: Validate manifest syntax before production
4. **Monitor processed/ directory**: Review reports for conversion quality
5. **Archive old manifests**: Periodically clean up dated subdirectories

## Troubleshooting

### Manifest Validation Errors

```bash
# Check manifest syntax
python -m json.tool my-manifest.json

# Or for YAML
python -c "import yaml; yaml.safe_load(open('my-manifest.yaml'))"
```

### Check Processing State

```bash
# List active manifests
ls -lh /var/lib/hyper2kvm/manifest-workflow/processing/

# View error details
cat /var/lib/hyper2kvm/manifest-workflow/failed/2026-01-24/my-vm.json.error.json
```

### Reprocess Failed Manifest

```bash
# Move back to to_be_processed
mv /var/lib/hyper2kvm/manifest-workflow/failed/2026-01-24/my-vm.json \
   /var/lib/hyper2kvm/manifest-workflow/to_be_processed/
```

## See Also

- [Disk Workflow Documentation](../workflow-daemon/README.md)
- [Manifest Format Specification](../../docs/Manifest-Format.md)
- [YAML Configuration Examples](../yaml/)
