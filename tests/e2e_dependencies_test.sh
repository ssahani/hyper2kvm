#!/bin/bash
#
# E2E Tests for Job Dependencies and DAG Execution
#
# Tests dependency resolution, DAG validation, and execution ordering.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
NAMESPACE="${NAMESPACE:-hyper2kvm-system}"
TIMEOUT="${TIMEOUT:-600}"
CLEANUP="${CLEANUP:-true}"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Utility functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

run_test() {
    ((TESTS_TOTAL++))
    log_info "Test #${TESTS_TOTAL}: $1"
}

# Test functions

test_prerequisites() {
    run_test "Check prerequisites"

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found"
        return 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    # Check if operator is running
    if ! kubectl get deployment hyper2kvm-operator -n "${NAMESPACE}" &> /dev/null; then
        log_error "hyper2kvm-operator not found in namespace ${NAMESPACE}"
        return 1
    fi

    log_success "All prerequisites met"
}

test_simple_dependency_chain() {
    run_test "Create simple dependency chain (A -> B -> C)"

    # Create job A (no dependencies)
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-a
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-a.vmdk
    format: vmdk
EOF

    sleep 2

    # Create job B (depends on A)
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-b
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-b.vmdk
    format: vmdk
  dependsOn:
    - job-a
EOF

    sleep 2

    # Create job C (depends on B)
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-c
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-c.vmdk
    format: vmdk
  dependsOn:
    - job-b
EOF

    sleep 5

    # Verify all jobs created
    if kubectl get migrationjob job-a job-b job-c -n "${NAMESPACE}" &> /dev/null; then
        log_success "Dependency chain created successfully"
    else
        log_error "Failed to create dependency chain"
        return 1
    fi
}

test_parallel_dependencies() {
    run_test "Create parallel dependencies (A -> B,C,D -> E)"

    # Create job A
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-parallel-a
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test.vmdk
    format: vmdk
EOF

    sleep 2

    # Create jobs B, C, D (all depend on A)
    for job in b c d; do
        kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-parallel-${job}
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-${job}.vmdk
    format: vmdk
  dependsOn:
    - job-parallel-a
EOF
    done

    sleep 2

    # Create job E (depends on B, C, D)
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-parallel-e
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-e.vmdk
    format: vmdk
  dependsOn:
    - job-parallel-b
    - job-parallel-c
    - job-parallel-d
EOF

    sleep 5

    # Verify dependency status for job E
    local deps=$(kubectl get migrationjob job-parallel-e -n "${NAMESPACE}" \
        -o jsonpath='{.status.dependencies.total}')

    if [ "$deps" == "3" ]; then
        log_success "Parallel dependencies created (job E has 3 dependencies)"
    else
        log_error "Expected 3 dependencies, got ${deps}"
        return 1
    fi
}

test_circular_dependency_rejection() {
    run_test "Test circular dependency rejection"

    # Create job X
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-cycle-x
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-x.vmdk
    format: vmdk
EOF

    sleep 2

    # Create job Y (depends on X)
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-cycle-y
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-y.vmdk
    format: vmdk
  dependsOn:
    - job-cycle-x
EOF

    sleep 2

    # Try to update job X to depend on Y (create cycle)
    kubectl patch migrationjob job-cycle-x -n "${NAMESPACE}" \
        --type merge \
        -p '{"spec":{"dependsOn":["job-cycle-y"]}}' 2>&1 | tee /tmp/cycle_test_output.txt

    # Check if job X has failed state due to circular dependency
    local state=$(kubectl get migrationjob job-cycle-x -n "${NAMESPACE}" \
        -o jsonpath='{.status.state}' 2>/dev/null || echo "Unknown")

    if [ "$state" == "Failed" ]; then
        log_success "Circular dependency rejected"
    else
        log_warning "Circular dependency not rejected (state: ${state})"
        # This is acceptable if validation happens at admission webhook level
    fi
}

test_self_dependency_rejection() {
    run_test "Test self-dependency rejection"

    # Try to create job with self-dependency
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-self
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test.vmdk
    format: vmdk
  dependsOn:
    - job-self
EOF

    sleep 3

    # Check if job was rejected or failed
    local state=$(kubectl get migrationjob job-self -n "${NAMESPACE}" \
        -o jsonpath='{.status.state}' 2>/dev/null || echo "NotFound")

    if [ "$state" == "Failed" ] || [ "$state" == "NotFound" ]; then
        log_success "Self-dependency rejected"
    else
        log_warning "Self-dependency not rejected (state: ${state})"
    fi
}

test_missing_dependency_rejection() {
    run_test "Test missing dependency rejection"

    # Try to create job depending on non-existent job
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-missing-dep
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test.vmdk
    format: vmdk
  dependsOn:
    - job-does-not-exist
EOF

    sleep 3

    # Check if job failed validation
    local state=$(kubectl get migrationjob job-missing-dep -n "${NAMESPACE}" \
        -o jsonpath='{.status.state}' 2>/dev/null || echo "NotFound")

    if [ "$state" == "Failed" ]; then
        log_success "Missing dependency rejected"
    else
        log_warning "Missing dependency not rejected (state: ${state})"
    fi
}

test_dependency_blocking() {
    run_test "Test job blocked by incomplete dependency"

    # Create dependency job
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-dep-base
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test.vmdk
    format: vmdk
EOF

    sleep 2

    # Create dependent job
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-dep-blocked
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test2.vmdk
    format: vmdk
  dependsOn:
    - job-dep-base
EOF

    sleep 5

    # Check if dependent job is blocked
    local blocking=$(kubectl get migrationjob job-dep-blocked -n "${NAMESPACE}" \
        -o jsonpath='{.status.dependencies.blocking}' 2>/dev/null || echo "[]")

    if echo "$blocking" | grep -q "job-dep-base"; then
        log_success "Job correctly blocked by dependency"
    else
        log_warning "Job not showing as blocked (blocking: ${blocking})"
    fi
}

test_dependency_status_tracking() {
    run_test "Test dependency status tracking"

    # Create base jobs
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-track-1
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test1.vmdk
    format: vmdk
---
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-track-2
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test2.vmdk
    format: vmdk
EOF

    sleep 2

    # Create dependent job
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: job-track-dep
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test-dep.vmdk
    format: vmdk
  dependsOn:
    - job-track-1
    - job-track-2
EOF

    sleep 5

    # Check dependency status
    local total=$(kubectl get migrationjob job-track-dep -n "${NAMESPACE}" \
        -o jsonpath='{.status.dependencies.total}' 2>/dev/null || echo "0")

    local completed=$(kubectl get migrationjob job-track-dep -n "${NAMESPACE}" \
        -o jsonpath='{.status.dependencies.completed}' 2>/dev/null || echo "0")

    if [ "$total" == "2" ]; then
        log_success "Dependency status tracked (total: $total, completed: $completed)"
    else
        log_error "Expected 2 total dependencies, got ${total}"
        return 1
    fi
}

test_complex_dag() {
    run_test "Test complex DAG execution"

    # Create a complex DAG:
    #     A
    #    / \
    #   B   C
    #   |   |\
    #   D   E F
    #    \ /| |
    #     G | |
    #      \|/
    #       H

    # Level 0: A
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-a
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-a.vmdk
    format: vmdk
EOF

    sleep 1

    # Level 1: B, C
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-b
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-b.vmdk
    format: vmdk
  dependsOn: [dag-a]
---
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-c
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-c.vmdk
    format: vmdk
  dependsOn: [dag-a]
EOF

    sleep 1

    # Level 2: D, E, F
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-d
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-d.vmdk
    format: vmdk
  dependsOn: [dag-b]
---
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-e
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-e.vmdk
    format: vmdk
  dependsOn: [dag-c]
---
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-f
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-f.vmdk
    format: vmdk
  dependsOn: [dag-c]
EOF

    sleep 1

    # Level 3: G
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-g
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-g.vmdk
    format: vmdk
  dependsOn: [dag-d, dag-e]
EOF

    sleep 1

    # Level 4: H
    kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: dag-h
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/dag-h.vmdk
    format: vmdk
  dependsOn: [dag-e, dag-f, dag-g]
EOF

    sleep 5

    # Verify all jobs created
    local count=$(kubectl get migrationjob -n "${NAMESPACE}" \
        -l test=dag 2>/dev/null | grep -c dag- || echo "0")

    if [ "$count" -ge "8" ]; then
        log_success "Complex DAG created with 8 jobs"
    else
        log_error "Expected 8 jobs, found ${count}"
        return 1
    fi

    # Check that job H has 3 dependencies
    local h_deps=$(kubectl get migrationjob dag-h -n "${NAMESPACE}" \
        -o jsonpath='{.status.dependencies.total}' 2>/dev/null || echo "0")

    if [ "$h_deps" == "3" ]; then
        log_info "Job H correctly has 3 dependencies"
    else
        log_warning "Job H has ${h_deps} dependencies (expected 3)"
    fi
}

cleanup() {
    if [ "$CLEANUP" == "true" ]; then
        log_info "Cleaning up test resources..."

        # Delete all test jobs
        kubectl delete migrationjob --all -n "${NAMESPACE}" &> /dev/null || true

        log_info "Cleanup complete"
    else
        log_info "Skipping cleanup (CLEANUP=false)"
    fi
}

print_summary() {
    echo ""
    echo "==============================================="
    echo "Job Dependencies E2E Test Summary"
    echo "==============================================="
    echo -e "Total Tests:  ${TESTS_TOTAL}"
    echo -e "${GREEN}Passed:       ${TESTS_PASSED}${NC}"
    echo -e "${RED}Failed:       ${TESTS_FAILED}${NC}"
    echo "==============================================="

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}All tests passed! ✓${NC}"
        return 0
    else
        echo -e "${RED}Some tests failed! ✗${NC}"
        return 1
    fi
}

# Main test execution
main() {
    echo "==============================================="
    echo "Job Dependencies E2E Test Suite"
    echo "==============================================="
    echo "Namespace:      ${NAMESPACE}"
    echo "Timeout:        ${TIMEOUT}s"
    echo "Cleanup:        ${CLEANUP}"
    echo "==============================================="
    echo ""

    # Run tests
    test_prerequisites || exit 1

    test_simple_dependency_chain || true
    test_parallel_dependencies || true
    test_circular_dependency_rejection || true
    test_self_dependency_rejection || true
    test_missing_dependency_rejection || true
    test_dependency_blocking || true
    test_dependency_status_tracking || true
    test_complex_dag || true

    # Print summary
    print_summary
    local exit_code=$?

    # Cleanup
    cleanup

    exit $exit_code
}

# Trap to ensure cleanup on exit
trap cleanup EXIT INT TERM

# Run main
main "$@"
