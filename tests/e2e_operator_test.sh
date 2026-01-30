#!/bin/bash
#
# End-to-End Test Suite for hyper2kvm Operator
# Tests operator deployment, webhook functionality, and job lifecycle
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
WORKER_NAMESPACE="${WORKER_NAMESPACE:-hyper2kvm-workers}"
RELEASE_NAME="${RELEASE_NAME:-hyper2kvm-operator}"
HELM_CHART="${HELM_CHART:-./helm/hyper2kvm-operator}"
TIMEOUT="${TIMEOUT:-300}"
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

wait_for_pod() {
    local namespace=$1
    local label=$2
    local timeout=$3

    log_info "Waiting for pod with label ${label} in namespace ${namespace}..."

    kubectl wait --for=condition=ready pod \
        -l "${label}" \
        -n "${namespace}" \
        --timeout="${timeout}s" 2>/dev/null
}

wait_for_deployment() {
    local namespace=$1
    local deployment=$2
    local timeout=$3

    log_info "Waiting for deployment ${deployment} in namespace ${namespace}..."

    kubectl wait --for=condition=available deployment/${deployment} \
        -n "${namespace}" \
        --timeout="${timeout}s"
}

# Test functions

test_prerequisites() {
    run_test "Check prerequisites"

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found"
        return 1
    fi

    # Check helm
    if ! command -v helm &> /dev/null; then
        log_error "helm not found"
        return 1
    fi

    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    log_success "All prerequisites met"
}

test_helm_install() {
    run_test "Install operator via Helm"

    # Create namespace
    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - || true

    # Install chart
    helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART}" \
        --namespace "${NAMESPACE}" \
        --set operator.config.logLevel=DEBUG \
        --set webhook.enabled=true \
        --wait \
        --timeout=5m

    if [ $? -eq 0 ]; then
        log_success "Operator installed successfully"
    else
        log_error "Operator installation failed"
        return 1
    fi
}

test_crd_installation() {
    run_test "Verify CRD installation"

    if kubectl get crd migrationjobs.hyper2kvm.io &> /dev/null; then
        log_success "MigrationJob CRD is installed"
    else
        log_error "MigrationJob CRD not found"
        return 1
    fi

    # Verify CRD version
    local version=$(kubectl get crd migrationjobs.hyper2kvm.io -o jsonpath='{.spec.versions[0].name}')
    if [ "$version" == "v1alpha1" ]; then
        log_success "CRD version is v1alpha1"
    else
        log_error "CRD version mismatch: expected v1alpha1, got $version"
        return 1
    fi
}

test_operator_deployment() {
    run_test "Verify operator deployment"

    # Wait for operator pod
    if wait_for_deployment "${NAMESPACE}" "${RELEASE_NAME}" "${TIMEOUT}"; then
        log_success "Operator deployment is ready"
    else
        log_error "Operator deployment failed to become ready"
        kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=operator
        kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/component=operator --tail=50 || true
        return 1
    fi

    # Check operator pod health
    local operator_pod=$(kubectl get pod -n "${NAMESPACE}" -l app.kubernetes.io/component=operator -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$operator_pod" ]; then
        log_success "Operator pod is running: $operator_pod"
    else
        log_error "Operator pod not found"
        return 1
    fi
}

test_webhook_deployment() {
    run_test "Verify webhook deployment"

    # Wait for webhook pods
    if wait_for_deployment "${NAMESPACE}" "${RELEASE_NAME}-webhook" "${TIMEOUT}"; then
        log_success "Webhook deployment is ready"
    else
        log_error "Webhook deployment failed to become ready"
        kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=webhook
        kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/component=webhook --tail=50 || true
        return 1
    fi

    # Check webhook replicas
    local replicas=$(kubectl get deployment -n "${NAMESPACE}" "${RELEASE_NAME}-webhook" -o jsonpath='{.spec.replicas}')
    local ready_replicas=$(kubectl get deployment -n "${NAMESPACE}" "${RELEASE_NAME}-webhook" -o jsonpath='{.status.readyReplicas}')

    if [ "$replicas" == "$ready_replicas" ]; then
        log_success "All webhook replicas are ready ($ready_replicas/$replicas)"
    else
        log_error "Webhook replicas not ready ($ready_replicas/$replicas)"
        return 1
    fi
}

test_webhook_configurations() {
    run_test "Verify webhook configurations"

    # Check validating webhook
    if kubectl get validatingwebhookconfiguration "${RELEASE_NAME}-validating" &> /dev/null; then
        log_success "ValidatingWebhookConfiguration exists"
    else
        log_error "ValidatingWebhookConfiguration not found"
        return 1
    fi

    # Check mutating webhook
    if kubectl get mutatingwebhookconfiguration "${RELEASE_NAME}-mutating" &> /dev/null; then
        log_success "MutatingWebhookConfiguration exists"
    else
        log_error "MutatingWebhookConfiguration not found"
        return 1
    fi

    # Verify CA bundle is set
    local ca_bundle=$(kubectl get validatingwebhookconfiguration "${RELEASE_NAME}-validating" \
        -o jsonpath='{.webhooks[0].clientConfig.caBundle}')

    if [ -n "$ca_bundle" ] && [ "$ca_bundle" != "Cg==" ]; then
        log_success "CA bundle is configured"
    else
        log_error "CA bundle is not set or is placeholder"
        return 1
    fi
}

test_operator_health() {
    run_test "Check operator health endpoint"

    local operator_pod=$(kubectl get pod -n "${NAMESPACE}" -l app.kubernetes.io/component=operator -o jsonpath='{.items[0].metadata.name}')

    # Port-forward and test health endpoint
    kubectl port-forward -n "${NAMESPACE}" "${operator_pod}" 18080:8080 &> /dev/null &
    local pf_pid=$!
    sleep 2

    local health_status=$(curl -s http://localhost:18080/healthz || echo "failed")
    kill $pf_pid &> /dev/null || true

    if [ "$health_status" != "failed" ]; then
        log_success "Operator health endpoint responds"
    else
        log_error "Operator health endpoint failed"
        return 1
    fi
}

test_webhook_health() {
    run_test "Check webhook health endpoint"

    local webhook_pod=$(kubectl get pod -n "${NAMESPACE}" -l app.kubernetes.io/component=webhook -o jsonpath='{.items[0].metadata.name}')

    # Port-forward and test health endpoint
    kubectl port-forward -n "${NAMESPACE}" "${webhook_pod}" 18080:8080 &> /dev/null &
    local pf_pid=$!
    sleep 2

    local health_status=$(curl -s http://localhost:18080/healthz || echo "failed")
    kill $pf_pid &> /dev/null || true

    if [ "$health_status" != "failed" ]; then
        log_success "Webhook health endpoint responds"
    else
        log_error "Webhook health endpoint failed"
        return 1
    fi
}

test_metrics_endpoints() {
    run_test "Verify Prometheus metrics endpoints"

    local operator_pod=$(kubectl get pod -n "${NAMESPACE}" -l app.kubernetes.io/component=operator -o jsonpath='{.items[0].metadata.name}')

    # Port-forward and fetch metrics
    kubectl port-forward -n "${NAMESPACE}" "${operator_pod}" 18080:8080 &> /dev/null &
    local pf_pid=$!
    sleep 2

    local metrics=$(curl -s http://localhost:18080/metrics | grep "hyper2kvm_operator" || echo "")
    kill $pf_pid &> /dev/null || true

    if [ -n "$metrics" ]; then
        log_success "Operator metrics are exposed"
    else
        log_error "Operator metrics not found"
        return 1
    fi
}

test_webhook_validation_success() {
    run_test "Test webhook validation (valid job)"

    # Create valid job
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-valid-job
  namespace: default
spec:
  operation: inspect
  image:
    path: /data/test.vmdk
    format: vmdk
EOF

    if [ $? -eq 0 ]; then
        log_success "Valid job was accepted by webhook"
        kubectl delete migrationjob test-valid-job -n default &> /dev/null || true
    else
        log_error "Valid job was rejected by webhook"
        return 1
    fi
}

test_webhook_validation_failure() {
    run_test "Test webhook validation (invalid job)"

    # Create invalid job (invalid operation)
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-invalid-job
  namespace: default
spec:
  operation: invalid_operation
  image:
    path: /data/test.vmdk
    format: vmdk
EOF

    if [ $? -ne 0 ]; then
        log_success "Invalid job was correctly rejected by webhook"
    else
        log_error "Invalid job was not rejected by webhook"
        kubectl delete migrationjob test-invalid-job -n default &> /dev/null || true
        return 1
    fi
}

test_webhook_mutation() {
    run_test "Test webhook mutation (default values)"

    # Create job without priority/timeout
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-mutation-job
  namespace: default
spec:
  operation: convert
  image:
    path: /data/test.vmdk
    format: vmdk
EOF

    # Check if defaults were applied
    local priority=$(kubectl get migrationjob test-mutation-job -n default -o jsonpath='{.spec.priority}')
    local timeout=$(kubectl get migrationjob test-mutation-job -n default -o jsonpath='{.spec.timeout}')

    kubectl delete migrationjob test-mutation-job -n default &> /dev/null || true

    if [ "$priority" == "50" ] && [ "$timeout" == "2h" ]; then
        log_success "Webhook mutation applied defaults (priority=50, timeout=2h)"
    else
        log_error "Webhook mutation failed (priority=$priority, timeout=$timeout)"
        return 1
    fi
}

test_servicemonitor() {
    run_test "Verify ServiceMonitor creation"

    # Check if ServiceMonitor CRD exists
    if ! kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        log_warning "ServiceMonitor CRD not found (Prometheus Operator not installed)"
        return 0
    fi

    # Check operator ServiceMonitor
    if kubectl get servicemonitor -n "${NAMESPACE}" "${RELEASE_NAME}" &> /dev/null; then
        log_success "Operator ServiceMonitor exists"
    else
        log_error "Operator ServiceMonitor not found"
        return 1
    fi

    # Check webhook ServiceMonitor
    if kubectl get servicemonitor -n "${NAMESPACE}" "${RELEASE_NAME}-webhook" &> /dev/null; then
        log_success "Webhook ServiceMonitor exists"
    else
        log_error "Webhook ServiceMonitor not found"
        return 1
    fi
}

test_helm_test() {
    run_test "Run Helm tests"

    if helm test "${RELEASE_NAME}" -n "${NAMESPACE}" --timeout=2m; then
        log_success "Helm tests passed"
    else
        log_error "Helm tests failed"
        kubectl logs -n "${NAMESPACE}" "${RELEASE_NAME}-test-connection" || true
        return 1
    fi
}

cleanup() {
    if [ "$CLEANUP" == "true" ]; then
        log_info "Cleaning up test resources..."

        # Delete test jobs
        kubectl delete migrationjob --all -n default &> /dev/null || true

        # Uninstall Helm release
        helm uninstall "${RELEASE_NAME}" -n "${NAMESPACE}" &> /dev/null || true

        # Delete namespace (keeps CRDs due to resource-policy: keep)
        kubectl delete namespace "${NAMESPACE}" &> /dev/null || true

        log_info "Cleanup complete"
    else
        log_info "Skipping cleanup (CLEANUP=false)"
    fi
}

print_summary() {
    echo ""
    echo "==============================================="
    echo "E2E Test Summary"
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
    echo "hyper2kvm Operator E2E Test Suite"
    echo "==============================================="
    echo "Namespace:      ${NAMESPACE}"
    echo "Release:        ${RELEASE_NAME}"
    echo "Helm Chart:     ${HELM_CHART}"
    echo "Timeout:        ${TIMEOUT}s"
    echo "Cleanup:        ${CLEANUP}"
    echo "==============================================="
    echo ""

    # Run tests
    test_prerequisites || exit 1
    test_helm_install || exit 1
    sleep 5  # Allow cert-job to complete

    test_crd_installation || true
    test_operator_deployment || true
    test_webhook_deployment || true
    test_webhook_configurations || true
    test_operator_health || true
    test_webhook_health || true
    test_metrics_endpoints || true
    test_webhook_validation_success || true
    test_webhook_validation_failure || true
    test_webhook_mutation || true
    test_servicemonitor || true
    test_helm_test || true

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
