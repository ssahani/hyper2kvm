"""
Windows migration support module.

This module provides specialized functionality for Windows VM migrations including:
- Automated license reactivation (KMS, MAK, OEM)
- Active Directory integration and domain rejoin
- SQL Server migration support
- Windows Update integration for VirtIO drivers
"""

from hyper2kvm.windows.license import WindowsLicenseManager
from hyper2kvm.windows.active_directory import ActiveDirectoryManager
from hyper2kvm.windows.sql_server import SQLServerManager
from hyper2kvm.windows.windows_update import WindowsUpdateManager

__all__ = [
    "WindowsLicenseManager",
    "ActiveDirectoryManager",
    "SQLServerManager",
    "WindowsUpdateManager",
]
