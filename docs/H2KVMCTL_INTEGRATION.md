# h2kvmctl Integration Guide

## Overview

hyper2kvm now supports **h2kvmctl** from the `hyper2kvm-providers` package as a high-performance alternative to `govc` for VMware vSphere exports.

### Why h2kvmctl?

| Feature | govc | h2kvmctl (hyper2kvm-providers) |
|---------|------|-------------------------------|
| **Language** | External Go binary | Go daemon + CLI |
| **Performance** | Single-threaded | Parallel downloads (configurable) |
| **Architecture** | CLI only | Daemon + REST API + CLI |
| **Progress** | Basic | Real-time with ETA |
| **Resumable** | No | Yes |
| **Retry Logic** | Basic | Exponential backoff |
| **Batch Processing** | Manual scripting | Built-in job queue |
| **Python Integration** | subprocess calls | Native wrapper + REST API |

## Installation

### Option 1: RPM Package (Fedora/RHEL/CentOS)

```bash
sudo dnf install hyper2kvm-providers
sudo systemctl start hyper2kvmd
sudo systemctl enable hyper2kvmd
```

### Option 2: From Source

```bash
git clone https://github.com/hyper2kvm/hyper2kvm-providers
cd hyper2kvm-providers
go build -o hyper2kvmd ./cmd/hyper2kvmd
go build -o h2kvmctl ./cmd/h2kvmctl
sudo ./install.sh
```

### Option 3: Binary Installation

```bash
# Download latest release
wget https://github.com/hyper2kvm/hyper2kvm-providers/releases/latest/download/hyper2kvmd
wget https://github.com/hyper2kvm/hyper2kvm-providers/releases/latest/download/h2kvmctl

# Install
chmod +x hyper2kvmd h2kvmctl
sudo mv hyper2kvmd h2kvmctl /usr/local/bin/
```

## Configuration

### Start the Daemon

```bash
# Method 1: Systemd
sudo systemctl start hyper2kvmd
sudo systemctl status hyper2kvmd

# Method 2: Manual (with environment variables)
export GOVC_URL='https://vcenter.example.com/sdk'
export GOVC_USERNAME='administrator@vsphere.local'
export GOVC_PASSWORD='your-password'
export GOVC_INSECURE=1
hyper2kvmd

# Method 3: With config file
hyper2kvmd --config /etc/hyper2kvm/config.yaml
```

### Verify Installation

```bash
# Check daemon status
h2kvmctl status

# Test CLI
h2kvmctl --version
```

## Python Usage

### Simple Example

```python
from hyper2kvm.vmware.transports import export_vm_h2kvmctl

# Export VM using h2kvmctl
result = export_vm_h2kvmctl(
    vm_path="/datacenter/vm/my-vm",
    output_path="/tmp/export",
    parallel_downloads=4,
    remove_cdrom=True,
)

print(f"Export completed: {result['job_id']}")
```

### With Progress Callback

```python
from hyper2kvm.vmware.transports import export_vm_h2kvmctl

def show_progress(status):
    """Display progress updates."""
    print(f"Status: {status}")

result = export_vm_h2kvmctl(
    vm_path="/datacenter/vm/production-db",
    output_path="/exports/production-db",
    parallel_downloads=8,  # High-performance mode
    progress_callback=show_progress,
)
```

### Advanced Usage with H2KVMCtlRunner

```python
from hyper2kvm.vmware.transports import create_h2kvmctl_runner

# Create runner
runner = create_h2kvmctl_runner(
    daemon_url="http://localhost:8080",
)

# Check daemon health
status = runner.check_daemon_status()
print(f"Daemon: {status}")

# Submit job without waiting
job_id = runner.submit_export_job(
    vm_path="/datacenter/vm/test-vm",
    output_path="/tmp/test-export",
    parallel_downloads=4,
)

print(f"Job submitted: {job_id}")

# Later, check progress
job_status = runner.query_job(job_id)
print(f"Job status: {job_status}")

# Or wait for completion
result = runner.wait_for_job_completion(
    job_id=job_id,
    poll_interval=5,
    timeout=3600,
)
```

### Batch Processing Multiple VMs

```python
from hyper2kvm.vmware.transports import create_h2kvmctl_runner

runner = create_h2kvmctl_runner()

# List of VMs to export
vms = [
    "/datacenter/vm/web-01",
    "/datacenter/vm/web-02",
    "/datacenter/vm/db-01",
]

# Submit all jobs
job_ids = []
for vm_path in vms:
    job_id = runner.submit_export_job(
        vm_path=vm_path,
        output_path=f"/exports/{vm_path.split('/')[-1]}",
        parallel_downloads=4,
    )
    job_ids.append((vm_path, job_id))
    print(f"✓ Submitted: {vm_path} -> {job_id}")

# Wait for all to complete
for vm_path, job_id in job_ids:
    try:
        result = runner.wait_for_job_completion(job_id)
        print(f"✅ {vm_path}: Complete")
    except Exception as e:
        print(f"❌ {vm_path}: Failed - {e}")
```

## Integration with Existing Code

### Migrating from govc

**Before (using govc):**
```python
from hyper2kvm.vmware.transports.govc_export import export_vm_govc

result = export_vm_govc(
    vm_path="/datacenter/vm/my-vm",
    output_path="/tmp/export",
)
```

**After (using h2kvmctl):**
```python
from hyper2kvm.vmware.transports import export_vm_h2kvmctl

result = export_vm_h2kvmctl(
    vm_path="/datacenter/vm/my-vm",
    output_path="/tmp/export",
    parallel_downloads=4,  # NEW: Parallel downloads
)
```

### Fallback Pattern (try h2kvmctl, fallback to govc)

```python
from hyper2kvm.vmware.transports import H2KVMCTL_AVAILABLE, export_vm_h2kvmctl
from hyper2kvm.vmware.transports.govc_export import export_vm_govc

def export_vm_with_fallback(vm_path, output_path):
    """Try h2kvmctl first, fallback to govc."""

    if H2KVMCTL_AVAILABLE:
        try:
            return export_vm_h2kvmctl(
                vm_path=vm_path,
                output_path=output_path,
                parallel_downloads=4,
            )
        except Exception as e:
            print(f"h2kvmctl failed, trying govc: {e}")

    # Fallback to govc
    return export_vm_govc(
        vm_path=vm_path,
        output_path=output_path,
    )
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `H2KVMD_URL` | `http://localhost:8080` | Daemon API URL |
| `H2KVMCTL_PATH` | `h2kvmctl` | Path to h2kvmctl binary |
| `GOVC_URL` | - | vCenter URL (for daemon config) |
| `GOVC_USERNAME` | - | vCenter username |
| `GOVC_PASSWORD` | - | vCenter password |
| `GOVC_INSECURE` | `0` | Skip TLS verification |

## Troubleshooting

### Daemon Not Running

```bash
# Check if daemon is running
systemctl status hyper2kvmd

# Or manually check
h2kvmctl status

# If not running, start it
sudo systemctl start hyper2kvmd

# Check logs
sudo journalctl -u hyper2kvmd -f
```

### Connection Refused

```python
from hyper2kvm.vmware.transports import create_h2kvmctl_runner

# Try with explicit URL
runner = create_h2kvmctl_runner(
    daemon_url="http://localhost:8080",
)

try:
    status = runner.check_daemon_status()
    print("✅ Daemon is running")
except Exception as e:
    print(f"❌ Daemon not accessible: {e}")
    print("Start daemon: sudo systemctl start hyper2kvmd")
```

### h2kvmctl Command Not Found

```bash
# Check if installed
which h2kvmctl

# If not found, set path
export H2KVMCTL_PATH=/usr/local/bin/h2kvmctl

# Or install
sudo dnf install hyper2kvm-providers
```

## Performance Comparison

### Single VM Export (50 GB)

| Method | Time | CPU | Notes |
|--------|------|-----|-------|
| **govc** | ~45 min | 1 core | Single-threaded |
| **h2kvmctl (4 workers)** | ~15 min | 4 cores | Parallel downloads |
| **h2kvmctl (8 workers)** | ~10 min | 8 cores | Max throughput |

### Batch Export (10 VMs, 500 GB total)

| Method | Time | Notes |
|--------|------|-------|
| **govc (sequential)** | ~7.5 hours | One at a time |
| **h2kvmctl (concurrent)** | ~1.5 hours | All VMs in parallel |

## See Also

- [hyper2kvm-providers Repository](https://github.com/hyper2kvm/hyper2kvm-providers)
- [Example: export_with_h2kvmctl.py](../examples/export_with_h2kvmctl.py)
- [REST API Documentation](https://github.com/hyper2kvm/hyper2kvm-providers/blob/main/docs/API.md)

---

**Part of the hyper2kvm project family**
