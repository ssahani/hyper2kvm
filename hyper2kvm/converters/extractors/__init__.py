# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/converters/extractors/__init__.py
"""
Disk format extractors for various VM image formats.

This package provides extractors for converting VM disk images to raw format:
- ami: Amazon AMI (EC2 image format) extraction
- ovf: OVF/OVA package extraction and conversion
- raw: Raw disk image handling
- vhd: VHD/VHDX (Hyper-V) disk extraction
"""

from .ami import AMI
from .ovf import OVF
from .raw import RAW
from .vhd import VHD

__all__ = ["AMI", "OVF", "RAW", "VHD"]
