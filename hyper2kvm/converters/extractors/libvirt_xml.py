# SPDX-License-Identifier: LGPL-3.0-or-later
"""Libvirt domain XML parser and Artifact Manifest v1 generator."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ...core.utils import U


class LibvirtXML:
    """
    Parse libvirt domain XML and generate Artifact Manifest v1.

    This extractor enables importing existing libvirt VMs into hyper2kvm
    by parsing their domain XML configuration and discovering disk artifacts.

    Capabilities:
    - Parse disk paths and formats from libvirt domain XML
    - Extract network configuration (interfaces, bridges, MAC addresses)
    - Detect firmware type (BIOS/UEFI)
    - Extract memory/CPU settings
    - Extract OS metadata (type, distro hints)
    - Generate complete Artifact Manifest v1 for conversion

    Security:
    - Uses defusedxml if available to mitigate XML entity expansion
    - Validates disk paths exist before including in manifest
    - Safe path handling for disk artifacts
    """

    @staticmethod
    def parse_domain_xml(
        logger: logging.Logger | None,
        xml_path: Path,
        output_dir: Path | None = None,
        *,
        compute_checksums: bool = True,
        manifest_filename: str = "manifest.json",
    ) -> dict[str, Any]:
        """
        Parse libvirt domain XML and generate Artifact Manifest v1.

        Args:
            logger: Logger instance
            xml_path: Path to libvirt domain XML file
            output_dir: Output directory for manifest (defaults to xml_path.parent)
            compute_checksums: Whether to compute SHA256 checksums for disks
            manifest_filename: Manifest filename (default: "manifest.json")

        Returns:
            dict: Artifact Manifest v1 dictionary

        Raises:
            FileNotFoundError: If XML file doesn't exist
            ET.ParseError: If XML is invalid
        """
        U.banner(logger, "Parse Libvirt Domain XML")

        # Helper for safe logging
        def log_info(msg: str) -> None:
            if logger:
                logger.info(msg)

        def log_warning(msg: str) -> None:
            if logger:
                logger.warning(msg)

        xml_path = Path(xml_path).resolve()
        if not xml_path.exists():
            U.die(logger, f"Domain XML not found: {xml_path}", 1)

        if not xml_path.is_file():
            U.die(logger, f"Domain XML is not a file: {xml_path}", 1)

        log_info(f"Domain XML: {xml_path}")

        # Prefer defusedxml if available
        try:
            from defusedxml.ElementTree import parse as safe_parse  # type: ignore
        except ImportError:
            safe_parse = None

        try:
            tree = safe_parse(xml_path) if safe_parse else ET.parse(xml_path)
        except ET.ParseError as e:
            U.die(logger, f"Failed to parse domain XML: {e}", 1)
        except Exception as e:
            U.die(logger, f"Failed to read domain XML: {e}", 1)

        root = tree.getroot()

        # Extract domain metadata
        domain_name = LibvirtXML._get_text(root, "name", "unknown")
        domain_uuid = LibvirtXML._get_text(root, "uuid")

        log_info(f"Domain: {domain_name}")
        if domain_uuid:
            log_info(f"UUID:   {domain_uuid}")

        # Extract firmware type
        firmware = LibvirtXML._detect_firmware(root)
        log_info(f"Firmware: {firmware}")

        # Extract OS metadata
        os_type, os_distro = LibvirtXML._extract_os_metadata(root)
        log_info(f"OS Type: {os_type}")

        # Extract disks
        disks = LibvirtXML._extract_disks(logger, root, compute_checksums)
        if not disks:
            U.die(logger, "No disks found in domain XML", 1)

        log_info(f"Disks: {len(disks)} found")
        for disk in disks:
            log_info(f"  - {disk['id']}: {disk['local_path']} ({disk['source_format']})")

        # Extract network interfaces
        networks = LibvirtXML._extract_networks(logger, root)
        if networks:
            log_info(f"Networks: {len(networks)} interface(s)")
            for net in networks:
                log_info(f"  - {net.get('type', 'unknown')}: {net.get('source', 'unknown')}")

        # Extract memory and vcpus
        memory_bytes = LibvirtXML._extract_memory(root)
        vcpus = LibvirtXML._extract_vcpus(root)

        if memory_bytes:
            log_info(f"Memory: {U.human_bytes(memory_bytes)}")
        if vcpus:
            log_info(f"vCPUs: {vcpus}")

        # Build Artifact Manifest v1
        manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "libvirt",
                "vm_id": domain_uuid or domain_name,
                "vm_name": domain_name,
                "hypervisor_version": "unknown",
                "export_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "libvirt_xml_path": str(xml_path),
            },
            "disks": disks,
            "firmware": {"type": firmware},
            "os_hint": os_distro if os_distro != "unknown" else os_type,
        }

        # Add network metadata if present
        if networks:
            manifest["metadata"] = {
                "networks": networks,
                "memory_bytes": memory_bytes,
                "vcpus": vcpus,
            }

        # Add pipeline configuration with sensible defaults
        manifest["pipeline"] = {
            "inspect": {"enabled": True, "collect_guest_info": False},
            "fix": {
                "enabled": True,
                "backup": True,
                "update_grub": True,
                "regen_initramfs": True,
                "fstab_mode": "stabilize-all",
            },
            "convert": {"enabled": True, "compress": True, "compress_level": 6},
            "validate": {"enabled": True, "check_image_integrity": True},
        }

        # Default output configuration
        if output_dir:
            manifest["output"] = {
                "directory": str(output_dir),
                "format": "qcow2",
            }
        else:
            manifest["output"] = {"format": "qcow2"}

        # Write manifest
        output_path = (output_dir or xml_path.parent) / manifest_filename
        LibvirtXML._write_manifest(logger, manifest, output_path)

        return manifest

    @staticmethod
    def _get_text(root: ET.Element, tag: str, default: str | None = None) -> str | None:
        """Get text content of a direct child element."""
        elem = root.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return default

    @staticmethod
    def _detect_firmware(root: ET.Element) -> str:
        """
        Detect firmware type (BIOS or UEFI) from domain XML.

        Looks for:
        - <os><loader type="pflash"> indicates UEFI
        - <os firmware="efi"> indicates UEFI
        - Otherwise assume BIOS
        """
        os_elem = root.find("os")
        if os_elem is None:
            return "bios"

        # Check for loader element (UEFI)
        loader = os_elem.find("loader")
        if loader is not None:
            loader_type = loader.get("type", "")
            if "pflash" in loader_type.lower():
                return "uefi"

        # Check firmware attribute
        firmware_attr = os_elem.get("firmware", "")
        if firmware_attr and "efi" in firmware_attr.lower():
            return "uefi"

        # Check if loader path contains "OVMF" (common UEFI firmware)
        if loader is not None and loader.text:
            if "OVMF" in loader.text or "ovmf" in loader.text:
                return "uefi"

        return "bios"

    @staticmethod
    def _extract_os_metadata(root: ET.Element) -> tuple[str, str]:
        """
        Extract OS type and distro hints from domain XML.

        Returns:
            (os_type, os_distro): e.g., ("linux", "rhel9")
        """
        os_elem = root.find("os")
        if os_elem is None:
            return ("unknown", "unknown")

        # Get OS type
        type_elem = os_elem.find("type")
        os_type = "unknown"
        if type_elem is not None and type_elem.text:
            os_type = type_elem.text.strip().lower()
            if os_type == "hvm":
                os_type = "linux"  # Default assumption

        # Try to extract distro from metadata (if present)
        metadata_elem = root.find("metadata")
        os_distro = "unknown"

        if metadata_elem is not None:
            # Check for libosinfo metadata
            for ns_uri in [
                "http://libosinfo.org/xmlns/libvirt/domain/1.0",
                "libosinfo",
            ]:
                ns = {"libosinfo": ns_uri} if ns_uri.startswith("http") else {}

                libosinfo = metadata_elem.find("libosinfo:libosinfo", ns) if ns else None
                if libosinfo is None:
                    libosinfo = metadata_elem.find("libosinfo")

                if libosinfo is not None:
                    os_elem_info = libosinfo.find("{%s}os" % ns_uri) if ns else libosinfo.find("os")
                    if os_elem_info is not None:
                        os_id = os_elem_info.get("id", "")
                        if os_id:
                            # Extract distro from OS ID (e.g., "http://redhat.com/rhel/9.0")
                            if "rhel" in os_id.lower():
                                os_distro = "rhel9" if "9" in os_id else "rhel"
                            elif "ubuntu" in os_id.lower():
                                os_distro = "ubuntu22" if "22" in os_id else "ubuntu"
                            elif "debian" in os_id.lower():
                                os_distro = "debian"
                            elif "centos" in os_id.lower():
                                os_distro = "centos"
                            elif "fedora" in os_id.lower():
                                os_distro = "fedora"
                            break

        return (os_type, os_distro)

    @staticmethod
    def _extract_disks(
        logger: logging.Logger | None,
        root: ET.Element,
        compute_checksums: bool,
    ) -> list[dict[str, Any]]:
        """
        Extract disk artifacts from domain XML.

        Parses <devices><disk> elements to find disk paths, formats, and types.
        """
        devices = root.find("devices")
        if devices is None:
            return []

        disks: list[dict[str, Any]] = []
        boot_order = 0

        for disk_elem in devices.findall("disk"):
            disk_type = disk_elem.get("type", "file")
            device_type = disk_elem.get("device", "disk")

            # Skip CD-ROMs and floppies
            if device_type in ("cdrom", "floppy"):
                continue

            # Get source path
            source = disk_elem.find("source")
            if source is None:
                continue

            source_path = None
            if disk_type == "file":
                source_path = source.get("file")
            elif disk_type == "block":
                source_path = source.get("dev")

            if not source_path:
                continue

            disk_path = Path(source_path).resolve()

            # Skip if disk doesn't exist
            if not disk_path.exists():
                if logger:
                    logger.warning(f"Disk not found (skipping): {disk_path}")
                continue

            if not disk_path.is_file():
                if logger:
                    logger.warning(f"Disk is not a file (skipping): {disk_path}")
                continue

            # Get disk format
            driver = disk_elem.find("driver")
            source_format = "raw"  # Default
            if driver is not None:
                source_format = driver.get("type", "raw")

            # Get target device name (e.g., vda, sda)
            target = disk_elem.find("target")
            target_dev = "disk"
            if target is not None:
                target_dev = target.get("dev", "disk")

            # Determine disk type (boot vs data)
            # First disk is typically boot, others are data
            disk_id = target_dev if target_dev != "disk" else f"disk{len(disks)}"
            is_boot = len(disks) == 0

            # Get disk size
            stat = disk_path.stat()
            disk_bytes = stat.st_size

            # Compute checksum if requested
            checksum = None
            if compute_checksums:
                if logger:
                    logger.info(f"Computing SHA256 for {disk_id}...")
                checksum = LibvirtXML._compute_sha256(disk_path)

            disks.append({
                "id": disk_id,
                "source_format": source_format,
                "local_path": str(disk_path),
                "bytes": disk_bytes,
                "checksum": checksum,
                "boot_order_hint": boot_order if is_boot else boot_order + len(disks),
                "disk_type": "boot" if is_boot else "data",
            })

            boot_order += 1

        return disks

    @staticmethod
    def _extract_networks(
        logger: logging.Logger | None,
        root: ET.Element,
    ) -> list[dict[str, Any]]:
        """
        Extract network interface configuration from domain XML.

        Returns list of network interface metadata for reference.
        """
        devices = root.find("devices")
        if devices is None:
            return []

        networks: list[dict[str, Any]] = []

        for iface in devices.findall("interface"):
            iface_type = iface.get("type", "unknown")

            net_info: dict[str, Any] = {"type": iface_type}

            # Get source (network, bridge, etc.)
            source = iface.find("source")
            if source is not None:
                if iface_type == "network":
                    net_info["source"] = source.get("network", "unknown")
                elif iface_type == "bridge":
                    net_info["source"] = source.get("bridge", "unknown")
                else:
                    net_info["source"] = source.get("dev", "unknown")

            # Get MAC address
            mac = iface.find("mac")
            if mac is not None:
                net_info["mac"] = mac.get("address")

            # Get model
            model = iface.find("model")
            if model is not None:
                net_info["model"] = model.get("type", "virtio")

            networks.append(net_info)

        return networks

    @staticmethod
    def _extract_memory(root: ET.Element) -> int | None:
        """Extract memory size in bytes from domain XML."""
        memory_elem = root.find("memory")
        if memory_elem is None or not memory_elem.text:
            return None

        try:
            # Memory is in KiB by default
            unit = memory_elem.get("unit", "KiB")
            value = int(memory_elem.text.strip())

            # Convert to bytes
            if unit == "b":
                return value
            elif unit == "KiB" or unit == "KB":
                return value * 1024
            elif unit == "MiB" or unit == "MB":
                return value * 1024 * 1024
            elif unit == "GiB" or unit == "GB":
                return value * 1024 * 1024 * 1024
            else:
                return value * 1024  # Default to KiB
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _extract_vcpus(root: ET.Element) -> int | None:
        """Extract vCPU count from domain XML."""
        vcpu_elem = root.find("vcpu")
        if vcpu_elem is None or not vcpu_elem.text:
            return None

        try:
            return int(vcpu_elem.text.strip())
        except ValueError:
            return None

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Compute SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192 * 1024):  # 8MB chunks
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    @staticmethod
    def _write_manifest(
        logger: logging.Logger | None,
        manifest: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Write Artifact Manifest v1 to JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically (temp + replace)
        import tempfile

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(output_path.parent),
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )

        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=False)
                f.write("\n")

            import os
            os.replace(tmp_path, str(output_path))

            if logger:
                logger.info(f"✅ Manifest written: {output_path}")

        except Exception:
            # Clean up temp file on error
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
            raise
