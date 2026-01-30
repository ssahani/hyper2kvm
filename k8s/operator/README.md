# Hyper2KVM Kubernetes Operator

Production-ready Kubernetes Operator for automated migration job orchestration.

## Current Status: Production-Ready ✅

**v1.4.0** provides complete operator implementation with automatic job assignment and lifecycle management.

## Custom Resource Definitions

### MigrationJob CRD

The `MigrationJob` CRD allows declarative VM migration job management:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: convert-windows-2019
spec:
  operation: convert
  image:
    path: /data/input/windows-2019.vmdk
    format: vmdk
    checksum: sha256:abc123...

  parameters:
    output_format: qcow2
    compress: true
    fstab_mode: stabilize-all
    regen_initramfs: true

  artifacts:
    output_path: /data/output
    output_format: qcow2
    compress: true

  priority: 75
  timeout: 2h

  retryPolicy:
    maxRetries: 2
    backoff: exponential

  workerSelector:
    hyper2kvm.io/gpu: "true"
```

## Installation

### Prerequisites

- Kubernetes 1.24+
- Worker pods deployed (see `helm/hyper2kvm-worker/` or `k8s/README.md`)
- Kubectl configured with cluster access

### Step 1: Install CRD and RBAC

```bash
# Install CRD and operator RBAC resources
kubectl apply -f k8s/operator/crds/migrationjob.yaml
```

This creates:
- `MigrationJob` CustomResourceDefinition
- Namespace: `hyper2kvm-system`
- ServiceAccount: `hyper2kvm-operator`
- ClusterRole and ClusterRoleBinding

### Step 2: Build Operator Image

```bash
# Build operator container
docker build --target operator -t hyper2kvm:operator .

# For k3d/kind, import the image
k3d image import hyper2kvm:operator -c your-cluster
# or
kind load docker-image hyper2kvm:operator --name your-cluster
```

### Step 3: Deploy Operator

```bash
# Deploy operator
kubectl apply -f k8s/operator/deployment.yaml
```

This creates:
- Deployment: `hyper2kvm-operator` (1 replica)
- Service: `hyper2kvm-operator` (port 8080)
- ServiceMonitor: For Prometheus integration (optional)

### Step 4: Verify Installation

```bash
# Check CRD exists
kubectl get crd migrationjobs.hyper2kvm.io

# Check API resources
kubectl api-resources | grep hyper2kvm

# Check operator pod
kubectl get pods -n hyper2kvm-system

# Check operator logs
kubectl logs -n hyper2kvm-system -l app=hyper2kvm-operator -f

# Verify operator is ready
kubectl get deployment -n hyper2kvm-system hyper2kvm-operator
```

## Usage (Manual Mode)

Without an operator controller, you can still use the CRD for declarative job specifications:

### Create a MigrationJob

```bash
cat > example-job.yaml << 'EOF'
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: convert-debian-vm
  namespace: hyper2kvm-workers
spec:
  operation: convert
  image:
    path: /data/input/debian-12.vmdk
    format: vmdk
  parameters:
    output_format: qcow2
    compress: true
  artifacts:
    output_path: /data/output
  priority: 50
  timeout: 1h
EOF

kubectl apply -f example-job.yaml
```

### Automated Job Execution

With the operator running, jobs are automatically executed:

```bash
# Create a MigrationJob
kubectl apply -f examples/convert-job.yaml

# Watch job progress
kubectl get migrationjob convert-windows-server-2019 -n hyper2kvm-workers -w

# Check detailed status
kubectl describe migrationjob convert-windows-server-2019 -n hyper2kvm-workers

# View Kubernetes events
kubectl get events -n hyper2kvm-workers --field-selector involvedObject.name=convert-windows-server-2019
```

## Operator Features ✅

### Implemented Features

1. **Job Reconciliation Loop** ✅
   - Watches `MigrationJob` resources
   - Assigns jobs to workers based on capabilities
   - Updates job status automatically
   - 30-second reconciliation interval

2. **Worker Pool Management** ✅
   - Discovers available workers (label: `app=hyper2kvm-worker`)
   - Tracks worker capabilities
   - Load balancing (prefers idle workers)
   - Worker scoring algorithm (0-100 points)

3. **Progress Tracking** ✅
   - Streams events from workers
   - Updates `.status.progress` in real-time
   - Emits Kubernetes events
   - JSONL event storage on workers

4. **State Machine** ✅
   - 10-state job lifecycle
   - Automatic state transitions
   - Retry support
   - Cancellation handling

5. **Event Emission** ✅
   - Kubernetes events for all lifecycle changes
   - JobCreated, JobAssigned, JobCompleted, etc.
   - Visible in `kubectl describe`

### Implementation Technologies

**Recommended Frameworks:**

- **Operator SDK** (Go) - Most mature, full Kubernetes integration
- **Kopf** (Python) - Python-native, easier for hyper2kvm integration
- **Kubebuilder** (Go) - Modern code generation
- **KUDO** (Declarative) - No code required

### Operator Architecture

```
┌─────────────────────────────────────────┐
│         MigrationJob CRD                │
│  (User creates job specifications)      │
└────────────────┬────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────┐
│       Operator Controller                │
│  - Job reconciliation loop              │
│  - Worker discovery                     │
│  - Scheduling logic                     │
│  - Status updates                       │
└────────────────┬────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────┐
│      Worker Job Protocol v1             │
│  - Job validation                       │
│  - Capability matching                  │
│  - Execution                            │
│  - Progress streaming                   │
└─────────────────────────────────────────┘
```

## Architecture

### Operator Components

```
┌─────────────────────────────────────────────────────┐
│           Operator Pod (hyper2kvm-system)           │
│  ┌───────────────────────────────────────────────┐  │
│  │  Kopf Controller (Python)                     │  │
│  │  - Watch MigrationJob CRD                     │  │
│  │  - Discover workers                           │  │
│  │  - Assign jobs (scoring algorithm)            │  │
│  │  - Update status                              │  │
│  │  - Emit events                                │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │  Worker Registry                              │  │
│  │  - Track worker pods                          │  │
│  │  - Monitor load                               │  │
│  │  - Cache capabilities                         │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │  Job Assigner                                 │  │
│  │  - Match jobs to workers                      │  │
│  │  - Scoring algorithm (0-100)                  │  │
│  │  - Load balancing                             │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
           ↓                              ↑
   Copy job spec                   Read job status/events
           ↓                              ↑
┌─────────────────────────────────────────────────────┐
│        Worker Pods (hyper2kvm-workers namespace)    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Worker 1 │  │ Worker 2 │  │ Worker 3 │         │
│  │          │  │          │  │          │         │
│  │ Job Exec │  │ Job Exec │  │ Job Exec │         │
│  │ Engine   │  │ Engine   │  │ Engine   │         │
│  └──────────┘  └──────────┘  └──────────┘         │
└─────────────────────────────────────────────────────┘
```

### Job Lifecycle with Operator

```
User creates MigrationJob CRD
    ↓
Operator watches CREATE event
    ↓
Validate job spec → CREATED
    ↓
Schema validation → VALIDATED
    ↓
Add to queue → QUEUED
    ↓
Reconciliation loop (30s interval)
    ↓
Discover workers (label: app=hyper2kvm-worker)
    ↓
Score workers (capability + load + priority)
    ↓
Assign to best worker → ASSIGNED
    ↓
Copy job spec to worker pod
    ↓
Execute job on worker → RUNNING
    ↓
Stream progress events → PROGRESSING
    ↓
Job completes → COMPLETED
    ↓
Update CRD status
    ↓
Emit Kubernetes event
```

### Worker Scoring Algorithm

Each worker is scored 0-100 points:

| Factor | Max Points | Criteria |
|--------|------------|----------|
| **Capabilities** | 40 | Has required operations/formats |
| **Load** | 30 | Fewer active jobs = more points |
| **Priority** | 20 | High-priority jobs prefer idle workers |
| **Affinity** | 10 | Matches workerSelector labels |

Workers with score 0 are unsuitable. Highest score wins.

## Development Roadmap

### Phase 1: CRD Foundation ✅ (v1.3.0)
- [x] Define MigrationJob CRD
- [x] RBAC resources
- [x] Documentation

### Phase 2: Basic Operator ✅ (v1.4.0)
- [x] Implement controller in Python (Kopf)
- [x] Job reconciliation loop (30s interval)
- [x] Worker discovery
- [x] Job assignment with scoring
- [x] Status updates (real-time)
- [x] Event emission
- [x] Progress tracking

### Phase 3: Advanced Features (Future v1.5.0)
- [ ] Enhanced priority-based scheduling
- [ ] Worker affinity/anti-affinity rules
- [ ] Resource quotas per namespace
- [ ] Admission webhooks for validation
- [ ] Enhanced metrics and monitoring

### Phase 4: Production Hardening (Future v1.6.0)
- [ ] Leader election (multi-replica operator)
- [ ] Multi-tenant isolation
- [ ] Advanced retry policies (backoff strategies)
- [ ] Job dependencies (DAG support)
- [ ] Auto-scaling workers based on queue depth

## Contributing

To contribute to operator development:

1. Study the [Operator Pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
2. Review [Worker Job Protocol](../../docs/worker/PROTOCOL_SPEC.md)
3. Propose architecture in GitHub discussions
4. Implement in feature branch
5. Submit PR with tests

## References

- [Kubernetes Operator Pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- [Operator SDK](https://sdk.operatorframework.io/)
- [Kopf Framework](https://kopf.readthedocs.io/)
- [Custom Resource Definitions](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/)
- [Kubebuilder Book](https://book.kubebuilder.io/)

## License

Same as hyper2kvm main project.
