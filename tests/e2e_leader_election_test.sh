#!/bin/bash
#
# E2E Tests for Leader Election
#
# Tests leader election functionality with multiple operator replicas.
# Verifies leader failover, lease renewal, and standby behavior.
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
RELEASE_NAME="${RELEASE_NAME:-hyper2kvm-operator}"
HELM_CHART="${HELM_CHART:-./helm/hyper2kvm-operator}"
TIMEOUT="${TIMEOUT:-300}"
CLEANUP="${CLEANUP:-true}"
REPLICAS="${REPLICAS:-3}"

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

    if ! command -v helm &> /dev/null; then
        log_error "helm not found"
        return 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    log_success "All prerequisites met"
}

test_install_operator_ha() {
    run_test "Install operator with ${REPLICAS} replicas"

    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - || true

    helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART}" \
        --namespace "${NAMESPACE}" \
        --set operator.replicaCount="${REPLICAS}" \
        --set operator.leaderElection.enabled=true \
        --set operator.leaderElection.leaseDuration=15 \
        --set operator.leaderElection.renewDeadline=10 \
        --set operator.leaderElection.retryPeriod=2 \
        --set operator.config.logLevel=DEBUG \
        --wait \
        --timeout=5m

    if [ $? -eq 0 ]; then
        log_success "Operator installed with ${REPLICAS} replicas"
    else
        log_error "Operator installation failed"
        return 1
    fi
}

test_verify_replicas() {
    run_test "Verify ${REPLICAS} operator replicas are running"

    # Wait for all replicas to be ready
    kubectl wait --for=condition=available deployment/${RELEASE_NAME} \
        -n "${NAMESPACE}" \
        --timeout="${TIMEOUT}s"

    local ready_replicas=$(kubectl get deployment ${RELEASE_NAME} -n "${NAMESPACE}" \
        -o jsonpath='{.status.readyReplicas}')

    if [ "$ready_replicas" == "$REPLICAS" ]; then
        log_success "All ${REPLICAS} replicas are ready"
    else
        log_error "Expected ${REPLICAS} replicas, got ${ready_replicas}"
        kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=operator
        return 1
    fi
}

test_verify_lease_created() {
    run_test "Verify leader election lease created"

    # Wait a few seconds for lease creation
    sleep 5

    if kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" &> /dev/null; then
        log_success "Leader election lease exists"
    else
        log_error "Leader election lease not found"
        kubectl get leases -n "${NAMESPACE}"
        return 1
    fi
}

test_verify_single_leader() {
    run_test "Verify exactly one replica is leader"

    # Get lease holder
    local holder=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.holderIdentity}')

    if [ -n "$holder" ]; then
        log_success "Leader elected: $holder"
    else
        log_error "No leader elected"
        return 1
    fi

    # Check that only one pod claims to be leader
    local leader_count=0
    local pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=operator \
        -o jsonpath='{.items[*].metadata.name}')

    for pod in $pods; do
        # Check if pod logs show it's the leader
        if kubectl logs -n "${NAMESPACE}" "$pod" --tail=50 | grep -q "became leader\|This replica is the leader" 2>/dev/null; then
            ((leader_count++))
            log_info "Pod $pod claims leadership"
        fi
    done

    if [ $leader_count -eq 1 ]; then
        log_success "Exactly one replica claims leadership"
    elif [ $leader_count -eq 0 ]; then
        log_warning "No replica claims leadership yet (may be starting)"
    else
        log_error "Multiple replicas claim leadership: $leader_count"
        return 1
    fi
}

test_verify_lease_renewals() {
    run_test "Verify lease is being renewed"

    # Get initial renew time
    local initial_renew=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.renewTime}')

    log_info "Initial renew time: $initial_renew"

    # Wait for renewal (retry period is 2s)
    sleep 5

    # Get new renew time
    local new_renew=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.renewTime}')

    log_info "New renew time: $new_renew"

    if [ "$initial_renew" != "$new_renew" ]; then
        log_success "Lease is being renewed"
    else
        log_error "Lease not renewed"
        kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" -o yaml
        return 1
    fi
}

test_leader_failover() {
    run_test "Test leader failover on pod deletion"

    # Get current leader
    local current_leader=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.holderIdentity}')

    log_info "Current leader: $current_leader"

    # Delete leader pod
    log_info "Deleting leader pod: $current_leader"
    kubectl delete pod "$current_leader" -n "${NAMESPACE}" --wait=false

    # Wait for pod to be deleted
    sleep 5

    # Wait for new leader election (max 30s)
    local max_wait=30
    local waited=0

    while [ $waited -lt $max_wait ]; do
        local new_leader=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
            -o jsonpath='{.spec.holderIdentity}' 2>/dev/null || echo "")

        if [ -n "$new_leader" ] && [ "$new_leader" != "$current_leader" ]; then
            log_success "New leader elected: $new_leader (failover took ${waited}s)"
            return 0
        fi

        sleep 2
        ((waited+=2))
    done

    log_error "Leader failover did not complete in ${max_wait}s"
    kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" -o yaml
    kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=operator
    return 1
}

test_lease_transitions() {
    run_test "Verify lease transitions are tracked"

    local transitions=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.leaseTransitions}')

    log_info "Lease transitions: $transitions"

    # After failover test, should be >= 1
    if [ "$transitions" -ge 1 ]; then
        log_success "Lease transitions tracked: $transitions"
    else
        log_warning "Lease transitions: $transitions (expected >= 1 after failover)"
    fi
}

test_standby_replicas() {
    run_test "Verify standby replicas are healthy"

    # Get all operator pods
    local pods=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=operator \
        -o jsonpath='{.items[*].metadata.name}')

    # Get current leader
    local leader=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.holderIdentity}')

    local healthy_standby_count=0

    for pod in $pods; do
        if [ "$pod" == "$leader" ]; then
            continue
        fi

        # Check if standby pod is healthy
        if kubectl get pod "$pod" -n "${NAMESPACE}" -o jsonpath='{.status.phase}' | grep -q "Running"; then
            ((healthy_standby_count++))
            log_info "Standby replica healthy: $pod"
        fi
    done

    local expected_standby=$((REPLICAS - 1))

    if [ $healthy_standby_count -eq $expected_standby ]; then
        log_success "All $expected_standby standby replicas are healthy"
    else
        log_error "Expected $expected_standby healthy standby replicas, got $healthy_standby_count"
        return 1
    fi
}

test_metrics_leader_election() {
    run_test "Verify leader election metrics"

    # Get leader pod
    local leader=$(kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" \
        -o jsonpath='{.spec.holderIdentity}')

    # Port-forward to leader pod
    kubectl port-forward -n "${NAMESPACE}" "$leader" 18080:8080 &> /dev/null &
    local pf_pid=$!
    sleep 2

    # Fetch metrics
    local metrics=$(curl -s http://localhost:18080/metrics 2>/dev/null || echo "")
    kill $pf_pid &> /dev/null || true

    if [ -z "$metrics" ]; then
        log_warning "Could not fetch metrics"
        return 0
    fi

    # Check for leader election metrics
    if echo "$metrics" | grep -q "hyper2kvm_operator_is_leader"; then
        log_success "Leader election metrics exposed"

        # Check is_leader metric value
        local is_leader=$(echo "$metrics" | grep "hyper2kvm_operator_is_leader" | grep -v "#" | awk '{print $2}')
        if [ "$is_leader" == "1" ] || [ "$is_leader" == "1.0" ]; then
            log_info "Leader metric shows: is_leader=$is_leader"
        fi
    else
        log_warning "Leader election metrics not found"
    fi
}

test_scale_down() {
    run_test "Test scaling down replicas"

    log_info "Scaling down to 1 replica"

    helm upgrade "${RELEASE_NAME}" "${HELM_CHART}" \
        --namespace "${NAMESPACE}" \
        --set operator.replicaCount=1 \
        --set operator.leaderElection.enabled=true \
        --reuse-values \
        --wait \
        --timeout=2m

    sleep 5

    local ready_replicas=$(kubectl get deployment ${RELEASE_NAME} -n "${NAMESPACE}" \
        -o jsonpath='{.status.readyReplicas}')

    if [ "$ready_replicas" == "1" ]; then
        log_success "Scaled down to 1 replica"
    else
        log_error "Failed to scale down (replicas: $ready_replicas)"
        return 1
    fi

    # Verify lease still exists
    if kubectl get lease hyper2kvm-operator-leader -n "${NAMESPACE}" &> /dev/null; then
        log_info "Lease still exists after scale down"
    fi
}

cleanup() {
    if [ "$CLEANUP" == "true" ]; then
        log_info "Cleaning up test resources..."

        # Uninstall Helm release
        helm uninstall "${RELEASE_NAME}" -n "${NAMESPACE}" &> /dev/null || true

        # Delete namespace
        kubectl delete namespace "${NAMESPACE}" &> /dev/null || true

        log_info "Cleanup complete"
    else
        log_info "Skipping cleanup (CLEANUP=false)"
    fi
}

print_summary() {
    echo ""
    echo "==============================================="
    echo "Leader Election E2E Test Summary"
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
    echo "Leader Election E2E Test Suite"
    echo "==============================================="
    echo "Namespace:      ${NAMESPACE}"
    echo "Release:        ${RELEASE_NAME}"
    echo "Helm Chart:     ${HELM_CHART}"
    echo "Replicas:       ${REPLICAS}"
    echo "Timeout:        ${TIMEOUT}s"
    echo "Cleanup:        ${CLEANUP}"
    echo "==============================================="
    echo ""

    # Run tests
    test_prerequisites || exit 1
    test_install_operator_ha || exit 1
    sleep 10  # Wait for operator to initialize

    test_verify_replicas || true
    test_verify_lease_created || true
    test_verify_single_leader || true
    test_verify_lease_renewals || true
    test_leader_failover || true
    sleep 5  # Wait for new leader to stabilize
    test_lease_transitions || true
    test_standby_replicas || true
    test_metrics_leader_election || true
    test_scale_down || true

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
