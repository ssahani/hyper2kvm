# Worker Job Protocol - Quick Start Guide

Get up and running with the hyper2kvm Worker Job Protocol in 5 minutes.

---

## Step 1: Check Your Environment

```bash
cd /home/ssahani/tt/hyper2kvm
python3 -m hyper2kvm.worker.cli capabilities
```

This shows:
- Execution mode (host, safe_container, or privileged_container)
- Available capabilities (NBD, LVM, mount, SELinux, qemu-img)
- System resources

---

## Step 2: Create a Job Specification

Create `my-job.json`:

```json
{
  "version": "1.0",
  "job_id": "my-first-job",
  "operation": "inspect",
  "image": {
    "path": "/path/to/your/vm.qcow2",
    "format": "qcow2"
  },
  "artifacts": {
    "output_path": "/tmp/worker-output"
  },
  "audit": {
    "requested_by": "quickstart-guide"
  }
}
```

---

## Step 3: Run the Job

```bash
python3 -m hyper2kvm.worker.cli run my-job.json --follow
```

You'll see:
- Real-time progress bar
- Phase-by-phase execution
- Final result

---

## Step 4: Check the Results

```bash
# View job status
python3 -m hyper2kvm.worker.cli status my-first-job

# View events
python3 -m hyper2kvm.worker.cli events my-first-job

# Check output
ls -lh /tmp/worker-output/
```

---

## Next Steps

### Try Format Conversion

```json
{
  "version": "1.0",
  "job_id": "convert-job",
  "operation": "convert",
  "image": {
    "path": "/path/to/vm.vmdk",
    "format": "vmdk"
  },
  "parameters": {
    "output_format": "qcow2",
    "compress": true
  },
  "artifacts": {
    "output_path": "/tmp/converted"
  },
  "audit": {
    "requested_by": "quickstart"
  }
}
```

Run it:
```bash
python3 -m hyper2kvm.worker.cli run convert-job.json --follow
```

### Run the Example Script

```bash
python3 examples/worker_example.py
```

This demonstrates:
- Environment detection
- Job creation
- Execution with progress
- Result handling

---

## Common Operations

### List All Jobs

```bash
python3 -m hyper2kvm.worker.cli list
```

### Filter by State

```bash
python3 -m hyper2kvm.worker.cli list --state completed
python3 -m hyper2kvm.worker.cli list --state failed
```

### Follow Events in Real-Time

```bash
python3 -m hyper2kvm.worker.cli events my-job --follow
```

### Get JSON Output

```bash
python3 -m hyper2kvm.worker.cli capabilities --json-output
```

---

## Troubleshooting

### "Permission denied" on NBD operations

You're running in safe container mode. Options:
1. Run on host: `sudo python3 -m hyper2kvm.worker.cli run job.json`
2. Use privileged container
3. Stick to conversion/inspection operations

### "Job not found"

The job ID doesn't exist. List all jobs:
```bash
python3 -m hyper2kvm.worker.cli list
```

### "Missing required capability"

Your worker can't execute this job type. Check:
```bash
python3 -m hyper2kvm.worker.cli capabilities
```

---

## What's Next?

1. Read the [complete protocol spec](PROTOCOL_SPEC.md)
2. Try the Python API (see `examples/worker_example.py`)
3. Deploy workers in Kubernetes (see `k8s/worker/`)

---

**Happy job orchestration!** 🚀
