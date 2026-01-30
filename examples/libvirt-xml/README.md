# Libvirt Domain XML Import Examples

This directory contains examples for importing existing libvirt VMs into hyper2kvm using the libvirt-xml extractor.

## Overview

The libvirt-xml extractor parses libvirt domain XML files and generates an Artifact Manifest v1, enabling you to convert existing libvirt/KVM VMs to hyper2kvm-compatible formats.

## What It Extracts

From a libvirt domain XML file, the extractor gathers:

- **Disk Information**: Paths, formats (qcow2/raw/etc.), sizes
- **Firmware Type**: BIOS or UEFI detection
- **OS Metadata**: OS type and distro hints (from libosinfo if present)
- **Network Configuration**: Interfaces, bridges, MAC addresses, models
- **Resource Allocation**: Memory (bytes) and vCPU count
- **Boot Configuration**: Boot device order

## Usage

### Basic Usage

Parse a libvirt domain XML and generate an Artifact Manifest:

```bash
# Create a simple config to specify the command
cat > libvirt-import.yaml <<EOF
cmd: libvirt-xml
output_dir: /work/converted
EOF

# Run the extractor
sudo hyper2kvm \\
  --config libvirt-import.yaml \\
  --libvirt-xml /etc/libvirt/qemu/web-server-prod.xml
```

This generates `/work/converted/manifest.json` containing the complete Artifact Manifest v1.

### Convert the Extracted VM

After generating the manifest, use it for conversion:

```bash
# Run conversion using the generated manifest
sudo hyper2kvm --config /work/converted/manifest.json
```

### Skip Checksum Computation

For faster processing (useful for large disks):

```bash
sudo hyper2kvm \\
  --config libvirt-import.yaml \\
  --libvirt-xml /etc/libvirt/qemu/my-vm.xml \\
  --no-compute-checksums
```

### Custom Manifest Filename

```bash
sudo hyper2kvm \\
  --config libvirt-import.yaml \\
  --libvirt-xml /etc/libvirt/qemu/my-vm.xml \\
  --manifest-filename my-vm-manifest.json
```

## Example Files

### `sample-domain.xml`

A complete example libvirt domain XML with:
- UEFI firmware
- 2 disk devices (boot + data)
- Bridge network interface
- RHEL 9 OS metadata
- 8GB RAM, 4 vCPUs

To test with this sample:

```bash
# Create output directory
mkdir -p /tmp/libvirt-test

# Parse the sample domain
sudo hyper2kvm \\
  --config <(echo "cmd: libvirt-xml\noutput_dir: /tmp/libvirt-test") \\
  --libvirt-xml examples/libvirt-xml/sample-domain.xml \\
  --no-compute-checksums

# View the generated manifest
cat /tmp/libvirt-test/manifest.json
```

## Generated Manifest Structure

The libvirt-xml extractor creates an Artifact Manifest v1 with:

```json
{
  "manifest_version": "1.0",
  "source": {
    "provider": "libvirt",
    "vm_id": "<domain-uuid>",
    "vm_name": "<domain-name>",
    "export_timestamp": "2026-01-22T10:00:00Z",
    "libvirt_xml_path": "/path/to/domain.xml"
  },
  "disks": [
    {
      "id": "vda",
      "source_format": "qcow2",
      "local_path": "/var/lib/libvirt/images/boot.qcow2",
      "bytes": 53687091200,
      "checksum": "sha256:abc123...",
      "boot_order_hint": 0,
      "disk_type": "boot"
    }
  ],
  "firmware": {
    "type": "uefi"
  },
  "os_hint": "rhel9",
  "metadata": {
    "networks": [
      {
        "type": "bridge",
        "source": "br0",
        "mac": "52:54:00:6b:3c:58",
        "model": "virtio"
      }
    ],
    "memory_bytes": 8589934592,
    "vcpus": 4
  },
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {"enabled": true, "backup": true},
    "convert": {"enabled": true, "compress": true},
    "validate": {"enabled": true}
  },
  "output": {
    "directory": "/work/converted",
    "format": "qcow2"
  }
}
```

## Real-World Workflow

### 1. Export from Running Libvirt VM

```bash
# Get the domain XML from a running VM
virsh dumpxml my-vm > /tmp/my-vm.xml

# Parse it to generate manifest
sudo hyper2kvm \\
  --config <(echo "cmd: libvirt-xml\noutput_dir: /work/migration") \\
  --libvirt-xml /tmp/my-vm.xml
```

### 2. Review and Customize Manifest

```bash
# Edit the generated manifest to customize pipeline settings
vi /work/migration/manifest.json

# Example customizations:
# - Add network_mapping for bridge translation
# - Add hooks for pre/post conversion steps
# - Change output format or compression settings
# - Add profile reference
```

### 3. Run Conversion

```bash
# Execute the conversion pipeline
sudo hyper2kvm --config /work/migration/manifest.json
```

## Integration with Batch Conversion

You can combine libvirt-xml extraction with batch conversion:

```bash
# Generate manifests for multiple VMs
for vm in web-server db-server app-server; do
  virsh dumpxml $vm > /tmp/${vm}.xml
  sudo hyper2kvm \\
    --config <(echo "cmd: libvirt-xml\noutput_dir: /work/migration/$vm") \\
    --libvirt-xml /tmp/${vm}.xml
done

# Create batch manifest
cat > /work/migration/batch.json <<EOF
{
  "batch_version": "1.0",
  "batch_metadata": {
    "batch_id": "libvirt-migration",
    "parallel_limit": 3
  },
  "vms": [
    {"manifest": "/work/migration/web-server/manifest.json"},
    {"manifest": "/work/migration/db-server/manifest.json"},
    {"manifest": "/work/migration/app-server/manifest.json"}
  ]
}
EOF

# Run batch conversion
sudo hyper2kvm --batch-manifest /work/migration/batch.json
```

## Firmware Detection

The extractor automatically detects firmware type:

**UEFI Detected When**:
- `<loader type="pflash">` present
- `<os firmware="efi">` attribute set
- Loader path contains "OVMF"

**Otherwise**: Defaults to BIOS

## OS Distro Detection

The extractor attempts to extract OS distro from libosinfo metadata:

- Checks `<metadata><libosinfo:libosinfo><libosinfo:os id="...">`
- Parses OS ID for distro hints (rhel, ubuntu, debian, centos, fedora)
- Falls back to "unknown" if not found

## Limitations

- **CD-ROMs and Floppies**: Automatically skipped
- **Missing Disks**: Skipped with warning if disk file doesn't exist
- **Network-based Disks**: Block devices and network storage not fully supported
- **Advanced Features**: Some libvirt-specific features may not translate to manifest

## Troubleshooting

### "Disk not found" Warnings

If you see warnings like:

```
⚠️  Disk not found (skipping): /var/lib/libvirt/images/missing.qcow2
```

This means the domain XML references a disk that doesn't exist on the filesystem. Either:
1. Copy/move the disk to the expected location
2. Edit the XML to correct the path
3. The disk may have been deleted

### No Disks Found

```
❌ No disks found in domain XML
```

This means the XML doesn't contain any valid disk devices. Check:
- Disk elements are present in `<devices>`
- Disk type is `device="disk"` (not cdrom/floppy)
- Source paths are specified

### Parse Errors

```
❌ Failed to parse domain XML
```

The XML file may be malformed. Validate it:

```bash
xmllint --noout /path/to/domain.xml
```

## See Also

- **Artifact Manifest Specification**: `docs/06-Artifact-Manifest-Spec-v1.md`
- **Batch Conversion Guide**: `docs/14-Batch-Migration-Guide.md` (if available)
- **LibvirtXML Source**: `hyper2kvm/converters/extractors/libvirt_xml.py`
- **Disk Discovery Integration**: `hyper2kvm/orchestrator/disk_discovery.py`
