"""MSI interrupt configuration for VirtIO devices.

Enables Message Signaled Interrupts (MSI) for VirtIO storage and network devices.
MSI interrupts can improve performance by ~20% for network throughput and reduce
interrupt latency for storage operations.
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, List

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

logger = logging.getLogger(__name__)


def enable_msi_interrupts(
    g: "guestfs.GuestFS",
    root: str,
    devices: List[str] = None,
) -> Dict[str, Any]:
    """Enable MSI interrupts for VirtIO devices.

    Args:
        g: GuestFS instance
        root: Windows root path
        devices: List of device drivers to enable MSI for (default: ["viostor", "netkvm"])

    Returns:
        Dict with configuration results

    Configuration:
        - Enables MSI for VirtIO storage (viostor)
        - Enables MSI for VirtIO network (netkvm)
        - Sets MSISupported=1 in device Parameters
        - Creates MessageSignaledInterruptProperties registry keys
    """
    if devices is None:
        devices = ["viostor", "netkvm"]

    logger.info(f"Enabling MSI interrupts for devices: {devices}")

    results = {
        "success": False,
        "devices_configured": [],
        "devices_skipped": [],
        "verification_script": None,
        "warnings": [],
    }

    try:
        from ..registry.io import detect_windows_hive, download_and_open_hive
        from ..registry.encoding import _close_best_effort, _detect_current_controlset

        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            results["warnings"].append("SYSTEM hive not found - cannot enable MSI")
            return results

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive = download_and_open_hive(logger, g, system_path, local_hive, write=True)

            try:
                root_node = hive.root()
                controlset_name = _detect_current_controlset(hive, root_node)

                for device in devices:
                    if _enable_device_msi(hive, root_node, controlset_name, device):
                        results["devices_configured"].append(device)
                        logger.info(f"MSI enabled for {device}")
                    else:
                        results["devices_skipped"].append(device)
                        logger.warning(f"Could not enable MSI for {device} (service not found)")

                # Commit changes
                from ..registry.encoding import _commit_best_effort

                _commit_best_effort(hive)

                # Upload modified hive
                g.upload(str(local_hive), system_path)

                results["success"] = len(results["devices_configured"]) > 0

            finally:
                _close_best_effort(hive)

        # Generate verification script
        verification_script = _generate_msi_verification_script(devices)

        # Stage verification script
        script_path = f"{root}/hyper2kvm/performance/msi-verify.ps1"
        try:
            g.mkdir_p(f"{root}/hyper2kvm/performance")
            g.write(script_path, verification_script.encode("utf-8"))
            results["verification_script"] = script_path
            logger.info(f"MSI verification script staged at {script_path}")
        except Exception as e:
            logger.warning(f"Failed to stage verification script: {e}")
            results["warnings"].append(f"Could not stage verification script: {e}")

    except Exception as e:
        logger.error(f"Failed to enable MSI interrupts: {e}")
        logger.debug("MSI enablement error", exc_info=True)
        results["warnings"].append(f"MSI enablement failed: {e}")

    return results


def _enable_device_msi(
    hive: "hivex.Hivex",
    root_node: int,
    controlset_name: str,
    device: str,
) -> bool:
    """Enable MSI for a specific device.

    Args:
        hive: Hivex instance
        root_node: Registry root node
        controlset_name: Current control set name
        device: Device driver name

    Returns:
        True if MSI was enabled, False otherwise
    """
    from ..registry.encoding import _ensure_child, _set_dword

    # Path: CurrentControlSet\Services\{device}\Parameters\InterruptManagement\MessageSignaledInterruptProperties
    service_path = f"{controlset_name}\\Services\\{device}"
    service_node = hive.node_get_child(root_node, service_path)

    if not service_node:
        return False

    # Create Parameters key if needed
    params_node = hive.node_get_child(service_node, "Parameters")
    if not params_node:
        params_node = _ensure_child(hive, service_node, "Parameters")

    # Create InterruptManagement key
    intmgmt_node = hive.node_get_child(params_node, "InterruptManagement")
    if not intmgmt_node:
        intmgmt_node = _ensure_child(hive, params_node, "InterruptManagement")

    # Create MessageSignaledInterruptProperties key
    msi_node = hive.node_get_child(intmgmt_node, "MessageSignaledInterruptProperties")
    if not msi_node:
        msi_node = _ensure_child(hive, intmgmt_node, "MessageSignaledInterruptProperties")

    # Set MSISupported = 1
    _set_dword(hive, msi_node, "MSISupported", 1)

    return True


def _generate_msi_verification_script(devices: List[str]) -> str:
    """Generate PowerShell script to verify MSI configuration.

    Args:
        devices: List of device names to verify

    Returns:
        PowerShell script content
    """
    devices_str = ", ".join([f'"{d}"' for d in devices])

    script = f"""# MSI Interrupt Verification Script
# Generated by hyper2kvm

$LogFile = "C:\\hyper2kvm\\performance\\msi-verify.log"

function Write-Log {{
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}}

Write-Log "=== MSI Interrupt Verification ==="

$Devices = @({devices_str})
$AllSuccess = $true

foreach ($Device in $Devices) {{
    Write-Log "Checking MSI configuration for $Device..."

    $RegPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\$Device\\Parameters\\InterruptManagement\\MessageSignaledInterruptProperties"

    if (Test-Path $RegPath) {{
        $MSISupported = Get-ItemProperty -Path $RegPath -Name "MSISupported" -ErrorAction SilentlyContinue

        if ($MSISupported) {{
            $Enabled = $MSISupported.MSISupported -eq 1
            Write-Log "$Device MSISupported: $($MSISupported.MSISupported) (Enabled: $Enabled)"

            if ($Enabled) {{
                Write-Log "SUCCESS: MSI enabled for $Device"
            }} else {{
                Write-Log "WARNING: MSI not enabled for $Device"
                $AllSuccess = $false
            }}
        }} else {{
            Write-Log "WARNING: MSISupported value not found for $Device"
            $AllSuccess = $false
        }}
    }} else {{
        Write-Log "WARNING: MSI registry path not found for $Device"
        $AllSuccess = $false
    }}
}}

# Check actual MSI usage in Device Manager (requires elevated permissions)
Write-Log "Checking MSI usage in system..."

try {{
    $MSIDevices = Get-WmiObject -Class Win32_PnPEntity | Where-Object {{
        $_.Name -match "VirtIO" -or $_.Name -match "Red Hat"
    }}

    if ($MSIDevices) {{
        foreach ($Dev in $MSIDevices) {{
            Write-Log "Device: $($Dev.Name) - Status: $($Dev.Status)"
        }}
    }} else {{
        Write-Log "INFO: No VirtIO devices found via WMI"
    }}
}} catch {{
    Write-Log "WARNING: Could not query WMI for devices: $_"
}}

Write-Log "=== Verification Complete ==="

if ($AllSuccess) {{
    Write-Log "SUCCESS: All devices configured for MSI"
    exit 0
}} else {{
    Write-Log "WARNING: Some devices may not have MSI enabled"
    exit 1
}}
"""
    return script
