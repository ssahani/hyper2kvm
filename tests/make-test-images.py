#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
make-test-images.py

Create test disk images for hyper2kvm test suite.

This script generates various disk images used to test hyper2kvm functionality:
- VMDK descriptor and extent pairs
- Different disk layouts (flat, sparse, split)
- Various filesystem configurations
- Test cases for path traversal and security
- Multi-disk configurations

Usage:
    ./make-test-images.py simple /path/to/test/data
    ./make-test-images.py vmdk-descriptor /path/to/test/data
    ./make-test-images.py multi-extent /path/to/test/data
    ./make-test-images.py security /path/to/test/data
    ./make-test-images.py all /path/to/test/data

Layouts:
    simple          - Single raw disk image with ext4 filesystem
    vmdk-descriptor - VMDK descriptor + flat extent pair
    multi-extent    - VMDK with multiple extent files
    security        - Test images for security validation
    all             - Create all test images
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

# Configuration constants
IMAGE_SIZE_SMALL = 100 * 1024 * 1024  # 100 MiB
IMAGE_SIZE_MEDIUM = 500 * 1024 * 1024  # 500 MiB
IMAGE_SIZE_LARGE = 1 * 1024 * 1024 * 1024  # 1 GiB

SECTOR_SIZE = 512


def info(msg: str) -> None:
    """Print informational message."""
    print(f"ℹ  {msg}")


def success(msg: str) -> None:
    """Print success message."""
    print(f"✓  {msg}")


def warn(msg: str) -> None:
    """Print warning message."""
    print(f"⚠  {msg}")


def error(msg: str) -> NoReturn:
    """Print error and exit."""
    print(f"✗  {msg}", file=sys.stderr)
    sys.exit(1)


class TestImageCreator:
    """
    Create test disk images for hyper2kvm.

    Parameters
    ----------
    layout : str
        Image layout type (simple, vmdk-descriptor, multi-extent, security, all)
    output_dir : Path
        Directory where images will be created
    """

    def __init__(self, layout: str, output_dir: Path) -> None:
        self.layout = layout.lower()
        self.output_dir = output_dir
        self.images: list[str] = []

    def _create_vmdk_descriptor(
        self,
        name: str,
        create_type: str,
        extents: list[tuple[str, int, str]],
        cid: str = "12345678",
        adapter_type: str = "lsilogic",
        hw_version: str = "14"
    ) -> str:
        """
        Create a VMDK descriptor file.

        Parameters
        ----------
        name : str
            Base name for the descriptor file
        create_type : str
            VMDK create type (monolithicFlat, twoGbMaxExtentSparse, etc.)
        extents : list of (access, size_sectors, type, filename)
            List of extent definitions
        cid : str
            Content ID (hex string)
        adapter_type : str
            Adapter type (lsilogic, buslogic, ide)
        hw_version : str
            Virtual hardware version

        Returns
        -------
        str
            Path to created descriptor file
        """
        descriptor_path = self.output_dir / f"{name}.vmdk"

        content = [
            "# Disk DescriptorFile",
            "version=1",
            f"CID={cid}",
            "parentCID=ffffffff",
            f'createType="{create_type}"',
            "",
            "# Extent description",
        ]

        for access, size, extent_type, filename in extents:
            content.append(f'{access} {size} {extent_type} "{filename}"')

        content.extend([
            "",
            "# The Disk Data Base",
            f'ddb.virtualHWVersion = "{hw_version}"',
            'ddb.geometry.cylinders = "2610"',
            'ddb.geometry.heads = "255"',
            'ddb.geometry.sectors = "63"',
            f'ddb.adapterType = "{adapter_type}"',
            "",
        ])

        descriptor_path.write_text("\n".join(content))
        return str(descriptor_path)

    def _create_raw_extent(self, name: str, size_bytes: int) -> str:
        """Create a raw extent file filled with zeros."""
        extent_path = self.output_dir / name

        # Create sparse file
        with open(extent_path, "wb") as f:
            f.seek(size_bytes - 1)
            f.write(b"\0")

        return str(extent_path)

    def _build_simple(self) -> None:
        """Build a simple raw disk image."""
        info("Creating simple raw disk image")

        img_path = self.output_dir / "simple.raw"

        # Create a simple raw image
        with open(img_path, "wb") as f:
            f.seek(IMAGE_SIZE_SMALL - 1)
            f.write(b"\0")

        self.images.append(str(img_path))
        success(f"Created {img_path.name}")

    def _build_vmdk_descriptor(self) -> None:
        """Build VMDK descriptor with flat extent."""
        info("Creating VMDK descriptor with flat extent")

        # Calculate extent size in sectors (100 MiB)
        extent_size_sectors = IMAGE_SIZE_SMALL // SECTOR_SIZE

        # Create the flat extent
        extent_name = "test-flat.vmdk"
        extent_path = self._create_raw_extent(extent_name, IMAGE_SIZE_SMALL)

        # Create the descriptor
        descriptor = self._create_vmdk_descriptor(
            "test",
            "monolithicFlat",
            [("RW", extent_size_sectors, "FLAT", extent_name)],
        )

        self.images.extend([descriptor, extent_path])
        success(f"Created VMDK descriptor pair: test.vmdk + {extent_name}")

    def _build_multi_extent(self) -> None:
        """Build VMDK with multiple extent files (split sparse)."""
        info("Creating multi-extent VMDK")

        # Create 3 extents of 100 MiB each
        extent_size_sectors = IMAGE_SIZE_SMALL // SECTOR_SIZE
        extents = []

        for i in range(1, 4):
            extent_name = f"test-s{i:03d}.vmdk"
            extent_path = self._create_raw_extent(extent_name, IMAGE_SIZE_SMALL)
            extents.append(("RW", extent_size_sectors, "SPARSE", extent_name))
            self.images.append(extent_path)

        # Create descriptor
        descriptor = self._create_vmdk_descriptor(
            "test-multi",
            "twoGbMaxExtentSparse",
            extents,
        )

        self.images.append(descriptor)
        success(f"Created multi-extent VMDK with 3 extents")

    def _build_security_tests(self) -> None:
        """Build test images for security validation."""
        info("Creating security test images")

        # 1. Path traversal attempt in descriptor
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            malicious_dir = self.output_dir / "malicious"
            malicious_dir.mkdir(exist_ok=True)

            descriptor = malicious_dir / "traversal.vmdk"
            descriptor.write_text("""# Disk DescriptorFile
version=1
CID=12345678
createType="monolithicFlat"

# Extent description - attempts path traversal
RW 204800 FLAT "../../../etc/passwd"

ddb.virtualHWVersion = "14"
ddb.adapterType = "lsilogic"
""")
            self.images.append(str(descriptor))
            success("Created path traversal test descriptor")

        except Exception as e:
            warn(f"Could not create security test images: {e}")

        # 2. Valid subdirectory reference
        try:
            subdir = self.output_dir / "subdir"
            subdir.mkdir(exist_ok=True)

            extent_path = self._create_raw_extent("subdir/extent.vmdk", IMAGE_SIZE_SMALL // 10)

            descriptor = self.output_dir / "subdir-test.vmdk"
            descriptor.write_text("""# Disk DescriptorFile
version=1
CID=12345678
createType="monolithicFlat"

# Extent description - legitimate subdirectory
RW 204800 FLAT "subdir/extent.vmdk"

ddb.virtualHWVersion = "14"
ddb.adapterType = "lsilogic"
""")
            self.images.extend([str(descriptor), extent_path])
            success("Created subdirectory reference test")

        except Exception as e:
            warn(f"Could not create subdirectory test: {e}")

        # 3. Large descriptor (should be rejected)
        try:
            large_desc = self.output_dir / "large.vmdk"
            # Create descriptor larger than 8 MiB
            large_content = "# " + ("A" * 10 * 1024 * 1024)
            large_desc.write_text(large_content)
            self.images.append(str(large_desc))
            success("Created large descriptor test")

        except Exception as e:
            warn(f"Could not create large descriptor: {e}")

        # 4. Binary file (should not be treated as descriptor)
        try:
            binary = self.output_dir / "binary.vmdk"
            binary.write_bytes(b"KDMV\x00\x00\x00\x01" + b"\x00" * 1000)
            self.images.append(str(binary))
            success("Created binary file test")

        except Exception as e:
            warn(f"Could not create binary test: {e}")

    def run(self) -> None:
        """Execute the image creation."""
        info(f"Building layout: {self.layout.upper()}")

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Build requested layout(s)
        if self.layout == "simple":
            self._build_simple()
        elif self.layout == "vmdk-descriptor":
            self._build_vmdk_descriptor()
        elif self.layout == "multi-extent":
            self._build_multi_extent()
        elif self.layout == "security":
            self._build_security_tests()
        elif self.layout == "all":
            self._build_simple()
            self._build_vmdk_descriptor()
            self._build_multi_extent()
            self._build_security_tests()
        else:
            error(f"Unknown layout: {self.layout}")

        success(f"Created {len(self.images)} test file(s)")


def main() -> None:
    """Parse arguments and run the creator."""
    parser = argparse.ArgumentParser(
        description="Create test disk images for hyper2kvm",
        epilog="Layouts: simple, vmdk-descriptor, multi-extent, security, all",
    )

    parser.add_argument(
        "layout",
        help="Image layout (simple, vmdk-descriptor, multi-extent, security, all)",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory for output images",
    )

    args = parser.parse_args()

    # Create and run
    creator = TestImageCreator(args.layout, args.output_dir.resolve())
    creator.run()

    print("\n✓ Test images ready!")


if __name__ == "__main__":
    main()
