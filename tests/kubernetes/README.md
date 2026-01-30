# Kubernetes Tests

Comprehensive test suite for Hyper2KVM Kubernetes operator and integration.

---

## Test Organization

### Unit Tests (Python)
Located in `tests/kubernetes/`:
- **test_operator_controller.py** - Operator controller unit tests
- **test_operator_webhook.py** - Webhook validation and mutation tests
- **test_leader_election.py** - Leader election and HA tests

### Integration Tests (Python)
Located in `tests/kubernetes/`:
- **test_k8s_integration.py** - End-to-end integration tests (requires running cluster)

### E2E Tests (Shell)
Located in `scripts/`:
- **test-kubernetes-e2e.sh** - Comprehensive end-to-end test suite
- **test-k8s-centos8.sh** - CentOS 8 Kubernetes deployment tests
- **test-openshift-deployment.sh** - OpenShift deployment tests

---

## Running Tests

### Unit Tests

Run all unit tests:
```bash
# From repository root
pytest tests/kubernetes/test_operator_controller.py -v
pytest tests/kubernetes/test_operator_webhook.py -v
pytest tests/kubernetes/test_leader_election.py -v
```

Run specific test:
```bash
pytest tests/kubernetes/test_operator_controller.py::TestOperatorController::test_controller_initialization -v
```

### Integration Tests

**Prerequisites**:
- Running Kubernetes cluster
- Operator deployed
- CRDs installed

Run integration tests:
```bash
# Mark integration tests to run only when explicitly requested
pytest tests/kubernetes/test_k8s_integration.py -v -m integration
```

### E2E Tests

**Prerequisites**:
- Kubernetes cluster (minikube, kind, or cloud)
- kubectl configured
- Helm installed

Run complete E2E test suite:
```bash
# From repository root
./scripts/test-kubernetes-e2e.sh
```

Run with custom configuration:
```bash
NAMESPACE=my-namespace \
CLEANUP=false \
./scripts/test-kubernetes-e2e.sh
```

---

## Test Coverage

### Unit Tests

#### Operator Controller Tests (test_operator_controller.py)
✅ Controller initialization
✅ Watching MigrationJob resources
✅ Processing ADDED events
✅ Processing DELETED events
✅ Creating worker jobs
✅ Updating job status
✅ Spec validation
✅ Failure handling
✅ Graceful shutdown
✅ Job assignment logic
✅ Resource-based assignment
✅ Load balancing
✅ CRD schema validation

**Total**: 15+ test cases

#### Webhook Tests (test_operator_webhook.py)
✅ MigrationJob creation validation
✅ Invalid source type rejection
✅ Missing required fields rejection
✅ Invalid destination format rejection
✅ UPDATE operation validation
✅ Immutable field protection
✅ Resource limits validation
✅ Excessive resource rejection
✅ Health check endpoint
✅ Validate endpoint
✅ Mutate endpoint
✅ Default output format
✅ Default compression
✅ Default workers
✅ Default labels

**Total**: 15+ test cases

#### Leader Election Tests (test_leader_election.py)
✅ Leader elector initialization
✅ Acquiring leadership
✅ Leadership already held
✅ Renewing leadership
✅ Releasing leadership
✅ Leadership lost on failed renewal
✅ Lease expiration
✅ Lease not expired
✅ Leadership transition
✅ Controller starts as follower
✅ Leader election callback
✅ Follower callback
✅ Leader processes events
✅ Follower skips events
✅ Leadership change handling
✅ Multiple replicas election
✅ Leader failover
✅ Split-brain prevention
✅ Graceful shutdown

**Total**: 19+ test cases

### Integration Tests

#### K8s Integration Tests (test_k8s_integration.py)
✅ Create MigrationJob
✅ MigrationJob lifecycle
✅ Multiple MigrationJobs
✅ Jobs with resources
✅ OfflineFixJob creation
✅ Job dependencies
✅ Metrics endpoint
✅ Health endpoints

**Total**: 8+ test cases

### E2E Tests

#### Kubernetes E2E (test-kubernetes-e2e.sh)
✅ Prerequisites check (kubectl, helm, cluster)
✅ Namespace creation
✅ CRD installation
✅ Operator deployment
✅ Webhook configuration
✅ MigrationJob creation
✅ OfflineFixJob creation
✅ Batch MigrationJobs
✅ Job dependencies
✅ Metrics collection
✅ RBAC permissions
✅ Cleanup

**Total**: 12 test phases

---

## Test Configuration

### Environment Variables

**Namespaces**:
- `NAMESPACE` - Operator namespace (default: hyper2kvm-system)
- `WORKER_NAMESPACE` - Worker namespace (default: hyper2kvm-workers)
- `TEST_NAMESPACE` - Test namespace (default: hyper2kvm-test)

**Deployment**:
- `RELEASE_NAME` - Helm release name (default: hyper2kvm-operator)
- `HELM_CHART` - Helm chart path (default: ./helm/hyper2kvm-operator)

**Testing**:
- `TIMEOUT` - Timeout in seconds (default: 300)
- `CLEANUP` - Cleanup after tests (default: true)

### Example Configurations

**Quick test (no cleanup)**:
```bash
CLEANUP=false ./scripts/test-kubernetes-e2e.sh
```

**Custom namespaces**:
```bash
NAMESPACE=prod-operator \
WORKER_NAMESPACE=prod-workers \
./scripts/test-kubernetes-e2e.sh
```

**Extended timeout**:
```bash
TIMEOUT=600 ./scripts/test-kubernetes-e2e.sh
```

---

## Test Scenarios

### Scenario 1: Local Development Testing

**Goal**: Test operator changes in local cluster

```bash
# 1. Start local cluster
minikube start

# 2. Build and load operator image
docker build -t hyper2kvm-operator:dev .
minikube image load hyper2kvm-operator:dev

# 3. Run unit tests
pytest tests/kubernetes/ -v

# 4. Run E2E tests
./scripts/test-kubernetes-e2e.sh
```

### Scenario 2: CI/CD Pipeline Testing

**Goal**: Automated testing in CI pipeline

```bash
# 1. Setup test cluster (kind)
kind create cluster --name hyper2kvm-test

# 2. Run all tests
pytest tests/kubernetes/ -v
./scripts/test-kubernetes-e2e.sh

# 3. Cleanup
kind delete cluster --name hyper2kvm-test
```

### Scenario 3: Production Validation

**Goal**: Validate operator in production-like environment

```bash
# 1. Deploy to staging cluster
kubectl config use-context staging
helm upgrade --install hyper2kvm-operator ./helm/hyper2kvm-operator

# 2. Run integration tests only
pytest tests/kubernetes/test_k8s_integration.py -v -m integration

# 3. Manual validation
kubectl get migrationjobs --all-namespaces
```

---

## Debugging Tests

### View Test Output

**Unit tests**:
```bash
pytest tests/kubernetes/test_operator_controller.py -v -s
```

**E2E tests**:
```bash
# Test output is displayed in real-time
./scripts/test-kubernetes-e2e.sh
```

### Check Operator Logs

```bash
# Get operator pod
kubectl get pods -n hyper2kvm-system

# View logs
kubectl logs -n hyper2kvm-system <operator-pod-name> --follow
```

### Debug Failed Tests

```bash
# Run with increased verbosity
pytest tests/kubernetes/ -vv

# Run specific failing test
pytest tests/kubernetes/test_operator_controller.py::TestOperatorController::test_create_worker_job -vv

# Keep test resources for inspection
CLEANUP=false ./scripts/test-kubernetes-e2e.sh
```

### Common Issues

**Issue**: Tests fail with "connection refused"
**Solution**: Ensure Kubernetes cluster is running and accessible

**Issue**: CRD not found errors
**Solution**: Install CRDs: `kubectl apply -f k8s/operator/crds/`

**Issue**: Operator pod not starting
**Solution**: Check image pull policy and registry access

**Issue**: Webhook validation errors
**Solution**: Ensure webhook certificates are valid

---

## Test Data

### Sample MigrationJob

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-migration
  namespace: default
spec:
  source:
    type: vmdk
    path: /vms/test.vmdk
  destination:
    format: qcow2
    path: /output/test.qcow2
  workers: 1
  resources:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "2"
      memory: "4Gi"
```

### Sample OfflineFixJob

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: OfflineFixJob
metadata:
  name: test-fix
  namespace: default
spec:
  image: /vms/test.qcow2
  fixes:
    - fstab
    - grub
    - initramfs
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
```

---

## Continuous Testing

### Pre-commit Tests

```bash
# Run quick unit tests before commit
pytest tests/kubernetes/ -v --maxfail=1
```

### Pre-push Tests

```bash
# Run full test suite before push
pytest tests/kubernetes/ -v
./scripts/test-kubernetes-e2e.sh
```

### Nightly Tests

```bash
# Full test suite with all scenarios
pytest tests/kubernetes/ -v --cov=hyper2kvm.operator
./scripts/test-kubernetes-e2e.sh
./scripts/test-k8s-centos8.sh
```

---

## Related Documentation

- **[Kubernetes Deployment Guide](../../docs/deployment/KUBERNETES_INTEGRATION.md)** - Deployment instructions
- **[CentOS 8 K8s Test Plan](../../docs/testing/CENTOS8_TEST_PLAN.md)** - CentOS 8 specific testing
- **[Operator Documentation](../../docs/deployment/v1.4.0-operator.md)** - Operator features
- **[Worker Protocol](../../docs/worker/PROTOCOL_SPEC.md)** - Worker job protocol

---

## Contributing

When adding new tests:

1. **Unit tests**: Add to appropriate test_*.py file
2. **Integration tests**: Add to test_k8s_integration.py
3. **E2E tests**: Add test phase to test-kubernetes-e2e.sh
4. **Update this README**: Document new tests and scenarios

---

## Test Metrics

**Total Test Coverage**:
- Unit tests: 49+ test cases
- Integration tests: 8+ test cases
- E2E test phases: 12 phases

**Components Tested**:
- ✅ Operator controller
- ✅ Webhook validation
- ✅ Webhook mutation
- ✅ Leader election
- ✅ Job assignment
- ✅ CRD schemas
- ✅ RBAC permissions
- ✅ Metrics collection
- ✅ Job lifecycle
- ✅ Dependencies
- ✅ High availability

---

**Last Updated**: February 2026
**Test Suite Version**: 1.0
**Kubernetes Support**: v1.24+
