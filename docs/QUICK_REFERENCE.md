# Live Migration Quick Reference

## Common Commands

### Check Migration Status

```bash
# List all migrations
kubectl get migrationjobs
kubectl get virtualmachineinstancemigrations
kubectl get vmim  # short form

# Watch migrations
kubectl get vmim -w

# Detailed status
kubectl describe vmim <migration-name>
kubectl get vmim <migration-name> -o yaml
```

### Trigger Live Migration

```bash
# Manual migration
kubectl create -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachineInstanceMigration
metadata:
  name: my-vm-migration
spec:
  vmiName: my-vm-instance
EOF

# Via node cordon (automatic)
kubectl cordon node-1
```

### Abort Migration

```bash
kubectl delete vmim <migration-name>
```

### Check VM Eviction Strategy

```bash
kubectl get vm <vm-name> -o jsonpath='{.spec.template.spec.evictionStrategy}'
```

### View Migration Policies

```bash
kubectl get migrationpolicies
kubectl get mp  # short form
kubectl describe mp <policy-name>
```

## Common MigrationJob Patterns

### Basic VM with Live Migration

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: my-vm
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://storage.example.com/vm.vmdk"
  destination:
    pvcName: my-vm-disk
    size: 50Gi
  createVM:
    enabled: true
    evictionStrategy: LiveMigrate
    cpu: "4"
    memory: 8Gi
```

### UEFI VM

```yaml
createVM:
  enabled: true
  evictionStrategy: LiveMigrate
  firmware:
    bootloader: uefi
    secureBoot: true
```

### Multi-Disk VM

```yaml
createVM:
  enabled: true
  disks:
    - name: data-disk
      pvcName: my-data-pvc
      bootOrder: 2
      bus: virtio
```

### CPU Topology

```yaml
createVM:
  enabled: true
  cpuConfig:
    cores: 4
    sockets: 2
    threads: 1
```

## Migration Policy Templates

### Conservative (Default)

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: default
spec:
  bandwidthPerMigration: "100Mi"
  allowAutoConverge: true
  allowPostCopy: false
  maxParallelMigrationsPerCluster: 5
  maxParallelMigrationsPerNode: 2
```

### High Performance

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: fast-migration
spec:
  bandwidthPerMigration: "2Gi"
  allowAutoConverge: true
  allowPostCopy: true
  maxParallelMigrationsPerCluster: 10
```

## Troubleshooting One-Liners

```bash
# Check why migration failed
kubectl get vmim <name> -o jsonpath='{.status.migrationState.failureReason}'

# Check migration progress
kubectl get vmim <name> -o jsonpath='{.status.migrationState}{"\n"}'

# Find VMs on a node
kubectl get vmi -o wide | grep <node-name>

# Check policy violations
kubectl get events | grep PolicyViolation

# View migration metrics
kubectl port-forward -n hyper2kvm-system deployment/hyper2kvm-operator 8080:8080
curl localhost:8080/metrics | grep live_migration

# Check operator logs
kubectl logs -n hyper2kvm-system deployment/hyper2kvm-operator -f
```

## Metrics Queries (Prometheus)

```promql
# Active migrations
sum(hyper2kvm_live_migrations_active)

# Success rate (last 5m)
sum(rate(hyper2kvm_live_migrations_succeeded_total[5m])) /
sum(rate(hyper2kvm_live_migrations_total[5m]))

# Average duration
avg(hyper2kvm_live_migration_duration_seconds)

# Policy violations
sum(rate(hyper2kvm_migration_policy_violations_total[5m]))

# Migrations by phase
sum by (phase) (hyper2kvm_live_migrations_active)
```

## Node Maintenance Workflow

```bash
# 1. Cordon node
kubectl cordon node-1

# 2. Watch migrations
kubectl get vmim -w

# 3. Wait for migrations to complete
kubectl get vmim | grep -v Succeeded

# 4. Drain node
kubectl drain node-1 --ignore-daemonsets

# 5. Perform maintenance

# 6. Uncordon node
kubectl uncordon node-1
```

## Emergency Procedures

### Stop All Migrations

```bash
kubectl delete vmim --all
```

### Disable Auto-Migration for a VM

```bash
kubectl patch vm <vm-name> --type=merge -p '
{
  "spec": {
    "template": {
      "spec": {
        "evictionStrategy": "None"
      }
    }
  }
}'
```

### Increase Policy Limits

```bash
kubectl patch migrationpolicy default --type=merge -p '
{
  "spec": {
    "maxParallelMigrationsPerCluster": 20
  }
}'
```

## Eviction Strategy Values

| Value | Behavior |
|-------|----------|
| `LiveMigrate` | Always migrate |
| `LiveMigrateIfPossible` | Try migration, else shutdown |
| `None` | Shutdown only |
| `External` | Wait for external orchestration |

## Migration Phases

| Phase | Meaning |
|-------|---------|
| `Pending` | Queued |
| `Scheduling` | Finding target node |
| `Running` | Actively migrating |
| `Succeeded` | Completed |
| `Failed` | Failed (check reason) |

## Common Errors

| Error | Solution |
|-------|----------|
| InsufficientResources | Free up node resources |
| PolicyViolation | Wait or increase limits |
| NetworkError | Check network connectivity |
| Timeout | Increase timeout or enable post-copy |

## Resource Naming

```
VirtualMachine (VM) - Template for VMs
  └─ VirtualMachineInstance (VMI) - Running VM
      └─ VirtualMachineInstanceMigration (VMIM) - Migration

MigrationJob - hyper2kvm cold migration
MigrationPolicy - Migration behavior policy
```

## Labels and Annotations

```yaml
# Apply policy to VM
metadata:
  annotations:
    hyper2kvm.io/migration-policy: my-policy

# VM created by MigrationJob
metadata:
  labels:
    hyper2kvm.io/migration-job: job-name
```

## Useful kubectl Plugins

```bash
# Install kubevirt kubectl plugin
kubectl krew install virt

# Use virt plugin
kubectl virt migrate <vm-name>
kubectl virt console <vm-name>
```

## Configuration Files

```
├── k8s/
│   ├── operator/
│   │   ├── crds/
│   │   │   └── migrationpolicy.yaml       # MigrationPolicy CRD
│   │   ├── migrationjob-crd.yaml          # MigrationJob CRD
│   │   └── deployment.yaml                # Operator deployment + RBAC
│   └── examples/
│       ├── migrationpolicy-*.yaml         # Policy examples
│       └── migrationjob-*.yaml            # Job examples
└── docs/
    ├── LIVE_MIGRATION.md                  # Full documentation
    ├── UPGRADE_GUIDE.md                   # Upgrade instructions
    └── QUICK_REFERENCE.md                 # This file
```

## Support

- Documentation: `docs/LIVE_MIGRATION.md`
- Examples: `k8s/examples/`
- Issues: https://github.com/your-org/hyper2kvm/issues
