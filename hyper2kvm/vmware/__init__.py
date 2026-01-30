# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/__init__.py
"""VMware/vSphere integration for VM migration."""

from .clients.client import VMwareClient

__all__ = ["VMwareClient"]
