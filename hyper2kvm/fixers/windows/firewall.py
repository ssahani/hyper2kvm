# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/firewall.py

"""
Windows Firewall rule migration for preserving network security configuration.

Exports firewall rules before migration and stages import scripts for first boot.
This preserves custom firewall rules that protect applications and services.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore


def stage_firewall_export_script(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Stage a PowerShell script to export Windows Firewall rules.

    The script will run on first boot BEFORE migration to capture current rules,
    then import them after hardware change is complete.

    Args:
        g: GuestFS instance with Windows disk mounted
        root: Windows root path (e.g., '/sysroot')

    Returns:
        Dict with staging results:
            {
                "staged": bool,
                "script_path": str,
                "error": str
            }
    """
    result = {
        "staged": False,
        "script_path": None,
        "error": None,
    }

    try:
        # Create firewall backup/restore script
        script_content = _generate_firewall_migration_script()

        # Stage script in Windows directory
        script_path = f"{root}/Windows/Temp/hyper2kvm-firewall-migrate.ps1"

        g.write(script_path, script_content)
        result["staged"] = True
        result["script_path"] = script_path

        logging.info(f"✅ Staged firewall migration script: {script_path}")

        # Also create a scheduled task to run it
        task_result = _stage_firewall_migration_task(g, root)
        result["task_staged"] = task_result.get("staged", False)

    except Exception as e:
        result["error"] = str(e)
        logging.error(f"Failed to stage firewall migration script: {e}")

    return result


def _generate_firewall_migration_script() -> str:
    """
    Generate PowerShell script for firewall rule migration.

    The script:
        1. Exports current firewall rules to XML
        2. Stores them in a safe location
        3. After migration, imports them back
    """
    script = r'''# hyper2kvm Firewall Migration Script
# Preserves Windows Firewall rules during VM migration

$ErrorActionPreference = "Stop"
$LogFile = "C:\Windows\Temp\hyper2kvm-firewall-migration.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}

Write-Log "=== Windows Firewall Migration Started ==="

try {
    # Export location
    $BackupPath = "C:\Windows\Temp\hyper2kvm-firewall-backup.wfw"
    $RulesPath = "C:\Windows\Temp\hyper2kvm-firewall-rules.xml"

    # Check if this is pre-migration or post-migration
    if (-not (Test-Path $BackupPath)) {
        # PRE-MIGRATION: Export current rules
        Write-Log "Exporting firewall configuration..."

        # Export all firewall rules
        try {
            netsh advfirewall export $BackupPath | Out-Null
            Write-Log "✓ Exported firewall policy to: $BackupPath"
        } catch {
            Write-Log "⚠ Failed to export firewall policy: $_"
        }

        # Also export individual rules as XML for inspection
        try {
            $Rules = Get-NetFirewallRule | Where-Object { $_.Enabled -eq $true }
            $Rules | Export-Clixml -Path $RulesPath
            Write-Log "✓ Exported $($Rules.Count) enabled firewall rules"
        } catch {
            Write-Log "⚠ Failed to export firewall rules: $_"
        }

    } else {
        # POST-MIGRATION: Import rules back
        Write-Log "Importing firewall configuration..."

        try {
            # Import firewall policy
            netsh advfirewall import $BackupPath | Out-Null
            Write-Log "✓ Imported firewall policy from: $BackupPath"

            # Verify critical rules are present
            $RdpRule = Get-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
            if ($RdpRule) {
                Write-Log "✓ Remote Desktop firewall rules verified"
            } else {
                Write-Log "⚠ Remote Desktop rules not found - enabling..."
                Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
            }

        } catch {
            Write-Log "⚠ Failed to import firewall policy: $_"
        }

        # Clean up backup files
        Remove-Item $BackupPath -Force -ErrorAction SilentlyContinue
        Remove-Item $RulesPath -Force -ErrorAction SilentlyContinue
    }

    Write-Log "=== Firewall Migration Completed ==="

} catch {
    Write-Log "ERROR: Firewall migration failed: $_"
    Write-Log $_.ScriptStackTrace
    exit 1
}

exit 0
'''
    return script


def _stage_firewall_migration_task(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Create a scheduled task to run firewall migration on first boot.

    Uses Windows Task Scheduler XML format.
    """
    result = {"staged": False, "error": None}

    try:
        task_xml = r'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>hyper2kvm - Preserve Windows Firewall rules during migration</Description>
    <Author>hyper2kvm</Author>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -File "C:\Windows\Temp\hyper2kvm-firewall-migrate.ps1"</Arguments>
    </Exec>
  </Actions>
</Task>'''

        # Write task XML
        task_path = f"{root}/Windows/System32/Tasks/hyper2kvm-firewall-migration"

        # Ensure Tasks directory exists
        tasks_dir = f"{root}/Windows/System32/Tasks"
        if not g.is_dir(tasks_dir):
            g.mkdir_p(tasks_dir)

        g.write(task_path, task_xml)
        result["staged"] = True
        logging.info("✅ Staged firewall migration scheduled task")

    except Exception as e:
        result["error"] = str(e)
        logging.debug(f"Failed to stage firewall task: {e}")

    return result


def extract_firewall_rules_for_report(g: guestfs.GuestFS, root: str) -> List[Dict[str, Any]]:
    """
    Extract Windows Firewall rules for documentation/reporting.

    This is informational only - actual rules are migrated via scheduled task.

    Returns:
        List of firewall rule summaries for migration report
    """
    rules = []

    try:
        # Windows Firewall rules are stored in:
        # Registry: HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy
        # Files: %SystemRoot%\System32\LogFiles\Firewall\

        # For now, just log that firewall migration will occur
        rules.append({
            "name": "Windows Firewall Migration",
            "description": "Firewall rules will be exported and re-imported on first boot",
            "status": "Scheduled",
        })

    except Exception as e:
        logging.debug(f"Could not extract firewall rules: {e}")

    return rules


def verify_firewall_service_enabled(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Verify Windows Firewall service is enabled.

    If firewall is disabled, rules don't matter - document this.
    """
    result = {
        "firewall_service_enabled": None,
        "warnings": [],
    }

    try:
        # Check registry for MpsSvc (Windows Firewall service)
        # HKLM\SYSTEM\CurrentControlSet\Services\MpsSvc\Start
        # 2 = Automatic, 3 = Manual, 4 = Disabled

        system_hive_path = f"{root}/Windows/System32/config/SYSTEM"

        if g.exists(system_hive_path):
            # TODO: Read registry value using hivex
            # For now, add informational message
            result["warnings"].append(
                "ℹ️  Verify Windows Firewall service after migration:\n"
                "  PowerShell: Get-Service -Name 'MpsSvc' | Select-Object Status, StartType"
            )

    except Exception as e:
        logging.debug(f"Could not check firewall service: {e}")

    return result


def get_firewall_migration_instructions() -> str:
    """
    Return instructions for manual firewall rule migration.

    Used if automated migration fails or for documentation.
    """
    return """
Windows Firewall Rule Migration Instructions:

BEFORE MIGRATION (in VMware):
  1. Export firewall rules:
       netsh advfirewall export C:\\firewall-backup.wfw

  2. Document custom rules:
       Get-NetFirewallRule | Where-Object {$_.Direction -eq 'Inbound' -and $_.Enabled -eq $true} | Format-Table

  3. Save to external location (USB, network share)

AFTER MIGRATION (in KVM):
  1. Import firewall rules:
       netsh advfirewall import C:\\firewall-backup.wfw

  2. Verify critical rules:
       Get-NetFirewallRule -DisplayGroup "Remote Desktop"
       Get-NetFirewallRule -DisplayGroup "File and Printer Sharing"

  3. Enable RDP rule if needed:
       Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

  4. Test connectivity:
       Test-NetConnection -ComputerName localhost -Port 3389

TROUBLESHOOTING:
  - If import fails, rules may need manual recreation
  - Check Windows Event Viewer: Applications and Services Logs → Microsoft → Windows → Windows Firewall With Advanced Security
  - Reset to defaults: netsh advfirewall reset
"""
