"""
Offline VM Fix Operations

Portable repair scripts that run inside offline-fix VMs or on bare metal.
These operations require full NBD partition access and guest filesystem mounting.

All fixers are:
- Idempotent: Safe to re-run multiple times
- Portable: Work in VM, bare metal, or online mode
- OS-aware: Detect and adapt to different distros
- Testable: Can be validated on real disk images
"""

from .fix_fstab import FstabFixer
from .utils import (
    get_block_device_uuid,
    get_block_device_label,
    detect_os_from_root,
    is_lvm_device
)

__all__ = [
    'FstabFixer',
    'get_block_device_uuid',
    'get_block_device_label',
    'detect_os_from_root',
    'is_lvm_device'
]
