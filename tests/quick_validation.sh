#!/bin/bash
# Quick validation - smoke test for all production tools

set -e

echo "Quick Validation of hyper2kvm Production Tools"
echo "=============================================="
echo ""

EXAMPLES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../examples" && pwd)"

# Find a test VM
LINUX_VM=$(find /home/ssahani/vmware -name "Ubuntu*.vmdk" -o -name "photon*.vmdk" | head -1)

if [ -z "$LINUX_VM" ]; then
    echo "Error: No test VM found"
    exit 1
fi

echo "Using test VM: $(basename "$LINUX_VM")"
echo ""

# Test each tool
echo "[1/5] Testing systemd_forensic_analysis.py..."
timeout 60 python3 "$EXAMPLES_DIR/systemd_forensic_analysis.py" "$LINUX_VM" >/dev/null 2>&1 && echo "  ✓ OK" || echo "  ✗ FAILED"

echo "[2/5] Testing migration_readiness_check.py..."
timeout 60 python3 "$EXAMPLES_DIR/migration_readiness_check.py" "$LINUX_VM" >/dev/null 2>&1 && echo "  ✓ OK" || echo "  ✗ FAILED"

echo "[3/5] Testing security_audit.py..."
timeout 60 python3 "$EXAMPLES_DIR/security_audit.py" "$LINUX_VM" >/dev/null 2>&1 && echo "  ✓ OK" || echo "  ✗ FAILED"

echo "[4/5] Testing filesystem_api_demo.py..."
timeout 60 python3 "$EXAMPLES_DIR/filesystem_api_demo.py" "$LINUX_VM" >/dev/null 2>&1 && echo "  ✓ OK" || echo "  ✗ FAILED"

# Find second VM for comparison
SECOND_VM=$(find /home/ssahani/vmware -name "openSUSE*.vmdk" -o -name "win*.vmdk" | head -1)

if [ -n "$SECOND_VM" ]; then
    echo "[5/5] Testing systemd_comparison.py..."
    timeout 90 python3 "$EXAMPLES_DIR/systemd_comparison.py" "$LINUX_VM" "$SECOND_VM" >/dev/null 2>&1 && echo "  ✓ OK" || echo "  ✗ FAILED"
else
    echo "[5/5] Skipping systemd_comparison.py (need 2 VMs)"
fi

echo ""
echo "Validation complete!"
