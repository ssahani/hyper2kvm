# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/transports/__init__.py
"""
VMware transport/download mechanisms.

This package provides various transport methods for downloading VM data:
- vddk_client: VMware VDDK-based transport
- vddk_loader: VDDK library loader and wrapper
- http_client: HTTPS download client
- http_progress: Progress reporters for HTTP downloads
- ovftool_client: VMware ovftool-based transport
- ovftool_loader: ovftool binary loader
- govc_common: Common govc utility functions
- govc_export: govc-based export functionality
"""

__all__ = []
