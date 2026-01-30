# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/__init__.py
"""
hyper2kvm - Hypervisor to KVM Migration Library

A comprehensive tool for migrating virtual machines from various hypervisors
(VMware, Hyper-V, Azure) to KVM/libvirt.

Usage as a library:

    from hyper2kvm import Orchestrator, GuestDetector, VMwareClient

    # Detect guest OS
    detector = GuestDetector()
    guest = detector.detect('/mnt/disk')

    # Migrate from VMware
    client = VMwareClient(host='vcenter.example.com', ...)
    orchestrator = Orchestrator(vmware_client=client)
    result = orchestrator.run()

See docs/08-Library-API.md for detailed usage examples.
"""

__version__ = "0.2.0"

# High-level orchestration
# Platform providers
from .azure import AzureConfig, AzureSourceProvider

# Guest detection
from .core import GuestDetector, GuestIdentity, GuestType
from .orchestrator import DiskProcessor, Orchestrator
from .vmware import VMwareClient

__all__ = [
    # Version
    "__version__",

    # Orchestration
    "Orchestrator",
    "DiskProcessor",

    # Guest detection
    "GuestIdentity",
    "GuestDetector",
    "GuestType",

    # Platform providers
    "AzureSourceProvider",
    "AzureConfig",
    "VMwareClient",
]
