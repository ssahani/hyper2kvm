"""Windows performance optimization modules.

This module provides performance tuning for Windows VMs migrating to KVM:

- VirtIO balloon driver auto-configuration
- TRIM/discard enablement for SSD-backed storage
- MSI interrupt configuration for VirtIO devices
- Hyper-V enlightenments removal
"""

from .balloon import configure_balloon_driver
from .trim import enable_trim_discard
from .msi import enable_msi_interrupts
from .hyperv_cleanup import cleanup_hyperv_enlightenments

__all__ = [
    "configure_balloon_driver",
    "enable_trim_discard",
    "enable_msi_interrupts",
    "cleanup_hyperv_enlightenments",
]
