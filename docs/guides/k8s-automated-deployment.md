# Automated Kubernetes/k3s Deployment

hyper2kvm now supports **fully automated end-to-end migration** from VMware to Kubernetes/k3s clusters with KubeVirt. No manual steps required!

## Overview

The `--deploy-k8s` flag enables automatic deployment of migrated VMs directly to Kubernetes clusters. This eliminates all manual steps after migration.

### What Gets Automated

1. ✅ **Cluster Validation** - Checks k8s connectivity and KubeVirt availability
2. ✅ **Namespace Creation** - Creates namespace if it doesn't exist
3. ✅ **PVC Creation** - Creates PersistentVolumeClaim for VM disk
4. ✅ **Image Upload** - Uploads QCOW2 to PVC using temporary pod
5. ✅ **VM Creation** - Creates KubeVirt VirtualMachine resource
6. ✅ **VM Start** - Optionally starts VM and waits for ready status

## Quick Start

### Basic Usage

```bash
# Migrate and deploy in one command
sudo ./h2kvmctl --config centos9.yaml --deploy-k8s
```

### With Custom Options

```bash
sudo ./h2kvmctl \\
  --config centos9.yaml \\
  --deploy-k8s \\
  --k8s-namespace production \\
  --k8s-vm-name web-server-01 \\
  --k8s-cpu 4 \\
  --k8s-memory 8Gi \\
  --k8s-auto-start
```

## Configuration File

Add deployment options directly to your YAML config:

```yaml
# centos9-to-k8s.yaml
cmd: local
vmdk: /path/to/centos9.vmdk
output_dir: out/centos9
to_output: centos9.qcow2
compress: true

# Enable automated K8s deployment
deploy_k8s: true
k8s_namespace: my-vms
k8s_vm_name: centos9-prod
k8s_storage_class: longhorn  # or local-path for k3s
k8s_pvc_size: 20Gi
k8s_cpu: "4"
k8s_memory: 8Gi
k8s_auto_start: true
k8s_wait_ready: true

# Migration options
fstab_mode: stabilize-all
initramfs_regen_enable: true
initramfs_modules:
  - virtio_blk
  - virtio_scsi
  - virtio_net
```

Then run:

```bash
sudo ./h2kvmctl --config centos9-to-k8s.yaml
```

## CLI Options Reference

### Deployment Control

| Option | Default | Description |
|--------|---------|-------------|
| `--deploy-k8s` | `false` | Enable Kubernetes deployment |
| `--k8s-namespace NS` | `default` | Target namespace (created if needed) |
| `--k8s-vm-name NAME` | from filename | VirtualMachine resource name |
| `--k8s-pvc-name NAME` | `<vm-name>-disk` | PersistentVolumeClaim name |

### Storage Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--k8s-storage-class SC` | `local-path` | StorageClass for PVC |
| `--k8s-pvc-size SIZE` | `10Gi` | PVC size (must be larger than QCOW2) |

### VM Resources

| Option | Default | Description |
|--------|---------|-------------|
| `--k8s-cpu CORES` | `2` | Number of CPU cores |
| `--k8s-memory MEM` | `2Gi` | Memory allocation |

### VM Lifecycle

| Option | Default | Description |
|--------|---------|-------------|
| `--k8s-auto-start` | `false` | Auto-start VM after creation |
| `--k8s-wait-ready` | `true` | Wait for VM ready status (if auto-start) |
| `--no-k8s-wait-ready` | - | Don't wait for ready status |

## End-to-End Example

### 1. Prepare Configuration

```yaml
# production-migration.yaml
cmd: local
vmdk: /vms/prod-web-01.vmdk
output_dir: out/prod-web-01
to_output: prod-web-01.qcow2
out_format: qcow2
compress: true

# Offline fixes
fstab_mode: stabilize-all
grub_fixes_enable: true
initramfs_regen_enable: true
initramfs_modules:
  - virtio_blk
  - virtio_scsi
  - virtio_net
  - virtio_pci

network_fixes_enable: true

# K8s deployment
deploy_k8s: true
k8s_namespace: production
k8s_vm_name: web-server-01
k8s_storage_class: longhorn
k8s_pvc_size: 50Gi
k8s_cpu: "8"
k8s_memory: 16Gi
k8s_auto_start: true
k8s_wait_ready: true

# Reporting
report: out/prod-web-01/migration-report.md
verbose: 2
```

### 2. Run Migration

```bash
sudo ./h2kvmctl --config production-migration.yaml
```

### 3. Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 hyper2kvm - Production-Grade Hypervisor to KVM Migration Toolkit
   Built for the Enterprise Linux ecosystem (Fedora/RHEL/CentOS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
➡️ Sanity checks
✅ Sanity checks passed
─────────────
 Mode: local
─────────────
➡️ Processing disk 1/1: prod-web-01.vmdk
📥 Input VMDK: /vms/prod-web-01.vmdk (25.3 GiB)
...
✅ Offline fixes complete
➡️ Convert image → prod-web-01.qcow2
✅ Conversion complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 Deploying to Kubernetes/k3s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Namespace: production
VM Name: web-server-01
PVC Name: web-server-01-disk
Storage Class: longhorn
➡️ Validating Kubernetes cluster
✅ Cluster is accessible
✅ KubeVirt CRDs found
➡️ Ensuring namespace: production
✅ Namespace exists: production
➡️ Creating PVC: web-server-01-disk
✅ Created PVC: web-server-01-disk
➡️ Uploading image to PVC
Created uploader pod: uploader-web-server-01
Waiting for uploader pod to be ready...
✅ Uploader pod is ready
Copying prod-web-01.qcow2 to PVC (this may take a while)...
✅ Image uploaded to PVC
Cleaned up uploader pod
➡️ Creating VirtualMachine: web-server-01
✅ Created VirtualMachine: web-server-01
➡️ Starting VM: web-server-01
✅ VM started: web-server-01
➡️ Waiting for VM to be ready (timeout: 300s)
   VM phase: Scheduling, waiting...
   VM phase: Running, waiting...
✅ VM is ready!
   Phase: Running
   IP: 10.42.1.15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Kubernetes deployment complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
──────────
 Done
──────────
📦 Output directory: out/prod-web-01
🎉 Generated images:
 - out/prod-web-01/prod-web-01.qcow2

✅ Deployed: web-server-01
   Namespace: production
   PVC: web-server-01-disk
   Status: Running
```

### 4. Verify VM

```bash
# Check VM status
kubectl get vm,vmi -n production

# Access console
kubectl virt console web-server-01 -n production

# Check VM IP
kubectl get vmi web-server-01 -n production -o jsonpath='{.status.interfaces[0].ipAddress}'
```

## Storage Classes

### k3s (local-path)

```yaml
k8s_storage_class: local-path
```

- **Pros:** Built-in, no setup required
- **Cons:** ReadWriteOnce only, no live migration
- **Best for:** Development, single-node clusters

### Longhorn

```yaml
k8s_storage_class: longhorn
```

- **Pros:** ReadWriteMany, live migration, replicated storage
- **Cons:** Requires installation
- **Best for:** Production, multi-node clusters

### NFS/Ceph

```yaml
k8s_storage_class: nfs  # or rook-ceph-block
```

- **Pros:** Shared storage, live migration
- **Cons:** External storage system required
- **Best for:** Enterprise, existing infrastructure

## Advanced Scenarios

### Batch Migration to K8s

Migrate multiple VMs to Kubernetes:

```yaml
# batch-to-k8s.yaml
batch_manifest:
  parallel: 2
  continue_on_error: true
  vms:
    - name: web-01
      vmdk: /vms/web-01.vmdk
      k8s_vm_name: web-server-01
      k8s_namespace: production
      k8s_cpu: "4"
      k8s_memory: 8Gi

    - name: web-02
      vmdk: /vms/web-02.vmdk
      k8s_vm_name: web-server-02
      k8s_namespace: production
      k8s_cpu: "4"
      k8s_memory: 8Gi

    - name: db-01
      vmdk: /vms/db-01.vmdk
      k8s_vm_name: database-primary
      k8s_namespace: databases
      k8s_cpu: "8"
      k8s_memory: 32Gi
      k8s_storage_class: longhorn

# Common deployment settings
deploy_k8s: true
k8s_auto_start: false
```

### CI/CD Integration

```bash
#!/bin/bash
# migrate-to-k8s.sh - CI/CD migration script

set -e

VM_NAME=$1
VMDK_PATH=$2

# Create temp config
cat > /tmp/migration-$VM_NAME.yaml <<EOF
cmd: local
vmdk: $VMDK_PATH
output_dir: /tmp/out-$VM_NAME
to_output: $VM_NAME.qcow2
compress: true

# Fixes
fstab_mode: stabilize-all
initramfs_regen_enable: true

# K8s deployment
deploy_k8s: true
k8s_namespace: migrated-vms
k8s_vm_name: $VM_NAME
k8s_auto_start: true
EOF

# Run migration
sudo ./h2kvmctl --config /tmp/migration-$VM_NAME.yaml

# Cleanup
rm /tmp/migration-$VM_NAME.yaml
```

## Troubleshooting

### PVC Not Binding

**Symptom:** PVC stays in "Pending" state

**Cause:** local-path uses WaitForFirstConsumer binding mode

**Solution:** This is normal - PVC will bind when uploader pod is created

### Image Upload Fails

**Symptom:** `kubectl cp` fails with permission error

**Cause:** Insufficient RBAC permissions

**Solution:** Ensure your kubeconfig has admin permissions:
```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

### KubeVirt Not Found

**Symptom:** "⚠️ KubeVirt CRDs not found"

**Solution:** Install KubeVirt:
```bash
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-operator.yaml
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-cr.yaml
```

### VM Won't Start

**Symptom:** VM created but not starting

**Cause:** Manual start required (auto-start disabled)

**Solution:**
```bash
kubectl patch vm <vm-name> -n <namespace> --type merge -p '{"spec":{"running":true}}'
```

## Requirements

### Python Packages

```bash
pip install kubernetes
```

### Kubernetes Access

- Valid kubeconfig file
- Admin permissions (namespace creation, PVC creation)
- KubeVirt installed on cluster

### Storage

- StorageClass with sufficient capacity
- For k3s: local-path provisioner (included)
- For production: Longhorn, NFS, or Ceph

## Comparison: Before vs After

### Before (Manual Steps)

```bash
# Step 1: Migrate
sudo ./h2kvmctl --config centos9.yaml

# Step 2: Create namespace
kubectl create namespace my-vms

# Step 3: Create PVC
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: centos9-disk
  namespace: my-vms
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi
EOF

# Step 4: Upload image
kubectl run uploader --image=alpine --restart=Never -n my-vms \\
  --overrides='...' # Complex JSON
kubectl wait --for=condition=Ready pod/uploader -n my-vms
kubectl cp out/centos9.qcow2 my-vms/uploader:/disk/disk.img
kubectl delete pod uploader -n my-vms

# Step 5: Create VM
cat <<EOF | kubectl apply -f -
apiVersion: kubevirt.io/v1
kind: VirtualMachine
# ... lots of YAML
EOF

# Step 6: Start VM
kubectl patch vm centos9 -n my-vms --type merge -p '{"spec":{"running":true}}'
```

### After (Fully Automated)

```bash
sudo ./h2kvmctl --config centos9.yaml --deploy-k8s
```

**That's it!** 🎉

## See Also

- [KubeVirt Documentation](https://kubevirt.io/user-guide/)
- [k3s Documentation](https://docs.k3s.io/)
- [Longhorn Documentation](https://longhorn.io/docs/)
- [hyper2kvm Migration Guide](../migration/quick-reference.md)
