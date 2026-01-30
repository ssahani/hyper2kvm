#!/bin/bash
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Validation script for hyper2kvm production tools
#
# Tests all 5 example tools against multiple VM types to ensure:
# - Proper error handling
# - Correct output formats
# - No crashes on different OS types
# - Reports generated successfully
#
# Usage:
#   ./tests/validate_tools.sh [vm-directory]
#
# Example:
#   ./tests/validate_tools.sh /home/ssahani/vmware

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXAMPLES_DIR="$PROJECT_DIR/examples"

# Default VM directory
VM_DIR="${1:-/home/ssahani/vmware}"

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_test_pass() {
    echo -e "${GREEN}[✓]${NC} $*"
    ((TESTS_PASSED++))
}

log_test_fail() {
    echo -e "${RED}[✗]${NC} $*"
    ((TESTS_FAILED++))
}

test_tool() {
    local tool_name="$1"
    local tool_script="$2"
    local vm_path="$3"
    local vm_type="$4"
    local extra_args="${5:-}"

    ((TESTS_RUN++))

    log_info "Testing $tool_name on $vm_type VM..."

    # Run tool and capture exit code
    if timeout 180 python3 "$EXAMPLES_DIR/$tool_script" $extra_args "$vm_path" >/dev/null 2>&1; then
        log_test_pass "$tool_name works on $vm_type"
        return 0
    else
        local exit_code=$?
        if [ $exit_code -eq 124 ]; then
            log_test_fail "$tool_name timed out on $vm_type (>180s)"
        else
            log_test_fail "$tool_name failed on $vm_type (exit code: $exit_code)"
        fi
        return 1
    fi
}

test_output_file() {
    local file_path="$1"
    local description="$2"

    ((TESTS_RUN++))

    if [ -f "$file_path" ]; then
        local size=$(stat -c%s "$file_path" 2>/dev/null || stat -f%z "$file_path" 2>/dev/null || echo "0")
        if [ "$size" -gt 0 ]; then
            log_test_pass "$description exists and has content ($size bytes)"
            return 0
        else
            log_test_fail "$description exists but is empty"
            return 1
        fi
    else
        log_test_fail "$description was not generated"
        return 1
    fi
}

echo "================================================================================"
echo " hyper2kvm Production Tools Validation"
echo "================================================================================"
echo ""

# Check if examples directory exists
if [ ! -d "$EXAMPLES_DIR" ]; then
    log_error "Examples directory not found: $EXAMPLES_DIR"
    exit 1
fi

# Check if VM directory exists
if [ ! -d "$VM_DIR" ]; then
    log_error "VM directory not found: $VM_DIR"
    exit 1
fi

log_info "VM Directory: $VM_DIR"
log_info "Examples Directory: $EXAMPLES_DIR"
echo ""

# Find test VMs
log_info "Discovering VM disk images..."
LINUX_VM=""
WINDOWS_VM=""

# Find first Linux VM (Ubuntu or openSUSE)
for vm in "$VM_DIR"/Ubuntu*/Ubuntu*.vmdk "$VM_DIR"/*/openSUSE*.vmdk "$VM_DIR"/*/photon*.vmdk; do
    if [ -f "$vm" ]; then
        LINUX_VM="$vm"
        log_info "Found Linux VM: $(basename "$vm")"
        break
    fi
done

# Find first Windows VM
for vm in "$VM_DIR"/win*/win*.vmdk "$VM_DIR"/Windows*/*.vmdk; do
    if [ -f "$vm" ]; then
        WINDOWS_VM="$vm"
        log_info "Found Windows VM: $(basename "$vm")"
        break
    fi
done

if [ -z "$LINUX_VM" ]; then
    log_warn "No Linux VM found for testing"
fi

if [ -z "$WINDOWS_VM" ]; then
    log_warn "No Windows VM found for testing"
fi

echo ""

# Clean up old test reports
log_info "Cleaning up old test reports..."
rm -f /tmp/forensic_analysis_report.json
rm -f /tmp/migration_readiness_*.json
rm -f /tmp/security_audit_*.{html,json,txt}
rm -f /tmp/systemd_comparison_report.json
rm -f /tmp/filesystem_api_demo_*.json
rm -f /tmp/boot-plot.svg
rm -f /tmp/journal_export.bin

echo ""
echo "================================================================================"
echo " Testing systemd Forensic Analysis"
echo "================================================================================"
echo ""

if [ -n "$LINUX_VM" ]; then
    test_tool "systemd_forensic_analysis.py" "systemd_forensic_analysis.py" "$LINUX_VM" "Linux"
    test_output_file "/tmp/forensic_analysis_report.json" "Forensic analysis report"
fi

if [ -n "$WINDOWS_VM" ]; then
    test_tool "systemd_forensic_analysis.py" "systemd_forensic_analysis.py" "$WINDOWS_VM" "Windows"
fi

echo ""
echo "================================================================================"
echo " Testing Migration Readiness Check"
echo "================================================================================"
echo ""

if [ -n "$LINUX_VM" ]; then
    test_tool "migration_readiness_check.py" "migration_readiness_check.py" "$LINUX_VM" "Linux"

    # Extract VM name for report file
    VM_NAME=$(basename "$LINUX_VM" .vmdk)
    test_output_file "/tmp/migration_readiness_${VM_NAME}.json" "Migration readiness report"
fi

if [ -n "$WINDOWS_VM" ]; then
    test_tool "migration_readiness_check.py" "migration_readiness_check.py" "$WINDOWS_VM" "Windows"
fi

echo ""
echo "================================================================================"
echo " Testing Security Audit"
echo "================================================================================"
echo ""

if [ -n "$LINUX_VM" ]; then
    # Test text output (default)
    test_tool "security_audit.py (text)" "security_audit.py" "$LINUX_VM" "Linux"

    # Test JSON output
    test_tool "security_audit.py (JSON)" "security_audit.py" "$LINUX_VM" "Linux" "--format json"

    # Test HTML output
    test_tool "security_audit.py (HTML)" "security_audit.py" "$LINUX_VM" "Linux" "--format html"

    # Check for HTML report (most recent)
    LATEST_HTML=$(ls -t /tmp/security_audit_*.html 2>/dev/null | head -1 || echo "")
    if [ -n "$LATEST_HTML" ]; then
        test_output_file "$LATEST_HTML" "Security audit HTML report"
    fi
fi

echo ""
echo "================================================================================"
echo " Testing systemd Comparison"
echo "================================================================================"
echo ""

if [ -n "$LINUX_VM" ] && [ -n "$WINDOWS_VM" ]; then
    test_tool "systemd_comparison.py" "systemd_comparison.py" "$LINUX_VM $WINDOWS_VM" "Linux+Windows"
    test_output_file "/tmp/systemd_comparison_report.json" "systemd comparison report"
elif [ -n "$LINUX_VM" ]; then
    log_warn "Skipping systemd_comparison.py (need at least 2 VMs)"
fi

echo ""
echo "================================================================================"
echo " Testing Filesystem API Demo"
echo "================================================================================"
echo ""

if [ -n "$LINUX_VM" ]; then
    test_tool "filesystem_api_demo.py" "filesystem_api_demo.py" "$LINUX_VM" "Linux"

    # Extract VM name for report file
    VM_NAME=$(basename "$LINUX_VM" .vmdk)
    test_output_file "/tmp/filesystem_api_demo_${VM_NAME}.json" "Filesystem API demo report"
fi

if [ -n "$WINDOWS_VM" ]; then
    test_tool "filesystem_api_demo.py" "filesystem_api_demo.py" "$WINDOWS_VM" "Windows"
fi

echo ""
echo "================================================================================"
echo " VALIDATION SUMMARY"
echo "================================================================================"
echo ""

echo "Tests Run:    $TESTS_RUN"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    log_info "All tests passed! ✓"
    echo ""
    echo "Production tools are validated and ready for use."
    exit 0
else
    log_error "$TESTS_FAILED test(s) failed"
    echo ""
    echo "Some tests failed. Please review the output above."
    exit 1
fi
